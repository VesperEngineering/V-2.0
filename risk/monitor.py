"""Real-time portfolio risk tracking."""

import logging
from datetime import datetime

from vesper.execution.broker import Position

logger = logging.getLogger("vesper.risk.monitor")


class RiskMonitor:
    def __init__(self):
        self.starting_equity: float = 0.0
        self.daily_pnl: float = 0.0
        self.realized_pnl: float = 0.0
        self.unrealized_pnl: float = 0.0
        self.peak_equity: float = 0.0
        self.max_drawdown: float = 0.0
        self.total_exposure: float = 0.0
        self.num_positions: int = 0
        self._session_date = None

    def start_session(self, equity: float, timestamp: datetime):
        self.starting_equity = equity
        self.peak_equity = equity
        self.daily_pnl = 0.0
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.max_drawdown = 0.0
        self._session_date = timestamp.date()
        logger.info("Risk session started: equity=$%,.0f", equity)

    def update(self, positions: dict[str, Position], account: dict,
               timestamp: datetime):
        equity = account.get("equity", 0)
        self.daily_pnl = equity - self.starting_equity
        self.unrealized_pnl = sum(p.unrealized_pnl for p in positions.values())
        self.realized_pnl = self.daily_pnl - self.unrealized_pnl
        self.total_exposure = sum(p.market_value for p in positions.values())
        self.num_positions = len(positions)
        if equity > self.peak_equity:
            self.peak_equity = equity
        if self.peak_equity > 0:
            self.max_drawdown = min(
                self.max_drawdown,
                (equity - self.peak_equity) / self.peak_equity,
            )

    def get_summary(self) -> dict:
        return {
            "daily_pnl": self.daily_pnl,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_exposure": self.total_exposure,
            "num_positions": self.num_positions,
            "peak_equity": self.peak_equity,
            "max_drawdown": self.max_drawdown,
            "starting_equity": self.starting_equity,
        }