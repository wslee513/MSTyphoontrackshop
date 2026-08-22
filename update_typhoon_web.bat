@echo off
rem 颱風路徑更新腳本：先抓取最新資料，再重新產生網頁。
rem 用法：直接雙擊執行；由工作排程器執行時可加參數 nopause（結束不等待按鍵）。
setlocal
cd /d "%~dp0"

echo [%date% %time%] 開始更新颱風路徑網頁...
echo ========================================

where python >nul 2>nul
if errorlevel 1 (
  echo [錯誤] 找不到 python，請先安裝 Python 並加入 PATH。
  pause
  exit /b 1
)

echo [1/4] 取得最新颱風資料 ^(fetch_typhoon2000.py^)...
python fetch_typhoon2000.py
if errorlevel 1 (
  echo [錯誤] fetch 失敗，中止更新。
  echo 可於 config.json 加入 "typhoon_name" 手動指定颱風名稱後重試。
  pause
  exit /b 1
)

echo.

echo [2/4] 更新 WeatherNext AI 預報 (fetch_weathernext.py)...
python fetch_weathernext.py
if errorlevel 1 (
  echo [錯誤] WeatherNext 更新失敗。
  pause
  exit /b 1
)

echo [3/4] 更新 ECMWF 模式預報 (fetch_ecmwf.py)...
python fetch_ecmwf.py
if errorlevel 1 (
  echo [警告] ECMWF 更新失敗或無相符颱風，繼續產生網頁。
)

echo.

echo [4/4] 重新產生網頁 ^(plot_web.py^)...
python plot_web.py
if errorlevel 1 (
  echo [錯誤] 產生網頁失敗。
  pause
  exit /b 1
)

echo ========================================
echo [完成] 網頁已更新：output\各國颱風路徑.html
echo 完成時間：%date% %time%
echo.
if /i not "%~1"=="nopause" pause
