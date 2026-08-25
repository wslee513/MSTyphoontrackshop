@echo off
cd /d "%~dp0"

rem --- ecCodes (ECMWF GRIB) support: point findlibs at the local eccodes build ---
set "ECCODES_PYTHON_USE_FINDLIBS=1"
set "ECCODESLIB_DIR=C:\eccodes"
set "PATH=%PATH%;C:\eccodes\lib"

echo [%date% %time%] Scheduled update started...

echo [1/5] Fetch typhoon data...
python fetch_typhoon2000.py
if errorlevel 1 (
    echo [ERROR] fetch_typhoon2000.py failed.
    exit /b 1
)

echo [2/5] Fetch WeatherNext...
python fetch_weathernext.py
if errorlevel 1 (
    echo [ERROR] fetch_weathernext.py failed.
    exit /b 1
)

echo [3/5] Fetch ECMWF...
python fetch_ecmwf.py
if errorlevel 1 (
    echo [WARN] ECMWF fetch failed, continuing...
)

echo [4/5] Generate web page...
python plot_web.py
if errorlevel 1 (
    echo [ERROR] plot_web.py failed.
    exit /b 1
)

echo [5/5] Deploy to GitHub...
git add -A
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set commit_msg=Auto update %datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2% %datetime:~8,2%:%datetime:~10,2%
git commit -m "%commit_msg%"
git push origin main

echo.
echo [%date% %time%] Done.
