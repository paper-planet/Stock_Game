@echo off
setlocal
title STOCK GAME PRO - DEBUG BUILD
echo Building console/debug executable...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist StockGamePro.spec del /q StockGamePro.spec
python -m PyInstaller --noconfirm --clean --onefile --console --name StockGamePro_Debug main.py
if errorlevel 1 (
    echo BUILD FAILED
    pause
    exit /b 1
)
echo.
echo DEBUG EXE:
echo   dist\StockGamePro_Debug.exe
pause
