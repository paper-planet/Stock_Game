STOCK GAME PRO 2.5 - WINDOWS INSTALLATION
==========================================

FOR NORMAL PLAYERS
------------------
1. Extract this ZIP to a normal folder.
2. Double-click INSTALL_STOCK_GAME_PRO.bat.
3. Leave Desktop / Start Menu shortcuts checked if desired.
4. Click INSTALL STOCK GAME PRO.
5. The installer launches the game automatically when finished.

The helper installs Stock Game Pro into your Windows user profile, creates a
private Python environment, installs requirements.txt, and creates shortcuts.
If Python is missing, it can install Python 3.12 automatically with winget.
No administrator privileges are normally required.

UNINSTALL
---------
Double-click UNINSTALL_STOCK_GAME_PRO.bat from the extracted package, or use
"Uninstall Stock Game Pro" from the Start Menu if that shortcut was selected.

FOR DISTRIBUTION AS A NORMAL SETUP.EXE
--------------------------------------
The repository also contains:

  BUILD_STANDALONE_EXE.bat
  BUILD_WINDOWS_INSTALLER.bat
  installer\StockGamePro.iss

On a Windows development machine:
1. Install Python 3.
2. Install Inno Setup 6.
3. Double-click BUILD_WINDOWS_INSTALLER.bat.

The script builds a standalone StockGamePro.exe with PyInstaller and then
creates a conventional Stock_Game_Pro_2.5_Setup.exe with Inno Setup. Players
using that Setup.exe do NOT need Python installed separately.

The Inno installer includes a Start Menu shortcut, optional Desktop shortcut,
uninstaller, and a checked-by-default "Launch Stock Game Pro" finish option.

SOURCE FILES
------------
main.py
ui.py
market.py
game_core.py
data.py
requirements.txt
