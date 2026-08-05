from __future__ import annotations

import gc
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from weakref import ReferenceType, ref

import pytest
from pydantic import ValidationError

from vesper.platform.ops import notification_health
from vesper.platform.ops.notification_health import AtomicNotificationFailureHealthSink
from vesper.platform.tui import notifications
from vesper.platform.tui.notifications import (
    APP_USER_MODEL_ID,
    GENERIC_ATTENTION_TEXT,
    WindowsNotificationPort,
    _WinRtToastBackend,
    build_toast_xml,
)


class _Sessions:
    def __init__(self, authenticated: bool = False) -> None:
        self.authenticated = authenticated

    def has_authenticated_client(self) -> bool:
        return self.authenticated


class _Backend:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.resolutions: list[str] = []
        self.failure = failure

    def show(self, app_id: str, xml: str) -> None:
        self.calls.append((app_id, xml))
        if self.failure is not None:
            raise self.failure

    def resolve(self, alert_id: str) -> None:
        self.resolutions.append(alert_id)


class _Health:
    def __init__(self) -> None:
        self.failures: list[tuple[str, str]] = []
        self.healthy_calls = 0

    def record_notification_failure(self, alert_id: str, code: str) -> None:
        self.failures.append((alert_id, code))

    def record_notification_healthy(self) -> None:
        self.healthy_calls += 1


class _Toast:
    def __init__(self, events: list[str]) -> None:
        self.handler: Callable[[object, object], None] | None = None
        self.removed_tokens: list[object] = []
        self.tag: str | None = None
        self.group: str | None = None
        self._events = events

    def add_activated(self, handler: Callable[[object, object], None]) -> object:
        self.handler = handler
        return (41,)

    def remove_activated(self, token: object) -> None:
        self._events.append("callback")
        self.removed_tokens.append(token)
        self.handler = None

    def activate(self) -> None:
        assert self.handler is not None
        self.handler(self, object())


class _Notifier:
    def show(self, toast: _Toast) -> None:
        del toast


class _FailOnceNotifier(_Notifier):
    def __init__(self) -> None:
        self.calls = 0

    def show(self, toast: _Toast) -> None:
        del toast
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("private first-show failure")


class _ToastFactory:
    def __init__(self) -> None:
        self.last_toast: ReferenceType[_Toast] | None = None
        self.notifier = _Notifier()
        self.events: list[str] = []

    def __call__(self, app_id: str, xml: str) -> tuple[_Notifier, _Toast]:
        del app_id, xml
        toast = _Toast(self.events)
        self.last_toast = ref(toast)
        return self.notifier, toast


class _HistoryRemover:
    def __init__(self, events: list[str], *, failure: Exception | None = None) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.events = events
        self.failure = failure

    def __call__(self, tag: str, group: str, app_id: str) -> None:
        self.calls.append((tag, group, app_id))
        self.events.append("history")
        if self.failure is not None:
            raise self.failure


class _Launcher:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.failure = failure

    def __call__(self, argv: list[str], **kwargs: object) -> object:
        self.calls.append((argv, kwargs))
        if self.failure is not None:
            raise self.failure
        return object()


def _visible_text(xml: str) -> list[str]:
    root = ET.fromstring(xml)
    return [node.text or "" for node in root.findall(".//text")]


def test_notification_contains_only_generic_text() -> None:
    backend = _Backend()
    port = WindowsNotificationPort(_Sessions(), backend=backend)

    receipt = port.send_attention("alert-1")

    assert receipt.status == "sent"
    assert backend.calls[0][0] == APP_USER_MODEL_ID
    assert _visible_text(backend.calls[0][1]) == [GENERIC_ATTENTION_TEXT]
    lowered = backend.calls[0][1].lower()
    assert all(
        forbidden not in lowered
        for forbidden in ("portfolio", "account", "stock", "order", "model", "agent")
    )


