"""Bounded binary subprocess capture shared by read-only TUI projections."""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any


READ_CHUNK_BYTES = 64 * 1024
_PROCESS_POLL_SECONDS = 0.05
_PROCESS_STOP_TIMEOUT_SECONDS = 1


class BoundedProcessError(RuntimeError):
    """Base error for a bounded process capture failure."""


class BoundedProcessConfigurationError(BoundedProcessError):
    """The caller requested unsafe process controls."""


class BoundedProcessPipesUnavailableError(BoundedProcessError):
    """The requested binary output pipes were not created."""


class BoundedProcessStreamCloseError(BoundedProcessError):
    """An output reader did not stop after the child was stopped."""


class BoundedProcessOutputLimitError(BoundedProcessError):
    """At least one output stream exceeded its independent byte limit."""


class BoundedProcessReadError(BoundedProcessError):
    """An output stream could not be read safely."""


def _drain_bounded(
    stream: Any,
    output: bytearray,
    overflow: threading.Event,
    read_errors: list[BaseException],
    error_lock: threading.Lock,
    max_output_bytes: int,
) -> None:
    try:
        while chunk := stream.read(READ_CHUNK_BYTES):
            remaining = max_output_bytes - len(output)
            if remaining > 0:
                output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                overflow.set()
    except (OSError, ValueError) as exc:
        with error_lock:
            read_errors.append(exc)


def _stop_process(process: Any) -> None:
    if process.returncode is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=_PROCESS_STOP_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=_PROCESS_STOP_TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            pass


def run_bounded_process(
    command: tuple[str, ...],
    *,
    max_output_bytes: int,
    cwd: Path,
    timeout: float,
    shell: bool,
    stdin: int,
    stdout: int,
    stderr: int,
    check: bool,
    env: Mapping[str, str],
) -> subprocess.CompletedProcess[bytes]:
    """Run one process while retaining at most the limit per output stream."""
    if (
        type(max_output_bytes) is not int
        or max_output_bytes <= 0
        or shell
        or stdin != subprocess.DEVNULL
        or stdout != subprocess.PIPE
        or stderr != subprocess.PIPE
        or check
    ):
        raise BoundedProcessConfigurationError("Unsafe process runner configuration.")

    process = subprocess.Popen(
        command,
        cwd=cwd,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(env),
    )
    if process.stdout is None or process.stderr is None:
        _stop_process(process)
        raise BoundedProcessPipesUnavailableError("Process output pipes were unavailable.")

    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    overflow = threading.Event()
    read_errors: list[BaseException] = []
    error_lock = threading.Lock()
    threads = (
        threading.Thread(
            target=_drain_bounded,
            args=(
                process.stdout,
                stdout_buffer,
                overflow,
                read_errors,
                error_lock,
                max_output_bytes,
            ),
            daemon=True,
            name="bounded-process-stdout",
        ),
        threading.Thread(
            target=_drain_bounded,
            args=(
                process.stderr,
                stderr_buffer,
                overflow,
                read_errors,
                error_lock,
                max_output_bytes,
            ),
            daemon=True,
            name="bounded-process-stderr",
        ),
    )
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + timeout
    timed_out = False
    try:
        while process.returncode is None:
            if overflow.is_set():
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                process.wait(timeout=min(_PROCESS_POLL_SECONDS, remaining))
            except subprocess.TimeoutExpired:
                continue
        if overflow.is_set() or timed_out:
            _stop_process(process)
        for thread in threads:
            thread.join(timeout=_PROCESS_STOP_TIMEOUT_SECONDS)
        if any(thread.is_alive() for thread in threads):
            _stop_process(process)
            raise BoundedProcessStreamCloseError("Process output stream did not close.")
    finally:
        process.stdout.close()
        process.stderr.close()

    if overflow.is_set():
        raise BoundedProcessOutputLimitError("Process output exceeded the safe size limit.")
    if timed_out:
        raise subprocess.TimeoutExpired(command, timeout)
    if read_errors:
        raise BoundedProcessReadError("Process output could not be read.") from read_errors[0]
    return subprocess.CompletedProcess(
        command,
        process.returncode,
        stdout=bytes(stdout_buffer),
        stderr=bytes(stderr_buffer),
    )
