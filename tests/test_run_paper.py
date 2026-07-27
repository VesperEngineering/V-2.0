import importlib.util
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_paper.py"


def _load_run_paper():
    spec = importlib.util.spec_from_file_location("run_paper_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_paper_help_is_side_effect_free(tmp_path):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-X", "importtime", str(SCRIPT), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert "paper" in result.stdout.lower()
    assert list(tmp_path.iterdir()) == []
    for module_name in (
        "tkinter",
        "vesper.dashboard.app",
        "vesper.engine",
        "vesper.secrets",
        "alpaca",
        "yfinance",
    ):
        assert f"| {module_name}" not in result.stderr


def test_run_session_starts_engine_and_closes_cleanly():
    run_paper = _load_run_paper()
    events = []

    class Engine:
        def start(self):
            events.append("engine.start")

        def stop(self):
            events.append("engine.stop")

    class Dashboard:
        def close(self):
            events.append("dashboard.close")

    class Root:
        def protocol(self, name, callback):
            events.append(f"root.protocol:{name}")
            self.close_callback = callback

        def mainloop(self):
            events.append("root.mainloop")
            self.close_callback()

    run_paper.run_session(Engine(), Root(), Dashboard())

    assert events == [
        "root.protocol:WM_DELETE_WINDOW",
        "engine.start",
        "root.mainloop",
        "engine.stop",
        "dashboard.close",
    ]
