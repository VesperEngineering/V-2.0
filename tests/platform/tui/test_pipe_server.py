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
    import winerror

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
    assert server.ready_event.wait(5)
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
    assert server.pending_cancellation_count == 0


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


def test_current_logon_connection_before_readiness_is_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = WindowsPipeServer(pipe_name(current_logon_sid()))
    handles = tuple(object() for _ in range(4))
    monkeypatch.setattr(server, "_create_pipe_set", lambda: handles)
    monkeypatch.setattr(
        pipe_server.win32pipe,
        "ConnectNamedPipe",
        lambda handle, overlapped: winerror.ERROR_PIPE_CONNECTED,
    )
    listeners = server._bootstrap_listeners()
    try:
        assert len(listeners) == 4
        assert all(listener.already_connected for listener in listeners.values())
        assert not server.ready_event.is_set()
    finally:
        for listener in listeners.values():
            server._cancel_listener(listener)


def test_consumption_after_all_listeners_are_armed_waits_for_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = pipe_name(current_logon_sid())
    server = WindowsPipeServer(name)
    stop = threading.Event()
    handler_calls: list[bytes] = []
    clients: list[object] = []
    ready_sets: list[bool] = []
    original_gate = server._pre_readiness_gate
    original_ready_set = server.ready_event.set

    def consume_then_gate(listeners: object) -> None:
        clients.append(_connect(name))
        original_gate(listeners)
        assert server.active_client_count == 1
        assert not server.ready_event.is_set()

    def record_ready() -> None:
        ready_sets.append(True)
        original_ready_set()

    def run() -> None:
        server.serve(
            lambda body: handler_calls.append(body) or body,
            stop,
        )

    monkeypatch.setattr(server, "_pre_readiness_gate", consume_then_gate)
    monkeypatch.setattr(server.ready_event, "set", record_ready)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert server.ready_event.wait(5)
    assert clients
    _write_frame(clients[0], b"early")
    assert _read_frame(clients[0]) == b"early"
    assert handler_calls == [b"early"]
    assert ready_sets == [True]
    win32file.CloseHandle(clients[0])
    stop.set()
    server.stop()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert server.active_handle_count == 0
    assert server.pending_cancellation_count == 0


def test_connection_factory_opens_fresh_context_and_closes_once_per_client() -> None:
    name = pipe_name(current_logon_sid())
    opened: list[int] = []
    closed: list[int] = []

    def factory():
        connection_id = len(opened) + 1
        opened.append(connection_id)

        def handle(body: bytes) -> bytes:
            return f"{connection_id}:".encode() + body

        return handle, lambda: closed.append(connection_id)

    server = WindowsPipeServer(name)
    stop = threading.Event()
    thread = threading.Thread(
        target=server.serve,
        args=(lambda body: body, stop),
        kwargs={"connection_factory": factory},
    )
    thread.start()
    assert server.ready_event.wait(5)

    first = _connect(name)
    _write_frame(first, b"one")
    assert _read_frame(first) == b"1:one"
    win32file.CloseHandle(first)
    deadline = time.monotonic() + 2
    while closed != [1] and time.monotonic() < deadline:
        time.sleep(0.01)

    second = _connect(name)
    _write_frame(second, b"two")
    assert _read_frame(second) == b"2:two"
    win32file.CloseHandle(second)
    deadline = time.monotonic() + 2
    while closed != [1, 2] and time.monotonic() < deadline:
        time.sleep(0.01)

    stop.set()
    server.stop()
    thread.join(timeout=5)
    assert opened == [1, 2]
    assert closed == [1, 2]
    assert not thread.is_alive()


def test_incomplete_cancellation_retains_event_until_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = WindowsPipeServer(pipe_name(current_logon_sid()))
    handle = object()
    overlapped = object()
    event = object()
    closed: list[object] = []
    monkeypatch.setattr(pipe_server.win32file, "CancelIo", lambda value: None)
    monkeypatch.setattr(pipe_server.win32file, "CloseHandle", closed.append)
    monkeypatch.setattr(
        pipe_server.win32event,
        "WaitForSingleObject",
        lambda value, milliseconds: pipe_server.win32event.WAIT_TIMEOUT,
    )

    assert not server._cancel_and_finish(handle, overlapped, event)
    assert server.pending_cancellation_count == 1
    assert closed == [handle]

    monkeypatch.setattr(
        pipe_server.win32event,
        "WaitForSingleObject",
        lambda value, milliseconds: pipe_server.win32event.WAIT_OBJECT_0,
    )
    monkeypatch.setattr(
        pipe_server.win32file,
        "GetOverlappedResult",
        lambda value, operation, wait: 0,
    )
    server._reap_cancellations()

    assert server.pending_cancellation_count == 0
    assert closed == [handle, event]


