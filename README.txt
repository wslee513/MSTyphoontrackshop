Typhoon2000.ph Multi-Agency TC Forecast Parser & Visualizer
============================================================

Overview
--------
This tool fetches multi-agency tropical cyclone forecast data from
typhoon2000.ph, parses it into structured JSON, and generates
track maps with CWA 7-level (七級暴風半徑) and 10-level
(十級暴風半徑) storm radius overlays.

Files
-----
fetch_typhoon2000.py   - Fetch & parse forecast data from typhoon2000.ph
fetch_weathernext.py   - Fetch Google WeatherNext 2 AI forecast (via Open-Meteo free API)
fetch_ecmwf.py         - Fetch ECMWF Open Data HRES/ENS TC-track forecasts (free, CC-BY-4.0)
plot_typhoon.py        - Plot forecast tracks & storm radius on a map
plot_web.py            - Generate self-contained Leaflet web page (output/各國颱風路徑.html)
update_typhoon_web.bat - One-click update: fetch → fetch_weathernext → fetch_ecmwf → plot_web (double-click, or add arg nopause for Task Scheduler)
config.json            - Configuration (output path, agency names, colors, etc.)
output/                - Generated JSON data, PNG maps & HTML web page

Requirements
------------
Python 3.8+ with packages:
    requests, matplotlib, numpy, cartopy

Optional (for Taiwan 100km buffer):
    shapely, pyproj

Install dependencies:
    pip install requests matplotlib numpy cartopy
    pip install shapely pyproj   (optional, for 100km buffer)
    pip install ecmwf-opendata eccodes   (for fetch_ecmwf.py)

Usage
-----

1. 取得最新預報資料 (Fetch latest forecast data)
    python fetch_typhoon2000.py
    程式會自動從 CWA 開放資料 API 取得目前活躍颱風名稱，
    再查詢 typhoon2000.ph 取得多機構預報資料。
     - 僅 1 個颱風 → 直接擷取（不彈選擇視窗）
     - 2+ 個颱風 → 跳出視窗讓使用者選擇
    - 無颱風 → 需在 config.json 中加入 "typhoon_name" 手動指定
    執行後會在 output/ 產生 JSON 檔案。

1b. 取得 Google WeatherNext 2 AI 預報 (Fetch AI forecast)
    python fetch_weathernext.py
    讀取上一步的 output/各國颱風路徑.json，沿每顆颱風的 CWA 預報軌跡各點，
    向 Open-Meteo 免費 API（免金鑰）查詢 Google WeatherNext 2 ensemble mean 的
    風速（10m/100m）、海平面氣壓與氣溫，寫出 output/weathernext_各國颱風路徑.json。
    此步驟可於 fetch 之後執行（每顆颱風約 3~7 個軌跡點，需網路連線）。

1c. 取得 ECMWF 模式預報 (Fetch ECMWF HRES/ENS forecast)
    python fetch_ecmwf.py
    從 ECMWF Open Data（免費、免金鑰、CC-BY-4.0）下載最近一筆已釋出的熱帶氣旋
    路徑 BUFR 產品（stream=oper|enfo, type=tf），用 eccodes 以 ranked-key 方式
    解出每顆颱風的 HRES 決定性軌跡（實線）與 ENS 系集平均軌跡（51 個成員平均，
    虛線），寫出 output/ecmwf_各國颱風路徑.json。
    00/12z run 可達 +360h、06/18z 只到 +144h；某 run 若無颱風資料會 404，
    程式自動退回前一 run。ECMWF 以颱風名（longStormName）與 pipeline 的
    storm_name 比對；比對不到時該颱風不列入，exit code 為 1。

2. 繪製路徑圖 (Plot forecast track map)
    python plot_typhoon.py
    執行後會在 output/ 目錄產生 PNG 地圖。

    可選參數：指定歷史 entry index (由 _all.json 中的 index 決定)
    python plot_typhoon.py 3

