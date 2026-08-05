from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vesper.platform.ops.alerts import (
    MAX_NOTIFICATION_CLEANUP_IDS,
    AtomicAlertRecordStore,
    OperationsAlertRecord,
    OperationsAlertRouter,
)
from vesper.platform.ops.notification_health import AtomicNotificationFailureHealthSink
from vesper.platform.ops.policy import OperationsState, ResourceState
from vesper.platform.tui.notifications import GENERIC_ATTENTION_TEXT, WindowsNotificationPort


NOW = datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)


class Sessions:
    def __init__(self, authenticated: bool = False) -> None:
        self.authenticated = authenticated

    def has_authenticated_client(self) -> bool:
        return self.authenticated


class Backend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def show(self, app_id: str, xml: str) -> None:
        self.calls.append((app_id, xml))


class HealthyBackend(Backend):
    def __init__(self, health: AtomicNotificationFailureHealthSink) -> None:
        super().__init__()
        self._health = health

    def show(self, app_id: str, xml: str) -> None:
        super().show(app_id, xml)
        self._health.record_notification_healthy()


class FailingResolveNotifications:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.resolve_calls: list[str] = []
        self.overflow_calls: list[str] = []

    def send_attention(self, alert_id: str):
        self.sent.append(alert_id)

    def resolve(self, alert_id: str) -> None:
        self.resolve_calls.append(alert_id)
        raise RuntimeError("private-history-cleanup-failure")

    def record_cleanup_overflow(self, alert_id: str) -> None:
        self.overflow_calls.append(alert_id)


class RecordingNotifications:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.resolve_calls: list[str] = []

    def send_attention(self, alert_id: str) -> None:
        self.sent.append(alert_id)

    def resolve(self, alert_id: str) -> None:
        self.resolve_calls.append(alert_id)


def state(incident_id: str | None, *, has_incident: bool | None = None) -> OperationsState:
    return OperationsState(
        resources=ResourceState(
            gpu_percent=0,
            gpu_temperature_c=30,
            memory_percent=10,
            disk_free_gb=100,
            recent_errors=0,
            qwen_lease_active=False,
        ),
        has_incident=incident_id is not None if has_incident is None else has_incident,
        incident_id=incident_id,
    )


def test_explicit_incident_persists_opaque_generic_alert_and_coalesces(tmp_path: Path) -> None:
    backend = Backend()
    router = OperationsAlertRouter(
        WindowsNotificationPort(Sessions(), backend=backend),
        AtomicAlertRecordStore(tmp_path),
    )

    router.observe(state("incident:nvda-risk"), NOW)
    router.observe(state("incident:nvda-risk"), NOW)

    raw = (tmp_path / "attention-alert.json").read_text(encoding="utf-8")
    record = json.loads(raw)
    assert set(record) == {
        "alert_id",
        "created_at_utc",
        "notification_cleanup_alert_ids",
        "notification_cleanup_overflow",
        "notification_cleanup_pending",
        "resolved_at_utc",
        "severity",
    }
    assert record["alert_id"].startswith("alert:")
    assert len(record["alert_id"]) == len("alert:") + 32
    assert record["severity"] == "urgent"
    assert record["resolved_at_utc"] is None
    assert record["notification_cleanup_pending"] is False
    assert record["notification_cleanup_alert_ids"] == []
    assert record["notification_cleanup_overflow"] is False
    assert "nvda" not in raw.casefold()
    assert len(backend.calls) == 1
    assert GENERIC_ATTENTION_TEXT in backend.calls[0][1]
    assert "nvda" not in backend.calls[0][1].casefold()


def test_any_string_incident_id_is_hashed_before_safe_alert_validation(tmp_path: Path) -> None:
    backend = Backend()
    router = OperationsAlertRouter(
        WindowsNotificationPort(Sessions(), backend=backend),
        AtomicAlertRecordStore(tmp_path),
    )
    private_incident = "private incident/NVDA weight " + "x" * 200

    router.observe(state(private_incident), NOW)

    raw = (tmp_path / "attention-alert.json").read_text(encoding="utf-8")
    assert private_incident not in raw
    assert len(backend.calls) == 1
    assert private_incident not in backend.calls[0][1]


def test_existing_alert_record_without_cleanup_queue_remains_readable(tmp_path: Path) -> None:
    store = AtomicAlertRecordStore(tmp_path)
    store.path.write_text(
        json.dumps(
            {
                "alert_id": "alert:0123456789abcdef0123456789abcdef",
                "severity": "resolved",
                "created_at_utc": "2026-08-04T15:00:00Z",
                "resolved_at_utc": "2026-08-04T15:01:00Z",
                "notification_cleanup_pending": True,
            }
        ),
        encoding="utf-8",
    )

    record = store.read()

    assert record is not None
    assert record.notification_cleanup_alert_ids == ()
    assert record.notification_cleanup_overflow is False


