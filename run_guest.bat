@echo off
setlocal
cd /d "%~dp0"
python --version
if errorlevel 1 (echo Python not available.&pause&exit /b 1)
python main.py --guest
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" if exist startup_error.log type startup_error.log
pause
exit /b %ERR%
