from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from vesper.platform.tui.command_contracts import (
    COMMAND_SPECS,
    CommandRequest,
    ConfirmationProof,
    ReceiptStatus,
)
from vesper.platform.tui.command_policy import (
    CommandContext,
    EvaluatedPrerequisites,
    canonical_request_hash,
)
from vesper.platform.tui.command_ports import (
    DISABLED_COMMAND_REASONS,
    PortResult,
)
from vesper.platform.tui.command_registry import CommandRegistry
from vesper.platform.tui.command_store import (
    CommandClaimError,
    CommandConflict,
    CommandStore,
)
from vesper.platform.tui.notes import NoteStore, NoteTarget
from vesper.platform.tui.operator_decisions import OperatorDecisionStore
from vesper.platform.tui.sqlite_ledger import LedgerCorruptionError
from vesper.platform.tui.views import CapabilityState, CapabilityView


NOW = datetime(2026, 8, 4, 14, 0, tzinfo=timezone.utc)
CONTROL_HASH = "7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43"
HANDLED = {
    "note.add",
    "approval.approve",
    "approval.hold",
    "approval.reject",
    "agent.enqueue",
}
PAYLOADS: dict[str, dict[str, object]] = {
    "note.add": {
        "target_type": "stock",
        "target_id": "AAPL",
        "body": "Review concentration.",
        "visibility": "private",
    },
    "alert.dismiss": {"alert_id": "alert:1"},
    "layout.reset": {"screen": None},
    "approval.approve": {"run_id": "run:1", "checkpoint_id": "checkpoint:1"},
    "approval.hold": {"run_id": "run:1", "checkpoint_id": "checkpoint:1"},
    "approval.reject": {"run_id": "run:1", "checkpoint_id": "checkpoint:1"},
    "approval.rework": {
        "run_id": "run:1",
        "checkpoint_id": "checkpoint:1",
        "evidence_ids": ["evidence:1"],
    },
    "agent.send-message": {"agent_id": "v20-risk-review", "text": "Review."},
    "agent.enqueue": {
        "agent_id": "v20-model-researcher",
        "title": "Review candidate",
        "objective": "Review candidate evidence.",
        "priority": 75,
    },
    "agent.pause": {"work_id": "work:1"},
    "agent.stop": {"work_id": "work:1", "workflow_run_id": None},
    "agent.retry": {"work_id": "work:1"},
    "agent.set-priority": {"work_id": "work:1", "priority": 75},
    "risk.propose-limit": {
        "limit_id": "limit:1",
        "proposed_value": "0.05",
        "evidence_ids": ["evidence:1"],
    },
    "trading.pause": {},
    "trading.emergency-stop": {},
    "service.pause": {"service_id": "service:qwen"},
    "service.restart": {"service_id": "service:qwen"},
    "runtime.start": {"mode": "paper", "activation_receipt_id": "receipt:1"},
    "runtime.stop-safe": {},
    "runtime.stop-force": {},
    "runtime.prepare-shutdown": {},
    "mode.switch": {"target_mode": "shadow"},
    "mode.leave-live": {"target_mode": "paper"},
    "mode.enable-live": {"desired_portfolio_id": "portfolio:1"},
    "model.request-promotion": {
        "candidate_id": "candidate:1",
        "evidence_ids": ["evidence:1"],
    },
    "model.request-rollback": {
        "candidate_id": "candidate:1",
        "evidence_ids": ["evidence:1"],
    },
    "memory.compress-now": {"agent_id": "v20-risk-review"},
    "backup.create": {"destination": "C:\\backups\\v20.zip"},
    "backup.restore": {
        "archive": "C:\\backups\\v20.zip",
        "preview_hash": CONTROL_HASH,
        "safety_backup_receipt_id": "receipt:backup",
    },
    "source-control.push": {"expected_revision": "a" * 40},
}


class MutableClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **changes: int) -> datetime:
        self.now += timedelta(**changes)
        return self.now


class PortSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.recovery_calls: list[tuple[str, CommandRequest]] = []
        self.effects: dict[str, dict[str, object]] = {}
        self.recovery: dict[str, str] = {}
        self.raise_after_effect: set[str] = set()
        self.result_override: dict[str, object] | None = None

    def approve_run(
        self,
        command_id: str,
        run_id: str,
        checkpoint_id: str,
        reason: str | None = None,
    ) -> PortResult:
        result = {
            "decision": "approve",
            "resume_required": True,
            "run_id": run_id,
            "checkpoint_id": checkpoint_id,
            "reason": reason,
        }
        return self._record("approval.approve", command_id, result)

    def reject_run(
        self,
        command_id: str,
        run_id: str,
        checkpoint_id: str,
        reason: str,
    ) -> PortResult:
        result = {
            "decision": "reject",
            "resume_required": False,
            "run_id": run_id,
            "checkpoint_id": checkpoint_id,
            "reason": reason,
        }
        return self._record("approval.reject", command_id, result)

    def enqueue(self, command_id: str, payload: object) -> PortResult:
        result = {
            "work_id": f"work:{command_id}",
            "agent_id": payload.agent_id,
            "priority": payload.priority,
        }
        return self._record("agent.enqueue", command_id, result)

    def recover(self, command_id: str, request: CommandRequest) -> str:
        self.recovery_calls.append((command_id, request))
        return self.recovery.get(
            command_id,
            "completed" if command_id in self.effects else "not-started",
        )

    def _record(
        self,
        command_type: str,
        command_id: str,
        result: dict[str, object],
    ) -> PortResult:
        self.calls.append((command_type, command_id))
        selected = result if self.result_override is None else self.result_override
        self.effects[command_id] = selected
        if command_id in self.raise_after_effect:
            raise RuntimeError("crash after external effect")
        return PortResult(
            ok=True,
            code="completed",
            safe_message="External effect completed.",
            result=selected,
        )


def _spec(command_type: str):
    return next(spec for spec in COMMAND_SPECS if spec.command_type == command_type)


def _request(
    command_type: str,
    *,
    command_id: str | None = None,
    reason: str | None = None,
) -> CommandRequest:
    spec = _spec(command_type)
    selected_reason = reason
    if selected_reason is None and spec.reason_rule == "required":
        selected_reason = "Reviewed rationale."
    confirmation = None
    if spec.confirmation_level == "confirm":
        confirmation = ConfirmationProof(first_confirmed=True)
    elif spec.confirmation_level == "double-confirm":
        confirmation = ConfirmationProof(
            first_confirmed=True,
            second_confirmed=True,
            bound_preview_hash=(
                CONTROL_HASH if command_type == "backup.restore" else None
            ),
        )
    elif spec.confirmation_level == "typed-live":
        confirmation = ConfirmationProof(
            first_confirmed=True,
            typed_text="ENABLE LIVE",
        )
    return CommandRequest.model_validate(
        {
            "command_id": command_id or f"client:registry:{command_type}",
            "command_type": command_type,
            "reviewed_control_version": 19,
            "reviewed_control_hash": CONTROL_HASH,
            "reason": selected_reason,
            "confirmation": (
                None if confirmation is None else confirmation.model_dump(mode="json")
            ),
            "payload": PAYLOADS[command_type],
        }
    )


def _context(
    request: CommandRequest,
    *,
    control_version: int = 19,
    capability_state: CapabilityState = CapabilityState.ENABLED,
) -> CommandContext:
    request_hash = canonical_request_hash(request)
    return CommandContext(
        operator_id="operator:windows",
        client_id="client:console",
        authenticated=True,
        owns_control_lease=True,
        control_version=control_version,
        control_hash=CONTROL_HASH,
        capabilities=(
            CapabilityView(
                capability_id=request.command_type,
                state=capability_state,
                reason=(
                    None
                    if capability_state is CapabilityState.ENABLED
                    else DISABLED_COMMAND_REASONS[request.command_type]
                ),
            ),
        ),
        prerequisites=EvaluatedPrerequisites(
            request_sha256=request_hash,
            complete=True,
            checks=(),
        ),
    )


def _registry(database, port: PortSpy, clock: MutableClock) -> CommandRegistry:
    return CommandRegistry(
        database,
        port,
        clock=clock,
        worker_id="worker:registry",
        claim_lease=timedelta(seconds=10),
    )


