from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from vesper.platform.ops.alerts import AtomicAlertRecordStore, OperationsAlertRecord
from vesper.platform.tui.alert_dismissals import (
    AlertDismissalStore,
    AlertDismissalUnavailable,
)
from vesper.platform.tui.command_contracts import (
    AlertDismissPayload,
    CommandRequest,
    ReceiptStatus,
)
from vesper.platform.tui.command_policy import (
    CommandContext,
    EvaluatedPrerequisites,
    canonical_request_hash,
)
from vesper.platform.tui.command_registry import CommandRegistry
from vesper.platform.tui.projections.operations_status import AttentionAlertProjection
from vesper.platform.tui.snapshot import ControlStateBuilder
from vesper.platform.tui.sqlite_ledger import TuiLedger
from vesper.platform.tui.views import CapabilityState, CapabilityView, Freshness


NOW = datetime(2026, 8, 4, 18, 0, tzinfo=timezone.utc)
CONTROL_HASH = "7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43"
ALERT_ID = "alert:0123456789abcdef0123456789abcdef"


class MutableClock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **changes: int) -> datetime:
        self.now += timedelta(**changes)
        return self.now


class UnusedPlatformPort:
    def approve_run(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("alert dismissal must remain TUI-owned")

    reject_run = approve_run
    enqueue = approve_run

    def recover(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("alert dismissal must not use an external recovery port")


def _request(
    *,
    command_id: str = "client:alert-dismiss:1",
    created_at: datetime = NOW,
) -> CommandRequest:
    return CommandRequest(
        command_id=command_id,
        command_type="alert.dismiss",
        reviewed_control_version=19,
        reviewed_control_hash=CONTROL_HASH,
        reason=None,
        confirmation=None,
        payload=AlertDismissPayload(
            alert_id=ALERT_ID,
            created_at_utc=created_at,
        ),
    )


def _context(request: CommandRequest) -> CommandContext:
    return CommandContext(
        operator_id="operator:windows",
        client_id="client:console",
        authenticated=True,
        owns_control_lease=True,
        control_version=19,
        control_hash=CONTROL_HASH,
        capabilities=(
            CapabilityView(
                capability_id="alert.dismiss",
                state=CapabilityState.ENABLED,
                reason=None,
            ),
        ),
        prerequisites=EvaluatedPrerequisites(
            request_sha256=canonical_request_hash(request),
            complete=True,
            checks=(),
        ),
    )


def _write_alert(
    state_root: Path,
    *,
    created_at: datetime = NOW,
    severity: str = "urgent",
) -> None:
    AtomicAlertRecordStore(state_root).write(
        OperationsAlertRecord(
            alert_id=ALERT_ID,
            severity=severity,
            created_at_utc=created_at,
            resolved_at_utc=(created_at + timedelta(minutes=1) if severity == "resolved" else None),
        )
    )


def _runtime(
    tmp_path: Path,
    *,
    severity: str = "resolved",
) -> tuple[TuiLedger, AlertDismissalStore, CommandRegistry, MutableClock]:
    state_root = tmp_path / "state"
    _write_alert(state_root, severity=severity)
    ledger = TuiLedger(state_root / "operations.sqlite3")
    dismissals = AlertDismissalStore(ledger, state_root)
    clock = MutableClock()
    registry = CommandRegistry(
        ledger,
        UnusedPlatformPort(),
        alert_store=dismissals,
        clock=clock,
        worker_id="worker:alert-dismiss",
    )
    return ledger, dismissals, registry, clock


def test_alert_dismissal_is_atomic_durable_and_exactly_idempotent(tmp_path: Path) -> None:
    ledger, dismissals, registry, _clock = _runtime(tmp_path)
    request = _request()

    receipt = registry.execute(_context(request), request)

    assert receipt.status is ReceiptStatus.COMPLETED
    assert receipt.code == "completed"
    assert receipt.safe_message == "Alert dismissed."
    assert receipt.result == {
        "alert_id": ALERT_ID,
        "created_at_utc": "2026-08-04T18:00:00Z",
    }
    assert dismissals.is_dismissed(ALERT_ID, NOW)
    assert registry.execute(_context(request), request) == receipt
    with ledger.read() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM alert_dismissal_bindings").fetchone()[0] == 1
        )
        assert connection.execute("SELECT COUNT(*) FROM alert_dismissals").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM command_receipt_events WHERE status = 'completed'"
            ).fetchone()[0]
            == 1
        )
    registry.close()
    ledger.close()

    reopened = TuiLedger(tmp_path / "state" / "operations.sqlite3")
    reopened_store = AlertDismissalStore(reopened, tmp_path / "state")
    assert reopened_store.is_dismissed(ALERT_ID, NOW)
    reopened_store.close()
    reopened.close()


