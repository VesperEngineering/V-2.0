"""Telegram notifications for critical events."""

import json
import logging
import urllib.request
from datetime import datetime

logger = logging.getLogger("vesper.notify")


class Notifier:
    def __init__(self, config: dict):
        cfg = config.get("notifications", {})
        self.enabled = cfg.get("enabled", False)
        self.token = cfg.get("telegram_token", "")
        self.chat_id = cfg.get("telegram_chat_id", "")
        self.min_interval = cfg.get("min_interval_seconds", 60)
        self._last: dict[str, float] = {}

        if self.enabled and not self.token:
            logger.warning("Notifications enabled but no token. Disabling.")
            self.enabled = False

    def send(self, event: str, message: str, urgent: bool = False):
        if not self.enabled:
            logger.info("[NOTIFY] %s: %s", event, message)
            return

        now = datetime.utcnow().timestamp()
        if not urgent and (now - self._last.get(event, 0)) < self.min_interval:
            return
        self._last[event] = now

        icons = {
            "circuit_breaker": "\U0001f6a8",
            "crash": "\U0001f4a5",
            "eod": "\U0001f4ca",
            "start": "\U0001f7e2",
            "stop": "\U0001f534",
            "reject": "\u274c",
        }
        icon = icons.get(event, "\u2139\ufe0f")
        text = f"{icon} VESPER [{event}]\n{message}\n{datetime.now():%H:%M:%S}"

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = json.dumps({
                "chat_id": self.chat_id,
                "text": text,
            }).encode()
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logger.error("Notification failed: %s", e)

    def circuit_breaker(self, pnl: float, limit: float):
        self.send("circuit_breaker",
                  f"CIRCUIT BREAKER\nP&L: ${pnl:,.0f}\nLimit: ${limit:,.0f}\nFlattening.",
                  urgent=True)

    def eod_summary(self, s: dict):
        self.send("eod",
                  f"END OF DAY\n"
                  f"P&L: ${s.get('daily_pnl', 0):+,.0f}\n"
                  f"Exposure: ${s.get('total_exposure', 0):,.0f}\n"
                  f"Positions: {s.get('num_positions', 0)}\n"
                  f"Max DD: {s.get('max_drawdown', 0):.2%}")

    def order_rejected(self, symbol: str, reason: str):
        self.send("reject", f"REJECTED: {symbol}\n{reason}")