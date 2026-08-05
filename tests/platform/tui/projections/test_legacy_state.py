from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from vesper.platform.tui.views import Freshness


NOW = datetime(2026, 8, 3, 22, 30, tzinfo=timezone.utc)
PROTECTED_PARTS = {
    ("vesper", "data", "massive"),
    ("vesper", "data", "model_research"),
}


def _lower_parts(path: Path) -> tuple[str, ...]:
    return tuple(part.casefold() for part in path.absolute().parts)


def _contains_parts(parts: tuple[str, ...], target: tuple[str, ...]) -> bool:
    return any(parts[index : index + len(target)] == target for index in range(len(parts)))


@pytest.fixture(autouse=True)
def forbid_protected_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    original_open = Path.open

    def guarded_open(path: Path, *args: object, **kwargs: object):
        mode = str(args[0]) if args else str(kwargs.get("mode", "r"))
        parts = _lower_parts(path)
        if "r" in mode and any(
            _contains_parts(parts, target) for target in PROTECTED_PARTS
        ):
            raise AssertionError(f"protected path read attempted: {path}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)


def _payload(timestamp: str | None = None) -> dict[str, object]:
    return {
        "ts": timestamp or NOW.isoformat(),
        "session_date": "2026-08-03",
        "daily_pnl": "-12.50",
        "starting_equity": 100_000,
        "peak_equity": "101000.25",
        "breaker_tripped": False,
        "positions": {
            "NVDA": {"qty": "2.500", "entry": "100.00", "price": 110.25},
        },
    }


def _write_state(root: Path, payload: dict[str, object], name: str = "state.json") -> Path:
    path = root / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_legacy_state_returns_only_unreconciled_risk_facts(tmp_path: Path) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    _write_state(tmp_path, _payload())
    projection = LegacyStateProjection(tmp_path, Path("state.json"), clock=lambda: NOW)

    sample = projection.read()

    assert sample.freshness is Freshness.FRESH
    assert sample.observed_at_utc == NOW
    assert sample.source == "legacy saved engine state"
    assert sample.error is None
    assert sample.value is not None
    assert sample.value.broker_reconciled is False
    assert sample.value.session_date.isoformat() == "2026-08-03"
    assert sample.value.daily_pnl == -12.5
    assert sample.value.starting_equity == 100_000
    assert sample.value.peak_equity == 101_000.25
    assert sample.value.breaker_tripped is False
    assert sample.value.positions[0].symbol == "NVDA"
    assert sample.value.positions[0].quantity == "2.5"
    assert sample.value.positions[0].entry_price == "100"
    assert sample.value.positions[0].current_price == "110.25"
    assert not hasattr(sample.value.positions[0], "asset_type")
    assert not hasattr(sample.value.positions[0], "current_weight")
    assert not hasattr(sample.value.positions[0], "reconciliation")


def test_legacy_state_marks_retained_facts_stale_by_age(tmp_path: Path) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    old = NOW - timedelta(minutes=10)
    _write_state(tmp_path, _payload(old.isoformat()))
    projection = LegacyStateProjection(
        tmp_path,
        Path("state.json"),
        clock=lambda: NOW,
        stale_after=timedelta(minutes=5),
    )

    sample = projection.read()

    assert sample.freshness is Freshness.STALE
    assert sample.value is not None
    assert sample.observed_at_utc == old
    assert sample.error == "Legacy saved engine state is older than 300 seconds."


@pytest.mark.parametrize("bad_now", [datetime(2026, 8, 3, 22, 30), object()])
def test_legacy_state_fails_closed_when_clock_is_not_utc(
    tmp_path: Path,
    bad_now: object,
) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    _write_state(tmp_path, _payload())

    sample = LegacyStateProjection(
        tmp_path,
        Path("state.json"),
        clock=lambda: bad_now,
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.observed_at_utc is None
    assert sample.error == "Legacy projection clock did not return UTC."


def test_legacy_state_fails_closed_when_clock_raises(tmp_path: Path) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    _write_state(tmp_path, _payload())

    def failed_clock() -> datetime:
        raise OSError("clock unavailable")

    sample = LegacyStateProjection(
        tmp_path,
        Path("state.json"),
        clock=failed_clock,
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.error == "Legacy projection clock did not return UTC."


def test_legacy_state_rejects_decimal_before_large_fixed_point_expansion(
    tmp_path: Path,
) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    payload = _payload()
    payload["positions"]["NVDA"]["qty"] = "1e+999999999"
    _write_state(tmp_path, payload)

    sample = LegacyStateProjection(tmp_path, Path("state.json"), clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.error == "Legacy saved engine state schema is invalid."


@pytest.mark.parametrize("field", ["max_bytes", "max_positions"])
def test_legacy_state_rejects_non_integer_bounds(tmp_path: Path, field: str) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    with pytest.raises(ValueError, match="positive integer"):
        LegacyStateProjection(
            tmp_path,
            Path("state.json"),
            **{field: 1.5},
        )


def test_legacy_state_keeps_portfolio_and_orders_explicitly_unavailable(
    tmp_path: Path,
) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    projection = LegacyStateProjection(tmp_path, Path("state.json"), clock=lambda: NOW)

    assert projection.portfolio_port.read().error == (
        "Legacy saved state cannot prove asset type, cash, weights, rank, or reconciliation."
    )
    assert projection.order_port.read().error == (
        "Legacy saved state contains no typed order history."
    )


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("{not-json", "Legacy saved engine state is not valid strict JSON."),
        (
            '{"ts":"2026-08-03T22:30:00+00:00","ts":"2026-08-03T22:30:00+00:00"}',
            "Legacy saved engine state is not valid strict JSON.",
        ),
        (
            json.dumps({**_payload(), "unexpected": True}),
            "Legacy saved engine state schema is invalid.",
        ),
    ],
)
def test_legacy_state_rejects_bad_json_and_schema(
    tmp_path: Path,
    raw: str,
    reason: str,
) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    (tmp_path / "state.json").write_text(raw, encoding="utf-8")

    sample = LegacyStateProjection(tmp_path, Path("state.json"), clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.error == reason


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda payload: payload.update(
                {"ts": (NOW + timedelta(seconds=1)).isoformat()}
            ),
            "Legacy saved engine state timestamp is in the future.",
        ),
        (
            lambda payload: payload.update({"ts": "2026-08-03T23:30:00+01:00"}),
            "Legacy saved engine state timestamp must be UTC.",
        ),
        (
            lambda payload: payload["positions"]["NVDA"].update({"qty": "-1"}),
            "Legacy saved engine state schema is invalid.",
        ),
        (
            lambda payload: payload.update(
                {"positions": {"../NVDA": {"qty": 1, "entry": 1, "price": 1}}}
            ),
            "Legacy saved engine state schema is invalid.",
        ),
    ],
)
def test_legacy_state_rejects_future_non_utc_and_invalid_positions(
    tmp_path: Path,
    mutate,
    reason: str,
) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    payload = _payload()
    mutate(payload)
    _write_state(tmp_path, payload)

    sample = LegacyStateProjection(tmp_path, Path("state.json"), clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == reason


def test_legacy_state_rejects_outside_and_protected_paths_before_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    outside = tmp_path.parent / "outside-state.json"
    outside.write_text(json.dumps(_payload()), encoding="utf-8")
    original_open = Path.open
    original_lstat = Path.lstat
    original_resolve = Path.resolve
    original_stat = Path.stat
    opened: list[Path] = []

    def record_open(path: Path, *args: object, **kwargs: object):
        if path == outside:
            opened.append(path)
        return original_open(path, *args, **kwargs)

    def reject_protected_lstat(path: Path, *args: object, **kwargs: object):
        if any(_contains_parts(_lower_parts(path), target) for target in PROTECTED_PARTS):
            raise AssertionError(f"protected lstat attempted: {path}")
        return original_lstat(path, *args, **kwargs)

    def reject_protected_resolve(path: Path, *args: object, **kwargs: object):
        if any(_contains_parts(_lower_parts(path), target) for target in PROTECTED_PARTS):
            raise AssertionError(f"protected resolve attempted: {path}")
        return original_resolve(path, *args, **kwargs)

    def reject_protected_stat(path: Path, *args: object, **kwargs: object):
        if any(_contains_parts(_lower_parts(path), target) for target in PROTECTED_PARTS):
            raise AssertionError(f"protected stat attempted: {path}")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", record_open)
    monkeypatch.setattr(Path, "lstat", reject_protected_lstat)
    monkeypatch.setattr(Path, "resolve", reject_protected_resolve)
    monkeypatch.setattr(Path, "stat", reject_protected_stat)
    outside_sample = LegacyStateProjection(tmp_path, outside, clock=lambda: NOW).read()
    protected_sample = LegacyStateProjection(
        tmp_path,
        Path("vesper/data/massive/state.json"),
        clock=lambda: NOW,
    ).read()

    assert outside_sample.error == "Legacy state path is outside its configured root."
    assert protected_sample.error == "Legacy state path targets protected data."
    assert opened == []


def test_legacy_state_rechecks_protected_path_after_canonical_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    alias = _write_state(tmp_path, _payload(), "alias.json")
    canonical_protected = tmp_path / "vesper" / "data" / "massive" / "state.json"
    original_resolve = Path.resolve
    original_stat = Path.stat

    def fake_resolve(path: Path, *args: object, **kwargs: object) -> Path:
        if path == alias:
            return canonical_protected
        return original_resolve(path, *args, **kwargs)

    def reject_protected_stat(path: Path, *args: object, **kwargs: object):
        if path == canonical_protected:
            raise AssertionError("canonical protected path reached stat")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    monkeypatch.setattr(Path, "stat", reject_protected_stat)
    sample = LegacyStateProjection(tmp_path, alias, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Legacy state path targets protected data."


def test_legacy_state_stat_race_fails_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    state_path = _write_state(tmp_path, _payload()).resolve()
    root_path = tmp_path.resolve()
    original_resolve = Path.resolve
    original_stat = Path.stat

    def stable_resolve(path: Path, *args: object, **kwargs: object):
        if path in {root_path, state_path}:
            return path
        return original_resolve(path, *args, **kwargs)

    def removed_after_resolve(path: Path, *args: object, **kwargs: object):
        if path == state_path:
            raise FileNotFoundError("state replaced")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", stable_resolve)
    monkeypatch.setattr(Path, "stat", removed_after_resolve)
    sample = LegacyStateProjection(tmp_path, state_path, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Legacy saved engine state is unavailable."


def test_legacy_state_opened_handle_identity_mismatch_fails_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    _write_state(tmp_path, _payload())
    original_fstat = os.fstat

    def swapped_file(fileno: int):
        status = original_fstat(fileno)
        return SimpleNamespace(
            st_mode=status.st_mode,
            st_dev=status.st_dev,
            st_ino=status.st_ino + 1,
            st_nlink=status.st_nlink,
            st_size=status.st_size,
            st_mtime_ns=status.st_mtime_ns,
            st_file_attributes=getattr(status, "st_file_attributes", 0),
        )

    monkeypatch.setattr(os, "fstat", swapped_file)
    sample = LegacyStateProjection(tmp_path, Path("state.json"), clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Legacy saved engine state changed while it was read."


def test_legacy_state_rejects_opened_handle_outside_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui.projections import legacy_state

    _write_state(tmp_path, _payload())
    monkeypatch.setattr(
        legacy_state,
        "_opened_handle_path",
        lambda _handle: tmp_path.parent / "outside-state.json",
        raising=False,
    )

    sample = legacy_state.LegacyStateProjection(
        tmp_path,
        Path("state.json"),
        clock=lambda: NOW,
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Legacy state opened outside its configured root."


def test_legacy_state_rejects_symlink_and_oversized_files(tmp_path: Path) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    target = _write_state(tmp_path, _payload(), "target.json")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("file symlinks are unavailable for this Windows account")

    linked = LegacyStateProjection(tmp_path, Path("link.json"), clock=lambda: NOW).read()
    assert linked.error == "Legacy state path is a symlink or reparse point."

    (tmp_path / "large.json").write_bytes(b"x" * 65)
    oversized = LegacyStateProjection(
        tmp_path,
        Path("large.json"),
        clock=lambda: NOW,
        max_bytes=64,
    ).read()
    assert oversized.error == "Legacy saved engine state exceeds the 64-byte limit."


def test_legacy_state_rejects_hardlinked_state_file(tmp_path: Path) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    source = _write_state(tmp_path, _payload(), "source.json")
    linked = tmp_path / "state.json"
    try:
        os.link(source, linked)
    except OSError:
        pytest.skip("hard links are unavailable for this Windows account")

    sample = LegacyStateProjection(tmp_path, linked, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Legacy state path has multiple hard links."


def test_legacy_state_rejects_a_reparse_configured_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    _write_state(tmp_path, _payload())
    original_lstat = Path.lstat

    def fake_root_reparse(path: Path):
        if path == tmp_path.absolute():
            return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_root_reparse)

    sample = LegacyStateProjection(tmp_path, Path("state.json"), clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Legacy state path is a symlink or reparse point."


def test_legacy_state_rejects_an_actual_symlink_configured_root(tmp_path: Path) -> None:
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    real_root = tmp_path / "real"
    real_root.mkdir()
    _write_state(real_root, _payload())
    linked_root = tmp_path / "linked"
    try:
        linked_root.symlink_to(real_root, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable for this Windows account")

    sample = LegacyStateProjection(
        linked_root,
        Path("state.json"),
        clock=lambda: NOW,
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Legacy state path is a symlink or reparse point."


def test_legacy_state_does_not_construct_state_manager_or_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vesper import engine as trading_engine
    from vesper import state
    from vesper.platform import service
    from vesper.platform.tui.projections.legacy_state import LegacyStateProjection

    _write_state(tmp_path, _payload())
    calls: list[str] = []

    def forbidden(name: str):
        def fail(*_args: object, **_kwargs: object) -> None:
            calls.append(name)
            raise AssertionError(f"forbidden constructor reached: {name}")

        return fail

    monkeypatch.setattr(state.StateManager, "__init__", forbidden("state-manager"))
    monkeypatch.setattr(service.LocalPlatformService, "__init__", forbidden("service"))
    monkeypatch.setattr(trading_engine.TradingEngine, "__init__", forbidden("trading"))

    sample = LegacyStateProjection(tmp_path, Path("state.json"), clock=lambda: NOW).read()

    assert sample.freshness is Freshness.FRESH
    assert calls == []
