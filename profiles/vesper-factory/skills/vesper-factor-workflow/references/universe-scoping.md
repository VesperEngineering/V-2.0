# Universe Scoping Gate

## Problem
Informal factors (e.g. `market_micro`) emit scores for 19K+ tickers spanning
all US exchanges. When the score combiner takes the **union** of all factor
universes and z-scores cross-sectionally, small-cap/ADR tickers dominate the
S&P 500 ranking. IAUX (i-80 Gold Corp, small-cap miner) can rank #1 despite
being uninvestable in a notional S&P 500 basket.

## Fix
`scripts/run_all_factors.py` now gates the published ranking to the admitted
scoring universe (`data/sp500_tickers.json`, 502 names). The combiner
intersects raw factor tickers with the universe set before scoring.

Key change in `run()`:
```python
scoring_universe = load_scoring_universe()
raw_tickers = {t for r in results.values() for t in r.scores}
all_tickers = raw_tickers & scoring_universe  # gate here
external_tickers = sorted(raw_tickers - scoring_universe)
```

## Artifact Fields Added
- `universe`: `"sp500_current"`
- `universe_path`: path to tickers file
- `universe_size`: 502
- `external_factor_tickers_excluded`: count of non-S&P tickers dropped

External tickers are logged but not published. The gate fails closed:
if the universe file is missing or empty, scoring returns exit code 1.

## Testing
Three test functions in `tests/test_run_all_factors.py`:
- `test_load_scoring_universe_parses_comma_list` — file format
- `test_run_excludes_non_universe_factor_tickers` — IAUX excluded
- Updated `test_run_excludes_zero_weight_only_ticker_and_keeps_negative_governed_score` — uses AAPL + monkeypatched universe

## See also
- `scripts/run_all_factors.py` — `load_scoring_universe()`, gated combine
- `data/sp500_tickers.json` — current S&P 500 constituents (502)