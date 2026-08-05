from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from vesper.platform.tui.command_contracts import (
    AgentEnqueuePayload,
    CommandMessagePayload,
    CommandReceiptPayload,
    CommandRequest,
    ConfirmationProof,
    EmptyPayload,
    EnableLivePayload,
    NoteAddPayload,
    ReceiptStatus,
)
from vesper.platform.tui.command_ports import DISABLED_COMMAND_REASONS, PortResult
from vesper.platform.tui.command_registry import CommandRegistry
from vesper.platform.tui.command_store import CommandStore
from vesper.platform.tui.contracts import (
    Freshness,
    MessageType,
    ProtocolErrorPayload,
    WireEnvelope,
    decode_payload,
)
from vesper.platform.tui.gateway import Gateway
from vesper.platform.tui.notes import NoteStore, NoteTarget
from vesper.platform.tui.ports import PlatformRuntimeFacts, SourceSample
from vesper.platform.tui.views import ConsoleSnapshot, PortfolioRow


NOW = datetime(2026, 8, 4, 16, 0, tzinfo=timezone.utc)


class _FakePort:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_after_effect: set[str] = set()
        self.fail_results: set[str] = set()
        self.recovery: dict[str, str] = {}
        self.results: dict[str, dict[str, object]] = {}

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
        if command_id in self.fail_after_effect:
            raise RuntimeError("simulated failure after effect")
        if command_id in self.fail_results:
            return PortResult(False, "downstream-failed", "Downstream work failed safely.")
        return PortResult(
            True,
            "completed",
            "Agent work queued.",
            self.results.get(command_id),
        )

    def recover(self, command_id: str, request: object) -> str:
        del request
        return self.recovery.get(command_id, "not-started")


class _RuntimeReader:
    def read(self) -> SourceSample[PlatformRuntimeFacts]:
        return SourceSample[PlatformRuntimeFacts](
            value=PlatformRuntimeFacts(pending_approvals=(), active_work=()),
            freshness=Freshness.FRESH,
            observed_at_utc=NOW,
            source="native platform runtime",
            error=None,
        )


def _envelope(
    client_id: str,
    message_type: MessageType,
    sequence: int,
    payload: dict[str, object],
) -> WireEnvelope:
    return WireEnvelope(
        schema_version=1,
        message_id=f"{client_id}:message:{sequence}",
        sequence=sequence,
        state_version=0,
        timestamp_utc=NOW,
        message_type=message_type,
        payload=payload,
    )


def _send(
    gateway: Gateway,
    client_id: str,
    message_type: MessageType,
    sequence: int,
    payload: dict[str, object],
) -> WireEnvelope:
    responses = gateway.handle(
        client_id,
        _envelope(client_id, message_type, sequence, payload),
    )
    assert len(responses) == 1
    return responses[0]


def _unlock(
    gateway: Gateway,
    client_id: str,
    *,
    first_run: bool,
) -> None:
    _send(
        gateway,
        client_id,
        MessageType.CLIENT_HELLO,
        1,
        {"client_version": "0.1.0", "supported_schema_versions": [1]},
    )
    message_type = MessageType.AUTH_SETUP if first_run else MessageType.AUTH_UNLOCK
    payload = (
        {"password": "correct horse", "confirmation": "correct horse"}
        if first_run
        else {"password": "correct horse"}
    )
    _send(gateway, client_id, message_type, 2, payload)


def _publish_stock(gateway: Gateway, tmp_path: Path) -> ConsoleSnapshot:
    seed = Gateway(tmp_path / "projection-seed", clock=lambda: NOW).snapshot()
    stock = PortfolioRow(
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
            "portfolio": seed.portfolio.model_copy(update={"rows": (stock,)}),
        }
    )
    gateway.publish_snapshot(snapshot)
    return snapshot


def _take_control(gateway: Gateway, client_id: str, sequence: int = 3) -> None:
    response = _send(
        gateway,
        client_id,
        MessageType.LEASE_REQUEST,
        sequence,
        {"action": "take-control"},
    )
    assert decode_payload(response).status == "controller"


