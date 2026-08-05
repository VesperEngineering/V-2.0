from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.contracts import AgentRole
from vesper.platform.tui.command_contracts import (
    COMMAND_SPECS,
    AgentEnqueuePayload,
    ApprovalPayload,
    CommandMessagePayload,
    CommandReceiptPayload,
    CommandRequest,
    ConfirmationProof,
    EmptyPayload,
    NoteAddPayload,
    ReceiptStatus,
)
from vesper.platform.tui.command_ports import DISABLED_COMMAND_REASONS, PortResult
from vesper.platform.tui.command_registry import CommandRegistry
from vesper.platform.tui.command_store import CommandStore
from vesper.platform.tui.contracts import (
    CapabilityState,
    Freshness,
    MessageType,
    ProtocolErrorPayload,
    WireEnvelope,
    decode_payload,
)
from vesper.platform.tui.gateway import Gateway
from vesper.platform.tui.notes import NoteStore, NoteTarget
from vesper.platform.tui.ports import PlatformRuntimeFacts, SourceSample
from vesper.platform.tui.views import AgentCard, ApprovalRow, ConsoleSnapshot, PortfolioRow


NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)
HANDLED = {
    "note.add",
    "layout.reset",
    "approval.approve",
    "approval.hold",
    "approval.reject",
    "agent.enqueue",
}


class _Port:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def approve_run(
        self,
        command_id: str,
        run_id: str,
        checkpoint_id: str,
        reason: str | None = None,
    ) -> PortResult:
        del run_id, checkpoint_id, reason
        self.calls.append(("approval.approve", command_id))
        return PortResult(True, "completed", "Decision recorded.")

    def reject_run(
        self,
        command_id: str,
        run_id: str,
        checkpoint_id: str,
        reason: str,
    ) -> PortResult:
        del run_id, checkpoint_id, reason
        self.calls.append(("approval.reject", command_id))
        return PortResult(True, "completed", "Decision recorded.")

    def enqueue(self, command_id: str, payload: object) -> PortResult:
        del payload
        self.calls.append(("agent.enqueue", command_id))
        return PortResult(True, "completed", "Agent work queued.")

    def recover(self, command_id: str, request: object) -> str:
        del command_id, request
        return "not-started"


class _ExplodingPort(_Port):
    def enqueue(self, command_id: str, payload: object) -> PortResult:
        del payload
        self.calls.append(("agent.enqueue", command_id))
        raise RuntimeError("sensitive downstream detail")


class _RuntimeReader:
    def __init__(self, sample: SourceSample[PlatformRuntimeFacts]) -> None:
        self.sample = sample
        self.failure: Exception | None = None
        self.read_count = 0

    def read(self) -> SourceSample[PlatformRuntimeFacts]:
        self.read_count += 1
        if self.failure is not None:
            raise self.failure
        return self.sample


def _runtime_sample(
    *,
    pending_approvals: tuple[ApprovalRow, ...] = (),
    active_work: tuple[AgentCard, ...] = (),
) -> SourceSample[PlatformRuntimeFacts]:
    return SourceSample[PlatformRuntimeFacts](
        value=PlatformRuntimeFacts(
            pending_approvals=pending_approvals,
            active_work=active_work,
        ),
        freshness=Freshness.FRESH,
        observed_at_utc=NOW,
        source="native platform runtime",
        error=None,
    )


def _unavailable_runtime_sample() -> SourceSample[PlatformRuntimeFacts]:
    return SourceSample[PlatformRuntimeFacts](
        value=None,
        freshness=Freshness.UNAVAILABLE,
        observed_at_utc=None,
        source="native platform runtime",
        error="Native platform runtime state is unavailable.",
    )


def _governed_gateway(
    tmp_path: Path,
    registry: CommandRegistry,
    *,
    runtime: _RuntimeReader | None = None,
    state_name: str = "auth",
    sid: str = "S-1-5-5-1-2",
) -> Gateway:
    return Gateway(
        tmp_path / state_name,
        clock=lambda: NOW,
        command_registry=registry,
        platform_runtime_reader=runtime or _RuntimeReader(_runtime_sample()),
        logon_sid_provider=lambda: sid,
    )


def _envelope(
    message_type: MessageType,
    sequence: int,
    payload: dict[str, object],
) -> WireEnvelope:
    return WireEnvelope(
        schema_version=1,
        message_id=f"client:{sequence}",
        sequence=sequence,
        state_version=0,
        timestamp_utc=NOW,
        message_type=message_type,
        payload=payload,
    )


