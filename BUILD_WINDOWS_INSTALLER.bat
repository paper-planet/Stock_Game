@echo off
setlocal
cd /d "%~dp0"
call BUILD_STANDALONE_EXE.bat
if errorlevel 1 exit /b 1
set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (
  echo.
  echo Inno Setup 6 was not found.
  echo Install Inno Setup, then run BUILD_WINDOWS_INSTALLER.bat again.
  start "" "https://jrsoftware.org/isdl.php"
  pause
  exit /b 1
)
"%ISCC%" "%~dp0installer\StockGamePro.iss"
if errorlevel 1 exit /b 1
echo.
echo Installer created in: %CD%\dist-installer
pause
