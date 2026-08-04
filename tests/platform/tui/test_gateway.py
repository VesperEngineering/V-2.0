from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.persistence import PlatformPaths
from vesper.platform.tui.contracts import (
    AuthResultPayload,
    Freshness,
    LeaseResultPayload,
    MessageType,
    OperatingMode,
    PongPayload,
    ProtocolErrorPayload,
    SearchResultsPayload,
    SnapshotPayload,
    WireEnvelope,
    decode_payload,
)
from vesper.platform.tui.gateway import Gateway
from vesper.platform.tui.notes import NoteFilters, NoteStore, NoteTarget, NoteVisibility
from vesper.platform.tui.protocol import MAX_FRAME_BYTES
from vesper.platform.tui.search import GlobalSearchService, SearchKind
from vesper.platform.tui.views import (
    AccountSummaryView,
    AlertRow,
    CommandSpecView,
    ConsoleSnapshot,
    EventPayload,
    EventPresentation,
    MetricRow,
    ScreenMeta,
    TimelineRow,
)


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


def send(
    gateway: Gateway, client_id: str, message_type: MessageType, sequence: int, **payload: object
):
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


def presentation(gateway: Gateway) -> EventPresentation:
    snapshot = gateway.snapshot()

    def meta(view) -> ScreenMeta:
        return ScreenMeta(
            freshness=view.freshness,
            as_of_utc=view.as_of_utc,
            source=view.source,
            error=view.error,
        )

    return EventPresentation(
        generated_at_utc=snapshot.shell.generated_at_utc,
        header=snapshot.shell.header,
        control_version=snapshot.control_version,
        control_hash=snapshot.control_hash,
        window_omissions=snapshot.window_omissions,
        impact=meta(snapshot.impact),
        portfolio=meta(snapshot.portfolio),
        orders=meta(snapshot.orders),
        agents=meta(snapshot.agents),
        models=meta(snapshot.models),
        timeline=meta(snapshot.timeline),
        risk=meta(snapshot.risk),
        data=meta(snapshot.data),
        memory=meta(snapshot.memory),
        system=meta(snapshot.system),
        portfolio_rank_source=snapshot.portfolio.rank_source,
        timeline_hidden_event_count=snapshot.timeline.hidden_event_count,
    )


def metric_event(gateway: Gateway, value: float) -> EventPayload:
    return EventPayload(
        entity_type="metric-row",
        entity_id="metric:cpu",
        operation="upsert",
        entity=MetricRow(
            metric_id="metric:cpu",
            value=value,
            unit="percent",
            freshness=Freshness.FRESH,
            observed_at_utc=NOW,
            error=None,
        ),
        targets=("system.metrics",),
        presentation=presentation(gateway),
    )


def alert_event(gateway: Gateway) -> EventPayload:
    return EventPayload(
        entity_type="alert-row",
        entity_id="alert:required",
        operation="upsert",
        entity=AlertRow(
            alert_id="alert:required",
            severity="urgent",
            summary="Required alert",
            created_at_utc=NOW,
            resolved_at_utc=None,
        ),
        targets=("shell.alerts",),
        presentation=presentation(gateway),
    )


def subscribe(gateway: Gateway, client_id: str = "subscriber") -> None:
    setup(gateway, client_id)
    assert gateway.poll(client_id) is not None
    assert gateway.poll(client_id) is not None
    response = send(gateway, client_id, MessageType.SNAPSHOT_REQUEST, 3)
    assert gateway.poll(client_id) == response
    assert gateway.poll(client_id) is None


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
    assert (
        send(gateway, "second", MessageType.SNAPSHOT_REQUEST, 3).message_type
        is MessageType.PROTOCOL_ERROR
    )


@pytest.mark.parametrize(
    "message_type,payload",
    [
        (MessageType.SNAPSHOT_REQUEST, {}),
        (MessageType.LEASE_REQUEST, {"action": "take-control"}),
        (MessageType.LOCK_REQUEST, {"action": "lock"}),
    ],
)
def test_locked_session_rejects_state_lease_and_lock(
    gateway: Gateway, message_type: MessageType, payload: dict[str, object]
) -> None:
    response = send(gateway, "locked", message_type, 1, **payload)
    error = decode_payload(response)
    assert response.message_type is MessageType.PROTOCOL_ERROR
    assert isinstance(error, ProtocolErrorPayload)
    assert error.code == "locked"


