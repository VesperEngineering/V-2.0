"""Train an XGBoost regressor on SP500 historical data.

Reads from the local Massive SP500 SQLite store, computes features,
applies cross-sectional z-scoring within each date, and trains an
XGBRegressor. The resulting model is saved to models/xgb_ranker.json.
"""

import json
import hashlib
import logging
import sqlite3
import sys
from pathlib import Path

import argparse
import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).parent.parent))

from vesper.data.features import compute_features, FEATURE_COLS

logger = logging.getLogger("train_model")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")

SP500_DB = Path("vesper/data/massive/sp500/sp500_ohlcv.sqlite")
MODEL_PATH = Path("models/xgb_ranker.json")
LOOKBACK_MIN = 50
LABEL_HORIZON = 5
MODEL_PARAMS = {
    "n_estimators": 50,
    "max_depth": 2,
    "learning_rate": 0.05,
    "subsample": 0.6,
    "colsample_bytree": 0.6,
    "reg_alpha": 5.0,
    "reg_lambda": 20.0,
    "objective": "reg:squarederror",
    "n_jobs": -1,
    "random_state": 42,
}

# Candidate paths for split-adjustment map (cumulative forward factors)
SPLIT_ADJ_PATHS = [
    Path("vesper/data/massive/split_adjustments.json"),
]


def _load_split_adjustments() -> dict[str, dict[str, float]] | None:
    """Load cumulative forward split-adjustment factors if available."""
    for p in SPLIT_ADJ_PATHS:
        if p.exists():
            logger.info("Loading split adjustments from %s", p)
            return json.loads(p.read_text())
    return None


def _apply_split_adjustments(
    bars: dict[str, pd.DataFrame], adjustments: dict[str, dict[str, float]]
) -> dict[str, pd.DataFrame]:
    """Multiply price columns by cumulative forward split factors."""
    adjusted = {}
    for ticker, df in bars.items():
        df = df.copy()
        adj = adjustments.get(ticker, {})
        if adj:
            # Build a series of factors aligned to df index
            factor = pd.Series({pd.Timestamp(d): v for d, v in adj.items()})
            factor = factor.reindex(df.index, method="ffill").fillna(1.0)
            for col in ("open", "high", "low", "close"):
                df[col] = df[col] * factor
        adjusted[ticker] = df
    return adjusted


def load_bars(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    """Load all SP500 bars from SQLite, keyed by ticker."""
    query = """
        SELECT ticker, date, open, high, low, close, volume
        FROM sp500_ohlcv
        ORDER BY ticker, date
    """
    df = pd.read_sql_query(query, conn, parse_dates=["date"])
    df = df.set_index("date")
    grouped = {}
    for ticker, g in df.groupby("ticker"):
        g = g[["open", "high", "low", "close", "volume"]].sort_index()
        grouped[ticker] = g
    return grouped


def build_training_set(
    bars: dict[str, pd.DataFrame],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute features, z-score cross-sectionally within each date, return X, y, dates."""
    rows: list[pd.DataFrame] = []

    for ticker, df in bars.items():
        if len(df) < LOOKBACK_MIN + LABEL_HORIZON:
            continue

        try:
            feats = compute_features(df)
            labels = df["close"].pct_change(LABEL_HORIZON).shift(-LABEL_HORIZON)
        except Exception as e:
            logger.warning("Feature error for %s: %s", ticker, e)
            continue

        aligned = feats.join(labels.rename("label"), how="inner").dropna()
        if aligned.empty:
            continue

        aligned = aligned.copy()
        aligned["ticker"] = ticker
        aligned = aligned.reset_index()
        rows.append(aligned)

    if not rows:
        raise RuntimeError("No valid training samples produced.")

    panel = pd.concat(rows, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])

    # Cross-sectional z-score within each date
    def _zscore(s: pd.Series) -> pd.Series:
        m = s.mean()
        std = s.std()
        return pd.Series(0.0, index=s.index) if std == 0 or pd.isna(std) else (s - m) / std

    for col in FEATURE_COLS:
        panel[col] = panel.groupby("date", group_keys=False)[col].apply(_zscore)

    # Also z-score the label cross-sectionally (ranking target)
    panel["label"] = panel.groupby("date", group_keys=False)["label"].apply(_zscore)

    # Drop NaN / inf
    panel = panel.replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURE_COLS + ["label"])

    X = panel[FEATURE_COLS].values
    y = panel["label"].values
    dates = panel["date"].values.astype("datetime64[ns]")

    logger.info("Training set after z-score: X=%s, y=%s", X.shape, y.shape)
    return X, y, dates


def train(X: np.ndarray, y: np.ndarray) -> xgb.XGBRegressor:
    model = xgb.XGBRegressor(**MODEL_PARAMS)
    model.fit(X, y)
    return model


def evaluate(model: xgb.XGBRegressor, X: np.ndarray, y: np.ndarray) -> float:
    preds = model.predict(X)
    ic = np.corrcoef(preds, y)[0, 1]
    return float(ic)


def write_model_metadata(
    model_path: Path,
    *,
    train_ic: float,
    test_ic: float,
    train_samples: int,
    test_samples: int,
) -> Path:
    """Persist the model's reproducibility-critical training result."""
    metadata_path = model_path.with_suffix(".metadata.json")
    metadata = {
        "model_path": str(model_path),
        "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "label_horizon": LABEL_HORIZON,
        "train_ic": train_ic,
        "out_of_sample_ic": test_ic,
        "train_samples": train_samples,
        "test_samples": test_samples,
        "model_parameters": MODEL_PARAMS,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata_path


def main():
    parser = argparse.ArgumentParser(description="Train Vesper XGBoost ranker")
    parser.add_argument("--log-file", type=Path, help="Write log output to file")
    args = parser.parse_args()

    if args.log_file:
        fh = logging.FileHandler(args.log_file)
        fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        logging.getLogger().addHandler(fh)

    if not SP500_DB.exists():
        logger.error("SP500 DB not found at %s", SP500_DB)
        sys.exit(1)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Loading bars from %s", SP500_DB)
    conn = sqlite3.connect(str(SP500_DB))
    bars = load_bars(conn)
    conn.close()
    logger.info("Loaded %d tickers", len(bars))

    # Split adjustment (if available)
    split_adj = _load_split_adjustments()
    if split_adj:
        bars = _apply_split_adjustments(bars, split_adj)
        logger.info("Applied split adjustments to %d tickers", len(split_adj))
    else:
        logger.warning("No split adjustments found; using raw prices")

    logger.info("Building training set...")
    X, y, dates = build_training_set(bars)

    # Chronological split
    cutoff = np.datetime64("2021-01-01")
    train_mask = dates < cutoff
    test_mask = dates >= cutoff

    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]

    logger.info("Train samples: %d | Test samples: %d", len(y_train), len(y_test))

    if len(y_train) == 0 or len(y_test) == 0:
        logger.error("Insufficient data for chronological split")
        sys.exit(1)

    logger.info("Training model...")
    model = train(X_train, y_train)

    train_ic = evaluate(model, X_train, y_train)
    test_ic = evaluate(model, X_test, y_test)

    logger.info("Train IC: %.4f | Out-of-sample IC: %.4f", train_ic, test_ic)

    model.save_model(str(MODEL_PATH))
    logger.info("Model saved to %s", MODEL_PATH)
    metadata_path = write_model_metadata(
        MODEL_PATH,
        train_ic=train_ic,
        test_ic=test_ic,
        train_samples=len(y_train),
        test_samples=len(y_test),
    )
    logger.info("Model metadata saved to %s", metadata_path)


if __name__ == "__main__":
    main()