def _send(
    gateway: Gateway,
    message_type: MessageType,
    sequence: int,
    payload: dict[str, object],
) -> WireEnvelope:
    responses = gateway.handle("client:1", _envelope(message_type, sequence, payload))
    assert len(responses) == 1
    return responses[0]


def _unlock(gateway: Gateway) -> None:
    _send(
        gateway,
        MessageType.CLIENT_HELLO,
        1,
        {"client_version": "0.1.0", "supported_schema_versions": [1]},
    )
    result = _send(
        gateway,
        MessageType.AUTH_SETUP,
        2,
        {"password": "correct horse", "confirmation": "correct horse"},
    )
    assert result.message_type is MessageType.AUTH_RESULT


def _publish_stock(gateway: Gateway, tmp_path: Path) -> ConsoleSnapshot:
    seed = Gateway(tmp_path / "projection-seed", clock=lambda: NOW).snapshot()
    row = PortfolioRow(
        symbol="NVDA",
        description="NVIDIA",
        asset_type="stock",
        quantity="10",
        price="100",
        market_value="1000",
        current_weight=10.0,
        proposed_weight=None,
        approved_weight=None,
        change_state="unchanged",
        confirmed_rank=1,
        reconciliation="not-required",
    )
    snapshot = seed.model_copy(
        update={
            "shell": seed.shell.model_copy(update={"state_version": 1}),
            "portfolio": seed.portfolio.model_copy(update={"rows": (row,)}),
        }
    )
    gateway.publish_snapshot(snapshot)
    return snapshot


def _approval_row(
    *,
    run_id: str = "run:1",
    checkpoint_id: str = "checkpoint:1",
) -> ApprovalRow:
    return ApprovalRow(
        approval_id="approval:1",
        run_id=run_id,
        checkpoint_id=checkpoint_id,
        state="pending",
        reason=None,
        evidence_ids=("evidence:1",),
        requested_at_utc=NOW,
        affected_symbols=(),
        weight_changes=(),
        risks=(),
        expected_consequences=(),
        basis_sha256=None,
        stale_reason=None,
    )


def _publish_approval(gateway: Gateway, tmp_path: Path) -> ConsoleSnapshot:
    seed = Gateway(tmp_path / "approval-seed", clock=lambda: NOW).snapshot()
    approval = _approval_row()
    snapshot = seed.model_copy(
        update={
            "shell": seed.shell.model_copy(update={"state_version": 1}),
            "risk": seed.risk.model_copy(update={"approvals": (approval,)}),
        }
    )
    gateway.publish_snapshot(snapshot)
    return snapshot


def test_attaching_registry_publishes_exact_command_catalog(tmp_path: Path) -> None:
    gateway = Gateway(tmp_path / "auth", clock=lambda: NOW)
    before = gateway.snapshot()
    runtime = _RuntimeReader(_runtime_sample())

    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        gateway.attach_platform_runtime_reader(runtime)
        gateway.attach_command_registry(registry)
        snapshot = gateway.snapshot()

        assert snapshot.command_specs == COMMAND_SPECS
        assert tuple(row.capability_id for row in snapshot.shell.capabilities) == (
            "snapshot.read",
            *(spec.capability_id for spec in COMMAND_SPECS),
        )
        assert {
            row.capability_id for row in snapshot.shell.capabilities if row.state.value == "enabled"
        } == HANDLED
        assert {
            row.capability_id: row.reason
            for row in snapshot.shell.capabilities
            if row.state.value == "disabled"
        } == dict(DISABLED_COMMAND_REASONS)
        assert snapshot.shell.capabilities[0].state.value == "read-only"
        assert snapshot.control_version == before.control_version + 1
        assert snapshot.control_hash != before.control_hash

        gateway.attach_command_registry(registry)
        assert gateway.snapshot() is snapshot


def test_gateway_rejects_registry_with_noncanonical_catalog(tmp_path: Path) -> None:
    gateway = Gateway(tmp_path / "auth", clock=lambda: NOW)
    gateway.attach_platform_runtime_reader(_RuntimeReader(_runtime_sample()))
    with CommandRegistry(
        tmp_path / "commands.sqlite3",
        _Port(),
        specs=(),
        clock=lambda: NOW,
    ) as registry:
        with pytest.raises(ValueError, match="canonical command catalog"):
            gateway.attach_command_registry(registry)

    snapshot = gateway.snapshot()
    assert snapshot.command_specs == ()
    assert all(row.state is CapabilityState.DISABLED for row in snapshot.shell.capabilities)


