from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.tui.contracts import (
    AuthResultPayload,
    Freshness,
    LeaseResultPayload,
    MessageType,
    OperatingMode,
    PongPayload,
    ProtocolErrorPayload,
    SnapshotPayload,
    WireEnvelope,
    decode_payload,
)
from vesper.platform.tui.gateway import Gateway


NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)
PHASE_ONE_REASON = "Phase 1 provides the secure console shell only."


def envelope(message_type: MessageType, sequence: int, payload: dict[str, object]) -> WireEnvelope:
    return WireEnvelope(
        schema_version=1,
        message_id=f"client:{sequence}",
        sequence=sequence,
        state_version=999,
        timestamp_utc=NOW,
        message_type=message_type,
        payload=payload,
    )


def send(gateway: Gateway, client_id: str, message_type: MessageType, sequence: int, **payload: object):
    responses = gateway.handle(client_id, envelope(message_type, sequence, payload))
    assert len(responses) == 1
    return responses[0]


def greet(gateway: Gateway, client_id: str, sequence: int = 1):
    return send(
        gateway,
        client_id,
        MessageType.CLIENT_HELLO,
        sequence,
        client_version="0.1.0",
        supported_schema_versions=[1],
    )


def setup(gateway: Gateway, client_id: str = "first") -> None:
    hello = greet(gateway, client_id)
    assert hello.message_type is MessageType.SERVER_HELLO
    assert hello.payload["requires_setup"] is True
    result = send(
        gateway,
        client_id,
        MessageType.AUTH_SETUP,
        2,
        password="correct horse",
        confirmation="correct horse",
    )
    assert decode_payload(result) == AuthResultPayload(
        success=True,
        access_state="viewer",
        reason=None,
    )


def unlock(gateway: Gateway, client_id: str, start: int = 1) -> None:
    hello = greet(gateway, client_id, start)
    assert hello.payload["requires_setup"] is False
    result = send(
        gateway,
        client_id,
        MessageType.AUTH_UNLOCK,
        start + 1,
        password="correct horse",
    )
    assert decode_payload(result) == AuthResultPayload(
        success=True,
        access_state="viewer",
        reason=None,
    )


@pytest.fixture
def gateway(tmp_path: Path) -> Gateway:
    return Gateway(tmp_path, clock=lambda: NOW)


def test_required_handshake_order_and_same_viewer_snapshot(gateway: Gateway) -> None:
    setup(gateway)
    first_snapshot = send(gateway, "first", MessageType.SNAPSHOT_REQUEST, 3)
    assert first_snapshot.message_type is MessageType.SNAPSHOT

    unlock(gateway, "viewer")
    second_snapshot = send(gateway, "viewer", MessageType.SNAPSHOT_REQUEST, 3)
    assert decode_payload(first_snapshot) == decode_payload(second_snapshot)


def test_setup_is_first_run_only_and_every_new_session_unlocks(gateway: Gateway) -> None:
    setup(gateway)
    hello = greet(gateway, "second")
    assert hello.payload["requires_setup"] is False
    denied = send(
        gateway,
        "second",
        MessageType.AUTH_SETUP,
        2,
        password="different",
        confirmation="different",
    )
    assert decode_payload(denied).success is False
    assert send(gateway, "second", MessageType.SNAPSHOT_REQUEST, 3).message_type is MessageType.PROTOCOL_ERROR


@pytest.mark.parametrize("message_type,payload", [
    (MessageType.SNAPSHOT_REQUEST, {}),
    (MessageType.LEASE_REQUEST, {"action": "take-control"}),
    (MessageType.LOCK_REQUEST, {"action": "lock"}),
])
def test_locked_session_rejects_state_lease_and_lock(gateway: Gateway, message_type: MessageType, payload: dict[str, object]) -> None:
    response = send(gateway, "locked", message_type, 1, **payload)
    error = decode_payload(response)
    assert response.message_type is MessageType.PROTOCOL_ERROR
    assert isinstance(error, ProtocolErrorPayload)
    assert error.code == "locked"


def test_ping_works_while_locked_without_state(gateway: Gateway) -> None:
    response = send(gateway, "locked", MessageType.PING, 1, nonce="probe")
    assert response.message_type is MessageType.PONG
    assert response.state_version == 0
    assert decode_payload(response) == PongPayload(nonce="probe")


