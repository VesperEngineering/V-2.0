"""Truthful, read-only Windows host metrics for the operations console."""

from __future__ import annotations

import csv
import ctypes
import io
import math
import os
import shutil
import stat
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from vesper.platform.tui.ports import SourceSample, SystemFacts
from vesper.platform.tui.process_capture import run_bounded_process
from vesper.platform.tui.views import Freshness, MetricRow, ServiceRow


_NVIDIA_QUERY_ARGS = (
    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
    "--format=csv,noheader,nounits",
)
_MAX_NVIDIA_OUTPUT_BYTES = 64 * 1024
_MAX_GPU_ROWS = 16
_DEFAULT_NVIDIA = object()
_SAFE_PROCESS_CWD = Path(Path(__file__).resolve().anchor)


class SystemApi(Protocol):
    def cpu_percent(self) -> float: ...

    def memory_bytes(self) -> tuple[int, int]: ...


class _UnavailableSystemApi:
    def cpu_percent(self) -> float:
        raise OSError("Windows CPU counters are unavailable")

    def memory_bytes(self) -> tuple[int, int]:
        raise OSError("Windows memory counters are unavailable")


class _FileTime(ctypes.Structure):
    _fields_ = (("low", ctypes.c_uint32), ("high", ctypes.c_uint32))


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = (
        ("length", ctypes.c_uint32),
        ("memory_load", ctypes.c_uint32),
        ("total_physical", ctypes.c_uint64),
        ("available_physical", ctypes.c_uint64),
        ("total_page_file", ctypes.c_uint64),
        ("available_page_file", ctypes.c_uint64),
        ("total_virtual", ctypes.c_uint64),
        ("available_virtual", ctypes.c_uint64),
        ("available_extended_virtual", ctypes.c_uint64),
    )


def _filetime_value(value: _FileTime) -> int:
    return (int(value.high) << 32) | int(value.low)


