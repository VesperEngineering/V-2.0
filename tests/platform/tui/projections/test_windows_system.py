from __future__ import annotations

import subprocess
import threading
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from vesper.platform.tui.projections import windows_system
from vesper.platform.tui.ports import SourceSample
from vesper.platform.tui.projections.windows_system import WindowsSystemProjection
from vesper.platform.tui.views import Freshness, ServiceRow


NOW = datetime(2026, 8, 3, 16, 0, tzinfo=timezone.utc)
NVIDIA_ARGS = [
    "nvidia-smi",
    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
    "--format=csv,noheader,nounits",
]
DiskUsage = namedtuple("DiskUsage", "total used free")


class FakeSystemApi:
    def __init__(
        self,
        *,
        cpu: float | BaseException = 25.0,
        memory: tuple[int, int] | BaseException = (4_000, 16_000),
    ) -> None:
        self.cpu = cpu
        self.memory = memory

    def cpu_percent(self) -> float:
        if isinstance(self.cpu, BaseException):
            raise self.cpu
        return self.cpu

    def memory_bytes(self) -> tuple[int, int]:
        if isinstance(self.memory, BaseException):
            raise self.memory
        return self.memory


def _runner(stdout: bytes, *, returncode: int = 0):
    def run(argv, **kwargs):
        assert list(argv) == NVIDIA_ARGS
        assert kwargs == {
            "check": False,
            "shell": False,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "timeout": 5,
            "cwd": Path(Path(windows_system.__file__).resolve().anchor),
            "env": {"LANG": "C", "LC_ALL": "C"},
        }
        return subprocess.CompletedProcess(argv, returncode, stdout, b"driver error")

    return run


def _projection(tmp_path, **changes) -> WindowsSystemProjection:
    options = {
        "clock": lambda: NOW,
        "disk_paths": {"workspace": tmp_path},
        "system_api": FakeSystemApi(),
        "disk_usage": lambda _path: DiskUsage(1_000, 400, 600),
        "service_reader": lambda observed_at: (
            ServiceRow(
                service_id="v20-runtime",
                state="running",
                health_reason=None,
                observed_at_utc=observed_at,
            ),
        ),
        "nvidia_smi_executable": "nvidia-smi",
        "runner": _runner(b"RTX 5070 Ti, 12, 2048, 16384, 54\n"),
    }
    options.update(changes)
    return WindowsSystemProjection(**options)


def _metrics(sample: SourceSample):
    assert sample.value is not None
    assert sample.value.metrics is not None
    return {row.metric_id: row for row in sample.value.metrics}


def test_read_returns_truthful_system_facts_and_exact_nvidia_command(tmp_path) -> None:
    sample = _projection(
        tmp_path,
        runner=_runner(
            b"RTX 5070 Ti, 12, 2048, 16384, 54\n"
            b"RTX 4000, 50.5, 4096, 8192, 61\n"
        ),
    ).read()

    assert sample.freshness is Freshness.FRESH
    assert sample.observed_at_utc == NOW
    assert sample.error is None
    assert sample.value is not None
    assert sample.value.services is not None
    assert sample.value.services[0].service_id == "v20-runtime"
    assert sample.value.repositories is None
    assert sample.value.repositories_error == "Repository facts use a separate read port."

    rows = _metrics(sample)
    expected = {
        "system.cpu.utilization": (25.0, "percent"),
        "system.memory.used-bytes": (4_000.0, "bytes"),
        "system.memory.total-bytes": (16_000.0, "bytes"),
        "system.disk.workspace.used-bytes": (400.0, "bytes"),
        "system.disk.workspace.total-bytes": (1_000.0, "bytes"),
        "system.disk.workspace.free-bytes": (600.0, "bytes"),
        "system.gpu.0.utilization": (12.0, "percent"),
        "system.gpu.0.memory-used-mib": (2_048.0, "MiB"),
        "system.gpu.0.memory-total-mib": (16_384.0, "MiB"),
        "system.gpu.0.temperature-c": (54.0, "celsius"),
        "system.gpu.1.utilization": (50.5, "percent"),
        "system.gpu.1.memory-used-mib": (4_096.0, "MiB"),
        "system.gpu.1.memory-total-mib": (8_192.0, "MiB"),
        "system.gpu.1.temperature-c": (61.0, "celsius"),
    }
    for metric_id, (value, unit) in expected.items():
        assert rows[metric_id].value == value
        assert rows[metric_id].unit == unit
        assert rows[metric_id].freshness is Freshness.FRESH
        assert rows[metric_id].observed_at_utc == NOW
        assert rows[metric_id].error is None