def test_second_first_instance_server_fails() -> None:
    name = pipe_name(current_logon_sid())
    first = WindowsPipeServer(name)
    stop = threading.Event()
    thread = threading.Thread(target=first.serve, args=(lambda body: body, stop))
    thread.start()
    assert first.ready_event.wait(5)
    client = _connect(name)
    try:
        second = WindowsPipeServer(name)
        with pytest.raises(pywintypes.error) as failure:
            second._create_pipe_set()
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
    assert server.ready_event.wait(5)
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
    thread = threading.Thread(
        target=server.serve,
        args=(lambda body: body, stop),
        daemon=True,
    )
    thread.start()
    assert server.ready_event.wait(5)

    assert server.active_handle_count == 4
    stop.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert server.active_handle_count == 0
    assert server.active_worker_count == 0
    assert server.pending_cancellation_count == 0

    replacement = WindowsPipeServer(name)
    already_stopped = threading.Event()
    already_stopped.set()
    replacement.serve(lambda body: body, already_stopped)
    assert replacement.active_handle_count == 0


def test_stop_before_serve_does_not_create_or_leak_pipe() -> None:
    name = pipe_name(current_logon_sid())
    server = WindowsPipeServer(name)
    server.stop()

    server.serve(lambda body: body, threading.Event())

    assert server.active_handle_count == 0
    probe = win32pipe.CreateNamedPipe(
        name,
        win32pipe.PIPE_ACCESS_DUPLEX | win32pipe.FILE_FLAG_FIRST_PIPE_INSTANCE,
        win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE,
        1,
        4096,
        4096,
        0,
        pipe_server.current_user_security_attributes(),
    )
    win32file.CloseHandle(probe)


def test_four_clients_connect_concurrently_and_fifth_instance_is_denied() -> None:
    name = pipe_name(current_logon_sid())
    server = WindowsPipeServer(name)
    stop = threading.Event()
    thread = threading.Thread(target=server.serve, args=(lambda body: body, stop))
    thread.start()
    assert server.ready_event.wait(5)
    clients: list[object] = []
    try:
        for index in range(4):
            client = _connect(name)
            clients.append(client)
            payload = f"client-{index}".encode()
            _write_frame(client, payload)
            assert _read_frame(client) == payload

        with pytest.raises(pywintypes.error) as fifth_client:
            win32file.CreateFile(
                name,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )
        assert fifth_client.value.winerror == 231

        with pytest.raises(pywintypes.error) as foreign_instance:
            win32pipe.CreateNamedPipe(
                name,
                win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE,
                4,
                4096,
                4096,
                0,
                pipe_server.current_user_security_attributes(),
            )
        assert foreign_instance.value.winerror == 5
    finally:
        for client in clients:
            win32file.CloseHandle(client)
        stop.set()
        server.stop()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert server.active_handle_count == 0


def test_handler_exception_is_connection_scoped_without_threading_excepthook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = pipe_name(current_logon_sid())
    failures: list[threading.ExceptHookArgs] = []
    monkeypatch.setattr(threading, "excepthook", failures.append)
    calls = 0

    def handler(body: bytes) -> bytes:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("connection failure")
        return body

    server = WindowsPipeServer(name)
    stop = threading.Event()
    thread = threading.Thread(target=server.serve, args=(handler, stop))
    thread.start()
    assert server.ready_event.wait(5)
    first = _connect(name)
    try:
        _write_frame(first, b"fail")
    finally:
        win32file.CloseHandle(first)
    second = _connect(name)
    try:
        _write_frame(second, b"recover")
        assert _read_frame(second) == b"recover"
    finally:
        win32file.CloseHandle(second)
        stop.set()
        server.stop()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert failures == []
    assert server.active_handle_count == 0


def test_blocked_handler_does_not_hold_pipe_handles_or_process_shutdown() -> None:
    name = pipe_name(current_logon_sid())
    entered = threading.Event()
    release = threading.Event()

    def handler(body: bytes) -> bytes:
        entered.set()
        release.wait()
        return body

    server = WindowsPipeServer(name)
    stop = threading.Event()
    thread = threading.Thread(target=server.serve, args=(handler, stop))
    thread.start()
    assert server.ready_event.wait(5)
    client = _connect(name)
    _write_frame(client, b"blocked")
    assert entered.wait(2)

    started = time.monotonic()
    stop.set()
    server.stop()
    thread.join(timeout=2)
    elapsed = time.monotonic() - started
    win32file.CloseHandle(client)

    assert not thread.is_alive()
    assert elapsed < 2
    assert server.active_handle_count == 0
    assert server.active_worker_count == 1
    assert server.pending_cancellation_count == 0
    worker = next(iter(server._workers))
    assert worker.daemon

    release.set()
    worker.join(timeout=2)
    assert not worker.is_alive()
