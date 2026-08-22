"""
Typhoon Track and Storm Radius Visualizer

Plots multi-agency forecast tracks from typhoon2000.ph data
and overlays CWA 7-level (Circle15ms, 七級暴風半徑) and 10-level (Circle25ms, 十級暴風半徑)
storm radius from CWA Open Data API.
"""

import json
import os
import sys
import warnings
from datetime import datetime, timedelta, timezone

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cartopy.io.shapereader as shapereader
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.legend_handler import HandlerTuple
import numpy as np
import requests

try:
    import shapely.geometry as sgeom
    from shapely.ops import transform as shapely_transform
    import pyproj
    HAS_GEOM = True
except ImportError:
    HAS_GEOM = False

warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    pass

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Noto Sans TC", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

# ── Configuration ──────────────────────────────────────────────────────────
CONFIG_PATH = "config.json"
OUTPUT_DIR = "output"
CWA_API_URL = (
    "https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0034-005"
)

AGENCY_STYLE = {
    "CWA":  {"color": "#E0004D", "marker": "o", "linestyle": "-", "linewidth": 1.3, "zorder": 6},
    "JTWC": {"color": "#00A2E8", "marker": "s", "linestyle": "-", "linewidth": 1, "zorder": 5},
    "JMA":  {"color": "#FF7F27", "marker": "^", "linestyle": "-", "linewidth": 1, "zorder": 5},
    "HKO":  {"color": "#22B573", "marker": "D", "linestyle": "-", "linewidth": 1, "zorder": 5},
    "NMC":  {"color": "#A349A4", "marker": "v", "linestyle": "-", "linewidth": 1, "zorder": 5},
    "KMA":  {"color": "#3F48CC", "marker": "<", "linestyle": "-", "linewidth": 1, "zorder": 5},
    "PAGASA": {"color": "#880015", "marker": ">", "linestyle": "-", "linewidth": 1, "zorder": 5},
}

TYPHOON_MARKERS = ["o", "s", "^", "D", "v", "<", ">", "p", "*", "h", "X", "d", "8"]

STORM_RADIUS_COLOR = "#E0004D"
STORM_RADIUS_ALPHA = 0.15
STORM_RADIUS_EDGE_ALPHA = 0.5

# Taiwan reference lines
CONDITION_LINES = {
    "lon_east": 122,
    "lon_west": 120,
    "lat_south": 22,
}

# Basemap style presets
BASEMAP_STYLES = {
    "default": {
        "label": "預設",
        "land": "#f5f0e8", "ocean": "#e8f4f8",
        "coastline": "#444444", "borders": "#888888",
        "lakes": "#e8f4f8", "rivers": "#c8dce0",
        "lake_edge": "#cccccc",
    },
    "light": {
        "label": "淺色",
        "land": "#f8f8f8", "ocean": "#f0f6fa",
        "coastline": "#555555", "borders": "#aaaaaa",
        "lakes": "#f0f6fa", "rivers": "#c0d8e8",
        "lake_edge": "#cccccc",
    },
    "dark": {
        "label": "深色",
        "land": "#2a2a2a", "ocean": "#141e28",
        "coastline": "#8a8a8a", "borders": "#666666",
        "lakes": "#141e28", "rivers": "#2a4a5e",
        "lake_edge": "#444444",
    },
    "terrain": {
        "label": "地形",
        "land": "#e8e0c8", "ocean": "#d4e8f0",
        "coastline": "#5a6a4a", "borders": "#888888",
        "lakes": "#d4e8f0", "rivers": "#8ab4c4",
        "lake_edge": "#aabbcc",
    },
}

TAIWAN_100KM_LINE_COLOR = "#FF6600"


# ── Helper functions ──────────────────────────────────────────────────────

def load_config(path=CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


DATA_JSON = "各國颱風路徑.json"
ALL_JSON  = "各國颱風路徑_all.json"


def load_typhoon_data(output_dir=OUTPUT_DIR):
    """Load typhoon JSON. Returns a list of info dicts (one per typhoon).
    Handles both new format ({"typhoons": [...]}) and old single-object format.
    """
    path = os.path.join(output_dir, DATA_JSON)
    if not os.path.exists(path):
        print(f"Data file not found: {path}")
        print("Run fetch_typhoon2000.py first.")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict) and "typhoons" in raw:
        return raw["typhoons"]
    return [raw]


def load_all_entries(output_dir=OUTPUT_DIR):
    """Load the full _all.json. Returns a dict: storm_name -> list of entries.
    Handles both new format ({"typhoons": [...]}) and old list format.
    """
    path = os.path.join(output_dir, ALL_JSON)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict) and "typhoons" in raw:
        return {item["storm_name"]: item["entries"] for item in raw["typhoons"]}
    return {"": raw}


def utc_str_to_ltc(utc_str, tau=0):
    """Convert UTC time string to Taiwan time (UTC+8)."""
    try:
        if utc_str and tau == 0:
            dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S UTC")
        else:
            if "UTC" in utc_str:
                utc_str = utc_str.replace(" UTC", "")
            dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc) + timedelta(hours=8)
        return dt.strftime("%m/%d %H") + " LTC"
    except (ValueError, TypeError):
        return utc_str if utc_str else "?"