def test_urgent_alert_cannot_be_dismissed_and_remains_visible(tmp_path: Path) -> None:
    ledger, dismissals, registry, _clock = _runtime(tmp_path, severity="urgent")
    request = _request()

    capability = next(
        row for row in registry.command_capabilities if row.capability_id == "alert.dismiss"
    )
    receipt = registry.execute(_context(request), request)
    sample = AttentionAlertProjection(tmp_path / "state", dismissals=dismissals).read()

    assert capability.state is CapabilityState.DISABLED
    assert capability.reason == "Only a resolved alert can be dismissed."
    assert receipt.status is ReceiptStatus.REJECTED
    assert receipt.code == "capability-disabled"
    assert receipt.safe_message == "Only a resolved alert can be dismissed."
    assert dismissals.binding_for_command(request.command_id) is None
    assert not dismissals.is_dismissed(ALERT_ID, NOW)
    assert sample.freshness is Freshness.FRESH
    assert sample.value is not None
    assert tuple(alert.severity for alert in sample.value.alerts) == ("urgent",)
    registry.close()
    ledger.close()


def test_resolved_to_urgent_race_is_rejected_with_exact_safe_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, dismissals, registry, _clock = _runtime(tmp_path)
    request = _request()
    original_capability = registry._handler_capability

    def enable_then_reopen(command_type):
        capability = original_capability(command_type)
        _write_alert(tmp_path / "state", severity="urgent")
        return capability

    monkeypatch.setattr(registry, "_handler_capability", enable_then_reopen)

    receipt = registry.execute(_context(request), request)

    assert receipt.status is ReceiptStatus.REJECTED
    assert receipt.code == "prerequisite-failed"
    assert receipt.safe_message == "Only a resolved alert can be dismissed."
    assert dismissals.binding_for_command(request.command_id) is None
    sample = AttentionAlertProjection(tmp_path / "state", dismissals=dismissals).read()
    assert sample.value is not None
    assert tuple(alert.severity for alert in sample.value.alerts) == ("urgent",)
    registry.close()
    ledger.close()


def test_recovery_never_rebinds_or_hides_a_newer_occurrence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, dismissals, registry, clock = _runtime(tmp_path)
    request = _request()
    original_finish = registry._store.finish_in_transaction
    monkeypatch.setattr(
        registry._store,
        "finish_in_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("rollback")),
    )

    with pytest.raises(RuntimeError, match="rollback"):
        registry.execute(_context(request), request)

    binding = dismissals.binding_for_command(request.command_id)
    assert binding is not None
    assert binding.alert_id == ALERT_ID
    assert binding.created_at_utc == NOW
    assert not dismissals.is_dismissed(ALERT_ID, NOW)

    recurrence = NOW + timedelta(minutes=5)
    _write_alert(tmp_path / "state", created_at=recurrence)
    monkeypatch.setattr(registry._store, "finish_in_transaction", original_finish)

    recovered = registry.recover_running(clock.advance(seconds=31))

    assert len(recovered) == 1
    assert recovered[0].status is ReceiptStatus.COMPLETED
    assert dismissals.is_dismissed(ALERT_ID, NOW)
    assert not dismissals.is_dismissed(ALERT_ID, recurrence)
    sample = AttentionAlertProjection(tmp_path / "state", dismissals=dismissals).read()
    assert sample.freshness is Freshness.FRESH
    assert sample.value is not None
    assert tuple(alert.created_at_utc for alert in sample.value.alerts) == (recurrence,)
    assert registry.execute(_context(request), request) == recovered[0]
    registry.close()
    ledger.close()