def test_locked_search_returns_no_results_but_viewer_searches_private_and_shared_notes(
    tmp_path: Path,
) -> None:
    notes = NoteStore(
        tmp_path / "operations.sqlite3",
        clock=lambda: NOW,
        id_factory=iter(("note:private", "note:shared", "note:blank")).__next__,
    )
    notes.add(
        NoteTarget(target_type="stock", target_id="AAPL"),
        "operator context private",
        NoteVisibility.PRIVATE,
        "operator",
    )
    notes.add(
        NoteTarget(target_type="stock", target_id="AAPL"),
        "operator context shared",
        NoteVisibility.SHARED,
        "operator",
    )
    notes.add(
        NoteTarget(target_type="stock", target_id="AAPL"),
        "   ",
        NoteVisibility.PRIVATE,
        "operator",
    )
    initial = Gateway(tmp_path / "seed", clock=lambda: NOW).snapshot()
    search = GlobalSearchService(initial, None, notes)
    gateway = Gateway(tmp_path / "auth", clock=lambda: NOW, search_service=search)
    request = {
        "request_id": 9,
        "query": "operator context",
        "filters": {"kinds": ["note"], "screens": [], "source": None},
        "limit": 100,
    }
    try:
        locked = send(gateway, "locked", MessageType.SEARCH_REQUEST, 1, **request)
        assert locked.message_type is MessageType.PROTOCOL_ERROR
        assert "note" not in json.dumps(locked.payload).casefold()

        setup(gateway, "viewer")
        response = send(gateway, "viewer", MessageType.SEARCH_REQUEST, 3, **request)
        payload = decode_payload(response)
        assert response.message_type is MessageType.SEARCH_RESULTS
        assert isinstance(payload, SearchResultsPayload)
        assert payload.request_id == 9
        assert payload.indexed_state_version == initial.shell.state_version
        assert [(row.kind, row.record_id) for row in payload.results] == [
            (SearchKind.NOTE, "note:shared"),
            (SearchKind.NOTE, "note:private"),
        ]
        assert all(row.context_only is True for row in payload.results)
        assert payload.error is None
        assert gateway.controller_id is None

        blank_response = send(
            gateway,
            "viewer",
            MessageType.SEARCH_REQUEST,
            4,
            request_id=10,
            query="note blank",
            filters={"kinds": ["note"], "screens": [], "source": None},
            limit=10,
        )
        blank_payload = decode_payload(blank_response)
        assert isinstance(blank_payload, SearchResultsPayload)
        assert [(row.record_id, row.summary) for row in blank_payload.results] == [
            ("note:blank", "NOTE BODY IS BLANK")
        ]
    finally:
        search.close()
        notes.close()


def test_search_index_tracks_published_state_and_missing_service_is_a_safe_visible_error(
    tmp_path: Path,
) -> None:
    fixture = Path("TUI testing/contracts/v1/console_snapshot_empty_command_specs.json")
    snapshot = ConsoleSnapshot.model_validate_json(fixture.read_text(encoding="utf-8"))
    snapshot = snapshot.model_copy(
        update={
            "shell": snapshot.shell.model_copy(update={"state_version": 12}),
        }
    )
    seed = Gateway(tmp_path / "seed", clock=lambda: NOW).snapshot()
    search = GlobalSearchService(seed, None, None)
    gateway = Gateway(tmp_path / "auth", clock=lambda: NOW, search_service=search)
    gateway.publish_snapshot(snapshot)
    setup(gateway)

    response = send(
        gateway,
        "first",
        MessageType.SEARCH_REQUEST,
        3,
        request_id=10,
        query="AAPL",
        filters={"kinds": ["stock"], "screens": [], "source": None},
        limit=10,
    )
    payload = decode_payload(response)
    assert isinstance(payload, SearchResultsPayload)
    assert payload.indexed_state_version == 12
    assert [(row.kind, row.record_id) for row in payload.results] == [
        (SearchKind.STOCK, "AAPL")
    ]
    search.close()

    unavailable = Gateway(tmp_path / "missing", clock=lambda: NOW)
    setup(unavailable)
    response = send(
        unavailable,
        "first",
        MessageType.SEARCH_REQUEST,
        3,
        request_id=11,
        query="AAPL",
        filters={"kinds": [], "screens": [], "source": None},
        limit=10,
    )
    payload = decode_payload(response)
    assert isinstance(payload, SearchResultsPayload)
    assert payload.results == ()
    assert payload.error == "Search is unavailable."


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

    assert (
        send(gateway, "owner", MessageType.SNAPSHOT_REQUEST, 5).message_type
        is MessageType.PROTOCOL_ERROR
    )
    assert (
        send(gateway, "owner", MessageType.LEASE_REQUEST, 6, action="take-control").message_type
        is MessageType.PROTOCOL_ERROR
    )
    unlocked = send(gateway, "owner", MessageType.AUTH_UNLOCK, 7, password="correct horse")
    assert decode_payload(unlocked).success is True


