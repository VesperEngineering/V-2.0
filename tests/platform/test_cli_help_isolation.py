from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_IMPORTS = (
    "tkinter",
    "vesper.dashboard",
    "vesper.engine",
    "vesper.execution",
    "vesper.secrets",
    "vesper.data",
    "alpaca",
    "yfinance",
    "openai_codex",
    "langgraph",
)


@pytest.mark.parametrize("arguments", (["--help"], ["status", "--help"]))
def test_cli_help_is_side_effect_free_in_fresh_process(tmp_path, arguments):
    probe = """
import importlib.abc
import runpy
import sys

forbidden = tuple(sys.argv[1].split(','))
target_args = sys.argv[2:]

class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == item or fullname.startswith(item + '.') for item in forbidden):
            raise RuntimeError('forbidden help import: ' + fullname)
        return None

sys.meta_path.insert(0, Guard())
sys.argv = ['vesper-agent', *target_args]
runpy.run_module('vesper.platform.cli', run_name='__main__')
"""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(REPOSITORY_ROOT)
    before = tuple(tmp_path.iterdir())

    result = subprocess.run(
        [sys.executable, "-c", probe, ",".join(FORBIDDEN_IMPORTS), *arguments],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Usage:" in result.stdout
    assert tuple(tmp_path.iterdir()) == before
