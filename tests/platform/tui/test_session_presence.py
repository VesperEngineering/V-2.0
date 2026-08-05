from __future__ import annotations

import pytest

from vesper.platform.tui.session_presence import (
    CurrentLogonSessionProbe,
    NamedEventSessionPresence,
    session_presence_event_name,
)


class FakeNamedEventBackend:
    def __init__(self) -> None:
        self.states: dict[str, bool] = {}
        self.closed: list[str] = []

    def create_event(self, name: str) -> str:
        self.states.setdefault(name, False)
        return name

    def set_event(self, handle: object) -> None:
        self.states[str(handle)] = True

    def reset_event(self, handle: object) -> None:
        self.states[str(handle)] = False

    def close_event(self, handle: object) -> None:
        name = str(handle)
        self.states.pop(name, None)
        self.closed.append(name)

    def is_event_set(self, name: str) -> bool:
        return self.states.get(name, False)


def test_presence_name_is_stable_and_does_not_expose_the_logon_sid() -> None:
    first = session_presence_event_name("S-1-5-5-123-456")
    second = session_presence_event_name("S-1-5-5-123-456")

    assert first == second
    assert first.startswith("Local\\V20TuiAuthenticated-")
    assert "S-1-5-5-123-456" not in first
    assert len(first.rsplit("-", 1)[1]) == 32


def test_named_event_publisher_and_probe_share_only_one_boolean() -> None:
    backend = FakeNamedEventBackend()
    publisher = NamedEventSessionPresence(
        backend=backend,
        logon_sid_provider=lambda: "S-1-5-5-1-2",
    )
    probe = CurrentLogonSessionProbe(
        backend=backend,
        logon_sid_provider=lambda: "S-1-5-5-1-2",
    )

    assert probe.has_authenticated_client() is False
    publisher.set_authenticated(True)
    assert probe.has_authenticated_client() is True
    publisher.set_authenticated(False)
    assert probe.has_authenticated_client() is False

    publisher.close()
    assert backend.closed == [publisher.event_name]
    assert probe.has_authenticated_client() is False


def test_presence_rejects_invalid_state_and_invalid_backend_result() -> None:
    backend = FakeNamedEventBackend()
    publisher = NamedEventSessionPresence(
        backend=backend,
        logon_sid_provider=lambda: "S-1-5-5-1-2",
    )

    with pytest.raises(TypeError, match="boolean"):
        publisher.set_authenticated(1)  # type: ignore[arg-type]

    class InvalidProbeBackend(FakeNamedEventBackend):
        def is_event_set(self, name: str) -> bool:
            del name
            return 1  # type: ignore[return-value]

    probe = CurrentLogonSessionProbe(
        backend=InvalidProbeBackend(),
        logon_sid_provider=lambda: "S-1-5-5-1-2",
    )
    with pytest.raises(OSError, match="state is unavailable"):
        probe.has_authenticated_client()