def test_note_add_is_atomic_deterministic_and_uses_context_operator(tmp_path) -> None:
    database = tmp_path / "registry.db"
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(database, port, clock)
    request = _request("note.add")

    receipt = registry.execute(_context(request), request)

    digest = hashlib.sha256(request.command_id.encode("ascii")).hexdigest()
    assert receipt.status is ReceiptStatus.COMPLETED
    assert receipt.result == {"note_id": f"note:command:{digest}"}
    notes = NoteStore(registry.ledger)
    stored = notes.list(NoteTarget(target_type="stock", target_id="AAPL"))
    assert len(stored) == 1
    assert stored[0].note_id == receipt.result["note_id"]
    assert stored[0].author == "operator:windows"
    assert port.calls == []
    notes.close()
    registry.close()


def test_hold_is_atomic_and_retains_pending_approval_as_tui_decision(tmp_path) -> None:
    port = PortSpy()
    registry = _registry(tmp_path / "registry.db", port, MutableClock())
    request = _request("approval.hold")

    receipt = registry.execute(_context(request), request)

    decisions = OperatorDecisionStore(registry.ledger)
    decision = decisions.get(request.command_id)
    assert decision is not None
    assert decision.run_id == "run:1"
    assert decision.checkpoint_id == "checkpoint:1"
    assert decision.operator_id == "operator:windows"
    assert decision.reason == request.reason
    assert receipt.result == {"decision_id": decision.decision_id}
    assert port.calls == []
    decisions.close()
    registry.close()


@pytest.mark.parametrize(
    ("command_type", "expected_method", "resume_required"),
    (
        ("approval.approve", "approval.approve", True),
        ("approval.reject", "approval.reject", False),
        ("agent.enqueue", "agent.enqueue", None),
    ),
)
def test_external_handlers_call_exactly_one_port_and_preserve_result(
    tmp_path,
    command_type: str,
    expected_method: str,
    resume_required: bool | None,
) -> None:
    port = PortSpy()
    registry = _registry(tmp_path / f"{command_type}.db", port, MutableClock())
    request = _request(command_type)

    receipt = registry.execute(_context(request), request)

    assert port.calls == [(expected_method, request.command_id)]
    assert receipt.status is ReceiptStatus.COMPLETED
    assert receipt.safe_message == "External effect completed."
    assert receipt.result == port.effects[request.command_id]
    if resume_required is not None:
        assert receipt.result["resume_required"] is resume_required
    registry.close()


def test_other_26_commands_are_safe_durable_rejections_with_zero_port_calls(
    tmp_path,
) -> None:
    assert set(DISABLED_COMMAND_REASONS) == {
        spec.command_type for spec in COMMAND_SPECS if spec.command_type not in HANDLED
    }
    database = tmp_path / "registry.db"
    port = PortSpy()
    registry = _registry(database, port, MutableClock())

    for index, (command_type, reason) in enumerate(DISABLED_COMMAND_REASONS.items()):
        request = _request(command_type, command_id=f"client:disabled:{index}")
        receipt = registry.execute(
            _context(request, capability_state=CapabilityState.DISABLED),
            request,
        )
        assert receipt.status is ReceiptStatus.REJECTED
        assert receipt.code == "capability-disabled"
        assert receipt.safe_message == reason

    assert port.calls == []
    assert port.recovery_calls == []
    with registry.ledger.read() as connection:
        rows = connection.execute(
            "SELECT handler_key, accepted_request_json, result_json FROM commands"
        ).fetchall()
    assert len(rows) == 26
    assert all(tuple(row) == (None, None, None) for row in rows)
    registry.close()


def test_missing_handler_fails_closed_if_capability_is_incorrectly_enabled(
    tmp_path,
) -> None:
    port = PortSpy()
    registry = _registry(tmp_path / "registry.db", port, MutableClock())
    request = _request("trading.pause")

    receipt = registry.execute(_context(request), request)

    assert receipt.status is ReceiptStatus.REJECTED
    assert receipt.code == "capability-disabled"
    assert receipt.safe_message == DISABLED_COMMAND_REASONS["trading.pause"]
    assert port.calls == []
    registry.close()


