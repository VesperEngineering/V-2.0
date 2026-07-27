# Massive SQLite Feed Adapter Pattern
## Added 2026-07-22

## Context
When wiring VESPER v20 to use local Massive SQLite stores instead of YFinance, the minimal change is a `MassiveFeed` class in `vesper/data/feed.py` plus a config switch in `config/settings.yaml`.

## Implementation

### `vesper/data/feed.py` — add `MassiveFeed`

```python
class MassiveFeed(DataFeed):
    """Read from local Massive SQLite stores."""

    def __init__(self, config: dict):
        self.config = config
        data_cfg = config.get("data", {})
        self.data_dir = Path(data_cfg.get("massive_data_dir", "vesper/data/massive"))
        self.sp500_db = self.data_dir / "sp500" / "sp500_ohlcv.sqlite"

    def get_bars(self, symbols: list[str], start: datetime, end: datetime,
                 interval: str = "1d") -> dict[str, pd.DataFrame]:
        if not self.sp500_db.exists():
            return {}
        conn = sqlite3.connect(str(self.sp500_db))
        result = {}
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")
        for sym in symbols:
            try:
                df = pd.read_sql_query(
                    """SELECT date, open, high, low, close, volume
                       FROM sp500_ohlcv
                       WHERE ticker = ? AND date >= ? AND date <= ?
                       ORDER BY date""",
                    conn, params=(sym, start_str, end_str), parse_dates=["date"]
                )
                if df.empty:
                    continue
                df = df.set_index("date")
                df.columns = ["open", "high", "low", "close", "volume"]
                result[sym] = df
            except Exception as e:
                logger.error("Failed to load %s from Massive: %s", sym, e)
        conn.close()
        return result

    def get_latest_price(self, symbols: list[str]) -> dict[str, float]:
        if not self.sp500_db.exists():
            return {}
        conn = sqlite3.connect(str(self.sp500_db))
        prices = {}
        for sym in symbols:
            try:
                row = conn.execute(
                    "SELECT close FROM sp500_ohlcv WHERE ticker = ? ORDER BY date DESC LIMIT 1",
                    (sym,),
                ).fetchone()
                if row and row[0] is not None:
                    price = float(row[0])
                    if 0 < price < 100_000:
                        prices[sym] = price
            except Exception as e:
                logger.error("Failed to get price for %s from Massive: %s", sym, e)
        conn.close()
        return prices
```

Also wire it into `create_feed`:

```python
def create_feed(config: dict) -> DataFeed:
    provider = config.get("data", {}).get("provider", "yfinance")
    if provider == "yfinance":
        return YFinanceFeed()
    if provider == "massive":
        return MassiveFeed(config)
    ...
```

### `config/settings.yaml` — switch provider

```yaml
data:
  provider: massive
  massive_data_dir: "vesper/data/massive"
  cache_db: "data/market_cache.db"
  lookback_days: 60
```

## Why this pattern

- **No external API calls** — backtests are reproducible and not rate-limited.
- **Strategy-agnostic** — works for momentum, XGB, or transformer strategies.
- **Single-file change** — only touches `feed.py` and `settings.yaml`.
- **Graceful fallback** — missing tickers or empty symbol lists return empty dicts without crashing.

## Verification pattern

After wiring, run a narrow ad-hoc check (then delete the temp script):

```python
from datetime import datetime, timedelta
from vesper.data.feed import MassiveFeed, create_feed

feed = MassiveFeed({"data": {"massive_data_dir": "vesper/data/massive"}})
end = datetime(2026, 7, 20)
start = end - timedelta(days=30)

# get_bars
bars = feed.get_bars(["AAPL", "MSFT"], start, end)
assert "AAPL" in bars and len(bars["AAPL"]) > 20
assert list(bars["AAPL"].columns) == ["open", "high", "low", "close", "volume"]

# get_latest_price
prices = feed.get_latest_price(["AAPL"])
assert prices["AAPL"] > 0

# factory
factory = create_feed({"data": {"provider": "massive", "massive_data_dir": "vesper/data/massive"}})
assert isinstance(factory, MassiveFeed)
```

## Pitfalls

- **SPY may not be in the DB** — the 502-ticker `sp500_ohlcv.sqlite` contains S&P constituents like `A`, `AAPL`, etc. Verify with `SELECT DISTINCT ticker FROM sp500_ohlcv LIMIT 10` before assuming any specific ticker exists.
- **Index fund tickers** — `SPY`, `QQQ`, etc. are in the *adjusted* DB (33-ticker universe), not necessarily in the SP500 constituent DB. If the strategy needs ETFs, point `MassiveFeed` at the adjusted or total_return SQLite instead.
- **Raw prices** — `sp500_ohlcv.sqlite` stores raw unadjusted prices. For backtests requiring split-adjusted data, use `fetch_adjusted_ohlcv_rows` from `app/factors/db.py` (in the D:/vesper repo) or multiply by split factors from `vesper_data/split_adjustments.json`.
