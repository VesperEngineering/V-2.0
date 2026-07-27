---
name: vesper-factor-workflow
description: Portfolio snapshot cron and equity chart integration
file: references/portfolio-snapshot.md
---

# Portfolio Snapshot Cron (20:00 UTC Weekdays)

Captures end-of-day portfolio state from Alpaca paper trading account.
Powers the equity curve chart in the dashboard's Portfolio panel.

## Module
`scripts/alpaca_portfolio.py`

## Cron
`0 20 * * 1-5` — 20:00 UTC (4pm ET) weekdays

## Output
`artifacts/evals/alpaca_portfolio_YYYYMMDD.json`

## Dashboard Integration

### Widgets
- `self.port_equity` — `Equity: $106,563.41`
- `self.port_cash` — `Cash: $5,328.17`
- `self.port_positions` — `1 pos  BP: $213,127`

### Equity Curve
Draws line on `self.equity_canvas` (tk.Canvas, h=100). Requires >=2 history points.
Padding: 10/10/10/20. Shows min/max equity labels.

### Refresh
Add `self._load_portfolio()` to `refresh()`.

## History Growth
One entry per day at 20:00 UTC. Builds equity curve over weeks/months.