def _agent_request(gateway: Gateway, command_id: str) -> CommandRequest:
    snapshot = gateway.snapshot()
    return CommandRequest(
        command_id=command_id,
        command_type="agent.enqueue",
        reviewed_control_version=snapshot.control_version,
        reviewed_control_hash=snapshot.control_hash,
        reason="Queue approved local research.",
        confirmation=ConfirmationProof(first_confirmed=True),
        payload=AgentEnqueuePayload(
            agent_id="v20-model-researcher",
            title="Review model evidence",
            objective="Review the current V20 model evidence only.",
            priority=50,
        ),
    )


def _note_request(gateway: Gateway) -> CommandRequest:
    snapshot = gateway.snapshot()
    return CommandRequest(
        command_id="command:reconnect:note",
        command_type="note.add",
        reviewed_control_version=snapshot.control_version,
        reviewed_control_hash=snapshot.control_hash,
        reason=None,
        confirmation=None,
        payload=NoteAddPayload(
            target_type="stock",
            target_id="NVDA",
            body="Keep this durable note once.",
            visibility="private",
        ),
    )


def test_locked_command_is_protocol_only_and_never_enters_the_ledger(
    tmp_path: Path,
) -> None:
    with CommandRegistry(
        tmp_path / "commands.sqlite3",
        _FakePort(),
        clock=lambda: NOW,
    ) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
        )
        _publish_stock(gateway, tmp_path)
        request = _note_request(gateway)

        response = _send(
            gateway,
            "client:locked",
            MessageType.COMMAND,
            1,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        error = decode_payload(response)

        assert isinstance(error, ProtocolErrorPayload)
        assert error.code == "locked"
        with CommandStore(registry.ledger) as store:
            assert store.list(100, None) == ()


def test_viewer_and_disabled_commands_are_durable_rejections_with_no_effect(
    tmp_path: Path,
) -> None:
    port = _FakePort()
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
        )
        _publish_stock(gateway, tmp_path)
        _unlock(gateway, "client:one", first_run=True)
        viewer_request = _note_request(gateway).model_copy(
            update={"command_id": "command:viewer:note"}
        )
        viewer_response = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            3,
            CommandMessagePayload(request=viewer_request).model_dump(mode="json"),
        )
        viewer_receipt = decode_payload(viewer_response)
        assert isinstance(viewer_receipt, CommandReceiptPayload)
        assert viewer_receipt.receipt.status is ReceiptStatus.REJECTED
        assert viewer_receipt.receipt.code == "viewer"

        _take_control(gateway, "client:one", sequence=4)
        snapshot = gateway.snapshot()
        disabled_request = CommandRequest(
            command_id="command:disabled:trading-pause",
            command_type="trading.pause",
            reviewed_control_version=snapshot.control_version,
            reviewed_control_hash=snapshot.control_hash,
            reason="Test the unavailable adapter boundary.",
            confirmation=ConfirmationProof(first_confirmed=True),
            payload=EmptyPayload(),
        )
        disabled_response = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            5,
            CommandMessagePayload(request=disabled_request).model_dump(mode="json"),
        )
        disabled_receipt = decode_payload(disabled_response)

        assert isinstance(disabled_receipt, CommandReceiptPayload)
        assert disabled_receipt.receipt.status is ReceiptStatus.REJECTED
        assert disabled_receipt.receipt.code == "capability-disabled"
        assert (
            disabled_receipt.receipt.safe_message
            == DISABLED_COMMAND_REASONS["trading.pause"]
        )
        assert port.calls == []
        with NoteStore(registry.ledger) as notes:
            assert notes.list(NoteTarget(target_type="stock", target_id="NVDA")) == ()
        with CommandStore(registry.ledger) as store:
            assert store.get(viewer_request.command_id) == viewer_receipt.receipt
            assert store.get(disabled_request.command_id) == disabled_receipt.receipt


def test_required_confirmation_is_rejected_then_exact_confirmation_runs_once(
    tmp_path: Path,
) -> None:
    port = _FakePort()
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
        )
        _unlock(gateway, "client:one", first_run=True)
        _take_control(gateway, "client:one")
        missing = _agent_request(gateway, "command:agent:missing-confirmation").model_copy(
            update={"confirmation": None}
        )
        rejected = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=missing).model_dump(mode="json"),
        )
        rejected_payload = decode_payload(rejected)
        assert isinstance(rejected_payload, CommandReceiptPayload)
        assert rejected_payload.receipt.code == "confirmation-missing"

        confirmed = _agent_request(gateway, "command:agent:confirmed")
        completed = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            5,
            CommandMessagePayload(request=confirmed).model_dump(mode="json"),
        )
        completed_payload = decode_payload(completed)

        assert isinstance(completed_payload, CommandReceiptPayload)
        assert completed_payload.receipt.status is ReceiptStatus.COMPLETED
        assert port.calls == [("agent.enqueue", confirmed.command_id)]


