import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True,
        text=True,
        capture_output=True,
    )


def test_repository_baseline_tracks_required_review_surface() -> None:
    head = git("rev-parse", "--verify", "HEAD").stdout.strip()
    assert re.fullmatch(r"[0-9a-f]{40}", head)
    assert head != "0" * 40

    git(
        "ls-files",
        "--error-unmatch",
        "AGENTS.md",
        "README.md",
        "config/settings.yaml",
        "vesper/engine.py",
        "scripts/run_backtest.py",
        "tests/test_risk.py",
        "models/xgb_ranker.json",
        "reports/repository_baseline_vs_003.md",
    )


def test_repository_baseline_ignores_local_and_protected_paths() -> None:
    for path in (
        ".env",
        ".venv/pyvenv.cfg",
        ".fusion/project.json",
        ".codegraph/codegraph.db",
        ".tmp/example",
        "tmp/example",
        ".state/example",
        "target/example",
        "node_modules/example",
        ".pytest_tmp/example",
        ".worktrees/example",
        "vesper/data/massive/example",
        "vesper/data/model_research/example",
    ):
        subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-q", path],
            check=True,
            text=True,
            capture_output=True,
        )


def test_native_runtime_has_no_retired_hermes_dependency() -> None:
    hits = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "vesper").rglob("*.py")
        if "hermes" in path.read_text(encoding="utf-8").lower()
    ]

    assert hits == []
