StockGame Pro startup/build fix

1. Use run_game.bat to run from source.
2. Use build_windows.bat to create dist\\StockGamePro.exe.
3. The release EXE is built with PyInstaller --onefile, so it does not depend
   on an external _internal\\python311.dll folder.
4. Do not use older build/dist executables from previous packages.
5. If the GUI EXE fails, build_debug.bat creates a console EXE that displays
   the actual traceback.
6. This package uses the working 'python' command and does not use 'py' or
   'where'.
