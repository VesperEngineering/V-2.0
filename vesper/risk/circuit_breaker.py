"""Daily loss kill switch. Trips once, auto-resets next trading day."""

import logging
from datetime import date, datetime

logger = logging.getLogger("vesper.risk.breaker")


class CircuitBreaker:
    def __init__(self, max_daily_loss: float):
        self.max_daily_loss = max_daily_loss
        self._tripped = False
        self._trip_date: date | None = None
        self._trip_pnl: float = 0.0
        logger.info("CircuitBreaker armed: limit=$%,.0f", max_daily_loss)

    @property
    def is_tripped(self) -> bool:
        return self._tripped

    def check(self, daily_pnl: float, timestamp: datetime) -> bool:
        """Returns True if trading should STOP."""
        today = timestamp.date()

        # Auto-reset on new day
        if self._trip_date and self._trip_date != today:
            logger.info("CircuitBreaker reset (new day)")
            self._tripped = False
            self._trip_date = None

        if self._tripped:
            return True

        if daily_pnl <= self.max_daily_loss:
            self._tripped = True
            self._trip_date = today
            self._trip_pnl = daily_pnl
            logger.critical(
                f"CIRCUIT BREAKER TRIPPED — P&L ${daily_pnl:,.0f} "
                f"<= limit ${self.max_daily_loss:,.0f} — HALTING"
            )
            return True

        return False

    def get_status(self) -> dict:
        return {
            "tripped": self._tripped,
            "trip_date": self._trip_date.isoformat() if self._trip_date else None,
            "trip_pnl": self._trip_pnl,
            "limit": self.max_daily_loss,
        }