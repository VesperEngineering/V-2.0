from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from vesper.platform.ops.alerts import AtomicAlertRecordStore, OperationsAlertRecord
from vesper.platform.ops.notification_health import AtomicNotificationFailureHealthSink
from vesper.platform.tui.notifications import GENERIC_ATTENTION_TEXT
from vesper.platform.tui.projections.operations_status import (
    AttentionAlertProjection,
    NotificationHealthProjection,
)
from vesper.platform.tui.views import Freshness


NOW = datetime(2026, 8, 4, 16, 0, tzinfo=timezone.utc)
RESOLVED = NOW + timedelta(minutes=1)


@pytest.mark.parametrize(
    ("severity", "resolved_at", "observed_at"),
    (("urgent", None, NOW), ("resolved", RESOLVED, RESOLVED)),
)
def test_attention_projection_maps_opaque_record_to_exact_generic_alert(
    tmp_path: Path,
    severity: str,
    resolved_at: datetime | None,
    observed_at: datetime,
) -> None:
    store = AtomicAlertRecordStore(tmp_path)
    store.write(
        OperationsAlertRecord(
            alert_id="alert:0123456789abcdef0123456789abcdef",
            severity=severity,
            created_at_utc=NOW,
            resolved_at_utc=resolved_at,
        )
    )

    sample = AttentionAlertProjection(tmp_path).read()

    assert sample.freshness is Freshness.FRESH
    assert sample.observed_at_utc == observed_at
    assert sample.error is None
    assert sample.value is not None
    assert len(sample.value.alerts) == 1
    alert = sample.value.alerts[0]
    assert alert.alert_id == "alert:0123456789abcdef0123456789abcdef"
    assert alert.severity == severity
    assert alert.summary == GENERIC_ATTENTION_TEXT
    assert alert.created_at_utc == NOW
    assert alert.resolved_at_utc == resolved_at


