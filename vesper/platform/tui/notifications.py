"""Generic local Windows attention notifications for the V20 console."""

from __future__ import annotations

import hashlib
import stat
import subprocess
from collections.abc import Callable
from html import escape
from pathlib import Path
from threading import Lock
from typing import Literal, Protocol

from pydantic import TypeAdapter

from .views import SafeId, StrictModel


APP_USER_MODEL_ID = "Vesper.V20.TUI"
GENERIC_ATTENTION_TEXT = "V20 needs attention"
_ACTIVATION_FAILURE_CODE = "windows-notification-activation-failed"
_HISTORY_FAILURE_CODE = "windows-notification-history-remove-failed"
_CLEANUP_OVERFLOW_CODE = "windows-notification-cleanup-queue-overflow"
_TOAST_GROUP = "v20-attention"
_EXECUTABLE_ERROR = (
    "notification activation executable must be an absolute regular non-reparse file"
)
_DEFAULT_TUI_EXECUTABLE = Path(__file__).parents[3] / "dist" / "tui" / "vesper-ratatui-console.exe"
_SAFE_ID = TypeAdapter(SafeId)


class NotificationReceipt(StrictModel):
    """Safe result exposed to the supervisor and TUI."""

    alert_id: SafeId
    status: Literal["sent", "suppressed", "coalesced", "failed"]
    code: SafeId


class NotificationPort(Protocol):
    """Stable boundary for a future private phone adapter."""

    def send_attention(self, alert_id: SafeId) -> NotificationReceipt: ...

    def resolve(self, alert_id: SafeId) -> None: ...

    def record_cleanup_overflow(self, alert_id: SafeId) -> None: ...


class AuthenticatedSessionProbe(Protocol):
    def has_authenticated_client(self) -> bool: ...


class NotificationHealthSink(Protocol):
    def record_notification_failure(self, alert_id: SafeId, code: SafeId) -> None: ...

    def record_notification_healthy(self) -> None: ...


class WindowsToastBackend(Protocol):
    def show(self, app_id: str, xml: str) -> None: ...


class _NullHealthSink:
    def record_notification_failure(self, alert_id: SafeId, code: SafeId) -> None:
        del alert_id, code

    def record_notification_healthy(self) -> None:
        return None


class _Toast(Protocol):
    tag: str
    group: str

    def add_activated(self, handler: Callable[[object, object], None]) -> object: ...

    def remove_activated(self, token: object) -> None: ...


class _Notifier(Protocol):
    def show(self, toast: _Toast) -> None: ...


class _ToastFactory(Protocol):
    def __call__(self, app_id: str, xml: str) -> tuple[_Notifier, _Toast]: ...


class _ProcessLauncher(Protocol):
    def __call__(self, argv: list[str], *, shell: bool) -> object: ...


class _HistoryRemover(Protocol):
    def __call__(self, tag: str, group: str, app_id: str) -> None: ...


def _is_reparse_point(path: Path) -> bool:
    metadata = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _validated_executable(executable: Path) -> Path:
    try:
        candidate = Path(executable)
        if not candidate.is_absolute():
            raise ValueError(_EXECUTABLE_ERROR)
        current = Path(candidate.anchor)
        if _is_reparse_point(current):
            raise ValueError(_EXECUTABLE_ERROR)
        for part in candidate.parts[1:]:
            current /= part
            if _is_reparse_point(current):
                raise ValueError(_EXECUTABLE_ERROR)
        if not stat.S_ISREG(candidate.lstat().st_mode):
            raise ValueError(_EXECUTABLE_ERROR)
        resolved = candidate.resolve(strict=True)
        if resolved != candidate:
            raise ValueError(_EXECUTABLE_ERROR)
        return resolved
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
        raise ValueError(_EXECUTABLE_ERROR) from None


def _create_winrt_toast(app_id: str, xml: str) -> tuple[_Notifier, _Toast]:
    from winrt.windows.data.xml.dom import XmlDocument
    from winrt.windows.ui.notifications import (
        ToastNotification,
        ToastNotificationManager,
    )

    document = XmlDocument()
    document.load_xml(xml)
    notifier = ToastNotificationManager.create_toast_notifier(app_id)
    return notifier, ToastNotification(document)


def _remove_winrt_toast(tag: str, group: str, app_id: str) -> None:
    from winrt.windows.ui.notifications import ToastNotificationManager

    ToastNotificationManager.history.remove(tag, group, app_id)


def _toast_tag(alert_id: SafeId) -> str:
    return hashlib.sha256(str(alert_id).encode("utf-8")).hexdigest()[:16]