def test_command_registry_requires_platform_runtime_read_port(tmp_path: Path) -> None:
    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        with pytest.raises(ValueError, match="runtime read port"):
            Gateway(
                tmp_path / "auth",
                clock=lambda: NOW,
                command_registry=registry,
            )


def test_platform_runtime_reader_is_one_time_and_operator_id_is_stable(
    tmp_path: Path,
) -> None:
    calls = 0

    def sid() -> str:
        nonlocal calls
        calls += 1
        return "S-1-5-5-9-9"

    gateway = Gateway(tmp_path / "auth", clock=lambda: NOW, logon_sid_provider=sid)
    runtime = _RuntimeReader(_runtime_sample())

    gateway.attach_platform_runtime_reader(runtime)
    gateway.attach_platform_runtime_reader(runtime)

    assert gateway.operator_id == gateway.operator_id
    assert gateway.operator_id.startswith("windows:")
    assert calls == 1
    with pytest.raises(RuntimeError, match="already attached"):
        gateway.attach_platform_runtime_reader(_RuntimeReader(_runtime_sample()))


def test_unavailable_runtime_disables_only_runtime_governed_actions(
    tmp_path: Path,
) -> None:
    runtime = _RuntimeReader(_unavailable_runtime_sample())
    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry, runtime=runtime)

        capabilities = {row.capability_id: row for row in gateway.snapshot().shell.capabilities}

        assert capabilities["note.add"].state is CapabilityState.ENABLED
        for capability_id in {
            "approval.approve",
            "approval.hold",
            "approval.reject",
            "agent.enqueue",
        }:
            assert capabilities[capability_id].state is CapabilityState.DISABLED
            assert capabilities[capability_id].reason == ("Platform runtime state is unavailable.")
        assert capabilities["trading.pause"].reason == DISABLED_COMMAND_REASONS["trading.pause"]
        assert runtime.read_count == 1


def test_each_publication_rereads_and_binds_platform_runtime(tmp_path: Path) -> None:
    runtime = _RuntimeReader(_unavailable_runtime_sample())
    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry, runtime=runtime)
        seed = Gateway(tmp_path / "seed", clock=lambda: NOW).snapshot()
        upstream = seed.model_copy(
            update={"shell": seed.shell.model_copy(update={"state_version": 1})}
        )
        gateway.publish_snapshot(upstream)
        unavailable = gateway.snapshot()
        runtime.sample = _runtime_sample()

        gateway.publish_snapshot(upstream)
        fresh = gateway.snapshot()

        assert runtime.read_count == 3
        assert fresh.control_version == unavailable.control_version + 1
        assert fresh.control_hash != unavailable.control_hash
        assert (
            next(
                row for row in fresh.shell.capabilities if row.capability_id == "approval.approve"
            ).state
            is CapabilityState.ENABLED
        )


def test_gateway_without_registry_never_publishes_enabled_actions(tmp_path: Path) -> None:
    gateway = Gateway(tmp_path / "auth", clock=lambda: NOW)
    upstream = gateway.snapshot()
    capabilities = tuple(
        row.model_copy(update={"state": CapabilityState.ENABLED, "reason": None})
        if row.capability_id == "note.add"
        else row
        for row in upstream.shell.capabilities
    )

    gateway.publish_snapshot(
        upstream.model_copy(
            update={
                "shell": upstream.shell.model_copy(
                    update={"state_version": 1, "capabilities": capabilities}
                )
            }
        )
    )

    published = gateway.snapshot()
    note = next(row for row in published.shell.capabilities if row.capability_id == "note.add")
    assert note.state is CapabilityState.DISABLED
    assert all(
        row.state is not CapabilityState.ENABLED
        for row in published.shell.capabilities
        if row.capability_id != "snapshot.read"
    )