@pytest.mark.parametrize(
    "runner",
    (
        _runner(b"", returncode=1),
        _runner(b"x" * 65_537),
        _runner(b"\xff"),
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("nvidia-smi", 5)
        ),
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("runner failed")),
    ),
)
def test_gpu_failure_is_bounded_and_does_not_hide_cpu_memory_or_disk(
    tmp_path, runner
) -> None:
    sample = _projection(tmp_path, runner=runner).read()
    rows = _metrics(sample)

    assert rows["system.cpu.utilization"].freshness is Freshness.FRESH
    assert rows["system.memory.used-bytes"].freshness is Freshness.FRESH
    assert rows["system.disk.workspace.used-bytes"].freshness is Freshness.FRESH
    for suffix in (
        "utilization",
        "memory-used-mib",
        "memory-total-mib",
        "temperature-c",
    ):
        row = rows[f"system.gpu.0.{suffix}"]
        assert row.freshness is Freshness.UNAVAILABLE
        assert row.value is None
        assert row.observed_at_utc is None
        assert row.error


def test_gpu_runner_boundary_assertions_are_not_swallowed(tmp_path) -> None:
    def boundary_spy(*_args, **_kwargs):
        raise AssertionError("GPU process controls changed")

    with pytest.raises(AssertionError, match="GPU process controls changed"):
        _projection(tmp_path, runner=boundary_spy).read()


def test_malformed_gpu_field_is_isolated_to_that_metric(tmp_path) -> None:
    sample = _projection(
        tmp_path,
        runner=_runner(b"GPU A, bad, 100, 1000, 55\nGPU B, 101, 1001, 1000, -1\n"),
    ).read()
    rows = _metrics(sample)

    assert rows["system.gpu.0.utilization"].freshness is Freshness.UNAVAILABLE
    assert rows["system.gpu.0.memory-used-mib"].freshness is Freshness.FRESH
    assert rows["system.gpu.0.memory-total-mib"].freshness is Freshness.FRESH
    assert rows["system.gpu.0.temperature-c"].freshness is Freshness.FRESH
    for suffix in (
        "utilization",
        "memory-used-mib",
        "memory-total-mib",
        "temperature-c",
    ):
        assert rows[f"system.gpu.1.{suffix}"].freshness is Freshness.UNAVAILABLE


def test_cpu_memory_disk_and_service_failures_are_isolated(tmp_path) -> None:
    def disk_usage(path):
        if str(path).endswith("bad"):
            raise OSError("disk offline")
        return DiskUsage(1_000, 400, 600)

    def services(_observed_at):
        raise OSError("service registry offline")

    sample = _projection(
        tmp_path,
        disk_paths={"good": tmp_path / "good", "bad": tmp_path / "bad"},
        system_api=FakeSystemApi(cpu=OSError("counter offline"), memory=(2_000, 8_000)),
        disk_usage=disk_usage,
        service_reader=services,
    ).read()
    assert sample.value is not None
    assert sample.value.services is None
    assert sample.value.services_error == "Service status is unavailable."
    rows = _metrics(sample)
    assert rows["system.cpu.utilization"].freshness is Freshness.UNAVAILABLE
    assert rows["system.memory.used-bytes"].freshness is Freshness.FRESH
    assert rows["system.disk.good.used-bytes"].freshness is Freshness.FRESH
    assert rows["system.disk.bad.used-bytes"].freshness is Freshness.UNAVAILABLE


@pytest.mark.parametrize(
    ("cpu", "memory"),
    (
        (float("nan"), (1, 2)),
        (101.0, (1, 2)),
        (50.0, (-1, 2)),
        (50.0, (3, 2)),
        (50.0, (1, 0)),
    ),
)
def test_nonfinite_or_out_of_range_system_values_are_unavailable(
    tmp_path, cpu, memory
) -> None:
    rows = _metrics(
        _projection(tmp_path, system_api=FakeSystemApi(cpu=cpu, memory=memory)).read()
    )
    if not isinstance(cpu, float) or not 0 <= cpu <= 100:
        assert rows["system.cpu.utilization"].freshness is Freshness.UNAVAILABLE
    if memory[0] < 0 or memory[1] <= 0 or memory[0] > memory[1]:
        assert rows["system.memory.used-bytes"].freshness is Freshness.UNAVAILABLE
        assert rows["system.memory.total-bytes"].freshness is Freshness.UNAVAILABLE


