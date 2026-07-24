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
    "macd",
    "macd_signal",
    "atr_14",
    "intraday_ret",
    "mfi_14",
    "stoch_k",
    "cci_20",
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

    # ── MACD ───────────────────────────────────────────────
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    f["macd"] = ema12 - ema26
    f["macd_signal"] = f["macd"].ewm(span=9, adjust=False).mean()

    # ── ATR (14-day) ───────────────────────────────────────
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    f["atr_14"] = tr.rolling(14).mean() / close.replace(0, np.nan)

    # ── Intraday return ────────────────────────────────────
    f["intraday_ret"] = (close - df["open"]) / df["open"].replace(0, np.nan)

    # ── Money Flow Index (14-day) ──────────────────────────
    typical_price = (high + low + close) / 3
    raw_money_flow = typical_price * volume
    money_flow_sign = np.where(typical_price > typical_price.shift(1), 1, -1)
    signed_money_flow = raw_money_flow * money_flow_sign
    positive_flow = pd.Series(np.where(signed_money_flow > 0, signed_money_flow, 0), index=df.index)
    negative_flow = pd.Series(np.where(signed_money_flow < 0, -signed_money_flow, 0), index=df.index)
    positive_sum = positive_flow.rolling(14).sum()
    negative_sum = negative_flow.rolling(14).sum()
    mfi_ratio = positive_sum / negative_sum.replace(0, np.nan)
    f["mfi_14"] = 100 - (100 / (1 + mfi_ratio))

    # ── Stochastic %K ──────────────────────────────────────
    lowest_low = low.rolling(14).min()
    highest_high = high.rolling(14).max()
    f["stoch_k"] = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)

    # ── CCI (20-day) ───────────────────────────────────────
    sma_tp = typical_price.rolling(20).mean()
    mad_tp = typical_price.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    f["cci_20"] = (typical_price - sma_tp) / (0.015 * mad_tp.replace(0, np.nan))

    return f[FEATURE_COLS]


def compute_label(df: pd.DataFrame, horizon: int = 5) -> pd.Series:
    """
    Forward N-day return. This is what the model learns to predict.

    horizon=5 means: "what will this stock return over the next 5 trading days?"
    Shifted backward so row T contains the return from T to T+5.
    """
    return df["close"].pct_change(horizon).shift(-horizon)


def zscore_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cross-sectionally z-score features.

    Input: DataFrame with one row per stock, FEATURE_COLS columns.
    Output: Same shape, each column standardized to mean=0, std=1.
    """
    out = df.copy()
    for col in FEATURE_COLS:
        m = df[col].mean()
        std = df[col].std()
        if std == 0 or pd.isna(std):
            out[col] = 0.0
        else:
            out[col] = (df[col] - m) / std
    return out