3. 產生網頁地圖 (Generate Leaflet web map)
    python plot_web.py
    讀取最新 JSON、歷史資料與 WeatherNext AI 預報，產生 output/各國颱風路徑.html
    （資料內嵌，不需伺服器，直接在瀏覽器雙擊開啟即可）。內含各國路徑、
    CWA 七級暴風半徑圈（依風速估算）、歷史軌跡、每顆颱風的歷史 entry 下拉選單，
    以及 WeatherNext AI 預報軌跡（青綠色虛線，風速/氣壓/氣溫）與 ECMWF 模式
    預報軌跡（深靛 HRES 實線、淺靛 ENS 系集平均虛線）。底圖提供
    Google 地圖、Esri 衛星圖與 Stamen 地形圖（需 stadia_api_key）三種，
    圖磚與 Leaflet 庫來自網路，需網路連線。
    注意：只有存在 output/weathernext_各國颱風路徑.json（由 fetch_weathernext.py
    產生）時，WeatherNext 圖層才會出現；沒有該檔時網頁照常運作。
    ECMWF 圖層同理，只有存在 output/ecmwf_各國颱風路徑.json 時才會出現。

    可選參數（教材網頁用）：
    python plot_web.py --data-dir teaching/白海豚 --out 白海豚教材.html
    從指定目錄讀取 JSON（不是預設的 output/）產生教材頁，並將即時頁與教材頁
    互加連結。即時頁（各國颱風路徑.html）面板頂部有「📚 教材範例：白海豚」
    按鈕可切換至教材頁；教材頁有「↩ 回到即時更新網頁」返回。
    teaching/ 資料夾存放教材用的凍結資料（固定快照，fetch 更新不會動到它）。

4. 一鍵更新網頁 (One-click update for latest data)
    update_typhoon_web.bat
    依序執行 fetch（步驟 1）→ fetch_weathernext（步驟 1b）→ fetch_ecmwf
    （步驟 1c）→ 產生網頁（步驟 3），維持最新颱風資訊並附上 WeatherNext AI 與
    ECMWF 模式預報。ECMWF 步驟若失敗（如無相符颱風）只警告、不中斷。
    直接雙擊執行；由工作排程器定時執行時加參數 nopause：
        update_typhoon_web.bat nopause
    檔案以 CP950 (Big5) + CRLF 編碼，若以其他編碼重新儲存需還原。

Output
------
output/各國颱風路徑.json       - 最新一筆預報資料 (含 forecast_time_utc)
output/各國颱風路徑_all.json   - 所有歷史預報資料
output/weathernext_各國颱風路徑.json - WeatherNext AI 預報 (fetch_weathernext.py 產生)
output/ecmwf_各國颱風路徑.json     - ECMWF HRES/ENS 路徑 (fetch_ecmwf.py 產生)
output/各國颱風路徑.png        - 路徑圖
output/各國颱風路徑.html       - Leaflet 互動地圖 (plot_web.py 產生)
output/白海豚教材.html         - 教材網頁（白海豚 2026，固定快照，plot_web.py 以
                                --data-dir teaching/白海豚 產生）
teaching/白海豚/               - 教材用凍結資料（各國颱風路徑.json 與 _all.json）

Configuration (config.json)
---------------------------
{
  "output_path": "output",                    # 輸出目錄
  "cwa_api_key": "YOUR_KEY",                 # CWA 開放資料 API Key
  "agency_names_cn": {                       # 各機構圖例顯示名稱
    "CWA": "臺灣", "JTWC": "美國", "JMA": "日本",
    "HKO": "香港", "NMC": "中國", "KMA": "韓國",
    "PAGASA": "菲律賓"
  },
  "agency_colors": {                         # 各機構路徑顏色 (可自訂)
    "CWA": "#E0004D", "JTWC": "#00A2E8",
    "JMA": "#FF7F27", "HKO": "#22B573",
    "NMC": "#A349A4", "KMA": "#3F48CC",
    "PAGASA": "#880015"
  },
  "cwa_grade_thresholds": {                  # 臺灣颱風分級標準 (m/s)
    "熱帶低壓_max": 17.1,                     #   ≤ 17.1 熱帶低壓
    "輕度颱風_min": 17.2,                     # 17.2~32.6 輕颱
    "輕度颱風_max": 32.6,
    "中度颱風_min": 32.7,                     # 32.7~50.9 中颱
    "中度颱風_max": 50.9,
    "強烈颱風_min": 51.0                      #   ≥ 51.0 強颱
  },
  "basemap_style": "default",                # 底圖風格
  "show_taiwan_100km_buffer": false,         # 是否顯示臺灣 100km 海域線
  "taiwan_100km_line_color": "#FF6600",      # 海域線顏色 (Hex)
  "legend_fontsize": 11,                     # 圖例文字大小
  "legend_title_fontsize": 13,               # 圖例標題文字大小
  "annot_date_fontsize": 7,                  # 日期標註大小
  "annot_radius_fontsize": 6,                # 半徑標註大小
  "annot_wind_fontsize": 5                   # 風速標註大小
}

