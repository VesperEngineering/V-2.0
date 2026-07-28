from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.contracts import TaskRequest
from vesper.platform.evidence import FilesystemEvidenceStore
from vesper.platform.research import LocalDataResearcher, LocalModelEvaluator

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
DATABASE_RELATIVE = Path("vesper/data/massive/sp500/sp500_ohlcv.sqlite")
SPLITS_RELATIVE = Path("vesper/data/massive/split_adjustments.json")


def _request(run_id: str = "run-research") -> TaskRequest:
    return TaskRequest(
        run_id=run_id,
        task_id="task-research",
        repository_revision="abc1234",
        created_at=NOW,
        objective="Inspect bounded local research evidence.",
        repository_root=".",
        acceptance_checks=("pytest",),
    )


def _market_database(root: Path) -> Path:
    database = root / DATABASE_RELATIVE
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE sp500_ohlcv (
                   ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL
               )"""
        )
        connection.executemany(
            "INSERT INTO sp500_ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                ("AAA", "2026-01-02", 98765.4321, 11.0, 9.0, 10.5, 100.0),
                ("AAA", "2026-01-03", 10.5, 12.0, 10.0, None, 110.0),
                ("BBB", "2026-01-05", 20.0, 21.0, 19.0, 20.5, 200.0),
            ),
        )
    return database


def _split_adjustments(root: Path) -> Path:
    splits = root / SPLITS_RELATIVE
    splits.parent.mkdir(parents=True, exist_ok=True)
    splits.write_bytes(b'{"AAA":[{"date":"2020-01-01","ratio":2.0}]}')
    return splits


def _write_model_fixture(
    root: Path,
    *,
    model_bytes: bytes = b"raw-model-secret-bytes",
    expected_sha256: str | None = None,
    metadata_updates: dict[str, object] | None = None,
) -> tuple[Path, Path, Path]:
    settings = root / "config" / "settings.yaml"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        """broker:
  api_secret: SETTINGS-SECRET-MUST-NOT-LEAK
risk:
  max_position_value: 999999
strategy:
  params:
    model_path: models/xgb_ranker.json