def test_click_launches_with_only_safe_alert_id() -> None:
    backend = _Backend()
    port = WindowsNotificationPort(_Sessions(), backend=backend)

    port.send_attention("alert:high-1")

    root = ET.fromstring(backend.calls[0][1])
    assert root.attrib == {"launch": "--alert-id alert:high-1"}


@pytest.mark.parametrize(
    "alert_id",
    ("", " alert-1", "alert 1", "alert/1", "<alert>", "a" * 129),
)
def test_unsafe_alert_id_never_reaches_windows(alert_id: str) -> None:
    backend = _Backend()
    port = WindowsNotificationPort(_Sessions(), backend=backend)

    with pytest.raises(ValidationError):
        port.send_attention(alert_id)

    assert backend.calls == []


def test_xml_builder_escapes_visible_and_launch_text() -> None:
    xml = build_toast_xml('V20 <needs> & "attention"', "alert-1")

    root = ET.fromstring(xml)
    assert _visible_text(xml) == ['V20 <needs> & "attention"']
    assert root.attrib["launch"] == "--alert-id alert-1"


def test_authenticated_console_suppresses_windows_notification() -> None:
    backend = _Backend()
    port = WindowsNotificationPort(_Sessions(authenticated=True), backend=backend)

    receipt = port.send_attention("alert-1")

    assert receipt.status == "suppressed"
    assert backend.calls == []


def test_duplicate_active_alert_coalesces_until_resolved() -> None:
    backend = _Backend()
    port = WindowsNotificationPort(_Sessions(), backend=backend)

    first = port.send_attention("alert-1")
    duplicate = port.send_attention("alert-1")
    port.resolve("alert-1")
    after_resolution = port.send_attention("alert-1")

    assert [first.status, duplicate.status, after_resolution.status] == [
        "sent",
        "coalesced",
        "sent",
    ]
    assert len(backend.calls) == 2
    assert backend.resolutions == ["alert-1"]


def test_backend_failure_records_system_health_and_does_not_escape() -> None:
    backend = _Backend(failure=RuntimeError("private Windows failure"))
    health = _Health()
    port = WindowsNotificationPort(_Sessions(), backend=backend, health=health)

    receipt = port.send_attention("alert-1")

    assert receipt.status == "failed"
    assert receipt.code == "windows-notification-failed"
    assert health.failures == [("alert-1", "windows-notification-failed")]
    assert "private Windows failure" not in receipt.model_dump_json()


def test_failed_send_is_not_marked_active_and_can_retry() -> None:
    backend = _Backend(failure=RuntimeError("first failure"))
    port = WindowsNotificationPort(_Sessions(), backend=backend)

    assert port.send_attention("alert-1").status == "failed"
    backend.failure = None

    assert port.send_attention("alert-1").status == "sent"
    assert len(backend.calls) == 2


def test_failed_winrt_show_retries_after_failed_history_cleanup(tmp_path: Path) -> None:
    executable = tmp_path / "vesper-ratatui-console.exe"
    executable.write_bytes(b"test executable")
    factory = _ToastFactory()
    notifier = _FailOnceNotifier()
    factory.notifier = notifier
    history = _HistoryRemover(
        factory.events,
        failure=RuntimeError("private Action Center cleanup failure"),
    )
    health = _Health()
    backend = _WinRtToastBackend(
        executable,
        toast_factory=factory,
        process_launcher=_Launcher(),
        failure_sink=health,
        history_remover=history,
    )
    port = WindowsNotificationPort(_Sessions(), backend=backend, health=health)

    first = port.send_attention("alert-1")
    second = port.send_attention("alert-1")

    assert [first.status, second.status] == ["failed", "sent"]
    assert notifier.calls == 2
    assert len(history.calls) == 1


