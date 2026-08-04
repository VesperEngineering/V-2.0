from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from vesper.platform.agent_profiles import AUTONOMOUS_AGENT_ROLES
from vesper.platform.agent_queue import (
    AgentWorkQueue,
    WorkQueueConflict,
    WorkQueueRoleError,
)
from vesper.platform.contracts import (
    ApprovalDecision,
    AgentRole,
    HumanApprovalDecision,
    JournalEventType,
    RunStatus,
)
from vesper.platform.persistence import PlatformPaths, open_persistence
from vesper.platform.journals import AgentJournal
from vesper.platform.service import (
    RUN_RUNTIME_NAMESPACE,
    LocalPlatformService,
    SpecialistRuntimeUnavailable,
    _repository_lease,
)
from vesper.platform.tui.command_contracts import (
    AgentEnqueuePayload,
    ApprovalPayload,
    CommandRequest,
)
from vesper.platform.tui.command_ports import (
    DEFAULT_APPROVAL_REASON,
    DISABLED_COMMAND_REASONS,
    DisabledAgentActionPort,
    DisabledCommandPort,
    LocalPlatformCommandPort,
    deterministic_approval_id,
    deterministic_work_id,
    stable_session_id,
)
from vesper.platform.workflow import APPROVAL_DECISION_NAMESPACE


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def _command_request(
    command_id: str,
    command_type: str,
    payload,
    *,
    reason: str | None = None,
) -> CommandRequest:
    return CommandRequest(
        command_id=command_id,
        command_type=command_type,
        reviewed_control_version=1,
        reviewed_control_hash="a" * 64,
        reason=reason,
        confirmation=None,
        payload=payload,
    )


class _ApprovalController:
    def __init__(self, persistence, request_checkpoint_id: str = "checkpoint-1") -> None:
        self.persistence = persistence
        self.recorded: list[HumanApprovalDecision] = []
        self.resume_calls = 0
        self.cancel_calls = 0
        self.view = SimpleNamespace(
            checkpoint_id="checkpoint-1",
            pending_approval=SimpleNamespace(
                run_id="run-1",
                task_id="task-1",
                repository_revision="abc123",
                created_at=NOW,
                request_id="request-1",
                checkpoint_id=request_checkpoint_id,
            ),
            state=SimpleNamespace(status=RunStatus.AWAITING_APPROVAL),
        )

    def inspect(self, run_id: str):
        if run_id != "run-1":
            raise RuntimeError("run not found")
        return self.view

    def record_decision(self, run_id: str, decision: HumanApprovalDecision):
        assert run_id == "run-1"
        self.recorded.append(decision)
        self.persistence.store.put(
            APPROVAL_DECISION_NAMESPACE,
            run_id,
            decision.model_dump(mode="json"),
        )
        return decision

    def resume(self, _run_id: str):
        self.resume_calls += 1
        raise AssertionError("TUI decisions must never resume a run")

    def cancel(self, _run_id: str, _reason: str):
        self.cancel_calls += 1
        raise AssertionError("TUI decisions must never cancel a run")


class _ControllerFactory:
    def __init__(self, request_checkpoint_id: str = "checkpoint-1") -> None:
        self.request_checkpoint_id = request_checkpoint_id
        self.controllers: list[_ApprovalController] = []

    def __call__(self, persistence):
        controller = _ApprovalController(persistence, self.request_checkpoint_id)
        self.controllers.append(controller)
        return controller


def _service(tmp_path, factory: _ControllerFactory) -> LocalPlatformService:
    return LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        controller_factory=factory,
        clock=lambda: NOW,
    )


def test_deterministic_downstream_ids_are_command_bound() -> None:
    digest = hashlib.sha256(b"command:1").hexdigest()

    assert deterministic_approval_id("command:1") == f"tui-approval:{digest}"
    assert deterministic_work_id("command:1") == f"tui-work:{digest}"
    assert stable_session_id("v20-model-researcher") == stable_session_id(
        "v20-model-researcher"
    )
    assert stable_session_id("v20-model-researcher") != stable_session_id(
        "v20-portfolio-researcher"
    )


