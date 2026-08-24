"""
Typhoon2000.ph Multi-Agency TC Forecast Parser

Fetches the latest multi-agency tropical cyclone forecast data from
typhoon2000.ph and extracts structured data from all available agencies
(HKO, JTWC, JMA, NMC, CWA, KMA, PAGASA, etc.).
"""

import json
import os
import re
import sys
import urllib.parse
from datetime import datetime

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://www.typhoon2000.ph/multi/log.php"
CWA_API_URL = (
    "https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0034-005"
)


def load_config(path="config.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_page(typhoon_name):
    params = {"name": typhoon_name}
    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    print(f"Fetching: {url}")
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def extract_text_entries(html):
    pattern = re.compile(r'text\[(\d+)\]\s*=\s*"((?:[^"\\]|\\.)*)"')
    matches = []
    for m in pattern.finditer(html):
        idx = int(m.group(1))
        raw = m.group(2)
        text = raw.replace("\\n", "\n").replace('\\"', '"')
        matches.append((idx, text))
    matches.sort(key=lambda x: x[0])
    return matches


def parse_agency_block(lines, start):
    """Parse one agency block starting at line `start` in the text lines.
    Returns (agency_name, entries_list, next_line_index).
    entries_list: [{"tau": 0, "lat": ..., "lon": ..., "wind": ...}, ...]
    """
    if start >= len(lines):
        return None, start
    header = lines[start].strip()
    if not header.endswith(":"):
        return None, start
    agency = header.rstrip(":")
    entries = []
    i = start + 1
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.endswith(":") and re.match(r"^[A-Z][A-Za-z0-9]+:", line):
            break
        if line.startswith("TROPICAL CYCLONE") or line.startswith("==="):
            i += 1
            continue
        m = re.match(
            r"\(\+?(\d+)H\)\s+([\d.]+)N\s+([\d.]+)E\s+(\d+|---)KT",
            line,
        )
        if m:
            entries.append({
                "tau": int(m.group(1)),
                "lat": float(m.group(2)),
                "lon": float(m.group(3)),
                "wind_kt": int(m.group(4)) if m.group(4) != "---" else None,
            })
            i += 1
            continue
        m = re.match(
            r"(\d{6})Z\s+([\d.]+)N\s+([\d.]+)E\s+(\d+|---)KT",
            line,
        )
        if m:
            entries.append({
                "tau": 0,
                "datetime_z": m.group(1),
                "lat": float(m.group(2)),
                "lon": float(m.group(3)),
                "wind_kt": int(m.group(4)) if m.group(4) != "---" else None,
            })
            i += 1
            continue
        i += 1
    return agency, entries, i


def parse_entry_text(text):
    lines = text.split("\n")
    info = {}
    agencies = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("TROPICAL CYCLONE"):
            info["storm_name"] = line.replace("TROPICAL CYCLONE ", "").strip()
        elif line.startswith("(") and "UTC" in line:
            info["forecast_time_utc"] = line.strip("() ")
        elif line.startswith("==="):
            pass
        elif line.endswith(":") and re.match(r"^[A-Z][A-Za-z0-9]+:", line):
            result = parse_agency_block(lines, i)
            if result:
                agency, entries, next_i = result
                if entries:
                    agencies.append({"agency": agency, "forecasts": entries})
                i = next_i
                continue
        i += 1
    info["agencies"] = agencies

    # Derive the real forecast base time from the tau=0 datetime_z field.
    # typhoon2000.ph's (YYYY-MM-DD HH:MM:SS UTC) is the page generation time,
    # NOT the forecast cycle time. The actual cycle time is in tau=0's datetime_z
    # (format: DDHHMMZ, e.g. "201800" = 20th 18:00 UTC).
    raw_ft = info.get("forecast_time_utc", "")
    m_date = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw_ft)
    if m_date:
        year, month = m_date.group(1), m_date.group(2)
        for ag in agencies:
            for fc in ag.get("forecasts", []):
                if fc.get("tau") == 0 and fc.get("datetime_z"):
                    dz = fc["datetime_z"]  # e.g. "201800"
                    m_dz = re.match(r"(\d{2})(\d{2})(\d{2})", dz)
                    if m_dz:
                        day, hour, minute = m_dz.group(1), m_dz.group(2), m_dz.group(3)
                        info["forecast_time_utc"] = f"{year}-{month}-{day} {hour}:{minute}:00 UTC"
                    break
            if "forecast_time_utc" in info and info["forecast_time_utc"] != raw_ft:
                break

    return info