def parse_datetime_z(dtz, ref_utc_str):
    """Convert datetime_z (DDHHMM) to LTC, using ref_utc_str for month."""
    try:
        ref = ref_utc_str.replace(" UTC", "")
        ref_dt = datetime.strptime(ref, "%Y-%m-%d %H:%M:%S")
        day = int(dtz[:2])
        hour = int(dtz[2:4])
        minute = int(dtz[4:6])
        dt = ref_dt.replace(day=day, hour=hour, minute=minute)
        if dt > ref_dt + timedelta(days=1):
            dt -= timedelta(days=30)
        dt = dt.replace(tzinfo=timezone.utc) + timedelta(hours=8)
        return dt.strftime("%m/%d %H") + " LTC"
    except (ValueError, TypeError):
        return dtz


def estimate_radius_from_wind(wind_kt):
    """Estimate 7-level storm radius (km) from max wind speed (kt).
    
    Based on modern CWA 七級暴風半徑 values (up to 350 km).
    """
    if wind_kt is None:
        return 120
    if wind_kt < 34:
        return 120
    elif wind_kt < 45:
        return 150
    elif wind_kt < 55:
        return 180
    elif wind_kt < 65:
        return 200
    elif wind_kt < 75:
        return 250
    elif wind_kt < 85:
        return 280
    elif wind_kt < 95:
        return 300
    else:
        return 350


def fetch_cwa_radius_data(typhoon_name="JANGMI"):
    """Fetch CWA 7-level (Circle15ms) and 10-level (Circle25ms) storm radius
    from CWA Open Data API.
    Returns (radius_map_7, radius_map_10, radius_map_10_by_tau).
    """
    cfg = load_config()
    api_key = cfg.get("cwa_api_key", "")
    if not api_key or api_key == "your-cwa-api-key-here":
        print("Warning: No valid cwa_api_key in config.json, skipping CWA radius")
        return {}, {}, {}
    params = {"Authorization": api_key}
    try:
        resp = requests.get(CWA_API_URL, params=params, timeout=15, verify=False)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Warning: CWA API request failed: {e}")
        return {}, {}, {}

    radius_map_7 = {}
    radius_map_10 = {}
    radius_map_10_by_tau = {}
    try:
        tcs = data["records"]["TropicalCyclones"]["TropicalCyclone"]
        for tc in tcs:
            if tc.get("TyphoonName", "").upper() != typhoon_name.upper():
                continue
            for fix in tc.get("AnalysisData", {}).get("Fix", []):
                lat = float(fix.get("CoordinateLatitude", 0))
                lon = float(fix.get("CoordinateLongitude", 0))
                circle7 = fix.get("Circle15ms", {})
                if circle7 and circle7.get("Radius", "-") != "-":
                    r = int(circle7["Radius"])
                    radius_map_7[(round(lat, 1), round(lon, 1))] = r
                    radius_map_7[(lat, lon)] = r
                circle10 = fix.get("Circle25ms", {})
                if circle10 and circle10.get("Radius", "-") != "-":
                    r = int(circle10["Radius"])
                    radius_map_10[(round(lat, 1), round(lon, 1))] = r
                    radius_map_10[(lat, lon)] = r
            for fix in tc.get("ForecastData", {}).get("Fix", []):
                lat = float(fix.get("CoordinateLatitude", 0))
                lon = float(fix.get("CoordinateLongitude", 0))
                fhour = int(fix.get("ForecastHour", -1))
                circle7 = fix.get("Circle15ms", {})
                if circle7 and circle7.get("Radius", "-") != "-":
                    r = int(circle7["Radius"])
                    radius_map_7[(round(lat, 1), round(lon, 1))] = r
                    radius_map_7[(lat, lon)] = r
                circle10 = fix.get("Circle25ms", {})
                if circle10 and circle10.get("Radius", "-") != "-":
                    r = int(circle10["Radius"])
                    radius_map_10[(round(lat, 1), round(lon, 1))] = r
                    radius_map_10[(lat, lon)] = r
                    if fhour >= 0:
                        radius_map_10_by_tau[fhour] = r
    except (KeyError, TypeError, ValueError) as e:
        print(f"Warning: Failed to parse CWA API response: {e}")

    return radius_map_7, radius_map_10, radius_map_10_by_tau


# ── Special condition storm circles ───────────────────────────────────────

def find_approach_circles(cwa_forecasts, hist_cwa_track, radius_map):
    """Find additional 7-level storm circles for Taiwan reference lines.
    
    Rules:
    1. Center east of 122E → circle edge closest to 122E
    2. Center west of 120E → circle edge closest to 120E
    3. Center south of 22N  → circle edge closest to 22N
    """
    points = []
    for fc in cwa_forecasts:
        points.append({
            "lat": fc["lat"], "lon": fc["lon"],
            "radius_km": _get_radius(fc, radius_map),
        })
    for pt in hist_cwa_track:
        points.append({
            "lat": pt["lat"], "lon": pt["lon"],
            "radius_km": _get_radius(pt, radius_map),
        })

    results = []

    for line_key, line_val, side, attr, edge_fn in [
        ("lon_east", CONDITION_LINES["lon_east"], "east", "lon",
         lambda pt: pt["lon"] - pt["radius_km"] / (111.32 * np.cos(np.radians(pt["lat"])))),
        ("lon_west", CONDITION_LINES["lon_west"], "west", "lon",
         lambda pt: pt["lon"] + pt["radius_km"] / (111.32 * np.cos(np.radians(pt["lat"])))),
        ("lat_south", CONDITION_LINES["lat_south"], "south", "lat",
         lambda pt: pt["lat"] + pt["radius_km"] / 111.32),
    ]:
        candidates = []
        for pt in points:
            if side == "east" and pt["lon"] <= line_val:
                continue
            if side == "west" and pt["lon"] >= line_val:
                continue
            if side == "south" and pt["lat"] >= line_val:
                continue
            edge = edge_fn(pt)
            dist = abs(edge - line_val)
            candidates.append((dist, pt, edge))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            dist, best, edge = candidates[0]
            results.append({
                "type": line_key,
                "ref": line_val,
                "lat": best["lat"],
                "lon": best["lon"],
                "radius_km": best["radius_km"],
                "edge": edge,
            })

    return results


