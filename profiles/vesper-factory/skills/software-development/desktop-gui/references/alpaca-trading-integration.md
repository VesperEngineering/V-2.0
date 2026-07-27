# Alpaca Paper Trading Integration

## Setup
- API keys in `.env`: `ALPACA_KEY_ID`, `ALPACA_SECRET_KEY`
- Keys loaded via `python-dotenv`
- Paper trading is the default (`PAPER = True` in `alpaca_rebalance.py`)

## Rebalance flow
1. `scripts/alpaca_rebalance.py` reads latest `vesper_factor_basket_*.md`
2. Parses tickers in order (top 5 = target portfolio)
3. Fetches current Alpaca paper positions via `TradingClient.get_all_positions()`
4. Computes target: equal-weight allocation across tickers (95% of equity deployed)
5. Sells tickers not in target, buys/increases target tickers
6. Writes receipt to `artifacts/evals/alpaca_receipt_YYYYMMDD.json`

## Critical: notional rounding
Alpaca's REST API rejects notional values with more than 2 decimal places:
```python
round(val, 2)  # ALWAYS round before submitting
```
Skip adjustments under $1.00: `if abs(delta) < 1.0: continue`

## Cron
- Runs weekdays at 14:30 UTC (during market hours)
- Shell script: `~/AppData/Local/hermes/scripts/alpaca_rebalance.sh`
- Cron job ID: `a73b7f956aaf`

## Dashboard integration
- Portfolio bar below schedule shows `Alpaca: $106,563  5 positions`
- Alpaca Rebal row in schedule bar (mapped to `_last_receipt()`)
- "4. Alpaca" button runs the rebalance manually