def test_initial_snapshot_is_unknown_unavailable(gateway: Gateway) -> None:
    snapshot = gateway.snapshot()
    shell = snapshot.shell
    assert shell.state_version == 0
    assert shell.header.operating_mode is OperatingMode.UNKNOWN
    assert shell.header.operating_mode_freshness is Freshness.UNAVAILABLE
    assert shell.header.operating_mode_reason == "No reviewed runtime-status adapter is configured."
    assert shell.header.data_freshness is Freshness.UNAVAILABLE
    assert shell.header.portfolio_value is None
    assert shell.header.regime_label == "Unavailable"
    assert shell.header.agent_queue_length is None
    assert shell.header.rebalance_blockers is None
    assert shell.alerts is None
    assert len(shell.capabilities) == 31
    assert all(
        item.state.value == "disabled" and item.reason == PHASE_ONE_REASON
        for item in shell.capabilities
    )
    assert snapshot.command_specs == ()
    views = {
        name: getattr(snapshot, name)
        for name in (
            "impact",
            "portfolio",
            "orders",
            "agents",
            "models",
            "timeline",
            "risk",
            "data",
            "memory",
            "system",
        )
    }
    assert all(view.freshness is Freshness.UNAVAILABLE for view in views.values())
    assert all(view.as_of_utc is None and view.error for view in views.values())
    facts = {
        "capabilities": [item.model_dump(mode="json") for item in shell.capabilities],
        "command_prerequisites": {
            name: {
                "freshness": views[name].freshness.value,
                "source": views[name].source,
                "error": views[name].error,
            }
            for name in ("portfolio", "orders", "models", "risk", "data", "system")
        },
    }
    expected_hash = hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert snapshot.control_version == 0
    assert snapshot.control_hash == expected_hash
    assert snapshot.control_hash != "0" * 64


def test_state_version_zero_snapshot_is_one_cached_immutable_value(gateway: Gateway) -> None:
    first = gateway.snapshot()
    time.sleep(0.01)
    second = gateway.snapshot()
    assert first is second
    assert first.model_dump_json() == second.model_dump_json()


def test_push_requires_authentication_and_an_initial_snapshot(gateway: Gateway) -> None:
    greet(gateway, "locked")
    assert gateway.poll("locked") is not None
    gateway.publish_event(metric_event(gateway, 1.0))
    assert gateway.poll("locked") is None

    setup(gateway, "viewer")
    assert gateway.poll("viewer") is not None
    assert gateway.poll("viewer") is not None
    gateway.publish_event(metric_event(gateway, 2.0))
    assert gateway.poll("viewer") is None

    snapshot = send(gateway, "viewer", MessageType.SNAPSHOT_REQUEST, 3)
    assert gateway.poll("viewer") == snapshot
    gateway.publish_event(metric_event(gateway, 3.0))
    pushed = gateway.poll("viewer")
    assert pushed is not None
    assert pushed.message_type is MessageType.EVENT
    assert decode_payload(pushed).entity.value == 3.0


def test_pending_metric_replacements_reuse_one_admitted_sequence(gateway: Gateway) -> None:
    subscribe(gateway)

    gateway.publish_event(metric_event(gateway, 1.0))
    gateway.publish_event(metric_event(gateway, 2.0))
    gateway.publish_event(metric_event(gateway, 3.0))
    response = send(gateway, "subscriber", MessageType.PING, 4, nonce="after-metrics")

    metric = gateway.poll("subscriber")
    pong = gateway.poll("subscriber")
    assert metric is not None and pong is not None
    assert [metric.sequence, pong.sequence] == [4, 5]
    assert metric.message_type is MessageType.EVENT
    assert decode_payload(metric).entity.value == 3.0
    assert pong == response
    assert gateway.poll("subscriber") is None


def test_pending_full_snapshots_replace_without_a_sequence_gap(gateway: Gateway) -> None:
    subscribe(gateway)
    original = gateway.snapshot()
    for version in (1, 2, 3):
        shell = original.shell.model_copy(update={"state_version": version})
        gateway.publish_snapshot(original.model_copy(update={"shell": shell}))
    response = send(gateway, "subscriber", MessageType.PING, 4, nonce="after-snapshots")

    snapshot = gateway.poll("subscriber")
    pong = gateway.poll("subscriber")
    assert snapshot is not None and pong is not None
    assert [snapshot.sequence, pong.sequence] == [4, 5]
    assert snapshot.message_type is MessageType.SNAPSHOT
    assert decode_payload(snapshot).snapshot.shell.state_version == 3
    assert pong == response


def test_projection_snapshot_uses_full_baseline_then_incremental_row_event(
    gateway: Gateway,
) -> None:
    subscribe(gateway)
    original = gateway.snapshot()
    first_metric = MetricRow(
        metric_id="metric:cpu",
        value=10.0,
        unit="percent",
        freshness=Freshness.FRESH,
        observed_at_utc=NOW,
        error=None,
    )
    first = original.model_copy(
        update={
            "shell": original.shell.model_copy(update={"state_version": 1}),
            "system": original.system.model_copy(update={"metrics": (first_metric,)}),
        }
    )
    gateway.publish_snapshot(first)
    baseline = gateway.poll("subscriber")
    assert baseline is not None
    assert baseline.message_type is MessageType.SNAPSHOT
    assert gateway.poll("subscriber") is None

    second_metric = first_metric.model_copy(update={"value": 20.0})
    second = first.model_copy(
        update={
            "shell": first.shell.model_copy(update={"state_version": 2}),
            "system": first.system.model_copy(update={"metrics": (second_metric,)}),
        }
    )
    gateway.publish_snapshot(second)

    incremental = gateway.poll("subscriber")
    assert incremental is not None
    assert incremental.message_type is MessageType.EVENT
    assert incremental.state_version == 2
    assert decode_payload(incremental).entity == second_metric
    assert gateway.poll("subscriber") is None