def _get_radius(fc, radius_map):
    r = radius_map.get((fc["lat"], fc["lon"]))
    if r is None:
        r = radius_map.get((round(fc["lat"], 1), round(fc["lon"], 1)))
    if r is None:
        r = estimate_radius_from_wind(fc.get("wind_kt", 0))
    return r


def _load_grade_thresholds():
    """Load CWA grade thresholds from config (m/s)."""
    cfg = load_config()
    return cfg.get("cwa_grade_thresholds", {
        "熱帶低壓_max": 17.1,
        "輕度颱風_min": 17.2,
        "輕度颱風_max": 32.6,
        "中度颱風_min": 32.7,
        "中度颱風_max": 50.9,
        "強烈颱風_min": 51.0,
    })


def wind_kt_to_cwa_grade(wind_kt):
    if wind_kt is None:
        return "--"
    th = _load_grade_thresholds()
    ms = wind_kt * 0.514444
    if ms < th.get("輕度颱風_min", 17.2):
        return "熱帶低壓"
    elif ms < th.get("中度颱風_min", 32.7):
        return "輕颱"
    elif ms < th.get("強烈颱風_min", 51.0):
        return "中颱"
    else:
        return "強颱"


def cwa_ms_to_grade(mps):
    """Convert CWA MaxWindSpeed (m/s) to CWA typhoon grade from config."""
    if mps is None:
        return None
    th = _load_grade_thresholds()
    if mps <= th.get("熱帶低壓_max", 17.1):
        return "熱帶低壓"
    elif mps <= th.get("輕度颱風_max", 32.6):
        return "輕颱"
    elif mps <= th.get("中度颱風_max", 50.9):
        return "中颱"
    else:
        return "強颱"


def km_to_deg(radius_km, lat=25):
    return radius_km / (111.32 * np.cos(np.radians(lat)))


# ── Taiwan 100 km maritime buffer ─────────────────────────────────────────

def _filter_taiwan_geoms(geom):
    """Keep Taiwan main island + western outlying islands (Kinmen, Penghu).
    Excludes small eastern islets (Green Island, Orchid Island, etc.).
    """
    if geom.geom_type == "Polygon":
        polys = [geom]
    else:
        polys = list(geom.geoms)

    kept = []
    for poly in polys:
        centroid = poly.centroid
        bounds = poly.bounds
        if (bounds[2] - bounds[0]) > 0.8 and (bounds[3] - bounds[1]) > 0.8:
            kept.append(poly)
        elif centroid.x < 120.5:
            kept.append(poly)

    if not kept:
        return None
    if len(kept) == 1:
        return kept[0]
    from shapely.geometry import MultiPolygon
    return MultiPolygon(kept)


def _extract_matsu_from_china():
    """Extract Matsu island group polygons from China's geometry in Natural Earth.
    
    Matsu (馬祖) is attributed to China in Natural Earth, so we pull those
    small islands out and merge them into Taiwan's buffer geometry.
    """
    MATSU_BBOX = (119.4, 25.8, 120.6, 26.7)
    try:
        shp = shapereader.natural_earth(
            resolution="10m", category="cultural",
            name="admin_0_countries",
        )
        for record in shapereader.Reader(shp).records():
            name = record.attributes.get("NAME", "")
            iso = record.attributes.get("ADM0_A3", "") or record.attributes.get("ISO_A3", "")
            if name != "China" and iso != "CHN":
                continue
            china_geom = record.geometry
            polys = list(china_geom.geoms) if china_geom.geom_type != "Polygon" else [china_geom]
            matsu_polys = []
            for poly in polys:
                b = poly.bounds
                if not b:
                    continue
                if (b[0] < MATSU_BBOX[2] and b[2] > MATSU_BBOX[0] and
                    b[1] < MATSU_BBOX[3] and b[3] > MATSU_BBOX[1]):
                    if (b[2] - b[0]) < 0.15 and (b[3] - b[1]) < 0.15:
                        matsu_polys.append(poly)
            if matsu_polys:
                if len(matsu_polys) == 1:
                    return matsu_polys[0]
                from shapely.geometry import MultiPolygon
                return MultiPolygon(matsu_polys)
    except Exception as e:
        print(f"  (Matsu extraction failed: {e})")
    return None