def test_stale_request_is_rejected_before_any_port_call(tmp_path) -> None:
    port = PortSpy()
    registry = _registry(tmp_path / "registry.db", port, MutableClock())
    request = _request("approval.approve")

    receipt = registry.execute(_context(request, control_version=18), request)

    assert receipt.status is ReceiptStatus.REJECTED
    assert receipt.code == "stale-state"
    assert port.calls == []
    registry.close()


def test_terminal_replay_is_exact_and_changed_request_conflicts(tmp_path) -> None:
    port = PortSpy()
    registry = _registry(tmp_path / "registry.db", port, MutableClock())
    request = _request("approval.approve")
    context = _context(request)

    first = registry.execute(context, request)
    assert registry.execute(context, request) == first
    changed = _request(
        "approval.approve",
        command_id=request.command_id,
        reason="Changed reason.",
    )
    with pytest.raises(CommandConflict):
        registry.execute(_context(changed), changed)
    assert port.calls == [("approval.approve", request.command_id)]
    registry.close()


def test_nonexpired_running_replay_never_reissues_external_effect(tmp_path) -> None:
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(tmp_path / "registry.db", port, clock)
    request = _request("approval.approve")
    context = _context(request)
    port.raise_after_effect.add(request.command_id)

    with pytest.raises(RuntimeError, match="after external effect"):
        registry.execute(context, request)
    running = registry.execute(context, request)

    assert running.status is ReceiptStatus.RUNNING
    assert port.calls == [("approval.approve", request.command_id)]
    registry.close()


def test_slow_external_effect_cannot_finish_with_a_pre_effect_lease_time(
    tmp_path,
    monkeypatch,
) -> None:
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(tmp_path / "registry.db", port, clock)
    request = _request("approval.approve")
    original = port.approve_run

    def slow_approve(command_id, run_id, checkpoint_id, reason=None):
        result = original(command_id, run_id, checkpoint_id, reason)
        clock.advance(seconds=11)
        return result

    monkeypatch.setattr(port, "approve_run", slow_approve)
    with pytest.raises(CommandClaimError, match="expired"):
        registry.execute(_context(request), request)

    assert port.calls == [("approval.approve", request.command_id)]
    recovered = registry.recover_running(clock.now)
    assert recovered[0].status is ReceiptStatus.COMPLETED
    assert port.calls == [("approval.approve", request.command_id)]
    registry.close()


def test_delayed_hold_samples_time_inside_the_decision_transaction(
    tmp_path,
    monkeypatch,
) -> None:
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(tmp_path / "registry.db", port, clock)
    request = _request("approval.hold")
    original = registry._decisions.hold

    def delayed_hold(*args, **kwargs):
        clock.advance(seconds=11)
        return original(*args, **kwargs)

    monkeypatch.setattr(registry._decisions, "hold", delayed_hold)
    with pytest.raises(CommandClaimError, match="expired"):
        registry.execute(_context(request), request)
    decisions = OperatorDecisionStore(registry.ledger)
    assert decisions.get(request.command_id) is None
    decisions.close()

    monkeypatch.setattr(registry._decisions, "hold", original)
    recovered = registry.recover_running(clock.now)
    assert recovered[0].status is ReceiptStatus.COMPLETED
    registry.close()


def test_recovery_rejects_a_mismatched_persisted_handler_binding(
    tmp_path,
    monkeypatch,
) -> None:
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(tmp_path / "registry.db", port, clock)
    request = _request("approval.approve")
    original_claim = registry._store.claim
    monkeypatch.setattr(
        registry._store,
        "claim",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("before claim")),
    )
    with pytest.raises(RuntimeError, match="before claim"):
        registry.execute(_context(request), request)
    monkeypatch.setattr(registry._store, "claim", original_claim)
    original_get = registry._store.get_accepted
    accepted = original_get(request.command_id)
    assert accepted is not None
    monkeypatch.setattr(
        registry._store,
        "get_accepted",
        lambda _command_id: accepted.model_copy(update={"handler_key": "approval.reject"}),
    )

    with pytest.raises(LedgerCorruptionError, match="handler binding"):
        registry.recover_running(clock.advance(seconds=1))

    assert port.calls == []
    assert port.recovery_calls == []
    registry.close()