def test_projection_snapshot_uses_full_snapshot_when_command_specs_and_rows_change(
    gateway: Gateway,
) -> None:
    subscribe(gateway)
    original = gateway.snapshot()
    first_metric = MetricRow(
        metric_id="metric:cpu",
        value=10.0,
        unit="percent",
        freshness=Freshness.FRESH,
        observed_at_utc=NOW,
        error=None,
    )
    first = original.model_copy(
        update={
            "shell": original.shell.model_copy(update={"state_version": 1}),
            "system": original.system.model_copy(update={"metrics": (first_metric,)}),
        }
    )
    gateway.publish_snapshot(first)
    assert gateway.poll("subscriber") is not None

    second_metric = first_metric.model_copy(update={"value": 20.0})
    command_spec = CommandSpecView(
        command_type="note.add",
        payload_model="NotePayload",
        capability_id="note.add",
        reason_rule="optional",
        confirmation_level="none",
    )
    second = first.model_copy(
        update={
            "shell": first.shell.model_copy(update={"state_version": 2}),
            "command_specs": (command_spec,),
            "system": first.system.model_copy(update={"metrics": (second_metric,)}),
        }
    )
    gateway.publish_snapshot(second)

    replacement = gateway.poll("subscriber")
    assert replacement is not None
    assert replacement.message_type is MessageType.SNAPSHOT
    assert decode_payload(replacement).snapshot == second
    assert gateway.poll("subscriber") is None


def test_projection_snapshot_uses_full_snapshot_when_live_state_and_rows_change(
    gateway: Gateway,
) -> None:
    subscribe(gateway)
    original = gateway.snapshot()
    first_metric = MetricRow(
        metric_id="metric:cpu",
        value=10.0,
        unit="percent",
        freshness=Freshness.FRESH,
        observed_at_utc=NOW,
        error=None,
    )
    first = original.model_copy(
        update={
            "shell": original.shell.model_copy(update={"state_version": 1}),
            "system": original.system.model_copy(update={"metrics": (first_metric,)}),
        }
    )
    gateway.publish_snapshot(first)
    assert gateway.poll("subscriber") is not None

    account = AccountSummaryView(
        name="Primary brokerage",
        number="123456789",
        balance="1000",
        capital="900",
    )
    second = first.model_copy(
        update={
            "shell": first.shell.model_copy(update={"state_version": 2}),
            "system": first.system.model_copy(
                update={
                    "metrics": (first_metric.model_copy(update={"value": 20.0}),),
                    "live_account": account,
                }
            ),
        }
    )
    gateway.publish_snapshot(second)

    replacement = gateway.poll("subscriber")
    assert replacement is not None
    assert replacement.message_type is MessageType.SNAPSHOT
    assert decode_payload(replacement).snapshot == second
    assert gateway.poll("subscriber") is None


def test_projection_snapshot_rejects_nonadvancing_state_changes_before_mutation(
    gateway: Gateway,
) -> None:
    subscribe(gateway)
    original = gateway.snapshot()
    first = original.model_copy(
        update={"shell": original.shell.model_copy(update={"state_version": 2})}
    )
    gateway.publish_snapshot(first)
    assert gateway.poll("subscriber") is not None

    gateway.publish_snapshot(first)
    assert gateway.poll("subscriber") is None

    same_version_change = first.model_copy(
        update={
            "shell": first.shell.model_copy(update={"generated_at_utc": NOW.replace(microsecond=1)})
        }
    )
    with pytest.raises(ValueError, match="state version must advance"):
        gateway.publish_snapshot(same_version_change)
    regressive = first.model_copy(
        update={"shell": first.shell.model_copy(update={"state_version": 1})}
    )
    with pytest.raises(ValueError, match="state version must advance"):
        gateway.publish_snapshot(regressive)

    assert gateway.snapshot() == first
    assert gateway.poll("subscriber") is None


def test_required_event_overflow_sends_resnapshot_required_then_closes(gateway: Gateway) -> None:
    subscribe(gateway)
    event = alert_event(gateway)

    for _ in range(257):
        gateway.publish_event(event)

    terminal = gateway.poll("subscriber")
    assert terminal is not None
    assert terminal.sequence == 4
    assert terminal.message_type is MessageType.PROTOCOL_ERROR
    assert decode_payload(terminal) == ProtocolErrorPayload(
        code="resnapshot-required",
        safe_message="Outbound state was not preserved; request a new snapshot.",
    )
    with pytest.raises(ConnectionAbortedError, match="resnapshot-required"):
        gateway.poll("subscriber")