def test_composite_control_state_is_stable_and_binds_agent_roster(tmp_path: Path) -> None:
    gateway = Gateway(tmp_path / "auth", clock=lambda: NOW)
    runtime = _RuntimeReader(_runtime_sample())
    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        gateway.attach_platform_runtime_reader(runtime)
        gateway.attach_command_registry(registry)
        seed = Gateway(tmp_path / "seed", clock=lambda: NOW).snapshot()
        first_upstream = seed.model_copy(
            update={
                "shell": seed.shell.model_copy(update={"state_version": 1}),
                "control_version": 7,
                "control_hash": "a" * 64,
            }
        )
        gateway.publish_snapshot(first_upstream)
        first = gateway.snapshot()

        second_upstream = first_upstream.model_copy(
            update={"shell": first_upstream.shell.model_copy(update={"state_version": 2})}
        )
        gateway.publish_snapshot(second_upstream)
        second = gateway.snapshot()
        assert second.control_version == first.control_version
        assert second.control_hash == first.control_hash
        assert second.command_specs == COMMAND_SPECS

        agent = AgentCard(
            work_id="work:1",
            agent="v20-model-researcher",
            title="Review candidate",
            stage="queued",
            priority=50,
            urgent=False,
            elapsed_seconds=None,
            model="qwen:64k",
            affected_areas=("models",),
            session_id=None,
            plan_steps=(),
            activity=(),
            evidence_ids=(),
            context_percent=None,
            chat_agent_id="v20-model-researcher",
            detail_next_cursor=None,
        )
        runtime.sample = _runtime_sample(active_work=(agent,))
        changed_upstream = second_upstream.model_copy(
            update={"shell": second_upstream.shell.model_copy(update={"state_version": 3})}
        )
        gateway.publish_snapshot(changed_upstream)
        changed = gateway.snapshot()

        assert changed.control_version == second.control_version + 1
        assert changed.control_hash != second.control_hash


def test_composite_control_state_binds_approved_agent_catalog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from vesper.platform.tui import gateway as gateway_module

    gateway = Gateway(tmp_path / "auth", clock=lambda: NOW)
    runtime = _RuntimeReader(_runtime_sample())
    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        gateway.attach_platform_runtime_reader(runtime)
        gateway.attach_command_registry(registry)
        seed = Gateway(tmp_path / "seed", clock=lambda: NOW).snapshot()
        first_upstream = seed.model_copy(
            update={"shell": seed.shell.model_copy(update={"state_version": 1})}
        )
        gateway.publish_snapshot(first_upstream)
        first = gateway.snapshot()

        monkeypatch.setattr(
            gateway_module,
            "AUTONOMOUS_AGENT_ROLES",
            (AgentRole.MODEL_RESEARCHER,),
        )
        gateway.publish_snapshot(
            first_upstream.model_copy(
                update={"shell": first_upstream.shell.model_copy(update={"state_version": 2})}
            )
        )
        changed = gateway.snapshot()

        assert changed.control_version == first.control_version + 1
        assert changed.control_hash != first.control_hash


def test_composite_control_state_binds_exact_pending_approval(tmp_path: Path) -> None:
    gateway = Gateway(tmp_path / "auth", clock=lambda: NOW)
    runtime = _RuntimeReader(_runtime_sample(pending_approvals=(_approval_row(),)))
    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        gateway.attach_platform_runtime_reader(runtime)
        gateway.attach_command_registry(registry)
        upstream = _publish_approval(gateway, tmp_path)
        first = gateway.snapshot()
        runtime.sample = _runtime_sample(
            pending_approvals=(_approval_row(checkpoint_id="checkpoint:2"),)
        )
        gateway.publish_snapshot(
            upstream.model_copy(
                update={
                    "shell": upstream.shell.model_copy(update={"state_version": 2}),
                }
            )
        )
        changed = gateway.snapshot()

        assert changed.control_version == first.control_version + 1
        assert changed.control_hash != first.control_hash


def test_controller_note_uses_latest_snapshot_and_server_operator(tmp_path: Path) -> None:
    sid = "S-1-5-5-123-456"
    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry, sid=sid)
        _publish_stock(gateway, tmp_path)
        _unlock(gateway)
        lease = _send(
            gateway,
            MessageType.LEASE_REQUEST,
            3,
            {"action": "take-control"},
        )
        assert lease.message_type is MessageType.LEASE_RESULT
        snapshot = gateway.snapshot()
        request = CommandRequest(
            command_id="command:note:1",
            command_type="note.add",
            reviewed_control_version=snapshot.control_version,
            reviewed_control_hash=snapshot.control_hash,
            reason=None,
            confirmation=None,
            payload=NoteAddPayload(
                target_type="stock",
                target_id="NVDA",
                body="Watch earnings risk.",
                visibility="shared",
            ),
        )

        response = _send(
            gateway,
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )

        assert response.message_type is MessageType.COMMAND_RECEIPT
        payload = decode_payload(response)
        assert isinstance(payload, CommandReceiptPayload)
        assert payload.receipt.status is ReceiptStatus.COMPLETED
        with NoteStore(registry.ledger) as notes:
            stored = notes.list(NoteTarget(target_type="stock", target_id="NVDA"))
        assert len(stored) == 1
        assert stored[0].author == (
            "windows:bc484936aeef0b0d16a8e27487182ac53bab2df5d723a51d15e3f52244acaac6"
        )


