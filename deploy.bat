@echo off
cd /d "%~dp0"

git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] git not found. Install: https://git-scm.com/download/win
    pause
    exit /b 1
)

git remote -v | findstr "origin" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] git remote not set. Run:
    echo   git init
    echo   git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
    pause
    exit /b 1
)

echo [1/3] git add -A
git add -A

echo [2/3] git commit
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set commit_msg=Update %datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2% %datetime:~8,2%:%datetime:~10,2%
git commit -m "%commit_msg%"

echo [3/3] git push
git push origin main
if errorlevel 1 (
    echo Trying master branch...
    git push origin master
)

echo.
echo Done. GitHub Pages updates in 1-2 min.
if /i not "%~1"=="nopause" pause
