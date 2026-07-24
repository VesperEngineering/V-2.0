"""Crash recovery. Saves state every tick, reconciles with broker on restart."""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("vesper.state")

STATE_FILE = Path("data/engine_state.json")


class StateManager:
    def __init__(self, path: Path = STATE_FILE):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, engine):
        state = {
            "ts": datetime.utcnow().isoformat(),
            "session_date": str(engine.risk_monitor._session_date),
            "daily_pnl": engine.risk_monitor.daily_pnl,
            "starting_equity": engine.risk_monitor.starting_equity,
            "peak_equity": engine.risk_monitor.peak_equity,
            "breaker_tripped": engine.circuit_breaker.is_tripped,
            "positions": {
                sym: {"qty": p.qty, "entry": p.avg_entry_price, "price": p.current_price}
                for sym, p in engine.broker.get_positions().items()
            },
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, default=str))
        tmp.rename(self.path)

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text())
        except Exception as e:
            logger.error("Failed to load state: %s", e)
            return None

    def reconcile(self, engine) -> dict:
        saved = self.load()
        broker_pos = engine.broker.get_positions()
        report = {"action": "none", "details": []}

        if saved is None:
            if broker_pos:
                report["action"] = "adopt_broker"
                report["details"].append(
                    f"No saved state. Broker has {len(broker_pos)} positions. Adopting."
                )
            return report

        saved_syms = set(saved.get("positions", {}).keys())
        broker_syms = set(broker_pos.keys())

        orphaned = broker_syms - saved_syms
        if orphaned:
            report["action"] = "reconcile"
            report["details"].append(f"Orphaned positions (keeping): {orphaned}")

        ghost = saved_syms - broker_syms
        if ghost:
            report["action"] = "reconcile"
            report["details"].append(f"Ghost positions (removing): {ghost}")

        if saved.get("session_date") == str(datetime.now().date()):
            engine.risk_monitor.starting_equity = saved.get("starting_equity", 0)
            engine.risk_monitor.peak_equity = saved.get("peak_equity", 0)
            engine.risk_monitor.daily_pnl = saved.get("daily_pnl", 0)
            if saved.get("breaker_tripped"):
                engine.circuit_breaker._tripped = True
                engine.circuit_breaker._trip_date = datetime.now().date()
            report["details"].append("Restored risk state from saved session.")

        return report

    def clear(self):
        if self.path.exists():
            self.path.unlink()
            logger.info("State cleared (end of day)")