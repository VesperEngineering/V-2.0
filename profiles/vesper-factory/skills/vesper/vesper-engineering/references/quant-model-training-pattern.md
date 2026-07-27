# Quant Model Training Pattern — Chronological Split

Template for training an XGBoost ranker on Vesper's SP500 SQLite data with proper chronological split to avoid data leakage.

## Script Structure

```python
"""Train an XGBoost regressor on SP500 historical data with chronological split."""

import logging
import sqlite3
import sys
from pathlib import Path

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
TRAIN_CUTOFF = np.datetime64("2021-01-01")


def load_bars(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:
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


def build_training_set(bars: dict[str, pd.DataFrame]):
    X_rows, y_vals, dates = [], [], []

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

        X_rows.append(aligned[FEATURE_COLS].values)
        y_vals.extend(aligned["label"].tolist())
        dates.extend(aligned.index.tolist())

    X = np.vstack(X_rows)
    y = np.array(y_vals, dtype=float)
    dates_arr = np.array(dates, dtype="datetime64[ns]")

    valid = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    return X[valid], y[valid], dates_arr[valid]


def evaluate(model, X, y) -> float:
    preds = model.predict(X)
    return float(np.corrcoef(preds, y)[0, 1])


def main():
    if not SP500_DB.exists():
        logger.error("SP500 DB not found")
        sys.exit(1)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(SP500_DB))
    bars = load_bars(conn)
    conn.close()
    logger.info("Loaded %d tickers", len(bars))

    X, y, dates = build_training_set(bars)

    train_mask = dates < TRAIN_CUTOFF
    test_mask = dates >= TRAIN_CUTOFF
    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]

    logger.info("Train: %d | Test: %d", len(y_train), len(y_test))

    model = xgb.XGBRegressor(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        objective="reg:squarederror", n_jobs=-1, random_state=42,
    )
    model.fit(X_train, y_train)

    train_ic = evaluate(model, X_train, y_train)
    test_ic = evaluate(model, X_test, y_test)
    logger.info("Train IC: %.4f | Out-of-sample IC: %.4f", train_ic, test_ic)

    model.save_model(str(MODEL_PATH))
    logger.info("Model saved to %s", MODEL_PATH)


if __name__ == "__main__":
    main()
```

## Key Rules

- `TRAIN_CUTOFF` must be a calendar date, never a random percentage.
- Report **both** train and out-of-sample IC. Out-of-sample is the only number that matters for go/no-go.
- In-sample IC > 0.90 without chronological split = overfitting red flag.
- Save the model with `model.save_model()` (JSON format for XGBoost >= 1.0).
