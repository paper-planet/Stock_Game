Stock Game Pro 2.5 — Chart Stability / Index Universe / Performance Overhaul

KEY FIXES
- Rigid live-chart camera: the vertical scale no longer expands/contracts on every pump/dump wick. The viewport remains fixed while price stays inside it, translates only after price actually leaves the visible range, and expands only if a single candle physically cannot fit.
- Fixed synthetic-history/live-price welding. A current live candle is appended instead of forcing the current quote into a stale historical candle, eliminating artificial mega-wicks on intraday views.
- Startup is SPY 1D / 5 Min with a dense full-session view instead of a 1M synthetic chart that paints ~1,400 candles immediately.
- Chart scheduler renders at most one due canvas per 16 ms pulse and main charts default to a calmer ~160 ms redraw interval.
- Synthetic intraday expansion is cached; duplicate per-frame session shading/data rebuild passes were removed.
- 1-Tick zero-volume prints preserve the last visible non-zero display volume so volume bars do not blink out for one frame.
- DAY/AH metrics are moved away from the open/close countdown row.
- Market clock is compact/adaptive and receives right-edge toolbar priority so resizing the portfolio pane does not push it off-screen.

INDEX / ASSET UNIVERSE
- S&P 500: all 503 listed securities representing the 500 constituent companies.
- Nasdaq-100: 101 listed securities in the bundled current snapshot.
- Dow Jones Industrial Average: all 30 constituents.
- Russell 2000: broad IWM holdings proxy bundled for practical small-cap constituent coverage (1,960 equity rows in the captured holdings file; ETF holdings can differ from the licensed official Russell membership).
- FTSE 100: all 100 constituents in the bundled snapshot.
- DAX: all 40 constituents in the bundled snapshot.
- Hang Seng: all 88 constituents in the bundled snapshot.
- Existing representative baskets remain for other global indexes not covered by these bundled constituent snapshots.

PERFORMANCE ARCHITECTURE
- Roughly 2,800 total tradable/index/FX/commodity/futures/crypto assets can coexist without updating every asset every engine pulse.
- Allocation-free short-horizon momentum path avoids converting long price histories to Python lists on each quote.
- Broad symbols advance in a rotating batch; active chart/position/order symbols get a higher-frequency hot path.
- Index calculations use incremental constituent-return caches rather than rescanning every underlying at each refresh.
- Market watchlist streaming updates only visible rows plus a small buffer instead of rewriting thousands of hidden Treeview rows.
- Creation-time quote/history hydration is batched and bounded; established-account gameplay remains cache-only unless the player explicitly requests a snapshot refresh.
- Large-position safeguards from 2.2.1 remain in place.

SESSION / CLOCK
- 1x = one simulated second per real second.
- Time warp range remains 1x–100x.
- Opening-bell CHG% baseline reset remains enabled per exchange session.
- Extended/night highlighting remains enabled by default.

TESTS RUN
- Python compilation for all bundled source modules.
- Headless Tk workstation smoke test with SPY startup chart.
- Rigid-axis test: price movement inside the viewport did not change bounds; an actual edge crossing translated the viewport while preserving span.
- 1-Tick zero-volume display test retained the prior visible volume instead of disappearing.
- Opening-bell SPY change reset test returned exactly 0.0% at the session transition.
- Large-position UI/mark-value test with a 10^15-share synthetic position completed without overflow/crash.
- Five-second headless UI + market-engine run over ~2,800 assets completed without engine errors; observed process CPU was low single digits in that test environment (actual Windows hardware/UI load will vary).
- Verified ordinary gameplay fetch APIs remain network-silent, the explicit refresh writes an account-specific snapshot, repricing preserves share quantity/cost basis, and the Experimental menu item stays disabled for guests and enables for saved accounts.

INSTALLATION
Use INSTALL_STOCK_GAME_PRO.bat for the helper installer, or BUILD_WINDOWS_INSTALLER.bat to build the standalone Windows distribution.

PRODUCTION OFFLINE-DATA POLICY
------------------------------
- Version remains 2.5.
- A new account performs one visible market snapshot attempt before gameplay starts.
- Normal gameplay is cache-only/offline: charts, options, watchlists, global views, FIT MAX,
  simulation ticks, and background loaders do not poll the internet.
- Experimental -> Refresh Market Snapshot… is the sole gameplay-time exception. It requires an
  explicit warning/confirmation, pauses the simulation, performs a bounded snapshot request,
  applies the new marks, saves the account, and immediately returns to offline mode.
- If the network is unavailable, account creation and manual refresh both fall back to the
  newest local quote/history cache.
- Refreshing an established account never changes quantities or cost basis, but it can change
  marked P/L, option values, margin, and whether working limit/stop orders become executable.