def test_port_activation_uses_only_fixed_executable_and_validated_alert_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "vesper-ratatui-console.exe"
    executable.write_bytes(b"test executable")
    factory = _ToastFactory()
    launcher = _Launcher()
    backend = _WinRtToastBackend(
        executable,
        toast_factory=factory,
        process_launcher=launcher,
        failure_sink=_Health(),
    )
    untrusted_xml = '<toast launch="C:\\private\\other.exe --alert-id other" />'
    monkeypatch.setattr(notifications, "build_toast_xml", lambda _title, _alert_id: untrusted_xml)
    port = WindowsNotificationPort(_Sessions(), backend=backend)

    assert port.send_attention("alert-1").status == "sent"
    assert factory.last_toast is not None
    toast = factory.last_toast()
    assert toast is not None
    toast.activate()

    assert launcher.calls == [
        (
            [str(executable.resolve()), "--alert-id", "alert-1"],
            {"shell": False},
        )
    ]


def test_resolve_unregisters_callback_and_releases_retained_toast(tmp_path: Path) -> None:
    executable = tmp_path / "vesper-ratatui-console.exe"
    executable.write_bytes(b"test executable")
    factory = _ToastFactory()
    history = _HistoryRemover(factory.events)
    backend = _WinRtToastBackend(
        executable,
        toast_factory=factory,
        process_launcher=_Launcher(),
        failure_sink=_Health(),
        history_remover=history,
    )

    backend.show_attention(APP_USER_MODEL_ID, "<toast />", "alert-1")
    assert factory.last_toast is not None
    toast_reference = factory.last_toast
    gc.collect()
    toast = toast_reference()
    assert toast is not None

    backend.resolve("alert-1")

    assert history.calls == [("682dc44f5fe34328", "v20-attention", APP_USER_MODEL_ID)]
    assert factory.events == ["history", "callback"]
    assert toast.removed_tokens == [(41,)]
    assert toast.handler is None
    del toast
    gc.collect()
    assert toast_reference() is None