def test_viewer_command_is_a_durable_registry_rejection(tmp_path: Path) -> None:
    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry)
        _publish_stock(gateway, tmp_path)
        _unlock(gateway)
        snapshot = gateway.snapshot()
        request = CommandRequest(
            command_id="command:viewer:1",
            command_type="note.add",
            reviewed_control_version=snapshot.control_version,
            reviewed_control_hash=snapshot.control_hash,
            reason=None,
            confirmation=None,
            payload=NoteAddPayload(
                target_type="stock",
                target_id="NVDA",
                body="Viewer cannot write.",
                visibility="private",
            ),
        )

        response = _send(
            gateway,
            MessageType.COMMAND,
            3,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )

        payload = decode_payload(response)
        assert isinstance(payload, CommandReceiptPayload)
        assert payload.receipt.status is ReceiptStatus.REJECTED
        assert payload.receipt.code == "viewer"
        with CommandStore(registry.ledger) as store:
            assert store.get(request.command_id) == payload.receipt
        with NoteStore(registry.ledger) as notes:
            assert notes.list(NoteTarget(target_type="stock", target_id="NVDA")) == ()


def test_command_direction_and_payload_errors_fail_closed(tmp_path: Path) -> None:
    gateway = Gateway(tmp_path / "plain-auth", clock=lambda: NOW)
    _unlock(gateway)
    no_registry = _send(
        gateway,
        MessageType.COMMAND,
        3,
        {"not": "a command"},
    )
    error = decode_payload(no_registry)
    assert isinstance(error, ProtocolErrorPayload)
    assert error.code == "direction"

    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        governed = _governed_gateway(
            tmp_path,
            registry,
            state_name="governed-auth",
        )
        _unlock(governed)
        invalid = _send(
            governed,
            MessageType.COMMAND,
            3,
            {"not": "a command"},
        )
        error = decode_payload(invalid)
        assert isinstance(error, ProtocolErrorPayload)
        assert error.code == "invalid-payload"

        snapshot = governed.snapshot()
        spoofed_request = CommandRequest(
            command_id="command:spoofed:1",
            command_type="note.add",
            reviewed_control_version=snapshot.control_version,
            reviewed_control_hash=snapshot.control_hash,
            reason=None,
            confirmation=None,
            payload=NoteAddPayload(
                target_type="stock",
                target_id="NVDA",
                body="Spoof attempt.",
                visibility="private",
            ),
        ).model_dump(mode="json")
        spoofed_request["operator_id"] = "windows:spoofed"
        spoofed = _send(
            governed,
            MessageType.COMMAND,
            4,
            {"request": spoofed_request},
        )
        error = decode_payload(spoofed)
        assert isinstance(error, ProtocolErrorPayload)
        assert error.code == "invalid-payload"


def test_disabled_command_is_rejected_before_request_facts(tmp_path: Path) -> None:
    port = _Port()
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry)
        _unlock(gateway)
        _send(
            gateway,
            MessageType.LEASE_REQUEST,
            3,
            {"action": "take-control"},
        )
        snapshot = gateway.snapshot()
        request = CommandRequest(
            command_id="command:disabled:1",
            command_type="trading.pause",
            reviewed_control_version=snapshot.control_version + 1,
            reviewed_control_hash="f" * 64,
            reason="Testing disabled policy order.",
            confirmation=ConfirmationProof(),
            payload=EmptyPayload(),
        )

        response = _send(
            gateway,
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )

        payload = decode_payload(response)
        assert isinstance(payload, CommandReceiptPayload)
        assert payload.receipt.status is ReceiptStatus.REJECTED
        assert payload.receipt.code == "capability-disabled"
        assert payload.receipt.safe_message == DISABLED_COMMAND_REASONS["trading.pause"]
        assert port.calls == []


