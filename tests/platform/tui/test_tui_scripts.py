from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[3]
SCRIPTS = (
    ROOT / "scripts" / "build-tui.ps1",
    ROOT / "scripts" / "install-tui-shortcut.ps1",
    ROOT / "scripts" / "verify-tui.ps1",
)


def _create_junction(pwsh: str, link: Path, target: Path) -> None:
    environment = os.environ.copy()
    environment["V20_TEST_JUNCTION"] = str(link)
    environment["V20_TEST_JUNCTION_TARGET"] = str(target)
    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "New-Item -ItemType Junction -Path $env:V20_TEST_JUNCTION "
                "-Target $env:V20_TEST_JUNCTION_TARGET | Out-Null"
            ),
        ],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert link.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT


def _success_command_stubs(root: Path) -> Path:
    stubs = root / "command-stubs"
    stubs.mkdir(parents=True)
    for name in ("uv.cmd", "cargo.cmd"):
        (stubs / name).write_text("@echo off\r\nexit /b 0\r\n", encoding="ascii")
    return stubs


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
    assert "CARGO_TARGET_DIR" in text and "WorkRoot" in text
    assert "$scratchLocalAppData = Join-Path $work 'local-app-data'" in text
    assert "$env:LOCALAPPDATA = $scratchLocalAppData" in text
    assert "Assert-ScratchPath" in text
    assert "SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')" in text
    assert "GetTempPath" in text
    assert "scratch files must stay outside the repository" in text
    assert "must be exactly dist\\tui" in text
    assert "dedicated scratch directory" in text
    assert "ReparsePoint" in text
    assert "Assert-PackagePath -Path $output -RepositoryRoot $repoRoot" in text
    assert "TUI package path cannot contain a reparse point" in text
    assert "dist\\tui" in text
    assert "vesper-ratatui-console.exe" in text
    assert "README.md" in text
    assert "Get-FileHash" in text and "SHA256" in text
    assert "$allowedPackageNames" in text
    assert "Copy-Item -Recurse" not in text
    assert "$packageStage" in text
    assert "$installStage" in text
    assert "$backup" in text
    assert "Move-Item -LiteralPath $installStage -Destination $output" in text
    assert "Remove-Item -LiteralPath $backup -Recurse" not in text
    assert "Unapproved package backup entry" in text
    assert text.index("Invoke-Checked -Label 'Rust tests'") < text.index("$packageStage")


