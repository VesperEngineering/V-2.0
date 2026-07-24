"""US equity market calendar — hours, holidays, session state."""

from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo


# NYSE holidays 2026
HOLIDAYS_2026 = {
    date(2026, 1, 1),    # New Year's Day
    date(2026, 1, 19),   # MLK Day
    date(2026, 2, 16),   # Presidents' Day
    date(2026, 4, 3),    # Good Friday
    date(2026, 5, 25),   # Memorial Day
    date(2026, 6, 19),   # Juneteenth
    date(2026, 7, 3),    # Independence Day (observed)
    date(2026, 9, 7),    # Labor Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas
}

EARLY_CLOSE_2026 = {
    date(2026, 7, 2),    # Day before July 4th
    date(2026, 11, 27),  # Day after Thanksgiving
    date(2026, 12, 24),  # Christmas Eve
}


class MarketState(Enum):
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    OPEN = "open"
    EARLY_CLOSE = "early_close"
    POST_MARKET = "post_market"
    HOLIDAY = "holiday"
    WEEKEND = "weekend"


class MarketCalendar:
    def __init__(self, timezone: str = "US/Eastern"):
        self.tz = ZoneInfo(timezone)
        self.open_time = time(9, 30)
        self.close_time = time(16, 0)
        self.early_close_time = time(13, 0)

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def is_trading_day(self, d: date | None = None) -> bool:
        d = d or self.now().date()
        return d.weekday() < 5 and d not in HOLIDAYS_2026

    def get_close_time(self, d: date | None = None) -> time:
        d = d or self.now().date()
        if d in EARLY_CLOSE_2026:
            return self.early_close_time
        return self.close_time

    def get_state(self, dt: datetime | None = None) -> MarketState:
        dt = dt or self.now()
        d, t = dt.date(), dt.time()

        if d.weekday() >= 5:
            return MarketState.WEEKEND
        if d in HOLIDAYS_2026:
            return MarketState.HOLIDAY

        close = self.get_close_time(d)

        if t < time(4, 0):
            return MarketState.CLOSED
        if t < self.open_time:
            return MarketState.PRE_MARKET
        if t < close:
            if close == self.early_close_time:
                return MarketState.EARLY_CLOSE
            return MarketState.OPEN
        if t < time(20, 0):
            return MarketState.POST_MARKET
        return MarketState.CLOSED

    def is_market_open(self, dt: datetime | None = None) -> bool:
        return self.get_state(dt) in (MarketState.OPEN, MarketState.EARLY_CLOSE)

    def seconds_until_close(self, dt: datetime | None = None) -> float:
        dt = dt or self.now()
        close = datetime.combine(dt.date(), self.get_close_time(dt.date()), tzinfo=self.tz)
        return max(0.0, (close - dt).total_seconds())