def _get_china_mainland():
    """Get China mainland polygon from Natural Earth."""
    try:
        shp = shapereader.natural_earth(
            resolution="10m", category="cultural",
            name="admin_0_countries",
        )
        for record in shapereader.Reader(shp).records():
            name = record.attributes.get("NAME", "")
            iso = record.attributes.get("ADM0_A3", "") or record.attributes.get("ISO_A3", "")
            if name != "China" and iso != "CHN":
                continue
            geom = record.geometry
            polys = list(geom.geoms) if geom.geom_type != "Polygon" else [geom]
            polys.sort(key=lambda p: p.area, reverse=True)
            return polys[0]
    except Exception as e:
        print(f"  (China mainland extraction failed: {e})")
    return None


def get_taiwan_100km_buffer():
    """Compute 100 km offshore buffer around Taiwan coastline.
    
    Clips against China mainland so the line only appears on the maritime side.
    """
    if not HAS_GEOM:
        print("  (shapely/pyproj not available, skipping 100 km buffer)")
        return None

    try:
        # ── Load Taiwan geometry ──
        taiwan_geom = None
        for resolution in ["10m", "50m", "110m"]:
            try:
                shp = shapereader.natural_earth(
                    resolution=resolution, category="cultural",
                    name="admin_0_countries",
                )
                for record in shapereader.Reader(shp).records():
                    attrs = record.attributes
                    name = attrs.get("NAME", "")
                    iso_a3 = attrs.get("ADM0_A3", "") or attrs.get("ISO_A3", "")
                    if "Taiwan" in name and "Taiwan: " not in name:
                        taiwan_geom = record.geometry
                        break
                    if iso_a3 == "TWN":
                        taiwan_geom = record.geometry
                        break
                if taiwan_geom is not None:
                    break
            except Exception:
                continue
        if taiwan_geom is None:
            print("  (Taiwan outline not found in Natural Earth)")
            return None

        # Filter out small eastern islets
        taiwan_geom = _filter_taiwan_geoms(taiwan_geom)
        if taiwan_geom is None:
            print("  (No Taiwan geometries after filtering)")
            return None

        # Merge Matsu (attributed to China in Natural Earth)
        matsu = _extract_matsu_from_china()
        if matsu is not None:
            from shapely.geometry import MultiPolygon
            base_polys = list(taiwan_geom.geoms) if taiwan_geom.geom_type == "MultiPolygon" else [taiwan_geom]
            matsu_polys = list(matsu.geoms) if matsu.geom_type == "MultiPolygon" else [matsu]
            taiwan_geom = MultiPolygon(base_polys + matsu_polys)

        # Add Wuqiu (烏坵, 24.98°N 119.45°E) — tiny island, not in Natural Earth
        wuqiu = sgeom.box(119.43, 24.96, 119.47, 25.00)
        base_polys = list(taiwan_geom.geoms) if taiwan_geom.geom_type == "MultiPolygon" else [taiwan_geom]
        taiwan_geom = MultiPolygon(base_polys + [wuqiu])

        # ── Load China mainland (for clipping) ──
        china_mainland = _get_china_mainland()

        # ── Project to local CRS and compute buffer ──
        centroid = taiwan_geom.centroid
        proj_local = (
            f"+proj=tmerc +lat_0={centroid.y:.2f} +lon_0={centroid.x:.2f} "
            f"+k=1 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
        )

        transformer = pyproj.Transformer.from_crs("EPSG:4326", proj_local, always_xy=True)
        transformer_back = pyproj.Transformer.from_crs(proj_local, "EPSG:4326", always_xy=True)

        taiwan_proj = shapely_transform(transformer.transform, taiwan_geom)
        buffer_proj = taiwan_proj.buffer(100_000)

        # Clip off buffer portions that overlap China mainland
        if china_mainland is not None:
            china_proj = shapely_transform(transformer.transform, china_mainland)
            buffer_proj = buffer_proj.difference(china_proj)

        buffer_wgs84 = shapely_transform(transformer_back.transform, buffer_proj)

        # ── Extract outer boundary, keep only the longest (main) segment ──
        if buffer_wgs84.geom_type == "Polygon":
            return sgeom.LineString(buffer_wgs84.exterior.coords)
        elif buffer_wgs84.geom_type == "MultiPolygon":
            from shapely.geometry import MultiLineString
            lines = [sgeom.LineString(poly.exterior.coords) for poly in buffer_wgs84.geoms]
            lines.sort(key=lambda l: l.length, reverse=True)
            return lines[0]
        return None
    except Exception as e:
        print(f"  (100 km buffer computation failed: {e})")
        return None


# ── Plotting ──────────────────────────────────────────────────────────────