@pytest.mark.parametrize(
    ("decision", "reason", "resume_required"),
    [
        (ApprovalDecision.APPROVE, DEFAULT_APPROVAL_REASON, True),
        (ApprovalDecision.REJECT, "Evidence is incomplete.", False),
    ],
)
def test_approval_ports_record_exact_decision_without_execution(
    tmp_path,
    decision: ApprovalDecision,
    reason: str,
    resume_required: bool,
) -> None:
    factory = _ControllerFactory()
    service = _service(tmp_path, factory)
    port = LocalPlatformCommandPort(service, operator_id="operator:1", clock=lambda: NOW)

    if decision is ApprovalDecision.APPROVE:
        result = port.approve_run("command:1", "run-1", "checkpoint-1")
    else:
        result = port.reject_run(
            "command:1", "run-1", "checkpoint-1", reason=reason
        )

    recorded = factory.controllers[-1].recorded
    assert len(recorded) == 1
    assert recorded[0].approval_id == deterministic_approval_id("command:1")
    assert recorded[0].decided_at == NOW
    assert recorded[0].decision is decision
    assert recorded[0].reason == reason
    assert factory.controllers[-1].resume_calls == 0
    assert factory.controllers[-1].cancel_calls == 0
    assert result.ok is True
    assert result.result is not None
    assert result.result["resume_required"] is resume_required
    assert result.result["decision"] == decision.value


def test_approval_exact_replay_returns_existing_and_conflict_fails(tmp_path) -> None:
    factory = _ControllerFactory()
    times = iter((NOW, NOW + timedelta(seconds=1), NOW + timedelta(seconds=2)))
    port = LocalPlatformCommandPort(
        _service(tmp_path, factory), operator_id="operator:1", clock=lambda: next(times)
    )

    first = port.approve_run("command:1", "run-1", "checkpoint-1", "Reviewed.")
    replay = port.approve_run("command:1", "run-1", "checkpoint-1", "Reviewed.")

    assert replay == first
    assert sum(len(controller.recorded) for controller in factory.controllers) == 1
    with open_persistence(port._service.paths) as persistence:
        events = AgentJournal(persistence.store).list(AgentRole.RISK_REVIEW, "run-1")
    assert len(events) == 1
    with pytest.raises(SpecialistRuntimeUnavailable, match="conflicting TUI approval"):
        port.reject_run(
            "command:1",
            "run-1",
            "checkpoint-1",
            reason="Changed decision.",
        )


def test_approval_rejects_stale_checkpoint_and_active_execution_without_touching_it(
    tmp_path,
) -> None:
    factory = _ControllerFactory()
    service = _service(tmp_path, factory)
    port = LocalPlatformCommandPort(service, operator_id="operator:1", clock=lambda: NOW)

    with pytest.raises(SpecialistRuntimeUnavailable, match="exact pending checkpoint"):
        port.approve_run("command:stale", "run-1", "checkpoint-old")
    service.control.mark_active(
        run_id="run-1",
        execution_id="execution:1",
        sandbox_name="sandbox:1",
        role="v20-development",
        attempt=1,
    )
    before = service.control.active_execution("run-1")

    with pytest.raises(SpecialistRuntimeUnavailable, match="active execution"):
        port.approve_run("command:active", "run-1", "checkpoint-1")

    assert service.control.active_execution("run-1") == before
    assert sum(len(controller.recorded) for controller in factory.controllers) == 0
    with open_persistence(service.paths) as persistence:
        assert AgentJournal(persistence.store).list(AgentRole.RISK_REVIEW, "run-1") == ()


def test_approval_rejects_pending_request_checkpoint_mismatch(tmp_path) -> None:
    factory = _ControllerFactory(request_checkpoint_id="checkpoint-other")
    service = _service(tmp_path, factory)
    port = LocalPlatformCommandPort(service, operator_id="operator:1", clock=lambda: NOW)

    with pytest.raises(SpecialistRuntimeUnavailable, match="exact pending checkpoint"):
        port.approve_run("command:mismatch", "run-1", "checkpoint-1")

    assert sum(len(controller.recorded) for controller in factory.controllers) == 0
    with open_persistence(service.paths) as persistence:
        assert AgentJournal(persistence.store).list(AgentRole.RISK_REVIEW, "run-1") == ()


