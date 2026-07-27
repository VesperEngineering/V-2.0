import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _module_names():
    names = []
    for source_root in (ROOT / "vesper", ROOT / "scripts"):
        for path in sorted(source_root.rglob("*.py")):
            relative = path.relative_to(ROOT).with_suffix("")
            parts = list(relative.parts)
            if parts[-1] == "__init__":
                parts.pop()
            names.append(".".join(parts))
    return names


@pytest.mark.parametrize("module_name", _module_names())
def test_project_module_imports_in_isolation(module_name):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import importlib; importlib.import_module({module_name!r})",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
