STOCK GAME PRO 2.2 — PROFESSIONAL WORKSTATION OVERHAUL

Highlights
- Global Trader is now a 2D world map with exchange blips, real port coordinates, directional ocean freight routes, air-freight routes, ships, aircraft and risk markers. Camera pan/zoom never advances game time.
- Startup workspace is one SPY chart, 1M / 5-minute candles, with a calmer 100 ms chart refresh.
- New time-warp convention: 1x is the minimum and equals the previous 0.25x engine rate; 10x is the maximum.
- NEXT OPEN refuses to run while the selected asset is already in its regular session. NEXT DAY +24H is removed.
- Per-chart tick-rate dropdown is placed immediately left of timeframe. FIT MAX shows full available history from inception.
- Chart price following now uses hysteresis: center initially, then move only when price approaches the viewport edge. This reduces vertical shimmer.
- Overnight-session shading is on by default. RSI and MACD render in dedicated subpanels.
- Advanced free-screen mode supports horizontal time panning and vertical price panning by click-drag.
- Advanced charts expose indicator toggles and inception fit.
- Market Conditions Research Lab has staged/non-destructive sliders, wider ranges, descriptions, macro controls and scenario variables. Closing without Apply discards changes.
- Market prediction is now multi-factor (multi-horizon momentum, RSI, macro regime, market momentum and newest loaded real quote/history).
- Market Map now includes sector breadth, heat tiles and index constituent-impact decomposition.
- SPX uses a broad US component basket and SPY is explicitly modeled as a tightly tracking ETF.
- Professional Options Strategy Builder adds target-day P/L curves and IV-shift scenarios on top of the manual multi-leg chain/payoff workflow.
- Expanded universe to roughly 250 assets across US/global sectors. Background real-quote/MAX-history loading starts immediately after login.
- Windows installer/build helpers retained and updated to 2.2.

Research note
This remains an educational simulator. Real quote/history adapters seed the simulation when network data is available, but the forward path is simulated and is not a scientifically validated forecast of future prices.