def test_resolved_alert_reopened_with_same_id_is_rejected_before_admission(
    tmp_path: Path,
) -> None:
    ledger, dismissals, registry, _clock = _runtime(tmp_path)
    reviewed_request = _request()
    _write_alert(tmp_path / "state", severity="resolved")
    recurrence = NOW + timedelta(minutes=5)
    _write_alert(tmp_path / "state", created_at=recurrence, severity="resolved")

    receipt = registry.execute(_context(reviewed_request), reviewed_request)

    assert receipt.status is ReceiptStatus.REJECTED
    assert receipt.code == "prerequisite-failed"
    assert receipt.safe_message == "Selected alert occurrence is no longer current."
    assert dismissals.binding_for_command(reviewed_request.command_id) is None
    assert not dismissals.is_dismissed(ALERT_ID, NOW)
    assert not dismissals.is_dismissed(ALERT_ID, recurrence)
    sample = AttentionAlertProjection(tmp_path / "state", dismissals=dismissals).read()
    assert sample.freshness is Freshness.FRESH
    assert sample.value is not None
    assert tuple(alert.created_at_utc for alert in sample.value.alerts) == (recurrence,)
    registry.close()
    ledger.close()


def test_future_created_alert_uses_monotonic_completion_time_and_reopens(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    created_at = NOW + timedelta(seconds=5)
    _write_alert(state_root, created_at=created_at, severity="resolved")
    ledger_path = state_root / "operations.sqlite3"
    ledger = TuiLedger(ledger_path)
    dismissals = AlertDismissalStore(ledger, state_root)
    registry = CommandRegistry(
        ledger,
        UnusedPlatformPort(),
        alert_store=dismissals,
        clock=MutableClock(),
        worker_id="worker:alert-dismiss",
    )
    request = _request(created_at=created_at)

    receipt = registry.execute(_context(request), request)

    assert receipt.status is ReceiptStatus.COMPLETED
    assert receipt.finished_at_utc == created_at
    registry.close()
    ledger.close()

    reopened = TuiLedger(ledger_path)
    with reopened.read() as connection:
        row = connection.execute(
            "SELECT dismissed_at_utc FROM alert_dismissals WHERE command_id = ?",
            (request.command_id,),
        ).fetchone()
    assert row is not None
    assert row["dismissed_at_utc"] == "2026-08-04T18:00:05Z"
    reopened.close()


def test_dismissal_state_failure_returns_a_safe_terminal_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, dismissals, registry, _clock = _runtime(tmp_path)
    request = _request()
    monkeypatch.setattr(
        dismissals,
        "binding_for_command_in_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AlertDismissalUnavailable("private failure")
        ),
    )

    receipt = registry.execute(_context(request), request)

    assert receipt.status is ReceiptStatus.FAILED
    assert receipt.code == "manual-intervention-required"
    assert "private failure" not in receipt.safe_message
    assert not dismissals.is_dismissed(ALERT_ID, NOW)
    registry.close()
    ledger.close()


def test_binding_failure_during_admission_is_safely_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger, dismissals, registry, _clock = _runtime(tmp_path)
    request = _request()
    monkeypatch.setattr(
        dismissals,
        "bind_for_command_in_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AlertDismissalUnavailable("private failure")
        ),
    )

    receipt = registry.execute(_context(request), request)

    assert receipt.status is ReceiptStatus.REJECTED
    assert receipt.code == "prerequisite-failed"
    assert "private failure" not in receipt.safe_message
    assert dismissals.binding_for_command(request.command_id) is None
    registry.close()
    ledger.close()