def test_missing_note_target_fails_without_writing(tmp_path: Path) -> None:
    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry)
        _publish_stock(gateway, tmp_path)
        _unlock(gateway)
        _send(
            gateway,
            MessageType.LEASE_REQUEST,
            3,
            {"action": "take-control"},
        )
        snapshot = gateway.snapshot()
        request = CommandRequest(
            command_id="command:note:missing",
            command_type="note.add",
            reviewed_control_version=snapshot.control_version,
            reviewed_control_hash=snapshot.control_hash,
            reason=None,
            confirmation=None,
            payload=NoteAddPayload(
                target_type="stock",
                target_id="AAPL",
                body="This target is absent.",
                visibility="private",
            ),
        )

        response = _send(
            gateway,
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )

        payload = decode_payload(response)
        assert isinstance(payload, CommandReceiptPayload)
        assert payload.receipt.code == "prerequisite-failed"
        with NoteStore(registry.ledger) as notes:
            assert notes.list(NoteTarget(target_type="stock", target_id="AAPL")) == ()


def test_operator_identity_failure_returns_only_safe_error(tmp_path: Path) -> None:
    def unavailable_sid() -> str:
        raise OSError("sensitive SID detail")

    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(_runtime_sample()),
            logon_sid_provider=unavailable_sid,
        )
        _publish_stock(gateway, tmp_path)
        _unlock(gateway)
        _send(
            gateway,
            MessageType.LEASE_REQUEST,
            3,
            {"action": "take-control"},
        )
        snapshot = gateway.snapshot()
        request = CommandRequest(
            command_id="command:sid:failure",
            command_type="note.add",
            reviewed_control_version=snapshot.control_version,
            reviewed_control_hash=snapshot.control_hash,
            reason=None,
            confirmation=None,
            payload=NoteAddPayload(
                target_type="stock",
                target_id="NVDA",
                body="Cannot identify operator.",
                visibility="private",
            ),
        )

        response = _send(
            gateway,
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )

        error = decode_payload(response)
        assert isinstance(error, ProtocolErrorPayload)
        assert error.code == "command-unavailable"
        assert "sensitive" not in error.safe_message
        with CommandStore(registry.ledger) as store:
            assert store.get(request.command_id) is None


def test_approval_requires_exact_pending_run_checkpoint(tmp_path: Path) -> None:
    port = _Port()
    runtime = _RuntimeReader(_runtime_sample(pending_approvals=(_approval_row(),)))
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry, runtime=runtime)
        _publish_approval(gateway, tmp_path)
        _unlock(gateway)
        _send(
            gateway,
            MessageType.LEASE_REQUEST,
            3,
            {"action": "take-control"},
        )
        snapshot = gateway.snapshot()
        confirmation = ConfirmationProof(first_confirmed=True)
        wrong = CommandRequest(
            command_id="command:approval:wrong",
            command_type="approval.approve",
            reviewed_control_version=snapshot.control_version,
            reviewed_control_hash=snapshot.control_hash,
            reason=None,
            confirmation=confirmation,
            payload=ApprovalPayload(run_id="run:1", checkpoint_id="checkpoint:other"),
        )
        rejected = _send(
            gateway,
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=wrong).model_dump(mode="json"),
        )
        rejected_payload = decode_payload(rejected)
        assert isinstance(rejected_payload, CommandReceiptPayload)
        assert rejected_payload.receipt.code == "prerequisite-failed"
        assert port.calls == []

        exact = wrong.model_copy(
            update={
                "command_id": "command:approval:exact",
                "payload": ApprovalPayload(
                    run_id="run:1",
                    checkpoint_id="checkpoint:1",
                ),
            }
        )
        completed = _send(
            gateway,
            MessageType.COMMAND,
            5,
            CommandMessagePayload(request=exact).model_dump(mode="json"),
        )
        completed_payload = decode_payload(completed)
        assert isinstance(completed_payload, CommandReceiptPayload)
        assert completed_payload.receipt.status is ReceiptStatus.COMPLETED
        assert port.calls == [("approval.approve", exact.command_id)]


