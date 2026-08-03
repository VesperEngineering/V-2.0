from __future__ import annotations

import struct
import sys
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows named-pipe integration")

if sys.platform == "win32":
    import pywintypes
    import win32file
    import win32pipe

from vesper.platform.tui.pipe_security import current_logon_sid, pipe_name
from vesper.platform.tui import pipe_server
from vesper.platform.tui.pipe_server import WindowsPipeServer

_LENGTH = struct.Struct(">I")


def _write_frame(handle: object, payload: bytes) -> None:
    win32file.WriteFile(handle, _LENGTH.pack(len(payload)) + payload)


def _read_exact(handle: object, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        _, chunk = win32file.ReadFile(handle, size - len(data))
        data.extend(chunk)
    return bytes(data)


def _read_frame(handle: object) -> bytes:
    size = _LENGTH.unpack(_read_exact(handle, _LENGTH.size))[0]
    return _read_exact(handle, size)


def _connect(name: str) -> object:
    deadline = time.monotonic() + 5
    while True:
        try:
            return win32file.CreateFile(
                name,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )
        except pywintypes.error as error:
            if error.winerror not in {2, 231} or time.monotonic() >= deadline:
                raise
            win32pipe.WaitNamedPipe(name, 100)


def test_same_user_round_trips_two_framed_messages_and_stops_cleanly() -> None:
    name = pipe_name(current_logon_sid())
    server = WindowsPipeServer(name)
    stop = threading.Event()
    thread = threading.Thread(target=server.serve, args=(lambda body: body.upper(), stop))
    thread.start()
    client = _connect(name)
    try:
        _write_frame(client, b"first")
        assert _read_frame(client) == b"FIRST"
        _write_frame(client, b"second")
        assert _read_frame(client) == b"SECOND"
    finally:
        win32file.CloseHandle(client)
        stop.set()
        server.stop()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert server.active_handle_count == 0
    assert server.active_worker_count == 0


def test_create_parameters_are_explicit_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[object] = []
    security_attributes = object()

    def create_named_pipe(*arguments: object) -> object:
        captured.extend(arguments)
        return object()

    monkeypatch.setattr(pipe_server.win32pipe, "CreateNamedPipe", create_named_pipe)
    monkeypatch.setattr(
        pipe_server,
        "current_user_security_attributes",
        lambda: security_attributes,
    )
    server = WindowsPipeServer(pipe_name(current_logon_sid()))

    server._create_pipe(first_instance=True)

    assert captured[1] & win32pipe.PIPE_ACCESS_DUPLEX
    assert captured[1] & win32pipe.FILE_FLAG_FIRST_PIPE_INSTANCE
    assert captured[1] & win32file.FILE_FLAG_OVERLAPPED
    assert captured[2] == (
        win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT
    )
    assert captured[3:7] == [4, 1_048_576, 1_048_576, 0]
    assert captured[7] is security_attributes


def test_second_first_instance_server_fails() -> None:
    name = pipe_name(current_logon_sid())
    first = WindowsPipeServer(name)
    stop = threading.Event()
    thread = threading.Thread(target=first.serve, args=(lambda body: body, stop))
    thread.start()
    client = _connect(name)
    try:
        second = WindowsPipeServer(name)
        already_stopped = threading.Event()
        already_stopped.set()
        with pytest.raises(pywintypes.error) as failure:
            second.serve(lambda body: body, already_stopped)
        assert failure.value.winerror == 5
        assert second.active_handle_count == 0
    finally:
        win32file.CloseHandle(client)
        stop.set()
        first.stop()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert first.active_handle_count == 0


def test_none_handler_response_sends_no_frame_and_connection_can_continue() -> None:
    name = pipe_name(current_logon_sid())
    seen: list[bytes] = []

    def handler(body: bytes) -> bytes | None:
        seen.append(body)
        return None if body == b"one-way" else b"ok"

    server = WindowsPipeServer(name)
    stop = threading.Event()
    thread = threading.Thread(target=server.serve, args=(handler, stop))
    thread.start()
    client = _connect(name)
    try:
        _write_frame(client, b"one-way")
        _write_frame(client, b"request")
        assert _read_frame(client) == b"ok"
        assert seen == [b"one-way", b"request"]
    finally:
        win32file.CloseHandle(client)
        stop.set()
        server.stop()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert server.active_handle_count == 0


def test_external_stop_event_cancels_waiting_listener_without_leaks() -> None:
    name = pipe_name(current_logon_sid())
    server = WindowsPipeServer(name)
    stop = threading.Event()
    thread = threading.Thread(target=server.serve, args=(lambda body: body, stop))
    thread.start()
    deadline = time.monotonic() + 5
    while server.active_handle_count == 0 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert server.active_handle_count == 1
    stop.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert server.active_handle_count == 0
    assert server.active_worker_count == 0

    replacement = WindowsPipeServer(name)
    already_stopped = threading.Event()
    already_stopped.set()
    replacement.serve(lambda body: body, already_stopped)
    assert replacement.active_handle_count == 0
