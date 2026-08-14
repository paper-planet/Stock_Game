@echo off
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --windowed --name STOCK_GAME_PRO main.py
