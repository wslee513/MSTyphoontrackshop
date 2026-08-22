# -*- coding: utf-8 -*-
"""從 ECMWF Open Data 拉取 HRES / ENS 熱帶氣旋路徑預報。

來源：ECMWF Open Data（免費、CC-BY-4.0、免金鑰）
  - HRES: https://data.ecmwf.int/forecasts/... stream=oper,  type=tf
  - ENS : 同上 stream=enfo, type=tf（一檔含 51 個 ensemble 成員）
  - 00/12z run → step=360（15 天）；06/18z run → step=144
  - 只有當該 run 有觀測到/預報出颱風時才會有資料（否則 404）
檔案格式為 BUFR（edition 4），需 eccodes 解碼（ranked-key 方式，見下方）。

輸入：output/各國颱風路徑.json（取颱風名稱做比對）
輸出：output/ecmwf_各國颱風路徑.json（HRES + ENS 軌跡，供 plot_web.py 畫圖）

執行：python fetch_ecmwf.py
"""
import io
import json
import os
import sys
import contextlib
from datetime import datetime, timedelta, timezone

import numpy as np

OUTPUT_DIR = "output"
DATA_JSON = "各國颱風路徑.json"
OUT_JSON = "ecmwf_各國颱風路徑.json"

try:
    from ecmwf.opendata import Client
except ImportError:
    Client = None

try:
    import eccodes
except ImportError:
    eccodes = None

# 各 run 產品的釋出時間（相對 run 時刻的小時數）
RELEASE_HOURS = {0: 6 + 55 / 60, 6: 12 + 12 / 60, 12: 18 + 55 / 60, 18: 24 + 12 / 60}
STEP_BY_HOUR = {0: 360, 6: 144, 12: 360, 18: 144}
MISSING = -1e+100
MISSING_I = -2147483647


def latest_runs(now_utc):
    """回傳已釋出的 (date_str, run_hour) 候選清單。
    優先取 step 較長的 run（00z/12z step=360 優先於 06z/18z step=144），
    同 step 長度內由新到舊。"""
    runs = []
    for day_offset in range(0, 3):
        day = (now_utc - timedelta(days=day_offset)).date()
        for h in (0, 6, 12, 18):
            run_dt = datetime(day.year, day.month, day.day, h, tzinfo=timezone.utc)
            avail = run_dt + timedelta(hours=RELEASE_HOURS[h])
            if avail <= now_utc:
                runs.append((run_dt.strftime("%Y%m%d"), h))
    runs.sort(key=lambda r: (STEP_BY_HOUR.get(r[1], 0), r[0], r[1]), reverse=True)
    return runs


def download_run(client, date_str, run_hour, stream, step, target):
    if Client is None:
        raise RuntimeError("未安裝 ecmwf-opendata：pip install ecmwf-opendata")
    client.retrieve(date=date_str, time=run_hour, stream=stream, type="tf",
                    step=step, target=target)


def get(msg, key):
    try:
        return eccodes.codes_get(msg, key)
    except Exception:
        return None


def rank_get_array(msg, rank, key):
    try:
        return list(np.atleast_1d(eccodes.codes_get_array(msg, f"#{rank}#{key}")))
    except Exception:
        return None


