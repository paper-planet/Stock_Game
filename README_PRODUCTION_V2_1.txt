Stock Game Pro 2.1 — Liquidity / Whale Dynamics

- Market orders consume displayed Level 2 liquidity and sweep synthetic deeper liquidity.
- Player BUY/COVER flow moves quotes upward; SELL/SHORT flow moves quotes downward.
- Square-root impact scales with order size versus estimated ADV, volatility, price and current liquidity.
- Penny/distressed stocks become much more sensitive to large orders.
- Liquidity is depleted by large sweeps and replenishes gradually instead of instantly.
- Execution messages report VWAP, estimated market impact and ADV participation.
- Price impact persists and decays rather than disappearing on the next engine tick.
- Distressed stocks have a fundamental-value mean-reversion mechanism so the price floor is not an absorbing state.
- Existing 2.0 bounded-history, staggered engine and daily autosave architecture retained.

This is a simulated market-impact model for training/gameplay, not an exchange-certified execution simulator.
