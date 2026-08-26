"""
Generate a self-contained Leaflet web page from fetched typhoon data.

Reads config.json, output/各國颱風路徑.json (latest forecasts) and
output/各國颱風路徑_all.json (historical entries), then writes a single
output/各國颱風路徑.html with all data embedded — open it directly in a
browser (double-click, file:// works, no server needed).

Features: multi-agency forecast tracks, CWA 7-level (七級風) and 10-level
(十級風) storm radius circles (from CWA API radius data when available,
otherwise estimated from wind speed, same rule as plot_typhoon.py), historical
actual tracks, and a per-typhoon dropdown to switch to a past forecast entry.
"""

import json
import os
from datetime import datetime

CONFIG_PATH = "config.json"
OUTPUT_DIR = "output"
DATA_JSON = "各國颱風路徑.json"
ALL_JSON = "各國颱風路徑_all.json"
HTML_OUT = "各國颱風路徑.html"
TEACHING_HTML = "白海豚教材.html"

# Metadata fetch_typhoon2000.py injects on the latest info; we forward these
# to historical entries too so grades/radius render for past selections.
LATEST_EXTRA_FIELDS = (
    "_fetch_name",
    "_storm_name_cn",
    "_max_wind_ms",
    "_is_td",
    "_td_no",
    "_td_state_map",
    "_cwa_fc_mws_map",
    "_cwa_fc_mws_map_by_tau",
    "_cwa_fc_radius7_map",
    "_cwa_fc_radius7_map_by_tau",
    "_cwa_fc_radius10_map",
    "_cwa_fc_radius10_map_by_tau",
    "_cwa_an_radius7_map",
    "_cwa_an_radius10_map",
    "_cwa_an_radius7_quad_map",
    "_cwa_an_radius10_quad_map",
    "_cwa_an_radius7_quad_latest",
    "_cwa_an_radius10_quad_latest",
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_taiwan_buffer(cfg):
    """Reuse plot_typhoon.get_taiwan_100km_buffer() and return the line as a
    plain list of {lat, lon} for embedding (or None if unavailable/disabled).
    """
    if not cfg.get("show_taiwan_100km_buffer", False):
        return None
    try:
        from plot_typhoon import get_taiwan_100km_buffer, HAS_GEOM
    except Exception as e:
        print(f"  (plot_web) could not import plot_typhoon buffer helper: {e}")
        return None
    if not HAS_GEOM:
        print("  (shapely/pyproj not available, skipping 100 km buffer on web page)")
        return None
    try:
        line = get_taiwan_100km_buffer()
    except Exception as e:
        print(f"  (100 km buffer computation failed: {e})")
        return None
    if line is None:
        return None
    return {
        "color": cfg.get("taiwan_100km_line_color", "#FF6600"),
        "line": [{"lat": y, "lon": x} for x, y in line.coords],
    }


def build_embedded(data_dir=None):
    data_dir = data_dir or OUTPUT_DIR
    cfg = load_json(CONFIG_PATH)
    raw_latest = load_json(os.path.join(data_dir, DATA_JSON))
    raw_all = load_json(os.path.join(data_dir, ALL_JSON))

    wn_map = {}
    wn_path = os.path.join(data_dir, "weathernext_" + DATA_JSON)
    if os.path.exists(wn_path):
        try:
            wn_raw = load_json(wn_path)
            for t in wn_raw.get("typhoons", []):
                wn_map[t.get("storm_name")] = t.get("points", [])
        except Exception as e:
            print(f"  (weathernext json read failed: {e})")

    ecmwf_run = ""
    ecmwf_map = {}
    ecmwf_path = os.path.join(data_dir, "ecmwf_" + DATA_JSON)
    if os.path.exists(ecmwf_path):
        try:
            ec_raw = load_json(ecmwf_path)
            ecmwf_run = ec_raw.get("run", "")
            for t in ec_raw.get("typhoons", []):
                ecmwf_map[t.get("storm_name")] = t
        except Exception as e:
            print(f"  (ecmwf json read failed: {e})")

    if isinstance(raw_latest, dict) and "typhoons" in raw_latest:
        latest_typhoons = raw_latest["typhoons"]
    else:
        latest_typhoons = [raw_latest]

    all_map = {}
    if isinstance(raw_all, dict) and "typhoons" in raw_all:
        for item in raw_all["typhoons"]:
            all_map[item["storm_name"]] = item.get("entries", [])
    elif isinstance(raw_all, list):
        all_map[""] = raw_all

    typhoons = []
    for info in latest_typhoons:
        fetch_name = info.get("_fetch_name", "")
        storm_name = info.get("storm_name", "?")
        entries = all_map.get(fetch_name, all_map.get("", []))

        extra = {k: info.get(k) for k in LATEST_EXTRA_FIELDS if info.get(k) is not None}
        entry_list = []
        for e in entries:
            data = dict(e.get("data", {}))
            for k, v in extra.items():
                data.setdefault(k, v)
            entry_list.append({
                "index": e.get("index"),
                "forecast_time_utc": data.get("forecast_time_utc", ""),
                "data": data,
            })

        typhoons.append({
            "storm_name": storm_name,
            "storm_name_cn": info.get("_storm_name_cn", storm_name),
            "fetch_name": fetch_name,
            "forecast_time_utc": info.get("forecast_time_utc", ""),
            "latest": info,
            "entries": entry_list,
            "weathernext": wn_map.get(storm_name, []),
            "ecmwf": ecmwf_map.get(storm_name),
        })

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "agency_names_cn": cfg.get("agency_names_cn", {}),
            "agency_colors": cfg.get("agency_colors", {}),
            "cwa_grade_thresholds": cfg.get("cwa_grade_thresholds", {}),
            "stadia_api_key": cfg.get("stadia_api_key", ""),
        },
        "taiwan_100km_buffer": compute_taiwan_buffer(cfg),
        "weathernext": wn_map,
        "ecmwf_run": ecmwf_run,
        "typhoons": typhoons,
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__PAGE_TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body { margin: 0; height: 100%; }
  #map { position: absolute; inset: 0; z-index: 0; }
  #panel {
    position: absolute; top: 12px; right: 12px; z-index: 1000;
    background: rgba(255,255,255,0.95); border: 1px solid #ccc;
    border-radius: 8px; padding: 10px 14px; max-width: 240px;
    max-height: calc(100vh - 120px); overflow-y: auto;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2); font-family: "Microsoft JhengHei", "Noto Sans TC", sans-serif;
  }
  #panel-collapse-btn {
    float: right; cursor: pointer; border: none; background: none;
    font-size: 12px; color: #888; padding: 0 3px; line-height: 1.2;
  }
  #help-btn {
    float: right; cursor: pointer; border: none; background: none;
    font-size: 13px; color: #888; padding: 0 3px; line-height: 1.2;
  }
  #help-modal {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    z-index: 2000; background: rgba(0,0,0,0.45);
    display: none; align-items: center; justify-content: center; padding: 16px;
  }
  #help-modal.open { display: flex; }
  #help-box {
    background: #fff; border-radius: 8px; max-width: 560px; width: 100%;
    max-height: 80vh; overflow-y: auto; padding: 16px 20px;
    font-family: "Microsoft JhengHei", "Noto Sans TC", sans-serif;
    font-size: 13px; line-height: 1.7; color: #333;
    box-shadow: 0 4px 24px rgba(0,0,0,0.3);
  }
  #help-box h3 { margin: 0 0 8px; font-size: 17px; }
  #help-box h4 { margin: 14px 0 4px; font-size: 14px; color: #D81B60; }
  #help-box p { margin: 4px 0; }
  .typhoon-icon-legend { margin: 6px 0; }
  .ty-icon-row { display: flex; align-items: center; gap: 8px; margin: 5px 0; }
  .ty-icon-row span { font-size: 13px; }
  #help-close {
    float: right; cursor: pointer; border: none; background: none;
    font-size: 16px; color: #888; line-height: 1; padding: 0 2px;
  }
  #panel.collapsed { max-width: 30px; padding: 6px; }
  #panel.collapsed > *:not(#panel-collapse-btn) { display: none; }
  #panel h3 { margin: 0 0 6px; font-size: 16px; }
  #panel .meta { font-size: 11px; color: #666; margin-bottom: 8px; line-height: 1.5; }
  .typhoon-sel { margin: 6px 0; }
  .typhoon-sel label { display: block; font-size: 13px; font-weight: bold; margin-bottom: 2px; }
  .typhoon-sel select { width: 100%; font-size: 12px; box-sizing: border-box; }
  .base-title { font-size: 13px; font-weight: bold; margin: 4px 0 2px; }
  .base-opt { display: block; font-size: 13px; margin: 3px 0; cursor: pointer; }
  .base-opt input { margin-right: 6px; }
  .sep { border: none; border-top: 1px solid #ddd; margin: 8px 0; }
  .play-title { font-size: 13px; font-weight: bold; margin: 4px 0 2px; }
  .play-controls { display: flex; gap: 6px; margin: 4px 0; }
  .play-controls button {
    flex: 1; font-size: 13px; padding: 4px 0; cursor: pointer;
    font-family: "Microsoft JhengHei", "Noto Sans TC", sans-serif;
  }
  .now-btn {
    display: block; width: 100%; font-size: 12px; padding: 3px 0; margin: 4px 0 2px;
    cursor: pointer; box-sizing: border-box;
    font-family: "Microsoft JhengHei", "Noto Sans TC", sans-serif;
    background: #f0f4ff; border: 1px solid #7986CB; border-radius: 4px; color: #333;
  }
  .now-btn:hover { background: #dce4ff; }
  #play-slider { width: 100%; box-sizing: border-box; margin: 2px 0; }
  .play-time { font-size: 12px; color: #444; text-align: center; }
  .hint { font-size: 11px; color: #999; margin-top: 6px; }
  .nav-link {
    display: block; font-size: 11px; color: #D81B60; text-decoration: none;
    margin-bottom: 6px; border: 1px solid rgba(216,27,96,0.35); border-radius: 999px;
    padding: 2px 9px; text-align: center; background: rgba(216,27,96,0.06);
  }
  .nav-link:hover { background: rgba(216,27,96,0.16); }
  .pin-controls { display: flex; gap: 6px; margin: 4px 0 2px; }
  .pin-controls button {
    flex: 1; font-size: 12px; padding: 3px 0; cursor: pointer;
    font-family: "Microsoft JhengHei", "Noto Sans TC", sans-serif;
  }
  .pin-controls button.pin-help {
    flex: 0 0 auto; width: 22px; padding: 0;
    border: 1px solid #999; border-radius: 50%;
    font-size: 12px; font-weight: bold; color: #555; background: #fff;
  }
  .pin-help[aria-pressed="true"] { background: #eee; }
  .pin-list { margin-top: 2px; max-height: 96px; overflow-y: auto; }
  .pin-item {
    display: flex; align-items: center; justify-content: space-between;
    gap: 6px; font-size: 11px; color: #444;
    border-top: 1px dotted #ddd; padding: 1px 0;
  }
  .pin-item button {
    border: none; background: none; cursor: pointer; color: #999; font-size: 13px; padding: 0 2px;
  }
  .legend {
    background: rgba(255,255,255,0.92); border: 1px solid #ccc; border-radius: 6px;
    padding: 8px 10px; font-family: "Microsoft JhengHei", "Noto Sans TC", sans-serif; font-size: 12px;
  }
  .legend h4 { margin: 0 0 6px; font-size: 13px; }
  .legend-row { display: flex; align-items: center; gap: 6px; margin: 2px 0; }
  .swatch { display: inline-block; width: 16px; height: 8px; border-radius: 2px; }
  .legend-note { margin-top: 6px; font-size: 11px; color: #666; }
  .legend-help { margin-top: 6px; }
  .legend-help summary {
    cursor: pointer; list-style: none; user-select: none;
    display: inline-block; width: 18px; height: 18px; line-height: 18px;
    text-align: center; border: 1px solid #999; border-radius: 50%;
    font-size: 12px; font-weight: bold; color: #555;
  }
  .legend-help summary::-webkit-details-marker { display: none; }
  .popup { font-size: 12px; line-height: 1.6; }
  .track-marker { color: #888; font-weight: bold; font-size: 12px; }
  #brand {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 14px 8px 9px;
    background: linear-gradient(135deg, rgba(255,255,255,0.97), rgba(255,255,255,0.9));
    border-radius: 12px;
    box-shadow: 0 3px 12px rgba(0,0,0,0.28), inset 0 0 0 1px rgba(224,0,77,0.18);
    font-family: "Microsoft JhengHei", "Noto Sans TC", sans-serif;
    pointer-events: none;
  }
  .brand-ico {
    width: 34px; height: 34px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
    background: linear-gradient(135deg, #E0004D, #FF8C00);
    box-shadow: 0 2px 6px rgba(224,0,77,0.35);
  }
  .brand-name {
    font-size: 19px; font-weight: 700; letter-spacing: 2px; line-height: 1.25;
    background: linear-gradient(135deg, #E0004D, #FF8C00);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  .brand-sub {
    font-size: 9px; color: #8a8a8a; letter-spacing: 1.5px; line-height: 1;
    margin-top: 2px;
  }
  .radius-label {
    background: rgba(255,255,255,0.92) !important;
    border: 1px solid rgba(0,0,0,0.25) !important;
    border-radius: 4px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.3) !important;
    font-family: "Microsoft JhengHei", "Noto Sans TC", sans-serif;
    font-size: 10px; font-weight: bold; line-height: 1;
    padding: 2px 3px !important;
  }
  .radius-label.r7 { color: #C62828; border-color: rgba(198,40,40,0.55) !important; }
  .radius-label.r10 { color: #B25E00; border-color: rgba(255,140,0,0.65) !important; }
  @media (max-width: 640px) {
    #panel {
      top: auto; bottom: 8px; left: 8px; right: 8px;
      max-width: none; max-height: 48vh; overflow-y: auto;
      padding: 8px 10px;
    }
    .play-controls button { font-size: 12px; }
    .now-btn { font-size: 11px; }
    #brand { padding: 5px 10px 5px 6px; gap: 7px; border-radius: 10px; }
    .brand-ico { width: 26px; height: 26px; font-size: 15px; }
    .brand-name { font-size: 15px; letter-spacing: 1px; }
    .brand-sub { display: none; }
  }
</style>
</head>
<body>
<div id="map"></div>
<div id="panel">
  <button id="help-btn" type="button" title="網頁說明">❓</button>
  <button id="panel-collapse-btn" type="button" title="收合面板">◀</button>
  <h3>__PAGE_TITLE__</h3>
  __NAV_LINK__
  <div class="meta" id="meta"></div>
  <div class="base-title">底圖</div>
  <div id="basemap-panel"></div>
  <hr class="sep">
  <div id="typhoon-panel"></div>
  <hr class="sep">
  <div class="play-title">時間播放</div>
  <div class="play-controls">
    <button id="prev-hour-btn" type="button">◀ 1H</button>
    <button id="play-btn" type="button">▶ 播放</button>
    <button id="reset-btn" type="button">↺ 重設</button>
    <button id="next-hour-btn" type="button">1H ▶</button>
  </div>
  <button id="now-btn" type="button" class="now-btn">📍 現在時間</button>
  <input type="range" id="play-slider" min="0" max="1000" step="1" value="1000">
  <div class="play-time" id="play-time"></div>
  <div class="pin-controls">
    <button id="pin-btn" type="button">📌 固定此時間風圈</button>
    <button id="clear-pins-btn" type="button">清除全部標記</button>
    <button id="pin-help-btn" type="button" class="pin-help" title="固定風圈說明">?</button>
  </div>
  <div class="pin-list" id="pin-list"></div>
  <div class="hint" id="pin-hint" hidden>在時間軸選定時間後按「固定此時間風圈」，可把該時間的七級/十級風圈留在圖上（列表可個別 ✕ 刪除）</div>
  <div class="hint">切換下拉選單可檢視歷史某次預報（歷史軌跡固定顯示）</div>
  <hr class="sep">
  <div class="play-title">各國路徑</div>
  <div id="agency-panel"></div>
</div>
<div id="help-modal">
  <div id="help-box">
    <button id="help-close" type="button" title="關閉">✕</button>
    <h3>網頁說明</h3>
    <p>本頁由 <b>plot_web.py</b> 產生，資料已內嵌於檔案，直接開啟即可使用；圖磚與 Leaflet 函式庫需網路連線。</p>
    <h4>資料來源</h4>
    <p>多機構預報路徑（CWA／JTWC／JMA／HKO／NMC／KMA／PAGASA）來自 typhoon2000.ph；CWA 颱風強度與暴風半徑來自中央氣象署開放資料 API（W-C0034-005），於產生網頁時一併取得。</p>
    <h4>地圖操作</h4>
    <p>拖曳平移、滾輪縮放。左上方「?」可展開風圈與軌跡的圖例說明。</p>
    <h4>底圖切換</h4>
    <p>右側面板「底圖」可切換 Google 地圖／Esri 衛星圖／Stamen 地形圖（後者需在 config.json 填入 stadia_api_key）。</p>
    <h4>歷史預報</h4>
    <p>每顆颱風有下拉選單（最新時間置頂），可切換查看歷史任一次預報；歷史實際軌跡以灰色虛線固定顯示。</p>
    <h4>時間播放</h4>
    <p>「▶ 播放」沿時間軸播放歷史軌跡至預報；「◀ 1H」「1H ▶」每步前後 1 小時；拖曳時間軸可跳轉。播放時移動標記旁的紅／橘虛線多邊形為 CWA 分析資料的四象限七級／十級風圈，實線圓為平均半徑。</p>
    <h4>固定風圈標註</h4>
    <p>在時間軸選定時間後按「📌 固定此時間風圈」，將該時間各颱風的七級／十級風圈留在圖上（虛線為四象限、實線為平均半徑）；下方列表可個別 ✕ 刪除，或按「清除全部標記」。</p>
    <h4>各國路徑開關</h4>
    <p>右側面板「各國路徑」可逐一勾選，開關各機構的預報路徑線。</p>
    <h4>WeatherNext AI 預報</h4>
    <p>暫時停用。原本的 fetch_weathernext.py 是沿各國預報路徑取點去問 Open-Meteo 免費 API 的風速／氣壓／氣溫，路徑與 CWA 重疊、並非 Google 自身的預測路徑，故先移除。待改用能取得 Google WeatherNext 2 自身熱帶氣旋預測路徑的資料來源後再加回。</p>
    <h4>ECMWF 模式預報</h4>
    <p>深靛實線為 ECMWF Open Data 的 HRES 決定性預報，淺靛虛線為 ENS 系集平均（51 個成員平均）；由 fetch_ecmwf.py 從 ECMWF 官方 BUFR 熱帶氣旋路徑產品解碼（CC-BY-4.0），點擊圓點查看各時段位置、最大風速與中心氣壓。圖層控制中每顆颱風有「XX ECMWF HRES」與「XX ECMWF ENS」可分別開關。</p>
    <h4>圖層控制</h4>
    <p>地圖角落的層疊圖示按鈕（桌面右下、手機右上）可開關各颱風圖層、歷史軌跡、臺灣 100km 海域線、經緯度線與固定風圈標註。</p>
    <h4>經緯度線</h4>
    <p>以每 5° 一條的淡灰虛線標出經度與緯度網格，便於讀取颱風所在座標，可於圖層控制開關（預設顯示）。</p>
    <h4>暴風半徑</h4>
    <p>靜態檢視不直接畫風圈，改在 CWA 預報點的快顯視窗中顯示七級／十級暴風半徑（點擊路徑點即可查看）。時間播放時，移動標記旁會框出 CWA 四象限風圈（紅＝七級、橘＝十級，虛線＝四象限、實線＝平均半徑）；也可按「📌 固定此時間風圈」把指定時間的風圈留在圖上。</p>
    <h4>颱風中心圖示</h4>
    <p>播放時的移動標記與最新預報點（tau=0）會依強度顯示不同的颱風標誌：</p>
    <div id="typhoon-icon-legend" class="typhoon-icon-legend"></div>
    <p>圈中點為颱風眼、上下兩條旋臂為颱風標誌；顏色表示強度——綠色＝中度、紅色＝強烈，深灰空心＝輕度，灰點＝熱帶性低氣壓。</p>
    <h4>臺灣 100km 海域線</h4>
    <p>由臺灣海岸輪廓向外緩衝 100 公里的海洋界線，用於觀察颱風是否進入警戒範圍，可於圖層控制開關。</p>
  </div>
</div>
<script>
const DATA = __DATA__;

const AGENCY_CN = DATA.config.agency_names_cn || {};
const AGENCY_COLORS = DATA.config.agency_colors || {};
const GRADE_TH = DATA.config.cwa_grade_thresholds || {};
const CWA_COLOR = AGENCY_COLORS['CWA'] || '#E0004D';

function pad2(n) { return String(n).padStart(2, '0'); }

function utcToLTC(utcStr) {
  const s = String(utcStr || '');
  const m = s.match(/(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
  if (!m) return '—';
  const d = new Date(Date.UTC(+m[1], +m[2]-1, +m[3], +m[4], +m[5], +m[6]) + 8*3600*1000);
  return `${d.getUTCFullYear()}/${pad2(d.getUTCMonth()+1)}/${pad2(d.getUTCDate())} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())} LTC`;
}

function fcTimeLTC(info, fc) {
  const s = String(info.forecast_time_utc || '');
  const m = s.match(/(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
  if (!m) return '—';
  const hours = (fc.tau || 0) + 8;
  const d = new Date(Date.UTC(+m[1], +m[2]-1, +m[3], +m[4], +m[5], +m[6]) + hours*3600*1000);
  return `${pad2(d.getUTCMonth()+1)}/${pad2(d.getUTCDate())} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())} LTC`;
}

function parseUtcMs(s) {
  const m = String(s || '').match(/(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
  if (!m) return null;
  return Date.UTC(+m[1], +m[2]-1, +m[3], +m[4], +m[5], +m[6]);
}

function utcMsToLTC(ms) {
  const d = new Date(ms + 8*3600*1000);
  return `${d.getUTCFullYear()}/${pad2(d.getUTCMonth()+1)}/${pad2(d.getUTCDate())} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())} LTC`;
}

function fcTimeAbs(info, fc) {
  const base = parseUtcMs(info.forecast_time_utc);
  return base == null ? null : base + (fc.tau || 0) * 3600000;
}

function ecmwfTimeLTC(runStr, tau) {
  const m = String(runStr || '').match(/(\d{4})(\d{2})(\d{2})\/(\d{2})z/);
  if (!m) return '?';
  const base = Date.UTC(+m[1], +m[2]-1, +m[3], +m[4], 0, 0) + ((tau || 0)) * 3600000;
  return utcMsToLTC(base);
}

function windKtToRadius(kt) {
  if (kt == null) return 0;
  if (kt < 34) return 0;
  if (kt < 45) return 150;
  if (kt < 55) return 180;
  if (kt < 65) return 200;
  if (kt < 75) return 250;
  if (kt < 85) return 280;
  if (kt < 95) return 300;
  return 350;
}

function windKtToRadius10(kt) {
  if (kt == null) return 0;
  if (kt < 50) return 0;
  if (kt < 55) return 80;
  if (kt < 65) return 100;
  if (kt < 75) return 120;
  if (kt < 85) return 150;
  if (kt < 95) return 180;
  return 200;
}

function ktToMsStr(kt) {
  if (kt == null) return '--';
  return `${(kt * 0.514444).toFixed(1)} m/s`;
}

function northRadius(radii) {
  if (!radii) return null;
  const r = Math.max(radii.NE || 0, radii.NW || 0);
  return r > 0 ? r : null;
}

function addRadiusLabel(grp, lat, lon, rKm, cls) {
  const tip = L.tooltip({
    permanent: true, direction: 'center', className: `radius-label ${cls}`,
  }).setLatLng([lat + rKm / 111.32, lon]).setContent(`${rKm} km`);
  grp.addLayer(tip);
  return tip;
}

function updateRadiusLabel(tip, lat, lon, rKm) {
  if (!tip) return;
  tip.setLatLng([lat + rKm / 111.32, lon]).setContent(`${rKm} km`);
}

function polyWithHalo(grp, latlngs, color, weight, opacity, fillColor, fillOpacity, dashed) {
  const opts = { color: '#ffffff', weight: weight + 3, opacity: 0.9, fill: false };
  if (dashed) opts.dashArray = '8 4';
  L.polygon(latlngs, opts).addTo(grp);
  L.polygon(latlngs, { color, weight, opacity, fillColor, fillOpacity }).addTo(grp);
}

function radiusFromMaps(fc, info, mapKey, tauKey) {
  const byPos = info[mapKey] || {};
  const byTau = info[tauKey] || {};
  let r = byPos[`${fc.lat.toFixed(1)},${fc.lon.toFixed(1)}`];
  if (r == null) r = byTau[String(fc.tau)];
  return r;
}

function quadrantCirclePoints(lat, lon, radii) {
  const R_KM = 111.32;
  const m = Math.cos(lat * Math.PI / 180) || 1e-9;
  const pts = [];
  const segs = [['NE', 0, 90], ['SE', 90, 180], ['SW', 180, 270], ['NW', 270, 360]];
  segs.forEach(([q, a0, a1]) => {
    const r = radii[q];
    if (!r || r <= 0) return;
    const steps = 5;
    for (let i = 0; i <= steps; i++) {
      const rad = (a0 + (a1 - a0) * i / steps) * Math.PI / 180;
      pts.push([
        lat + (r / R_KM) * Math.cos(rad),
        lon + (r / (R_KM * m)) * Math.sin(rad),
      ]);
    }
  });
  if (pts.length) pts.push(pts[0]);
  return pts;
}

function msToGrade(ms) {
  if (ms == null) return null;
  if (ms <= (GRADE_TH['熱帶低壓_max'] ?? 17.1)) return '熱帶低壓';
  if (ms <= (GRADE_TH['輕度颱風_max'] ?? 32.6)) return '輕颱';
  if (ms <= (GRADE_TH['中度颱風_max'] ?? 50.9)) return '中颱';
  return '強颱';
}

function pointGrade(fc, info) {
  const byTau = info['_cwa_fc_mws_map_by_tau'] || {};
  const byPos = info['_cwa_fc_mws_map'] || {};
  let ms = byPos[`${fc.lat.toFixed(1)},${fc.lon.toFixed(1)}`];
  if (ms == null) ms = byTau[String(fc.tau)];
  if (ms == null) ms = info['_max_wind_ms'];
  return msToGrade(ms);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);
}

function trackIcon(ch) {
  return L.divIcon({
    html: `<div class="track-marker">${ch}</div>`,
    className: '', iconSize: [14, 14], iconAnchor: [7, 7],
  });
}

function windTier(windMs) {
  if (windMs >= 51) return 'strong';
  if (windMs >= 32) return 'medium';
  if (windMs >= 17) return 'light';
  return 'td';
}

function typhoonArms(n, cx, cy, R, color, sw) {
  if (n <= 0) return '';
  let paths = '';
  for (let k = 0; k < n; k++) {
    const a = -Math.PI / 2 + k * (2 * Math.PI / n);
    const sx = cx + R * Math.cos(a), sy = cy + R * Math.sin(a);
    const c1x = cx + (R + 3.2) * Math.cos(a - 0.5), c1y = cy + (R + 3.2) * Math.sin(a - 0.5);
    const ex = cx + (R + 6.2) * Math.cos(a + 0.65), ey = cy + (R + 6.2) * Math.sin(a + 0.65);
    paths += `<path d="M ${sx.toFixed(2)} ${sy.toFixed(2)} Q ${c1x.toFixed(2)} ${c1y.toFixed(2)} ${ex.toFixed(2)} ${ey.toFixed(2)}" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linecap="round"/>`;
  }
  return paths;
}

function typhoonCenterIcon(windMs, color) {
  const tier = windTier(windMs);
  const cx = 14, cy = 14, R = 6.5;
  let fill, stroke, eye, armColor, arms;
  if (tier === 'strong') {
    fill = '#FF2D2D'; stroke = '#FF2D2D'; eye = '#ffffff'; armColor = '#FF2D2D'; arms = 2;
  } else if (tier === 'medium') {
    fill = '#22B573'; stroke = '#22B573'; eye = '#ffffff'; armColor = '#22B573'; arms = 2;
  } else if (tier === 'light') {
    fill = 'none'; stroke = '#444444'; eye = '#444444'; armColor = '#444444'; arms = 2;
  } else {
    fill = 'none'; stroke = '#888888'; eye = '#888888'; armColor = '#888888'; arms = 0;
  }
  const S = 28;
  const inner =
    `<circle cx="${cx}" cy="${cy}" r="${R}" fill="${fill}" stroke="${stroke}" stroke-width="2"/>` +
    `<circle cx="${cx}" cy="${cy}" r="1.7" fill="${eye}"/>` +
    typhoonArms(arms, cx, cy, R, armColor, 2);
  const html = `<div style="background:none;border:none;line-height:0;">` +
    `<svg width="${S}" height="${S}" viewBox="0 0 ${S} ${S}">${inner}</svg></div>`;
  return L.divIcon({ html, className: 'typhoon-center-icon', iconSize: [S, S], iconAnchor: [S/2, S/2] });
}

const map = L.map('map', { zoomControl: false });
const radiusLabelGrp = L.layerGroup().addTo(map);
const pinLabelGrp = L.layerGroup().addTo(map);
const baseLayers = {
  'Google 地圖': L.tileLayer('https://{s}.google.com/vt/lyrs=m&hl=zh-TW&x={x}&y={y}&z={z}', {
    subdomains: ['mt0', 'mt1', 'mt2', 'mt3'],
    maxZoom: 19,
    attribution: '&copy; Google',
  }),
  'Esri 衛星圖': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19,
    attribution: '&copy; Esri, DigitalGlobe, GeoEye, Earthstar Geographics, CNES/Airbus DS, USDA, USGS, AeroGRID, IGN, and the GIS User Community',
  }),
};
if (DATA.config.stadia_api_key) {
  baseLayers['Stamen 地形圖'] = L.tileLayer(
    'https://tiles.stadiamaps.com/tiles/stamen_terrain/{z}/{x}/{y}{r}.png?api_key=' + encodeURIComponent(DATA.config.stadia_api_key),
    {
      maxZoom: 20,
      attribution: '&copy; Stadia Maps &copy; Stamen Design &copy; OpenMapTiles &copy; OpenStreetMap',
    }
  );
}

let activeBase = null;
function setBasemap(name) {
  if (activeBase) map.removeLayer(activeBase);
  activeBase = baseLayers[name];
  activeBase.addTo(map);
}

const basePanel = document.getElementById('basemap-panel');
Object.keys(baseLayers).forEach((name, i) => {
  const label = document.createElement('label');
  label.className = 'base-opt';
  const radio = document.createElement('input');
  radio.type = 'radio';
  radio.name = 'basemap';
  radio.value = name;
  if (i === 0) radio.checked = true;
  radio.addEventListener('change', () => {
    if (radio.checked) setBasemap(name);
  });
  label.appendChild(radio);
  label.appendChild(document.createTextNode(name));
  basePanel.appendChild(label);
});
setBasemap(Object.keys(baseLayers)[0]);

const overlays = {};
const allBounds = [];
const stormSelections = {};
const hiddenAgencies = new Set();

if (DATA.taiwan_100km_buffer) {
  const buf = DATA.taiwan_100km_buffer;
  const bufLayer = L.polyline(buf.line.map(p => [p.lat, p.lon]), {
    color: buf.color, weight: 1.2, opacity: 0.9,
  });
  overlays['臺灣 100km 海域線'] = L.layerGroup([bufLayer]).addTo(map);
}

// ── 經緯度線 (graticule) ────────────────────────────────────────
function buildGraticule(step) {
  const grp = L.layerGroup();
  const latMin = -80, latMax = 80, lonMin = -180, lonMax = 180;
  const common = { color: '#9aa0a6', weight: 0.6, opacity: 0.55, dashArray: '2,4', interactive: false };
  for (let lat = latMin; lat <= latMax; lat += step) {
    L.polyline([[lat, lonMin], [lat, lonMax]], common).addTo(grp);
  }
  for (let lon = lonMin; lon <= lonMax; lon += step) {
    L.polyline([[latMin, lon], [latMax, lon]], common).addTo(grp);
  }
  return grp;
}
const graticuleGrp = buildGraticule(5).addTo(map);
overlays['經緯度線'] = graticuleGrp;

function collectBounds(info) {
  (info.agencies || []).forEach(ag =>
    (ag.forecasts || []).forEach(fc => allBounds.push([fc.lat, fc.lon])));
}

function selectedInfo(t, selIdx) {
  if (selIdx != null && t.entries && t.entries[selIdx]) {
    return t.entries[selIdx].data;
  }
  return t.latest;
}

function drawForecast(t, grp, selIdx, upto) {
  grp.clearLayers();
  const info = selectedInfo(t, selIdx);
  for (const ag of (info.agencies || [])) {
    const agency = ag.agency;
    if (hiddenAgencies.has(agency)) continue;
    let fcs = (ag.forecasts || []).slice().sort((a, b) => a.tau - b.tau);
    if (!fcs.length) continue;
    if (upto != null) {
      fcs = fcs.filter(fc => {
        const t0 = fcTimeAbs(info, fc);
        return t0 == null || t0 <= upto;
      });
      if (!fcs.length) continue;
    }
    const color = AGENCY_COLORS[agency] || '#888888';
    const cn = AGENCY_CN[agency] || agency;

    if (fcs.length >= 2) {
      L.polyline(fcs.map(f => [f.lat, f.lon]), {
        color, weight: 2.5, opacity: 0.9,
      }).addTo(grp);
    }

    fcs.forEach(fc => {
      const grade = pointGrade(fc, info);
      const radius = radiusFromMaps(fc, info, '_cwa_fc_radius7_map', '_cwa_fc_radius7_map_by_tau') || windKtToRadius(fc.wind_kt);
      const radius10 = radiusFromMaps(fc, info, '_cwa_fc_radius10_map', '_cwa_fc_radius10_map_by_tau') || windKtToRadius10(fc.wind_kt);
      const windStr = ktToMsStr(fc.wind_kt);
      const tdState = (info._td_state_map || {})[String(fc.tau)];
      const tdLine = tdState ? `<br>狀態轉換：${escapeHtml(tdState)}` : '';
      const popup =
        `<div class="popup">` +
        `<b>${escapeHtml(t.storm_name_cn)} ${escapeHtml(t.storm_name)}</b><br>` +
        `機構：${escapeHtml(cn)}（${escapeHtml(agency)}）<br>` +
        `時間：${escapeHtml(fcTimeLTC(info, fc))}<br>` +
        `位置：${fc.lat.toFixed(1)}°N, ${fc.lon.toFixed(1)}°E<br>` +
        `風速：${windStr}${grade ? `（${grade}）` : ''}${tdLine}<br>` +
        `${radius > 0 ? `七級暴風半徑：${radius} km${radius10 > 0 ? `<br>十級暴風半徑：${radius10} km` : ''}` : ''}</div>`;

      let mk;
      if (fc.tau === 0) {
        mk = L.marker([fc.lat, fc.lon], {
          icon: typhoonCenterIcon(fc.wind_kt * 0.514444, color),
        }).addTo(grp);
      } else {
        mk = L.circleMarker([fc.lat, fc.lon], {
          radius: 4.5, color: '#ffffff', weight: 1,
          fillColor: color, fillOpacity: 0.95,
        }).addTo(grp);
      }
      mk.bindTooltip(`${escapeHtml(t.storm_name_cn)}（${escapeHtml(agency)}）${escapeHtml(fcTimeLTC(info, fc))} ${windStr}`);
      mk.bindPopup(popup);
    });
  }
}

function drawHistorical(t, grp) {
  grp.clearLayers();
  const pts = [];
  (t.entries || []).forEach(e => {
    outer:
    for (const ag of (e.data.agencies || [])) {
      for (const fc of (ag.forecasts || [])) {
        if (fc.tau === 0) { pts.push([fc.lat, fc.lon]); break outer; }
      }
    }
  });
  if (!pts.length) return;
  if (pts.length >= 2) {
    L.polyline(pts, { color: '#888888', weight: 1.5, opacity: 0.6, dashArray: '5,5' }).addTo(grp);
  }
  L.marker(pts[0], { icon: trackIcon('✕') }).addTo(grp);
  if (pts.length > 1) {
    L.marker(pts[pts.length - 1], { icon: trackIcon('★') }).addTo(grp);
  }
}

const ECMWF_COLOR = '#4527A0';
const ECMWF_ENS_COLOR = '#7986CB';
function drawECMWF(t, hresGrp, ensGrp) {
  hresGrp.clearLayers();
  ensGrp.clearLayers();
  const ec = t.ecmwf;
  if (!ec) return;
  const hres = (ec.hres || []).filter(p => p.lat != null && p.lon != null);
  const ens = (ec.ens_mean || []).filter(p => p.lat != null && p.lon != null);
  if (ens.length >= 2) {
    L.polyline(ens.map(p => [p.lat, p.lon]), {
      color: ECMWF_ENS_COLOR, weight: 1.5, opacity: 0.8, dashArray: '2,4',
    }).addTo(ensGrp);
  }
  if (hres.length >= 2) {
    L.polyline(hres.map(p => [p.lat, p.lon]), {
      color: ECMWF_COLOR, weight: 2, opacity: 0.9,
    }).addTo(hresGrp);
  }
  const drawPts = (pts, grp, color, label) => pts.forEach(p => {
    const timeStr = ecmwfTimeLTC(DATA.ecmwf_run, p.tau);
    const windStr = p.wind_ms != null ? `${p.wind_ms} m/s` : '?';
    const pressStr = p.pmsl_hpa != null ? `${p.pmsl_hpa} hPa` : '?';
    const mk = L.circleMarker([p.lat, p.lon], {
      radius: 4,
      color: '#ffffff', weight: 1,
      fillColor: color, fillOpacity: 0.95,
    }).addTo(grp);
    mk.bindTooltip(`ECMWF ${label} ${escapeHtml(timeStr)} ${windStr}`);
    mk.bindPopup(
      `<div class="popup">` +
      `<b>ECMWF ${label}</b><br>` +
      `預報時間：${escapeHtml(timeStr)}<br>` +
      `位置：${p.lat.toFixed(1)}°N, ${p.lon.toFixed(1)}°E<br>` +
      `最大風速：${windStr}<br>` +
      `中心氣壓：${pressStr}</div>`
    );
  });
  drawPts(ens, ensGrp, ECMWF_ENS_COLOR, 'ENS mean');
  drawPts(hres, hresGrp, ECMWF_COLOR, 'HRES');
}

function firstValidFtu() {
  for (const t of (DATA.typhoons || [])) {
    const s = t.forecast_time_utc || '';
    if (s && utcToLTC(s) !== '—') return s;
  }
  return '';
}

const meta = document.getElementById('meta');
meta.innerHTML =
  `產生時間：${escapeHtml(DATA.generated_at)}<br>` +
  `預報時間：${escapeHtml(utcToLTC(firstValidFtu()))}<br>` +
  `資料：${escapeHtml(DATA.typhoons.length)} 個颱風`;

const panel = document.getElementById('typhoon-panel');
const typhoonState = [];

DATA.typhoons.forEach((t, i) => {
  collectBounds(t.latest);
  (t.entries || []).forEach(e => collectBounds(e.data));

  const name = `${t.storm_name_cn} ${t.storm_name}`;
  const fcGrp = L.layerGroup().addTo(map);
  const histGrp = L.layerGroup().addTo(map);
  const ecmwfHresGrp = L.layerGroup().addTo(map);
  const ecmwfEnsGrp = L.layerGroup().addTo(map);
  overlays[name] = fcGrp;
  overlays[`${name} 歷史軌跡`] = histGrp;
  overlays[`${name} ECMWF HRES`] = ecmwfHresGrp;
  overlays[`${name} ECMWF ENS`] = ecmwfEnsGrp;

  const wrap = document.createElement('div');
  wrap.className = 'typhoon-sel';
  const label = document.createElement('label');
  label.textContent = `${t.storm_name_cn}（${t.storm_name}）`;
  const sel = document.createElement('select');
  const choices = (t.entries && t.entries.length) ? t.entries : [];
  if (choices.length) {
    for (let j = choices.length - 1; j >= 0; j--) {
      const opt = document.createElement('option');
      opt.value = j;
      opt.textContent = `#${choices[j].index} ${utcToLTC(choices[j].forecast_time_utc)}`;
      sel.appendChild(opt);
    }
    sel.value = choices.length - 1;
  } else {
    const opt = document.createElement('option');
    opt.value = -1;
    opt.textContent = '僅有最新預報';
    sel.appendChild(opt);
    sel.disabled = true;
  }
  wrap.appendChild(label);
  wrap.appendChild(sel);
  panel.appendChild(wrap);

  typhoonState.push({ sel, lastIdx: sel.value === '' ? -1 : +sel.value, fcGrp });
  sel.addEventListener('change', () => {
    const idx = sel.value === '' ? -1 : +sel.value;
    typhoonState[i].lastIdx = idx;
    stopPlayback('reset');
    drawForecast(t, fcGrp, idx);
    rebuildTimelines();
  });

  drawHistorical(t, histGrp);
  drawForecast(t, fcGrp, typhoonState[i].lastIdx);
  drawECMWF(t, ecmwfHresGrp, ecmwfEnsGrp);
});

function redrawAllForecasts() {
  DATA.typhoons.forEach((t, i) => drawForecast(t, typhoonState[i].fcGrp, typhoonState[i].lastIdx));
}

const agencyPanel = document.getElementById('agency-panel');
const seenAgencies = new Set();
const scanAgencies = info => (info.agencies || []).forEach(ag => seenAgencies.add(ag.agency));
DATA.typhoons.forEach(t => {
  scanAgencies(t.latest);
  (t.entries || []).forEach(e => scanAgencies(e.data));
});
const agencyList = Object.keys(AGENCY_CN).filter(a => seenAgencies.has(a))
  .concat(Array.from(seenAgencies).filter(a => !AGENCY_CN[a]));
agencyList.forEach(a => {
  const label = document.createElement('label');
  label.className = 'base-opt';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.checked = true;
  cb.addEventListener('change', () => {
    if (cb.checked) hiddenAgencies.delete(a); else hiddenAgencies.add(a);
    if (playback.playing) renderPlayback(); else redrawAllForecasts();
  });
  label.appendChild(cb);
  label.appendChild(document.createTextNode(`${AGENCY_CN[a] || a}（${a}）`));
  agencyPanel.appendChild(label);
});

if (allBounds.length) {
  map.fitBounds(allBounds, { padding: [30, 30] });
} else {
  map.setView([24, 121], 7);
}

// ── 時間播放 (time playback) ──────────────────────────────────────────────
const PLAY_COLORS = ['#E0004D', '#00A2E8', '#FF7F27', '#22B573', '#A349A4', '#3F48CC', '#880015', '#8E24AA'];
const DUR_MS = 20000;
const playback = {
  playing: false, clock: 0, tStart: 0, tEnd: 0, timer: null,
  timelines: [], quads: [], markers: [],
};
const playbackGrp = L.layerGroup().addTo(map);
const pinsGrp = L.layerGroup().addTo(map);
overlays['固定風圈標註'] = pinsGrp;

function buildTimeline(t, info) {
  const base = parseUtcMs(info.forecast_time_utc);
  if (base == null) return [];
  const byTime = new Map();
  const setPos = (tm, lat, lon, agency, wind) => {
    const key = Math.round(tm);
    const cur = byTime.get(key);
    if (!cur || (cur.agency !== 'CWA' && agency === 'CWA')) {
      byTime.set(key, { lat, lon, agency, wind });
    }
  };
  (t.entries || []).forEach(e => {
    const tm = parseUtcMs(e.forecast_time_utc);
    if (tm == null) return;
    outer:
    for (const ag of (e.data.agencies || [])) {
      for (const fc of (ag.forecasts || [])) {
        if (fc.tau === 0) { setPos(tm, fc.lat, fc.lon, ag.agency, fc.wind_kt); break outer; }
      }
    }
  });
  (info.agencies || []).forEach(ag => {
    (ag.forecasts || []).forEach(fc => {
      const tm = base + (fc.tau || 0) * 3600000;
      setPos(tm, fc.lat, fc.lon, ag.agency, fc.wind_kt);
    });
  });
  return Array.from(byTime.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([t, p]) => ({ t, lat: p.lat, lon: p.lon, wind: p.wind }));
}

function rebuildTimelines() {
  playback.timelines = [];
  playback.quads = [];
  DATA.typhoons.forEach((t, i) => {
    const info = selectedInfo(t, typhoonState[i].lastIdx);
    playback.timelines.push(buildTimeline(t, info));
    playback.quads.push(buildQuadTimeline(info, t.latest || {}));
  });
  playback.tStart = Infinity;
  playback.tEnd = -Infinity;
  playback.timelines.forEach(tl => {
    if (tl.length) {
      playback.tStart = Math.min(playback.tStart, tl[0].t);
      playback.tEnd = Math.max(playback.tEnd, tl[tl.length - 1].t);
    }
  });
  if (playback.tStart === Infinity) { playback.tStart = 0; playback.tEnd = 0; }
}

// CWA analysis 4-quadrant radii keyed by position; build a time-sorted list so
// the playback marker can morph the quadrant circle as it moves along the track.
function buildQuadTimeline(info, latest) {
  const r7q = latest['_cwa_an_radius7_quad_map'] || {};
  const r10q = latest['_cwa_an_radius10_quad_map'] || {};
  const r7avg = latest['_cwa_an_radius7_map'] || {};
  const r10avg = latest['_cwa_an_radius10_map'] || {};
  const fcR7 = latest['_cwa_fc_radius7_map_by_tau'] || {};
  const fcR10 = latest['_cwa_fc_radius10_map_by_tau'] || {};
  const base = parseUtcMs(info.forecast_time_utc);
  const out = [];
  if (base == null) return out;
  for (const ag of (info.agencies || [])) {
    if (ag.agency !== 'CWA') continue;
    (ag.forecasts || []).forEach(fc => {
      const tau = fc.tau || 0;
      const tAbs = base + tau * 3600000;
      const key = (Math.round(fc.lat * 10) / 10).toFixed(1) + ',' + (Math.round(fc.lon * 10) / 10).toFixed(1);
      let r7Entry = null, r10Entry = null, r7avgVal = null, r10avgVal = null;
      if (tau === 0) {
        r7Entry = r7q[key] || null;
        r10Entry = r10q[key] || null;
        r7avgVal = r7avg[key] || null;
        r10avgVal = r10avg[key] || null;
      } else {
        const fr7 = fcR7[String(tau)];
        const fr10 = fcR10[String(tau)];
        if (fr7 != null) r7avgVal = fr7;
        if (fr10 != null) r10avgVal = fr10;
      }
      out.push({ t: tAbs, r7: r7Entry, r10: r10Entry, r7avg: r7avgVal, r10avg: r10avgVal });
    });
  }
  return out.sort((a, b) => a.t - b.t);
}

function quadAt(qt, T) {
  if (!qt || !qt.length) return null;
  if (T <= qt[0].t) return qt[0];
  if (T >= qt[qt.length - 1].t) return qt[qt.length - 1];
  for (let i = 0; i < qt.length - 1; i++) {
    const a = qt[i], b = qt[i + 1];
    if (T >= a.t && T < b.t) {
      // 不內插：暴風半徑只在 CWA 有資料的時間點改變，區間內沿用前一個資料點（階梯式）
      return {
        r7: a.r7 || null,
        r10: a.r10 || null,
        r7avg: a.r7avg != null ? a.r7avg : null,
        r10avg: a.r10avg != null ? a.r10avg : null,
      };
    }
  }
  return null;
}

function circleRadii(r) {
  return { NE: r, SE: r, SW: r, NW: r };
}

function anyRadius(radii) {
  return !!(radii && (radii.NE || radii.SE || radii.SW || radii.NW));
}

function posAt(timeline, T) {
  if (!timeline.length) return null;
  const first = timeline[0];
  const last = timeline[timeline.length - 1];
  if (T <= first.t) return { lat: first.lat, lon: first.lon, wind: first.wind };
  if (T >= last.t) return { lat: last.lat, lon: last.lon, wind: last.wind };
  for (let i = 0; i < timeline.length - 1; i++) {
    const a = timeline[i], b = timeline[i + 1];
    if (T >= a.t && T <= b.t) {
      const f = (T - a.t) / (b.t - a.t);
      let wind = a.wind;
      if (a.wind != null && b.wind != null) wind = Math.round(a.wind + (b.wind - a.wind) * f);
      return {
        lat: a.lat + (b.lat - a.lat) * f,
        lon: a.lon + (b.lon - a.lon) * f,
        wind,
      };
    }
  }
  return null;
}

function clearMarkers() {
  playback.markers.forEach(st => {
    if (!st) return;
    if (st.m) playbackGrp.removeLayer(st.m);
    if (st.cU) playbackGrp.removeLayer(st.cU);
    if (st.c) playbackGrp.removeLayer(st.c);
    if (st.c10U) playbackGrp.removeLayer(st.c10U);
    if (st.c10) playbackGrp.removeLayer(st.c10);
    if (st.cL) radiusLabelGrp.removeLayer(st.cL);
    if (st.c10L) radiusLabelGrp.removeLayer(st.c10L);
  });
  playback.markers = [];
}

function renderPlayback() {
  const T = playback.clock;
  DATA.typhoons.forEach((t, i) => {
    const st = typhoonState[i];
    drawForecast(t, st.fcGrp, st.lastIdx, T);
    const pos = posAt(playback.timelines[i] || [], T);
    if (pos) {
      const quad = quadAt(playback.quads[i] || [], T);
      const r7 = (quad && quad.r7) || null;
      const r10 = (quad && quad.r10) || null;
      const r7avg = (quad && quad.r7avg != null) ? quad.r7avg : windKtToRadius(pos.wind);
      const r10avg = (quad && quad.r10avg != null) ? quad.r10avg : windKtToRadius10(pos.wind);
      const windMs = pos.wind != null ? pos.wind * 0.514444 : 0;
      const tier = windTier(windMs);
      if (!playback.markers[i]) {
        playback.markers[i] = {
          m: L.marker([pos.lat, pos.lon], {
            icon: typhoonCenterIcon(windMs, PLAY_COLORS[i % PLAY_COLORS.length]),
          }).addTo(playbackGrp),
          mTier: tier,
          cU: L.polygon([], { color: '#ffffff', weight: 4.2, opacity: 0.9, fill: false, dashArray: '8 4' }).addTo(playbackGrp),
          c: L.polygon([], {
            color: CWA_COLOR, weight: 1.2, opacity: 0.7,
            fillColor: CWA_COLOR, fillOpacity: 0.06, dashArray: '8 4',
          }).addTo(playbackGrp),
          cAvgU: null,
          cAvg: null,
          cL: null,
          c10U: null,
          c10: null,
          c10AvgU: null,
          c10Avg: null,
          c10L: null,
        };
      }
      playback.markers[i].m.setLatLng([pos.lat, pos.lon]);
      const curMs = pos.wind != null ? pos.wind * 0.514444 : 0;
      const curTier = windTier(curMs);
      if (curTier !== playback.markers[i].mTier) {
        playback.markers[i].m.setIcon(typhoonCenterIcon(curMs, PLAY_COLORS[i % PLAY_COLORS.length]));
        playback.markers[i].mTier = curTier;
      }
      const hasQuad7 = anyRadius(r7);
      const pts7 = hasQuad7 ? quadrantCirclePoints(pos.lat, pos.lon, r7) : [];
      playback.markers[i].cU.setLatLngs(pts7);
      playback.markers[i].c.setLatLngs(pts7);
      const r7label = (r7avg && r7avg > 0) ? r7avg : northRadius(r7);
      if (r7label) {
        if (!playback.markers[i].cL) {
          playback.markers[i].cL = addRadiusLabel(radiusLabelGrp, pos.lat, pos.lon, r7label, 'r7');
        } else {
          updateRadiusLabel(playback.markers[i].cL, pos.lat, pos.lon, r7label);
        }
      }
      if (!hasQuad7 && r7avg && r7avg > 0) {
        const avgCircle = quadrantCirclePoints(pos.lat, pos.lon, circleRadii(r7avg));
        if (!playback.markers[i].cAvgU) {
          playback.markers[i].cAvgU = L.polygon(avgCircle, { color: '#ffffff', weight: 3, opacity: 0.9, fill: false }).addTo(playbackGrp);
          playback.markers[i].cAvg = L.polygon(avgCircle, { color: CWA_COLOR, weight: 1, opacity: 0.7, fill: false }).addTo(playbackGrp);
        } else {
          playback.markers[i].cAvgU.setLatLngs(avgCircle);
          playback.markers[i].cAvg.setLatLngs(avgCircle);
        }
      } else if (playback.markers[i].cAvg) {
        playbackGrp.removeLayer(playback.markers[i].cAvgU);
        playbackGrp.removeLayer(playback.markers[i].cAvg);
        playback.markers[i].cAvgU = null;
        playback.markers[i].cAvg = null;
      }
      const hasQuad10 = anyRadius(r10);
      if (hasQuad10) {
        if (!playback.markers[i].c10) {
          playback.markers[i].c10U = L.polygon([], { color: '#ffffff', weight: 4, opacity: 0.9, fill: false, dashArray: '8 4' }).addTo(playbackGrp);
          playback.markers[i].c10 = L.polygon([], {
            color: '#FF8C00', weight: 1, opacity: 0.7,
            fill: false, dashArray: '8 4',
          }).addTo(playbackGrp);
        }
        const pts10 = quadrantCirclePoints(pos.lat, pos.lon, r10);
        playback.markers[i].c10U.setLatLngs(pts10);
        playback.markers[i].c10.setLatLngs(pts10);
      } else if (playback.markers[i].c10) {
        playbackGrp.removeLayer(playback.markers[i].c10U);
        playbackGrp.removeLayer(playback.markers[i].c10);
        playback.markers[i].c10U = null;
        playback.markers[i].c10 = null;
      }
      const r10label = (r10avg && r10avg > 0) ? r10avg : (hasQuad10 ? northRadius(r10) : null);
      if (r10label) {
        if (!playback.markers[i].c10L) {
          playback.markers[i].c10L = addRadiusLabel(radiusLabelGrp, pos.lat, pos.lon, r10label, 'r10');
        } else {
          updateRadiusLabel(playback.markers[i].c10L, pos.lat, pos.lon, r10label);
        }
      } else if (playback.markers[i].c10L) {
        radiusLabelGrp.removeLayer(playback.markers[i].c10L);
        playback.markers[i].c10L = null;
      }
      if (!hasQuad10 && r10avg && r10avg > 0) {
        const avgCircle10 = quadrantCirclePoints(pos.lat, pos.lon, circleRadii(r10avg));
        if (!playback.markers[i].c10AvgU) {
          playback.markers[i].c10AvgU = L.polygon(avgCircle10, { color: '#ffffff', weight: 3, opacity: 0.9, fill: false }).addTo(playbackGrp);
          playback.markers[i].c10Avg = L.polygon(avgCircle10, { color: '#FF8C00', weight: 1, opacity: 0.7, fill: false }).addTo(playbackGrp);
        } else {
          playback.markers[i].c10AvgU.setLatLngs(avgCircle10);
          playback.markers[i].c10Avg.setLatLngs(avgCircle10);
        }
      } else if (playback.markers[i].c10Avg) {
        playbackGrp.removeLayer(playback.markers[i].c10AvgU);
        playbackGrp.removeLayer(playback.markers[i].c10Avg);
        playback.markers[i].c10AvgU = null;
        playback.markers[i].c10Avg = null;
      }
    }
  });
  const span = playback.tEnd - playback.tStart;
  playSlider.value = span > 0 ? Math.round(((T - playback.tStart) / span) * 1000) : 1000;
  playTime.textContent = span > 0 ? utcMsToLTC(T) : '--';
}

function renderFull() {
  DATA.typhoons.forEach((t, i) => drawForecast(t, typhoonState[i].fcGrp, typhoonState[i].lastIdx));
  clearMarkers();
  renderPlayback();
}

let lastFrameTs = null;
function playTick(ts) {
  if (!playback.playing) return;
  if (lastFrameTs == null) lastFrameTs = ts;
  const elapsed = ts - lastFrameTs;
  lastFrameTs = ts;
  const span = playback.tEnd - playback.tStart;
  if (span <= 0) { stopPlayback(); return; }
  playback.clock += (elapsed / DUR_MS) * span;
  if (playback.clock >= playback.tEnd) {
    playback.clock = playback.tEnd;
    playback.playing = false;
    cancelAnimationFrame(playback.timer);
    renderPlayback();
    updatePlayBtn();
    return;
  }
  renderPlayback();
  playback.timer = requestAnimationFrame(playTick);
}

function updatePlayBtn() {
  playBtn.textContent = playback.playing ? '⏸ 暫停' : '▶ 播放';
}

function stopPlayback(mode) {
  playback.playing = false;
  cancelAnimationFrame(playback.timer);
  if (mode === 'reset') {
    playback.clock = playback.tEnd;
    playSlider.value = 1000;
    renderFull();
    playTime.textContent = playback.tEnd > playback.tStart ? utcMsToLTC(playback.tEnd) : '--';
    updatePlayBtn();
  } else {
    renderPlayback();
    updatePlayBtn();
  }
}

const playBtn = document.getElementById('play-btn');
const resetBtn = document.getElementById('reset-btn');
const playSlider = document.getElementById('play-slider');
const playTime = document.getElementById('play-time');

playBtn.addEventListener('click', () => {
  if (playback.playing) {
    stopPlayback();
    return;
  }
  if (playback.tEnd <= playback.tStart) return;
  if (playback.clock >= playback.tEnd) playback.clock = playback.tStart;
  playback.playing = true;
  lastFrameTs = null;
  renderPlayback();
  playback.timer = requestAnimationFrame(playTick);
  updatePlayBtn();
});

resetBtn.addEventListener('click', () => stopPlayback('reset'));

const prevHourBtn = document.getElementById('prev-hour-btn');
const nextHourBtn = document.getElementById('next-hour-btn');
function nudgeClock(dh) {
  playback.playing = false;
  cancelAnimationFrame(playback.timer);
  const span = playback.tEnd - playback.tStart;
  if (span <= 0) return;
  playback.clock = Math.max(playback.tStart, Math.min(playback.tEnd, playback.clock + dh * 3600000));
  renderPlayback();
  updatePlayBtn();
}
prevHourBtn.addEventListener('click', () => nudgeClock(-1));
nextHourBtn.addEventListener('click', () => nudgeClock(1));

const nowBtn = document.getElementById('now-btn');
nowBtn.addEventListener('click', () => {
  playback.playing = false;
  cancelAnimationFrame(playback.timer);
  const nowMs = Date.now();
  const span = playback.tEnd - playback.tStart;
  if (span <= 0) return;
  playback.clock = Math.max(playback.tStart, Math.min(playback.tEnd, nowMs));
  renderPlayback();
  updatePlayBtn();
});

playSlider.addEventListener('input', () => {
  playback.playing = false;
  cancelAnimationFrame(playback.timer);
  const span = playback.tEnd - playback.tStart;
  playback.clock = span > 0 ? playback.tStart + (+playSlider.value / 1000) * span : playback.tStart;
  renderPlayback();
  updatePlayBtn();
});

// ── 固定風圈標註 (pinned wind circles) ─────────────────────────────────────
let pins = [];

function pinCurrentTime() {
  const T = playback.clock;
  const key = Math.round(T);
  DATA.typhoons.forEach((t, i) => {
    const pos = posAt(playback.timelines[i] || [], T);
    if (!pos) return;
    if (pins.some(p => p.i === i && Math.round(p.t) === key)) return;
    const quad = quadAt(playback.quads[i] || [], T);
    const r7 = (quad && quad.r7) || null;
    const r10 = (quad && quad.r10) || null;
    const r7avg = (quad && quad.r7avg != null) ? quad.r7avg : windKtToRadius(pos.wind);
    const r10avg = (quad && quad.r10avg != null) ? quad.r10avg : windKtToRadius10(pos.wind);
    pins.push({ t: T, i, lat: pos.lat, lon: pos.lon, r7, r10, r7avg, r10avg });
  });
  drawPins();
}

function drawPins() {
  pinsGrp.clearLayers();
  pinLabelGrp.clearLayers();
  pinList.innerHTML = '';
  pins.forEach((p, idx) => {
    const label = `${DATA.typhoons[p.i].storm_name_cn} ${utcMsToLTC(p.t)}`;
    if (anyRadius(p.r7)) {
      polyWithHalo(pinsGrp, quadrantCirclePoints(p.lat, p.lon, p.r7), CWA_COLOR, 1.5, 0.7, CWA_COLOR, 0.05, true);
      const rn7 = (p.r7avg && p.r7avg > 0) ? p.r7avg : northRadius(p.r7);
      if (rn7) addRadiusLabel(pinLabelGrp, p.lat, p.lon, rn7, 'r7');
    }
    if (p.r7avg && p.r7avg > 0) {
      polyWithHalo(pinsGrp, quadrantCirclePoints(p.lat, p.lon, circleRadii(p.r7avg)), CWA_COLOR, 1.2, 0.7, CWA_COLOR, 0);
    }
    if (anyRadius(p.r10)) {
      polyWithHalo(pinsGrp, quadrantCirclePoints(p.lat, p.lon, p.r10), '#FF8C00', 1, 0.7, '#FF8C00', 0, true);
      const rn10 = (p.r10avg && p.r10avg > 0) ? p.r10avg : northRadius(p.r10);
      if (rn10) addRadiusLabel(pinLabelGrp, p.lat, p.lon, rn10, 'r10');
    }
    if (p.r10avg && p.r10avg > 0) {
      polyWithHalo(pinsGrp, quadrantCirclePoints(p.lat, p.lon, circleRadii(p.r10avg)), '#FF8C00', 1, 0.7, '#FF8C00', 0);
    }
    L.circleMarker([p.lat, p.lon], {
      radius: 5, color: '#ffffff', weight: 1,
      fillColor: PLAY_COLORS[p.i % PLAY_COLORS.length], fillOpacity: 1,
    }).addTo(pinsGrp).bindTooltip(label);
    const item = document.createElement('div');
    item.className = 'pin-item';
    const span = document.createElement('span');
    span.textContent = `📌 ${label}`;
    const rm = document.createElement('button');
    rm.type = 'button';
    rm.textContent = '✕';
    rm.title = '刪除此標記';
    rm.addEventListener('click', () => { pins.splice(idx, 1); drawPins(); });
    item.appendChild(span);
    item.appendChild(rm);
    pinList.appendChild(item);
  });
}

const pinBtn = document.getElementById('pin-btn');
const clearPinsBtn = document.getElementById('clear-pins-btn');
const pinList = document.getElementById('pin-list');
pinBtn.addEventListener('click', pinCurrentTime);
clearPinsBtn.addEventListener('click', () => { pins = []; drawPins(); });

const pinHelpBtn = document.getElementById('pin-help-btn');
const pinHint = document.getElementById('pin-hint');
pinHelpBtn.addEventListener('click', () => {
  const show = pinHint.hidden;
  pinHint.hidden = !show;
  pinHelpBtn.setAttribute('aria-pressed', show ? 'true' : 'false');
});

const panelEl = document.getElementById('panel');
const panelCollapseBtn = document.getElementById('panel-collapse-btn');
panelCollapseBtn.addEventListener('click', () => {
  const collapsed = panelEl.classList.toggle('collapsed');
  panelCollapseBtn.textContent = collapsed ? '▶' : '◀';
  panelCollapseBtn.title = collapsed ? '展開面板' : '收合面板';
});

const helpModal = document.getElementById('help-modal');
function openHelp() { helpModal.classList.add('open'); }
function closeHelp() { helpModal.classList.remove('open'); }
document.getElementById('help-btn').addEventListener('click', openHelp);
document.getElementById('help-close').addEventListener('click', closeHelp);
helpModal.addEventListener('click', e => { if (e.target === helpModal) closeHelp(); });

(function buildTyphoonIconLegend() {
  const el = document.getElementById('typhoon-icon-legend');
  if (!el) return;
  const rows = [
    { ms: 25, label: '輕度颱風（17–32 m/s）：深灰空心圓' },
    { ms: 40, label: '中度颱風（32–51 m/s）：綠色實心圓' },
    { ms: 60, label: '強烈颱風（≥51 m/s）：紅色實心圓' },
    { ms: 10, label: '熱帶性低氣壓（<17 m/s）：灰點' },
  ];
  rows.forEach(r => {
    const row = document.createElement('div');
    row.className = 'ty-icon-row';
    row.innerHTML = typhoonCenterIcon(r.ms).html + '<span>' + r.label + '</span>';
    el.appendChild(row);
  });
})();
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeHelp(); });

rebuildTimelines();
stopPlayback('reset');

const brandCtl = L.control({ position: 'topleft' });
brandCtl.onAdd = function () {
  const el = L.DomUtil.create('div');
  el.innerHTML =
    `<div id="brand">` +
    `<div class="brand-ico">🌀</div>` +
    `<div class="brand-meta">` +
    `<div class="brand-name">多采颱跡店</div>` +
    `<div class="brand-sub">ManySplendid Typhoon Track Shop</div>` +
    `</div></div>`;
  return el;
};
brandCtl.addTo(map);
L.control.zoom({ position: 'topleft' }).addTo(map);

const legend = L.control({ position: 'topleft' });
legend.onAdd = function () {
  const div = L.DomUtil.create('div', 'legend');
  let h = '<h4>各國機構</h4>';
  Object.keys(AGENCY_CN).forEach(a => {
    h += `<div class="legend-row"><span class="swatch" style="background:${AGENCY_COLORS[a] || '#888'}"></span>${escapeHtml(AGENCY_CN[a])}（${escapeHtml(a)}）</div>`;
  });
  h += '<details class="legend-help"><summary>?</summary>';
  h += '<div class="legend-note">紅色虛線圈：CWA 四象限七級暴風半徑</div>';
  h += '<div class="legend-note">紅色實線圈：CWA 平均七級暴風半徑（CWA API 或依風速估算）</div>';
  h += '<div class="legend-note">橘色虛線圈：CWA 四象限十級暴風半徑</div>';
  h += '<div class="legend-note">橘色實線圈：CWA 平均十級暴風半徑（風速未達十級風則不畫）</div>';
  h += '<div class="legend-note">播放時：移動標記旁的四象限虛線多邊形為 CWA 分析七級/十級風圈，實線圓為平均半徑</div>';
  h += '<div class="legend-note">📌 固定風圈標註：時間軸選定時間後按「固定此時間風圈」留在圖上</div>';
  h += '<div class="legend-note">灰色虛線：歷史實際軌跡（✕ 起點 / ★ 最新）</div>';
  if (DATA.ecmwf_run) {
    h += `<div class="legend-note">ECMWF（Run ${escapeHtml(DATA.ecmwf_run)}）：深靛實線＝HRES 決定性、淺靛虛線＝ENS 系集平均（51 成員），可分別開關</div>`;
  }
  if (DATA.taiwan_100km_buffer) {
    h += `<div class="legend-row"><span class="swatch" style="background:${DATA.taiwan_100km_buffer.color}"></span>臺灣 100km 海域線</div>`;
  }
  h += '</details>';
  div.innerHTML = h;
  return div;
};
legend.addTo(map);

const layersCtl = L.control.layers(null, overlays, { collapsed: true });
const NARROW_MQ = window.matchMedia('(max-width: 640px)');
layersCtl.setPosition(NARROW_MQ.matches ? 'topright' : 'bottomright');
layersCtl.addTo(map);
NARROW_MQ.addEventListener('change', e => {
  layersCtl.setPosition(e.matches ? 'topright' : 'bottomright');
});
</script>
</body>
</html>
"""


def main():
    import argparse
    ap = argparse.ArgumentParser(description="產生各國颱風路徑網頁（資料內嵌於 HTML）")
    ap.add_argument("--data-dir", default=OUTPUT_DIR,
                    help=f"JSON 資料所在目錄（預設 {OUTPUT_DIR}，教材用可指向教學資料夾）")
    ap.add_argument("--out", default=HTML_OUT,
                    help=f"輸出檔名（預設 {HTML_OUT}，教材用如 {TEACHING_HTML}）")
    args = ap.parse_args()

    teaching_mode = (args.out == TEACHING_HTML)
    if teaching_mode:
        page_title = "颱風路徑教材：白海豚（2026）"
        nav_link = (f'<a class="nav-link" href="{HTML_OUT}" '
                    'title="開啟即時更新網頁">↩ 回到即時更新網頁</a>')
    else:
        page_title = "各國颱風路徑"
        nav_link = (f'<a class="nav-link" href="{TEACHING_HTML}" '
                    'title="開啟教材範例網頁（白海豚 2026）">📚 教材範例：白海豚</a>')

    embedded = json.dumps(build_embedded(args.data_dir), ensure_ascii=False).replace("</", "<\\/")
    html_out = (HTML_TEMPLATE
                .replace("__PAGE_TITLE__", page_title)
                .replace("__NAV_LINK__", nav_link)
                .replace("__DATA__", embedded))
    out_path = os.path.join(OUTPUT_DIR, args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"Saved: {out_path} ({os.path.getsize(out_path):,} bytes)")
    print("Open it directly in a browser (no server needed).")
    cfg = load_json(CONFIG_PATH)
    if not cfg.get("stadia_api_key"):
        print("Hint: add a free Stadia Maps API key to config.json (stadia_api_key) to enable the Stamen 地形圖 basemap.")


if __name__ == "__main__":
    main()
