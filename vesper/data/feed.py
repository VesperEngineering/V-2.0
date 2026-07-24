"""Market data feed. Default: yfinance. Swap in your API via CustomFeed."""

import logging
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

logger = logging.getLogger("vesper.data")


class DataFeed(ABC):
    @abstractmethod
    def get_bars(self, symbols: list[str], start: datetime, end: datetime,
                 interval: str = "1d") -> dict[str, pd.DataFrame]:
        ...

    @abstractmethod
    def get_latest_price(self, symbols: list[str]) -> dict[str, float]:
        ...


class YFinanceFeed(DataFeed):
    def get_bars(self, symbols, start, end, interval="1d"):
        result = {}
        for sym in symbols:
            try:
                df = yf.download(
                    sym,
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                    interval=interval,
                    progress=False,
                    auto_adjust=True,
                )
                if df.empty:
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
                df.columns = ["open", "high", "low", "close", "volume"]
                result[sym] = df
            except Exception as e:
                logger.error("Failed to fetch %s: %s", sym, e)
        return result

    def get_latest_price(self, symbols):
        prices = {}
        for sym in symbols:
            try:
                ticker = yf.Ticker(sym)
                price = float(ticker.fast_info.last_price)

                # Reject garbage data
                if price != price:          # NaN
                    logger.error("%s: NaN price, skipping", sym)
                    continue
                if price <= 0:
                    logger.error("%s: non-positive price $%.2f, skipping", sym, price)
                    continue
                if price > 100_000:
                    logger.error("%s: absurd price $%.2f, skipping", sym, price)
                    continue

                # Warn if price looks stale (equals previous close)
                hist = ticker.history(period="2d")
                if len(hist) >= 2:
                    prev = float(hist["Close"].iloc[-2])
                    if abs(price - prev) < 0.001:
                        logger.warning("%s: price equals prev close ($%.2f), may be stale", sym, price)

                prices[sym] = price
            except Exception as e:
                logger.error("Failed to get price for %s: %s", sym, e)
        return prices


class CustomFeed(DataFeed):
    """
    Plug your data API here.

    Implement get_bars() and get_latest_price() using your provider's
    SDK or REST API. The engine only calls these two methods.

    Example skeleton:

        import requests

        class MyFeed(CustomFeed):
            def __init__(self, api_key, base_url):
                self.s = requests.Session()
                self.s.headers["Authorization"] = f"Bearer {api_key}"
                self.url = base_url

            def get_bars(self, symbols, start, end, interval="1d"):
                out = {}
                for sym in symbols:
                    r = self.s.get(f"{self.url}/bars/{sym}", params={...})
                    r.raise_for_status()
                    df = pd.DataFrame(r.json()["bars"])
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df = df.set_index("timestamp")
                    out[sym] = df[["open","high","low","close","volume"]]
                return out

            def get_latest_price(self, symbols):
                out = {}
                for sym in symbols:
                    r = self.s.get(f"{self.url}/quote/{sym}")
                    out[sym] = float(r.json()["last"])
                return out
    """

    def get_bars(self, symbols, start, end, interval="1d"):
        raise NotImplementedError("Implement get_bars with your data API")

    def get_latest_price(self, symbols):
        raise NotImplementedError("Implement get_latest_price with your data API")


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
            logger.error("Massive SP500 DB not found at %s", self.sp500_db)
            return {}

        conn = sqlite3.connect(str(self.sp500_db))
        result = {}

        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        for sym in symbols:
            try:
                query = """
                    SELECT date, open, high, low, close, volume
                    FROM sp500_ohlcv
                    WHERE ticker = ? AND date >= ? AND date <= ?
                    ORDER BY date
                """
                df = pd.read_sql_query(
                    query, conn, params=(sym, start_str, end_str),
                    parse_dates=["date"]
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
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT close FROM sp500_ohlcv WHERE ticker = ? ORDER BY date DESC LIMIT 1",
                    (sym,),
                )
                row = cursor.fetchone()
                if row and row[0] is not None:
                    price = float(row[0])
                    if 0 < price < 100_000:
                        prices[sym] = price
            except Exception as e:
                logger.error("Failed to get price for %s from Massive: %s", sym, e)

        conn.close()
        return prices


def create_feed(config: dict) -> DataFeed:
    provider = config.get("data", {}).get("provider", "yfinance")
    if provider == "yfinance":
        logger.info("Data feed: yfinance")
        return YFinanceFeed()
    if provider == "massive":
        logger.info("Data feed: massive (local SQLite)")
        return MassiveFeed(config)
    if provider == "custom":
        logger.info("Data feed: custom")
        return CustomFeed()
    raise ValueError(f"Unknown data provider: {provider}")