@pytest.mark.parametrize("source_state", ("missing", "corrupt"))
def test_missing_or_corrupt_current_alert_fails_closed_without_binding(
    tmp_path: Path,
    source_state: str,
) -> None:
    state_root = tmp_path / source_state
    ledger = TuiLedger(state_root / "operations.sqlite3")
    if source_state == "corrupt":
        (state_root / "attention-alert.json").write_text(
            '{"private":"NVDA order detail"}',
            encoding="utf-8",
        )
    dismissals = AlertDismissalStore(ledger, state_root)
    registry = CommandRegistry(
        ledger,
        UnusedPlatformPort(),
        alert_store=dismissals,
        clock=MutableClock(),
    )
    request = _request()

    capability = next(
        row for row in registry.command_capabilities if row.capability_id == "alert.dismiss"
    )

    receipt = registry.execute(_context(request), request)

    assert capability.state is CapabilityState.DISABLED
    assert capability.reason == "Only a resolved alert can be dismissed."
    assert receipt.status is ReceiptStatus.REJECTED
    assert receipt.code == "capability-disabled"
    assert "NVDA" not in receipt.safe_message
    assert dismissals.binding_for_command(request.command_id) is None
    assert not dismissals.is_dismissed(ALERT_ID, NOW)
    assert registry.execute(_context(request), request) == receipt
    registry.close()
    ledger.close()


def test_projection_hides_only_the_exact_dismissed_occurrence_and_stays_fresh(
    tmp_path: Path,
) -> None:
    ledger, dismissals, registry, _clock = _runtime(tmp_path)
    request = _request()
    registry.execute(_context(request), request)
    _write_alert(tmp_path / "state", severity="resolved")

    hidden = AttentionAlertProjection(tmp_path / "state", dismissals=dismissals).read()

    assert hidden.freshness is Freshness.FRESH
    assert hidden.observed_at_utc == NOW + timedelta(minutes=1)
    assert hidden.error is None
    assert hidden.value is not None
    assert hidden.value.alerts == ()

    recurrence = NOW + timedelta(hours=1)
    _write_alert(tmp_path / "state", created_at=recurrence)
    visible = AttentionAlertProjection(tmp_path / "state", dismissals=dismissals).read()
    assert visible.freshness is Freshness.FRESH
    assert visible.value is not None
    assert tuple(alert.created_at_utc for alert in visible.value.alerts) == (recurrence,)
    registry.close()
    ledger.close()


def test_existing_dismissal_never_hides_an_urgent_occurrence(tmp_path: Path) -> None:
    ledger, dismissals, registry, _clock = _runtime(tmp_path)
    request = _request()
    receipt = registry.execute(_context(request), request)
    assert receipt.status is ReceiptStatus.COMPLETED

    _write_alert(tmp_path / "state", severity="urgent")
    sample = AttentionAlertProjection(tmp_path / "state", dismissals=dismissals).read()

    assert dismissals.is_dismissed(ALERT_ID, NOW)
    assert sample.freshness is Freshness.FRESH
    assert sample.value is not None
    assert tuple(alert.severity for alert in sample.value.alerts) == ("urgent",)
    registry.close()
    ledger.close()


def test_dismissal_visibility_never_changes_the_control_hash(tmp_path: Path) -> None:
    ledger, dismissals, registry, _clock = _runtime(tmp_path)
    visible = AttentionAlertProjection(tmp_path / "state").read()
    baseline = ControlStateBuilder().build({"operations.attention": visible})
    request = _request()
    registry.execute(_context(request), request)

    hidden = AttentionAlertProjection(tmp_path / "state", dismissals=dismissals).read()
    after = ControlStateBuilder().build(
        {"operations.attention": hidden},
        previous=baseline,
    )

    assert hidden.value is not None and hidden.value.alerts == ()
    assert after == baseline
    registry.close()
    ledger.close()