def test_take_control_is_explicit_and_never_implicitly_promotes(gateway: Gateway) -> None:
    setup(gateway, "controller")
    unlock(gateway, "viewer")
    assert gateway.controller_id is None

    acquired = send(gateway, "controller", MessageType.LEASE_REQUEST, 3, action="take-control")
    assert decode_payload(acquired) == LeaseResultPayload(status="controller", reason=None)
    held = send(gateway, "viewer", MessageType.LEASE_REQUEST, 3, action="take-control")
    assert decode_payload(held) == LeaseResultPayload(
        status="lease-held",
        reason="Another authenticated session has control.",
    )

    gateway.disconnect("controller")
    assert gateway.controller_id is None
    assert gateway.session("viewer").access_state == "viewer"
    transferred = send(gateway, "viewer", MessageType.LEASE_REQUEST, 4, action="take-control")
    assert decode_payload(transferred).status == "transferred"


def test_lock_releases_lease_and_requires_fresh_unlock(gateway: Gateway) -> None:
    setup(gateway, "owner")
    send(gateway, "owner", MessageType.LEASE_REQUEST, 3, action="take-control")
    locked = send(gateway, "owner", MessageType.LOCK_REQUEST, 4, action="lock")
    assert locked.message_type is MessageType.LOCK_RESULT
    assert gateway.controller_id is None

    assert send(gateway, "owner", MessageType.SNAPSHOT_REQUEST, 5).message_type is MessageType.PROTOCOL_ERROR
    assert send(gateway, "owner", MessageType.LEASE_REQUEST, 6, action="take-control").message_type is MessageType.PROTOCOL_ERROR
    unlocked = send(gateway, "owner", MessageType.AUTH_UNLOCK, 7, password="correct horse")
    assert decode_payload(unlocked).success is True


def test_initial_snapshot_is_unknown_unavailable(gateway: Gateway) -> None:
    snapshot = gateway.snapshot()
    assert snapshot.state_version == 0
    assert snapshot.header.operating_mode is OperatingMode.UNKNOWN
    assert snapshot.header.operating_mode_freshness is Freshness.UNAVAILABLE
    assert snapshot.header.operating_mode_reason == "No reviewed runtime-status adapter is configured."
    assert snapshot.header.data_freshness is Freshness.UNAVAILABLE
    assert snapshot.header.portfolio_value is None
    assert snapshot.header.regime_label == "Unavailable"
    assert snapshot.header.agent_queue_length is None
    assert snapshot.header.rebalance_blockers is None
    assert snapshot.alerts is None
    assert len(snapshot.capabilities) == 31
    assert all(item.state.value == "disabled" and item.reason == PHASE_ONE_REASON for item in snapshot.capabilities)


def test_state_version_zero_snapshot_is_one_cached_immutable_value(gateway: Gateway) -> None:
    first = gateway.snapshot()
    time.sleep(0.01)
    second = gateway.snapshot()
    assert first is second
    assert first.model_dump_json() == second.model_dump_json()


def test_sequences_are_strict_incoming_and_monotonic_outgoing(gateway: Gateway) -> None:
    first = greet(gateway, "sequence")
    replay = send(gateway, "sequence", MessageType.PING, 1, nonce="replay")
    skipped = send(gateway, "sequence", MessageType.PING, 3, nonce="skipped")
    valid = send(gateway, "sequence", MessageType.PING, 2, nonce="valid")

    assert [first.sequence, replay.sequence, skipped.sequence, valid.sequence] == [1, 2, 3, 4]
    assert decode_payload(replay).code == "sequence"
    assert decode_payload(skipped).code == "sequence"
    assert valid.message_type is MessageType.PONG


