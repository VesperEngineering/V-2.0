#!/usr/bin/env python3
"""Regenerate split_adjustments.json from sp500_ohlcv.sqlite.

Detects stock splits by scanning for large single-day price discontinuities
matching standard split ratios (2:1, 3:1, 4:1, 5:1, 7:1, 10:1, 20:1).
Builds cumulative forward-adjustment factors — multiply raw close prices by
the factor to get split-adjusted prices comparable to post-split scale.

Output: vesper_data/split_adjustments.json
Format: {ticker: {date: cumulative_factor}}

Usage: python scripts/detect_splits.py [--root /path/to/vesper]
"""
import json
import sqlite3
import sys
from pathlib import Path

STANDARD_RATIOS = {2: 0.5, 3: 1 / 3, 4: 0.25, 5: 0.2, 7: 1 / 7, 10: 0.1, 20: 0.05}
TOLERANCE = 0.02


def is_likely_split(ratio: float) -> int | None:
    for n, expected in STANDARD_RATIOS.items():
        if abs(ratio - expected) < TOLERANCE:
            return n
    return None


def main(root: Path) -> None:
    db_path = root / "vesper_data" / "massive" / "sp500" / "sp500_ohlcv.sqlite"
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    tickers = sorted(
        r["ticker"]
        for r in conn.execute(
            "SELECT DISTINCT ticker FROM sp500_ohlcv ORDER BY ticker"
        ).fetchall()
    )

    adjustments = {}
    split_count = 0
    affected = 0

    for ticker in tickers:
        rows = conn.execute(
            "SELECT date, close FROM sp500_ohlcv WHERE ticker=? ORDER BY date ASC",
            (ticker,),
        ).fetchall()
        if len(rows) < 2:
            continue

        cum_factor = 1.0
        ticker_adj = {}

        # Iterate BACKWARD: start at most recent date with factor=1.0
        for j in range(len(rows) - 1, -1, -1):
            date = rows[j]["date"]
            ticker_adj[date] = cum_factor

            if j > 0:
                prev_close = rows[j - 1]["close"]
                curr_close = rows[j]["close"]
                if prev_close > 0 and curr_close > 0:
                    forward_ratio = curr_close / prev_close
                    n = is_likely_split(forward_ratio)
                    if n is not None:
                        cum_factor *= 1.0 / n
                        split_count += 1

        adjustments[ticker] = ticker_adj
        if len(set(ticker_adj.values())) > 1:
            affected += 1

    conn.close()

    out_path = root / "vesper_data" / "split_adjustments.json"
    with open(out_path, "w") as f:
        json.dump(adjustments, f)

    print(f"Detected {split_count} splits across {affected}/{len(tickers)} tickers")
    print(f"Written to {out_path}")


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    main(root)