def test_oversized_projection_snapshot_is_rejected_before_queueing(
    gateway: Gateway,
) -> None:
    subscribe(gateway)
    original = gateway.snapshot()
    rows = tuple(
        TimelineRow(
            event_id=f"event:{index}",
            occurred_at_utc=NOW,
            impact=False,
            severity="active",
            summary="x" * 512,
            agent_id=None,
            symbol=None,
            model_id=None,
            approval_id=None,
            order_id=None,
            evidence_ids=(),
        )
        for index in range(2_100)
    )
    oversized = original.model_copy(
        update={
            "shell": original.shell.model_copy(update={"state_version": 1}),
            "timeline": original.timeline.model_copy(update={"rows": rows}),
        }
    )
    assert len(SnapshotPayload(snapshot=oversized).model_dump_json().encode("utf-8")) > (
        MAX_FRAME_BYTES
    )

    gateway.publish_snapshot(oversized)

    terminal = gateway.poll("subscriber")
    assert terminal is not None
    assert terminal.message_type is MessageType.PROTOCOL_ERROR
    assert decode_payload(terminal).code == "resnapshot-required"
    with pytest.raises(ConnectionAbortedError, match="resnapshot-required"):
        gateway.poll("subscriber")


def test_lock_stops_future_pushes(gateway: Gateway) -> None:
    subscribe(gateway, "owner")
    locked = send(gateway, "owner", MessageType.LOCK_REQUEST, 4, action="lock")
    gateway.publish_event(metric_event(gateway, 9.0))

    assert gateway.poll("owner") == locked
    assert gateway.poll("owner") is None


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


def test_malformed_state_transition_does_not_call_snapshot(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gateway, "snapshot", lambda: pytest.fail("state was accessed"))
    response = send(gateway, "new", MessageType.SNAPSHOT_REQUEST, 1)
    assert decode_payload(response).code == "locked"


def test_authenticated_session_rejects_repeated_auth_without_losing_access(
    gateway: Gateway,
) -> None:
    setup(gateway, "owner")
    repeated = send(gateway, "owner", MessageType.AUTH_UNLOCK, 3, password="wrong")
    assert decode_payload(repeated).code == "state"
    assert (
        send(gateway, "owner", MessageType.SNAPSHOT_REQUEST, 4).message_type is MessageType.SNAPSHOT
    )


def test_cli_print_pipe_name_is_exclusive_and_opens_no_state(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from vesper.platform.tui import cli

    monkeypatch.setattr(
        cli, "default_pipe_name", lambda: r"\\.\pipe\vesper-v20-tui-0123456789abcdef"
    )
    monkeypatch.setattr(cli, "Gateway", lambda *args, **kwargs: pytest.fail("state opened"))
    monkeypatch.setattr(cli, "_default_state_root", lambda: pytest.fail("LocalAppData touched"))
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


def test_cli_requires_exact_current_pipe_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from vesper.platform.tui import cli

    expected = r"\\.\pipe\vesper-v20-tui-0123456789abcdef"
    monkeypatch.setattr(cli, "default_pipe_name", lambda: expected)
    monkeypatch.setattr(cli, "Gateway", lambda *args, **kwargs: pytest.fail("state opened"))
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--state-root",
                str(tmp_path.resolve()),
                "--pipe-name",
                r"\\.\pipe\vesper-v20-tui-fedcba9876543210",
            ]
        )


def test_serving_state_root_must_equal_canonical_local_appdata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from vesper.platform.tui.cli import _serving_state_root

    local = tmp_path / "local"
    canonical = (local / "Vesper" / "v20" / "tui").resolve()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    assert _serving_state_root(None) == canonical
    assert _serving_state_root(canonical) == canonical
    with pytest.raises(ValueError, match="canonical"):
        _serving_state_root(tmp_path / "arbitrary")
    with pytest.raises(ValueError, match="canonical"):
        _serving_state_root(Path.cwd() / "vesper" / "data" / "massive")
    with pytest.raises(ValueError):
        _serving_state_root(Path("relative/state"))
    with pytest.raises(ValueError):
        _serving_state_root(Path(r"\\server\share\Vesper\v20\tui"))


def test_serving_state_root_rejects_reparse_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from vesper.platform.tui import cli

    local = tmp_path / "local"
    canonical = local / "Vesper" / "v20" / "tui"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(cli, "_contains_reparse_point", lambda path: path == canonical)
    with pytest.raises(ValueError, match="reparse"):
        cli._serving_state_root(canonical)


