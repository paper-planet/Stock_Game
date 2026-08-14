@echo off
setlocal
cd /d "%~dp0"
echo STOCK GAME PRO - DIAGNOSTIC
echo.
echo Checking Python...
python --version
if errorlevel 1 goto :no_python

echo.
echo Checking tkinter...
python -c "import tkinter; print('Tkinter OK')"
if errorlevel 1 goto :bad_tk

echo.
echo Checking source files...
python compile_check.py
if errorlevel 1 (echo Source compile check FAILED.) else (echo Source compile check PASSED.)

echo.
echo Checking game imports and market engine...
python -c "import market; m=market.Market(); print('Market engine OK -',len(m.all_assets()),'assets'); print('Clock:',m.clock.time)"
if errorlevel 1 echo Market engine check FAILED.

echo.
echo Starting game in diagnostic mode...
python main.py
set "ERR=%ERRORLEVEL%"
echo.
echo Exit code: %ERR%
if exist startup_error.log (
 echo.
 echo ===== startup_error.log =====
 type startup_error.log
)
pause
exit /b %ERR%
:no_python
echo Python command could not be started.
pause
exit /b 1
:bad_tk
echo Tkinter is not available.
pause
exit /b 1