def test_approval_uses_non_reconciling_repository_lease(tmp_path) -> None:
    factory = _ControllerFactory()
    service = _service(tmp_path, factory)
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    with open_persistence(service.paths) as persistence:
        persistence.store.put(
            RUN_RUNTIME_NAMESPACE,
            "run-1",
            {"repository_root": str(repository)},
        )
    port = LocalPlatformCommandPort(service, operator_id="operator:1", clock=lambda: NOW)

    with _repository_lease(repository):
        with pytest.raises(
            SpecialistRuntimeUnavailable,
            match="another controller operation owns the repository lease",
        ):
            port.approve_run("command:leased", "run-1", "checkpoint-1")

    assert sum(len(controller.recorded) for controller in factory.controllers) == 0


def test_queue_retains_caller_fields_and_rejects_conflicting_replay(tmp_path) -> None:
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        queue = AgentWorkQueue(persistence.store)
        first = queue.enqueue(
            "work:1",
            AgentRole.MODEL_RESEARCHER,
            "session:1",
            "Review candidate",
            "Review candidate evidence.",
            75,
            NOW,
        )
        replay = queue.enqueue(
            "work:1",
            AgentRole.MODEL_RESEARCHER,
            "session:1",
            "Review candidate",
            "Review candidate evidence.",
            75,
            NOW,
        )

        assert replay == first
        assert first.title == "Review candidate"
        assert first.created_at == NOW
        with pytest.raises(WorkQueueConflict, match="conflicting agent work"):
            queue.enqueue(
                "work:1",
                AgentRole.MODEL_RESEARCHER,
                "session:1",
                "Changed title",
                "Review candidate evidence.",
                75,
                NOW,
            )
        with pytest.raises(WorkQueueRoleError, match="autonomous quant role"):
            queue.enqueue(
                "work:product",
                AgentRole.PRODUCT,
                "session:1",
                "Product work",
                "Unsupported queue role.",
                75,
                NOW,
            )


def test_agent_enqueue_is_bounded_deterministic_and_recoverable(tmp_path) -> None:
    factory = _ControllerFactory()
    service = _service(tmp_path, factory)
    port = LocalPlatformCommandPort(service, operator_id="operator:1", clock=lambda: NOW)
    payload = AgentEnqueuePayload(
        agent_id=AgentRole.MODEL_RESEARCHER.value,
        title="Review candidate",
        objective="Review candidate evidence.",
        priority=75,
    )
    request = _command_request("command:queue", "agent.enqueue", payload)

    assert port.recover(request.command_id, request) == "not-started"
    first = port.enqueue("command:queue", payload)
    replay = port.enqueue("command:queue", payload)

    assert replay == first
    assert first.result is not None
    assert first.result["work_id"] == deterministic_work_id("command:queue")
    assert first.result["session_id"] == stable_session_id(payload.agent_id)
    assert first.result["title"] == payload.title
    assert first.result["objective"] == payload.objective
    assert first.result["priority"] == payload.priority
    assert first.result["created_at"] == "2026-08-04T12:00:00Z"
    assert port.recover(request.command_id, request) == "completed"

    denied = payload.model_copy(update={"agent_id": AgentRole.PRODUCT.value})
    with pytest.raises(SpecialistRuntimeUnavailable, match="autonomous quant role"):
        port.enqueue("command:denied", denied)
    assert AgentRole.PRODUCT not in AUTONOMOUS_AGENT_ROLES
    denied_request = _command_request("command:denied", "agent.enqueue", denied)
    assert port.recover(denied_request.command_id, denied_request) == "unknown"


@pytest.mark.parametrize(
    "status",
    ["queued", "claimed", "completed", "cancelled", "failed"],
)
def test_agent_recovery_binds_exact_request_not_later_work_outcome(tmp_path, status) -> None:
    factory = _ControllerFactory()
    service = _service(tmp_path, factory)
    port = LocalPlatformCommandPort(service, operator_id="operator:1", clock=lambda: NOW)
    payload = AgentEnqueuePayload(
        agent_id=AgentRole.MODEL_RESEARCHER.value,
        title="Review candidate",
        objective="Review candidate evidence.",
        priority=75,
    )
    request = _command_request("command:work-outcome", "agent.enqueue", payload)
    port.enqueue(request.command_id, payload)
    work_id = deterministic_work_id(request.command_id)
    with open_persistence(service.paths) as persistence:
        item = AgentWorkQueue(persistence.store).get(work_id)
        assert item is not None
        persistence.store.put(
            ("agent-work", "items"),
            work_id,
            item.model_copy(update={"status": status}).model_dump(mode="json"),
        )
    assert port.recover(request.command_id, request) == "completed"


