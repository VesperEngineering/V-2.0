from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from vesper.platform.persistence import default_platform_paths, open_persistence
from vesper.platform.ops.alerts import AtomicAlertRecordStore, OperationsAlertRecord
from vesper.platform.tui.alert_dismissals import AlertDismissalStore
from vesper.platform.tui.command_contracts import CommandRequest, ReceiptStatus
from vesper.platform.tui.command_policy import (
    CommandContext,
    EvaluatedPrerequisites,
    canonical_request_hash,
)
from vesper.platform.tui.command_registry import CommandRegistry
from vesper.platform.tui.gateway import Gateway
from vesper.platform.tui.projections.platform_runtime import PlatformRuntimeProjection
from vesper.platform.tui.sqlite_ledger import LedgerClosedError, TuiLedger
from vesper.platform.tui.views import CapabilityState, CapabilityView, Freshness


CONTROL_HASH = "7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43"
ALERT_ID = "alert:0123456789abcdef0123456789abcdef"


def _capabilities(gateway: Gateway) -> dict[str, CapabilityState]:
    return {row.capability_id: row.state for row in gateway.snapshot().shell.capabilities}


def _write_resolved_alert(state_root: Path, created_at: datetime) -> None:
    AtomicAlertRecordStore(state_root).write(
        OperationsAlertRecord(
            alert_id=ALERT_ID,
            severity="resolved",
            created_at_utc=created_at,
            resolved_at_utc=created_at + timedelta(seconds=1),
        )
    )


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
        assert capabilities["alert.dismiss"] is CapabilityState.DISABLED
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


def test_existing_platform_schema_enables_only_the_seven_reviewed_handlers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui import cli

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    paths = default_platform_paths()
    with open_persistence(paths):
        pass
    _write_resolved_alert(tmp_path / "tui", datetime.now(timezone.utc))
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
            "alert.dismiss",
            "layout.reset",
            "approval.approve",
            "approval.hold",
            "approval.reject",
            "agent.enqueue",
        }
    finally:
        runtime.close()


def test_startup_recovers_local_commands_without_activating_external_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui import cli

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    state_root = tmp_path / "tui"
    paths = default_platform_paths()
    created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    _write_resolved_alert(state_root, created_at)
    ledger = TuiLedger(state_root / "operations.sqlite3")

    class NoExternalEffects:
        def approve_run(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("startup must not activate external effects")

        reject_run = approve_run
        enqueue = approve_run

        def recover(self, *_args: object, **_kwargs: object) -> str:
            raise AssertionError("runtime-unavailable startup must not recover external effects")

    seed = CommandRegistry(
        ledger,
        NoExternalEffects(),
        alert_store=AlertDismissalStore(ledger, state_root),
        clock=lambda: created_at,
    )

    def request(command_type: str, command_id: str) -> CommandRequest:
        payloads = {
            "alert.dismiss": {
                "alert_id": ALERT_ID,
                "created_at_utc": created_at.isoformat().replace("+00:00", "Z"),
            },
            "layout.reset": {"screen": None},
            "agent.enqueue": {
                "agent_id": "v20-model-researcher",
                "title": "Deferred external work",
                "objective": "Remain pending until runtime truth is available.",
                "priority": 50,
            },
        }
        return CommandRequest.model_validate(
            {
                "command_id": command_id,
                "command_type": command_type,
                "reviewed_control_version": 1,
                "reviewed_control_hash": CONTROL_HASH,
                "reason": "Reviewed external work." if command_type == "agent.enqueue" else None,
                "confirmation": (
                    {"first_confirmed": True} if command_type == "agent.enqueue" else None
                ),
                "payload": payloads[command_type],
            }
        )

    def context(selected: CommandRequest) -> CommandContext:
        return CommandContext(
            operator_id="operator:windows",
            client_id="client:console",
            authenticated=True,
            owns_control_lease=True,
            control_version=1,
            control_hash=CONTROL_HASH,
            capabilities=(
                CapabilityView(
                    capability_id=selected.command_type,
                    state=CapabilityState.ENABLED,
                    reason=None,
                ),
            ),
            prerequisites=EvaluatedPrerequisites(
                request_sha256=canonical_request_hash(selected),
                complete=True,
                checks=(),
            ),
        )

    requests = (
        request("alert.dismiss", "client:startup:alert"),
        request("layout.reset", "client:startup:layout"),
        request("agent.enqueue", "client:startup:external"),
    )
    monkeypatch.setattr(
        seed,
        "_execute_claimed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("simulated crash")),
    )
    for selected in requests:
        with pytest.raises(RuntimeError, match="simulated crash"):
            seed.execute(context(selected), selected)
    seed.close()
    ledger.close()

    gateway = Gateway(tmp_path / "auth")
    runtime = cli._build_projection_runtime(state_root, gateway)
    try:
        assert runtime.platform_runtime_reader.read().freshness is Freshness.UNAVAILABLE
        assert runtime.command_registry is not None
        receipts = {
            selected.command_id: runtime.command_registry._store.get(selected.command_id)
            for selected in requests
        }
        assert receipts["client:startup:alert"].status is ReceiptStatus.COMPLETED
        assert receipts["client:startup:layout"].status is ReceiptStatus.COMPLETED
        assert receipts["client:startup:external"].status is ReceiptStatus.RUNNING
        assert not paths.root.exists()

        with open_persistence(paths):
            pass
        recovered = runtime.recover_commands(datetime.now(timezone.utc))
        assert [receipt.command_id for receipt in recovered] == ["client:startup:external"]
        assert recovered[0].status is ReceiptStatus.COMPLETED
        assert runtime.recover_commands(datetime.now(timezone.utc)) == ()
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