def fetch_txt_data(typhoon_name):
    """Fetch plain-text forecast data from data/{bare_name}.TXT (fallback for /multi/ page)."""
    bare_name = typhoon_name.split("_")[0]
    url = f"https://www.typhoon2000.ph/multi/data/{bare_name}.TXT"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/plain,*/*",
    }
    print(f"Fetching: {url}")
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def print_summary(info):
    name = info.get("storm_name", "?")
    time = info.get("forecast_time_utc", "?")
    print(f"\nStorm: {name}")
    print(f"Time:  {time}")
    for ag in info.get("agencies", []):
        agency = ag["agency"]
        forecasts = ag["forecasts"]
        print(f"\n  [{agency}]")
        for fc in forecasts:
            tau = fc["tau"]
            lat = fc["lat"]
            lon = fc["lon"]
            wind = fc["wind_kt"]
            wind_str = f"{wind}KT" if wind is not None else "---KT"
            if tau == 0:
                dt = fc.get("datetime_z", "??")
                print(f"    NOW ({dt}): {lat}N {lon}E  {wind_str}")
            else:
                print(f"    +{tau:3d}H:        {lat}N {lon}E  {wind_str}")


def fetch_active_typhoons_from_cwa():
    """Fetch all currently active typhoons AND tropical depressions from CWA Open Data API.
    Returns list of dicts: [{"en": "MEKKHALA", "cn": "米克拉"}, ...]
    """
    cfg = load_config()
    api_key = cfg.get("cwa_api_key", "")
    if not api_key or api_key == "your-cwa-api-key-here":
        print("Warning: No valid cwa_api_key in config.json")
        return []
    params = {"Authorization": api_key}
    try:
        resp = requests.get(CWA_API_URL, params=params, timeout=15, verify=False)
        resp.raise_for_status()
        data = resp.json()
        tcs = data["records"]["TropicalCyclones"]["TropicalCyclone"]
        result = []
        for tc in tcs:
            en = tc.get("TyphoonName")
            td_no = tc.get("CwaTdNo")
            # Skip entries with neither typhoon name nor TD number
            if not en and not td_no:
                continue
            # For pure TDs (no TyphoonName), generate a synthetic name
            if not en:
                en = f"TD{td_no}"
            cn = tc.get("CwaTyphoonName") or en
            td_state_map = {}  # tau -> state transfer text (zh-hant)
            # MaxWindSpeed is in the latest AnalysisData.Fix entry
            mws = None
            fixes = tc.get("AnalysisData", {}).get("Fix", [])
            if fixes:
                mws = fixes[-1].get("MaxWindSpeed")
                if mws is not None:
                    try:
                        mws = int(mws)
                    except (ValueError, TypeError):
                        mws = None
            # Build forecast MaxWindSpeed maps
            fc_mws_map = {}
            fc_mws_map_by_tau = {}
            fc_radius7_map = {}
            fc_radius7_map_by_tau = {}
            fc_radius10_map = {}
            fc_radius10_map_by_tau = {}
            for fc in tc.get("ForecastData", {}).get("Fix", []):
                try:
                    lat = round(float(fc.get("CoordinateLatitude", 0)), 1)
                    lon = round(float(fc.get("CoordinateLongitude", 0)), 1)
                    fhour = int(fc.get("ForecastHour", -1))
                    mws_val = fc.get("MaxWindSpeed")
                    parsed_mws = None
                    if mws_val is not None:
                        parsed_mws = int(mws_val)
                    fc_mws_map[f"{lat},{lon}"] = parsed_mws
                    if fhour >= 0:
                        fc_mws_map_by_tau[fhour] = parsed_mws
                    circle7 = fc.get("Circle15ms", {})
                    if circle7 and circle7.get("Radius", "-") != "-":
                        r7 = int(circle7["Radius"])
                        fc_radius7_map[f"{lat},{lon}"] = r7
                        if fhour >= 0:
                            fc_radius7_map_by_tau[fhour] = r7
                    circle10 = fc.get("Circle25ms", {})
                    if circle10 and circle10.get("Radius", "-") != "-":
                        r10 = int(circle10["Radius"])
                        fc_radius10_map[f"{lat},{lon}"] = r10
                        if fhour >= 0:
                            fc_radius10_map_by_tau[fhour] = r10
                    # Extract StateTransfer for TD designation
                    st = fc.get("StateTransfer")
                    if st and fhour >= 0:
                        for item in st:
                            if item.get("lang") == "zh-hant":
                                td_state_map[fhour] = item.get("value", "")
                                break
                except (ValueError, TypeError):
                    pass

            # Build analysis (nowcast + historical) radius/quadrant maps.
            # CWA puts 4-quadrant radii (NE/SE/SW/NW) in AnalysisData.Fix
            # only; ForecastData.Fix carries a single Radius.
            def _quadrant_map(circle):
                quads = {}
                for item in (circle or {}).get("QuadrantRadii", {}).get("Radius", []):
                    try:
                        quads[item.get("dir")] = int(item.get("value"))
                    except (ValueError, TypeError):
                        pass
                return quads or None

            an_radius7_map = {}
            an_radius10_map = {}
            an_radius7_quad_map = {}
            an_radius10_quad_map = {}
            an_r7_quad_latest = None
            an_r10_quad_latest = None
            an_fix_latest_time = None
            for fix in fixes:
                lat = round(float(fix.get("CoordinateLatitude", 0)), 1)
                lon = round(float(fix.get("CoordinateLongitude", 0)), 1)
                key = f"{lat},{lon}"
                c7 = fix.get("Circle15ms", {})
                if c7 and c7.get("Radius", "-") != "-":
                    an_radius7_map[key] = int(c7["Radius"])
                q7 = _quadrant_map(c7)
                if q7:
                    an_radius7_quad_map[key] = q7
                c10 = fix.get("Circle25ms", {})
                if c10 and c10.get("Radius", "-") != "-":
                    an_radius10_map[key] = int(c10["Radius"])
                q10 = _quadrant_map(c10)
                if q10:
                    an_radius10_quad_map[key] = q10
                it = fix.get("DateTime", "")
                if it and it > (an_fix_latest_time or ""):
                    an_fix_latest_time = it
                    an_r7_quad_latest = q7
                    an_r10_quad_latest = q10

            result.append({
                "en": en,
                "cn": cn,
                "max_wind_ms": mws,
                "is_td": not tc.get("TyphoonName"),
                "td_no": td_no,
                "td_state_map": td_state_map,
                "fc_mws_map": fc_mws_map,
                "fc_mws_map_by_tau": fc_mws_map_by_tau,
                "fc_radius7_map": fc_radius7_map,
                "fc_radius7_map_by_tau": fc_radius7_map_by_tau,
                "fc_radius10_map": fc_radius10_map,
                "fc_radius10_map_by_tau": fc_radius10_map_by_tau,
                "an_radius7_map": an_radius7_map,
                "an_radius10_map": an_radius10_map,
                "an_radius7_quad_map": an_radius7_quad_map,
                "an_radius10_quad_map": an_radius10_quad_map,
                "an_radius7_quad_latest": an_r7_quad_latest,
                "an_radius10_quad_latest": an_r10_quad_latest,
            })
        return result
    except Exception as e:
        print(f"Warning: CWA API request failed: {e}")
        return []


def resolve_typhoon_name(config):
    """Resolve typhoon name(s): auto-select ALL from CWA, fall back to config.
    Returns list of dicts:
      [{"name": "MEKKHALA_2026", "cn": "米克拉", "max_wind_ms": 51}, ...]
    """
    cwa_list = fetch_active_typhoons_from_cwa()
    year = datetime.now().year

    if cwa_list:
        result = []
        for tc in cwa_list:
            result.append({
                "name": f"{tc['en']}_{year}",
                "cn": tc["cn"],
                "max_wind_ms": tc.get("max_wind_ms"),
                "is_td": tc.get("is_td", False),
                "td_no": tc.get("td_no"),
                "td_state_map": tc.get("td_state_map", {}),
                "fc_mws_map": tc.get("fc_mws_map", {}),
                "fc_mws_map_by_tau": tc.get("fc_mws_map_by_tau", {}),
                "fc_radius7_map": tc.get("fc_radius7_map", {}),
                "fc_radius7_map_by_tau": tc.get("fc_radius7_map_by_tau", {}),
                "fc_radius10_map": tc.get("fc_radius10_map", {}),
                "fc_radius10_map_by_tau": tc.get("fc_radius10_map_by_tau", {}),
                "an_radius7_map": tc.get("an_radius7_map", {}),
                "an_radius10_map": tc.get("an_radius10_map", {}),
                "an_radius7_quad_map": tc.get("an_radius7_quad_map", {}),
                "an_radius10_quad_map": tc.get("an_radius10_quad_map", {}),
                "an_radius7_quad_latest": tc.get("an_radius7_quad_latest"),
                "an_radius10_quad_latest": tc.get("an_radius10_quad_latest"),
            })
        names_str = ", ".join(f"{t['en']}({t['cn']})" for t in cwa_list)
        print(f"Auto-detected from CWA: {names_str}")
        return result

    fallback = config.get("typhoon_name")
    if fallback:
        print(f"Using config fallback: {fallback}")
        return [{"name": fallback, "cn": fallback, "max_wind_ms": None, "fc_mws_map": {}, "fc_mws_map_by_tau": {},
                 "fc_radius7_map": {}, "fc_radius7_map_by_tau": {}, "fc_radius10_map": {}, "fc_radius10_map_by_tau": {},
                 "an_radius7_map": {}, "an_radius10_map": {}, "an_radius7_quad_map": {}, "an_radius10_quad_map": {},
                 "an_radius7_quad_latest": None, "an_radius10_quad_latest": None}]
    print("Error: No active typhoon from CWA and no typhoon_name in config.json")
    sys.exit(1)


def _build_cwa_only_entry(tc_info, storm_cn):
    """Build a CWA-only forecast entry for TDs without typhoon2000.ph data.
    Returns info dict in the same format as parse_entry_text() output.
    """
    from datetime import datetime as dt
    year = dt.now().year
    fc_mws_map = tc_info.get("fc_mws_map", {})
    fc_mws_map_by_tau = tc_info.get("fc_mws_map_by_tau", {})

    # Find the initial time from CWA forecast data - use the latest analysis fix time
    # or fallback to now
    initial_time_str = None

    # We need to reconstruct the CWA forecast as agencies data
    # Build from fc_mws_map_by_tau: tau -> (lat, lon, wind_kt, wind_ms)
    # We need lat/lon for each tau - reconstruct from fc_mws_map which is keyed by "lat,lon"
    # fc_mws_map_by_tau is tau -> mws (m/s)
    # We need to map tau back to lat/lon

    # Build the CWA agency forecast from the raw CWA API data
    # We need the raw forecast data, but tc_info only has processed maps
    # Let's rebuild from CWA API directly
    cfg = load_config()
    api_key = cfg.get("cwa_api_key", "")
    if not api_key:
        return None
    try:
        resp = requests.get(CWA_API_URL, params={"Authorization": api_key}, timeout=15, verify=False)
        resp.raise_for_status()
        data = resp.json()
        tcs = data["records"]["TropicalCyclones"]["TropicalCyclone"]
    except Exception:
        return None

    # Find the matching TD
    target = None
    for tc in tcs:
        en = tc.get("TyphoonName")
        td_no = tc.get("CwaTdNo")
        if not en and td_no:
            synthetic = f"TD{td_no}"
            if synthetic == tc_info.get("en") or f"{synthetic}_{datetime.now().year}" == tc_info.get("name"):
                target = tc
                break
    if not target:
        return None

    fixes = target.get("AnalysisData", {}).get("Fix", [])
    fc_fixes = target.get("ForecastData", {}).get("Fix", [])

    # Get initial time from first forecast fix
    if fc_fixes:
        initial_time_str = fc_fixes[0].get("InitialTime", "")

    # Build analysis track points (tau=0)
    cwa_forecasts = []
    if fixes:
        latest_fix = fixes[-1]
        lat = round(float(latest_fix.get("CoordinateLatitude", 0)), 1)
        lon = round(float(latest_fix.get("CoordinateLongitude", 0)), 1)
        mws_val = latest_fix.get("MaxWindSpeed")
        wind_ms = int(mws_val) if mws_val else None
        wind_kt = round(wind_ms / 0.514444) if wind_ms else None
        pressure = latest_fix.get("Pressure")
        try:
            pressure = int(pressure) if pressure else None
        except (ValueError, TypeError):
            pressure = None
        cwa_forecasts.append({
            "tau": 0,
            "lat": lat,
            "lon": lon,
            "wind_kt": wind_kt,
            "wind_ms": wind_ms,
            "pressure_hpa": pressure,
        })

        # Build forecast track points
        for fc_fix in fc_fixes:
            try:
                fhour = int(fc_fix.get("ForecastHour", -1))
                lat = round(float(fc_fix.get("CoordinateLatitude", 0)), 1)
                lon = round(float(fc_fix.get("CoordinateLongitude", 0)), 1)
                mws_val = fc_fix.get("MaxWindSpeed")
                wind_ms = int(mws_val) if mws_val else None
                wind_kt = round(wind_ms / 0.514444) if wind_ms else None
                pressure = fc_fix.get("Pressure")
                try:
                    pressure = int(pressure) if pressure else None
                except (ValueError, TypeError):
                    pressure = None
                cwa_forecasts.append({
                    "tau": fhour,
                    "lat": lat,
                    "lon": lon,
                    "wind_kt": wind_kt,
                    "wind_ms": wind_ms,
                    "pressure_hpa": pressure,
                })
            except (ValueError, TypeError):
                continue

    if not cwa_forecasts:
        return None

    # Build forecast_time_utc from initial time.
    # CWA InitialTime carries a +08:00 (Taiwan) offset; normalize to true UTC.
    forecast_time_utc = ""
    if initial_time_str:
        try:
            it = dt.fromisoformat(initial_time_str)
            if it.tzinfo is not None:
                it = it.astimezone(dt.timezone.utc)
            forecast_time_utc = it.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            pass

    info = {
        "name": storm_cn,
        "agencies": [{
            "agency": "CWA",
            "source": "CWA OpenData",
            "is_forecast": True,
            "forecasts": cwa_forecasts,
        }],
        "forecast_time_utc": forecast_time_utc,
    }
    return info


def main():
    config = load_config()
    typhoon_names = resolve_typhoon_name(config)
    output_path = config.get("output_path", "output")

    if not os.path.exists(output_path):
        os.makedirs(output_path)

    all_typhoons_data = []
    all_typhoons_entries = []

    for tc_info in typhoon_names:
        typhoon_name = tc_info["name"]
        storm_cn = tc_info.get("cn", typhoon_name)
        max_wind_ms = tc_info.get("max_wind_ms")
        fc_mws_map = tc_info.get("fc_mws_map", {})
        print(f"\n{'='*50}")
        print(f"Processing: {typhoon_name}")
        print(f"{'='*50}")

        html = fetch_page(typhoon_name)
        entries = extract_text_entries(html)

        if not entries:
            print(f"No log.php data for {typhoon_name}, trying TXT fallback...")
            info = None
            try:
                txt = fetch_txt_data(typhoon_name)
                info = parse_entry_text(txt)
            except Exception as e:
                print(f"TXT fallback failed: {e}")

            if not info or not info.get("agencies"):
                print(f"No usable data from TXT, trying CWA-only for TD...")
                cwa_info = _build_cwa_only_entry(tc_info, storm_cn)
                if cwa_info:
                    cwa_info["_fetch_name"] = typhoon_name
                    cwa_info["_storm_name_cn"] = storm_cn
                    cwa_info["_max_wind_ms"] = max_wind_ms
                    cwa_info["_cwa_fc_mws_map"] = fc_mws_map
                    cwa_info["_cwa_fc_mws_map_by_tau"] = tc_info.get("fc_mws_map_by_tau", {})
                    cwa_info["_cwa_fc_radius7_map"] = tc_info.get("fc_radius7_map", {})
                    cwa_info["_cwa_fc_radius7_map_by_tau"] = tc_info.get("fc_radius7_map_by_tau", {})
                    cwa_info["_cwa_fc_radius10_map"] = tc_info.get("fc_radius10_map", {})
                    cwa_info["_cwa_fc_radius10_map_by_tau"] = tc_info.get("fc_radius10_map_by_tau", {})
                    cwa_info["_cwa_an_radius7_map"] = tc_info.get("an_radius7_map", {})
                    cwa_info["_cwa_an_radius10_map"] = tc_info.get("an_radius10_map", {})
                    cwa_info["_cwa_an_radius7_quad_map"] = tc_info.get("an_radius7_quad_map", {})
                    cwa_info["_cwa_an_radius10_quad_map"] = tc_info.get("an_radius10_quad_map", {})
                    cwa_info["_cwa_an_radius7_quad_latest"] = tc_info.get("an_radius7_quad_latest")
                    cwa_info["_cwa_an_radius10_quad_latest"] = tc_info.get("an_radius10_quad_latest")
                    cwa_info["_is_td"] = tc_info.get("is_td", False)
                    cwa_info["_td_no"] = tc_info.get("td_no")
                    cwa_info["_td_state_map"] = tc_info.get("td_state_map", {})
                    cwa_info["_source"] = "cwa_only"
                    print(f"CWA-only TD entry built successfully.")
                    all_typhoons_data.append(cwa_info)
                    all_typhoons_entries.append({
                        "storm_name": typhoon_name,
                        "entries": [{"index": 0, "data": cwa_info}],
                    })
                else:
                    print(f"Could not build CWA-only entry, skipping.")
                continue

            info["_fetch_name"] = typhoon_name
            info["_storm_name_cn"] = storm_cn
            info["_max_wind_ms"] = max_wind_ms
            info["_cwa_fc_mws_map"] = fc_mws_map
            info["_cwa_fc_mws_map_by_tau"] = tc_info.get("fc_mws_map_by_tau", {})
            info["_cwa_fc_radius7_map"] = tc_info.get("fc_radius7_map", {})
            info["_cwa_fc_radius7_map_by_tau"] = tc_info.get("fc_radius7_map_by_tau", {})
            info["_cwa_fc_radius10_map"] = tc_info.get("fc_radius10_map", {})
            info["_cwa_fc_radius10_map_by_tau"] = tc_info.get("fc_radius10_map_by_tau", {})
            info["_cwa_an_radius7_map"] = tc_info.get("an_radius7_map", {})
            info["_cwa_an_radius10_map"] = tc_info.get("an_radius10_map", {})
            info["_cwa_an_radius7_quad_map"] = tc_info.get("an_radius7_quad_map", {})
            info["_cwa_an_radius10_quad_map"] = tc_info.get("an_radius10_quad_map", {})
            info["_cwa_an_radius7_quad_latest"] = tc_info.get("an_radius7_quad_latest")
            info["_cwa_an_radius10_quad_latest"] = tc_info.get("an_radius10_quad_latest")
            info["_is_td"] = tc_info.get("is_td", False)
            info["_td_no"] = tc_info.get("td_no")
            info["_td_state_map"] = tc_info.get("td_state_map", {})
            info["_source"] = "txt"
            agency_count = len(info.get("agencies", []))
            print(f"TXT fallback OK, agencies found: {agency_count}")
            print_summary(info)
            all_typhoons_data.append(info)
            all_typhoons_entries.append({
                "storm_name": typhoon_name,
                "entries": [{"index": 0, "data": info}],
            })
            continue

        print(f"Found {len(entries)} time entries (oldest -> newest)")
        print(f"Latest entry index: {entries[-1][0]}")

        latest_idx, latest_text = entries[-1]
        info = parse_entry_text(latest_text)
        info["_fetch_name"] = typhoon_name
        info["_storm_name_cn"] = storm_cn
        info["_max_wind_ms"] = max_wind_ms
        info["_cwa_fc_mws_map"] = fc_mws_map
        info["_cwa_fc_mws_map_by_tau"] = tc_info.get("fc_mws_map_by_tau", {})
        info["_cwa_fc_radius7_map"] = tc_info.get("fc_radius7_map", {})
        info["_cwa_fc_radius7_map_by_tau"] = tc_info.get("fc_radius7_map_by_tau", {})
        info["_cwa_fc_radius10_map"] = tc_info.get("fc_radius10_map", {})
        info["_cwa_fc_radius10_map_by_tau"] = tc_info.get("fc_radius10_map_by_tau", {})
        info["_cwa_an_radius7_map"] = tc_info.get("an_radius7_map", {})
        info["_cwa_an_radius10_map"] = tc_info.get("an_radius10_map", {})
        info["_cwa_an_radius7_quad_map"] = tc_info.get("an_radius7_quad_map", {})
        info["_cwa_an_radius10_quad_map"] = tc_info.get("an_radius10_quad_map", {})
        info["_cwa_an_radius7_quad_latest"] = tc_info.get("an_radius7_quad_latest")
        info["_cwa_an_radius10_quad_latest"] = tc_info.get("an_radius10_quad_latest")
        info["_is_td"] = tc_info.get("is_td", False)
        info["_td_no"] = tc_info.get("td_no")
        info["_td_state_map"] = tc_info.get("td_state_map", {})
        agency_count = len(info.get("agencies", []))
        print(f"\nAgencies found: {agency_count}")

        print_summary(info)

        all_typhoons_data.append(info)

        typhoon_entries = []
        for idx, txt in entries:
            typhoon_entries.append({"index": idx, "data": parse_entry_text(txt)})
        all_typhoons_entries.append({
            "storm_name": typhoon_name,
            "entries": typhoon_entries,
        })

    if not all_typhoons_data:
        print("No data fetched for any typhoon.")
        return

    safe_name = "各國颱風路徑"

    combined = {"typhoons": all_typhoons_data}
    json_path = os.path.join(output_path, f"{safe_name}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {json_path}")

    combined_all = {"typhoons": all_typhoons_entries}
    all_path = os.path.join(output_path, f"{safe_name}_all.json")
    with open(all_path, "w", encoding="utf-8") as f:
        json.dump(combined_all, f, ensure_ascii=False, indent=2)
    print(f"Saved: {all_path}")


if __name__ == "__main__":
    main()
