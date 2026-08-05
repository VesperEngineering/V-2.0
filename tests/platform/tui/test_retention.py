from __future__ import annotations

import gzip
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from vesper.platform.tui.retention import (
    HistoryRetentionService,
    RawLogRecord,
    RetentionError,
    deterministic_gzip,
)


NOW = datetime(2026, 8, 4, 16, 0, tzinfo=timezone.utc)
ORIGINAL_BYTES = b"first line\nsecond line\n"
ORIGINAL_HISTORY_ROWS = ("portfolio:1", "order:1", "approval:1", "evidence:1")


def _service(
    tmp_path: Path,
    *,
    age: timedelta = timedelta(days=30),
) -> tuple[HistoryRetentionService, Path]:
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    raw_log = raw_root / "agent-1.log"
    raw_log.write_bytes(ORIGINAL_BYTES)
    record = RawLogRecord(
        log_id="log:agent-1",
        relative_path="agent-1.log",
        closed_at_utc=NOW - age,
    )
    service = HistoryRetentionService(
        raw_root,
        tmp_path / "compressed",
        (record,),
        history_reader=lambda: ORIGINAL_HISTORY_ROWS,
    )
    return service, raw_log


def test_retention_removes_only_verified_raw_log_copy(tmp_path: Path) -> None:
    service, raw_log = _service(tmp_path)

    receipt = service.apply(NOW)

    assert receipt.compressed_sha256
    assert gzip.decompress(receipt.compressed_path.read_bytes()) == ORIGINAL_BYTES
    assert not raw_log.exists()
    assert service.permanent_history_rows() == ORIGINAL_HISTORY_ROWS


def test_deterministic_gzip_has_stable_bytes() -> None:
    first = deterministic_gzip(ORIGINAL_BYTES)
    second = deterministic_gzip(ORIGINAL_BYTES)

    assert first == second
    assert gzip.decompress(first) == ORIGINAL_BYTES


@pytest.mark.parametrize(
    ("age", "compressed"),
    (
        (timedelta(days=30) - timedelta(seconds=1), False),
        (timedelta(days=30), True),
        (timedelta(days=31), True),
    ),
)
def test_exact_thirty_day_boundary(
    tmp_path: Path,
    age: timedelta,
    compressed: bool,
) -> None:
    service, raw_log = _service(tmp_path, age=age)

    receipt = service.apply(NOW)

    assert bool(receipt.entries) is compressed
    assert raw_log.exists() is not compressed


def test_corrupt_existing_compressed_copy_leaves_raw_log(tmp_path: Path) -> None:
    service, raw_log = _service(tmp_path)
    compressed = tmp_path / "compressed"
    compressed.mkdir()
    (compressed / "agent-1.log.gz").write_bytes(b"not gzip")

    with pytest.raises(RetentionError, match="compressed-copy-conflict"):
        service.apply(NOW)

    assert raw_log.read_bytes() == ORIGINAL_BYTES


def test_matching_existing_compressed_copy_finishes_interrupted_run(tmp_path: Path) -> None:
    service, raw_log = _service(tmp_path)
    compressed = tmp_path / "compressed"
    compressed.mkdir()
    (compressed / "agent-1.log.gz").write_bytes(deterministic_gzip(ORIGINAL_BYTES))

    receipt = service.apply(NOW)

    assert len(receipt.entries) == 1
    assert not raw_log.exists()


@pytest.mark.parametrize(
    "relative_path",
    (
        "../outside.log",
        "/absolute.log",
        "C:/outside.log",
        "nested/../../outside.log",
        "agent-1.txt",
        "",
    ),
)
def test_invalid_raw_log_path_is_rejected(tmp_path: Path, relative_path: str) -> None:
    raw_root = tmp_path / "raw"
    raw_root.mkdir()

    with pytest.raises((TypeError, ValueError)):
        HistoryRetentionService(
            raw_root,
            tmp_path / "compressed",
            (
                RawLogRecord(
                    log_id="log:1",
                    relative_path=relative_path,
                    closed_at_utc=NOW - timedelta(days=30),
                ),
            ),
        )


def test_symlink_escape_is_rejected_without_touching_target(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    outside = tmp_path / "outside.log"
    outside.write_bytes(ORIGINAL_BYTES)
    link = raw_root / "escape.log"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    service = HistoryRetentionService(
        raw_root,
        tmp_path / "compressed",
        (
            RawLogRecord(
                log_id="log:escape",
                relative_path="escape.log",
                closed_at_utc=NOW - timedelta(days=30),
            ),
        ),
    )

    with pytest.raises(RetentionError, match="unsafe-raw-log"):
        service.apply(NOW)

    assert outside.read_bytes() == ORIGINAL_BYTES
    assert link.exists()


def test_compressed_parent_symlink_creates_nothing_outside(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    (raw_root / "nested" / "new").mkdir(parents=True)
    (raw_root / "nested" / "new" / "agent.log").write_bytes(ORIGINAL_BYTES)
    compressed_root = tmp_path / "compressed"
    compressed_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = compressed_root / "nested"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    service = HistoryRetentionService(
        raw_root,
        compressed_root,
        (
            RawLogRecord(
                log_id="log:nested",
                relative_path="nested/new/agent.log",
                closed_at_utc=NOW - timedelta(days=30),
            ),
        ),
    )

    with pytest.raises(RetentionError, match="unsafe-compressed-path"):
        service.apply(NOW)

    assert not (outside / "new").exists()
    assert (raw_root / "nested" / "new" / "agent.log").read_bytes() == ORIGINAL_BYTES


def test_missing_raw_log_is_reported_without_creating_output(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    service = HistoryRetentionService(
        raw_root,
        tmp_path / "compressed",
        (
            RawLogRecord(
                log_id="log:missing",
                relative_path="missing.log",
                closed_at_utc=NOW - timedelta(days=30),
            ),
        ),
    )

    with pytest.raises(RetentionError, match="raw-log-missing"):
        service.apply(NOW)

    assert not (tmp_path / "compressed").exists()


def test_duplicate_manifest_path_is_rejected(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    record = RawLogRecord(
        log_id="log:1",
        relative_path="agent.log",
        closed_at_utc=NOW - timedelta(days=30),
    )

    with pytest.raises(ValueError, match="duplicate raw log"):
        HistoryRetentionService(
            raw_root,
            tmp_path / "compressed",
            (record, record.model_copy(update={"log_id": "log:2"})),
        )


def test_naive_now_is_rejected_without_changes(tmp_path: Path) -> None:
    service, raw_log = _service(tmp_path)

    with pytest.raises(ValueError):
        service.apply(datetime(2026, 8, 4, 16, 0))

    assert raw_log.read_bytes() == ORIGINAL_BYTES
