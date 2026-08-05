"""Current-logon authenticated TUI presence over one local named event."""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable
from threading import Lock
from typing import Protocol

from .pipe_security import current_logon_sid


_EVENT_PREFIX = "Local\\V20TuiAuthenticated-"
_EVENT_MODIFY_STATE = 0x0002
_READ_CONTROL = 0x00020000
_SYNCHRONIZE = 0x00100000


class NamedEventBackend(Protocol):
    def create_event(self, name: str) -> object: ...

    def set_event(self, handle: object) -> None: ...

    def reset_event(self, handle: object) -> None: ...

    def close_event(self, handle: object) -> None: ...

    def is_event_set(self, name: str) -> bool: ...


class SessionPresencePublisher(Protocol):
    def set_authenticated(self, authenticated: bool) -> None: ...

    def close(self) -> None: ...


class _NullSessionPresence:
    def set_authenticated(self, authenticated: bool) -> None:
        if type(authenticated) is not bool:
            raise TypeError("authenticated presence must be boolean")

    def close(self) -> None:
        return None


class _Win32NamedEventBackend:
    """Import Win32 only when the production gateway or daemon needs it."""

    @staticmethod
    def _require_windows() -> None:
        if sys.platform != "win32":
            raise OSError("authenticated session presence requires Windows")

    @staticmethod
    def _security_attributes():
        _Win32NamedEventBackend._require_windows()
        import pywintypes
        import win32security

        sid = win32security.ConvertStringSidToSid(current_logon_sid())
        dacl = win32security.ACL()
        rights = _EVENT_MODIFY_STATE | _READ_CONTROL | _SYNCHRONIZE
        dacl.AddAccessAllowedAce(win32security.ACL_REVISION, rights, sid)
        descriptor = win32security.SECURITY_DESCRIPTOR()
        descriptor.Initialize()
        descriptor.SetSecurityDescriptorDacl(True, dacl, False)
        descriptor.SetSecurityDescriptorControl(
            win32security.SE_DACL_PROTECTED,
            win32security.SE_DACL_PROTECTED,
        )
        attributes = pywintypes.SECURITY_ATTRIBUTES()
        attributes.bInheritHandle = False
        attributes.SECURITY_DESCRIPTOR = descriptor
        return attributes

    def create_event(self, name: str) -> object:
        self._require_windows()
        import win32event

        try:
            return win32event.CreateEvent(self._security_attributes(), True, False, name)
        except Exception as exc:
            raise OSError("authenticated session presence is unavailable") from exc

    def set_event(self, handle: object) -> None:
        self._require_windows()
        import win32event

        try:
            win32event.SetEvent(handle)
        except Exception as exc:
            raise OSError("authenticated session presence is unavailable") from exc

    def reset_event(self, handle: object) -> None:
        self._require_windows()
        import win32event

        try:
            win32event.ResetEvent(handle)
        except Exception as exc:
            raise OSError("authenticated session presence is unavailable") from exc

    def close_event(self, handle: object) -> None:
        try:
            close = getattr(handle, "Close")
            close()
        except Exception as exc:
            raise OSError("authenticated session presence is unavailable") from exc

    def is_event_set(self, name: str) -> bool:
        self._require_windows()
        import pywintypes
        import win32event

        try:
            handle = win32event.OpenEvent(_SYNCHRONIZE, False, name)
        except pywintypes.error as exc:
            if getattr(exc, "winerror", None) == 2:
                return False
            raise OSError("authenticated session presence is unavailable") from exc
        try:
            result = win32event.WaitForSingleObject(handle, 0)
            if result == win32event.WAIT_OBJECT_0:
                return True
            if result == win32event.WAIT_TIMEOUT:
                return False
            raise OSError("authenticated session presence is unavailable")
        finally:
            try:
                handle.Close()
            except Exception:
                pass


def session_presence_event_name(logon_sid: str) -> str:
    if type(logon_sid) is not str or not logon_sid.strip():
        raise ValueError("logon SID is required")
    suffix = hashlib.sha256(logon_sid.encode("utf-8")).hexdigest()[:32]
    return f"{_EVENT_PREFIX}{suffix}"


class NamedEventSessionPresence:
    """Publish only whether at least one TUI session is authenticated."""

    def __init__(
        self,
        *,
        backend: NamedEventBackend | None = None,
        logon_sid_provider: Callable[[], str] = current_logon_sid,
    ) -> None:
        if not callable(logon_sid_provider):
            raise TypeError("logon SID provider must be callable")
        self._backend = _Win32NamedEventBackend() if backend is None else backend
        self._event_name = session_presence_event_name(logon_sid_provider())
        self._handle = self._backend.create_event(self._event_name)
        self._authenticated = False
        self._closed = False
        self._lock = Lock()

    @property
    def event_name(self) -> str:
        return self._event_name

    def set_authenticated(self, authenticated: bool) -> None:
        if type(authenticated) is not bool:
            raise TypeError("authenticated presence must be boolean")
        with self._lock:
            if self._closed:
                raise RuntimeError("authenticated session presence is closed")
            if authenticated == self._authenticated:
                return
            if authenticated:
                self._backend.set_event(self._handle)
            else:
                self._backend.reset_event(self._handle)
            self._authenticated = authenticated

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                if self._authenticated:
                    self._backend.reset_event(self._handle)
            finally:
                self._authenticated = False
                self._backend.close_event(self._handle)


class CurrentLogonSessionProbe:
    """Read the current logon's named event without opening TUI state."""

    def __init__(
        self,
        *,
        backend: NamedEventBackend | None = None,
        logon_sid_provider: Callable[[], str] = current_logon_sid,
    ) -> None:
        if not callable(logon_sid_provider):
            raise TypeError("logon SID provider must be callable")
        self._backend = _Win32NamedEventBackend() if backend is None else backend
        self._event_name = session_presence_event_name(logon_sid_provider())

    def has_authenticated_client(self) -> bool:
        value = self._backend.is_event_set(self._event_name)
        if type(value) is not bool:
            raise OSError("authenticated session state is unavailable")
        return value


NULL_SESSION_PRESENCE: SessionPresencePublisher = _NullSessionPresence()


__all__ = [
    "CurrentLogonSessionProbe",
    "NULL_SESSION_PRESENCE",
    "NamedEventBackend",
    "NamedEventSessionPresence",
    "SessionPresencePublisher",
    "session_presence_event_name",
]