class _WinRtToastBackend:
    """Import WinRT only when a real local notification is requested."""

    def __init__(
        self,
        executable: Path,
        *,
        toast_factory: _ToastFactory | None = None,
        process_launcher: _ProcessLauncher | None = None,
        failure_sink: NotificationHealthSink | None = None,
        history_remover: _HistoryRemover | None = None,
    ) -> None:
        self._executable = _validated_executable(executable)
        self._toast_factory = _create_winrt_toast if toast_factory is None else toast_factory
        self._process_launcher = subprocess.Popen if process_launcher is None else process_launcher
        self._failure_sink = _NullHealthSink() if failure_sink is None else failure_sink
        self._history_remover = _remove_winrt_toast if history_remover is None else history_remover
        self._active: dict[SafeId, tuple[_Toast, object, str, str, str]] = {}
        self._lock = Lock()

    def show_attention(self, app_id: str, xml: str, alert_id: SafeId) -> None:
        validated_id = _validated_alert_id(alert_id)
        notifier, toast = self._toast_factory(app_id, xml)
        tag = _toast_tag(validated_id)
        toast.tag = tag
        toast.group = _TOAST_GROUP

        def activated(_sender: object, _args: object) -> None:
            self._activate(validated_id)

        token = toast.add_activated(activated)
        with self._lock:
            if validated_id in self._active:
                toast.remove_activated(token)
                raise RuntimeError("notification alert is already active")
            self._active[validated_id] = (toast, token, tag, _TOAST_GROUP, app_id)
        try:
            notifier.show(toast)
        except Exception:
            self._discard_failed_show(validated_id)
            raise
        try:
            self._failure_sink.record_notification_healthy()
        except Exception:
            pass

    def resolve(self, alert_id: SafeId) -> None:
        validated_id = _validated_alert_id(alert_id)
        with self._lock:
            active = self._active.get(validated_id)
        if active is None:
            toast = token = None
            tag = _toast_tag(validated_id)
            group = _TOAST_GROUP
            app_id = APP_USER_MODEL_ID
        else:
            toast, token, tag, group, app_id = active
        try:
            self._history_remover(tag, group, app_id)
        except Exception:
            self._record_failure(validated_id, _HISTORY_FAILURE_CODE)
            raise RuntimeError("notification history removal failed") from None
        if active is None:
            return
        try:
            assert toast is not None and token is not None
            toast.remove_activated(token)
        except Exception:
            self._record_failure(
                validated_id,
                "windows-notification-callback-remove-failed",
            )
            raise RuntimeError("notification callback removal failed") from None
        with self._lock:
            if self._active.get(validated_id) == active:
                self._active.pop(validated_id)

    def _discard_failed_show(self, alert_id: SafeId) -> None:
        with self._lock:
            active = self._active.pop(alert_id, None)
        if active is None:
            return
        toast, token, tag, group, app_id = active
        try:
            self._history_remover(tag, group, app_id)
        except Exception:
            self._record_failure(alert_id, _HISTORY_FAILURE_CODE)
        try:
            toast.remove_activated(token)
        except Exception:
            self._record_failure(
                alert_id,
                "windows-notification-callback-remove-failed",
            )

    def _activate(self, alert_id: SafeId) -> None:
        with self._lock:
            if alert_id not in self._active:
                return
        try:
            executable = _validated_executable(self._executable)
            self._process_launcher(
                [str(executable), "--alert-id", str(alert_id)],
                shell=False,
            )
        except Exception:
            self._record_failure(alert_id, _ACTIVATION_FAILURE_CODE)

    def _record_failure(self, alert_id: SafeId, code: SafeId) -> None:
        try:
            self._failure_sink.record_notification_failure(alert_id, code)
        except Exception:
            pass


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
        backend: WindowsToastBackend | _WinRtToastBackend | None = None,
        health: NotificationHealthSink | None = None,
    ) -> None:
        self._sessions = sessions
        self._health = _NullHealthSink() if health is None else health
        self._backend = (
            _WinRtToastBackend(_DEFAULT_TUI_EXECUTABLE, failure_sink=self._health)
            if backend is None
            else backend
        )
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
                if isinstance(self._backend, _WinRtToastBackend):
                    self._backend.show_attention(APP_USER_MODEL_ID, xml, validated_id)
                else:
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
            resolver = getattr(self._backend, "resolve", None)
            if callable(resolver):
                try:
                    resolver(validated_id)
                except Exception:
                    try:
                        self._health.record_notification_failure(
                            validated_id,
                            "windows-notification-resolve-failed",
                        )
                    except Exception:
                        pass
                    raise RuntimeError("notification resolution failed") from None
            self._active.discard(validated_id)

    def record_cleanup_overflow(self, alert_id: SafeId) -> None:
        """Record one generic health failure without storing incident details."""

        validated_id = _validated_alert_id(alert_id)
        try:
            self._health.record_notification_failure(
                validated_id,
                _CLEANUP_OVERFLOW_CODE,
            )
        except Exception:
            pass

    def _failed(self, alert_id: SafeId, code: SafeId) -> NotificationReceipt:
        try:
            self._health.record_notification_failure(alert_id, code)
        except Exception:
            pass
        return NotificationReceipt(alert_id=alert_id, status="failed", code=code)


class UnavailableNotificationPort:
    """Keep persistence live when Windows notification setup is unavailable."""

    def __init__(self, *, health: NotificationHealthSink | None = None) -> None:
        self._health = _NullHealthSink() if health is None else health

    def send_attention(self, alert_id: SafeId) -> NotificationReceipt:
        validated_id = _validated_alert_id(alert_id)
        code: SafeId = "windows-notification-unavailable"
        try:
            self._health.record_notification_failure(validated_id, code)
        except Exception:
            pass
        return NotificationReceipt(alert_id=validated_id, status="failed", code=code)

    def resolve(self, alert_id: SafeId) -> None:
        _validated_alert_id(alert_id)

    def record_cleanup_overflow(self, alert_id: SafeId) -> None:
        validated_id = _validated_alert_id(alert_id)
        try:
            self._health.record_notification_failure(
                validated_id,
                _CLEANUP_OVERFLOW_CODE,
            )
        except Exception:
            pass