def test_suppressed_incident_sends_after_last_authenticated_tui_closes(
    tmp_path: Path,
) -> None:
    sessions = Sessions(authenticated=True)
    backend = Backend()
    router = OperationsAlertRouter(
        WindowsNotificationPort(sessions, backend=backend),
        AtomicAlertRecordStore(tmp_path),
    )

    router.observe(state("incident:service-failure"), NOW)
    assert backend.calls == []

    sessions.authenticated = False
    router.observe(state("incident:service-failure"), NOW)
    assert len(backend.calls) == 1


def test_explicit_resolution_allows_the_same_incident_to_notify_again(tmp_path: Path) -> None:
    backend = Backend()
    store = AtomicAlertRecordStore(tmp_path)
    router = OperationsAlertRouter(
        WindowsNotificationPort(Sessions(), backend=backend),
        store,
    )

    router.observe(state("incident:service-failure"), NOW)
    router.observe(state(None), NOW)
    resolved = store.read()
    assert resolved is not None
    assert resolved.severity == "resolved"
    assert resolved.resolved_at_utc == NOW

    router.observe(state("incident:service-failure"), NOW)
    assert len(backend.calls) == 2


def test_restart_retries_pending_notification_cleanup_once(tmp_path: Path) -> None:
    failing = FailingResolveNotifications()
    store = AtomicAlertRecordStore(tmp_path)
    router = OperationsAlertRouter(failing, store)
    router.observe(state("incident:service-failure"), NOW)

    try:
        router.observe(state(None), NOW + timedelta(seconds=1))
    except RuntimeError as error:
        assert str(error) == "notification cleanup remains pending"
    else:
        raise AssertionError("cleanup failure must remain visible")

    pending = store.read()
    assert pending is not None
    assert pending.severity == "resolved"
    assert pending.notification_cleanup_pending is False
    assert pending.notification_cleanup_alert_ids == (pending.alert_id,)

    restarted_notifications = RecordingNotifications()
    restarted = OperationsAlertRouter(restarted_notifications, store)
    restarted.observe(state(None), NOW + timedelta(seconds=2))
    restarted.observe(state(None), NOW + timedelta(seconds=3))

    cleaned = store.read()
    assert cleaned is not None
    assert cleaned.notification_cleanup_pending is False
    assert cleaned.notification_cleanup_alert_ids == ()
    assert restarted_notifications.resolve_calls == [pending.alert_id]


def test_resolution_time_never_precedes_creation_when_the_clock_rolls_back(
    tmp_path: Path,
) -> None:
    store = AtomicAlertRecordStore(tmp_path)
    router = OperationsAlertRouter(
        WindowsNotificationPort(Sessions(), backend=Backend()),
        store,
    )
    router.observe(state("incident:service-failure"), NOW)

    router.observe(state(None), NOW - timedelta(hours=1))

    resolved = store.read()
    assert resolved is not None
    assert resolved.created_at_utc == NOW
    assert resolved.resolved_at_utc == NOW


def test_reopened_occurrence_is_strictly_new_when_the_clock_repeats_or_rolls_back(
    tmp_path: Path,
) -> None:
    store = AtomicAlertRecordStore(tmp_path)
    router = OperationsAlertRouter(
        WindowsNotificationPort(Sessions(), backend=Backend()),
        store,
    )
    router.observe(state("incident:service-failure"), NOW)
    router.observe(state(None), NOW)
    resolved = store.read()
    assert resolved is not None

    router.observe(state("incident:service-failure"), NOW - timedelta(hours=1))

    reopened = store.read()
    assert reopened is not None
    assert reopened.alert_id == resolved.alert_id
    assert reopened.severity == "urgent"
    assert reopened.created_at_utc > resolved.resolved_at_utc


def test_has_incident_without_explicit_id_never_notifies_or_persists(tmp_path: Path) -> None:
    backend = Backend()
    router = OperationsAlertRouter(
        WindowsNotificationPort(Sessions(), backend=backend),
        AtomicAlertRecordStore(tmp_path),
    )

    router.observe(state(None, has_incident=True), NOW)

    assert backend.calls == []
    assert not (tmp_path / "attention-alert.json").exists()


def test_incident_switch_keeps_new_alert_truth_when_old_history_cleanup_fails(
    tmp_path: Path,
) -> None:
    notifications = FailingResolveNotifications()
    store = AtomicAlertRecordStore(tmp_path)
    router = OperationsAlertRouter(notifications, store)

    router.observe(state("incident:first"), NOW)
    first = store.read()
    assert first is not None

    router.observe(state("incident:second"), NOW)

    current = store.read()
    assert current is not None
    assert current.alert_id != first.alert_id
    assert current.severity == "urgent"
    assert current.notification_cleanup_alert_ids == (first.alert_id,)
    assert notifications.sent == [first.alert_id, current.alert_id]
    assert notifications.resolve_calls == [first.alert_id]

    restarted_notifications = RecordingNotifications()
    restarted = OperationsAlertRouter(restarted_notifications, store)
    restarted.observe(state("incident:second"), NOW + timedelta(seconds=1))
    restarted.observe(state("incident:second"), NOW + timedelta(seconds=2))

    cleaned = store.read()
    assert cleaned is not None
    assert cleaned.alert_id == current.alert_id
    assert cleaned.severity == "urgent"
    assert cleaned.notification_cleanup_alert_ids == ()
    assert restarted_notifications.resolve_calls == [first.alert_id]