def decode_bufr(path):
    """解出 {storm_id: {'name':..., 'long_name':..., 'members': {member: [points]}}}。

    points 依 forecast period（step_h）與 member 對齊：
      lat/lon = 暴風中心位置、pmsl_hpa = 中心氣壓、wind_ms = 最大 10m 風速。
    """
    storms = {}
    with open(path, "rb") as fh, contextlib.redirect_stderr(io.StringIO()):
        while True:
            msg = eccodes.codes_bufr_new_from_file(fh)
            if msg is None:
                break
            try:
                eccodes.codes_set(msg, "unpack", 1)
                sid = get(msg, "stormIdentifier")
                name = str(get(msg, "longStormName") or "").strip()
                members = list(np.atleast_1d(eccodes.codes_get_array(msg, "ensembleMemberNumber")))
                if sid is None:
                    continue
                st = storms.setdefault(sid, {"name": name, "members": {}})
                if name:
                    st["name"] = name

                nper = 0
                while rank_get_array(msg, nper + 1, "timePeriod") is not None:
                    nper += 1

                latA = rank_get_array(msg, 2, "latitude")
                lonA = rank_get_array(msg, 2, "longitude")
                presA = rank_get_array(msg, 1, "pressureReducedToMeanSeaLevel")
                latW0 = rank_get_array(msg, 3, "latitude")
                lonW0 = rank_get_array(msg, 3, "longitude")
                wind0 = rank_get_array(msg, 1, "windSpeedAt10M")

                def pick(vals, k):
                    return vals[k] if vals and k < len(vals) else None

                n = len(members) or 1
                for k in range(n):
                    m = int(members[k]) if members else 51
                    pts = st["members"].setdefault(m, [])
                    pts.append({
                        "step_h": 0,
                        "lat": pick(latA, k), "lon": pick(lonA, k),
                        "pmsl_hpa": pick(presA, k) / 100 if pick(presA, k) is not None else None,
                        "wind_ms": pick(wind0, k),
                    })

                sig_rank, pos_rank, pres_rank, wind_rank = 3, 3, 1, 1
                for i in range(2, nper + 1):
                    sig_rank += 1
                    pos_rank += 1
                    latC = rank_get_array(msg, pos_rank, "latitude")
                    lonC = rank_get_array(msg, pos_rank, "longitude")
                    pres_rank += 1
                    presC = rank_get_array(msg, pres_rank, "pressureReducedToMeanSeaLevel")
                    sig_rank += 1
                    pos_rank += 1
                    latW = rank_get_array(msg, pos_rank, "latitude")
                    lonW = rank_get_array(msg, pos_rank, "longitude")
                    wind_rank += 1
                    windF = rank_get_array(msg, wind_rank, "windSpeedAt10M")
                    tp = rank_get_array(msg, i, "timePeriod")
                    step = int(tp[0]) if tp and tp[0] is not None and tp[0] != MISSING_I else None
                    for k in range(n):
                        m = int(members[k]) if members else 51
                        pts = st["members"].setdefault(m, [])
                        pts.append({
                            "step_h": step,
                            "lat": pick(latC, k), "lon": pick(lonC, k),
                            "pmsl_hpa": pick(presC, k) / 100 if pick(presC, k) is not None else None,
                            "wind_ms": pick(windF, k),
                        })
            except Exception as e:
                print(f"  (message 解碼失敗: {e})")
            finally:
                eccodes.codes_release(msg)
    return storms


def clean_points(points):
    out = []
    for p in points:
        lat, lon = p["lat"], p["lon"]
        if lat is None or lat == MISSING or lon is None or lon == MISSING:
            continue

        def cv(v):
            return v if v is not None and v != MISSING else None

        out.append({
            "tau": p["step_h"],
            "lat": round(lat, 2), "lon": round(lon, 2),
            "pmsl_hpa": cv(p["pmsl_hpa"]),
            "wind_ms": round(cv(p["wind_ms"]), 1) if cv(p["wind_ms"]) is not None else None,
        })
    return out


def valid(p):
    return p["lat"] not in (None, MISSING) and p["lon"] not in (None, MISSING)


def member_mean(members_points):
    """把各成員的點依 step 平均成 ensemble mean 軌跡。"""
    by_step = {}
    for pts in members_points:
        for p in pts:
            if valid(p):
                by_step.setdefault(p["step_h"], []).append(p)
    mean = []
    for step in sorted(by_step):
        pts = by_step[step]
        n = len(pts)
        lat = sum(p["lat"] for p in pts) / n
        lon = sum(p["lon"] for p in pts) / n
        pmsl = [p["pmsl_hpa"] for p in pts if p["pmsl_hpa"] is not None]
        wind = [p["wind_ms"] for p in pts if p["wind_ms"] is not None]
        mean.append({
            "tau": step,
            "lat": round(lat, 2), "lon": round(lon, 2),
            "pmsl_hpa": round(sum(pmsl) / len(pmsl), 1) if pmsl else None,
            "wind_ms": round(sum(wind) / len(wind), 1) if wind else None,
            "n": n,
        })
    return mean


