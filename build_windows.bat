@echo off
setlocal
cd /d "%~dp0"
echo ==========================================
echo STOCK GAME PRO - WINDOWS BUILD
echo ==========================================
echo.

set "PYTHON="
python --version >nul 2>&1
if not errorlevel 1 set "PYTHON=python"
if not defined PYTHON (
    python3 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON=python3"
)
if not defined PYTHON (
    echo ERROR: Python is installed but the command could not be launched.
    echo Please run: python --version
    pause
    exit /b 1
)

echo Using: %PYTHON%
%PYTHON% --version
echo.

echo Installing/updating PyInstaller...
%PYTHON% -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo PIP/PyInstaller installation failed.
    pause
    exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo Building executable...
%PYTHON% -m PyInstaller --noconfirm --clean --onedir --windowed --name StockGamePro main.py
if errorlevel 1 (
    echo.
    echo BUILD FAILED
    echo Try run_game.bat first. If that works, send me startup_error.log.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo BUILD COMPLETE
echo ==========================================
echo EXE: %~dp0dist\StockGamePro\StockGamePro.exe
echo.
pause