def test_agent_recovery_returns_unknown_for_any_request_or_evidence_mismatch(tmp_path) -> None:
    factory = _ControllerFactory()
    service = _service(tmp_path, factory)
    port = LocalPlatformCommandPort(service, operator_id="operator:1", clock=lambda: NOW)
    payload = AgentEnqueuePayload(
        agent_id=AgentRole.MODEL_RESEARCHER.value,
        title="Review candidate",
        objective="Review candidate evidence.",
        priority=75,
    )
    request = _command_request("command:bound-work", "agent.enqueue", payload)
    port.enqueue(request.command_id, payload)

    assert port.recover("command:other", request) == "unknown"
    mismatches = (
        payload.model_copy(update={"agent_id": AgentRole.PORTFOLIO_RESEARCHER.value}),
        payload.model_copy(update={"agent_id": AgentRole.PRODUCT.value}),
        payload.model_copy(update={"title": "Changed title"}),
        payload.model_copy(update={"objective": "Changed objective"}),
        payload.model_copy(update={"priority": 74}),
    )
    for changed in mismatches:
        conflicting = _command_request(request.command_id, "agent.enqueue", changed)
        assert port.recover(request.command_id, conflicting) == "unknown"
    with open_persistence(service.paths) as persistence:
        work_id = deterministic_work_id(request.command_id)
        item = AgentWorkQueue(persistence.store).get(work_id)
        assert item is not None
        persistence.store.put(
            ("agent-work", "items"),
            work_id,
            item.model_copy(update={"title": "Tampered title"}).model_dump(mode="json"),
        )
    assert port.recover(request.command_id, request) == "unknown"
    wrong_type = _command_request(
        request.command_id,
        "approval.approve",
        ApprovalPayload(run_id="run-1", checkpoint_id="checkpoint-1"),
    )
    assert port.recover(request.command_id, wrong_type) == "unknown"


def test_approval_recovery_binds_request_decision_reason_and_operator(tmp_path) -> None:
    factory = _ControllerFactory()
    service = _service(tmp_path, factory)
    port = LocalPlatformCommandPort(service, operator_id="operator:1", clock=lambda: NOW)
    payload = ApprovalPayload(run_id="run-1", checkpoint_id="checkpoint-1")
    request = _command_request("command:approval", "approval.approve", payload)

    assert port.recover(request.command_id, request) == "not-started"
    port.approve_run(request.command_id, payload.run_id, payload.checkpoint_id)
    assert port.recover(request.command_id, request) == "completed"
    assert port.recover("command:other", request) == "unknown"
    assert LocalPlatformCommandPort(
        service,
        operator_id="operator:other",
        clock=lambda: NOW,
    ).recover(request.command_id, request) == "unknown"

    mismatches = (
        _command_request(
            request.command_id,
            "approval.approve",
            payload.model_copy(update={"run_id": "run-other"}),
        ),
        _command_request(
            request.command_id,
            "approval.approve",
            payload.model_copy(update={"checkpoint_id": "checkpoint-other"}),
        ),
        _command_request(
            request.command_id,
            "approval.approve",
            payload,
            reason="Different reason.",
        ),
        _command_request(
            request.command_id,
            "approval.reject",
            payload,
            reason=DEFAULT_APPROVAL_REASON,
        ),
    )
    for conflicting in mismatches:
        assert port.recover(request.command_id, conflicting) == "unknown"
    with open_persistence(service.paths) as persistence:
        raw = persistence.store.get(APPROVAL_DECISION_NAMESPACE, payload.run_id)
        assert raw is not None
        persistence.store.put(
            APPROVAL_DECISION_NAMESPACE,
            payload.run_id,
            {**raw, "approval_id": f"tui-approval:{'0' * 64}"},
        )
    assert port.recover(request.command_id, request) == "unknown"