def test_build_rejects_any_preexisting_unapproved_package_entry() -> None:
    text = SCRIPTS[0].read_text(encoding="utf-8")

    assert "$allowedPackageNames" in text
    assert "Unapproved package entry" in text
    assert "Get-ChildItem -LiteralPath $output -Force" in text


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_build_rejects_a_reparse_package_parent_before_running_tools(tmp_path: Path) -> None:
    pwsh = shutil.which("pwsh")
    assert pwsh is not None
    fake_repo = tmp_path / "fake-repo"
    scripts = fake_repo / "scripts"
    scripts.mkdir(parents=True)
    copied_script = scripts / "build-tui.ps1"
    shutil.copy2(SCRIPTS[0], copied_script)
    external_dist = tmp_path / "external-dist"
    external_dist.mkdir()
    junction = fake_repo / "dist"
    _create_junction(pwsh, junction, external_dist)
    try:
        result = subprocess.run(
            [
                pwsh,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                copied_script,
                "-WorkRoot",
                tmp_path / "work",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "package path cannot contain a reparse point" in (result.stdout + result.stderr)
        assert list(external_dist.iterdir()) == []
    finally:
        junction.rmdir()


def test_verify_script_uses_configurable_isolated_temp_contract_and_receipts() -> None:
    text = SCRIPTS[2].read_text(encoding="utf-8")

    assert "WorkRoot" in text and "GetTempPath" in text
    assert "dedicated scratch directory" in text
    assert "ReparsePoint" in text
    assert "$scratchTemp = Join-Path $work 'temp'" in text
    assert "$env:TEMP = $scratchTemp" in text
    assert "$env:TMP = $scratchTemp" in text
    assert "$scratchLocalAppData = Join-Path $work 'local-app-data'" in text
    assert "$env:LOCALAPPDATA = $scratchLocalAppData" in text
    assert "Assert-ScratchPath" in text
    assert "SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')" in text
    assert "uv run --locked python -m pytest" in text
    assert "--basetemp $pytestTemp" in text
    assert '"cache_dir=$pytestCache"' in text
    assert "cargo fmt" in text
    assert "cargo clippy" in text and "-D warnings" in text
    assert "cargo test" in text and "--locked" in text
    assert text.count("cargo clippy --manifest-path") == 2
    assert text.count("cargo test --manifest-path") == 2
    assert "catch {" in text
    assert "exit_code" in text and "duration_ms" in text and "command" in text
    assert "ConvertTo-Json" in text


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_verify_rejects_a_reparse_receipt_parent_before_running_tools(tmp_path: Path) -> None:
    pwsh = shutil.which("pwsh")
    assert pwsh is not None
    fake_repo = tmp_path / "fake-repo"
    scripts = fake_repo / "scripts"
    results_parent = fake_repo / "TUI testing"
    scripts.mkdir(parents=True)
    results_parent.mkdir()
    copied_script = scripts / "verify-tui.ps1"
    shutil.copy2(SCRIPTS[2], copied_script)
    external_results = tmp_path / "external-results"
    external_results.mkdir()
    junction = results_parent / "results"
    _create_junction(pwsh, junction, external_results)
    try:
        result = subprocess.run(
            [
                pwsh,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                copied_script,
                "-WorkRoot",
                tmp_path / "work",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "receipt path cannot contain a reparse point" in (result.stdout + result.stderr)
        assert list(external_results.iterdir()) == []
    finally:
        junction.rmdir()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
@pytest.mark.parametrize("script_index", (0, 2))
def test_build_and_verify_reject_reparse_scratch_child(
    tmp_path: Path,
    script_index: int,
) -> None:
    pwsh = shutil.which("pwsh")
    assert pwsh is not None
    fake_repo = tmp_path / f"fake-repo-{script_index}"
    scripts = fake_repo / "scripts"
    scripts.mkdir(parents=True)
    if script_index == 2:
        (fake_repo / "TUI testing").mkdir()
    copied_script = scripts / SCRIPTS[script_index].name
    shutil.copy2(SCRIPTS[script_index], copied_script)
    work = tmp_path / f"work-{script_index}"
    work.mkdir()
    external = tmp_path / f"external-{script_index}"
    external.mkdir()
    junction = work / "local-app-data"
    _create_junction(pwsh, junction, external)
    stubs = _success_command_stubs(tmp_path / f"stubs-{script_index}")
    environment = os.environ.copy()
    environment["PATH"] = f"{stubs}{os.pathsep}{environment['PATH']}"
    try:
        result = subprocess.run(
            [
                pwsh,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                copied_script,
                "-WorkRoot",
                work,
            ],
            check=False,
            capture_output=True,
            env=environment,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "scratch path cannot contain a reparse point" in (result.stdout + result.stderr)
        assert list(external.iterdir()) == []
    finally:
        junction.rmdir()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell environment behavior")
@pytest.mark.parametrize("script_index", (0, 2))
def test_build_and_verify_restore_caller_environment(
    tmp_path: Path,
    script_index: int,
) -> None:
    pwsh = shutil.which("pwsh")
    assert pwsh is not None
    fake_repo = tmp_path / f"restore-repo-{script_index}"
    scripts = fake_repo / "scripts"
    scripts.mkdir(parents=True)
    if script_index == 2:
        (fake_repo / "TUI testing").mkdir()
    copied_script = scripts / SCRIPTS[script_index].name
    shutil.copy2(SCRIPTS[script_index], copied_script)
    stubs = _success_command_stubs(tmp_path / f"restore-stubs-{script_index}")
    sentinels = {
        name: str(tmp_path / f"sentinel-{script_index}-{name.lower()}")
        for name in (
            "TEMP",
            "TMP",
            "UV_CACHE_DIR",
            "CARGO_TARGET_DIR",
            "LOCALAPPDATA",
        )
    }
    for path in sentinels.values():
        Path(path).mkdir()
    environment = os.environ.copy()
    environment.update(sentinels)
    environment["PATH"] = f"{stubs}{os.pathsep}{environment['PATH']}"
    environment["V20_TEST_SCRIPT"] = str(copied_script)
    environment["V20_TEST_WORK"] = str(tmp_path / f"restore-work-{script_index}")
    command = (
        "try { & $env:V20_TEST_SCRIPT -WorkRoot $env:V20_TEST_WORK } catch {}\n"
        "[ordered]@{TEMP=$env:TEMP;TMP=$env:TMP;UV_CACHE_DIR=$env:UV_CACHE_DIR;"
        "CARGO_TARGET_DIR=$env:CARGO_TARGET_DIR;LOCALAPPDATA=$env:LOCALAPPDATA} "
        "| ConvertTo-Json -Compress"
    )

    result = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-Command", command],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == sentinels


def test_shortcut_install_is_explicit_current_user_only_and_sets_app_id() -> None:
    text = SCRIPTS[1].read_text(encoding="utf-8")
    lowered = text.lower()

    assert "ConfirmInstall" in text
    assert "Start Menu\\Programs" in text
    assert "Vesper.V20.TUI" in text
    assert "SHGetPropertyStoreFromParsingName" in text
    assert "SetAppUserModelId" in text
    assert "vesper-ratatui-console.exe" in text
    assert "Shortcut target must be the packaged dist\\tui executable" in text
    assert "Shortcut target cannot contain a reparse point" in text
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
