from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.agent_profiles import (
    AUTONOMOUS_AGENT_ROLES,
    AgentProfileCatalog,
    AgentProfileIntegrityError,
)
from vesper.platform.tui.views import Freshness


ROOT = Path(__file__).parents[4]
NOW = datetime(2026, 8, 3, 22, 30, tzinfo=timezone.utc)
PROTECTED_PARTS = {
    ("vesper", "data", "massive"),
    ("vesper", "data", "model_research"),
}


def _lower_parts(path: Path) -> tuple[str, ...]:
    return tuple(part.casefold() for part in path.absolute().parts)


def _contains_parts(parts: tuple[str, ...], target: tuple[str, ...]) -> bool:
    return any(parts[index : index + len(target)] == target for index in range(len(parts)))


def _copy_native_profiles(repository_root: Path) -> Path:
    target = repository_root / "profiles" / "native"
    shutil.copytree(ROOT / "profiles" / "native", target)
    return target


@pytest.fixture(autouse=True)
def forbid_protected_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    original_open = Path.open

    def guarded_open(path: Path, *args: object, **kwargs: object):
        parts = _lower_parts(path)
        if any(_contains_parts(parts, target) for target in PROTECTED_PARTS):
            raise AssertionError(f"protected path read attempted: {path}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)


def test_native_projection_reads_only_five_configured_qwen_profiles() -> None:
    from vesper.platform.tui.projections.native_platform import NativePlatformProjection

    projection = NativePlatformProjection(ROOT, clock=lambda: NOW)

    sample = projection.read()

    assert sample.freshness is Freshness.FRESH
    assert sample.observed_at_utc == NOW
    assert sample.source == "native agent profile catalog"
    assert sample.error is None
    assert sample.value is not None
    assert tuple(fact.agent_id for fact in sample.value.configured_roster) == tuple(
        role.value for role in AUTONOMOUS_AGENT_ROLES
    )
    assert {fact.model for fact in sample.value.configured_roster} == {"qwen:64k"}
    assert sample.value.active_work is None
    assert sample.value.active_work_error == (
        "No bounded read-only active-work source is configured."
    )


def test_native_projection_keeps_untyped_portfolio_and_orders_unavailable() -> None:
    from vesper.platform.tui.projections.native_platform import NativePlatformProjection

    projection = NativePlatformProjection(ROOT, clock=lambda: NOW)

    portfolio = projection.portfolio_port.read()
    orders = projection.order_port.read()

    assert portfolio.freshness is Freshness.UNAVAILABLE
    assert portfolio.value is None
    assert portfolio.error == "No typed reconciled portfolio source is configured."
    assert orders.freshness is Freshness.UNAVAILABLE
    assert orders.value is None
    assert orders.error == "No controller-owned typed order source is configured."


def test_native_projection_fails_closed_when_profile_catalog_is_invalid(tmp_path: Path) -> None:
    from vesper.platform.tui.projections.native_platform import NativePlatformProjection

    sample = NativePlatformProjection(tmp_path, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.observed_at_utc is None
    assert sample.error == "Configured native profile root is unavailable or unsafe."


def test_native_projection_fails_closed_when_clock_raises() -> None:
    from vesper.platform.tui.projections.native_platform import NativePlatformProjection

    def failed_clock() -> datetime:
        raise OSError("clock unavailable")

    sample = NativePlatformProjection(ROOT, clock=failed_clock).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.observed_at_utc is None
    assert sample.error == "Native projection clock did not return UTC."


@pytest.mark.parametrize(
    "bad_time",
    (datetime(2026, 8, 3, 22, 30), object()),
)
def test_native_projection_fails_closed_when_clock_is_not_utc(bad_time: object) -> None:
    from vesper.platform.tui.projections.native_platform import NativePlatformProjection

    sample = NativePlatformProjection(ROOT, clock=lambda: bad_time).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.observed_at_utc is None
    assert sample.error == "Native projection clock did not return UTC."


def test_native_projection_rejects_protected_root_before_metadata_or_content_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui.projections.native_platform import NativePlatformProjection

    protected_root = tmp_path / "vesper" / "data" / "massive"
    original_lstat = Path.lstat
    original_resolve = Path.resolve
    original_stat = Path.stat

    def reject_protected(operation, path: Path, *args: object, **kwargs: object):
        if any(_contains_parts(_lower_parts(path), target) for target in PROTECTED_PARTS):
            raise AssertionError(f"protected {operation} attempted: {path}")

    def guarded_lstat(path: Path, *args: object, **kwargs: object):
        reject_protected("lstat", path, *args, **kwargs)
        return original_lstat(path, *args, **kwargs)

    def guarded_resolve(path: Path, *args: object, **kwargs: object):
        reject_protected("resolve", path, *args, **kwargs)
        return original_resolve(path, *args, **kwargs)

    def guarded_stat(path: Path, *args: object, **kwargs: object):
        reject_protected("stat", path, *args, **kwargs)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", guarded_lstat)
    monkeypatch.setattr(Path, "resolve", guarded_resolve)
    monkeypatch.setattr(Path, "stat", guarded_stat)

    sample = NativePlatformProjection(protected_root, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Configured native profile root is unavailable or unsafe."


def test_native_projection_rejects_symlink_repository_root(tmp_path: Path) -> None:
    from vesper.platform.tui.projections.native_platform import NativePlatformProjection

    real_repository = tmp_path / "real-repository"
    _copy_native_profiles(real_repository)
    linked_repository = tmp_path / "linked-repository"
    try:
        linked_repository.symlink_to(real_repository, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable for this Windows account")

    sample = NativePlatformProjection(linked_repository, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Configured native profile root is unavailable or unsafe."


def test_native_projection_rejects_reparse_profile_root_before_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui.projections import native_platform

    source_repository = tmp_path / "source-repository"
    source_profiles = _copy_native_profiles(source_repository)
    configured_repository = tmp_path / "configured-repository"
    (configured_repository / "profiles").mkdir(parents=True)
    linked_profiles = configured_repository / "profiles" / "native"
    try:
        linked_profiles.symlink_to(source_profiles, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable for this Windows account")
    monkeypatch.setattr(
        native_platform,
        "_MODULE_REPOSITORY_ROOT",
        configured_repository,
    )

    sample = native_platform.NativePlatformProjection(
        configured_repository,
        clock=lambda: NOW,
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Configured native profile root is unavailable or unsafe."


def test_bounded_catalog_rejects_oversized_profile_content(tmp_path: Path) -> None:
    profile_root = _copy_native_profiles(tmp_path)
    role = AUTONOMOUS_AGENT_ROLES[0]
    (profile_root / role.value / "SOUL.md").write_bytes(b"x" * 1_025)

    with pytest.raises(AgentProfileIntegrityError, match="size limit"):
        AgentProfileCatalog(profile_root).load_bounded(
            role,
            max_profile_bytes=4_096,
            max_soul_bytes=1_024,
            max_yaml_depth=32,
            max_yaml_events=2_048,
            max_yaml_aliases=0,
        )


def test_bounded_catalog_rejects_hardlinked_profile_file(tmp_path: Path) -> None:
    profile_root = _copy_native_profiles(tmp_path)
    role = AUTONOMOUS_AGENT_ROLES[0]
    profile_path = profile_root / role.value / "profile.yaml"
    source = tmp_path / "profile-source.yaml"
    source.write_bytes(profile_path.read_bytes())
    profile_path.unlink()
    try:
        os.link(source, profile_path)
    except OSError:
        pytest.skip("hard links are unavailable for this Windows account")

    with pytest.raises(AgentProfileIntegrityError, match="multiple hard links"):
        AgentProfileCatalog(profile_root).load_bounded(
            role,
            max_profile_bytes=4_096,
            max_soul_bytes=1_024,
            max_yaml_depth=32,
            max_yaml_events=2_048,
            max_yaml_aliases=0,
        )


@pytest.mark.parametrize(
    ("profile_text", "reason"),
    (
        ("root: &root [1]\ncopy: *root\n", "alias limit"),
        ("root: " + "[" * 40 + "0" + "]" * 40 + "\n", "depth limit"),
        ("\n".join(f"key{index}: 1" for index in range(40)), "event limit"),
    ),
)
def test_bounded_catalog_rejects_yaml_alias_or_depth_before_loading(
    tmp_path: Path,
    profile_text: str,
    reason: str,
) -> None:
    profile_root = _copy_native_profiles(tmp_path)
    role = AUTONOMOUS_AGENT_ROLES[0]
    (profile_root / role.value / "profile.yaml").write_text(
        profile_text,
        encoding="utf-8",
    )

    with pytest.raises(AgentProfileIntegrityError, match=reason):
        AgentProfileCatalog(profile_root).load_bounded(
            role,
            max_profile_bytes=4_096,
            max_soul_bytes=1_024,
            max_yaml_depth=16,
            max_yaml_events=32,
            max_yaml_aliases=0,
        )


def test_native_projection_never_reaches_runtime_or_trading_constructors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper import engine as trading_engine
    from vesper import state
    from vesper.execution import broker
    from vesper.platform import service, workflow
    from vesper.platform.tui.projections.native_platform import NativePlatformProjection
    from vesper.scheduler import engine as scheduler_engine

    calls: list[str] = []

    def forbidden(name: str):
        def fail(*_args: object, **_kwargs: object) -> None:
            calls.append(name)
            raise AssertionError(f"forbidden constructor reached: {name}")

        return fail

    monkeypatch.setattr(service.LocalPlatformService, "__init__", forbidden("service"))
    monkeypatch.setattr(workflow.WorkflowController, "__init__", forbidden("controller"))
    monkeypatch.setattr(state.StateManager, "__init__", forbidden("state-manager"))
    monkeypatch.setattr(trading_engine.TradingEngine, "__init__", forbidden("trading"))
    monkeypatch.setattr(scheduler_engine.MarketScheduler, "__init__", forbidden("scheduler"))
    monkeypatch.setattr(broker, "create_broker", forbidden("broker"))

    sample = NativePlatformProjection(ROOT, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.FRESH
    assert calls == []