@pytest.mark.parametrize(
    ("command_type", "confirmation", "payload"),
    [
        (
            "trading.emergency-stop",
            ConfirmationProof(first_confirmed=True, second_confirmed=True),
            EmptyPayload(),
        ),
        (
            "mode.enable-live",
            ConfirmationProof(first_confirmed=True, typed_text="ENABLE LIVE"),
            EnableLivePayload(desired_portfolio_id="portfolio:desired"),
        ),
    ],
)
def test_exact_high_risk_confirmation_still_cannot_bypass_disabled_capability(
    tmp_path: Path,
    command_type: str,
    confirmation: ConfirmationProof,
    payload: object,
) -> None:
    with CommandRegistry(
        tmp_path / "commands.sqlite3",
        _FakePort(),
        clock=lambda: NOW,
    ) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
        )
        _unlock(gateway, "client:one", first_run=True)
        _take_control(gateway, "client:one")
        snapshot = gateway.snapshot()
        request = CommandRequest(
            command_id=f"command:disabled:{command_type}",
            command_type=command_type,
            reviewed_control_version=snapshot.control_version,
            reviewed_control_hash=snapshot.control_hash,
            reason="Exercise the disabled high-risk boundary.",
            confirmation=confirmation,
            payload=payload,
        )

        response = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        result = decode_payload(response)

        assert isinstance(result, CommandReceiptPayload)
        assert result.receipt.status is ReceiptStatus.REJECTED
        assert result.receipt.code == "capability-disabled"


def test_changed_note_target_prerequisite_rejects_without_writing_note(tmp_path: Path) -> None:
    with CommandRegistry(
        tmp_path / "commands.sqlite3",
        _FakePort(),
        clock=lambda: NOW,
    ) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
        )
        upstream = _publish_stock(gateway, tmp_path)
        _unlock(gateway, "client:one", first_run=True)
        _take_control(gateway, "client:one")
        request = _note_request(gateway).model_copy(
            update={"command_id": "command:prerequisite:missing-target"}
        )
        reviewed_pair = (
            request.reviewed_control_version,
            request.reviewed_control_hash,
        )
        gateway.publish_snapshot(
            upstream.model_copy(
                update={
                    "shell": upstream.shell.model_copy(update={"state_version": 2}),
                    "portfolio": upstream.portfolio.model_copy(update={"rows": ()}),
                }
            )
        )
        assert (
            gateway.snapshot().control_version,
            gateway.snapshot().control_hash,
        ) == reviewed_pair

        response = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        result = decode_payload(response)

        assert isinstance(result, CommandReceiptPayload)
        assert result.receipt.status is ReceiptStatus.REJECTED
        assert result.receipt.code == "prerequisite-failed"
        with NoteStore(registry.ledger) as notes:
            assert notes.list(NoteTarget(target_type="stock", target_id="NVDA")) == ()


def test_handler_declared_failure_is_a_durable_failed_receipt(tmp_path: Path) -> None:
    port = _FakePort()
    command_id = "command:agent:handler-failed"
    port.fail_results.add(command_id)
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
        )
        _unlock(gateway, "client:one", first_run=True)
        _take_control(gateway, "client:one")
        request = _agent_request(gateway, command_id)

        response = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        result = decode_payload(response)

        assert isinstance(result, CommandReceiptPayload)
        assert result.receipt.status is ReceiptStatus.FAILED
        assert result.receipt.code == "downstream-failed"
        assert port.calls == [("agent.enqueue", command_id)]
        with CommandStore(registry.ledger) as store:
            assert store.get(command_id) == result.receipt


