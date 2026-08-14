Stock Game Pro 1.8 Production

UI / layout polish
- Removed redundant BUY / SELL / LIMIT / STOP buttons from the top workstation toolbar.
- Removed the duplicate top PAUSE / NEXT OPEN controls; the bottom world-time controls remain.
- Removed the duplicate Order Entry launcher beneath Portfolio / Account.
- Added an independent Candle period control beside Timeframe on the main workstation and Advanced Charting.
- Candle periods: Auto, 1 Tick, 30 Sec, 1 Min, 3 Min, 5 Min, 10 Min, 30 Min, 1 Hour, 1 Day.

Chart engine
- Added simulator tick and 30-second live candle streams.
- Added 3m / 10m / 30m aggregation without changing the global chart tick rate.
- Candle period belongs to the selected chart, independently from the displayed history timeframe.

Casino polish
- Blackjack dealer hand is centered.
- Player hand totals render beneath the cards so 4+ card hands do not overlap their value labels.
- Roulette denomination rack is visually separated farther below the wheel.
- Horse Racing track and controls are centered with a dedicated label area so moving horses never cross text.

Validation
- Python compile validation passed for ui.py, market.py, game_core.py, main.py and data.py.
- Headless Tk smoke test passed for the 8-chart workspace, redundant-toolbar removal, tick/30-second candles, two-hand 4-deck Blackjack, Roulette and Horse Racing with zero recorded market errors.
