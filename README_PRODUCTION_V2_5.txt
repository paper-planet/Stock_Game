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


PRODUCTION POLISH — LIVE TABLES / TRADE HISTORY / CHART PERSISTENCE
-------------------------------------------------------------------
• Market-watch visible rows now stream price and CHG% at ~180 ms without repainting the full multi-thousand-asset Treeview.
• The personal portfolio table has an independent fast mark stream: ~120 ms for ordinary portfolios, progressively throttled for very large portfolios to preserve whale-account stability.
• Account → Trade History opens a live fill ledger for stocks and options. Actual partial-fill quantities/VWAPs are logged and the most recent 5,000 fills persist with the account.
• Crypto receives a true UTC-midnight daily rollover, resetting its daily open/CHG% to 0.00% even though the asset class trades 24/7.
• Fixed the daily candle bucket: 1-day bars now bucket at midnight instead of accidentally retaining the current hour.
• Sparse intraday timeframes use immutable historical backfill plus persistent native simulator bars. Completed real simulator candles are never replaced by regenerated display bars when a new interval starts.
• Long offline 6M/1Y/5Y views receive deterministic display history when only a short local daily cache exists; richer cached real history automatically takes precedence.
• Long/tiny-interval combinations use OHLC-preserving level-of-detail aggregation instead of collapsing to only a handful of candles or creating tens of thousands of Canvas items.
• All gameplay market data remains offline except account creation and the explicitly confirmed Experimental → Refresh Market Snapshot action.

=== FINAL SYSTEM POLISH / STABILITY CONSOLIDATION ===

This production refresh keeps the public version at 2.5 and consolidates the most recent
workstation, chart, portfolio, global-research, career and casino fixes.

Portal / accounts
- The account portal now uses the same bundled real-coastline world geometry as Global Viewer.
- Saved-account columns resize with the window and expand the CASH column for very large balances.
- Saved accounts receive a 60-second safety checkpoint in addition to end-of-day and clean-exit saves.
  A hard OS/process failure can still interrupt the current checkpoint; this is damage reduction,
  not a guarantee that software can write after a process has already crashed.

Charts / account analytics
- Intraday display backfill can no longer create future candles. Synthetic fallback bars are immutable,
  completed-session history only; genuine simulator bars always take precedence.
- US fallback intraday history uses the completed regular session rather than inventing overnight bars.
  Real simulator premarket/after-hours prints remain visible and session shading remains available.
- 1D 30-second/1/3/5/10/30-minute and Auto views no longer generate a fake wave to the right of the live bar.
- FIT Y now fits the visible OHLC range with padding. Manual vertical scaling spans 0.05x through 50x.
- Portfolio performance attribution includes stocks, global securities, crypto and option strategies.
- Account model statistics aggregate the held portfolio instead of describing a single selected symbol.

Universe / research
- Crypto expanded to 15 modeled coins; physical/micro futures and international equities expanded.
- Complete bundled constituent sets remain available for the S&P 500 listed securities, Nasdaq-100,
  Dow 30, FTSE 100, DAX 40 and Hang Seng snapshots, with a broad Russell/IWM proxy universe.
- Additional European, Japanese, Korean, Indian, Australian, Canadian, Brazilian, Singaporean and
  South African securities expand representative coverage of the other global indexes.
- Market Map now browses the whole local universe in optimized pages with filters, sector breadth,
  index-impact decomposition, right-click trading and advanced-chart access.

Global Viewer
- Uses bundled real coastline/country geometry, with a wider default map pane.
- Session table now shows venue state and local exchange time for the expanded session set.
- Freight separates carrier from cargo owner. Ships and aircraft are directional and move from the
  simulated clock rather than frame rate. Ports, routes, vehicles, venues and risk/news objects expose
  associated tradable securities.
- Risk blips derive from market/news events or valid geolocated geopolitical events; zero-coordinate
  phantom risk markers are suppressed.
- Heavy research windows are reused instead of duplicated; advanced charts are bounded to six distinct
  live windows to prevent runaway Tk canvas/timer load.

Career / casino audit
- Career balances refresh at a modest live cadence. Boss objectives display their rewards explicitly.
- Boss rewards and Wendy's pay were sharply reduced; the five-positive-day bonus is now $100 + 10 XP.
- Slots were rebalanced from a player-positive table to an approximately 87.9% modeled return before
  any future rule changes. Slots, roulette and horse racing accept larger experimental bets.
- Blackjack cut-card targets: 50% penetration single-deck, 60% double, 75% four-deck, 80% six-deck,
  and 90% eight-deck.

Offline policy remains unchanged: normal gameplay does not poll market-data services. Network access is
reserved for new-account seeding and the explicit Experimental -> Refresh Market Snapshot action.