Features
--------

1. 多機構路徑繪製 (Multi-Agency Track Plotting)
   - 同時繪製 CWA、JTWC、JMA、HKO、NMC、KMA、PAGASA 等機構預報路徑
   - 每個機構以不同顏色/標記區分，顏色可在 config 中自訂
   - 多颱風時自動使用不同標記區分

2. CWA 暴風半徑圈 (CWA Storm Radius)
   七級暴風半徑 (Circle15ms, 15 m/s wind):
   - 從 CWA 開放資料 API 取得官方暴風半徑
   - API 無法取得時以風速估算
   - 半徑圈上標註距離與颱風強度等級 (輕/中/強颱)
   - 紅色實線半透明圈

   十級暴風半徑 (Circle25ms, 25 m/s wind):
   - 從 CWA API 的 Circle25ms 欄位取得
   - 無資料時不繪製（無估算值）
   - 橘色實線空心圈（無文字標註）

   四象限風圈 (QuadrantRadii, NE/SE/SW/NW):
   - CWA 分析資料 (AnalysisData.Fix) 的 Circle15ms/Circle25ms 內含四象限半徑
   - 僅「分析/歷史」位置有象限資料；預報 Fix (ForecastData.Fix) 只有單一半徑
   - 網頁版 (plot_web.py) 在「時間播放」時，移動標記的風圈會以四象限多邊形
     呈現 CWA 分析半徑（紅＝七級、橘＝十級），沿歷史軌跡隨動畫平滑變化；
     無象限資料的時段/時點回退為依風速估算的圓形風圈（紅＝七級、橘＝十級）
   - 靜態畫面不畫四象限風圈，只隨動畫播放出現

3. 歷史軌跡 (Historical Track)
   - 以灰色虛線繪製過去所有 forecast time 的實際位置
   - 起點標記 x，終點標記星號

4. 颱風接近參考線 (Approach Reference Lines)
   - 122°E、120°E 經線及 22°N 緯線 (灰色虛線)
   - 自動尋找最接近各參考線的暴風半徑邊緣，以橙色虛線圈標示

5. 臺灣 100km 海域線 (Taiwan 100km Maritime Buffer)
   - 從 Natural Earth 臺灣輪廓向外緩衝 100 公里
   - 自動扣除中國大陸重疊部分，僅保留海上區段
   - 需安裝 shapely 與 pyproj

6. 多颱風選擇 (Multi-Typhoon Selection)
   - 1 個颱風 → 直接繪製，不彈視窗
   - 2+ 個颱風 → 跳出視窗供選擇
   - 5.16 秒無操作自動全選

7. 歷史 Entry 選擇 (Historical Entry Selection)
   - python plot_typhoon.py N 可指定繪製第 N 筆歷史預報

8. 底圖風格 (Basemap Styles)
   "default"  - 預設 (米色陸地 + 淺藍海洋)
   "light"    - 淺色簡潔風格
   "dark"     - 深色模式
   "terrain"  - 地形色調

