# Alpaca Paper Trading Integration

> **Session**: 2026-07-05 — First live Alpaca paper trade executed.
> Account: PA327QEV72FG, $106,563 equity deployed across 5 positions.

## Overview

Connects the factor model's basket selection to a live Alpaca paper trading account.
The rebalance script reads the latest `vesper_factor_basket_*.md`, compares against
current Alpaca positions, and places market orders to match the target weights.

## File Locations

| File | Purpose |
|---|---|
| `scripts/alpaca_rebalance.py` | Rebalance logic (Python) |
| `~/AppData/Local/hermes/scripts/alpaca_rebalance.sh` | Cron wrapper for Hermes |
| `artifacts/evals/alpaca_receipt_*.json` | Rebalance receipt (written after each run) |

## API Credentials

Stored in the repo's `.env` file:

```
ALPACA_KEY_ID=PKVDI4NC...
ALPACA_SECRET_KEY=2Jj8jDoP...
```

Loaded via `python-dotenv`:

```python
import dotenv
dotenv.load_dotenv(ROOT / ".env")
API_KEY = os.getenv("ALPACA_KEY_ID")
API_SECRET = os.getenv("ALPACA_SECRET_KEY")
```

**These are paper trading keys.** Never switch to live keys without explicit user
authorization and guardrail updates. The `PAPER = True` constant in the script
is a safety belt — the Alpaca `TradingClient` also takes a `paper=` parameter.

## How Rebalance Works

1. **Read basket**: Finds the most recent `vesper_factor_basket_*.md` via glob
2. **Get account state**: Queries Alpaca for equity and current positions
3. **Calculate target**: Allocates 95% of equity equally across all basket tickers
4. **Sell exits**: Any position not in the target basket is fully liquidated
5. **Buy entries**: For each target ticker, buy the difference between current and target
6. **Write receipt**: Logs orders to `alpaca_receipt_YYYYMMDD.json`

### Key implementation details

```python
def _rebalance(client, target_tickers, budget_fraction=0.95):
    equity = _paper_value(client)
    total_to_deploy = equity * budget_fraction
    per_position = total_to_deploy / len(target_tickers)
    current = _current_positions(client)
    # Sell tickers not in target
    for ticker, val in current.items():
        if ticker not in target_tickers:
            client.submit_order(MarketOrderRequest(
                symbol=ticker, notional=round(val, 2),
                side=OrderSide.SELL, time_in_force=TimeInForce.DAY))
    # Buy/Adjust target tickers
    for ticker in target_tickers:
        existing = current.get(ticker, 0.0)
        delta = round(per_position - round(existing, 2), 2)
        if abs(delta) < 1.0: continue
        side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        client.submit_order(MarketOrderRequest(
            symbol=ticker, notional=abs(delta),
            side=side, time_in_force=TimeInForce.DAY))
```

**Critical**: Alpaca requires `notional` values to be rounded to 2 decimal places.
Unrounded floats cause a `422` error. Always use `round(val, 2)` before passing to `MarketOrderRequest`.

## Cron Schedule

```
30 14 * * 1-5  →  Alpaca Rebalance (weekdays only, 14:30 UTC / 10:30 AM ET)
```

| Field | Value |
|---|---|
| Job ID | `a73b7f956aaf` |
| Name | Vesper Alpaca Rebalance |
| Script | `alpaca_rebalance.sh` |
| Workdir | `D:\vesper` |
| Type | `no_agent=True` (pure shell script) |

## Dashboard Integration

The dashboard shows Alpaca account status in a **Portfolio** bar below the schedule.
The **"4. Rebalance Alpaca"** toolbar button runs the script on demand.
The `SCHEDULE` list includes an "Alpaca Rebal" row mapped to `_last_receipt()` for timestamp display.

## Alpaca-py Package

```bash
pip install alpaca-py
```

Version installed: `0.43.5`. Key modules:

```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
```

## Paper Account Details

| Field | Value |
|---|---|
| Account Number | PA327QEV72FG |
| Status | ACTIVE |
| Starting Equity | $106,563.41 |
| First Deployment | $101,235 across COST, NFLX, XLK, QQQ, IWM |
| Remaining Cash | ~$5,300 (5% cash reserve) |

## Safety Notes

- The rebalance script is designed for paper trading only. The `PAPER=True` constant
  must be changed to `False` for live deployment.
- Receipt files provide an audit trail and can be used to reconstruct trade history.
- Notional-based market orders are used for simplicity. Alpaca converts to fractional shares automatically.
- **Cancel stale orders before placing new ones**: The rebalance script must cancel all open orders at the top of `_rebalance()`. Without this, running the script multiple times stacks up duplicate buy orders that all execute at market open:
  ```python
  from alpaca.trading.requests import GetOrdersRequest
  stale = client.get_orders(filter=GetOrdersRequest(status="open"))
  for o in stale:
      try: client.cancel_order_by_id(o.id)
      except: pass
  if stale: print(f"Cancelled {len(stale)} stale orders")
  ```
  Place this code **before** computing equity or comparing positions.