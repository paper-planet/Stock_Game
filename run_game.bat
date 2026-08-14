@echo off
setlocal
cd /d "%~dp0"
echo ==========================================
echo STOCK GAME PRO - START
echo ==========================================
echo.
python --version
if errorlevel 1 (
 echo ERROR: The "python" command could not be started.
 echo Run: python --version
 pause
 exit /b 1
)
echo.
echo Starting game...
python main.py
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
 echo ==========================================
 echo GAME FAILED - ERROR CODE %ERR%
 echo ==========================================
 if exist startup_error.log type startup_error.log
 pause
 exit /b %ERR%
)
echo Game closed normally.
pause