def _filter_typhoons_for_plot(infos):
    """Show GUI to select which typhoons to plot.
    Returns filtered list of info dicts.
    Only shows dialog when 2+ typhoons; single typhoon returns immediately.
    """
    if len(infos) <= 1:
        return infos

    names = [info.get("storm_name", f"颱風{i+1}") for i, info in enumerate(infos)]

    try:
        import tkinter as tk
    except ImportError:
        print(f"\n偵測到 {len(infos)} 個颱風資料：")
        for i, name in enumerate(names, 1):
            print(f"  {i}. {name}")
        try:
            choice = input(f"\n選擇要繪製的颱風（逗號分隔，Enter=全部）: ").strip()
            if not choice:
                return infos
            indices = []
            for part in choice.split(","):
                idx = int(part.strip()) - 1
                if 0 <= idx < len(infos):
                    indices.append(idx)
            if indices:
                return [infos[i] for i in indices]
        except (ValueError, IndexError, EOFError):
            pass
        return infos

    root = tk.Tk()
    root.title("選擇要繪製的颱風")
    root.geometry("360x380")
    root.attributes("-topmost", True)
    root.resizable(False, False)

    result = infos[:]
    timeout_id = None

    tk.Label(
        root,
        text=f"共有 {len(infos)} 個颱風資料，請選擇要繪製的（5.16秒後自動全選）：",
        wraplength=320,
    ).pack(pady=8)

    cf = tk.Frame(root)
    cf.pack(pady=4, padx=20, fill=tk.BOTH, expand=True)

    vars = []
    for name in names:
        v = tk.BooleanVar(value=True)
        cb = tk.Checkbutton(cf, text=name, variable=v, font=("Microsoft JhengHei", 11))
        cb.pack(anchor=tk.W)
        vars.append(v)

    def toggle_all():
        new_val = all(v.get() for v in vars)
        for v in vars:
            v.set(not new_val)

    tk.Frame(cf, height=4).pack()
    tk.Button(cf, text="全選 / 全不選", command=toggle_all).pack(pady=2)

    def on_ok():
        nonlocal result, timeout_id
        if timeout_id:
            root.after_cancel(timeout_id)
        selected = [infos[i] for i, v in enumerate(vars) if v.get()]
        if selected:
            result = selected
        root.destroy()

    def on_cancel():
        nonlocal timeout_id
        if timeout_id:
            root.after_cancel(timeout_id)
        root.destroy()

    def auto_confirm():
        nonlocal result
        result = [infos[i] for i, v in enumerate(vars) if v.get()] or infos[:]
        root.destroy()

    timeout_id = root.after(5160, auto_confirm)

    frm = tk.Frame(root)
    frm.pack(pady=8)
    tk.Button(frm, text="確定", width=10, command=on_ok).pack(side=tk.LEFT, padx=5)
    tk.Button(frm, text="取消", width=10, command=on_cancel).pack(side=tk.LEFT, padx=5)

    root.mainloop()
    return result


