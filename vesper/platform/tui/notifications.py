"""Generic local Windows attention notifications for the V20 console."""

from __future__ import annotations

from html import escape
from threading import Lock
from typing import Literal, Protocol

from pydantic import TypeAdapter

from .views import SafeId, StrictModel


APP_USER_MODEL_ID = "Vesper.V20.TUI"
GENERIC_ATTENTION_TEXT = "V20 needs attention"
_SAFE_ID = TypeAdapter(SafeId)


class NotificationReceipt(StrictModel):
    """Safe result exposed to the supervisor and TUI."""

    alert_id: SafeId
    status: Literal["sent", "suppressed", "coalesced", "failed"]
    code: SafeId


class NotificationPort(Protocol):
    """Stable boundary for a future private phone adapter."""

    def send_attention(self, alert_id: SafeId) -> NotificationReceipt: ...


class AuthenticatedSessionProbe(Protocol):
    def has_authenticated_client(self) -> bool: ...


class NotificationHealthSink(Protocol):
    def record_notification_failure(self, alert_id: SafeId, code: SafeId) -> None: ...


class WindowsToastBackend(Protocol):
    def show(self, app_id: str, xml: str) -> None: ...


class _NullHealthSink:
    def record_notification_failure(self, alert_id: SafeId, code: SafeId) -> None:
        del alert_id, code


class _WinRtToastBackend:
    """Import WinRT only when a real local notification is requested."""

    def show(self, app_id: str, xml: str) -> None:
        from winrt.windows.data.xml.dom import XmlDocument
        from winrt.windows.ui.notifications import (
            ToastNotification,
            ToastNotificationManager,
        )

        document = XmlDocument()
        document.load_xml(xml)
        notifier = ToastNotificationManager.create_toast_notifier(app_id)
        notifier.show(ToastNotification(document))


def _validated_alert_id(alert_id: object) -> SafeId:
    return _SAFE_ID.validate_python(alert_id, strict=True)


def build_toast_xml(title: str, alert_id: SafeId) -> str:
    """Build one bounded toast with no hidden V20 data."""

    if type(title) is not str or not title or len(title) > 512:
        raise ValueError("notification title must be 1 to 512 characters")
    validated_id = _validated_alert_id(alert_id)
    launch = escape(f"--alert-id {validated_id}", quote=True)
    visible = escape(title, quote=False)
    return (
        f'<toast launch="{launch}"><visual><binding template="ToastGeneric">'
        f"<text>{visible}</text></binding></visual></toast>"
    )


class WindowsNotificationPort:
    """Send generic notifications only while no unlocked TUI is connected."""

    def __init__(
        self,
        sessions: AuthenticatedSessionProbe,
        *,
        backend: WindowsToastBackend | None = None,
        health: NotificationHealthSink | None = None,
    ) -> None:
        self._sessions = sessions
        self._backend = _WinRtToastBackend() if backend is None else backend
        self._health = _NullHealthSink() if health is None else health
        self._active: set[SafeId] = set()
        self._lock = Lock()

    def send_attention(self, alert_id: SafeId) -> NotificationReceipt:
        validated_id = _validated_alert_id(alert_id)
        try:
            has_authenticated_client = self._sessions.has_authenticated_client()
        except Exception:
            return self._failed(validated_id, "session-state-unavailable")
        if type(has_authenticated_client) is not bool:
            return self._failed(validated_id, "session-state-unavailable")
        if has_authenticated_client:
            return NotificationReceipt(
                alert_id=validated_id,
                status="suppressed",
                code="authenticated-client-connected",
            )

        with self._lock:
            if validated_id in self._active:
                return NotificationReceipt(
                    alert_id=validated_id,
                    status="coalesced",
                    code="active-alert-coalesced",
                )
            try:
                xml = build_toast_xml(GENERIC_ATTENTION_TEXT, validated_id)
                self._backend.show(APP_USER_MODEL_ID, xml)
            except Exception:
                return self._failed(validated_id, "windows-notification-failed")
            self._active.add(validated_id)
        return NotificationReceipt(
            alert_id=validated_id,
            status="sent",
            code="notification-sent",
        )

    def resolve(self, alert_id: SafeId) -> None:
        """Allow a resolved alert to notify again if it later reopens."""

        validated_id = _validated_alert_id(alert_id)
        with self._lock:
            self._active.discard(validated_id)

    def _failed(self, alert_id: SafeId, code: SafeId) -> NotificationReceipt:
        try:
            self._health.record_notification_failure(alert_id, code)
        except Exception:
            pass
        return NotificationReceipt(alert_id=alert_id, status="failed", code=code)