def match_typhoon(storm, names):
    """以 ECMWF 名稱（longStormName）比對 pipeline 的 storm_name。"""
    for n in names:
        if n and n.upper() == storm.get("name", "").upper():
            return n
    return None


def main():
    src = os.path.join(OUTPUT_DIR, DATA_JSON)
    if not os.path.exists(src):
        print(f"找不到 {src}，請先執行 python fetch_typhoon2000.py")
        return 1
    with open(src, "r", encoding="utf-8") as f:
        raw = json.load(f)
    typhoons = raw.get("typhoons", [])
    names = [t.get("storm_name") for t in typhoons]
    if not names:
        print("JSON 中沒有颱風資料。")
        return 1

    if eccodes is None:
        print("未安裝 eccodes：pip install eccodes")
        return 1

    now = datetime.now(timezone.utc)

    result = {"generated_at": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
              "source": "ECMWF Open Data TC-track BUFR (CC-BY-4.0)",
              "run": None, "typhoons": []}

    SOURCES = ["ecmwf", "aws", "google", "azure"]
    used = None
    used_source = None
    for date_str, run_hour in latest_runs(now):
        step = STEP_BY_HOUR[run_hour]
        hres_path = os.path.join(OUTPUT_DIR, f"_tmp_ecmwf_hres_{date_str}_{run_hour}.bufr")
        ens_path = os.path.join(OUTPUT_DIR, f"_tmp_ecmwf_ens_{date_str}_{run_hour}.bufr")
        for src in SOURCES:
            client = Client(source=src)
            try:
                print(f"下載 {date_str} {run_hour:02d}z (HRES+ENS, step={step}) [{src}] ...")
                download_run(client, date_str, run_hour, "oper", step, hres_path)
                download_run(client, date_str, run_hour, "enfo", step, ens_path)
                used = {"date": date_str, "run_hour": run_hour, "step": step}
                used_source = src
                break
            except Exception as e:
                print(f"  {src}: {e}")
                for p in (hres_path, ens_path):
                    if os.path.exists(p):
                        os.remove(p)
                continue
        if used:
            break

    if used is None:
        print("無法取得任何 ECMWF TC-track 資料（可能該時段無觀測/預報颱風）。")
        return 1

    result["run"] = f"{used['date']}/{used['run_hour']:02d}z (step={used['step']})"

    try:
        hres_storms = decode_bufr(hres_path)
        ens_storms = decode_bufr(ens_path)
    finally:
        for p in (hres_path, ens_path):
            if os.path.exists(p):
                os.remove(p)

    n_match = 0
    for info in typhoons:
        name = info.get("storm_name")
        entry = {"storm_name": name, "hres": [], "ens_mean": [], "ens_control": [], "ens_members": 0}

        # HRES：oper 檔單一軌跡（member=51 或唯一 key）
        for sid, st in hres_storms.items():
            if match_typhoon(st, [name]) == name:
                mkey = max(st["members"], key=lambda k: len(st["members"][k]))
                entry["hres"] = clean_points(st["members"][mkey])
                break

        # ENS：control(member 51) + 全部成員平均
        for sid, st in ens_storms.items():
            if match_typhoon(st, [name]) == name:
                members = st["members"]
                entry["ens_members"] = len(members)
                if 51 in members:
                    entry["ens_control"] = clean_points(members[51])
                elif members:
                    mkey = max(members, key=lambda k: len(members[k]))
                    entry["ens_control"] = clean_points(members[mkey])
                entry["ens_mean"] = member_mean(list(members.values()))
                break

        if entry["hres"] or entry["ens_mean"]:
            n_match += 1
            result["typhoons"].append(entry)
            print(f"== {name} ==")
            print(f"   HRES 點數: {len(entry['hres'])}  ENS 點數: {len(entry['ens_mean'])} (成員 {entry['ens_members']})")

    if n_match == 0:
        print("ECMWF 資料中沒有與目前颱風相符的軌跡。")
        return 1

    out = os.path.join(OUTPUT_DIR, OUT_JSON)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