def test_same_session_concurrent_outputs_are_unique_and_monotonic(gateway: Gateway) -> None:
    barrier = threading.Barrier(8)
    results: list[int] = []
    result_lock = threading.Lock()

    def ping(sequence: int) -> None:
        barrier.wait()
        response = send(gateway, "shared", MessageType.PING, sequence, nonce=f"n-{sequence}")
        with result_lock:
            results.append(response.sequence)

    threads = [threading.Thread(target=ping, args=(sequence,)) for sequence in range(1, 9)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == list(range(1, 9))


def test_concurrent_outputs_receive_unique_monotonic_sequences(gateway: Gateway) -> None:
    results: list[int] = []
    lock = threading.Lock()

    def ping(index: int) -> None:
        response = send(gateway, f"client-{index}", MessageType.PING, 1, nonce=f"n-{index}")
        with lock:
            results.append(response.sequence)

    threads = [threading.Thread(target=ping, args=(index,)) for index in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [1] * 12


def test_malformed_state_transition_does_not_call_snapshot(gateway: Gateway, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway, "snapshot", lambda: pytest.fail("state was accessed"))
    response = send(gateway, "new", MessageType.SNAPSHOT_REQUEST, 1)
    assert decode_payload(response).code == "locked"


def test_authenticated_session_rejects_repeated_auth_without_losing_access(gateway: Gateway) -> None:
    setup(gateway, "owner")
    repeated = send(gateway, "owner", MessageType.AUTH_UNLOCK, 3, password="wrong")
    assert decode_payload(repeated).code == "state"
    assert send(gateway, "owner", MessageType.SNAPSHOT_REQUEST, 4).message_type is MessageType.SNAPSHOT


def test_cli_print_pipe_name_is_exclusive_and_opens_no_state(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from vesper.platform.tui import cli

    monkeypatch.setattr(cli, "default_pipe_name", lambda: r"\\.\pipe\vesper-v20-tui-0123456789abcdef")
    monkeypatch.setattr(cli, "Gateway", lambda *args, **kwargs: pytest.fail("state opened"))
    assert cli.main(["--print-pipe-name"]) == 0
    assert capsys.readouterr().out.strip() == r"\\.\pipe\vesper-v20-tui-0123456789abcdef"
    with pytest.raises(SystemExit):
        cli.main(["--print-pipe-name", "--state-root", "elsewhere"])


def test_cli_parser_rejects_unapproved_arguments() -> None:
    from vesper.platform.tui import cli

    with pytest.raises(SystemExit):
        cli.main(["--mode", "paper"])
    with pytest.raises(SystemExit):
        cli.main(["--state", "C:\\safe"])


def test_cli_requires_exact_current_pipe_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from vesper.platform.tui import cli

    expected = r"\\.\pipe\vesper-v20-tui-0123456789abcdef"
    monkeypatch.setattr(cli, "default_pipe_name", lambda: expected)
    monkeypatch.setattr(cli, "Gateway", lambda *args, **kwargs: pytest.fail("state opened"))
    with pytest.raises(SystemExit):
        cli.main([
            "--state-root",
            str(tmp_path.resolve()),
            "--pipe-name",
            r"\\.\pipe\vesper-v20-tui-fedcba9876543210",
        ])


def test_state_root_must_be_absolute_and_is_normalized(tmp_path: Path) -> None:
    from vesper.platform.tui.cli import _normalize_state_root

    with pytest.raises(ValueError, match="absolute"):
        _normalize_state_root(Path("relative/state"))
    nested = tmp_path / "one" / ".." / "state"
    assert _normalize_state_root(nested) == (tmp_path / "state").resolve()


def test_coordinator_closes_admission_before_shutdown_sentinel(tmp_path: Path) -> None:
    from vesper.platform.tui.cli import CoordinatorClosedError, _GatewayCoordinator

    entered = threading.Event()
    release = threading.Event()
    real = Gateway(tmp_path, clock=lambda: NOW)

    class BlockingGateway:
        def handle(self, client_id: str, message: WireEnvelope):
            entered.set()
            release.wait(2)
            return real.handle(client_id, message)

        def disconnect(self, client_id: str) -> None:
            real.disconnect(client_id)

    coordinator = _GatewayCoordinator(BlockingGateway())  # type: ignore[arg-type]
    result: list[tuple[WireEnvelope, ...]] = []
    admitted = threading.Thread(
        target=lambda: result.append(
            coordinator.handle(
                "admitted",
                envelope(MessageType.PING, 1, {"nonce": "admitted"}),
            )
        )
    )
    admitted.start()
    assert entered.wait(1)
    stopping = threading.Thread(target=coordinator.stop)
    stopping.start()
    deadline = time.monotonic() + 1
    while not coordinator.closed and time.monotonic() < deadline:
        time.sleep(0.001)
    assert coordinator.closed
    with pytest.raises(CoordinatorClosedError):
        coordinator.handle("late", envelope(MessageType.PING, 1, {"nonce": "late"}))
    release.set()
    admitted.join(2)
    stopping.join(2)
    assert decode_payload(result[0][0]) == PongPayload(nonce="admitted")


def test_coordinator_serializes_disconnect_with_messages() -> None:
    from vesper.platform.tui.cli import _GatewayCoordinator

    calls: list[tuple[str, str, int]] = []

    class RecordingGateway:
        def handle(self, client_id: str, message: WireEnvelope):
            calls.append(("handle", client_id, threading.get_ident()))
            return (message,)

        def disconnect(self, client_id: str) -> None:
            calls.append(("disconnect", client_id, threading.get_ident()))

    coordinator = _GatewayCoordinator(RecordingGateway())  # type: ignore[arg-type]
    coordinator.handle("client", envelope(MessageType.PING, 1, {"nonce": "one"}))
    coordinator.disconnect("client")
    coordinator.stop()
    assert [call[:2] for call in calls] == [
        ("handle", "client"),
        ("disconnect", "client"),
    ]
    assert calls[0][2] == calls[1][2]


def test_connection_close_releases_controller_and_new_context_starts_at_sequence_one(
    gateway: Gateway,
) -> None:
    from vesper.platform.tui.cli import _GatewayCoordinator, _gateway_connection_factory

    setup(gateway, "seed")
    gateway.disconnect("seed")
    coordinator = _GatewayCoordinator(gateway)
    factory = _gateway_connection_factory(coordinator)

    first_handle, first_close = factory()

    def round_trip(handler, message: WireEnvelope) -> WireEnvelope:
        body = handler(message.model_dump_json().encode("utf-8"))
        assert body is not None
        return WireEnvelope.model_validate_json(body)

    round_trip(
        first_handle,
        envelope(
            MessageType.CLIENT_HELLO,
            1,
            {"client_version": "0.1.0", "supported_schema_versions": [1]},
        ),
    )
    round_trip(
        first_handle,
        envelope(MessageType.AUTH_UNLOCK, 2, {"password": "correct horse"}),
    )
    acquired = round_trip(
        first_handle,
        envelope(MessageType.LEASE_REQUEST, 3, {"action": "take-control"}),
    )
    assert decode_payload(acquired).status == "controller"
    assert gateway.controller_id is not None
    first_close()
    assert gateway.controller_id is None

    second_handle, second_close = factory()
    hello = round_trip(
        second_handle,
        envelope(
            MessageType.CLIENT_HELLO,
            1,
            {"client_version": "0.1.0", "supported_schema_versions": [1]},
        ),
    )
    assert hello.sequence == 1
    second_close()
    coordinator.stop()


def test_parent_exit_requires_thirty_continuous_seconds_without_clients() -> None:
    from vesper.platform.tui.cli import _ParentExitLatch

    latch = _ParentExitLatch()
    assert not latch.observe(parent_alive=False, client_count=0, now=10.0)
    assert not latch.observe(parent_alive=False, client_count=1, now=39.9)
    assert not latch.observe(parent_alive=False, client_count=0, now=40.0)
    assert not latch.observe(parent_alive=False, client_count=0, now=69.9)
    assert latch.observe(parent_alive=False, client_count=0, now=70.0)


def test_parent_return_resets_idle_window() -> None:
    from vesper.platform.tui.cli import _ParentExitLatch

    latch = _ParentExitLatch()
    assert not latch.observe(parent_alive=False, client_count=0, now=0.0)
    assert not latch.observe(parent_alive=True, client_count=0, now=29.0)
    assert not latch.observe(parent_alive=False, client_count=0, now=30.0)
    assert not latch.observe(parent_alive=False, client_count=0, now=59.9)
    assert latch.observe(parent_alive=False, client_count=0, now=60.0)
