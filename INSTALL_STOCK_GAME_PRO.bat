@echo off
setlocal
cd /d "%~dp0"
title Stock Game Pro Installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1"
if errorlevel 1 (
  echo.
  echo Installation did not complete successfully.
  pause
)
endlocal
