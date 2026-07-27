from __future__ import annotations

import os
import socket
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from vesper.platform.codex import CodexSdkAdapter
from vesper.platform.contracts import (
    ExecutionStatus,
    PermissionSet,
    SandboxMode,
    SpecialistInput,
    SpecialistRole,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class CompletedHandle:
    def stream(self):
        yield {
            "method": "turn/completed",
            "payload": {
                "turn": {
                    "final_response": "done",
                    "error": None,
                }
            },
        }

    def interrupt(self):
        raise AssertionError("completed fake turn must not be interrupted")


class CompletedThread:
    id = "thread-001"

    def turn(self, prompt, **kwargs):
        return CompletedHandle()


class OfflineSdk:
    def thread_start(self, **kwargs):
        return CompletedThread()

    def close(self):
        return None


def _tree_snapshot(root: Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_fake_specialist_boundary_has_no_external_or_filesystem_side_effects(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sentinel = workspace / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    before = _tree_snapshot(workspace)
    assert CodexSdkAdapter.sdk_available()

    def forbidden(*args, **kwargs):
        raise AssertionError("external authority was invoked")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)

    now = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)
    request = SpecialistInput(
        run_id="run-001",
        task_id="task-001",
        repository_revision="abc123",
        created_at=now,
        role=SpecialistRole.DEVELOPMENT,
        attempt=1,
        instructions="Use the fake boundary.",
        workspace=str(workspace),
        memory_namespace=("profiles", "v20-development", "development-episodes"),
        permissions=PermissionSet(
            sandbox=SandboxMode.WORKSPACE_WRITE,
            read_paths=(str(workspace),),
            write_paths=(str(workspace),),
            allowed_tools=("read", "write", "test"),
        ),
    )
    receipt = CodexSdkAdapter(
        repository_root=workspace,
        approved_models=("approved",),
        sdk_factory=OfflineSdk,
        clock=lambda: now,
    ).execute(request, prompt="No side effects.", model="approved")

    assert receipt.status is ExecutionStatus.COMPLETED
    assert _tree_snapshot(workspace) == before


def test_platform_imports_do_not_load_trading_provider_or_ui_modules(tmp_path):
    probe = """
import importlib.abc
import sys

blocked = tuple(sys.argv[1].split(','))
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == item or fullname.startswith(item + '.') for item in blocked):
            raise RuntimeError('forbidden platform import: ' + fullname)
        return None
sys.meta_path.insert(0, Guard())
import vesper.platform.cli
import vesper.platform.codex
import vesper.platform.contracts
import vesper.platform.evidence
import vesper.platform.memory
import vesper.platform.profiles
"""
    blocked = ",".join(
        (
            "tkinter",
            "vesper.dashboard",
            "vesper.engine",
            "vesper.execution",
            "vesper.data",
            "vesper.secrets",
            "alpaca",
            "yfinance",
        )
    )
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(REPOSITORY_ROOT)
    before = tuple(tmp_path.iterdir())

    result = subprocess.run(
        [sys.executable, "-c", probe, blocked],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert tuple(tmp_path.iterdir()) == before