def test_cleanup_success_before_queue_write_crash_retries_idempotently(
    tmp_path: Path,
    monkeypatch,
) -> None:
    notifications = RecordingNotifications()
    store = AtomicAlertRecordStore(tmp_path)
    router = OperationsAlertRouter(notifications, store)
    router.observe(state("incident:first"), NOW)
    first = store.read()
    assert first is not None
    original_write = store.write
    fail_removal = True

    def flaky_write(record) -> None:
        nonlocal fail_removal
        persisted = store.read()
        if (
            fail_removal
            and persisted is not None
            and persisted.alert_id != first.alert_id
            and persisted.notification_cleanup_alert_ids
            and not record.notification_cleanup_alert_ids
        ):
            fail_removal = False
            raise OSError("simulated crash after history cleanup")
        original_write(record)

    monkeypatch.setattr(store, "write", flaky_write)
    router.observe(state("incident:second"), NOW + timedelta(seconds=1))

    pending = store.read()
    assert pending is not None
    assert pending.alert_id != first.alert_id
    assert pending.notification_cleanup_alert_ids == (first.alert_id,)
    assert notifications.resolve_calls == [first.alert_id]

    restarted_notifications = RecordingNotifications()
    restarted = OperationsAlertRouter(restarted_notifications, store)
    restarted.observe(state("incident:second"), NOW + timedelta(seconds=2))

    cleaned = store.read()
    assert cleaned is not None
    assert cleaned.alert_id == pending.alert_id
    assert cleaned.notification_cleanup_alert_ids == ()
    assert restarted_notifications.resolve_calls == [first.alert_id]


def test_cleanup_queue_is_bounded_deduplicated_and_reports_generic_overflow(
    tmp_path: Path,
) -> None:
    notifications = FailingResolveNotifications()
    store = AtomicAlertRecordStore(tmp_path)
    router = OperationsAlertRouter(notifications, store)

    for index in range(MAX_NOTIFICATION_CLEANUP_IDS + 2):
        router.observe(
            state(f"private incident {index} / NVDA"),
            NOW + timedelta(seconds=index),
        )

    current = store.read()
    assert current is not None
    assert current.severity == "urgent"
    assert len(current.notification_cleanup_alert_ids) == MAX_NOTIFICATION_CLEANUP_IDS
    assert len(set(current.notification_cleanup_alert_ids)) == MAX_NOTIFICATION_CLEANUP_IDS
    assert current.alert_id not in current.notification_cleanup_alert_ids
    assert current.notification_cleanup_overflow is True
    assert notifications.overflow_calls == [current.alert_id]
    raw = store.path.read_text(encoding="utf-8")
    assert "NVDA" not in raw
    assert "private incident" not in raw


def test_restart_reasserts_persisted_overflow_after_later_healthy_toast(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = AtomicAlertRecordStore(tmp_path)
    queued_ids = tuple(f"alert:queued-{index}" for index in range(MAX_NOTIFICATION_CLEANUP_IDS))
    store.write(
        OperationsAlertRecord(
            alert_id="alert:old-current",
            severity="urgent",
            created_at_utc=NOW,
            resolved_at_utc=None,
            notification_cleanup_alert_ids=queued_ids,
        )
    )
    original_write = store.write
    crash_after_overflow_write = True

    def crashing_write(record: OperationsAlertRecord) -> None:
        nonlocal crash_after_overflow_write
        original_write(record)
        if crash_after_overflow_write and record.notification_cleanup_overflow:
            crash_after_overflow_write = False
            raise RuntimeError("simulated crash before overflow health report")

    monkeypatch.setattr(store, "write", crashing_write)
    crashed_router = OperationsAlertRouter(RecordingNotifications(), store)

    try:
        crashed_router.observe(state("private incident/NVDA"), NOW + timedelta(seconds=1))
    except RuntimeError as error:
        assert str(error) == "simulated crash before overflow health report"
    else:
        raise AssertionError("overflow write must complete before the simulated crash")

    persisted = store.read()
    assert persisted is not None
    assert persisted.notification_cleanup_overflow is True

    health = AtomicNotificationFailureHealthSink(tmp_path, clock=lambda: NOW)
    backend = HealthyBackend(health)
    restarted = OperationsAlertRouter(
        WindowsNotificationPort(Sessions(), backend=backend, health=health),
        store,
    )

    restarted.observe(state("private incident/NVDA"), NOW + timedelta(seconds=2))

    assert len(backend.calls) == 1
    assert json.loads(health.path.read_text(encoding="utf-8")) == {
        "code": "notification-delivery-failed",
        "observed_at_utc": "2026-08-04T15:00:00Z",
        "state": "failed",
    }
    raw_health = health.path.read_text(encoding="utf-8")
    assert "alert:" not in raw_health
    assert "NVDA" not in raw_health
    assert "private incident" not in raw_health