def test_projection_runtime_uses_only_reviewed_read_adapters_and_closes_ledger(
    tmp_path: Path,
) -> None:
    from vesper.platform.tui import cli
    from vesper.platform.tui.ports import UnavailablePort
    from vesper.platform.tui.projections import (
        EventTimelineProjection,
        LegacyStateProjection,
        NativePlatformProjection,
        PlatformRuntimeProjection,
    )
    from vesper.platform.tui.projections.repository import RepositoryProjection
    from vesper.platform.tui.projections.windows_system import WindowsSystemProjection
    from vesper.platform.tui.sqlite_ledger import LedgerClosedError

    gateway = Gateway(tmp_path / "auth")
    runtime = cli._build_projection_runtime(
        tmp_path,
        gateway,
        platform_paths=PlatformPaths.below(tmp_path / "platform"),
    )
    sources = runtime.loop._sources
    assert tuple(sources) == (
        "native.agents",
        "native.portfolio",
        "native.orders",
        "native.models",
        "legacy.risk",
        "native.data",
        "native.memory",
        "platform.runtime",
        "repository.system",
        "windows.system",
        "events.timeline",
    )
    assert isinstance(sources["native.agents"], NativePlatformProjection)
    assert isinstance(sources["native.portfolio"], UnavailablePort)
    assert isinstance(sources["native.orders"], UnavailablePort)
    assert isinstance(sources["native.models"], UnavailablePort)
    assert isinstance(sources["legacy.risk"], LegacyStateProjection)
    assert sources["legacy.risk"]._state_path == Path("data/engine_state.json")
    assert isinstance(sources["native.data"], UnavailablePort)
    assert isinstance(sources["native.memory"], UnavailablePort)
    assert isinstance(sources["platform.runtime"], PlatformRuntimeProjection)
    assert isinstance(sources["repository.system"], RepositoryProjection)
    assert isinstance(sources["windows.system"], WindowsSystemProjection)
    assert isinstance(sources["events.timeline"], EventTimelineProjection)
    assert runtime.event_store._ledger.path == tmp_path / "operations.sqlite3"
    assert runtime.note_store._ledger is runtime.event_store._ledger
    assert gateway.search_service is runtime.search_service

    runtime.close()
    with pytest.raises(LedgerClosedError):
        runtime.event_store.latest(1)
    with pytest.raises(LedgerClosedError):
        runtime.note_store.search("note", NoteFilters(), 1)


def test_projection_reads_never_cross_mutating_or_protected_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import builtins
    import io
    import os
    import sqlite3
    import subprocess

    from vesper.execution import broker as broker_module
    from vesper.platform.tui import cli
    from vesper.platform.tui.views import Freshness
    from vesper.scheduler import engine as scheduler_module

    access_counts = {
        "broker": 0,
        "scheduler": 0,
        "training": 0,
        "protected_path": 0,
    }

    def forbidden_boundary(name: str):
        def blocked(*_args, **_kwargs):
            access_counts[name] += 1
            raise AssertionError(f"projection crossed the {name} boundary")

        return blocked

    monkeypatch.setattr(broker_module.PaperBroker, "__init__", forbidden_boundary("broker"))
    monkeypatch.setattr(broker_module.AlpacaBroker, "__init__", forbidden_boundary("broker"))
    monkeypatch.setattr(
        scheduler_module.MarketScheduler,
        "__init__",
        forbidden_boundary("scheduler"),
    )

    original_popen = subprocess.Popen
    original_run = subprocess.run

    def is_training_command(command: object) -> bool:
        if isinstance(command, (str, bytes, os.PathLike)):
            parts = (os.fsdecode(command),)
        else:
            try:
                parts = tuple(os.fsdecode(part) for part in command)  # type: ignore[arg-type]
            except TypeError:
                return False
        return any("train_model.py" in part.replace("\\", "/").casefold() for part in parts)

    def guarded_popen(command, *args, **kwargs):
        if is_training_command(command):
            access_counts["training"] += 1
            raise AssertionError("projection launched model training")
        return original_popen(command, *args, **kwargs)

    def guarded_run(command, *args, **kwargs):
        if is_training_command(command):
            access_counts["training"] += 1
            raise AssertionError("projection launched model training")
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", guarded_popen)
    monkeypatch.setattr(subprocess, "run", guarded_run)

    def is_protected_path(value: object) -> bool:
        try:
            normalized = os.fsdecode(value).replace("\\", "/").casefold().strip("/")
        except TypeError:
            return False
        return any(
            marker in normalized for marker in ("vesper/data/massive", "vesper/data/model_research")
        )

    def guarded(original):
        def wrapper(path, *args, **kwargs):
            if is_protected_path(path):
                access_counts["protected_path"] += 1
                raise PermissionError("protected V20 data is read-only and outside TUI scope")
            return original(path, *args, **kwargs)

        return wrapper

    monkeypatch.setattr(builtins, "open", guarded(builtins.open))
    monkeypatch.setattr(io, "open", guarded(io.open))
    monkeypatch.setattr(os, "open", guarded(os.open))
    monkeypatch.setattr(os, "stat", guarded(os.stat))
    monkeypatch.setattr(os, "lstat", guarded(os.lstat))
    monkeypatch.setattr(os, "scandir", guarded(os.scandir))
    monkeypatch.setattr(sqlite3, "connect", guarded(sqlite3.connect))

    gateway = Gateway(tmp_path / "auth")
    runtime = cli._build_projection_runtime(
        tmp_path,
        gateway,
        platform_paths=PlatformPaths.below(tmp_path / "platform"),
    )
    try:
        samples = {source_id: source.read() for source_id, source in runtime.loop._sources.items()}
        snapshot = runtime.loop._builder.build(samples=samples, generated_at_utc=NOW)
        gateway.publish_snapshot(snapshot)
        setup(gateway)
        search_response = send(
            gateway,
            "first",
            MessageType.SEARCH_REQUEST,
            3,
            request_id=1,
            query="boundary probe",
            filters={"kinds": [], "screens": [], "source": None},
            limit=100,
        )
        search_payload = decode_payload(search_response)

        assert snapshot.portfolio.freshness is Freshness.UNAVAILABLE
        assert snapshot.orders.freshness is Freshness.UNAVAILABLE
        assert isinstance(search_payload, SearchResultsPayload)
        assert search_payload.error is None
        assert access_counts == {
            "broker": 0,
            "scheduler": 0,
            "training": 0,
            "protected_path": 0,
        }
    finally:
        runtime.close()


