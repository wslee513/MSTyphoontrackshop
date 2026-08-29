@echo off
cd /d "%~dp0"

rem --- logging to update.log so scheduled runs are diagnosable ---
set "LOG=%~dp0update.log"
echo [%date% %time%] Scheduled update started... > "%LOG%"

rem --- resolve python (Task Scheduler may use a different PATH) ---
set "PY=python"
where python >nul 2>&1
if errorlevel 1 (
  if exist "C:\Python313\python.exe" ( set "PY=C:\Python313\python.exe" )
  if not exist "C:\Python313\python.exe" (
    echo [ERROR] python not found on PATH and C:\Python313\python.exe missing >> "%LOG%"
    exit /b 1
  )
)
echo [%date% %time%] Using python: %PY% >> "%LOG%"

set "MAXTRY=3"

echo [1/5] Fetch typhoon data... >> "%LOG%"
set /a TRY=0
:fetch1
set /a TRY+=1
echo [%date% %time%] fetch_typhoon2000.py attempt %TRY%... >> "%LOG%"
%PY% fetch_typhoon2000.py >> "%LOG%" 2>&1
if not errorlevel 1 goto fetch1ok
if %TRY% lss %MAXTRY% (
  echo [WARN] fetch_typhoon2000.py attempt %TRY% failed, retrying... >> "%LOG%"
  goto fetch1
)
echo [ERROR] fetch_typhoon2000.py failed after %MAXTRY% attempts. >> "%LOG%"
exit /b 1
:fetch1ok

echo [2/5] Fetch WeatherNext... >> "%LOG%"
set /a TRY=0
:fetch2
set /a TRY+=1
echo [%date% %time%] fetch_weathernext.py attempt %TRY%... >> "%LOG%"
%PY% fetch_weathernext.py >> "%LOG%" 2>&1
if not errorlevel 1 goto fetch2ok
if %TRY% lss %MAXTRY% (
  echo [WARN] fetch_weathernext.py attempt %TRY% failed, retrying... >> "%LOG%"
  goto fetch2
)
echo [ERROR] fetch_weathernext.py failed after %MAXTRY% attempts. >> "%LOG%"
exit /b 1
:fetch2ok

echo [3/5] Fetch ECMWF... >> "%LOG%"
%PY% fetch_ecmwf.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [WARN] ECMWF fetch failed, continuing... >> "%LOG%"
)

echo [4/5] Generate web page... >> "%LOG%"
%PY% plot_web.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] plot_web.py failed. >> "%LOG%"
  exit /b 1
)

echo [5/5] Deploy to GitHub... >> "%LOG%"
git add -A >> "%LOG%" 2>&1
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set commit_msg=Auto update %datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2% %datetime:~8,2%:%datetime:~10,2%
git commit -m "%commit_msg%" >> "%LOG%" 2>&1
git push origin main >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo [%date% %time%] Done. >> "%LOG%"