def test_recovery_claims_accepted_then_executes_not_started_once(
    tmp_path,
    monkeypatch,
) -> None:
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(tmp_path / "registry.db", port, clock)
    request = _request("approval.approve")
    original_claim = registry._store.claim
    monkeypatch.setattr(
        registry._store,
        "claim",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("before claim")),
    )
    with pytest.raises(RuntimeError, match="before claim"):
        registry.execute(_context(request), request)
    monkeypatch.setattr(registry._store, "claim", original_claim)

    recovered = registry.recover_running(clock.advance(seconds=1))

    assert len(recovered) == 1
    assert recovered[0].status is ReceiptStatus.COMPLETED
    assert port.calls == [("approval.approve", request.command_id)]
    assert port.recovery_calls == [(request.command_id, request)]
    registry.close()


def test_recovery_reclaims_crash_after_claim_before_handler(
    tmp_path,
    monkeypatch,
) -> None:
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(tmp_path / "registry.db", port, clock)
    request = _request("approval.reject")
    original = registry._execute_claimed
    monkeypatch.setattr(
        registry,
        "_execute_claimed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("after claim before handler")
        ),
    )
    with pytest.raises(RuntimeError, match="after claim"):
        registry.execute(_context(request), request)
    monkeypatch.setattr(registry, "_execute_claimed", original)

    recovered = registry.recover_running(clock.advance(seconds=10))

    assert recovered[0].status is ReceiptStatus.COMPLETED
    assert port.calls == [("approval.reject", request.command_id)]
    registry.close()


def test_recovery_after_external_effect_finishes_without_reissue(tmp_path) -> None:
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(tmp_path / "registry.db", port, clock)
    request = _request("agent.enqueue")
    port.raise_after_effect.add(request.command_id)

    with pytest.raises(RuntimeError, match="after external effect"):
        registry.execute(_context(request), request)
    port.raise_after_effect.clear()
    recovered = registry.recover_running(clock.advance(seconds=10))

    assert recovered[0].status is ReceiptStatus.COMPLETED
    assert recovered[0].result is None
    assert port.calls == [("agent.enqueue", request.command_id)]
    assert port.recovery_calls == [(request.command_id, request)]
    registry.close()


def test_crash_before_finish_recovers_completed_effect_without_reissue(
    tmp_path,
    monkeypatch,
) -> None:
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(tmp_path / "registry.db", port, clock)
    request = _request("approval.approve")
    original_finish = registry._store.finish
    monkeypatch.setattr(
        registry._store,
        "finish",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("before finish")),
    )
    with pytest.raises(RuntimeError, match="before finish"):
        registry.execute(_context(request), request)
    monkeypatch.setattr(registry._store, "finish", original_finish)

    recovered = registry.recover_running(clock.advance(seconds=10))

    assert recovered[0].status is ReceiptStatus.COMPLETED
    assert port.calls == [("approval.approve", request.command_id)]
    registry.close()


def test_crash_after_finish_replays_terminal_without_reissue(tmp_path, monkeypatch) -> None:
    port = PortSpy()
    registry = _registry(tmp_path / "registry.db", port, MutableClock())
    request = _request("approval.approve")
    context = _context(request)
    original_finish = registry._store.finish

    def finish_then_crash(*args, **kwargs):
        original_finish(*args, **kwargs)
        raise RuntimeError("after finish")

    monkeypatch.setattr(registry._store, "finish", finish_then_crash)
    with pytest.raises(RuntimeError, match="after finish"):
        registry.execute(context, request)
    monkeypatch.setattr(registry._store, "finish", original_finish)

    receipt = registry.execute(context, request)

    assert receipt.status is ReceiptStatus.COMPLETED
    assert port.calls == [("approval.approve", request.command_id)]
    registry.close()