9. Leaflet 網頁地圖 (Web Map)
   - plot_web.py 產生單一自包含 HTML，資料直接內嵌於檔案中
   - 每顆颱風可切換歷史預報 entry（下拉選單，最新時間置頂）；歷史軌跡固定顯示
   - 側邊面板「底圖」單選鈕可切換底圖；圖層控制（桌面在右下、手機在右上，預設
     收合為小按鈕，點擊展開）開關各颱風圖層、歷史軌跡、100km 海域線與固定風圈標註
   - 右側功能面板：右上角「◀」可收合成小按鈕（再按「▶」展開）；面板縮窄至
     240px，內容過高時內部捲動，不會遮住右下角的圖層控制
   - 「時間播放」可動態播放颱風路徑：歷史 → 預報逐時推進（移動標記 + 路徑逐段
     浮現 + 移動標記隨風速變化的七級/十級暴風圈），含播放/暫停/重設、時間軸
     拖曳與 ◀ 1H / 1H ▶ 單步（每次進/退 1 小時）
   - 「固定風圈標註」：在時間軸選定某時間後按「📌 固定此時間風圈」，可把該時間
     點的七級/十級風圈（預報或 CWA 分析四象限）以實線留在圖上作為註記，列表可
     個別 ✕ 刪除或「清除全部標記」；固定風圈標註為獨立圖層，可在圖層控制開關
   - 「各國路徑」可逐一勾選開關各機構（CWA、JTWC、JMA、HKO 等）的路徑顯示
   - 臺灣 100km 海域線：與 PNG 相同，由 plot_typhoon.py 的計算邏輯（Natural
     Earth + shapely/pyproj）在產生 HTML 時算出並內嵌，圖層控制可開關；
     需 show_taiwan_100km_buffer: true（且本機裝有 shapely/pyproj 與
     Natural Earth 資料）
   - 暴風半徑：靜態檢視不畫風圈（避免遮住 CWA 路徑、擋住滑鼠選取），改在 CWA
     預報點的快顯視窗中顯示七級/十級半徑（點擊路徑點查看）；風圈只在時間播放
     （CWA 分析四象限）與「📌 固定此時間風圈」（紅色七級、橘色十級，帶白色外框，
     深色底圖下仍清晰可見）時出現；風圈頂端有等高線式的小型半徑標籤（如「180 km」，
     紅字七級／橙字十級）
   - 風速顯示為 m/s（JSON 內仍以 KT 儲存，1 KT ≈ 0.5144 m/s）
   - CWA 四象限風圈：播放時移動標記旁的多邊形即為 CWA 分析資料（AnalysisData.Fix）
     的 NE/SE/SW/NW 四象限七級/十級半徑，隨動畫沿歷史軌跡移動並平滑變形；
     靜態畫面不顯示（僅動畫出現）
   - 底圖：Google 地圖（預設）、Esri 衛星圖（免 key）與 Stamen 地形圖（需免費
     Stadia Maps API key，填入 config.json 的 stadia_api_key 才會出現）
   - 響應式版面：窄螢幕（手機）下面板自動改為底部抽屜（高度受限、可捲動），
     圖例移至左上角；圖例僅列出各國機構，其餘說明（風圈/軌跡/100km 線）收合在
     圖例的「?」按鈕，點選後展開
   - 網頁說明：面板標題旁的「❓」按鈕會開啟全螢幕說明視窗（資料來源、地圖操作、
     時間播放、固定風圈、暴風半徑等），點視窗外圍或按 Esc 關閉
    - 產品名稱：左上角縮放鍵上方顯示「多采颱跡店」品牌標題（漸層字色 + 🌀 徽章，
      英文副標 ManySplendid Typhoon Track Shop），與縮放鍵、圖例垂直堆疊不
      重疊；窄螢幕自動縮小並隱藏副標
    - 地圖圖磚與 Leaflet 庫需網路連線才能載入

10. WeatherNext AI 預報 (Google WeatherNext 2 via Open-Meteo)
    - 資料來源：Open-Meteo 免費 API（免金鑰、免 Google 帳號），
      endpoint https://ensemble-api.open-meteo.com/v1/ensemble，
      model=google_weathernext2_ensemble_mean（Open-Meteo 計算的 64 成員平均）。
      對照：Google 官方管道（GCP/BigQuery/Earth Engine）需申請 API key，
      本專案不走該管道。
    - 產生方式：python fetch_weathernext.py 讀取 output/各國颱風路徑.json，
      沿每顆颱風的 CWA 預報軌跡各點（tau=0/24/48/...），抓該座標的 10m/100m 風速
      (kn)、海平面氣壓 (hPa)、氣溫 (°C)，以 6 小時原生解析度取最接近 tau 的時刻，
      寫出 output/weathernext_各國颱風路徑.json。
    - 網頁呈現：plot_web.py 將該 JSON 以 "weathernext" 鍵內嵌進 HTML；每顆颱風
      新增「XXX WeatherNext」圖層（青綠色虛線軌跡，圖層控制可開關），圓點點開有
      tooltip（+τH 風速）與 popup（時間/位置/風速/氣壓/氣溫）。圖例與「❓」說明
      也有相應項目。
    - 執行順序：fetch_typhoon2000.py → fetch_weathernext.py → plot_web.py；
      update_typhoon_web.bat 已依序執行三者。
    - 若無 WeatherNext JSON 檔，網頁不會出現該圖層，其餘功能不受影響。