def test_projection_runtime_degrades_corrupt_ledger_without_losing_other_sources(
    tmp_path: Path,
) -> None:
    from vesper.platform.tui import cli
    from vesper.platform.tui.ports import UnavailablePort
    from vesper.platform.tui.projections import NativePlatformProjection

    (tmp_path / "operations.sqlite3").write_bytes(b"not sqlite")
    gateway = Gateway(tmp_path / "auth")
    runtime = cli._build_projection_runtime(
        tmp_path,
        gateway,
        platform_paths=PlatformPaths.below(tmp_path / "platform"),
    )

    assert runtime.event_store is None
    assert isinstance(runtime.loop._sources["events.timeline"], UnavailablePort)
    assert isinstance(runtime.loop._sources["native.agents"], NativePlatformProjection)
    setup(gateway)
    response = send(
        gateway,
        "first",
        MessageType.SEARCH_REQUEST,
        3,
        request_id=1,
        query="AAPL",
        filters={"kinds": [], "screens": [], "source": None},
        limit=10,
    )
    payload = decode_payload(response)
    assert isinstance(payload, SearchResultsPayload)
    assert payload.error == "Persisted search history is unavailable."
    runtime.close()


def test_projection_runtime_degrades_one_adapter_initialization_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from vesper.platform.tui import cli
    from vesper.platform.tui.ports import UnavailablePort
    from vesper.platform.tui.projections import NativePlatformProjection

    def fail_windows(**kwargs):
        raise OSError("host API unavailable")

    monkeypatch.setattr(cli, "WindowsSystemProjection", fail_windows)
    runtime = cli._build_projection_runtime(
        tmp_path,
        Gateway(tmp_path / "auth"),
        platform_paths=PlatformPaths.below(tmp_path / "platform"),
    )

    assert isinstance(runtime.loop._sources["windows.system"], UnavailablePort)
    assert isinstance(runtime.loop._sources["native.agents"], NativePlatformProjection)
    runtime.close()


def test_projection_runtime_does_not_hide_adapter_programmer_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from vesper.platform.tui import cli

    def fail_native(_repository_root: Path):
        raise TypeError("adapter wiring bug")

    monkeypatch.setattr(cli, "NativePlatformProjection", fail_native)

    with pytest.raises(TypeError, match="adapter wiring bug"):
        cli._build_projection_runtime(
            tmp_path,
            Gateway(tmp_path / "auth"),
            platform_paths=PlatformPaths.below(tmp_path / "platform"),
        )


