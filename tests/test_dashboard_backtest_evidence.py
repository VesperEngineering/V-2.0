import json

from vesper.dashboard.backtest_evidence import backtest_evidence, load_backtest_evidence


def test_backtest_evidence_surfaces_open_control_finding():
    audit = {
        "method": "Current logic mirrored exactly.",
        "window": {"start": "2026-03-24", "end": "2026-07-22", "sessions": 82},
        "final": {"return": -0.0615622},
        "broker_status_counts": {"FILLED": 36},
        "stale_snapshot_approvals": 18,
    }

    evidence = backtest_evidence(audit)

    assert evidence == {
        "status": "CONTROL FINDING OPEN",
        "window": "2026-03-24 to 2026-07-22 (82 sessions)",
        "return": -0.0615622,
        "fills": 36,
        "stale_snapshot_approvals": 18,
        "method": "Current logic mirrored exactly.",
    }


def test_backtest_evidence_is_unavailable_without_required_audit_fields():
    evidence = backtest_evidence({"final": {"return": -0.01}})

    assert evidence["status"] == "EVIDENCE UNAVAILABLE"


def test_load_backtest_evidence_reads_the_authoritative_audit(tmp_path):
    audit_path = tmp_path / "backtest_accounting_audit.json"
    audit_path.write_text(json.dumps({
        "method": "Current logic mirrored exactly.",
        "window": {"start": "2026-03-24", "end": "2026-07-22", "sessions": 82},
        "final": {"return": -0.0615622},
        "broker_status_counts": {"FILLED": 36},
        "stale_snapshot_approvals": 18,
    }), encoding="utf-8")

    assert load_backtest_evidence(audit_path)["status"] == "CONTROL FINDING OPEN"