def test_unknown_recovery_requires_manual_intervention_and_never_retries(
    tmp_path,
) -> None:
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(tmp_path / "registry.db", port, clock)
    request = _request("approval.approve")
    context = _context(request)
    port.raise_after_effect.add(request.command_id)
    with pytest.raises(RuntimeError):
        registry.execute(context, request)
    port.raise_after_effect.clear()
    port.recovery[request.command_id] = "unknown"

    recovered = registry.recover_running(clock.advance(seconds=10))

    assert recovered[0].status is ReceiptStatus.FAILED
    assert recovered[0].code == "manual-intervention-required"
    assert 1 <= len(recovered[0].safe_message) <= 512
    assert registry.recover_running(clock.advance(minutes=1)) == ()
    assert registry.execute(context, request) == recovered[0]
    assert port.calls == [("approval.approve", request.command_id)]
    assert len(port.recovery_calls) == 1
    registry.close()


@pytest.mark.parametrize("recovery_status", ("completed", "failed"))
def test_recovery_terminal_states_never_reissue(
    tmp_path,
    monkeypatch,
    recovery_status: str,
) -> None:
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(tmp_path / f"{recovery_status}.db", port, clock)
    request = _request("approval.reject")
    original_claim = registry._store.claim
    monkeypatch.setattr(
        registry._store,
        "claim",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("before claim")),
    )
    with pytest.raises(RuntimeError):
        registry.execute(_context(request), request)
    monkeypatch.setattr(registry._store, "claim", original_claim)
    port.recovery[request.command_id] = recovery_status

    receipt = registry.recover_running(clock.advance(seconds=1))[0]

    assert receipt.status.value == recovery_status
    assert port.calls == []
    registry.close()


@pytest.mark.parametrize("command_type", ("note.add", "approval.hold"))
def test_local_effect_rolls_back_with_terminal_receipt(
    tmp_path,
    monkeypatch,
    command_type: str,
) -> None:
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(tmp_path / f"{command_type}.db", port, clock)
    request = _request(command_type)
    context = _context(request)
    command_store = (
        registry._store
        if command_type == "note.add"
        else registry._decisions._commands
    )
    original_finish = command_store.finish_in_transaction
    monkeypatch.setattr(
        command_store,
        "finish_in_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("rollback")),
    )
    with pytest.raises(RuntimeError, match="rollback"):
        registry.execute(context, request)
    monkeypatch.setattr(command_store, "finish_in_transaction", original_finish)

    if command_type == "note.add":
        notes = NoteStore(registry.ledger)
        assert notes.list(NoteTarget(target_type="stock", target_id="AAPL")) == ()
        notes.close()
    else:
        decisions = OperatorDecisionStore(registry.ledger)
        assert decisions.get(request.command_id) is None
        decisions.close()
    recovered = registry.recover_running(clock.advance(seconds=10))
    assert recovered[0].status is ReceiptStatus.COMPLETED
    registry.close()


def test_recovery_processes_admission_order(tmp_path, monkeypatch) -> None:
    port = PortSpy()
    clock = MutableClock()
    registry = _registry(tmp_path / "registry.db", port, clock)
    requests = (
        _request("approval.approve", command_id="client:ordered:1"),
        _request("approval.reject", command_id="client:ordered:2"),
    )
    original_claim = registry._store.claim
    monkeypatch.setattr(
        registry._store,
        "claim",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("before claim")),
    )
    for request in requests:
        with pytest.raises(RuntimeError):
            registry.execute(_context(request), request)
    monkeypatch.setattr(registry._store, "claim", original_claim)

    recovered = registry.recover_running(clock.advance(seconds=1))

    assert [row.command_id for row in recovered] == [row.command_id for row in requests]
    assert [row[0] for row in port.recovery_calls] == [row.command_id for row in requests]
    registry.close()


@pytest.mark.parametrize(
    "invalid_result",
    ({"bad": object()}, {"too_large": "x" * (64 * 1024)}),
)
def test_external_results_must_be_bounded_command_json(tmp_path, invalid_result) -> None:
    port = PortSpy()
    registry = _registry(tmp_path / "registry.db", port, MutableClock())
    request = _request("agent.enqueue")
    port.result_override = invalid_result

    with pytest.raises((TypeError, ValueError)):
        registry.execute(_context(request), request)

    store = CommandStore(registry.ledger)
    assert store.get(request.command_id).status is ReceiptStatus.RUNNING
    store.close()
    registry.close()