class _CtypesWindowsSystemApi:
    """Small kernel32 reader; it never opens a process or changes host state."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Windows system APIs are unavailable on this platform")
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._previous_times: tuple[int, int, int] | None = None
        try:
            self._previous_times = self._system_times()
        except OSError:
            pass

    def _system_times(self) -> tuple[int, int, int]:
        idle = _FileTime()
        kernel = _FileTime()
        user = _FileTime()
        if not self._kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return (_filetime_value(idle), _filetime_value(kernel), _filetime_value(user))

    def cpu_percent(self) -> float:
        current = self._system_times()
        previous = self._previous_times
        self._previous_times = current
        if previous is None:
            raise OSError("CPU utilization needs a prior counter sample")
        idle_delta = current[0] - previous[0]
        total_delta = (current[1] - previous[1]) + (current[2] - previous[2])
        if total_delta <= 0 or idle_delta < 0 or idle_delta > total_delta:
            raise OSError("Windows CPU counters did not advance safely")
        return 100.0 * (total_delta - idle_delta) / total_delta

    def memory_bytes(self) -> tuple[int, int]:
        status = _MemoryStatusEx()
        status.length = ctypes.sizeof(status)
        if not self._kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        total = int(status.total_physical)
        available = int(status.available_physical)
        return total - available, total


def _default_system_api() -> SystemApi:
    try:
        return _CtypesWindowsSystemApi()
    except (AttributeError, OSError):
        return _UnavailableSystemApi()


def _is_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return path.is_symlink() or bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)


def _windows_system_directory() -> Path | None:
    """Resolve System32 through the Windows API, never process environment."""

    if os.name != "nt":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_system_directory = kernel32.GetSystemDirectoryW
        get_system_directory.restype = ctypes.c_uint
        buffer = ctypes.create_unicode_buffer(32_768)
        length = get_system_directory(buffer, len(buffer))
    except (AttributeError, OSError, ValueError):
        return None
    if length == 0 or length >= len(buffer):
        return None
    directory = Path(buffer.value)
    return directory if directory.is_absolute() else None


def _trusted_nvidia_smi() -> str | None:
    try:
        system_directory = _windows_system_directory()
        if system_directory is None or _is_reparse_point(system_directory):
            return None
        trusted_directory = system_directory.resolve(strict=True)
        candidate = trusted_directory / "nvidia-smi.exe"
        if not candidate.is_file() or _is_reparse_point(candidate):
            return None
        resolved = candidate.resolve(strict=True)
        if resolved.parent != trusted_directory or not resolved.is_file():
            return None
        return str(resolved)
    except (OSError, ValueError):
        return None


def _nvidia_environment() -> dict[str, str]:
    return {"LANG": "C", "LC_ALL": "C"}


def _bounded_nvidia_process_run(
    command: tuple[str, ...],
    *,
    cwd: Path,
    timeout: float,
    shell: bool,
    stdin: int,
    stdout: int,
    stderr: int,
    check: bool,
    env: Mapping[str, str],
) -> subprocess.CompletedProcess[bytes]:
    return run_bounded_process(
        command,
        max_output_bytes=_MAX_NVIDIA_OUTPUT_BYTES,
        cwd=cwd,
        timeout=timeout,
        shell=shell,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        check=check,
        env=env,
    )


_DEFAULT_RUNNER = _bounded_nvidia_process_run


def _validated_nvidia_smi(
    executable: str | Path,
    runner: Callable[..., subprocess.CompletedProcess[bytes]],
) -> str:
    if not isinstance(executable, (str, Path)):
        raise TypeError("nvidia-smi executable must be a string or pathlib.Path")
    if executable == "nvidia-smi" and runner is not _DEFAULT_RUNNER:
        return "nvidia-smi"
    candidate = Path(executable)
    if (
        not candidate.is_absolute()
        or candidate.name.casefold() != "nvidia-smi.exe"
        or _is_reparse_point(candidate)
    ):
        raise ValueError("GPU executable must be a trusted nvidia-smi binary")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("GPU executable must be a trusted nvidia-smi binary") from exc
    if not resolved.is_file() or _is_reparse_point(resolved):
        raise ValueError("GPU executable must be a trusted nvidia-smi binary")
    if runner is _DEFAULT_RUNNER:
        trusted = _trusted_nvidia_smi()
        if trusted is None or os.path.normcase(str(resolved)) != os.path.normcase(trusted):
            raise ValueError("GPU executable must be a trusted nvidia-smi binary")
    return str(resolved)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fresh_metric(metric_id: str, value: float, unit: str, observed_at: datetime) -> MetricRow:
    return MetricRow(
        metric_id=metric_id,
        value=value,
        unit=unit,
        freshness=Freshness.FRESH,
        observed_at_utc=observed_at,
        error=None,
    )


def _unavailable_metric(metric_id: str, unit: str, reason: str) -> MetricRow:
    return MetricRow(
        metric_id=metric_id,
        value=None,
        unit=unit,
        freshness=Freshness.UNAVAILABLE,
        observed_at_utc=None,
        error=reason,
    )


def _plain_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("metric is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("metric is not finite")
    return result


class WindowsSystemProjection:
    """Read independent host facts without touching V20 runtime control."""

    def __init__(
        self,
        *,
        disk_paths: Mapping[str, Path] | None = None,
        clock: Callable[[], datetime] = _utc_now,
        system_api: SystemApi | None = None,
        disk_usage: Callable[[Path], object] = shutil.disk_usage,
        service_reader: Callable[[datetime], tuple[ServiceRow, ...]] | None = None,
        nvidia_smi_executable: str | Path | None | object = _DEFAULT_NVIDIA,
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = _DEFAULT_RUNNER,
    ) -> None:
        if runner is subprocess.run:
            raise ValueError("The injected GPU test runner must not execute real processes.")
        self._clock = clock
        self._system_api = system_api if system_api is not None else _default_system_api()
        self._disk_usage = disk_usage
        self._service_reader = service_reader
        self._runner = runner
        self._disk_paths = self._validate_disk_paths(
            {"workspace": Path.cwd()} if disk_paths is None else disk_paths
        )
        if nvidia_smi_executable is _DEFAULT_NVIDIA:
            self._nvidia_smi_executable = _trusted_nvidia_smi()
        elif nvidia_smi_executable is None:
            self._nvidia_smi_executable = None
        else:
            self._nvidia_smi_executable = _validated_nvidia_smi(
                nvidia_smi_executable,
                runner,
            )

    @staticmethod
    def _validate_disk_paths(paths: Mapping[str, Path]) -> tuple[tuple[str, Path], ...]:
        if not paths or len(paths) > 8:
            raise ValueError("disk_paths must contain between one and eight roots")
        rows: list[tuple[str, Path]] = []
        for alias, path in paths.items():
            if (
                not isinstance(alias, str)
                or not alias
                or len(alias) > 64
                or not alias[0].isalnum()
                or any(not (character.isalnum() or character in "._:-") for character in alias)
            ):
                raise ValueError("disk alias must be a safe identifier")
            if not isinstance(path, Path):
                raise TypeError("disk paths must be pathlib.Path values")
            rows.append((alias, path))
        return tuple(sorted(rows))

    def read(self) -> SourceSample[SystemFacts]:
        try:
            observed_at = self._clock()
            if not isinstance(observed_at, datetime) or observed_at.utcoffset() != timedelta(0):
                raise ValueError("clock is not UTC")
        except Exception:
            return SourceSample[SystemFacts](
                value=None,
                freshness=Freshness.UNAVAILABLE,
                observed_at_utc=None,
                source="windows-system",
                error="Windows system clock did not return UTC.",
            )

        services, services_error = self._read_services(observed_at)
        metrics = (
            *self._read_cpu(observed_at),
            *self._read_memory(observed_at),
            *self._read_disks(observed_at),
            *self._read_gpus(observed_at),
        )
        facts = SystemFacts(
            services=services,
            services_error=services_error,
            metrics=metrics,
            metrics_error=None,
            repositories=None,
            repositories_error="Repository facts use a separate read port.",
        )
        return SourceSample[SystemFacts](
            value=facts,
            freshness=Freshness.FRESH,
            observed_at_utc=observed_at,
            source="windows-system",
            error=None,
        )

    def _read_services(
        self, observed_at: datetime
    ) -> tuple[tuple[ServiceRow, ...] | None, str | None]:
        if self._service_reader is None:
            return None, "No controller-owned service reader is configured."
        try:
            rows = self._service_reader(observed_at)
            if type(rows) is not tuple or any(type(row) is not ServiceRow for row in rows):
                raise ValueError("service reader returned invalid rows")
            return rows, None
        except Exception:
            return None, "Service status is unavailable."

    def _read_cpu(self, observed_at: datetime) -> tuple[MetricRow, ...]:
        metric_id = "system.cpu.utilization"
        try:
            value = _plain_number(self._system_api.cpu_percent())
            if not 0 <= value <= 100:
                raise ValueError("CPU utilization is outside 0..100")
            return (_fresh_metric(metric_id, value, "percent", observed_at),)
        except Exception:
            return (_unavailable_metric(metric_id, "percent", "CPU utilization is unavailable."),)

    def _read_memory(self, observed_at: datetime) -> tuple[MetricRow, ...]:
        identifiers = (
            ("system.memory.used-bytes", "bytes"),
            ("system.memory.total-bytes", "bytes"),
        )
        try:
            values = self._system_api.memory_bytes()
            if type(values) is not tuple or len(values) != 2:
                raise ValueError("memory reader returned invalid values")
            used, total = (_plain_number(item) for item in values)
            if used < 0 or total <= 0 or used > total:
                raise ValueError("memory values are outside valid bounds")
            return (
                _fresh_metric(identifiers[0][0], used, identifiers[0][1], observed_at),
                _fresh_metric(identifiers[1][0], total, identifiers[1][1], observed_at),
            )
        except Exception:
            return tuple(
                _unavailable_metric(metric_id, unit, "Memory metrics are unavailable.")
                for metric_id, unit in identifiers
            )

    def _read_disks(self, observed_at: datetime) -> tuple[MetricRow, ...]:
        rows: list[MetricRow] = []
        for alias, path in self._disk_paths:
            identifiers = (
                (f"system.disk.{alias}.used-bytes", "bytes"),
                (f"system.disk.{alias}.total-bytes", "bytes"),
                (f"system.disk.{alias}.free-bytes", "bytes"),
            )
            try:
                usage = self._disk_usage(path)
                used = _plain_number(getattr(usage, "used"))
                total = _plain_number(getattr(usage, "total"))
                free = _plain_number(getattr(usage, "free"))
                if (
                    used < 0
                    or total <= 0
                    or free < 0
                    or used > total
                    or free > total
                    or used + free > total
                ):
                    raise ValueError("disk values are outside valid bounds")
                rows.extend(
                    (
                        _fresh_metric(identifiers[0][0], used, "bytes", observed_at),
                        _fresh_metric(identifiers[1][0], total, "bytes", observed_at),
                        _fresh_metric(identifiers[2][0], free, "bytes", observed_at),
                    )
                )
            except Exception:
                rows.extend(
                    _unavailable_metric(metric_id, unit, f"Disk {alias} is unavailable.")
                    for metric_id, unit in identifiers
                )
        return tuple(rows)

    def _read_gpus(self, observed_at: datetime) -> tuple[MetricRow, ...]:
        executable = self._nvidia_smi_executable
        if executable is None:
            return self._unavailable_gpu_rows(0, "NVIDIA GPU metrics are unavailable.")
        argv = (executable, *_NVIDIA_QUERY_ARGS)
        try:
            completed = self._runner(
                argv,
                check=False,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                cwd=_SAFE_PROCESS_CWD,
                env=_nvidia_environment(),
            )
            stdout = completed.stdout
            stderr = completed.stderr
            if (
                type(completed.returncode) is not int
                or completed.returncode != 0
                or type(stdout) is not bytes
                or type(stderr) is not bytes
                or len(stdout) > _MAX_NVIDIA_OUTPUT_BYTES
                or len(stderr) > _MAX_NVIDIA_OUTPUT_BYTES
            ):
                raise ValueError("nvidia-smi failed or exceeded its output bound")
            text = stdout.decode("utf-8", errors="strict")
            parsed = tuple(csv.reader(io.StringIO(text), skipinitialspace=True, strict=True))
            if not parsed or len(parsed) > _MAX_GPU_ROWS:
                raise ValueError("nvidia-smi returned an invalid GPU count")
        except (OSError, RuntimeError, ValueError, csv.Error, subprocess.SubprocessError):
            return self._unavailable_gpu_rows(0, "NVIDIA GPU metrics are unavailable.")

        rows: list[MetricRow] = []
        for index, fields in enumerate(parsed):
            rows.extend(self._parse_gpu(index, fields, observed_at))
        return tuple(rows)

    def _parse_gpu(
        self, index: int, fields: Sequence[str], observed_at: datetime
    ) -> tuple[MetricRow, ...]:
        if len(fields) != 5 or not fields[0].strip():
            return self._unavailable_gpu_rows(index, f"GPU {index} returned malformed metrics.")
        utilization_id = f"system.gpu.{index}.utilization"
        memory_used_id = f"system.gpu.{index}.memory-used-mib"
        memory_total_id = f"system.gpu.{index}.memory-total-mib"
        temperature_id = f"system.gpu.{index}.temperature-c"
        rows: list[MetricRow] = []

        try:
            utilization = _parse_finite_text(fields[1])
            if not 0 <= utilization <= 100:
                raise ValueError("utilization outside range")
            rows.append(_fresh_metric(utilization_id, utilization, "percent", observed_at))
        except ValueError:
            rows.append(
                _unavailable_metric(utilization_id, "percent", f"GPU {index} utilization is unavailable.")
            )

        try:
            used = _parse_finite_text(fields[2])
            total = _parse_finite_text(fields[3])
            if used < 0 or total <= 0 or used > total:
                raise ValueError("memory outside range")
            rows.extend(
                (
                    _fresh_metric(memory_used_id, used, "MiB", observed_at),
                    _fresh_metric(memory_total_id, total, "MiB", observed_at),
                )
            )
        except ValueError:
            rows.extend(
                (
                    _unavailable_metric(
                        memory_used_id, "MiB", f"GPU {index} memory is unavailable."
                    ),
                    _unavailable_metric(
                        memory_total_id, "MiB", f"GPU {index} memory is unavailable."
                    ),
                )
            )

        try:
            temperature = _parse_finite_text(fields[4])
            if not 0 <= temperature <= 150:
                raise ValueError("temperature outside range")
            rows.append(_fresh_metric(temperature_id, temperature, "celsius", observed_at))
        except ValueError:
            rows.append(
                _unavailable_metric(
                    temperature_id, "celsius", f"GPU {index} temperature is unavailable."
                )
            )
        return tuple(rows)

    @staticmethod
    def _unavailable_gpu_rows(index: int, reason: str) -> tuple[MetricRow, ...]:
        return (
            _unavailable_metric(f"system.gpu.{index}.utilization", "percent", reason),
            _unavailable_metric(f"system.gpu.{index}.memory-used-mib", "MiB", reason),
            _unavailable_metric(f"system.gpu.{index}.memory-total-mib", "MiB", reason),
            _unavailable_metric(f"system.gpu.{index}.temperature-c", "celsius", reason),
        )


def _parse_finite_text(value: str) -> float:
    result = float(value.strip())
    if not math.isfinite(result):
        raise ValueError("GPU metric is not finite")
    return result