def test_agent_enqueue_accepts_only_approved_autonomous_role(tmp_path: Path) -> None:
    port = _Port()
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry)
        _unlock(gateway)
        _send(
            gateway,
            MessageType.LEASE_REQUEST,
            3,
            {"action": "take-control"},
        )
        snapshot = gateway.snapshot()
        confirmation = ConfirmationProof(first_confirmed=True)
        denied = CommandRequest(
            command_id="command:agent:denied",
            command_type="agent.enqueue",
            reviewed_control_version=snapshot.control_version,
            reviewed_control_hash=snapshot.control_hash,
            reason="Queue approved research.",
            confirmation=confirmation,
            payload=AgentEnqueuePayload(
                agent_id="v20-development",
                title="Wrong lane",
                objective="Do not queue a non-autonomous role.",
                priority=50,
            ),
        )
        denied_response = _send(
            gateway,
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=denied).model_dump(mode="json"),
        )
        denied_payload = decode_payload(denied_response)
        assert isinstance(denied_payload, CommandReceiptPayload)
        assert denied_payload.receipt.code == "prerequisite-failed"
        assert port.calls == []

        admitted = denied.model_copy(
            update={
                "command_id": "command:agent:admitted",
                "payload": AgentEnqueuePayload(
                    agent_id="v20-model-researcher",
                    title="Review model",
                    objective="Review current V20 model evidence.",
                    priority=50,
                ),
            }
        )
        admitted_response = _send(
            gateway,
            MessageType.COMMAND,
            5,
            CommandMessagePayload(request=admitted).model_dump(mode="json"),
        )
        admitted_payload = decode_payload(admitted_response)
        assert isinstance(admitted_payload, CommandReceiptPayload)
        assert admitted_payload.receipt.status is ReceiptStatus.COMPLETED
        assert port.calls == [("agent.enqueue", admitted.command_id)]


def test_changed_control_facts_reject_reviewed_request_as_stale(tmp_path: Path) -> None:
    port = _Port()
    runtime = _RuntimeReader(_runtime_sample())
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry, runtime=runtime)
        _publish_stock(gateway, tmp_path)
        _unlock(gateway)
        _send(
            gateway,
            MessageType.LEASE_REQUEST,
            3,
            {"action": "take-control"},
        )
        reviewed = gateway.snapshot()
        request = CommandRequest(
            command_id="command:stale:1",
            command_type="note.add",
            reviewed_control_version=reviewed.control_version,
            reviewed_control_hash=reviewed.control_hash,
            reason=None,
            confirmation=None,
            payload=NoteAddPayload(
                target_type="stock",
                target_id="NVDA",
                body="This review is now stale.",
                visibility="private",
            ),
        )
        agent = AgentCard(
            work_id="work:changed",
            agent="v20-model-researcher",
            title="Changed roster",
            stage="queued",
            priority=50,
            urgent=False,
            elapsed_seconds=None,
            model="qwen:64k",
            affected_areas=("models",),
            session_id=None,
            plan_steps=(),
            activity=(),
            evidence_ids=(),
            context_percent=None,
            chat_agent_id="v20-model-researcher",
            detail_next_cursor=None,
        )
        runtime.sample = _runtime_sample(active_work=(agent,))

        response = _send(
            gateway,
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )

        payload = decode_payload(response)
        assert isinstance(payload, CommandReceiptPayload)
        assert payload.receipt.code == "stale-state"
        assert runtime.read_count == 3
        assert port.calls == []
        with CommandStore(registry.ledger) as store:
            assert store.get(request.command_id) == payload.receipt


def test_pending_approval_change_is_reread_and_rejected_as_stale(
    tmp_path: Path,
) -> None:
    port = _Port()
    runtime = _RuntimeReader(_runtime_sample(pending_approvals=(_approval_row(),)))
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry, runtime=runtime)
        _publish_approval(gateway, tmp_path)
        _unlock(gateway)
        _send(gateway, MessageType.LEASE_REQUEST, 3, {"action": "take-control"})
        reviewed = gateway.snapshot()
        request = CommandRequest(
            command_id="command:approval:stale",
            command_type="approval.approve",
            reviewed_control_version=reviewed.control_version,
            reviewed_control_hash=reviewed.control_hash,
            reason=None,
            confirmation=ConfirmationProof(first_confirmed=True),
            payload=ApprovalPayload(run_id="run:1", checkpoint_id="checkpoint:1"),
        )
        runtime.sample = _runtime_sample(
            pending_approvals=(_approval_row(checkpoint_id="checkpoint:2"),)
        )

        response = _send(
            gateway,
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )

        payload = decode_payload(response)
        assert isinstance(payload, CommandReceiptPayload)
        assert payload.receipt.code == "stale-state"
        assert port.calls == []
        assert gateway.snapshot().control_hash != reviewed.control_hash
        with CommandStore(registry.ledger) as store:
            assert store.get(request.command_id) == payload.receipt


