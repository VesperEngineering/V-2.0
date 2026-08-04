from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from pydantic import ValidationError

from vesper.platform.tui.notifications import (
    APP_USER_MODEL_ID,
    GENERIC_ATTENTION_TEXT,
    WindowsNotificationPort,
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
        self.failure = failure

    def show(self, app_id: str, xml: str) -> None:
        self.calls.append((app_id, xml))
        if self.failure is not None:
            raise self.failure


class _Health:
    def __init__(self) -> None:
        self.failures: list[tuple[str, str]] = []

    def record_notification_failure(self, alert_id: str, code: str) -> None:
        self.failures.append((alert_id, code))


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