def test_same_pipe_duplicate_and_reunlock_require_fresh_control_lease(tmp_path: Path) -> None:
    with CommandRegistry(
        tmp_path / "commands.sqlite3",
        _FakePort(),
        clock=lambda: NOW,
    ) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
        )
        _publish_stock(gateway, tmp_path)
        _unlock(gateway, "client:one", first_run=True)
        _take_control(gateway, "client:one")
        first_request = _note_request(gateway).model_copy(
            update={"command_id": "command:same-pipe:first"}
        )
        first = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=first_request).model_dump(mode="json"),
        )
        first_payload = decode_payload(first)
        assert isinstance(first_payload, CommandReceiptPayload)
        with registry.ledger.read() as connection:
            events_before = connection.execute(
                "SELECT COUNT(*) FROM command_receipt_events WHERE command_id = ?",
                (first_request.command_id,),
            ).fetchone()[0]

        duplicate = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            5,
            CommandMessagePayload(request=first_request).model_dump(mode="json"),
        )
        duplicate_payload = decode_payload(duplicate)
        assert isinstance(duplicate_payload, CommandReceiptPayload)
        assert duplicate_payload.receipt == first_payload.receipt
        with registry.ledger.read() as connection:
            events_after = connection.execute(
                "SELECT COUNT(*) FROM command_receipt_events WHERE command_id = ?",
                (first_request.command_id,),
            ).fetchone()[0]
        assert events_after == events_before

        lock = _send(
            gateway,
            "client:one",
            MessageType.LOCK_REQUEST,
            6,
            {"action": "lock"},
        )
        assert decode_payload(lock).locked is True
        unlocked = _send(
            gateway,
            "client:one",
            MessageType.AUTH_UNLOCK,
            7,
            {"password": "correct horse"},
        )
        assert decode_payload(unlocked).access_state == "viewer"
        viewer_request = _note_request(gateway).model_copy(
            update={"command_id": "command:same-pipe:viewer"}
        )
        viewer = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            8,
            CommandMessagePayload(request=viewer_request).model_dump(mode="json"),
        )
        viewer_payload = decode_payload(viewer)
        assert isinstance(viewer_payload, CommandReceiptPayload)
        assert viewer_payload.receipt.status is ReceiptStatus.REJECTED
        assert viewer_payload.receipt.code == "viewer"
        with NoteStore(registry.ledger) as notes:
            assert len(notes.list(NoteTarget(target_type="stock", target_id="NVDA"))) == 1

        _take_control(gateway, "client:one", sequence=9)
        controlled_request = _note_request(gateway).model_copy(
            update={"command_id": "command:same-pipe:controlled"}
        )
        controlled = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            10,
            CommandMessagePayload(request=controlled_request).model_dump(mode="json"),
        )
        controlled_payload = decode_payload(controlled)
        assert isinstance(controlled_payload, CommandReceiptPayload)
        assert controlled_payload.receipt.status is ReceiptStatus.COMPLETED
        with NoteStore(registry.ledger) as notes:
            assert len(notes.list(NoteTarget(target_type="stock", target_id="NVDA"))) == 2


def test_presentation_only_change_keeps_review_valid_but_control_change_is_stale(
    tmp_path: Path,
) -> None:
    port = _FakePort()
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
        )
        upstream = _publish_stock(gateway, tmp_path)
        _unlock(gateway, "client:one", first_run=True)
        _take_control(gateway, "client:one")
        reviewed = _note_request(gateway).model_copy(
            update={"command_id": "command:presentation:valid"}
        )
        reviewed_pair = (
            reviewed.reviewed_control_version,
            reviewed.reviewed_control_hash,
        )
        gateway.publish_snapshot(
            upstream.model_copy(
                update={
                    "shell": upstream.shell.model_copy(update={"state_version": 2})
                }
            )
        )
        assert (
            gateway.snapshot().control_version,
            gateway.snapshot().control_hash,
        ) == reviewed_pair
        completed = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=reviewed).model_dump(mode="json"),
        )
        completed_payload = decode_payload(completed)
        assert isinstance(completed_payload, CommandReceiptPayload)
        assert completed_payload.receipt.status is ReceiptStatus.COMPLETED

        stale_request = _note_request(gateway).model_copy(
            update={"command_id": "command:control:stale"}
        )
        gateway.publish_snapshot(
            upstream.model_copy(
                update={
                    "shell": upstream.shell.model_copy(update={"state_version": 3}),
                    "control_version": upstream.control_version + 1,
                    "control_hash": "f" * 64,
                }
            )
        )
        stale = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            5,
            CommandMessagePayload(request=stale_request).model_dump(mode="json"),
        )
        stale_payload = decode_payload(stale)

        assert isinstance(stale_payload, CommandReceiptPayload)
        assert stale_payload.receipt.status is ReceiptStatus.REJECTED
        assert stale_payload.receipt.code == "stale-state"
        with NoteStore(registry.ledger) as notes:
            assert len(
                notes.list(NoteTarget(target_type="stock", target_id="NVDA"))
            ) == 1


