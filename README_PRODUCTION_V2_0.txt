STOCK GAME PRO 2.1 — CHART FOLLOW / PERFORMANCE / AUTOSAVE OVERHAUL

Major changes
- Replaced the layered chart renderer with one optimized renderer. Live charts always center on the authoritative ticker price and force the right-most candle close to the live quote.
- Historical/free-scroll charts remain detached from live-follow behavior by design.
- Chart render cache now depends only on state relevant to that chart rather than the entire portfolio.
- Engine clock remains smooth at ~40 Hz, while the ~196-asset universe is repriced in rotating batches. Each asset still receives a smooth quote stream without thousands of updates per engine pass.
- High-frequency tick/30-second/intraday bar histories are bounded. This prevents millions of Candle objects from accumulating during long sessions.
- Index, freight, geopolitics, orders, earnings and corporate-action work is cadence-throttled instead of running at full engine frequency.
- Saved accounts now persist the full trading state: cash, stock positions, cost basis, option strategies, working stock/option/spread orders, realized P/L, margin, market clock and macro state.
- Automatic progress save runs at the end of each US trading day, on NEXT DAY +24H, and on clean exit.
- Main watchlist streaming is throttled to reduce Tk event-loop contention while remaining visually live.

Installation
- INSTALL_STOCK_GAME_PRO.bat remains the one-click helper.
- BUILD_WINDOWS_INSTALLER.bat builds a conventional Stock_Game_Pro_2.1_Setup.exe when Inno Setup is installed.
