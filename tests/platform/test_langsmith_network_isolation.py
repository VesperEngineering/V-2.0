from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_full_local_graph_path_attempts_no_langsmith_network_activity(tmp_path):
    allowed_names = (
        "SYSTEMROOT",
        "WINDIR",
        "PATH",
        "PATHEXT",
        "COMSPEC",
        "TEMP",
        "TMP",
        "LOCALAPPDATA",
    )
    env = {name: os.environ[name] for name in allowed_names if name in os.environ}
    env.update(
        {
            "PYTHONPATH": str(REPOSITORY_ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_TRACING_V2": "true",
            "LANGCHAIN_TRACING_V2": "true",
            "LANGGRAPH_CLI_NO_ANALYTICS": "0",
        }
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.platform.offline_graph_probe",
            str(tmp_path),
        ],
        cwd=REPOSITORY_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "offline-langsmith-network-proof: ok"
