from __future__ import annotations

import threading
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
    assert snapshot.alerts == ()
    assert len(snapshot.capabilities) == 31
    assert all(item.state.value == "disabled" and item.reason == PHASE_ONE_REASON for item in snapshot.capabilities)


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
