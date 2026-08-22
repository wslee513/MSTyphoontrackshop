# -*- coding: utf-8 -*-
"""從 Open-Meteo 拉取 Google WeatherNext 2 對颱風軌跡的 AI 預報。

走「Open-Meteo 免費免金鑰」路線（ensemble-api.open-meteo.com），
不需 Google 帳號/GCP。輸入是 pipeline 的 output/各國颱風路徑.json，
沿每顆颱風的預報軌跡各 tau 點（優先 CWA，缺位用其他機構平均補位），
抓該座標的 WeatherNext 風速/氣壓/氣溫，
輸出 output/weathernext_各國颱風路徑.json 供比對（各國機構 vs AI 模型）。

執行：python fetch_weathernext.py
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

OUTPUT_DIR = "output"
DATA_JSON = "各國颱風路徑.json"
OUT_JSON = "weathernext_各國颱風路徑.json"

API = "https://ensemble-api.open-meteo.com/v1/ensemble"
# google_weathernext2_ensemble_mean：Open-Meteo 算好的 64 成員平均（回傳小）
# 若要個別成員，改 models=google_weathernext2_ensemble（回傳會大很多）
MODEL = "google_weathernext2_ensemble_mean"
HOURLY_VARS = "wind_speed_10m,wind_speed_100m,pressure_msl,temperature_2m"
# native：保留 WeatherNext 原生 6 小時解析度（資料最短，最貼近模型）
TEMP_RES = "native"

CWA_AGENCY = "CWA"


def load_latest(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    typhoons = raw.get("typhoons", [])
    return typhoons


def iter_track_points(info):
    """從最新 entry 所有機構的預報軌跡，依 tau 合併出 (tau, datetime_utc, lat, lon)。

    取每個 tau 的代表座標：優先 CWA，其次各機構平均，取不到才跳過。
    這樣即使 CWA 只有 tau=0，也能用其他機構的 +24/48/72... 拼出完整路徑。
    """
    agencies = info.get("agencies", [])
    if not agencies:
        return
    by_tau = {}
    for ag in agencies:
        for fc in ag.get("forecasts", []):
            tau = fc.get("tau", 0)
            if fc.get("lat") is None or fc.get("lon") is None:
                continue
            by_tau.setdefault(tau, []).append((ag.get("agency"), float(fc["lat"]), float(fc["lon"])))
    for tau in sorted(by_tau):
        pts = by_tau[tau]
        cwa_pt = next((p for p in pts if p[0] == CWA_AGENCY), None)
        if cwa_pt is not None:
            lat, lon = cwa_pt[1], cwa_pt[2]
        else:
            lat = sum(p[1] for p in pts) / len(pts)
            lon = sum(p[2] for p in pts) / len(pts)
        yield tau, lat, lon, ""


def fetch_weathernext(lat, lon, forecast_days=6, timeout=30):
    """抓單一座標的 WeatherNext 6 小時風速/氣壓/氣溫序列。"""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": HOURLY_VARS,
        "models": MODEL,
        "temporal_resolution": TEMP_RES,
        "forecast_days": forecast_days,
        "timezone": "UTC",
        "cell_selection": "sea",  # 颱風多在海上，避免選到陸地格點
        "wind_speed_unit": "kn",
    }
    r = requests.get(API, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def utc_to_iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    src = os.path.join(OUTPUT_DIR, DATA_JSON)
    if not os.path.exists(src):
        print(f"找不到 {src}，請先執行 python fetch_typhoon2000.py")
        return 1
    typhoons = load_latest(src)
    if not typhoons:
        print("JSON 中沒有颱風資料。")
        return 1

    result = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
              "source": "Open-Meteo Google WeatherNext 2 Ensemble Mean (free API)",
              "api": API, "model": MODEL, "variable_unit": "kn (wind), hPa (pressure), degC (temp)",
              "typhoons": []}

    for info in typhoons:
        name = info.get("storm_name", "?")
        print(f"== {name} ==")
        points = list(iter_track_points(info))
        if not points:
            print("  無預報軌跡點，跳過")
            continue
        entry = {"storm_name": name, "forecast_time_utc": info.get("forecast_time_utc", ""), "points": []}
        base = None
        ft = info.get("forecast_time_utc", "")
        if ft:
            try:
                base = datetime.strptime(ft, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
            except ValueError:
                base = None

        for tau, lat, lon, datetime_z in points:
            try:
                data = fetch_weathernext(lat, lon)
            except Exception as e:
                print(f"  tau={tau} ({lat:.1f},{lon:.1f}) 失敗: {e}")
                continue
            h = data.get("hourly", {})
            times, ws10 = h.get("time", []), h.get("wind_speed_10m", [])
            ws100 = h.get("wind_speed_100m", [])
            pmsl = h.get("pressure_msl", [])
            t2m = h.get("temperature_2m", [])
            if not times:
                continue
            # 找最接近 tau 小時的 6 小時步
            target = base + timedelta(hours=tau) if base else None
            idx = 0
            if target:
                best, idx = 1e12, 0
                for i, t in enumerate(times):
                    try:
                        tt = datetime.strptime(t, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                    d = abs((tt - target).total_seconds())
                    if d < best:
                        best, idx = d, i
            pt = {"tau": tau, "lat": round(lat, 2), "lon": round(lon, 2),
                  "time_utc": times[idx] if idx < len(times) else None}
            if idx < len(ws10):
                pt["wind_kt_10m"] = ws10[idx]
            if idx < len(ws100):
                pt["wind_kt_100m"] = ws100[idx]
            if idx < len(pmsl):
                pt["pressure_hpa"] = pmsl[idx]
            if idx < len(t2m):
                pt["temp_c"] = t2m[idx]
            entry["points"].append(pt)
            print(f"  tau={tau:>3} ({lat:.1f},{lon:.1f}) -> "
                  f"{pt.get('time_utc')} 風{pt.get('wind_kt_10m')}kn 壓{pt.get('pressure_hpa')}hPa")
        result["typhoons"].append(entry)

    out = os.path.join(OUTPUT_DIR, OUT_JSON)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
