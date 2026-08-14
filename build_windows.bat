@echo off
setlocal
title STOCK GAME PRO - WINDOWS BUILD
echo ==========================================
echo STOCK GAME PRO - WINDOWS BUILD
echo ==========================================
echo.
python --version
if errorlevel 1 (
    echo ERROR: Python command is not available.
    echo.
    pause
    exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist StockGamePro.spec del /q StockGamePro.spec

echo.
echo Checking PyInstaller...
python -m PyInstaller --version
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    python -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo ERROR: Could not install PyInstaller.
        pause
        exit /b 1
    )
)

echo.
echo Building ONE-FILE executable...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name StockGamePro main.py
if errorlevel 1 (
    echo.
    echo BUILD FAILED
    pause
    exit /b 1
)

echo.
echo ==========================================
echo BUILD COMPLETE
echo ==========================================
echo.
echo Your executable is:
echo   dist\StockGamePro.exe
echo.
pause