def test_approval_recovery_requires_the_exact_run_storage_key(tmp_path) -> None:
    factory = _ControllerFactory()
    service = _service(tmp_path, factory)
    port = LocalPlatformCommandPort(service, operator_id="operator:1", clock=lambda: NOW)
    payload = ApprovalPayload(run_id="run-1", checkpoint_id="checkpoint-1")
    request = _command_request("command:approval-key", "approval.approve", payload)
    port.approve_run(request.command_id, payload.run_id, payload.checkpoint_id)

    approval_id = deterministic_approval_id(request.command_id)
    with open_persistence(service.paths) as persistence:
        raw = persistence.store.get(APPROVAL_DECISION_NAMESPACE, payload.run_id)
        assert raw is not None
        persistence.store.delete(APPROVAL_DECISION_NAMESPACE, payload.run_id)
        persistence.store.put(APPROVAL_DECISION_NAMESPACE, "wrong-run-key", raw)
        persistence.store.delete(
            ("agent-journals", AgentRole.RISK_REVIEW.value, payload.run_id),
            f"{payload.run_id}:operator:{approval_id}",
        )

    assert port.recover(request.command_id, request) == "unknown"
    with open_persistence(service.paths) as persistence:
        assert persistence.store.get(APPROVAL_DECISION_NAMESPACE, payload.run_id) is None
        assert AgentJournal(persistence.store).list(AgentRole.RISK_REVIEW, payload.run_id) == ()


@pytest.mark.parametrize(
    ("command_type", "reason", "decision"),
    [
        ("approval.approve", "Explicit approval.", ApprovalDecision.APPROVE),
        ("approval.reject", "Evidence is incomplete.", ApprovalDecision.REJECT),
    ],
)
def test_approval_recovery_supports_explicit_reason_and_reject(
    tmp_path,
    command_type,
    reason,
    decision,
) -> None:
    factory = _ControllerFactory()
    service = _service(tmp_path, factory)
    port = LocalPlatformCommandPort(service, operator_id="operator:1", clock=lambda: NOW)
    payload = ApprovalPayload(run_id="run-1", checkpoint_id="checkpoint-1")
    request = _command_request("command:decision", command_type, payload, reason=reason)

    if decision is ApprovalDecision.APPROVE:
        port.approve_run(request.command_id, payload.run_id, payload.checkpoint_id, reason)
    else:
        port.reject_run(request.command_id, payload.run_id, payload.checkpoint_id, reason)

    assert port.recover(request.command_id, request) == "completed"


class _InjectedCrash(RuntimeError):
    pass


def _crash_after_decision_write(_persistence, _decision) -> None:
    raise _InjectedCrash("after decision write")


def test_approval_recovery_repairs_missing_journal_after_crash(tmp_path, monkeypatch) -> None:
    factory = _ControllerFactory()
    service = _service(tmp_path, factory)
    port = LocalPlatformCommandPort(service, operator_id="operator:1", clock=lambda: NOW)
    payload = ApprovalPayload(run_id="run-1", checkpoint_id="checkpoint-1")
    request = _command_request("command:crash", "approval.approve", payload)
    journal_writer = service._journal_operator_decision
    monkeypatch.setattr(service, "_journal_operator_decision", _crash_after_decision_write)

    with pytest.raises(_InjectedCrash, match="after decision write"):
        port.approve_run(request.command_id, payload.run_id, payload.checkpoint_id)
    monkeypatch.setattr(service, "_journal_operator_decision", journal_writer)
    with open_persistence(service.paths) as persistence:
        assert persistence.store.get(APPROVAL_DECISION_NAMESPACE, payload.run_id) is not None
        assert AgentJournal(persistence.store).list(AgentRole.RISK_REVIEW, payload.run_id) == ()

    mismatched = _command_request(
        request.command_id,
        request.command_type,
        payload,
        reason="Different reason.",
    )
    assert port.recover(request.command_id, mismatched) == "unknown"
    with open_persistence(service.paths) as persistence:
        assert AgentJournal(persistence.store).list(AgentRole.RISK_REVIEW, payload.run_id) == ()

    assert port.recover(request.command_id, request) == "completed"
    assert port.recover(request.command_id, request) == "completed"
    with open_persistence(service.paths) as persistence:
        journal = AgentJournal(persistence.store)
        assert len(journal.list(AgentRole.RISK_REVIEW, payload.run_id)) == 1
        assert journal.verify(AgentRole.RISK_REVIEW, payload.run_id) is True
    assert sum(len(controller.recorded) for controller in factory.controllers) == 1


