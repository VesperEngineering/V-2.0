"""Read-only projections of daemon-owned generic attention and health receipts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from vesper.platform.ops.alerts import OperationsAlertRecord
from vesper.platform.ops.notification_health import NotificationHealthRecord
from vesper.platform.ops.supervisor import validate_state_root
from vesper.platform.tui.alert_dismissals import (
    AlertDismissalStore,
    AlertDismissalUnavailable,
)
from vesper.platform.tui.notifications import GENERIC_ATTENTION_TEXT
from vesper.platform.tui.ports import AttentionFacts, SourceSample, SystemFacts
from vesper.platform.tui.views import (
    AlertView,
    Freshness,
    ServiceRow,
    SystemHealthCheckRow,
    SystemHealthRow,
)


_ATTENTION_SOURCE = "operations attention"
_HEALTH_SOURCE = "operations notification health"


class AttentionAlertProjection:
    """Read one opaque attention record without creating daemon state."""

    def __init__(
        self,
        state_root: Path,
        *,
        dismissals: AlertDismissalStore | None = None,
    ) -> None:
        self._path = validate_state_root(state_root) / "attention-alert.json"
        self._dismissals = dismissals

    def read(self) -> SourceSample[AttentionFacts]:
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            return self._unavailable("Attention alert state is unavailable.")
        except OSError:
            return self._unavailable("Attention alert state is unavailable.")
        try:
            record = OperationsAlertRecord.model_validate_json(raw, strict=True)
        except (ValidationError, ValueError):
            return self._unavailable("Attention alert state is invalid.")
        observed_at = record.resolved_at_utc or record.created_at_utc
        if self._dismissals is not None and record.severity == "resolved":
            try:
                dismissed = self._dismissals.is_dismissed(
                    record.alert_id,
                    record.created_at_utc,
                )
            except AlertDismissalUnavailable:
                return self._unavailable("Attention dismissal state is unavailable.")
            if dismissed:
                return SourceSample[AttentionFacts](
                    value=AttentionFacts(alerts=()),
                    freshness=Freshness.FRESH,
                    observed_at_utc=observed_at,
                    source=_ATTENTION_SOURCE,
                    error=None,
                )
        alert = AlertView(
            alert_id=record.alert_id,
            severity=record.severity,
            summary=GENERIC_ATTENTION_TEXT,
            created_at_utc=record.created_at_utc,
            resolved_at_utc=record.resolved_at_utc,
        )
        return SourceSample[AttentionFacts](
            value=AttentionFacts(alerts=(alert,)),
            freshness=Freshness.FRESH,
            observed_at_utc=observed_at,
            source=_ATTENTION_SOURCE,
            error=None,
        )

    @staticmethod
    def _unavailable(reason: str) -> SourceSample[AttentionFacts]:
        return SourceSample[AttentionFacts](
            value=None,
            freshness=Freshness.UNAVAILABLE,
            observed_at_utc=None,
            source=_ATTENTION_SOURCE,
            error=reason,
        )


class NotificationHealthProjection:
    """Read generic notification health without creating daemon state."""

    def __init__(
        self,
        state_root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        stale_after: timedelta = timedelta(minutes=5),
    ) -> None:
        if stale_after < timedelta(0):
            raise ValueError("stale_after cannot be negative")
        self._path = validate_state_root(state_root) / "notification-health.json"
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._stale_after = stale_after

    def read(self) -> SourceSample[SystemFacts]:
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            return self._unavailable("Notification health state is unavailable.")
        except OSError:
            return self._unavailable("Notification health state is unavailable.")
        try:
            record = NotificationHealthRecord.model_validate_json(raw, strict=True)
        except (ValidationError, ValueError):
            return self._unavailable("Notification health state is invalid.")
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
            return self._unavailable("Notification health clock did not return UTC.")
        if record.observed_at_utc > now:
            return self._unavailable("Notification health timestamp is in the future.")
        stale = now - record.observed_at_utc > self._stale_after
        if record.state == "healthy":
            service_state = "unavailable" if stale else "running"
            health_reason = (
                "Windows notification delivery health is stale."
                if stale
                else "Windows notification delivery is healthy."
            )
        else:
            service_state = "failed"
            health_reason = "Windows notification delivery failed."
        facts = SystemFacts(
            services=(
                ServiceRow(
                    service_id="service:windows-notifications",
                    state=service_state,
                    health_reason=health_reason,
                    observed_at_utc=record.observed_at_utc,
                ),
            ),
            services_error=None,
            metrics=None,
            metrics_error="Notification health does not provide system metrics.",
            repositories=None,
            repositories_error="Notification health does not provide repositories.",
            qwen=None,
            qwen_error="Notification health does not provide Qwen status.",
            health=(
                SystemHealthRow(
                    component="notifications",
                    state=("degraded" if stale or record.state != "healthy" else "healthy"),
                    reason=health_reason if stale or record.state != "healthy" else None,
                    observed_at_utc=record.observed_at_utc,
                    checks=(
                        SystemHealthCheckRow(
                            check_id="check:windows-notifications",
                            state="pass" if record.state == "healthy" and not stale else "fail",
                            reason=(
                                None
                                if record.state == "healthy" and not stale
                                else health_reason
                            ),
                        ),
                    ),
                    broker_actions_blocked=False,
                ),
            ),
            health_error=None,
        )
        return SourceSample[SystemFacts](
            value=facts,
            freshness=Freshness.STALE if stale else Freshness.FRESH,
            observed_at_utc=record.observed_at_utc,
            source=_HEALTH_SOURCE,
            error=self._stale_reason() if stale else None,
        )

    def _stale_reason(self) -> str:
        seconds = self._stale_after.total_seconds()
        rendered = str(int(seconds)) if seconds.is_integer() else f"{seconds:g}"
        return f"Notification health is older than {rendered} seconds."

    @staticmethod
    def _unavailable(reason: str) -> SourceSample[SystemFacts]:
        return SourceSample[SystemFacts](
            value=None,
            freshness=Freshness.UNAVAILABLE,
            observed_at_utc=None,
            source=_HEALTH_SOURCE,
            error=reason,
        )


__all__ = ["AttentionAlertProjection", "NotificationHealthProjection"]
