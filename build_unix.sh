#!/usr/bin/env bash
set -e
python3 -m pip install -r requirements-build.txt
python3 -m PyInstaller --noconfirm --clean --windowed --name STOCK_GAME_PRO main.py
