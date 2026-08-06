"""Controller-owned, read-only local research evaluators."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import stat
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

import yaml

from .contracts import DataResearchResult, ModelEvaluationResult, TaskRequest
from .evidence import FilesystemEvidenceStore

_DATABASE_PATH = "vesper/data/massive/sp500/sp500_ohlcv.sqlite"
_SPLIT_ADJUSTMENTS_PATH = "vesper/data/massive/split_adjustments.json"
_TABLE_NAME = "sp500_ohlcv"
_REQUIRED_COLUMNS = ("ticker", "date", "open", "high", "low", "close", "volume")
_DEFAULT_MODEL_PATH = "models/xgb_ranker.json"
_SHA256_CHUNK_SIZE = 1024 * 1024
_MAX_RESEARCH_DOCUMENT_BYTES = 1024 * 1024
_MAX_MODEL_PATH_LENGTH = 240
_REPLAY_STABLE_TIMESTAMP_SCOPE = "run-created-at-for-replay"
_MODEL_EVALUATION_SCOPE = "artifact-integrity-only"
_WINDOWS_INVALID_PATH_CHARACTERS = frozenset('<>:"|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_reparse_point(path: Path) -> bool:
    metadata = path.lstat()
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _is_safe_regular_file(repository_root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(repository_root)
        current = repository_root
        for part in relative.parts:
            current = current / part
            if _is_reparse_point(current):
                return False
        resolved = path.resolve(strict=True)
        return resolved.is_relative_to(repository_root) and stat.S_ISREG(path.lstat().st_mode)
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        return False


def _stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_SHA256_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_body(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _authority_payload(request: TaskRequest, created_at: datetime) -> dict[str, object]:
    return {
        "schema_version": request.schema_version,
        "run_id": request.run_id,
        "task_id": request.task_id,
        "repository_revision": request.repository_revision,
        "created_at": created_at.isoformat(),
    }


def _normalize_relative_path(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > _MAX_MODEL_PATH_LENGTH
        or "\x00" in value
    ):
        return None
    windows = PureWindowsPath(value)
    candidate = PurePosixPath(value.replace("\\", "/"))
    if windows.is_absolute() or windows.drive or candidate.is_absolute() or ".." in candidate.parts:
        return None
    normalized = candidate.as_posix()
    if normalized in {"", "."}:
        return None
    for part in candidate.parts:
        if (
            not part
            or len(part) > 255
            or part.endswith((" ", "."))
            or any(character in _WINDOWS_INVALID_PATH_CHARACTERS for character in part)
            or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
        ):
            return None
    return normalized


def _metadata_path_for(model_path: str) -> str:
    return PurePosixPath(model_path).with_suffix(".metadata.json").as_posix()


def _finite_correlation(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        candidate = float(value)
    except (OverflowError, ValueError):
        return None
    return candidate if math.isfinite(candidate) and -1 <= candidate <= 1 else None


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _read_document(path: Path) -> str:
    with path.open("rb") as handle:
        body = handle.read(_MAX_RESEARCH_DOCUMENT_BYTES + 1)
    if len(body) > _MAX_RESEARCH_DOCUMENT_BYTES:
        raise ValueError("research document exceeds size limit")
    return body.decode("utf-8")


class LocalDataResearcher:
    """Inspect fixed local market-data artifacts without exposing observations."""

    def __init__(
        self,
        repository_root: Path,
        evidence: FilesystemEvidenceStore,
        clock: Callable[[], datetime] = _utc_now,
        query_timeout_seconds: float = 30,
        massive_data_root: Path | None = None,
    ) -> None:
        if query_timeout_seconds <= 0:
            raise ValueError("query_timeout_seconds must be positive")
        self.repository_root = repository_root.resolve()
        self.massive_data_root = (
            self.repository_root / "vesper" / "data" / "massive"
            if massive_data_root is None
            else massive_data_root.resolve()
        )
        self.evidence = evidence
        self.clock = clock
        self.query_timeout_seconds = query_timeout_seconds

    def research(self, request: TaskRequest) -> DataResearchResult:
        created_at = request.created_at
        database = self.massive_data_root / "sp500" / "sp500_ohlcv.sqlite"
        split_adjustments = self.massive_data_root / "split_adjustments.json"
        warnings: list[str] = []
        row_count = 0
        ticker_count = 0
        start_date: str | None = None
        end_date: str | None = None
        null_price_rows = 0
        invalid_date_rows = 0
        available = False

        if not _is_safe_regular_file(self.massive_data_root, database):
            warnings.append("Market database is missing or unsafe.")
        else:
            connection: sqlite3.Connection | None = None
            try:
                connection = sqlite3.connect(
                    f"{database.as_uri()}?mode=ro&immutable=1",
                    uri=True,
                )
                connection.execute("PRAGMA query_only = ON")
                connection.execute("PRAGMA trusted_schema = OFF")
                deadline = time.monotonic() + self.query_timeout_seconds
                connection.set_progress_handler(
                    lambda: 1 if time.monotonic() >= deadline else 0,
                    10_000,
                )
                columns = {
                    str(row[1]).casefold()
                    for row in connection.execute(f'PRAGMA table_info("{_TABLE_NAME}")')
                }
                if not set(_REQUIRED_COLUMNS).issubset(columns):
                    warnings.append("Market database schema is missing required columns.")
                else:
                    aggregate = connection.execute(
                        f'''SELECT COUNT(*), COUNT(DISTINCT ticker),
                                   MIN(substr(CAST(date AS TEXT), 1, 10)),
                                   MAX(substr(CAST(date AS TEXT), 1, 10)),
                                   SUM(CASE WHEN open IS NULL OR high IS NULL OR low IS NULL
                                                 OR close IS NULL OR volume IS NULL
                                            THEN 1 ELSE 0 END),
                                   SUM(CASE
                                         WHEN typeof(date) <> 'text' THEN 1
                                         WHEN substr(CAST(date AS BLOB), 11, 1) <> X'' THEN 1
                                         WHEN length(CAST(date AS BLOB)) <> 10 THEN 1
                                         WHEN substr(date, 1, 10) NOT GLOB
                                              '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
                                           THEN 1
                                         WHEN julianday(substr(date, 1, 10)) IS NULL THEN 1
                                         WHEN date(julianday(substr(date, 1, 10))) <>
                                              substr(date, 1, 10)
                                           THEN 1
                                         ELSE 0
                                       END)
                            FROM "{_TABLE_NAME}"'''
                    ).fetchone()
                    if aggregate is None or len(aggregate) != 6:
                        raise sqlite3.DatabaseError("aggregate result unavailable")
                    (
                        candidate_rows,
                        candidate_tickers,
                        candidate_start,
                        candidate_end,
                        candidate_nulls,
                        candidate_invalid_dates,
                    ) = aggregate
                    valid_counts = all(
                        type(value) is int and value >= 0
                        for value in (candidate_rows, candidate_tickers)
                    ) and all(
                        value is None or type(value) is int
                        for value in (candidate_nulls, candidate_invalid_dates)
                    )
                    valid_dates = all(
                        _is_iso_date(value) for value in (candidate_start, candidate_end)
                    )
                    if valid_counts:
                        row_count = candidate_rows
                        ticker_count = candidate_tickers
                        null_price_rows = candidate_nulls or 0
                        invalid_date_rows = candidate_invalid_dates or 0
                        if (
                            valid_dates
                            and row_count > 0
                            and ticker_count > 0
                            and invalid_date_rows == 0
                        ):
                            start_date = candidate_start
                            end_date = candidate_end
                            if null_price_rows == 0:
                                available = True
                            else:
                                warnings.append("Market database contains null price rows.")
                        else:
                            warnings.append("Market database has no usable coverage.")
                    else:
                        warnings.append("Market database has no usable coverage.")
            except (OSError, sqlite3.Error, TypeError, ValueError):
                warnings.append("Market database could not be queried safely.")
            finally:
                if connection is not None:
                    connection.close()

        split_sha256: str | None = None
        if not split_adjustments.exists():
            warnings.append("Split adjustments file is missing.")
        elif not _is_safe_regular_file(self.massive_data_root, split_adjustments):
            warnings.append("Split adjustments file is unsafe.")
        else:
            try:
                split_sha256 = _stream_sha256(split_adjustments)
            except OSError:
                warnings.append("Split adjustments file could not be hashed safely.")
        if split_sha256 is None:
            available = False

        result_fields: dict[str, object] = {
            "timestamp_scope": _REPLAY_STABLE_TIMESTAMP_SCOPE,
            "available": available,
            "database_path": _DATABASE_PATH,
            "table_name": _TABLE_NAME,
            "row_count": row_count,
            "ticker_count": ticker_count,
            "start_date": start_date,
            "end_date": end_date,
            "required_columns": _REQUIRED_COLUMNS,
            "null_price_rows": null_price_rows,
            "invalid_date_rows": invalid_date_rows,
            "split_adjustments_path": _SPLIT_ADJUSTMENTS_PATH,
            "split_adjustments_sha256": split_sha256,
            "warnings": tuple(warnings),
        }
        evidence = self.evidence.put_bytes(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=created_at,
            artifact_id="data-research",
            body=_json_body({**_authority_payload(request, created_at), **result_fields}),
            media_type="application/json",
            suffix=".json",
        )
        return DataResearchResult(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=created_at,
            **result_fields,
            evidence=(evidence,),
        )


class LocalModelEvaluator:
    """Validate a configured local model artifact without loading or executing it."""

    def __init__(
        self,
        repository_root: Path,
        evidence: FilesystemEvidenceStore,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.evidence = evidence
        self.clock = clock

    def evaluate(self, request: TaskRequest) -> ModelEvaluationResult:
        created_at = request.created_at
        warnings: list[str] = []
        configured_model_path = _DEFAULT_MODEL_PATH
        metadata_path = _metadata_path_for(configured_model_path)
        config_valid = False
        settings_path = self.repository_root / "config" / "settings.yaml"

        if not _is_safe_regular_file(self.repository_root, settings_path):
            warnings.append("Model settings are missing or unsafe; evaluation failed closed.")
        else:
            try:
                settings = yaml.safe_load(_read_document(settings_path))
                configured = settings["strategy"]["params"]["model_path"]
                normalized = _normalize_relative_path(configured)
                if normalized is None:
                    raise ValueError("invalid model path")
                configured_model_path = normalized
                metadata_path = _metadata_path_for(normalized)
                config_valid = True
            except (
                KeyError,
                OSError,
                RecursionError,
                TypeError,
                UnicodeError,
                ValueError,
                yaml.YAMLError,
            ):
                warnings.append("Model settings are malformed; evaluation failed closed.")

        actual_sha256: str | None = None
        expected_sha256: str | None = None
        hash_matches: bool | None = None
        label_horizon: int | None = None
        train_ic: float | None = None
        out_of_sample_ic: float | None = None
        train_samples: int | None = None
        test_samples: int | None = None
        available = False

        configured_parts = PurePosixPath(configured_model_path).parts
        path_inside_models = len(configured_parts) > 1 and configured_parts[0] == "models"
        model = self.repository_root.joinpath(*configured_parts)
        metadata = self.repository_root.joinpath(*PurePosixPath(metadata_path).parts)

        if config_valid and not path_inside_models:
            warnings.append("Configured model path is outside the repository models directory.")
        elif config_valid and not _is_safe_regular_file(self.repository_root, model):
            warnings.append("Configured model artifact is missing or unsafe.")
        elif config_valid and not _is_safe_regular_file(self.repository_root, metadata):
            warnings.append("Model metadata is missing or unsafe.")
        elif config_valid:
            try:
                actual_sha256 = _stream_sha256(model)
                metadata_document = json.loads(_read_document(metadata))
            except (OSError, RecursionError, UnicodeError, ValueError):
                warnings.append("Model artifact or metadata could not be read safely.")
            else:
                if not isinstance(metadata_document, dict):
                    warnings.append("Model metadata is malformed.")
                else:
                    metadata_model_path = _normalize_relative_path(
                        metadata_document.get("model_path")
                    )
                    raw_sha256 = metadata_document.get("sha256")
                    if (
                        isinstance(raw_sha256, str)
                        and len(raw_sha256) == 64
                        and all(character in "0123456789abcdef" for character in raw_sha256)
                    ):
                        expected_sha256 = raw_sha256
                        hash_matches = actual_sha256 == expected_sha256
                    raw_label_horizon = metadata_document.get("label_horizon")
                    raw_train_samples = metadata_document.get("train_samples")
                    raw_test_samples = metadata_document.get("test_samples")
                    raw_train_ic = metadata_document.get("train_ic")
                    raw_out_of_sample_ic = metadata_document.get("out_of_sample_ic")
                    if type(raw_label_horizon) is int and raw_label_horizon > 0:
                        label_horizon = raw_label_horizon
                    if type(raw_train_samples) is int and raw_train_samples > 0:
                        train_samples = raw_train_samples
                    if type(raw_test_samples) is int and raw_test_samples > 0:
                        test_samples = raw_test_samples
                    train_ic = _finite_correlation(raw_train_ic)
                    out_of_sample_ic = _finite_correlation(raw_out_of_sample_ic)

                    metadata_valid = (
                        all(
                            value is not None
                            for value in (
                                expected_sha256,
                                label_horizon,
                                train_ic,
                                out_of_sample_ic,
                                train_samples,
                                test_samples,
                            )
                        )
                        and metadata_model_path == configured_model_path
                    )
                    if not metadata_valid:
                        warnings.append("Model metadata failed validation.")
                    else:
                        available = True
                        if hash_matches is False:
                            warnings.append("Model artifact hash does not match metadata.")

        evaluation_passed = bool(available and hash_matches)
        result_fields: dict[str, object] = {
            "timestamp_scope": _REPLAY_STABLE_TIMESTAMP_SCOPE,
            "evaluation_scope": _MODEL_EVALUATION_SCOPE,
            "available": available,
            "configured_model_path": configured_model_path,
            "metadata_path": metadata_path,
            "actual_sha256": actual_sha256,
            "expected_sha256": expected_sha256,
            "hash_matches": hash_matches,
            "label_horizon": label_horizon,
            "train_ic": train_ic,
            "out_of_sample_ic": out_of_sample_ic,
            "train_samples": train_samples,
            "test_samples": test_samples,
            "evaluation_passed": evaluation_passed,
            "warnings": tuple(warnings),
        }
        evidence = self.evidence.put_bytes(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=created_at,
            artifact_id="model-evaluation",
            body=_json_body({**_authority_payload(request, created_at), **result_fields}),
            media_type="application/json",
            suffix=".json",
        )
        return ModelEvaluationResult(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=created_at,
            **result_fields,
            evidence=(evidence,),
        )
