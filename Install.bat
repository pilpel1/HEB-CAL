@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" (
  echo HEB-CAL install failed. Error %ERR%.
  pause
  exit /b %ERR%
)
echo Open http://127.0.0.1:5000 on this computer.
pause
exit /b 0
