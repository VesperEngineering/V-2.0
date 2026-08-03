"""Bounded byte-framed Windows named-pipe transport for the local console."""

from __future__ import annotations

import struct
import sys
import threading
from collections.abc import Callable

from .protocol import MAX_FRAME_BYTES
from .pipe_security import current_logon_sid, current_user_security_attributes, pipe_name

if sys.platform == "win32":
    import pywintypes
    import win32event
    import win32file
    import win32pipe
    import winerror

PipeHandler = Callable[[bytes], bytes | None]

_LENGTH = struct.Struct(">I")
_PIPE_BUFFER_BYTES = 1_048_576
_MAX_INSTANCES = 4
_POLL_MILLISECONDS = 50
_DISCONNECT_ERRORS = {6, 109, 232, 233, 536, 995}


class WindowsPipeServer:
    """Serve transport-only callbacks over a current-logon Windows pipe."""

    def __init__(self, name: str | None = None) -> None:
        if sys.platform != "win32":
            raise OSError("the V20 console named pipe requires Windows")
        self.name = name or pipe_name(current_logon_sid())
        self._lock = threading.Lock()
        self._handles: set[object] = set()
        self._workers: set[threading.Thread] = set()
        self._stop_requested = threading.Event()

    @property
    def active_handle_count(self) -> int:
        with self._lock:
            return len(self._handles)

    @property
    def active_worker_count(self) -> int:
        with self._lock:
            return sum(worker.is_alive() for worker in self._workers)

    def stop(self) -> None:
        """Cancel listeners and clients so a blocked serve call can finish."""

        self._stop_requested.set()
        with self._lock:
            handles = tuple(self._handles)
        for handle in handles:
            self._close_handle(handle)

    def serve(self, handler: PipeHandler, stop_event: threading.Event) -> None:
        """Accept connections and give each one a transport-only worker."""

        self._stop_requested.clear()
        handle = self._create_pipe(first_instance=True)
        self._track_handle(handle)
        try:
            while True:
                self._reap_workers()
                if self._should_stop(stop_event):
                    break
                if not self._connect(handle, stop_event):
                    break
                worker = threading.Thread(
                    target=self._serve_connection,
                    args=(handle, handler),
                    name="v20-tui-pipe-worker",
                )
                with self._lock:
                    self._workers.add(worker)
                worker.start()
                while worker.is_alive() and not self._should_stop(stop_event):
                    worker.join(_POLL_MILLISECONDS / 1000)
                if self._should_stop(stop_event):
                    self._close_handle(handle)
                worker.join(timeout=5)
                self._reap_workers()
                if self._should_stop(stop_event):
                    break
                try:
                    win32pipe.DisconnectNamedPipe(handle)
                except pywintypes.error as error:
                    if error.winerror not in _DISCONNECT_ERRORS:
                        raise
        finally:
            self.stop()
            self._join_workers()

    def _create_pipe(self, first_instance: bool) -> object:
        access = win32pipe.PIPE_ACCESS_DUPLEX | win32file.FILE_FLAG_OVERLAPPED
        if first_instance:
            access |= win32pipe.FILE_FLAG_FIRST_PIPE_INSTANCE
        return win32pipe.CreateNamedPipe(
            self.name,
            access,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            _MAX_INSTANCES,
            _PIPE_BUFFER_BYTES,
            _PIPE_BUFFER_BYTES,
            0,
            current_user_security_attributes(),
        )

    def _connect(self, handle: object, stop_event: threading.Event) -> bool:
        overlapped = pywintypes.OVERLAPPED()
        event = win32event.CreateEvent(None, True, False, None)
        overlapped.hEvent = event
        pending = False
        try:
            try:
                result = win32pipe.ConnectNamedPipe(handle, overlapped)
            except pywintypes.error as error:
                if error.winerror == winerror.ERROR_PIPE_CONNECTED:
                    return True
                if self._should_stop(stop_event) and error.winerror in _DISCONNECT_ERRORS:
                    return False
                if error.winerror != winerror.ERROR_IO_PENDING:
                    raise
                pending = True
            else:
                if result == winerror.ERROR_IO_PENDING:
                    pending = True
                elif result == winerror.ERROR_PIPE_CONNECTED:
                    return True
                elif result not in {None, 0}:
                    raise OSError(result, "ConnectNamedPipe returned an unexpected status")
            while pending:
                result = win32event.WaitForSingleObject(event, _POLL_MILLISECONDS)
                if result == win32event.WAIT_OBJECT_0:
                    win32file.GetOverlappedResult(handle, overlapped, False)
                    return True
                if self._should_stop(stop_event):
                    try:
                        win32file.CancelIo(handle)
                    except pywintypes.error as error:
                        if error.winerror not in _DISCONNECT_ERRORS:
                            raise
                    win32event.WaitForSingleObject(event, 1000)
                    return False
            return True
        finally:
            win32file.CloseHandle(event)

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
                response = handler(body)
                if response is None:
                    continue
                if not isinstance(response, bytes):
                    raise TypeError("pipe handler response must be bytes or None")
                if not 0 < len(response) <= MAX_FRAME_BYTES:
                    return
                self._write_all(handle, _LENGTH.pack(len(response)) + response)
        except pywintypes.error as error:
            if error.winerror not in _DISCONNECT_ERRORS:
                raise

    @staticmethod
    def _read_exact(handle: object, size: int) -> bytes | None:
        data = bytearray()
        while len(data) < size:
            try:
                _, chunk = win32file.ReadFile(handle, size - len(data))
            except pywintypes.error as error:
                if error.winerror in _DISCONNECT_ERRORS:
                    return None
                raise
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data)

    @staticmethod
    def _write_all(handle: object, data: bytes) -> None:
        offset = 0
        while offset < len(data):
            _, written = win32file.WriteFile(handle, data[offset:])
            if isinstance(written, int):
                if written <= 0:
                    raise OSError("named pipe write made no progress")
                offset += written
            else:
                # pywin32 synchronous handles return the written bytes.
                offset += len(written)

    def _track_handle(self, handle: object) -> None:
        with self._lock:
            self._handles.add(handle)

    def _close_handle(self, handle: object) -> None:
        with self._lock:
            if handle not in self._handles:
                return
            self._handles.remove(handle)
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

    def _reap_workers(self) -> None:
        with self._lock:
            finished = {worker for worker in self._workers if not worker.is_alive()}
            self._workers.difference_update(finished)
        for worker in finished:
            worker.join()

    def _join_workers(self) -> None:
        with self._lock:
            workers = tuple(self._workers)
        for worker in workers:
            worker.join(timeout=5)
        with self._lock:
            self._workers = {worker for worker in self._workers if worker.is_alive()}
