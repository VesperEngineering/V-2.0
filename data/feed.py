"""Market data feed. Default: yfinance. Swap in your API via CustomFeed."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime

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


def create_feed(config: dict) -> DataFeed:
    provider = config.get("data", {}).get("provider", "yfinance")
    if provider == "yfinance":
        logger.info("Data feed: yfinance")
        return YFinanceFeed()
    if provider == "custom":
        logger.info("Data feed: custom")
        return CustomFeed()
    raise ValueError(f"Unknown data provider: {provider}")