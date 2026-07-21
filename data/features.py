"""
Feature engineering from OHLCV data.
Every feature is computed from past data only. No look-ahead.
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger("vesper.features")

# These are the columns the model trains on. Order matters.
FEATURE_COLS = [
    "ret_1d", "ret_5d", "ret_10d", "ret_20d",
    "vol_5d", "vol_10d", "vol_20d",
    "vol_ratio", "vol_trend",
    "sma_10", "sma_20", "sma_50",
    "rsi_14",
    "bb_pos",
    "range_hl", "close_pos",
    "dist_from_mean",
]


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute features from a single stock's OHLCV DataFrame.

    Input columns: open, high, low, close, volume (DatetimeIndex).
    Output: DataFrame with FEATURE_COLS columns, same index.
    """
    f = pd.DataFrame(index=df.index)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"].astype(float)

    # ── Returns ────────────────────────────────────────────
    f["ret_1d"] = close.pct_change(1)
    f["ret_5d"] = close.pct_change(5)
    f["ret_10d"] = close.pct_change(10)
    f["ret_20d"] = close.pct_change(20)

    # ── Volatility ─────────────────────────────────────────
    daily_ret = close.pct_change()
    f["vol_5d"] = daily_ret.rolling(5).std()
    f["vol_10d"] = daily_ret.rolling(10).std()
    f["vol_20d"] = daily_ret.rolling(20).std()

    # ── Volume ─────────────────────────────────────────────
    vol_ma20 = volume.rolling(20).mean()
    f["vol_ratio"] = volume / vol_ma20.replace(0, np.nan)
    f["vol_trend"] = volume.rolling(5).mean() / vol_ma20.replace(0, np.nan)

    # ── Moving average position ────────────────────────────
    f["sma_10"] = close / close.rolling(10).mean() - 1
    f["sma_20"] = close / close.rolling(20).mean() - 1
    sma50 = close.rolling(50).mean()
    f["sma_50"] = close / sma50.replace(0, np.nan) - 1

    # ── RSI (14-day) ───────────────────────────────────────
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-10)
    f["rsi_14"] = 100 - (100 / (1 + rs))

    # ── Bollinger Band position ────────────────────────────
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    f["bb_pos"] = (close - sma20) / (2 * std20).replace(0, 1e-10)

    # ── Range / candle position ────────────────────────────
    f["range_hl"] = (high - low) / close.replace(0, np.nan)
    f["close_pos"] = (close - low) / (high - low).replace(0, 1e-10)

    # ── Mean reversion ─────────────────────────────────────
    f["dist_from_mean"] = (close - sma20) / sma20.replace(0, np.nan)

    return f[FEATURE_COLS]


def compute_label(df: pd.DataFrame, horizon: int = 5) -> pd.Series:
    """
    Forward N-day return. This is what the model learns to predict.

    horizon=5 means: "what will this stock return over the next 5 trading days?"
    Shifted backward so row T contains the return from T to T+5.
    """
    return df["close"].pct_change(horizon).shift(-horizon)