def test_missing_trusted_nvidia_binary_never_launches_a_process(tmp_path) -> None:
    def forbidden_runner(*_args, **_kwargs):
        raise AssertionError("no process may launch without a trusted executable")

    rows = _metrics(
        _projection(
            tmp_path,
            nvidia_smi_executable=None,
            runner=forbidden_runner,
        ).read()
    )
    assert rows["system.gpu.0.utilization"].freshness is Freshness.UNAVAILABLE


def test_default_gpu_discovery_and_child_environment_ignore_poisoned_environment(
    monkeypatch,
    tmp_path,
) -> None:
    trusted_system = tmp_path / "trusted" / "System32"
    trusted_system.mkdir(parents=True)
    trusted_executable = trusted_system / "nvidia-smi.exe"
    trusted_executable.touch()

    poisoned_root = tmp_path / "poisoned-windows"
    poisoned_system = poisoned_root / "System32"
    poisoned_system.mkdir(parents=True)
    (poisoned_system / "nvidia-smi.exe").touch()
    poisoned_program_files = tmp_path / "poisoned-program-files"
    poisoned_nv = poisoned_program_files / "NVIDIA Corporation" / "NVSMI"
    poisoned_nv.mkdir(parents=True)
    (poisoned_nv / "nvidia-smi.exe").touch()

    poisoned = {
        "SystemRoot": str(poisoned_root),
        "ProgramFiles": str(poisoned_program_files),
        "PATH": str(poisoned_system),
        "ALPACA_KEY_ID": "never-inherit",
        "ALPACA_SECRET_KEY": "never-inherit",
        "ALPACA_API_KEY": "never-inherit",
        "ALPACA_API_SECRET": "never-inherit",
    }
    for name, value in poisoned.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        windows_system,
        "_windows_system_directory",
        lambda: trusted_system,
        raising=False,
    )

    calls = []

    def runner(argv, **kwargs):
        calls.append((tuple(argv), kwargs))
        return subprocess.CompletedProcess(
            argv,
            0,
            b"RTX 5070 Ti, 12, 2048, 16384, 54\n",
            b"",
        )

    sample = WindowsSystemProjection(
        clock=lambda: NOW,
        disk_paths={"workspace": tmp_path},
        system_api=FakeSystemApi(),
        disk_usage=lambda _path: DiskUsage(1_000, 400, 600),
        runner=runner,
    ).read()

    assert _metrics(sample)["system.gpu.0.utilization"].freshness is Freshness.FRESH
    assert calls[0][0][0] == str(trusted_executable.resolve())
    assert calls[0][1]["cwd"] == Path(Path(windows_system.__file__).resolve().anchor)
    assert calls[0][1]["env"] == {"LANG": "C", "LC_ALL": "C"}
    assert not set(poisoned).intersection(calls[0][1]["env"])


@pytest.mark.parametrize(
    "executable",
    (
        "cmd.exe",
        "powershell",
        "nvidia-smi.exe",
        Path("C:/Windows/System32/cmd.exe"),
        Path("C:/tools/powershell.exe"),
    ),
)
def test_constructor_rejects_arbitrary_gpu_executables(tmp_path, executable) -> None:
    with pytest.raises(ValueError, match="trusted nvidia-smi"):
        _projection(tmp_path, nvidia_smi_executable=executable)


def test_bare_nvidia_smi_requires_an_injected_runner(tmp_path) -> None:
    with pytest.raises(ValueError, match="trusted nvidia-smi"):
        WindowsSystemProjection(
            clock=lambda: NOW,
            disk_paths={"workspace": tmp_path},
            system_api=FakeSystemApi(),
            disk_usage=lambda _path: DiskUsage(1_000, 400, 600),
            nvidia_smi_executable="nvidia-smi",
        )


def test_existing_absolute_nvidia_smi_path_is_allowed(tmp_path) -> None:
    executable = tmp_path / "nvidia-smi.exe"
    executable.touch()
    observed_commands = []

    def runner(argv, **_kwargs):
        observed_commands.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, b"RTX 5070 Ti, 12, 2048, 16384, 54\n", b"")

    sample = _projection(
        tmp_path,
        nvidia_smi_executable=executable,
        runner=runner,
    ).read()

    assert observed_commands[0][0] == str(executable.resolve())
    assert _metrics(sample)["system.gpu.0.utilization"].freshness is Freshness.FRESH