def test_resolve_after_backend_restart_removes_deterministic_history(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "vesper-ratatui-console.exe"
    executable.write_bytes(b"test executable")
    events: list[str] = []
    history = _HistoryRemover(events)
    backend = _WinRtToastBackend(
        executable,
        toast_factory=_ToastFactory(),
        process_launcher=_Launcher(),
        failure_sink=_Health(),
        history_remover=history,
    )

    backend.resolve("alert-1")

    assert history.calls == [("682dc44f5fe34328", "v20-attention", APP_USER_MODEL_ID)]
    assert events == ["history"]


def test_winrt_toast_uses_bounded_deterministic_action_center_identity(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "vesper-ratatui-console.exe"
    executable.write_bytes(b"test executable")
    factory = _ToastFactory()
    backend = _WinRtToastBackend(
        executable,
        toast_factory=factory,
        process_launcher=_Launcher(),
        failure_sink=_Health(),
        history_remover=_HistoryRemover(factory.events),
    )

    backend.show_attention(APP_USER_MODEL_ID, "<toast />", "alert-1")

    assert factory.last_toast is not None
    toast = factory.last_toast()
    assert toast is not None
    assert toast.tag == "682dc44f5fe34328"
    assert toast.group == "v20-attention"
    assert len(toast.tag) <= 16
    assert len(toast.group) <= 16


def test_history_removal_failure_keeps_visible_toast_actionable_and_retryable(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "vesper-ratatui-console.exe"
    executable.write_bytes(b"test executable")
    factory = _ToastFactory()
    launcher = _Launcher()
    health = _Health()
    history = _HistoryRemover(
        factory.events,
        failure=RuntimeError("private Action Center failure"),
    )
    backend = _WinRtToastBackend(
        executable,
        toast_factory=factory,
        process_launcher=launcher,
        failure_sink=health,
        history_remover=history,
    )
    port = WindowsNotificationPort(_Sessions(), backend=backend, health=health)

    assert port.send_attention("alert-1").status == "sent"
    assert factory.last_toast is not None
    toast = factory.last_toast()
    assert toast is not None

    with pytest.raises(RuntimeError, match="notification resolution failed"):
        port.resolve("alert-1")

    assert toast.handler is not None
    assert toast.removed_tokens == []
    assert port.send_attention("alert-1").status == "coalesced"
    toast.activate()
    assert launcher.calls == [
        ([str(executable.resolve()), "--alert-id", "alert-1"], {"shell": False})
    ]
    assert health.failures == [
        ("alert-1", "windows-notification-history-remove-failed"),
        ("alert-1", "windows-notification-resolve-failed"),
    ]

    history.failure = None
    port.resolve("alert-1")
    assert toast.handler is None
    assert port.send_attention("alert-1").status == "sent"


def test_cleanup_queue_overflow_records_only_generic_notification_health() -> None:
    health = _Health()
    port = WindowsNotificationPort(_Sessions(), backend=_Backend(), health=health)

    port.record_cleanup_overflow("alert-opaque-1")

    assert health.failures == [("alert-opaque-1", "windows-notification-cleanup-queue-overflow")]


def test_successful_winrt_show_replaces_prior_failure_with_strict_generic_health(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 4, 18, 0, tzinfo=timezone.utc)
    executable = tmp_path / "vesper-ratatui-console.exe"
    executable.write_bytes(b"test executable")
    sink = AtomicNotificationFailureHealthSink(tmp_path, clock=lambda: now)
    sink.record_notification_failure("alert-1", "private-failure")
    factory = _ToastFactory()
    backend = _WinRtToastBackend(
        executable,
        toast_factory=factory,
        process_launcher=_Launcher(),
        failure_sink=sink,
        history_remover=_HistoryRemover(factory.events),
    )

    backend.show_attention(APP_USER_MODEL_ID, "<toast />", "alert-2")

    raw = sink.path.read_text(encoding="utf-8")
    assert json.loads(raw) == {
        "code": "notification-delivery-healthy",
        "observed_at_utc": "2026-08-04T18:00:00Z",
        "state": "healthy",
    }
    record_type = notification_health.NotificationHealthRecord
    record = record_type.model_validate_json(raw, strict=True)
    assert record.state == "healthy"
    with pytest.raises(ValidationError):
        record_type.model_validate(
            {
                "state": "healthy",
                "code": "notification-delivery-failed",
                "observed_at_utc": now,
                "details": "must not persist",
            },
            strict=True,
        )


@pytest.mark.parametrize("kind", ("relative", "missing", "directory", "reparse"))
def test_winrt_backend_rejects_unsafe_activation_executable(
    kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "vesper-ratatui-console.exe"
    executable.write_bytes(b"test executable")
    configured = executable
    if kind == "relative":
        configured = Path("vesper-ratatui-console.exe")
    elif kind == "missing":
        configured = tmp_path / "missing.exe"
    elif kind == "directory":
        configured = tmp_path
    elif kind == "reparse":
        monkeypatch.setattr(
            notifications,
            "_is_reparse_point",
            lambda path: path == executable,
        )

    with pytest.raises(ValueError, match="absolute regular non-reparse file"):
        _WinRtToastBackend(
            configured,
            toast_factory=_ToastFactory(),
            process_launcher=_Launcher(),
            failure_sink=_Health(),
        )


def test_activation_failure_is_contained_and_reports_only_safe_code(tmp_path: Path) -> None:
    executable = tmp_path / "vesper-ratatui-console.exe"
    executable.write_bytes(b"test executable")
    factory = _ToastFactory()
    launcher = _Launcher(failure=RuntimeError("C:\\private\\secret.exe --token do-not-expose"))
    health = _Health()
    backend = _WinRtToastBackend(
        executable,
        toast_factory=factory,
        process_launcher=launcher,
        failure_sink=health,
    )

    backend.show_attention(APP_USER_MODEL_ID, "<toast />", "alert-1")
    assert factory.last_toast is not None
    toast = factory.last_toast()
    assert toast is not None

    toast.activate()

    assert health.failures == [("alert-1", "windows-notification-activation-failed")]
    assert "secret" not in repr(health.failures).casefold()