def plot_typhoon(entry_index=None):
    """Plot one or more typhoon tracks together on a single map."""
    config = load_config()
    agency_names_cn = config.get("agency_names_cn", {})

    # Override agency colors from config
    agency_colors = config.get("agency_colors", {})
    for agency, color in agency_colors.items():
        if agency in AGENCY_STYLE:
            AGENCY_STYLE[agency]["color"] = color

    basemap_name = config.get("basemap_style", "default")
    basemap_style = BASEMAP_STYLES.get(basemap_name, BASEMAP_STYLES["default"])
    show_100km = config.get("show_taiwan_100km_buffer", False)
    taiwan_100km_line_color = config.get("taiwan_100km_line_color", "#FF6600")
    legend_fontsize = config.get("legend_fontsize", 11)
    legend_title_fontsize = config.get("legend_title_fontsize", 13)
    annot_date_fontsize = config.get("annot_date_fontsize", 7)
    annot_radius_fontsize = config.get("annot_radius_fontsize", 6)
    annot_wind_fontsize = config.get("annot_wind_fontsize", 5)
    print(f"Basemap style: {basemap_name} ({basemap_style['label']})")
    print(f"Taiwan 100 km buffer: {'ON' if show_100km else 'OFF'}")

    # Load data — returns list of info dicts + entries map
    all_infos = load_typhoon_data()
    all_entries = load_all_entries()

    # Handle entry_index: replace latest info with a specific historical entry
    if entry_index is not None:
        found_infos = []
        for info in all_infos:
            fetch_name = info.get("_fetch_name", "")
            hist_entries = all_entries.get(fetch_name, all_entries.get("", []))
            target = None
            for e in hist_entries:
                if e["index"] == entry_index:
                    target = e["data"]
                    break
            if target is not None:
                target["_fetch_name"] = fetch_name
                found_infos.append(target)
                print(f"Using entry index {entry_index} for {fetch_name}: {target.get('forecast_time_utc')}")
            else:
                found_infos.append(info)
                print(f"Entry index {entry_index} not found for {fetch_name}, using latest.")
        all_infos = found_infos

    # Let user pick which typhoons to plot (if multiple available)
    all_infos = _filter_typhoons_for_plot(all_infos)
    if not all_infos:
        print("No typhoon selected for plotting.")
        return

    is_multi = len(all_infos) > 1
    cwa_color = AGENCY_STYLE.get("CWA", {}).get("color", "#E0004D")

    # Collect ALL positions for extent computation
    all_lats, all_lons = [], []

    def _collect_positions(lat, lon):
        all_lats.append(lat)
        all_lons.append(lon)

    for info in all_infos:
        for ag in info.get("agencies", []):
            for fc in ag["forecasts"]:
                _collect_positions(fc["lat"], fc["lon"])

    # Historical track positions from all entries
    for storm_key, entries in all_entries.items():
        for entry in entries:
            for ag in entry["data"].get("agencies", []):
                for fc in ag["forecasts"]:
                    if fc.get("tau") == 0:
                        _collect_positions(fc["lat"], fc["lon"])

    if not all_lats:
        print("No position data to plot.")
        return

    margin = 5
    lat_min = max(-90, min(all_lats) - margin)
    lat_max = min(90, max(all_lats) + margin)
    lon_min = max(-180, min(all_lons) - margin)
    lon_max = min(180, max(all_lons) + margin)

    TAIWAN_BBOX = {"lon_min": 110, "lon_max": 130, "lat_min": 15, "lat_max": 32}
    lat_min = min(lat_min, TAIWAN_BBOX["lat_min"])
    lat_max = max(lat_max, TAIWAN_BBOX["lat_max"])
    lon_min = min(lon_min, TAIWAN_BBOX["lon_min"])
    lon_max = max(lon_max, TAIWAN_BBOX["lon_max"])

    lat_center = (lat_min + lat_max) / 2
    dlat = lat_max - lat_min
    dlon = lon_max - lon_min
    cos_lat = np.cos(np.radians(lat_center))
    if dlat > 0 and cos_lat > 0:
        target_dlon = (16 / 9) * dlat / cos_lat
        if dlon < target_dlon:
            expand = (target_dlon - dlon) / 2
            lon_min -= expand
            lon_max += expand
        else:
            target_dlat = (9 / 16) * dlon * cos_lat
            expand = (target_dlat - dlat) / 2
            lat_min -= expand
            lat_max += expand

    fig = plt.figure(figsize=(16, 9), dpi=150)
    proj = ccrs.PlateCarree()
    ax = fig.add_subplot(1, 1, 1, projection=proj)
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=proj)

    s = basemap_style
    ax.add_feature(cfeature.LAND, facecolor=s["land"], edgecolor=s["lake_edge"], linewidth=0.3)
    ax.add_feature(cfeature.OCEAN, facecolor=s["ocean"])
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor=s["coastline"])
    ax.add_feature(cfeature.BORDERS, linewidth=0.3, edgecolor=s["borders"])
    ax.add_feature(cfeature.LAKES, facecolor=s["lakes"], edgecolor=s["lake_edge"], linewidth=0.3)
    ax.add_feature(cfeature.RIVERS, edgecolor=s["rivers"], linewidth=0.2)

    buffer_line = None
    if show_100km:
        buffer_line = get_taiwan_100km_buffer()
        if buffer_line is not None:
            ax.add_geometries(
                [buffer_line],
                crs=ccrs.PlateCarree(),
                facecolor="none",
                edgecolor=taiwan_100km_line_color,
                linewidth=1.2,
                linestyle="--",
                alpha=0.8,
                zorder=3,
            )
            ax.text(
                118.5, 22.5, "100km 海域線",
                fontsize=7, color=taiwan_100km_line_color, alpha=0.8,
                rotation=25,
                transform=ccrs.PlateCarree(), zorder=3,
            )

    for line_lon in [CONDITION_LINES["lon_east"], CONDITION_LINES["lon_west"]]:
        ax.plot([line_lon, line_lon], [lat_min, lat_max],
                color="#888888", linewidth=0.6, linestyle=":", alpha=0.5,
                transform=ccrs.PlateCarree(), zorder=1)
        ax.text(line_lon, lat_max - 0.5, f"{line_lon}°E", fontsize=7, color="#888888",
                ha="center", va="top", alpha=0.6, transform=ccrs.PlateCarree(), zorder=1)
    ax.plot([lon_min, lon_max], [CONDITION_LINES["lat_south"], CONDITION_LINES["lat_south"]],
            color="#888888", linewidth=0.6, linestyle=":", alpha=0.5,
            transform=ccrs.PlateCarree(), zorder=1)
    ax.text(lon_min + 0.5, CONDITION_LINES["lat_south"], f"{CONDITION_LINES['lat_south']}°N",
            fontsize=7, color="#888888", ha="left", va="bottom", alpha=0.6,
            transform=ccrs.PlateCarree(), zorder=1)

    gl = ax.gridlines(draw_labels=True, linestyle="--", alpha=0.3, color="gray")
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = {"size": 8}
    gl.ylabel_style = {"size": 8}

    # ── Per-typhoon plotting ──
    agency_info = {}
    typhoon_list = []
    legend_title_text = ""

    for idx, info in enumerate(all_infos):
        typhoon_marker = TYPHOON_MARKERS[idx % len(TYPHOON_MARKERS)] if is_multi else None
        storm_name = info.get("storm_name", "?")
        storm_name_cn = info.get("_storm_name_cn", storm_name)
        max_wind_ms = info.get("_max_wind_ms")
        grade_str = cwa_ms_to_grade(max_wind_ms)
        legend_label = storm_name_cn
        if grade_str:
            legend_label += f" ({grade_str})"
        typhoon_list.append((legend_label, typhoon_marker))
        forecast_time_utc = info.get("forecast_time_utc", "?")
        forecast_time_ltc = utc_str_to_ltc(forecast_time_utc)
        fetch_name = info.get("_fetch_name", "")

        print(f"\n── Typhoon {idx + 1}: {storm_name} ({fetch_name}) ──")

        # Historical track for this typhoon
        hist_entries = all_entries.get(fetch_name, all_entries.get("", []))
        hist_track = []
        cwa_hist_track = []
        for entry in hist_entries:
            for ag in entry["data"].get("agencies", []):
                for fc in ag["forecasts"]:
                    if fc.get("tau") == 0:
                        pt = {
                            "lat": fc["lat"], "lon": fc["lon"],
                            "wind_kt": fc.get("wind_kt"),
                            "time": entry["data"].get("forecast_time_utc", ""),
                            "agency": ag["agency"],
                        }
                        hist_track.append(pt)
                        if ag["agency"] == "CWA":
                            cwa_hist_track.append(pt)
                        break
                break

        radius_map_7, radius_map_10, radius_map_10_by_tau = fetch_cwa_radius_data(storm_name)

        # Plot historical track
        if hist_track:
            hlats = [p["lat"] for p in hist_track]
            hlons = [p["lon"] for p in hist_track]
            ax.plot(hlons, hlats, color="#888888", linewidth=0.8, alpha=0.5,
                    transform=ccrs.PlateCarree(), zorder=2,
                    label=f"{storm_name} 歷史軌跡")
            ax.scatter(hlons[0], hlats[0], color="#888888", s=10, marker="x",
                       transform=ccrs.PlateCarree(), zorder=3)
            ax.scatter(hlons[-1], hlats[-1], color="#888888", s=20, marker="*",
                       transform=ccrs.PlateCarree(), zorder=3)

            # Wind speed annotations
            for pt in hist_track[::5]:
                if pt.get("wind_kt"):
                    ax.annotate(
                        f"{pt['wind_kt']}KT",
                        (pt["lon"], pt["lat"]),
                        textcoords="offset points", xytext=(3, -8),
                        fontsize=annot_wind_fontsize, color="#888888", alpha=0.4,
                        transform=ccrs.PlateCarree(), zorder=2,
                    )

        # Plot agency forecasts
        cwa_fcs = []
        for ag in info.get("agencies", []):
            name = ag["agency"]
            fcs = ag["forecasts"]
            if not fcs:
                continue

            base_style = AGENCY_STYLE.get(name, {"color": "#888888", "marker": "o", "linestyle": "-",
                                                  "linewidth": 1.5, "zorder": 4})

            marker = typhoon_marker if is_multi else base_style["marker"]
            tc_style = {
                "color": base_style["color"],
                "marker": marker,
                "linestyle": base_style["linestyle"],
                "linewidth": base_style["linewidth"],
                "zorder": base_style["zorder"],
            }

            fcs_sorted = sorted(fcs, key=lambda x: x["tau"])
            flats = [f["lat"] for f in fcs_sorted]
            flons = [f["lon"] for f in fcs_sorted]

            ax.plot(flons, flats, color=tc_style["color"],
                    linestyle=tc_style["linestyle"],
                    linewidth=tc_style["linewidth"],
                    transform=ccrs.PlateCarree(), zorder=tc_style["zorder"])

            for fc in fcs_sorted:
                tau = fc["tau"]
                ax.scatter(fc["lon"], fc["lat"], color=tc_style["color"],
                           marker=tc_style["marker"], s=20 if tau > 0 else 30,
                           edgecolors="white", linewidth=0.3,
                           transform=ccrs.PlateCarree(), zorder=tc_style["zorder"] + 1)

            if name == "CWA":
                cwa_fcs = fcs_sorted
                for fc in fcs_sorted:
                    tau = fc["tau"]
                    if tau == 0:
                        label = parse_datetime_z(fc.get("datetime_z", ""), forecast_time_utc).replace(" LTC", "")
                    else:
                        try:
                            ref = forecast_time_utc.replace(" UTC", "")
                            ref_dt = datetime.strptime(ref, "%Y-%m-%d %H:%M:%S")
                            fc_dt = ref_dt + timedelta(hours=tau)
                            fc_dt = fc_dt.replace(tzinfo=timezone.utc) + timedelta(hours=8)
                            label = fc_dt.strftime("%m/%d %H")
                        except (ValueError, TypeError):
                            label = f"+{tau}H"
                    ax.annotate(
                        label,
                        (fc["lon"], fc["lat"]),
                        textcoords="offset points", xytext=(0, -10),
                        fontsize=annot_date_fontsize, ha="center", va="top",
                        color=cwa_color, fontweight="bold",
                        transform=ccrs.PlateCarree(), zorder=10,
                    )

            # Collect agency info for legend
            cn_name = agency_names_cn.get(name, name)
            agency_info.setdefault(name, {
                "color": base_style["color"],
                "marker": tc_style["marker"],
                "linestyle": tc_style["linestyle"],
                "linewidth": tc_style["linewidth"],
                "cn_name": cn_name,
            })

        # ── CWA storm radius circles ──
        cwa_fc_mws_map = info.get("_cwa_fc_mws_map", {})
        for fc in cwa_fcs:
            lat = fc["lat"]
            lon = fc["lon"]
            wind = fc.get("wind_kt", 0)

            radius_km = _get_radius(fc, radius_map_7)
            if radius_km is None:
                radius_km = estimate_radius_from_wind(wind)

            source = "API" if (fc["lat"], fc["lon"]) in radius_map_7 or \
                (round(fc["lat"], 1), round(fc["lon"], 1)) in radius_map_7 else "estimated"
            print(f"  CWA +{fc['tau']}H: radius {source} = {radius_km} km (wind={wind}KT)")

            r_deg = km_to_deg(radius_km, lat)
            circle = mpatches.Circle(
                (lon, lat), radius=r_deg,
                facecolor=cwa_color,
                edgecolor=cwa_color,
                alpha=0.12,
                linewidth=1.5,
                linestyle="--",
                transform=ccrs.PlateCarree(),
                zorder=5,
            )
            ax.add_patch(circle)

            # Look up per-point MaxWindSpeed from CWA API forecast data
            fc_key = f"{round(lat, 1)},{round(lon, 1)}"
            if fc_key in cwa_fc_mws_map:
                pt_mws = cwa_fc_mws_map[fc_key]
            else:
                cwa_mws_by_tau = info.get("_cwa_fc_mws_map_by_tau", {})
                pt_mws = cwa_mws_by_tau.get(str(fc["tau"]), info.get("_max_wind_ms"))
            grade = cwa_ms_to_grade(pt_mws) or "--"
            ax.annotate(
                f"{radius_km} km {grade}",
                (lon, lat),
                textcoords="offset points", xytext=(8, 8),
                fontsize=annot_radius_fontsize, color=cwa_color, alpha=0.8,
                transform=ccrs.PlateCarree(), zorder=10,
            )

        # ── 10-level storm radius circles (十級暴風半徑, no annotations) ──
        radius_10_color = "#FF8C00"
        for fc in cwa_fcs:
            lat = fc["lat"]
            lon = fc["lon"]
            r10 = radius_map_10.get((lat, lon))
            if r10 is None:
                r10 = radius_map_10.get((round(lat, 1), round(lon, 1)))
            if r10 is None:
                r10 = radius_map_10_by_tau.get(fc["tau"])
            if r10 is None:
                continue
            r_deg = km_to_deg(r10, lat)
            circle = mpatches.Circle(
                (lon, lat), radius=r_deg,
                facecolor="none",
                edgecolor=radius_10_color,
                alpha=0.5,
                linewidth=1.0,
                linestyle="--",
                transform=ccrs.PlateCarree(),
                zorder=5,
            )
            ax.add_patch(circle)

        # ── Special condition approach circles ──
        approach = find_approach_circles(cwa_fcs, cwa_hist_track, radius_map_7)
        for ap in approach:
            r_deg = km_to_deg(ap["radius_km"], ap["lat"])
            circle = mpatches.Circle(
                (ap["lon"], ap["lat"]), radius=r_deg,
                facecolor="#FF6600",
                edgecolor="#FF6600",
                alpha=0.08,
                linewidth=2,
                linestyle="--",
                transform=ccrs.PlateCarree(),
                zorder=4,
            )
            ax.add_patch(circle)

        # Use time from first typhoon for legend title
        if not legend_title_text:
            if cwa_fcs and cwa_fcs[0]["tau"] == 0:
                legend_title_text = parse_datetime_z(
                    cwa_fcs[0].get("datetime_z", ""), forecast_time_utc
                ).replace(" LTC", "")
            if not legend_title_text:
                legend_title_text = forecast_time_ltc.replace(" LTC", "")

    # ── Legend ──
    all_handles = []
    all_labels = []

    # ── Typhoon entries (show markers) ──
    for sn, marker in typhoon_list:
        if is_multi and marker is not None:
            h = plt.Line2D([], [], color="#444444", marker=marker,
                           linestyle="None", markersize=7, label=sn)
        else:
            h = plt.Line2D([], [], color="#444444", linewidth=2, label=sn)
        all_handles.append(h)
        all_labels.append(sn)

    # ── Agency entries (show colors) ──
    config_order = list(agency_names_cn.keys())
    typhoon_markers_used = [m for _, m in typhoon_list if m is not None]

    for name in config_order:
        ag = agency_info.get(name)
        if not ag:
            continue
        if is_multi and typhoon_markers_used:
            sub = tuple(
                plt.Line2D([], [], color=ag["color"], marker=m,
                           linestyle="None", markersize=6)
                for m in typhoon_markers_used
            )
            all_handles.append(sub)
            all_labels.append(ag["cn_name"])
        else:
            h = plt.Line2D(
                [], [], color=ag["color"],
                marker=ag["marker"], linestyle=ag["linestyle"],
                linewidth=ag["linewidth"], label=ag["cn_name"],
            )
            all_handles.append(h)
            all_labels.append(ag["cn_name"])
    # Add any agencies not in config order
    for name, ag in agency_info.items():
        if name in agency_names_cn:
            continue
        if is_multi and typhoon_markers_used:
            sub = tuple(
                plt.Line2D([], [], color=ag["color"], marker=m,
                           linestyle="None", markersize=6)
                for m in typhoon_markers_used
            )
            all_handles.append(sub)
            all_labels.append(ag["cn_name"])
        else:
            h = plt.Line2D(
                [], [], color=ag["color"],
                marker=ag["marker"], linestyle=ag["linestyle"],
                linewidth=ag["linewidth"], label=ag["cn_name"],
            )
            all_handles.append(h)
            all_labels.append(ag["cn_name"])

    handler_map = {tuple: HandlerTuple(ndivide=None)} if is_multi else {}

    legend = ax.legend(
        handles=all_handles, labels=all_labels,
        handler_map=handler_map,
        loc="lower left",
        fontsize=legend_fontsize,
        framealpha=0.9,
        edgecolor="#cccccc",
        title=legend_title_text,
        title_fontsize=legend_title_fontsize,
    )

    out_path = os.path.join(OUTPUT_DIR, "各國颱風路徑.png")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\nMap saved: {out_path}")
    plt.close()


if __name__ == "__main__":
    idx = None
    if len(sys.argv) > 1:
        idx = int(sys.argv[1])
    plot_typhoon(entry_index=idx)
