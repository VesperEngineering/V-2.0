"""Market-hours scheduler. Fires callbacks at open, tick, and close."""

import logging
import threading
import time
from datetime import datetime

from vesper.data.calendar import MarketCalendar, MarketState

logger = logging.getLogger("vesper.scheduler")


class MarketScheduler:
    def __init__(self, calendar: MarketCalendar, callbacks: dict,
                 refresh_seconds: int = 5):
        self.calendar = calendar
        self.callbacks = callbacks
        self.refresh_seconds = refresh_seconds
        self._running = False
        self._thread: threading.Thread | None = None
        self._state = MarketState.CLOSED

    @property
    def state(self) -> MarketState:
        return self._state

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Scheduler stopped")

    def _loop(self):
        last_state = None
        while self._running:
            now = self.calendar.now()
            state = self.calendar.get_state(now)
            self._state = state

            if state != last_state:
                self._on_transition(last_state, state, now)
                last_state = state

            if state in (MarketState.OPEN, MarketState.EARLY_CLOSE):
                cb = self.callbacks.get("on_tick")
                if cb:
                    try:
                        cb(now)
                    except Exception as e:
                        logger.error("Tick callback error: %s", e)

            time.sleep(self.refresh_seconds)

    def _on_transition(self, old, new, ts):
        logger.info("Market state: %s -> %s", old, new.value)
        if new == MarketState.PRE_MARKET:
            cb = self.callbacks.get("on_pre_market")
            if cb:
                cb(ts)
        elif new == MarketState.OPEN:
            cb = self.callbacks.get("on_market_open")
            if cb:
                cb(ts)
        elif new in (MarketState.POST_MARKET, MarketState.CLOSED):
            if old in (MarketState.OPEN, MarketState.EARLY_CLOSE):
                cb = self.callbacks.get("on_market_close")
                if cb:
                    cb(ts)