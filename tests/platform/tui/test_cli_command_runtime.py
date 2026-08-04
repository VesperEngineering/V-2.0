from __future__ import annotations

from pathlib import Path

import pytest

from vesper.platform.persistence import default_platform_paths, open_persistence
from vesper.platform.tui.command_registry import CommandRegistry
from vesper.platform.tui.gateway import Gateway
from vesper.platform.tui.projections.platform_runtime import PlatformRuntimeProjection
from vesper.platform.tui.sqlite_ledger import LedgerClosedError
from vesper.platform.tui.views import CapabilityState


def _capabilities(gateway: Gateway) -> dict[str, CapabilityState]:
    return {
        row.capability_id: row.state for row in gateway.snapshot().shell.capabilities
    }


def test_startup_shares_query_only_runtime_reader_and_leaves_absent_state_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui import cli

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    paths = default_platform_paths()
    gateway = Gateway(tmp_path / "auth")

    runtime = cli._build_projection_runtime(tmp_path / "tui", gateway)
    registry = runtime.command_registry
    try:
        assert isinstance(runtime.loop._sources["platform.runtime"], PlatformRuntimeProjection)
        assert runtime.loop._sources["platform.runtime"] is runtime.platform_runtime_reader
        assert isinstance(registry, CommandRegistry)
        assert not paths.root.exists()
        capabilities = _capabilities(gateway)
        assert capabilities["note.add"] is CapabilityState.ENABLED
        assert capabilities["approval.approve"] is CapabilityState.DISABLED
        assert capabilities["approval.hold"] is CapabilityState.DISABLED
        assert capabilities["approval.reject"] is CapabilityState.DISABLED
        assert capabilities["agent.enqueue"] is CapabilityState.DISABLED
    finally:
        runtime.close()

    assert not paths.root.exists()
    assert registry is not None
    with pytest.raises(LedgerClosedError):
        _ = registry.specs


def test_existing_platform_schema_enables_only_the_five_reviewed_handlers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui import cli

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    paths = default_platform_paths()
    with open_persistence(paths):
        pass
    gateway = Gateway(tmp_path / "auth")

    runtime = cli._build_projection_runtime(tmp_path / "tui", gateway)
    try:
        capabilities = _capabilities(gateway)
        assert {
            capability_id
            for capability_id, state in capabilities.items()
            if state is CapabilityState.ENABLED
        } == {
            "note.add",
            "approval.approve",
            "approval.hold",
            "approval.reject",
            "agent.enqueue",
        }
    finally:
        runtime.close()


def test_corrupt_command_ledger_keeps_observability_but_attaches_no_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui import cli

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    state_root = tmp_path / "tui"
    state_root.mkdir(parents=True)
    (state_root / "operations.sqlite3").write_bytes(b"not sqlite")
    gateway = Gateway(tmp_path / "auth")

    runtime = cli._build_projection_runtime(state_root, gateway)
    try:
        assert runtime.command_registry is None
        assert isinstance(runtime.loop._sources["platform.runtime"], PlatformRuntimeProjection)
        assert all(
            state is not CapabilityState.ENABLED
            for capability_id, state in _capabilities(gateway).items()
            if capability_id != "snapshot.read"
        )
    finally:
        runtime.close()
