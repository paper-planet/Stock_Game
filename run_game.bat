@echo off
setlocal
title STOCK GAME PRO - START
echo ==========================================
echo STOCK GAME PRO - START
echo ==========================================
echo.
python --version
if errorlevel 1 (
    echo Python command not found.
    pause
    exit /b 1
)
echo.
echo Starting game...
python main.py
set ERR=%ERRORLEVEL%
echo.
echo Game exited with code %ERR%.
if exist startup_error.log (
    echo.
    echo startup_error.log was created:
    type startup_error.log
)
pause
