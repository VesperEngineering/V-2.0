"""Read-only backtest-audit data for the dashboard."""

import json
from pathlib import Path


def load_backtest_evidence(path: Path) -> dict:
    try:
        return backtest_evidence(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {"status": "EVIDENCE UNAVAILABLE"}


def backtest_evidence(audit: dict) -> dict:
    window = audit.get("window", {})
    final = audit.get("final", {})
    start = window.get("start")
    end = window.get("end")
    sessions = window.get("sessions")
    result = final.get("return")
    fills = audit.get("broker_status_counts", {}).get("FILLED")
    stale_approvals = audit.get("stale_snapshot_approvals")
    method = audit.get("method")
    if not all(isinstance(value, (int, float)) for value in
               (sessions, result, fills, stale_approvals)) or not all(isinstance(value, str) for value in
                                                                  (start, end, method)):
        return {"status": "EVIDENCE UNAVAILABLE"}
    return {
        "status": "CONTROL FINDING OPEN" if stale_approvals else "CONTROL CHECK CLEAR",
        "window": f"{start} to {end} ({sessions} sessions)",
        "return": result,
        "fills": fills,
        "stale_snapshot_approvals": stale_approvals,
        "method": method,
    }