def test_cli_starts_projection_loop_and_closes_it_before_return(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from vesper.platform.tui import cli

    expected_pipe = r"\\.\pipe\vesper-v20-tui-0123456789abcdef"
    started = threading.Event()
    stopped = threading.Event()
    closed = threading.Event()

    class FakeLoop:
        def run(self, stop_event: threading.Event) -> None:
            started.set()
            stop_event.wait(2)
            stopped.set()

    class FakeRuntime:
        loop = FakeLoop()

        def close(self) -> None:
            assert stopped.is_set()
            closed.set()

    class FakeServer:
        def __init__(self, name: str) -> None:
            assert name == expected_pipe
            self.ready_event = threading.Event()
            self.ready_event.set()
            self.active_client_count = 0

        def serve(self, handler, stop_event, *, connection_factory) -> None:
            assert connection_factory is not None
            assert started.wait(1)
            stop_event.set()

        def stop(self) -> None:
            pass

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(cli, "default_pipe_name", lambda: expected_pipe)
    monkeypatch.setattr(cli, "WindowsPipeServer", FakeServer)
    monkeypatch.setattr(
        cli,
        "_build_projection_runtime",
        lambda state_root, gateway: FakeRuntime(),
    )

    assert cli.main([]) == 0
    assert stopped.is_set()
    assert closed.is_set()


def test_projection_invariant_failure_stops_server_and_closes_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from vesper.platform.tui import cli

    expected_pipe = r"\\.\pipe\vesper-v20-tui-0123456789abcdef"
    closed = threading.Event()

    class FailingLoop:
        def run(self, stop_event: threading.Event) -> None:
            raise AssertionError("projection invariant")

    class FakeRuntime:
        loop = FailingLoop()

        def close(self) -> None:
            closed.set()

    class FakeServer:
        def __init__(self, name: str) -> None:
            self.ready_event = threading.Event()
            self.active_client_count = 0
            self.stopped = threading.Event()

        def serve(self, handler, stop_event, *, connection_factory) -> None:
            assert stop_event.wait(1)

        def stop(self) -> None:
            self.stopped.set()

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(cli, "default_pipe_name", lambda: expected_pipe)
    monkeypatch.setattr(cli, "WindowsPipeServer", FakeServer)
    monkeypatch.setattr(
        cli,
        "_build_projection_runtime",
        lambda state_root, gateway: FakeRuntime(),
    )

    with pytest.raises(RuntimeError, match="projection loop failed") as failure:
        cli.main([])
    assert isinstance(failure.value.__cause__, AssertionError)
    assert closed.is_set()


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


def test_coordinator_stop_waits_until_all_admitted_work_is_drained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui import cli

    entered = threading.Event()
    release = threading.Event()
    completed = threading.Event()

    class BlockingGateway:
        def handle(self, client_id: str, message: WireEnvelope):
            entered.set()
            release.wait(2)
            completed.set()
            return (message,)

        def disconnect(self, client_id: str) -> None:
            pass

    monkeypatch.setattr(cli, "_COORDINATOR_WAIT_SECONDS", 0.01)
    coordinator = cli._GatewayCoordinator(BlockingGateway())  # type: ignore[arg-type]
    errors: list[BaseException] = []

    def invoke() -> None:
        try:
            coordinator.handle("client", envelope(MessageType.PING, 1, {"nonce": "one"}))
        except BaseException as error:
            errors.append(error)

    caller = threading.Thread(target=invoke)
    caller.start()
    assert entered.wait(1)
    stopping = threading.Thread(target=coordinator.stop)
    stopping.start()
    time.sleep(0.05)
    assert stopping.is_alive()
    release.set()
    caller.join(2)
    stopping.join(2)
    assert completed.is_set()
    assert not stopping.is_alive()
    assert len(errors) <= 1


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


def test_connection_factory_uses_one_fifo_for_responses_and_idle_pushes(
    gateway: Gateway,
) -> None:
    from vesper.platform.tui.cli import _GatewayCoordinator, _gateway_connection_factory

    setup(gateway, "seed")
    gateway.disconnect("seed")
    coordinator = _GatewayCoordinator(gateway)
    connection, close = _gateway_connection_factory(coordinator)()

    def receive(message: WireEnvelope) -> WireEnvelope:
        body = connection(message.model_dump_json().encode("utf-8"))
        assert body is not None
        return WireEnvelope.model_validate_json(body)

    receive(
        envelope(
            MessageType.CLIENT_HELLO,
            1,
            {
                "client_version": "0.1.0",
                "supported_schema_versions": [1],
            },
        )
    )
    receive(envelope(MessageType.AUTH_UNLOCK, 2, {"password": "correct horse"}))
    receive(envelope(MessageType.SNAPSHOT_REQUEST, 3, {}))

    gateway.publish_event(metric_event(gateway, 42.0))
    first = receive(envelope(MessageType.PING, 4, {"nonce": "queued-after-push"}))
    assert first.message_type is MessageType.EVENT
    assert first.sequence == 4
    pushed_response = connection.poll()
    assert pushed_response is not None
    pong = WireEnvelope.model_validate_json(pushed_response)
    assert pong.message_type is MessageType.PONG
    assert pong.sequence == 5

    close()
    coordinator.stop()


def test_connection_close_after_coordinator_stop_releases_controller_exactly_once(
    gateway: Gateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui.cli import _GatewayCoordinator, _gateway_connection_factory

    setup(gateway, "seed")
    gateway.disconnect("seed")
    disconnects: list[str] = []
    original_disconnect = gateway.disconnect

    def record_disconnect(client_id: str) -> None:
        disconnects.append(client_id)
        original_disconnect(client_id)

    monkeypatch.setattr(gateway, "disconnect", record_disconnect)
    coordinator = _GatewayCoordinator(gateway)
    handle, close = _gateway_connection_factory(coordinator)()

    def round_trip(message: WireEnvelope) -> WireEnvelope:
        body = handle(message.model_dump_json().encode("utf-8"))
        assert body is not None
        return WireEnvelope.model_validate_json(body)

    round_trip(
        envelope(
            MessageType.CLIENT_HELLO,
            1,
            {"client_version": "0.1.0", "supported_schema_versions": [1]},
        )
    )
    round_trip(envelope(MessageType.AUTH_UNLOCK, 2, {"password": "correct horse"}))
    round_trip(envelope(MessageType.LEASE_REQUEST, 3, {"action": "take-control"}))
    assert gateway.controller_id is not None
    coordinator.stop()
    close()
    close()
    assert gateway.controller_id is None
    assert len(disconnects) == 1


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
