# STOCK_GAME PRO v1.0

A dependency-light Python/Tkinter global trading simulator designed as an educational Bloomberg/Thinkorswim-style training game.

## Features
- 8-chart default workspace: SPY, VIX, NVDA, AAPL, crude oil, gold, GME, random US equity
- Immediate chart fallback plus best-effort real historical data bridge
- 1D 5-minute charts through MAX history
- Candles/line/area, SMA/EMA/Bollinger/VWAP/RSI/volume, crosshair and drawing tools
- Click-to-load and right-click trading menus
- Market/limit/stop orders with draggable working orders on charts
- Equities, shorting, futures, commodities, crypto, FX and international sessions
- Options, 0DTE indexes, whole-dollar strikes, live chain, ITM/ATM highlighting
- Option limit/stop orders and custom multi-leg spread builder with preview Greeks
- Level 2/Level 3 simulated depth and market microstructure
- Square market-cap sector map
- Global rotating session globe and market-specific trading windows
- Filterable news tape
- Explainable momentum/volatility educational model
- Smart large-lot execution simulator
- Blackjack 1/2/6-deck counting trainer and roulette arcade
- GitHub Actions builds for Windows, macOS and Linux

## Run from source
Windows: `run_windows.bat`
macOS/Linux: `./run_unix.sh`

## Build a native application
Windows: `build_windows.bat`
macOS/Linux: `./build_unix.sh`

GitHub Actions builds OS-specific PyInstaller artifacts automatically. There is no single native executable that can run unchanged on every operating system; each OS receives its own artifact.

Market data is best-effort and the game remains playable offline. Predictive signals are educational simulation mechanics, not financial advice.
