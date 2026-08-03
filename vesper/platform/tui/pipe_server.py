"""Bounded overlapped Windows named-pipe transport for the local console."""

from __future__ import annotations

import struct
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from .pipe_security import (
    bootstrap_security_attributes,
    current_logon_sid,
    current_user_security_attributes,
    lock_down_pipe,
    pipe_name,
)
from .protocol import MAX_FRAME_BYTES

if sys.platform == "win32":
    import pywintypes
    import win32con
    import win32event
    import win32file
    import win32pipe
    import winerror

PipeHandler = Callable[[bytes], bytes | None]

_LENGTH = struct.Struct(">I")
_PIPE_BUFFER_BYTES = 1_048_576
_MAX_INSTANCES = 4
_POLL_MILLISECONDS = 50
_WORKER_SHUTDOWN_SECONDS = 0.25
_DISCONNECT_ERRORS = {6, 109, 232, 233, 536, 995}


@dataclass(frozen=True)
class _PendingConnect:
    handle: object
    overlapped: object
    event: object
    already_connected: bool = False


@dataclass(frozen=True)
class _PendingCancellation:
    handle: object
    overlapped: object
    event: object


class WindowsPipeServer:
    """Serve bounded, nonblocking transport callbacks on four local pipe instances.

    The handler runs on a daemon connection worker and must remain bounded and
    nonblocking. V20 application calls belong outside this transport callback.
    """

    def __init__(self, name: str | None = None) -> None:
        if sys.platform != "win32":
            raise OSError("the V20 console named pipe requires Windows")
        self.name = name or pipe_name(current_logon_sid())
        self.ready_event = threading.Event()
        self._lock = threading.Lock()
        self._handles: set[object] = set()
        self._workers: set[threading.Thread] = set()
        self._worker_handles: dict[threading.Thread, object] = {}
        self._pending_cancellations: list[_PendingCancellation] = []
        self._retired_event_ids: set[int] = set()
        self._cancellation_reaper: threading.Thread | None = None
        self._stop_requested = threading.Event()

    @property
    def active_handle_count(self) -> int:
        with self._lock:
            return len(self._handles)

    @property
    def active_worker_count(self) -> int:
        with self._lock:
            return sum(worker.is_alive() for worker in self._workers)

    @property
    def pending_cancellation_count(self) -> int:
        with self._lock:
            return len(self._pending_cancellations)

    def stop(self) -> None:
        """Request cooperative same-thread I/O cancellation."""

        self._stop_requested.set()

    def serve(self, handler: PipeHandler, stop_event: threading.Event) -> None:
        """Accept up to four concurrent local connections until stopped."""

        if self._should_stop(stop_event):
            return
        listeners = self._bootstrap_listeners()
        for listener in listeners.values():
            self._track_handle(listener.handle)
        self.ready_event.set()
        try:
            while not self._should_stop(stop_event):
                for handle in self._reap_workers():
                    listeners[handle] = self._arm_connect(handle, reject_preconnected=False)
                accepted = self._completed_listener(listeners)
                if accepted is None:
                    stop_event.wait(_POLL_MILLISECONDS / 1000)
                    continue
                listener = listeners.pop(accepted)
                if not self._finish_listener(listener):
                    break
                if self._should_stop(stop_event):
                    break
                worker = threading.Thread(
                    target=self._serve_connection,
                    args=(accepted, handler),
                    name="v20-tui-pipe-worker",
                    daemon=True,
                )
                with self._lock:
                    self._workers.add(worker)
                    self._worker_handles[worker] = accepted
                worker.start()
        finally:
            self.ready_event.clear()
            self._stop_requested.set()
            for listener in tuple(listeners.values()):
                self._cancel_listener(listener)
            self._join_workers_bounded()
            self._close_all_handles()
            self._join_workers_bounded()
            self._reap_workers()
            self._reap_cancellations()
            self._start_cancellation_reaper()

    def _bootstrap_listeners(self) -> dict[object, _PendingConnect]:
        handles = self._create_pipe_set()
        listeners: dict[object, _PendingConnect] = {}
        try:
            for handle in handles:
                listener = self._arm_connect(handle, reject_preconnected=True)
                listeners[handle] = listener
        except BaseException:
            for listener in listeners.values():
                self._cancel_listener(listener)
            for handle in handles:
                self._close_untracked_handle(handle)
            raise
        return listeners

    def _create_pipe_set(self) -> tuple[object, ...]:
        bootstrap = bootstrap_security_attributes()
        handles: list[object] = []
        try:
            for index in range(_MAX_INSTANCES):
                handles.append(
                    self._create_pipe(
                        first_instance=index == 0,
                        security_attributes=bootstrap,
                    )
                )
            for handle in handles:
                lock_down_pipe(handle)
        except BaseException:
            for handle in handles:
                self._close_untracked_handle(handle)
            raise
        return tuple(handles)

    def _create_pipe(
        self,
        first_instance: bool,
        security_attributes: object | None = None,
    ) -> object:
        access = (
            win32pipe.PIPE_ACCESS_DUPLEX
            | win32file.FILE_FLAG_OVERLAPPED
            | win32con.WRITE_DAC
        )
        if first_instance:
            access |= win32pipe.FILE_FLAG_FIRST_PIPE_INSTANCE
        attributes = security_attributes or current_user_security_attributes()
        return win32pipe.CreateNamedPipe(
            self.name,
            access,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            _MAX_INSTANCES,
            _PIPE_BUFFER_BYTES,
            _PIPE_BUFFER_BYTES,
            0,
            attributes,
        )

    def _arm_connect(self, handle: object, reject_preconnected: bool) -> _PendingConnect:
        overlapped, event = self._new_overlapped()
        try:
            try:
                status = win32pipe.ConnectNamedPipe(handle, overlapped)
            except pywintypes.error as error:
                if error.winerror == winerror.ERROR_PIPE_CONNECTED:
                    status = winerror.ERROR_PIPE_CONNECTED
                elif error.winerror == winerror.ERROR_IO_PENDING:
                    status = winerror.ERROR_IO_PENDING
                else:
                    raise
            connected = status in {None, 0, winerror.ERROR_PIPE_CONNECTED}
            if connected and reject_preconnected:
                raise RuntimeError("pipe instance was consumed before secure readiness")
            if not connected and status != winerror.ERROR_IO_PENDING:
                raise OSError(status, "ConnectNamedPipe returned an unexpected status")
            return _PendingConnect(handle, overlapped, event, connected)
        except BaseException:
            win32file.CloseHandle(event)
            raise

    @staticmethod
    def _completed_listener(
        listeners: dict[object, _PendingConnect],
    ) -> object | None:
        for handle, listener in listeners.items():
            if listener.already_connected:
                return handle
            if win32event.WaitForSingleObject(listener.event, 0) == win32event.WAIT_OBJECT_0:
                return handle
        return None

    def _finish_listener(self, listener: _PendingConnect) -> bool:
        try:
            if not listener.already_connected:
                try:
                    win32file.GetOverlappedResult(
                        listener.handle,
                        listener.overlapped,
                        False,
                    )
                except pywintypes.error as error:
                    if error.winerror in _DISCONNECT_ERRORS and self._stop_requested.is_set():
                        return False
                    raise
            return True
        finally:
            win32file.CloseHandle(listener.event)

    def _cancel_listener(self, listener: _PendingConnect) -> None:
        event_owned = True
        try:
            if not listener.already_connected:
                event_owned = self._cancel_and_finish(
                    listener.handle,
                    listener.overlapped,
                    listener.event,
                )
        finally:
            if event_owned:
                win32file.CloseHandle(listener.event)

    def _serve_connection(self, handle: object, handler: PipeHandler) -> None:
        try:
            while not self._stop_requested.is_set():
                header = self._read_exact(handle, _LENGTH.size)
                if header is None:
                    return
                size = _LENGTH.unpack(header)[0]
                if not 0 < size <= MAX_FRAME_BYTES:
                    return
                body = self._read_exact(handle, size)
                if body is None:
                    return
                try:
                    response = handler(body)
                except BaseException:
                    return
                if response is None:
                    continue
                if not isinstance(response, bytes):
                    return
                if not 0 < len(response) <= MAX_FRAME_BYTES:
                    return
                if not self._write_all(handle, _LENGTH.pack(len(response)) + response):
                    return
        except pywintypes.error:
            return

    def _read_exact(self, handle: object, size: int) -> bytes | None:
        data = bytearray()
        while len(data) < size:
            chunk = self._read_once(handle, size - len(data))
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data)

    def _read_once(self, handle: object, size: int) -> bytes | None:
        overlapped, event = self._new_overlapped()
        try:
            try:
                status, buffer = win32file.ReadFile(handle, size, overlapped)
            except pywintypes.error as error:
                if error.winerror in _DISCONNECT_ERRORS:
                    return None
                raise
            if status == winerror.ERROR_IO_PENDING:
                transferred = self._finish_overlapped(handle, overlapped)
                if transferred is None:
                    return None
            elif status == 0:
                transferred = win32file.GetOverlappedResult(handle, overlapped, False)
            else:
                raise OSError(status, "ReadFile returned an unexpected status")
            return bytes(buffer[:transferred])
        finally:
            if not self._event_is_retired(event):
                win32file.CloseHandle(event)

    def _write_all(self, handle: object, data: bytes) -> bool:
        offset = 0
        while offset < len(data):
            overlapped, event = self._new_overlapped()
            try:
                try:
                    status, _ = win32file.WriteFile(handle, data[offset:], overlapped)
                except pywintypes.error as error:
                    if error.winerror in _DISCONNECT_ERRORS:
                        return False
                    raise
                if status == winerror.ERROR_IO_PENDING:
                    transferred = self._finish_overlapped(handle, overlapped)
                    if transferred is None:
                        return False
                elif status == 0:
                    transferred = win32file.GetOverlappedResult(handle, overlapped, False)
                else:
                    raise OSError(status, "WriteFile returned an unexpected status")
                if transferred <= 0:
                    return False
                offset += transferred
            finally:
                if not self._event_is_retired(event):
                    win32file.CloseHandle(event)
        return True

    def _finish_overlapped(self, handle: object, overlapped: object) -> int | None:
        event = overlapped.hEvent
        while True:
            if win32event.WaitForSingleObject(event, _POLL_MILLISECONDS) == win32event.WAIT_OBJECT_0:
                try:
                    return win32file.GetOverlappedResult(handle, overlapped, False)
                except pywintypes.error as error:
                    if error.winerror in _DISCONNECT_ERRORS:
                        return None
                    raise
            if self._stop_requested.is_set():
                self._cancel_and_finish(handle, overlapped, event)
                return None

    def _cancel_and_finish(self, handle: object, overlapped: object, event: object) -> bool:
        try:
            win32file.CancelIo(handle)
        except pywintypes.error as error:
            if error.winerror not in _DISCONNECT_ERRORS:
                raise
        if win32event.WaitForSingleObject(event, 250) != win32event.WAIT_OBJECT_0:
            try:
                win32file.CloseHandle(handle)
            except pywintypes.error as error:
                if error.winerror not in _DISCONNECT_ERRORS:
                    raise
            if win32event.WaitForSingleObject(event, 250) != win32event.WAIT_OBJECT_0:
                with self._lock:
                    self._pending_cancellations.append(
                        _PendingCancellation(handle, overlapped, event)
                    )
                    self._retired_event_ids.add(id(event))
                return False
        try:
            win32file.GetOverlappedResult(handle, overlapped, False)
        except pywintypes.error as error:
            if error.winerror not in _DISCONNECT_ERRORS:
                raise
        return True

    @staticmethod
    def _new_overlapped() -> tuple[object, object]:
        overlapped = pywintypes.OVERLAPPED()
        event = win32event.CreateEvent(None, True, False, None)
        overlapped.hEvent = event
        return overlapped, event

    def _track_handle(self, handle: object) -> None:
        with self._lock:
            self._handles.add(handle)

    def _close_all_handles(self) -> None:
        with self._lock:
            handles = tuple(self._handles)
            self._handles.clear()
        for handle in handles:
            self._close_untracked_handle(handle)

    @staticmethod
    def _close_untracked_handle(handle: object) -> None:
        try:
            win32pipe.DisconnectNamedPipe(handle)
        except pywintypes.error:
            pass
        try:
            win32file.CloseHandle(handle)
        except pywintypes.error:
            pass

    def _should_stop(self, external: threading.Event) -> bool:
        return self._stop_requested.is_set() or external.is_set()

    def _reap_workers(self) -> tuple[object, ...]:
        with self._lock:
            finished = {worker for worker in self._workers if not worker.is_alive()}
            pairs = [(worker, self._worker_handles.pop(worker)) for worker in finished]
            self._workers.difference_update(finished)
            live_handles = set(self._handles)
        reusable: list[object] = []
        for worker, handle in pairs:
            worker.join()
            if handle in live_handles:
                try:
                    win32pipe.DisconnectNamedPipe(handle)
                except pywintypes.error as error:
                    if error.winerror not in _DISCONNECT_ERRORS:
                        raise
                reusable.append(handle)
        return tuple(reusable)

    def _join_workers_bounded(self) -> None:
        deadline = time.monotonic() + _WORKER_SHUTDOWN_SECONDS
        with self._lock:
            workers = tuple(self._workers)
        for worker in workers:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            worker.join(remaining)

    def _reap_cancellations(self) -> None:
        with self._lock:
            pending = tuple(self._pending_cancellations)
        completed: list[_PendingCancellation] = []
        for operation in pending:
            if win32event.WaitForSingleObject(operation.event, 0) != win32event.WAIT_OBJECT_0:
                continue
            try:
                win32file.GetOverlappedResult(
                    operation.handle,
                    operation.overlapped,
                    False,
                )
            except pywintypes.error:
                pass
            win32file.CloseHandle(operation.event)
            completed.append(operation)
        if completed:
            with self._lock:
                for operation in completed:
                    if operation in self._pending_cancellations:
                        self._pending_cancellations.remove(operation)
                    self._retired_event_ids.discard(id(operation.event))

    def _start_cancellation_reaper(self) -> None:
        with self._lock:
            if not self._pending_cancellations:
                return
            if self._cancellation_reaper is not None and self._cancellation_reaper.is_alive():
                return
            reaper = threading.Thread(
                target=self._reap_cancellations_until_done,
                name="v20-tui-pipe-cancellation-reaper",
                daemon=True,
            )
            self._cancellation_reaper = reaper
        reaper.start()

    def _reap_cancellations_until_done(self) -> None:
        while True:
            self._reap_cancellations()
            with self._lock:
                if not self._pending_cancellations:
                    return
            time.sleep(_POLL_MILLISECONDS / 1000)

    def _event_is_retired(self, event: object) -> bool:
        with self._lock:
            return id(event) in self._retired_event_ids
