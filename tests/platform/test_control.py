from __future__ import annotations

import subprocess
import sys
import time

from vesper.platform.control import RuntimeControl


def test_runtime_control_discovers_active_run_and_shares_cancellation(tmp_path):
    control = RuntimeControl(tmp_path / "control")
    control.register_run(
        {
            "run_id": "run-001",
            "task_id": "task-001",
            "repository_revision": "abc123",
        }
    )
    control.mark_active(
        run_id="run-001",
        execution_id="execution-001",
        sandbox_name="v20-development-test",
        role="v20-development",
        attempt=1,
    )

    active = control.list_active_runs()
    assert active[0]["run_id"] == "run-001"
    assert active[0]["active_execution"]["sandbox_name"] == "v20-development-test"
    assert control.cancellation_signal("run-001").is_set() is False

    control.request_cancel("run-001", "operator requested cancellation")

    assert control.cancellation_signal("run-001").is_set() is True
    control.clear_active("run-001", "execution-001")
    control.set_run_status("run-001", "cancelled")
    assert control.active_execution("run-001") is None
    assert control.list_active_runs() == ()


def test_cancellation_signal_crosses_a_real_process_boundary(tmp_path):
    root = tmp_path / "control"
    script = f"""
import time
from pathlib import Path
from vesper.platform.control import RuntimeControl

control = RuntimeControl(Path({str(root)!r}))
control.register_run({{"run_id": "run-001", "task_id": "task-001"}})
control.mark_active(
    run_id="run-001",
    execution_id="execution-001",
    sandbox_name="v20-development-test",
    role="v20-development",
    attempt=1,
)
signal = control.cancellation_signal("run-001")
deadline = time.monotonic() + 10
while not signal.is_set() and time.monotonic() < deadline:
    time.sleep(0.01)
raise SystemExit(0 if signal.is_set() else 3)
"""
    process = subprocess.Popen([sys.executable, "-c", script])
    control = RuntimeControl(root)
    deadline = time.monotonic() + 5
    while control.active_execution("run-001") is None and time.monotonic() < deadline:
        time.sleep(0.01)

    control.request_cancel("run-001", "parent process requested cancellation")
    returncode = process.wait(timeout=5)

    assert returncode == 0


def test_runtime_control_retains_transient_graph_statuses_in_active_listing(tmp_path):
    control = RuntimeControl(tmp_path / "control")
    control.register_run({"run_id": "run-001", "task_id": "task-001"})
    control.set_run_status("run-001", "validation")

    assert control.list_active_runs()[0]["run_id"] == "run-001"