""",
        encoding="utf-8",
    )
    model = root / "models" / "xgb_ranker.json"
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(model_bytes)
    metadata = model.with_suffix(".metadata.json")
    document: dict[str, object] = {
        "model_path": "models\\xgb_ranker.json",
        "sha256": expected_sha256 or hashlib.sha256(model_bytes).hexdigest(),
        "label_horizon": 5,
        "train_ic": 0.04,
        "out_of_sample_ic": 0.03,
        "train_samples": 100,
        "test_samples": 50,
        "model_parameters": {"credential": "METADATA-SECRET-MUST-NOT-LEAK"},
    }
    document.update(metadata_updates or {})
    metadata.write_text(json.dumps(document), encoding="utf-8")
    return settings, model, metadata


def test_data_research_is_read_only_and_reports_only_bounded_aggregates(tmp_path):
    repository = tmp_path / "repository"
    database = _market_database(repository)
    splits = _split_adjustments(repository)
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")
    database_before = database.read_bytes()
    splits_before = splits.read_bytes()
    files_before = tuple(sorted(path.relative_to(repository) for path in repository.rglob("*")))

    result = LocalDataResearcher(repository, evidence, clock=lambda: NOW).research(_request())

    assert result.available is True
    assert result.row_count == 3
    assert result.ticker_count == 2
    assert result.start_date == "2026-01-02"
    assert result.end_date == "2026-01-05"
    assert result.null_price_rows == 1
    assert result.invalid_date_rows == 0
    assert result.split_adjustments_sha256 == hashlib.sha256(splits_before).hexdigest()
    assert database.read_bytes() == database_before
    assert splits.read_bytes() == splits_before
    assert (
        tuple(sorted(path.relative_to(repository) for path in repository.rglob("*")))
        == files_before
    )

    report = evidence.read_verified(result.evidence[0])
    assert b"98765.4321" not in report
    assert b'"AAA"' not in report
    assert b'"open"' in report
    assert len(tuple((evidence.root / "runs" / result.run_id).glob("*.json"))) == 1


@pytest.mark.parametrize("database_body", (None, b"not-a-sqlite-database SECRET-PRICE-123"))
def test_data_research_missing_or_malformed_database_fails_closed(tmp_path, database_body):
    repository = tmp_path / "repository"
    database = repository / DATABASE_RELATIVE
    if database_body is not None:
        database.parent.mkdir(parents=True, exist_ok=True)
        database.write_bytes(database_body)
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")

    result = LocalDataResearcher(repository, evidence, clock=lambda: NOW).research(_request())

    assert result.available is False
    assert result.row_count == result.ticker_count == result.null_price_rows == 0
    assert result.start_date is result.end_date is None
    assert result.warnings
    assert b"SECRET-PRICE-123" not in evidence.read_verified(result.evidence[0])
    if database_body is not None:
        assert database.read_bytes() == database_body


def test_data_research_rejects_unbounded_or_malformed_dates_without_leaking_them(tmp_path):
    repository = tmp_path / "repository"
    database = _market_database(repository)
    secret_date = "SECRET-DATE-" * 10_000
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE sp500_ohlcv SET date = ?", (secret_date,))
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")

    result = LocalDataResearcher(repository, evidence, clock=lambda: NOW).research(_request())

    assert result.available is False
    assert result.start_date is result.end_date is None
    assert result.invalid_date_rows == 3
    assert secret_date.encode() not in evidence.read_verified(result.evidence[0])


def test_data_research_counts_calendar_invalid_dates_outside_coverage_bounds(tmp_path):
    repository = tmp_path / "repository"
    database = _market_database(repository)
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO sp500_ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                ("AAA", "2026-02-30", 10.0, 11.0, 9.0, 10.5, 100.0),
                ("AAA", "2026-06-30\x00SECRET", 10.0, 11.0, 9.0, 10.5, 100.0),
                ("AAA", "2026-12-31", 10.0, 11.0, 9.0, 10.5, 100.0),
            ),
        )
    _split_adjustments(repository)
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")

    result = LocalDataResearcher(repository, evidence, clock=lambda: NOW).research(_request())

    assert result.available is False
    assert result.invalid_date_rows == 2


def test_research_evidence_is_idempotent_across_replayed_nodes(tmp_path):
    repository = tmp_path / "repository"
    _market_database(repository)
    _split_adjustments(repository)
    _write_model_fixture(repository)
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")
    request = _request()

    first_data = LocalDataResearcher(repository, evidence).research(request)
    second_data = LocalDataResearcher(repository, evidence).research(request)
    first_model = LocalModelEvaluator(repository, evidence).evaluate(request)
    second_model = LocalModelEvaluator(repository, evidence).evaluate(request)

    assert first_data == second_data
    assert first_model == second_model


def test_data_research_rejects_linked_database_where_supported(tmp_path):
    repository = tmp_path / "repository"
    actual = _market_database(tmp_path / "outside")
    link = repository / DATABASE_RELATIVE
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(actual)
    except OSError:
        pytest.skip("file symlinks are not available")
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")
    before = actual.read_bytes()

    result = LocalDataResearcher(repository, evidence, clock=lambda: NOW).research(_request())

    assert result.available is False
    assert result.row_count == 0
    assert any("unsafe" in warning.lower() for warning in result.warnings)
    assert actual.read_bytes() == before


def test_data_research_can_use_separate_controller_owned_data_root(tmp_path):
    repository = tmp_path / "disposable-clone"
    repository.mkdir()
    protected_data_root = tmp_path / "protected-massive"
    database = _market_database(tmp_path / "fixture-root")
    target = protected_data_root / "sp500" / "sp500_ohlcv.sqlite"
    target.parent.mkdir(parents=True)
    target.write_bytes(database.read_bytes())
    source_splits = _split_adjustments(tmp_path / "fixture-root")
    (protected_data_root / "split_adjustments.json").write_bytes(source_splits.read_bytes())
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")

    result = LocalDataResearcher(
        repository,
        evidence,
        clock=lambda: NOW,
        massive_data_root=protected_data_root,
    ).research(_request())

    assert result.available is True
    assert result.row_count == 3
    assert not (repository / "vesper").exists()


def test_model_evaluation_hashes_without_loading_and_redacts_unbounded_inputs(tmp_path):
    repository = tmp_path / "repository"
    settings, model, metadata = _write_model_fixture(repository)
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")
    snapshots = {path: path.read_bytes() for path in (settings, model, metadata)}

    result = LocalModelEvaluator(repository, evidence, clock=lambda: NOW).evaluate(_request())

    assert result.available is True
    assert result.hash_matches is True
    assert result.evaluation_passed is True
    assert result.configured_model_path == "models/xgb_ranker.json"
    assert result.metadata_path == "models/xgb_ranker.metadata.json"
    assert result.label_horizon == 5
    assert result.train_ic == 0.04
    assert result.out_of_sample_ic == 0.03
    assert result.train_samples == 100
    assert result.test_samples == 50
    assert {path: path.read_bytes() for path in snapshots} == snapshots

    report = evidence.read_verified(result.evidence[0])
    assert b"raw-model-secret-bytes" not in report
    assert b"model_parameters" not in report
    assert b"SETTINGS-SECRET-MUST-NOT-LEAK" not in report
    assert b"METADATA-SECRET-MUST-NOT-LEAK" not in report
    assert b"max_position_value" not in report


def test_model_evaluation_hash_mismatch_is_available_but_does_not_pass(tmp_path):
    repository = tmp_path / "repository"
    _, model, _ = _write_model_fixture(repository, expected_sha256="a" * 64)
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")
    before = model.read_bytes()

    result = LocalModelEvaluator(repository, evidence, clock=lambda: NOW).evaluate(_request())

    assert result.available is True
    assert result.actual_sha256 == hashlib.sha256(before).hexdigest()
    assert result.expected_sha256 == "a" * 64
    assert result.hash_matches is False
    assert result.evaluation_passed is False
    assert model.read_bytes() == before


@pytest.mark.parametrize("settings_body", (None, "strategy: [malformed"))
def test_model_evaluation_bad_settings_does_not_use_default_artifact(tmp_path, settings_body):
    repository = tmp_path / "repository"
    settings, _, _ = _write_model_fixture(repository)
    if settings_body is None:
        settings.unlink()
    else:
        settings.write_text(settings_body, encoding="utf-8")
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")

    result = LocalModelEvaluator(repository, evidence, clock=lambda: NOW).evaluate(_request())

    assert result.available is False
    assert result.evaluation_passed is False
    assert result.configured_model_path == "models/xgb_ranker.json"
    assert result.actual_sha256 is None
    assert result.warnings
    assert result.evidence


@pytest.mark.parametrize(
    "model_path",
    (
        "models/xgb_ranker.json:payload",
        "models/CON.json",
        "models/" + "x" * 241,
    ),
)
def test_model_evaluation_rejects_windows_unsafe_or_unbounded_paths(tmp_path, model_path):
    repository = tmp_path / "repository"
    settings, _, _ = _write_model_fixture(repository)
    settings.write_text(
        f"strategy:\n  params:\n    model_path: {model_path}\n",
        encoding="utf-8",
    )
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")

    result = LocalModelEvaluator(repository, evidence, clock=lambda: NOW).evaluate(_request())

    assert result.available is False
    assert result.actual_sha256 is None
    assert result.configured_model_path == "models/xgb_ranker.json"


def test_model_evaluation_oversized_settings_returns_bounded_failure(tmp_path):
    repository = tmp_path / "repository"
    settings, _, _ = _write_model_fixture(repository)
    settings.write_bytes(b"x" * (1024 * 1024 + 1))
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")

    result = LocalModelEvaluator(repository, evidence, clock=lambda: NOW).evaluate(_request())

    assert result.available is False
    assert result.actual_sha256 is None
    assert any("settings" in warning.lower() for warning in result.warnings)


def test_model_evaluation_huge_json_integer_returns_typed_failure(tmp_path):
    repository = tmp_path / "repository"
    _, _, metadata = _write_model_fixture(repository)
    metadata.write_text('{"label_horizon":' + "9" * 5000 + "}", encoding="utf-8")
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")

    result = LocalModelEvaluator(repository, evidence, clock=lambda: NOW).evaluate(_request())

    assert result.available is False
    assert result.evaluation_passed is False
    assert any("safely" in warning.lower() for warning in result.warnings)


@pytest.mark.parametrize(
    "metadata_updates",
    (
        {"model_path": "models/another.json"},
        {"sha256": "invalid"},
        {"label_horizon": 0},
        {"train_ic": float("nan")},
        {"train_ic": 1.01},
        {"out_of_sample_ic": -1.01},
        {"train_ic": 10**1000},
        {"test_samples": True},
    ),
)
def test_model_evaluation_malformed_metadata_fails_closed(tmp_path, metadata_updates):
    repository = tmp_path / "repository"
    _write_model_fixture(repository, metadata_updates=metadata_updates)
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")

    result = LocalModelEvaluator(repository, evidence, clock=lambda: NOW).evaluate(_request())

    assert result.available is False
    assert result.evaluation_passed is False
    assert any("metadata" in warning.lower() for warning in result.warnings)
    assert result.evidence


def test_model_evaluation_rejects_linked_artifact_where_supported(tmp_path):
    repository = tmp_path / "repository"
    _, model, metadata = _write_model_fixture(repository)
    outside_model = tmp_path / "outside-model.json"
    outside_model.write_bytes(model.read_bytes())
    model.unlink()
    try:
        model.symlink_to(outside_model)
    except OSError:
        pytest.skip("file symlinks are not available")
    evidence = FilesystemEvidenceStore(tmp_path / "evidence")
    metadata_before = metadata.read_bytes()

    result = LocalModelEvaluator(repository, evidence, clock=lambda: NOW).evaluate(_request())

    assert result.available is False
    assert result.actual_sha256 is None
    assert result.evaluation_passed is False
    assert outside_model.read_bytes() == b"raw-model-secret-bytes"
    assert metadata.read_bytes() == metadata_before
