from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[3]
SCRIPTS = (
    ROOT / "scripts" / "build-tui.ps1",
    ROOT / "scripts" / "install-tui-shortcut.ps1",
    ROOT / "scripts" / "verify-tui.ps1",
)


@pytest.mark.parametrize("script", SCRIPTS)
def test_tui_script_parses_without_running(script: Path) -> None:
    pwsh = shutil.which("pwsh")
    assert pwsh is not None
    assert script.is_file()
    command = (
        "$errors=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{script}',"
        "[ref]$null,[ref]$errors)>$null;"
        "if($errors.Count){$errors|ConvertTo-Json -Compress;exit 1}"
    )

    result = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_build_script_is_locked_isolated_and_packages_only_public_files() -> None:
    text = SCRIPTS[0].read_text(encoding="utf-8")

    assert "uv run --locked python -m pytest" in text
    assert "cargo build" in text and "--release" in text and "--locked" in text
    assert "CARGO_TARGET_DIR" in text and "C:\\tmp" in text
    assert "dist\\tui" in text
    assert "vesper-ratatui-console.exe" in text
    assert "README.md" in text
    assert "Get-FileHash" in text and "SHA256" in text
    assert "$allowedPackageNames" in text
    assert "Copy-Item -Recurse" not in text


def test_build_rejects_any_preexisting_unapproved_package_entry() -> None:
    text = SCRIPTS[0].read_text(encoding="utf-8")

    assert "$allowedPackageNames" in text
    assert "Unapproved package entry" in text
    assert "Get-ChildItem -LiteralPath $output -Force" in text


def test_verify_script_uses_exact_locked_python_temp_contract_and_receipts() -> None:
    text = SCRIPTS[2].read_text(encoding="utf-8")

    assert "$env:TEMP='C:\\tmp\\v20-tui-operations-temp'" in text
    assert "$env:TMP='C:\\tmp\\v20-tui-operations-temp'" in text
    assert "uv run --locked python -m pytest" in text
    assert "--basetemp C:\\tmp\\v20-tui-operations-pytest" in text
    assert "cache_dir=C:\\tmp\\v20-tui-operations-cache" in text
    assert "cargo fmt" in text
    assert "cargo clippy" in text and "-D warnings" in text
    assert "cargo test" in text and "--locked" in text
    assert "exit_code" in text and "duration_ms" in text and "command" in text
    assert "ConvertTo-Json" in text


def test_shortcut_install_is_explicit_current_user_only_and_sets_app_id() -> None:
    text = SCRIPTS[1].read_text(encoding="utf-8")
    lowered = text.lower()

    assert "ConfirmInstall" in text
    assert "Start Menu\\Programs" in text
    assert "Vesper.V20.TUI" in text
    assert "SHGetPropertyStoreFromParsingName" in text
    assert "SetAppUserModelId" in text
    assert "vesper-ratatui-console.exe" in text
    assert "all users" not in lowered
    assert "programdata" not in lowered
    assert "runas" not in lowered
    assert "administrator" not in lowered


def test_build_receipt_contract_is_json_serializable() -> None:
    example = {
        "executable": "dist/tui/vesper-ratatui-console.exe",
        "sha256": "a" * 64,
        "tools": {"cargo": "cargo 1", "uv": "uv 1"},
    }

    assert json.loads(json.dumps(example))["sha256"] == "a" * 64