def test_attention_projection_missing_or_corrupt_state_is_unavailable_and_read_only(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    absent = AttentionAlertProjection(missing).read()

    assert absent.freshness is Freshness.UNAVAILABLE
    assert absent.value is None
    assert absent.error == "Attention alert state is unavailable."
    assert not missing.exists()

    corrupt_root = tmp_path / "corrupt"
    corrupt_root.mkdir()
    corrupt_path = corrupt_root / "attention-alert.json"
    corrupt_path.write_text('{"private":"NVDA order detail"}', encoding="utf-8")
    before = corrupt_path.read_bytes()

    corrupt = AttentionAlertProjection(corrupt_root).read()

    assert corrupt.freshness is Freshness.UNAVAILABLE
    assert corrupt.value is None
    assert corrupt.error == "Attention alert state is invalid."
    assert "NVDA" not in (corrupt.error or "")
    assert corrupt_path.read_bytes() == before
    assert tuple(corrupt_root.iterdir()) == (corrupt_path,)


def test_notification_failure_sink_persists_only_generic_health_and_projects_service(
    tmp_path: Path,
) -> None:
    sink = AtomicNotificationFailureHealthSink(tmp_path, clock=lambda: NOW)

    sink.record_notification_failure("alert:opaque", "private-backend-detail")

    raw = (tmp_path / "notification-health.json").read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert payload == {
        "code": "notification-delivery-failed",
        "observed_at_utc": "2026-08-04T16:00:00Z",
        "state": "failed",
    }
    assert "opaque" not in raw
    assert "private-backend-detail" not in raw
    assert not tuple(tmp_path.glob("*.tmp"))

    sample = NotificationHealthProjection(tmp_path, clock=lambda: NOW).read()
    assert sample.freshness is Freshness.FRESH
    assert sample.observed_at_utc == NOW
    assert sample.value is not None
    assert sample.value.services_error is None
    assert sample.value.services is not None
    assert len(sample.value.services) == 1
    service = sample.value.services[0]
    assert service.service_id == "service:windows-notifications"
    assert service.state == "failed"
    assert service.health_reason == "Windows notification delivery failed."
    assert service.observed_at_utc == NOW


def test_notification_success_replaces_failure_and_projects_running_service(
    tmp_path: Path,
) -> None:
    sink = AtomicNotificationFailureHealthSink(tmp_path, clock=lambda: NOW)
    sink.record_notification_failure("alert:opaque", "private-backend-detail")

    sink.record_notification_healthy()

    raw = (tmp_path / "notification-health.json").read_text(encoding="utf-8")
    assert json.loads(raw) == {
        "code": "notification-delivery-healthy",
        "observed_at_utc": "2026-08-04T16:00:00Z",
        "state": "healthy",
    }
    sample = NotificationHealthProjection(tmp_path, clock=lambda: NOW).read()
    assert sample.freshness is Freshness.FRESH
    assert sample.value is not None
    assert sample.value.services is not None
    assert len(sample.value.services) == 1
    service = sample.value.services[0]
    assert service.service_id == "service:windows-notifications"
    assert service.state == "running"
    assert service.health_reason == "Windows notification delivery is healthy."
    assert service.observed_at_utc == NOW


def test_old_notification_success_is_stale_and_does_not_claim_running(
    tmp_path: Path,
) -> None:
    observed_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    sink = AtomicNotificationFailureHealthSink(tmp_path, clock=lambda: observed_at)
    sink.record_notification_healthy()

    sample = NotificationHealthProjection(tmp_path).read()

    assert sample.freshness is Freshness.STALE
    assert sample.observed_at_utc == observed_at
    assert sample.error == "Notification health is older than 300 seconds."
    assert sample.value is not None
    assert sample.value.services is not None
    assert len(sample.value.services) == 1
    service = sample.value.services[0]
    assert service.state == "unavailable"
    assert service.health_reason == "Windows notification delivery health is stale."
    assert service.observed_at_utc == observed_at


def test_old_notification_failure_stays_failed_and_is_age_marked(
    tmp_path: Path,
) -> None:
    observed_at = NOW - timedelta(minutes=10)
    sink = AtomicNotificationFailureHealthSink(tmp_path, clock=lambda: observed_at)
    sink.record_notification_failure("alert:opaque", "private-backend-detail")

    sample = NotificationHealthProjection(tmp_path, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.STALE
    assert sample.observed_at_utc == observed_at
    assert sample.error == "Notification health is older than 300 seconds."
    assert sample.value is not None
    assert sample.value.services is not None
    assert len(sample.value.services) == 1
    service = sample.value.services[0]
    assert service.state == "failed"
    assert service.health_reason == "Windows notification delivery failed."
    assert service.observed_at_utc == observed_at


def test_notification_health_projection_rejects_future_observation(
    tmp_path: Path,
) -> None:
    sink = AtomicNotificationFailureHealthSink(tmp_path, clock=lambda: NOW)
    sink.record_notification_healthy()

    sample = NotificationHealthProjection(
        tmp_path,
        clock=lambda: NOW - timedelta(seconds=1),
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.observed_at_utc is None
    assert sample.error == "Notification health timestamp is in the future."


def test_notification_health_projection_rejects_negative_liveness_window(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="stale_after cannot be negative"):
        NotificationHealthProjection(tmp_path, stale_after=timedelta(seconds=-1))


def test_notification_health_projection_fails_closed_when_clock_is_not_utc(
    tmp_path: Path,
) -> None:
    sink = AtomicNotificationFailureHealthSink(tmp_path, clock=lambda: NOW)
    sink.record_notification_healthy()
    eastern_now = datetime(
        2026,
        8,
        4,
        12,
        0,
        tzinfo=timezone(timedelta(hours=-4)),
    )

    sample = NotificationHealthProjection(tmp_path, clock=lambda: eastern_now).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.observed_at_utc is None
    assert sample.error == "Notification health clock did not return UTC."


def test_notification_health_projection_missing_or_corrupt_state_is_unavailable_and_read_only(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-health"
    absent = NotificationHealthProjection(missing).read()

    assert absent.freshness is Freshness.UNAVAILABLE
    assert absent.value is None
    assert absent.error == "Notification health state is unavailable."
    assert not missing.exists()

    corrupt_root = tmp_path / "corrupt-health"
    corrupt_root.mkdir()
    corrupt_path = corrupt_root / "notification-health.json"
    corrupt_path.write_text('{"error":"private toast error"}', encoding="utf-8")
    before = corrupt_path.read_bytes()

    corrupt = NotificationHealthProjection(corrupt_root).read()

    assert corrupt.freshness is Freshness.UNAVAILABLE
    assert corrupt.value is None
    assert corrupt.error == "Notification health state is invalid."
    assert "private" not in (corrupt.error or "")
    assert corrupt_path.read_bytes() == before
    assert tuple(corrupt_root.iterdir()) == (corrupt_path,)
