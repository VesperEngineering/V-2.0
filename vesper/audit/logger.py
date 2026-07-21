"""Append-only JSON-lines audit trail for every signal, order, and risk event."""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("vesper.audit")


class AuditLogger:
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._file = None
        self._date = None

    def _get_file(self, ts: datetime):
        d = ts.date()
        if d != self._date:
            if self._file:
                self._file.close()
            path = self.log_dir / f"audit_{d.isoformat()}.jsonl"
            self._file = open(path, "a")
            self._date = d
        return self._file

    def _write(self, entry: dict):
        f = self._get_file(datetime.utcnow())
        f.write(json.dumps(entry, default=str) + "\n")
        f.flush()

    def log_signal(self, signal, risk_result=None):
        e = {
            "type": "signal",
            "ts": datetime.utcnow().isoformat(),
            "symbol": signal.symbol,
            "action": signal.action.value,
            "strength": signal.strength,
            "reason": signal.reason,
        }
        if risk_result:
            e["risk_approved"] = risk_result.approved
            e["risk_reason"] = risk_result.reason
        self._write(e)

    def log_order(self, order):
        self._write({
            "type": "order",
            "ts": datetime.utcnow().isoformat(),
            "id": order.id,
            "symbol": order.symbol,
            "side": order.side.value,
            "qty": order.qty,
            "status": order.status.value,
            "filled_qty": order.filled_qty,
            "fill_price": order.avg_fill_price,
        })

    def log_risk_event(self, event: str, details: dict):
        self._write({
            "type": "risk",
            "ts": datetime.utcnow().isoformat(),
            "event": event,
            "details": details,
        })

    def log_session(self, event: str, details: dict | None = None):
        self._write({
            "type": "session",
            "ts": datetime.utcnow().isoformat(),
            "event": event,
            "details": details or {},
        })

    def close(self):
        if self._file:
            self._file.close()