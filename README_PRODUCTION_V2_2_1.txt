Stock Game Pro 2.2.1 — Large Position Stability Hotfix

This release targets a scaling failure that could appear while repeatedly increasing large
stock/short/option positions.

Key changes
- Short-sale proceeds are now treated as restricted collateral instead of reusable free cash.
  This prevents recursive short pyramiding from creating astronomical positions and numerical
  states that eventually destabilize the simulator.
- Buying power = cash - restricted short proceeds - reserved margin.
- Marketable orders have realistic instantaneous capacity based on displayed depth, estimated
  average daily volume, and estimated tradable float. Oversized orders partially fill instead
  of forcing an effectively infinite quantity through one simulated print.
- Long/short ownership is capped by estimated float/borrow capacity while still allowing whale
  positions and substantial price impact.
- One-click permanent price displacement has safety rails; residual order-flow pressure still
  persists into later ticks, so whale trades remain consequential.
- Asset prices and trade-volume inputs are finite/clamped before entering chart and option math.
- Repeated fills of the same option contract/spread are aggregated into existing option position
  groups instead of appending an unbounded number of OptionStrategy objects.
- Old saves are compacted automatically on restore.
- Portfolio Treeview refreshes are coalesced under very large position counts.
- Status bar shows free buying power and position-group counts for performance diagnostics.

The 2.2 world map, professional charting, research lab, session shading, SPY startup chart,
real-data adapters, and end-of-day autosave remain intact.
