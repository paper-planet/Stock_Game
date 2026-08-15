@echo off
setlocal
cd /d "%~dp0"
title Build Stock Game Pro EXE
where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)
%PY% -m pip install --upgrade pyinstaller
if errorlevel 1 goto :fail
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name "StockGamePro" main.py
if errorlevel 1 goto :fail
echo.
echo Built: %CD%\dist\StockGamePro.exe
pause
exit /b 0
:fail
echo.
echo Build failed. Make sure Python 3 is installed.
pause
exit /b 1
