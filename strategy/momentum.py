"""Cross-sectional momentum: rank by N-day return, buy top_n, sell losers."""

import logging
from datetime import datetime

import pandas as pd

from .base import Signal, SignalAction, Strategy

logger = logging.getLogger("vesper.strategy.momentum")


class MomentumStrategy(Strategy):
    def __init__(self, params: dict):
        super().__init__("momentum", params)
        self.lookback = params.get("lookback", 20)
        self.top_n = params.get("top_n", 5)
        self.rebalance_interval = params.get("rebalance_interval", 30)
        self.entry_threshold = params.get("entry_threshold", 0.02)
        self.exit_threshold = params.get("exit_threshold", -0.01)
        self._last_rebalance: datetime | None = None

    def _momentum(self, data: dict[str, pd.DataFrame]) -> dict[str, float]:
        out = {}
        for sym, df in data.items():
            if len(df) < self.lookback + 1:
                continue
            c = df["close"].values
            out[sym] = float((c[-1] - c[-self.lookback - 1]) / c[-self.lookback - 1])
        return out

    def generate_signals(self, data, current_positions, timestamp):
        signals: list[Signal] = []

        # Respect rebalance interval
        if self._last_rebalance is not None:
            elapsed = (timestamp - self._last_rebalance).total_seconds() / 60
            if elapsed < self.rebalance_interval:
                return signals
        self._last_rebalance = timestamp

        mom = self._momentum(data)
        if not mom:
            return signals

        ranked = sorted(mom.items(), key=lambda x: x[1], reverse=True)

        # EXIT: close positions that fell below threshold
        for sym in current_positions:
            m = mom.get(sym)
            if m is not None and m < self.exit_threshold:
                signals.append(Signal(
                    sym, SignalAction.CLOSE, 1.0,
                    f"momentum {m:.3f} < exit threshold {self.exit_threshold}",
                    timestamp,
                ))

        # ENTRY: buy top_n above threshold, skip already-held
        held = set(current_positions.keys())
        candidates = [(s, m) for s, m in ranked if s not in held and m > self.entry_threshold]

        for sym, m in candidates[: self.top_n]:
            rank = next(i for i, (s, _) in enumerate(ranked) if s == sym)
            strength = max(0.1, 1.0 - rank / len(ranked))
            signals.append(Signal(
                sym, SignalAction.BUY, strength,
                f"momentum {m:.3f}, rank #{rank + 1}",
                timestamp,
                {"momentum": m, "rank": rank + 1},
            ))

        return signals