def test_approval_recovery_fails_closed_on_journal_conflict(tmp_path, monkeypatch) -> None:
    factory = _ControllerFactory()
    service = _service(tmp_path, factory)
    port = LocalPlatformCommandPort(service, operator_id="operator:1", clock=lambda: NOW)
    payload = ApprovalPayload(run_id="run-1", checkpoint_id="checkpoint-1")
    request = _command_request("command:conflict", "approval.approve", payload)
    journal_writer = service._journal_operator_decision
    monkeypatch.setattr(service, "_journal_operator_decision", _crash_after_decision_write)
    with pytest.raises(_InjectedCrash):
        port.approve_run(request.command_id, payload.run_id, payload.checkpoint_id)
    monkeypatch.setattr(service, "_journal_operator_decision", journal_writer)
    decision = factory.controllers[-1].recorded[0]
    with open_persistence(service.paths) as persistence:
        journal = AgentJournal(persistence.store)
        conflicting = journal.append(
            event_id=f"{decision.run_id}:operator:{decision.approval_id}",
            role=AgentRole.RISK_REVIEW,
            session_id=decision.run_id,
            run_id=decision.run_id,
            task_id=decision.task_id,
            repository_revision=decision.repository_revision,
            created_at=decision.decided_at,
            event_type=JournalEventType.OPERATOR_DECISION,
            payload={
                "decision": ApprovalDecision.REJECT.value,
                "operator_id": decision.operator_id,
                "reason": "Conflicting event.",
            },
        )

    assert port.recover(request.command_id, request) == "failed"
    with open_persistence(service.paths) as persistence:
        events = AgentJournal(persistence.store).list(AgentRole.RISK_REVIEW, payload.run_id)
    assert len(events) == 1
    assert events[0].event_hash == conflicting.event_hash
    assert sum(len(controller.recorded) for controller in factory.controllers) == 1


def test_disabled_ports_return_exact_reason_and_have_no_legacy_target() -> None:
    assert tuple(DISABLED_COMMAND_REASONS) == (
        "alert.dismiss",
        "layout.reset",
        "approval.rework",
        "agent.send-message",
        "agent.pause",
        "agent.stop",
        "agent.retry",
        "agent.set-priority",
        "risk.propose-limit",
        "trading.pause",
        "trading.emergency-stop",
        "service.pause",
        "service.restart",
        "runtime.start",
        "runtime.stop-safe",
        "runtime.stop-force",
        "runtime.prepare-shutdown",
        "mode.switch",
        "mode.leave-live",
        "mode.enable-live",
        "model.request-promotion",
        "model.request-rollback",
        "memory.compress-now",
        "backup.create",
        "backup.restore",
        "source-control.push",
    )
    generic = DisabledCommandPort()
    for command_type, reason in DISABLED_COMMAND_REASONS.items():
        result = generic.execute("command:1", command_type)
        assert result.ok is False
        assert result.code == "capability-disabled"
        assert result.safe_message == reason
        assert result.result is None

    agent = DisabledAgentActionPort()
    assert agent.send_message("command:1", object()).safe_message == DISABLED_COMMAND_REASONS[
        "agent.send-message"
    ]
    assert agent.pause("command:1", "work:1").safe_message == DISABLED_COMMAND_REASONS[
        "agent.pause"
    ]
    assert agent.stop("command:1", object()).safe_message == DISABLED_COMMAND_REASONS[
        "agent.stop"
    ]
    assert agent.retry("command:1", "work:1").safe_message == DISABLED_COMMAND_REASONS[
        "agent.retry"
    ]
    assert agent.set_priority("command:1", object()).safe_message == DISABLED_COMMAND_REASONS[
        "agent.set-priority"
    ]