def test_default_runner_rejects_untrusted_absolute_nvidia_smi_path(tmp_path) -> None:
    executable = tmp_path / "nvidia-smi.exe"
    executable.touch()

    with pytest.raises(ValueError, match="trusted nvidia-smi"):
        WindowsSystemProjection(
            clock=lambda: NOW,
            disk_paths={"workspace": tmp_path},
            system_api=FakeSystemApi(),
            disk_usage=lambda _path: DiskUsage(1_000, 400, 600),
            nvidia_smi_executable=executable,
        )


def test_subprocess_run_cannot_replace_the_bounded_default(tmp_path) -> None:
    with pytest.raises(ValueError, match="test runner"):
        WindowsSystemProjection(
            clock=lambda: NOW,
            disk_paths={"workspace": tmp_path},
            system_api=FakeSystemApi(),
            disk_usage=lambda _path: DiskUsage(1_000, 400, 600),
            runner=subprocess.run,
        )


def test_default_nvidia_runner_caps_streams_without_communicate(
    monkeypatch,
    tmp_path,
) -> None:
    trusted_executable = tmp_path / "nvidia-smi.exe"
    trusted_executable.touch()

    class ChunkedStream:
        def __init__(self) -> None:
            self.remaining = windows_system._MAX_NVIDIA_OUTPUT_BYTES + 1
            self.largest_read = 0
            self.closed = False
            self._lock = threading.Lock()

        def read(self, size: int) -> bytes:
            with self._lock:
                self.largest_read = max(self.largest_read, size)
                if self.remaining == 0:
                    return b""
                amount = min(size, self.remaining)
                self.remaining -= amount
                return b"x" * amount

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = ChunkedStream()
            self.stderr = ChunkedStream()
            self.returncode = 0
            self.communicate_calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def communicate(self, *_args, **_kwargs):
            self.communicate_calls += 1
            raise AssertionError("communicate() would buffer unbounded output")

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def terminate(self) -> None:
            self.returncode = -1

        def kill(self) -> None:
            self.returncode = -9

    process = FakeProcess()
    popen_calls = []

    def popen(argv, **kwargs):
        popen_calls.append((tuple(argv), kwargs))
        return process

    monkeypatch.setattr(
        windows_system,
        "_trusted_nvidia_smi",
        lambda: str(trusted_executable.resolve()),
    )
    monkeypatch.setattr(subprocess, "Popen", popen)

    sample = WindowsSystemProjection(
        clock=lambda: NOW,
        disk_paths={"workspace": tmp_path},
        system_api=FakeSystemApi(),
        disk_usage=lambda _path: DiskUsage(1_000, 400, 600),
    ).read()

    assert _metrics(sample)["system.gpu.0.utilization"].freshness is Freshness.UNAVAILABLE
    assert process.communicate_calls == 0
    assert 0 < process.stdout.largest_read <= windows_system._MAX_NVIDIA_OUTPUT_BYTES
    assert 0 < process.stderr.largest_read <= windows_system._MAX_NVIDIA_OUTPUT_BYTES
    assert process.stdout.closed
    assert process.stderr.closed
    assert popen_calls == [
        (
            (str(trusted_executable.resolve()), *windows_system._NVIDIA_QUERY_ARGS),
            {
                "cwd": windows_system._SAFE_PROCESS_CWD,
                "shell": False,
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "env": {"LANG": "C", "LC_ALL": "C"},
            },
        )
    ]


@pytest.mark.parametrize(
    "bad_time",
    (
        datetime(2026, 8, 3, 16, 0),
        datetime(2026, 8, 3, 12, 0, tzinfo=timezone(-timedelta(hours=4))),
    ),
)
def test_non_utc_clock_fails_closed_without_sampling(tmp_path, bad_time) -> None:
    class ForbiddenApi:
        def cpu_percent(self):
            raise AssertionError("invalid clock must fail before sampling")

        def memory_bytes(self):
            raise AssertionError("invalid clock must fail before sampling")

    sample = _projection(
        tmp_path,
        clock=lambda: bad_time,
        system_api=ForbiddenApi(),
    ).read()
    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.observed_at_utc is None
    assert sample.error == "Windows system clock did not return UTC."


def test_raising_clock_fails_closed_without_sampling(tmp_path) -> None:
    class ForbiddenApi:
        def cpu_percent(self):
            raise AssertionError("raising clock must fail before sampling")

        def memory_bytes(self):
            raise AssertionError("raising clock must fail before sampling")

    def raising_clock():
        raise RuntimeError("clock failed")

    sample = _projection(
        tmp_path,
        clock=raising_clock,
        system_api=ForbiddenApi(),
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.observed_at_utc is None
    assert sample.error == "Windows system clock did not return UTC."