11. ECMWF 模式預報 (ECMWF Open Data HRES/ENS TC tracks)
    - 資料來源：ECMWF Open Data（https://apps.ecmwf.int/datasets/data/open-data/，
      免費、免金鑰、CC-BY-4.0，需註明出處）。檔案為 BUFR edition 4 的熱帶氣旋
      路徑產品：HRES 走 stream=oper、ENS 走 stream=enfo，type=tf；
      download.ecmwf.int（data.ecmwf.int）路徑如下
      forecasts/<yyyyMMdd>/<HH>z/ifs/0p25/<oper|enfo>/<日期>-<時>-<step>h-<oper|enfo>-tf.bufr。
      00/12z run → step=360，06/18z run → step=144；釋出時間約為 run 後 6~7 小時
      （00z 06:55、06z 12:12、12z 18:55、18z 次日 00:12），程式自動挑已釋出的
      最新一筆，404 時退回前一 run。
    - 解碼方式：用 eccodes（pdbufr 0.14 讀此檔案回傳 0 行，不能用）。每顆颱風
      一個 BUFR message（dataCategory=7，local section 含 longStormName /
      stormIdentifier，如 NANGKA→20W；ENS 檔有 51 個 subset = 51 個成員）。
      不能直接 codes_get_array('latitude')（會混入「觀測中心」「分析中心」
      「最大風速位置」三組），要用 ranked-key：`#n#timePeriod` 為第 n 步（小時），
      中心位置 lat/lon 在 rank `#2n#`、最大風速位置在 rank `#(2n+1)#`、
      中心氣壓 `#n#pressureReducedToMeanSeaLevel`、最大風速 `#n#windSpeedAt10M`。
      逐步遞增 rank 依序解出每步的座標/氣壓/風速（中心氣壓為 hPa、風速為 m/s）。
    - ENS 平均：依 step 對各成員座標/氣壓/風速取平均（過濾 ECMWF 的 MISSING 哨兵值），
      另保留 member 51 的 ENS control 軌跡。
    - 網頁呈現：plot_web.py 將該 JSON 以 "ecmwf" 鍵內嵌進 HTML；每顆颱風新增
      「XXX ECMWF」圖層（深靛 HRES 實線、淺靛 ENS mean 虛線，圖層控制可開關），
      圓點點開有 tooltip（+τH 風速）與 popup（預報時間/位置/最大風速/中心氣壓）。
      圖例（顯示 run）與「❓」說明也有相應項目。
    - 執行順序：fetch_typhoon2000.py → fetch_weathernext.py → fetch_ecmwf.py
      → plot_web.py；update_typhoon_web.bat 已依序執行四者（ECMWF 失敗不中斷）。
    - 若無 ECMWF JSON 檔，網頁不會出現該圖層，其餘功能不受影響。

Notes
-----
- CWA 暴風半徑資料來自中央氣象署開放資料平臺 (須網路連線)。
- 如果 CWA API 無法取得 7 級半徑，會根據風速推算半徑；10 級半徑無資料時不繪製。
- ECMWF 資料為 CC-BY-4.0，使用時請註明出處：ECMWF Open Data（免費）。
- ECMWF 檔偶有「重複」的 stormIdentifier（如 71W 與 20W 軌跡相同），fetch_ecmwf.py
  以颱風名（longStormName）比對，不受影響。
- 各預報點的颱風強度分級（輕/中/強颱）透過 ForecastHour 匹配 CWA API 預報風速，
  而非使用當前風速，因此後期預報若減弱會正確顯示。
- 各國路徑顏色可在 config.json 的 agency_colors 中自訂 (Hex 色碼)。
- 100km 海域線需要 cartopy 內含的 Natural Earth 臺灣輪廓資料，
  以及 shapely、pyproj 程式庫 (與 cartopy 一同安裝)。
- 颱風分級標準 (熱帶低壓/輕颱/中颱/強颱) 定義在 config.json 的
  cwa_grade_thresholds，可依需求調整而不需修改程式碼。