def test_authenticated_reconnect_replays_original_receipt_without_reissuing(
    tmp_path: Path,
) -> None:
    database = tmp_path / "commands.sqlite3"
    with CommandRegistry(database, _FakePort(), clock=lambda: NOW) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
            logon_sid_provider=lambda: "S-1-5-5-100-200",
        )
        _publish_stock(gateway, tmp_path)
        first_client = "client:first"
        _unlock(gateway, first_client, first_run=True)
        _take_control(gateway, first_client)
        request = _note_request(gateway)
        first = _send(
            gateway,
            first_client,
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        first_payload = decode_payload(first)
        assert isinstance(first_payload, CommandReceiptPayload)
        assert first_payload.receipt.status is ReceiptStatus.COMPLETED

        original_operator = gateway.operator_id
        gateway.disconnect(first_client)
        reconnected = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
            logon_sid_provider=lambda: "S-1-5-5-100-200",
        )
        _publish_stock(reconnected, tmp_path)
        assert reconnected.operator_id == original_operator
        assert (
            reconnected.snapshot().control_version,
            reconnected.snapshot().control_hash,
        ) == (
            request.reviewed_control_version,
            request.reviewed_control_hash,
        )
        second_client = "client:second"
        _unlock(reconnected, second_client, first_run=False)
        viewer_replay = _send(
            reconnected,
            second_client,
            MessageType.COMMAND,
            3,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        viewer_error = decode_payload(viewer_replay)
        assert isinstance(viewer_error, ProtocolErrorPayload)
        assert viewer_error.code == "command-unavailable"

        _take_control(reconnected, second_client, sequence=4)
        with registry.ledger.read() as connection:
            events_before_replay = connection.execute(
                "SELECT COUNT(*) FROM command_receipt_events WHERE command_id = ?",
                (request.command_id,),
            ).fetchone()[0]
        changed_snapshot = reconnected.snapshot()
        reconnected.publish_snapshot(
            changed_snapshot.model_copy(
                update={
                    "shell": changed_snapshot.shell.model_copy(update={"state_version": 2}),
                    "control_version": changed_snapshot.control_version + 1,
                    "control_hash": "e" * 64,
                }
            )
        )
        assert (
            reconnected.snapshot().control_version,
            reconnected.snapshot().control_hash,
        ) != (
            request.reviewed_control_version,
            request.reviewed_control_hash,
        )
        changed_request = request.model_copy(
            update={
                "payload": request.payload.model_copy(
                    update={"body": "Conflicting reconnect content."}
                )
            }
        )
        request_conflict = _send(
            reconnected,
            second_client,
            MessageType.COMMAND,
            5,
            CommandMessagePayload(request=changed_request).model_dump(mode="json"),
        )
        request_error = decode_payload(request_conflict)
        assert isinstance(request_error, ProtocolErrorPayload)
        assert request_error.code == "command-unavailable"

        changed_command = _agent_request(reconnected, request.command_id)
        command_conflict = _send(
            reconnected,
            second_client,
            MessageType.COMMAND,
            6,
            CommandMessagePayload(request=changed_command).model_dump(mode="json"),
        )
        command_error = decode_payload(command_conflict)
        assert isinstance(command_error, ProtocolErrorPayload)
        assert command_error.code == "command-unavailable"

        replay = _send(
            reconnected,
            second_client,
            MessageType.COMMAND,
            7,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        replay_payload = decode_payload(replay)

        assert isinstance(replay_payload, CommandReceiptPayload)
        assert replay_payload.receipt == first_payload.receipt
        with NoteStore(registry.ledger) as notes:
            stored = notes.list(NoteTarget(target_type="stock", target_id="NVDA"))
        assert len(stored) == 1
        with registry.ledger.read() as connection:
            admission = connection.execute(
                "SELECT client_id FROM commands WHERE command_id = ?",
                (request.command_id,),
            ).fetchone()
            events_after_replay = connection.execute(
                "SELECT COUNT(*) FROM command_receipt_events WHERE command_id = ?",
                (request.command_id,),
            ).fetchone()[0]
        assert admission["client_id"] == first_client
        assert events_after_replay == events_before_replay


def test_authenticated_reconnect_replays_original_rejected_receipt_without_mutation(
    tmp_path: Path,
) -> None:
    with CommandRegistry(
        tmp_path / "commands.sqlite3",
        _FakePort(),
        clock=lambda: NOW,
    ) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
            logon_sid_provider=lambda: "S-1-5-5-100-200",
        )
        _publish_stock(gateway, tmp_path)
        _unlock(gateway, "client:first", first_run=True)
        request = _note_request(gateway).model_copy(
            update={"command_id": "command:reconnect:rejected"}
        )
        rejected = _send(
            gateway,
            "client:first",
            MessageType.COMMAND,
            3,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        rejected_payload = decode_payload(rejected)
        assert isinstance(rejected_payload, CommandReceiptPayload)
        assert rejected_payload.receipt.status is ReceiptStatus.REJECTED
        with registry.ledger.read() as connection:
            events_before = connection.execute(
                "SELECT COUNT(*) FROM command_receipt_events WHERE command_id = ?",
                (request.command_id,),
            ).fetchone()[0]

        gateway.disconnect("client:first")
        _unlock(gateway, "client:second", first_run=False)
        _take_control(gateway, "client:second")
        current = gateway.snapshot()
        gateway.publish_snapshot(
            current.model_copy(
                update={
                    "shell": current.shell.model_copy(update={"state_version": 2}),
                    "control_version": current.control_version + 1,
                    "control_hash": "d" * 64,
                }
            )
        )
        replay = _send(
            gateway,
            "client:second",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        replay_payload = decode_payload(replay)

        assert isinstance(replay_payload, CommandReceiptPayload)
        assert replay_payload.receipt == rejected_payload.receipt
        with registry.ledger.read() as connection:
            stored = connection.execute(
                "SELECT client_id FROM commands WHERE command_id = ?",
                (request.command_id,),
            ).fetchone()
            events_after = connection.execute(
                "SELECT COUNT(*) FROM command_receipt_events WHERE command_id = ?",
                (request.command_id,),
            ).fetchone()[0]
        assert stored["client_id"] == "client:first"
        assert events_after == events_before
        with NoteStore(registry.ledger) as notes:
            assert notes.list(NoteTarget(target_type="stock", target_id="NVDA")) == ()


def test_reconnect_with_a_different_operator_cannot_replay_the_receipt(
    tmp_path: Path,
) -> None:
    port = _FakePort()
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        first_gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
            logon_sid_provider=lambda: "S-1-5-5-100-200",
        )
        _publish_stock(first_gateway, tmp_path)
        _unlock(first_gateway, "client:first", first_run=True)
        _take_control(first_gateway, "client:first")
        request = _note_request(first_gateway)
        completed = _send(
            first_gateway,
            "client:first",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        completed_payload = decode_payload(completed)
        assert isinstance(completed_payload, CommandReceiptPayload)
        first_gateway.disconnect("client:first")

        other_operator = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
            logon_sid_provider=lambda: "S-1-5-5-999-999",
        )
        _publish_stock(other_operator, tmp_path)
        _unlock(other_operator, "client:other", first_run=False)
        _take_control(other_operator, "client:other")
        assert (
            other_operator.snapshot().control_version,
            other_operator.snapshot().control_hash,
        ) == (
            request.reviewed_control_version,
            request.reviewed_control_hash,
        )
        response = _send(
            other_operator,
            "client:other",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        error = decode_payload(response)

        assert isinstance(error, ProtocolErrorPayload)
        assert error.code == "command-unavailable"
        with NoteStore(registry.ledger) as notes:
            assert len(
                notes.list(NoteTarget(target_type="stock", target_id="NVDA"))
            ) == 1
        assert port.calls == []


def test_reconnect_after_effect_failure_returns_running_then_recovers_without_reissue(
    tmp_path: Path,
) -> None:
    port = _FakePort()
    command_id = "command:agent:effect-failure"
    port.fail_after_effect.add(command_id)
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
        )
        _unlock(gateway, "client:first", first_run=True)
        _take_control(gateway, "client:first")
        request = _agent_request(gateway, command_id)
        failed = _send(
            gateway,
            "client:first",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        failed_error = decode_payload(failed)
        assert isinstance(failed_error, ProtocolErrorPayload)
        assert failed_error.code == "command-unavailable"
        assert port.calls == [("agent.enqueue", command_id)]

        gateway.disconnect("client:first")
        _unlock(gateway, "client:second", first_run=False)
        _take_control(gateway, "client:second")
        replay = _send(
            gateway,
            "client:second",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        replay_payload = decode_payload(replay)
        assert isinstance(replay_payload, CommandReceiptPayload)
        assert replay_payload.receipt.status is ReceiptStatus.RUNNING
        assert port.calls == [("agent.enqueue", command_id)]

        port.fail_after_effect.clear()
        port.recovery[command_id] = "completed"
        recovered = registry.recover_running(NOW + timedelta(seconds=31))

        assert len(recovered) == 1
        assert recovered[0].status is ReceiptStatus.COMPLETED
        assert port.calls == [("agent.enqueue", command_id)]


def test_crash_before_handler_reconnects_to_accept_then_recovers_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _FakePort()
    clock = [NOW]
    with CommandRegistry(
        tmp_path / "commands.sqlite3",
        port,
        clock=lambda: clock[0],
    ) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: clock[0],
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
        )
        _unlock(gateway, "client:first", first_run=True)
        _take_control(gateway, "client:first")
        request = _agent_request(gateway, "command:agent:before-handler")
        real_claim = registry._store.claim
        monkeypatch.setattr(
            registry._store,
            "claim",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("simulated crash before handler")
            ),
        )
        crashed = _send(
            gateway,
            "client:first",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        crashed_error = decode_payload(crashed)
        assert isinstance(crashed_error, ProtocolErrorPayload)
        assert crashed_error.code == "command-unavailable"
        assert port.calls == []
        monkeypatch.setattr(registry._store, "claim", real_claim)

        gateway.disconnect("client:first")
        _unlock(gateway, "client:second", first_run=False)
        _take_control(gateway, "client:second")
        replay = _send(
            gateway,
            "client:second",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        replay_payload = decode_payload(replay)
        assert isinstance(replay_payload, CommandReceiptPayload)
        assert replay_payload.receipt.status is ReceiptStatus.ACCEPTED
        assert port.calls == []

        clock[0] = NOW + timedelta(seconds=1)
        recovered = registry.recover_running(clock[0])

        assert len(recovered) == 1
        assert recovered[0].status is ReceiptStatus.COMPLETED
        assert port.calls == [("agent.enqueue", request.command_id)]


def test_terminal_result_removes_secret_shaped_fields_before_receipt_and_storage(
    tmp_path: Path,
) -> None:
    port = _FakePort()
    command_id = "command:agent:redacted-result"
    port.results[command_id] = {
        "safe": "visible",
        "api_key": "<redacted-test-value>",
        "nested": {
            "password": "<redacted-test-value>",
            "count": 1,
        },
    }
    with CommandRegistry(tmp_path / "commands.sqlite3", port, clock=lambda: NOW) as registry:
        gateway = Gateway(
            tmp_path / "auth",
            clock=lambda: NOW,
            command_registry=registry,
            platform_runtime_reader=_RuntimeReader(),
        )
        _unlock(gateway, "client:one", first_run=True)
        _take_control(gateway, "client:one")
        request = _agent_request(gateway, command_id)
        response = _send(
            gateway,
            "client:one",
            MessageType.COMMAND,
            4,
            CommandMessagePayload(request=request).model_dump(mode="json"),
        )
        payload = decode_payload(response)

        assert isinstance(payload, CommandReceiptPayload)
        assert payload.receipt.result == {
            "safe": "visible",
            "nested": {"count": 1},
        }
        with registry.ledger.read() as connection:
            stored = connection.execute(
                "SELECT result_json FROM commands WHERE command_id = ?",
                (command_id,),
            ).fetchone()["result_json"]
        assert stored == '{"nested":{"count":1},"safe":"visible"}'