def test_runtime_reader_failure_durably_disables_external_command(
    tmp_path: Path,
) -> None:
    port = _Port()
    runtime = _RuntimeReader(_runtime_sample(pending_approvals=(_approval_row(),)))
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry, runtime=runtime)
        _publish_approval(gateway, tmp_path)
        _unlock(gateway)
        _send(gateway, MessageType.LEASE_REQUEST, 3, {"action": "take-control"})
        reviewed = gateway.snapshot()
        request = CommandRequest(
            command_id="command:approval:unavailable",
            command_type="approval.approve",
            reviewed_control_version=reviewed.control_version,
            reviewed_control_hash=reviewed.control_hash,
            reason=None,
            confirmation=ConfirmationProof(first_confirmed=True),
            payload=ApprovalPayload(run_id="run:1", checkpoint_id="checkpoint:1"),
        )
        runtime.failure = OSError("sensitive runtime reader detail")

        response = _send(
            gateway,
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )

        payload = decode_payload(response)
        assert isinstance(payload, CommandReceiptPayload)
        assert payload.receipt.code == "capability-disabled"
        assert payload.receipt.safe_message == "Platform runtime state is unavailable."
        assert "sensitive" not in payload.receipt.safe_message
        assert port.calls == []
        with CommandStore(registry.ledger) as store:
            assert store.get(request.command_id) == payload.receipt


def test_note_add_remains_safe_when_platform_runtime_is_unavailable(
    tmp_path: Path,
) -> None:
    runtime = _RuntimeReader(_unavailable_runtime_sample())
    with CommandRegistry(tmp_path / "commands.sqlite3", _Port(), clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry, runtime=runtime)
        _publish_stock(gateway, tmp_path)
        _unlock(gateway)
        _send(gateway, MessageType.LEASE_REQUEST, 3, {"action": "take-control"})
        reviewed = gateway.snapshot()
        request = CommandRequest(
            command_id="command:note:runtime-unavailable",
            command_type="note.add",
            reviewed_control_version=reviewed.control_version,
            reviewed_control_hash=reviewed.control_hash,
            reason=None,
            confirmation=None,
            payload=NoteAddPayload(
                target_type="stock",
                target_id="NVDA",
                body="Runtime outage does not block local notes.",
                visibility="private",
            ),
        )

        response = _send(
            gateway,
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )

        payload = decode_payload(response)
        assert isinstance(payload, CommandReceiptPayload)
        assert payload.receipt.status is ReceiptStatus.COMPLETED
        with NoteStore(registry.ledger) as notes:
            assert len(notes.list(NoteTarget(target_type="stock", target_id="NVDA"))) == 1


def test_operational_exception_is_safe_and_never_reissues(tmp_path: Path) -> None:
    port = _ExplodingPort()
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = _governed_gateway(tmp_path, registry)
        _unlock(gateway)
        _send(
            gateway,
            MessageType.LEASE_REQUEST,
            3,
            {"action": "take-control"},
        )
        snapshot = gateway.snapshot()
        request = CommandRequest(
            command_id="command:agent:exception",
            command_type="agent.enqueue",
            reviewed_control_version=snapshot.control_version,
            reviewed_control_hash=snapshot.control_hash,
            reason="Queue approved research.",
            confirmation=ConfirmationProof(first_confirmed=True),
            payload=AgentEnqueuePayload(
                agent_id="v20-model-researcher",
                title="Review model",
                objective="Review current V20 model evidence.",
                priority=50,
            ),
        )
        wire_request = CommandMessagePayload(request=request).model_dump(mode="json")

        first = _send(gateway, MessageType.COMMAND, 4, wire_request)
        first_error = decode_payload(first)
        assert isinstance(first_error, ProtocolErrorPayload)
        assert first_error.code == "command-unavailable"
        assert "sensitive" not in first_error.safe_message

        second = _send(gateway, MessageType.COMMAND, 5, wire_request)
        second_payload = decode_payload(second)
        assert isinstance(second_payload, CommandReceiptPayload)
        assert second_payload.receipt.status is ReceiptStatus.RUNNING
        assert port.calls == [("agent.enqueue", request.command_id)]
