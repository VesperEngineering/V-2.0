"""SQLite cache for market data."""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger("vesper.storage")


class DataCache:
    def __init__(self, db_path: str = "data/market_cache.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bars (
                    symbol    TEXT    NOT NULL,
                    timestamp TEXT    NOT NULL,
                    open      REAL,
                    high      REAL,
                    low       REAL,
                    close     REAL,
                    volume    INTEGER,
                    interval  TEXT    DEFAULT '1d',
                    fetched_at TEXT,
                    PRIMARY KEY (symbol, timestamp, interval)
                )
            """)
            conn.commit()

    def store_bars(self, symbol: str, df: pd.DataFrame, interval: str = "1d"):
        if df.empty:
            return
        now = datetime.utcnow().isoformat()
        rows = [
            (symbol, ts.isoformat(), r["open"], r["high"], r["low"],
             r["close"], int(r["volume"]), interval, now)
            for ts, r in df.iterrows()
        ]
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?,?)", rows
            )
            conn.commit()
        logger.debug("Cached %d bars for %s", len(rows), symbol)

    def load_bars(self, symbol: str, start: datetime, end: datetime,
                  interval: str = "1d") -> pd.DataFrame | None:
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(
                "SELECT timestamp, open, high, low, close, volume "
                "FROM bars WHERE symbol=? AND interval=? "
                "AND timestamp>=? AND timestamp<=? ORDER BY timestamp",
                conn,
                params=(symbol, interval, start.isoformat(), end.isoformat()),
                parse_dates=["timestamp"],
                index_col="timestamp",
            )
        return df if not df.empty else None