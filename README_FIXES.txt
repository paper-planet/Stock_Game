STOCK_GAME PRO - repaired source package

Main fixes:
1. Added a complete market.py engine with a clock that advances independently of Tkinter.
2. The simulation loop now catches tick exceptions instead of silently killing the daemon thread.
3. Fixed the module-name mismatch: data.py imported `assets` while the supplied source file was `asset.py`. A compatibility assets.py is included too.
4. Portfolio now initializes trade_count and best_net_worth, which the UI expects.
5. Background market-data workers are daemon threads and are best-effort; network/Yahoo failures cannot stop the game.
6. Added a Windows run_game.bat and a clean PyInstaller build_windows.bat.

Run from source:
- Double-click run_game.bat, or run: py -3 main.py
- For a no-login test: py -3 main.py --guest

Build Windows executable:
- Run build_windows.bat on Windows with Python 3 installed.
- The executable will be in dist\StockGamePro\StockGamePro.exe

This package is intentionally source-first because an executable built on Linux is not a usable Windows .exe.

IMPORTANT: On this PC the Windows 'where' command is unavailable, so the batch files no longer use it. The diagnostic compile test uses Python glob instead of the Windows shell wildcard.

If normal startup fails, run run_guest.bat. It bypasses account/menu code and is useful for isolating GUI/engine problems.
