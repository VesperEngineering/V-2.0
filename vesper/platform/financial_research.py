"""Deterministic Phase 1 financial-research intake and planning."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath

from vesper.platform.contracts import (
    AnalysisNode,
    DerivedDatasetReceipt,
    FinancialAnalysisPlan,
    FinancialEventEnvelope,
    FinancialEventType,
    FinancialGapAssessment,
    FinancialRecommendation,
    FinancialResearchRequest,
    FinancialResearchStatus,
    FinancialTriggerDecision,
)
from vesper.platform.evidence import DuplicateEvidenceError, FilesystemEvidenceStore


class FinancialResearchError(ValueError):
    """A financial-research request or plan is not admitted for Phase 1."""


_SUPPORTED_OPERATIONS = {
    "source-coverage": ("symbol", "coverage_start", "coverage_end"),
    "coverage-summary": ("symbol", "coverage_days"),
}
_TABLE_NAME = "sp500_ohlcv"
_REQUIRED_COLUMNS = {"ticker", "date", "close"}
_SHA256_CHUNK_SIZE = 1024 * 1024
_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
FINANCIAL_RESEARCH_NON_AUTHORITY = (
    "Research evidence only; no trading, order, capital-allocation, risk, deployment, "
    "scheduler, or model-promotion authority."
)


@dataclass(frozen=True, slots=True)
class _SourceIdentity:
    device: int
    inode: int
    size: int
    mtime_ns: int


def decide_financial_trigger(event: FinancialEventEnvelope) -> FinancialTriggerDecision:
    if event.event_type is FinancialEventType.DIRECT_REQUEST:
        triggered = True
        reason = "A direct operator request is in scope for analysis-only research."
    else:
        triggered = event.observed_metric < event.threshold
        reason = (
            "The weak model result is below the admitted threshold."
            if triggered
            else "The weak model result meets or exceeds the admitted threshold."
        )

    return FinancialTriggerDecision(
        run_id=event.run_id,
        task_id=event.task_id,
        repository_revision=event.repository_revision,
        created_at=event.created_at,
        event_id=event.event_id,
        non_authority=event.non_authority,
        triggered=triggered,
        status=(
            FinancialResearchStatus.REQUESTED if triggered else FinancialResearchStatus.IGNORED
        ),
        reason=reason,
        workflow="analysis-only",
        resource_budget="bounded-local",
    )


def build_coverage_research_request(
    event: FinancialEventEnvelope,
    decision: FinancialTriggerDecision,
) -> FinancialResearchRequest:
    if not decision.should_research:
        raise FinancialResearchError("ignored events cannot build a research request")
    if (
        decision.run_id != event.run_id
        or decision.task_id != event.task_id
        or decision.repository_revision != event.repository_revision
        or decision.event_id != event.event_id
    ):
        raise FinancialResearchError("trigger decision authority does not match the event")

    symbols = ", ".join(event.symbols)
    return FinancialResearchRequest(
        run_id=event.run_id,
        task_id=event.task_id,
        repository_revision=event.repository_revision,
        created_at=event.created_at,
        event_id=event.event_id,
        non_authority=event.non_authority,
        request_id=f"{event.event_id}-coverage",
        status=FinancialResearchStatus.REQUESTED,
        questions=(f"What local coverage exists for {symbols}?",),
        source_classes=("local-market-data",),
        symbols=event.symbols,
        time_window_start=event.requested_start_date,
        time_window_end=event.requested_end_date,
        sufficiency_criteria=("Coverage dates are known.",),
    )


def build_coverage_analysis_plan(request: FinancialResearchRequest) -> FinancialAnalysisPlan:
    source = AnalysisNode(
        run_id=request.run_id,
        task_id=request.task_id,
        repository_revision=request.repository_revision,
        created_at=request.created_at,
        event_id=request.event_id,
        non_authority=request.non_authority,
        node_id="market-coverage-source",
        kind="source-coverage",
        output_schema=_SUPPORTED_OPERATIONS["source-coverage"],
        transform_sha256=_transform_hash("source-coverage"),
    )
    summary = AnalysisNode(
        run_id=request.run_id,
        task_id=request.task_id,
        repository_revision=request.repository_revision,
        created_at=request.created_at,
        event_id=request.event_id,
        non_authority=request.non_authority,
        node_id="coverage-summary",
        kind="coverage-summary",
        depends_on=(source.node_id,),
        output_schema=_SUPPORTED_OPERATIONS["coverage-summary"],
        transform_sha256=_transform_hash("coverage-summary"),
    )
    return FinancialAnalysisPlan(
        run_id=request.run_id,
        task_id=request.task_id,
        repository_revision=request.repository_revision,
        created_at=request.created_at,
        event_id=request.event_id,
        non_authority=request.non_authority,
        plan_id=f"{request.request_id}-plan",
        status=FinancialResearchStatus.PLANNED,
        nodes=(source, summary),
        acceptance_checks=("coverage dates are present",),
    )


def validate_financial_analysis_plan(plan: FinancialAnalysisPlan) -> tuple[str, ...]:
    node_ids = tuple(node.node_id for node in plan.nodes)
    if len(set(node_ids)) != len(node_ids):
        raise FinancialResearchError("analysis plan contains duplicate node IDs")

    known_node_ids = set(node_ids)
    for node in plan.nodes:
        expected_schema = _SUPPORTED_OPERATIONS.get(node.kind)
        if expected_schema is None:
            raise FinancialResearchError(f"unsupported analysis operation: {node.kind}")
        if node.output_schema != expected_schema:
            raise FinancialResearchError(f"invalid output schema for operation: {node.kind}")
        if not set(node.depends_on).issubset(known_node_ids):
            raise FinancialResearchError("analysis plan has an unknown dependency")

    remaining_dependencies = {node.node_id: set(node.depends_on) for node in plan.nodes}
    ready = [node.node_id for node in plan.nodes if not remaining_dependencies[node.node_id]]
    order: list[str] = []
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for node in plan.nodes:
            dependencies = remaining_dependencies[node.node_id]
            if node_id not in dependencies:
                continue
            dependencies.remove(node_id)
            if not dependencies:
                ready.append(node.node_id)

    if len(order) != len(plan.nodes):
        raise FinancialResearchError("analysis plan contains a dependency cycle")

    expected_nodes = ("market-coverage-source", "coverage-summary")
    if node_ids != expected_nodes:
        raise FinancialResearchError("Phase 1 requires the static two-node analysis plan")
    source, summary = plan.nodes
    if (
        source.kind != "source-coverage"
        or source.depends_on
        or summary.kind != "coverage-summary"
        or summary.depends_on != (source.node_id,)
    ):
        raise FinancialResearchError("Phase 1 requires the static two-node analysis plan")
    return tuple(order)


class LocalFinancialResearchExecutor:
    """Execute the single admitted Phase 1 coverage aggregate locally."""

    def __init__(
        self,
        massive_root: Path,
        derived_root: Path,
        evidence: FilesystemEvidenceStore,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.massive_root = Path(massive_root).absolute()
        resolved_derived = _validate_derived_root(Path(derived_root), self.massive_root)
        self.evidence = _validate_evidence_store(
            evidence,
            massive_root=self.massive_root,
            derived_root=resolved_derived,
        )
        self._evidence_root = self.evidence.root.resolve(strict=True)
        self.derived_root = resolved_derived
        self.clock = clock

    def execute(
        self,
        event: FinancialEventEnvelope,
        request: FinancialResearchRequest,
        plan: FinancialAnalysisPlan,
    ) -> tuple[DerivedDatasetReceipt, FinancialGapAssessment, FinancialRecommendation]:
        _validate_execution_inputs(event, request, plan)
        start = _parse_iso_date(request.time_window_start, "start date")
        end = _parse_iso_date(request.time_window_end, "end date")
        if start > end:
            raise FinancialResearchError("research start date must not follow end date")

        database = self.massive_root / "sp500" / "sp500_ohlcv.sqlite"
        _reject_sqlite_sidecars(database)
        source_identity = _source_identity(self.massive_root, database)
        source_sha256 = _stream_sha256(database, self.massive_root, source_identity)
        _reject_sqlite_sidecars(database)
        aggregate = self._coverage_aggregate(
            database,
            request.symbols,
            request.time_window_start,
            request.time_window_end,
            self.massive_root,
            source_identity,
        )
        _reject_sqlite_sidecars(database)
        _require_source_identity(self.massive_root, database, source_identity)
        if _stream_sha256(database, self.massive_root, source_identity) != source_sha256:
            raise FinancialResearchError("market database changed during analysis")
        _reject_sqlite_sidecars(database)

        row_count, ticker_count, coverage_start, coverage_end, null_close_count = aggregate
        if row_count == 0 or ticker_count == 0 or coverage_start is None or coverage_end is None:
            raise FinancialResearchError("requested market coverage is empty")
        _parse_iso_date(coverage_start, "coverage start")
        _parse_iso_date(coverage_end, "coverage end")

        plan_sha256 = sha256(_canonical_json(plan.model_dump(mode="json"))).hexdigest()
        transform_sha256 = sha256(
            _canonical_json(
                [
                    {
                        "kind": node.kind,
                        "output_schema": node.output_schema,
                        "transform_sha256": node.transform_sha256,
                    }
                    for node in plan.nodes
                ]
            )
        ).hexdigest()
        cache_key_sha256 = sha256(
            _canonical_json(
                {
                    "source_sha256": source_sha256,
                    "plan_sha256": plan_sha256,
                    "transform_sha256": transform_sha256,
                    "symbols": request.symbols,
                    "time_window_start": request.time_window_start,
                    "time_window_end": request.time_window_end,
                }
            )
        ).hexdigest()
        dataset_id = f"coverage-{cache_key_sha256[:16]}"
        relative_output = f"{event.run_id}/{dataset_id}.json"
        body = _canonical_json(
            {
                "cache_key_sha256": cache_key_sha256,
                "coverage_end": coverage_end,
                "coverage_start": coverage_start,
                "dataset_id": dataset_id,
                "event_id": event.event_id,
                "lineage_ids": [event.event_id, request.request_id, plan.plan_id],
                "null_close_count": null_close_count,
                "plan_sha256": plan_sha256,
                "repository_revision": event.repository_revision,
                "row_count": row_count,
                "run_id": event.run_id,
                "source_sha256": source_sha256,
                "symbols": list(request.symbols),
                "task_id": event.task_id,
                "ticker_count": ticker_count,
                "time_window_end": request.time_window_end,
                "time_window_start": request.time_window_start,
                "transform_sha256": transform_sha256,
            }
        )
        _require_current_evidence_store(
            self.evidence,
            expected_root=self._evidence_root,
            massive_root=self.massive_root,
            derived_root=self.derived_root,
        )
        _write_immutable(self.derived_root, relative_output, body)
        _require_current_evidence_store(
            self.evidence,
            expected_root=self._evidence_root,
            massive_root=self.massive_root,
            derived_root=self.derived_root,
        )
        try:
            validation = self.evidence.put_bytes(
                run_id=event.run_id,
                task_id=event.task_id,
                repository_revision=event.repository_revision,
                created_at=event.created_at,
                artifact_id=f"{dataset_id}-validation",
                body=body,
                media_type="application/json",
                suffix=".json",
            )
        except DuplicateEvidenceError as exc:
            raise FinancialResearchError(
                "immutable evidence copy already exists with different content"
            ) from exc
        dataset = DerivedDatasetReceipt(
            run_id=event.run_id,
            task_id=event.task_id,
            repository_revision=event.repository_revision,
            created_at=event.created_at,
            event_id=event.event_id,
            non_authority=FINANCIAL_RESEARCH_NON_AUTHORITY,
            dataset_id=dataset_id,
            schema_fields=(
                "row_count",
                "ticker_count",
                "coverage_start",
                "coverage_end",
                "null_close_count",
            ),
            source_hashes=(source_sha256,),
            transform_sha256=transform_sha256,
            cache_key_sha256=cache_key_sha256,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            lineage_ids=(event.event_id, request.request_id, plan.plan_id),
            derived_output_path=relative_output,
            validation_evidence=validation,
            row_count=row_count,
            ticker_count=ticker_count,
            null_close_count=null_close_count,
        )
        return dataset, *_assess_coverage(dataset, validation)

    @staticmethod
    def _coverage_aggregate(
        database: Path,
        symbols: tuple[str, ...],
        start: str,
        end: str,
        massive_root: Path,
        source_identity: _SourceIdentity,
    ) -> tuple[int, int, str | None, str | None, int]:
        placeholders = ", ".join("?" for _ in symbols)
        connection: sqlite3.Connection | None = None
        try:
            _require_stable_source(massive_root, database, source_identity)
            connection = sqlite3.connect(
                f"{database.resolve(strict=True).as_uri()}?mode=ro&immutable=1",
                uri=True,
            )
            _require_stable_source(massive_root, database, source_identity)
            connection.execute("PRAGMA query_only = ON")
            _require_stable_source(massive_root, database, source_identity)
            connection.execute("PRAGMA trusted_schema = OFF")
            _require_stable_source(massive_root, database, source_identity)
            columns = {
                str(row[1]).casefold()
                for row in connection.execute(f'PRAGMA table_info("{_TABLE_NAME}")')
            }
            _require_stable_source(massive_root, database, source_identity)
            if not _REQUIRED_COLUMNS.issubset(columns):
                raise FinancialResearchError("market database schema is missing required columns")
            _require_stable_source(massive_root, database, source_identity)
            result = connection.execute(
                f'''WITH requested AS (
                        SELECT ticker, date, close,
                               CASE
                                 WHEN typeof(date) <> 'text' THEN 0
                                 WHEN length(CAST(date AS BLOB)) <> 10 THEN 0
                                 WHEN date NOT GLOB
                                      '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN 0
                                 WHEN substr(date, 1, 4) = '0000' THEN 0
                                 WHEN julianday(date) IS NULL THEN 0
                                 WHEN date(julianday(date)) <> date THEN 0
                                 ELSE 1
                               END AS valid_date
                        FROM "{_TABLE_NAME}"
                        WHERE ticker IN ({placeholders})
                    ), classified AS (
                        SELECT ticker, date, close, valid_date,
                               CASE
                                 WHEN valid_date = 1 AND date >= ? AND date <= ? THEN 1
                                 ELSE 0
                               END AS in_window
                        FROM requested
                    )
                    SELECT COALESCE(SUM(in_window), 0),
                           COUNT(DISTINCT CASE WHEN in_window = 1 THEN ticker END),
                           MIN(CASE WHEN in_window = 1 THEN date END),
                           MAX(CASE WHEN in_window = 1 THEN date END),
                           COALESCE(SUM(CASE
                             WHEN in_window = 1 AND close IS NULL THEN 1 ELSE 0 END), 0),
                           COALESCE(SUM(CASE WHEN valid_date = 0 THEN 1 ELSE 0 END), 0)
                    FROM classified''',
                (*symbols, start, end),
            ).fetchone()
            _require_stable_source(massive_root, database, source_identity)
        except FinancialResearchError:
            raise
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            raise FinancialResearchError("market database could not be queried safely") from exc
        finally:
            if connection is not None:
                connection.close()
        _require_stable_source(massive_root, database, source_identity)
        if result is None or len(result) != 6:
            raise FinancialResearchError("market coverage aggregate is unavailable")
        rows, tickers, coverage_start, coverage_end, nulls, invalid_dates = result
        if (
            type(rows) is not int
            or type(tickers) is not int
            or type(nulls) is not int
            or type(invalid_dates) is not int
            or min(rows, tickers, nulls, invalid_dates) < 0
        ):
            raise FinancialResearchError("market coverage aggregate is malformed")
        if invalid_dates:
            raise FinancialResearchError("market coverage contains invalid dates")
        return rows, tickers, coverage_start, coverage_end, nulls


def _transform_hash(operation: str) -> str:
    return sha256(operation.encode("utf-8")).hexdigest()


def _validate_execution_inputs(
    event: FinancialEventEnvelope,
    request: FinancialResearchRequest,
    plan: FinancialAnalysisPlan,
) -> None:
    if not _SAFE_SEGMENT.fullmatch(event.run_id) or event.run_id in {".", ".."}:
        raise FinancialResearchError("unsafe financial research run ID")
    authority = (event.run_id, event.task_id, event.repository_revision, event.event_id)
    if authority != (
        request.run_id,
        request.task_id,
        request.repository_revision,
        request.event_id,
    ) or authority != (plan.run_id, plan.task_id, plan.repository_revision, plan.event_id):
        raise FinancialResearchError("financial research authority does not match")
    if request.status is not FinancialResearchStatus.REQUESTED:
        raise FinancialResearchError("financial research request is not executable")
    if plan.status is not FinancialResearchStatus.PLANNED:
        raise FinancialResearchError("financial analysis plan is not executable")
    if not decide_financial_trigger(event).should_research:
        raise FinancialResearchError("event does not trigger financial research")
    validate_financial_analysis_plan(plan)


def _parse_iso_date(value: str, label: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise FinancialResearchError(f"invalid {label}") from exc
    if parsed.isoformat() != value:
        raise FinancialResearchError(f"invalid {label}")
    return parsed


def _canonical_json(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _is_reparse_point(path: Path) -> bool:
    metadata = path.lstat()
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _has_reparse_component(path: Path) -> bool:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    try:
        for part in absolute.parts[1:]:
            current = current / part
            if (current.exists() or current.is_symlink()) and _is_reparse_point(current):
                return True
    except OSError:
        return True
    return False


def _is_safe_source_file(root: Path, path: Path) -> bool:
    try:
        if _has_reparse_component(root) or _has_reparse_component(path):
            return False
        resolved_root = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        return resolved.is_relative_to(resolved_root) and stat.S_ISREG(path.lstat().st_mode)
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        return False


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _protected_roots(massive_root: Path) -> tuple[Path, ...]:
    repository = Path(__file__).resolve().parents[2]
    return (
        repository,
        (repository / "vesper" / "data" / "massive").resolve(),
        (repository / "vesper" / "data" / "model_research").resolve(),
        massive_root.resolve(),
    )


def _validate_derived_root(configured: Path, massive_root: Path) -> Path:
    if _has_reparse_component(configured):
        raise FinancialResearchError("derived root must not traverse a symlink or reparse point")
    resolved = configured.resolve()
    if any(_paths_overlap(resolved, root) for root in _protected_roots(massive_root)):
        raise FinancialResearchError(
            "derived root must be outside the repository and protected data"
        )
    return resolved


def _prepare_derived_root(root: Path) -> Path:
    parent = root.parent
    try:
        if (
            _has_reparse_component(parent)
            or parent.resolve(strict=True) != parent
            or not parent.is_dir()
        ):
            raise FinancialResearchError("derived root parent is unsafe")
        root.mkdir(parents=False, exist_ok=True)
    except FinancialResearchError:
        raise
    except OSError as exc:
        raise FinancialResearchError("derived root could not be created safely") from exc
    _require_derived_root(root)
    return root


def _validate_evidence_store(
    evidence: object,
    *,
    massive_root: Path,
    derived_root: Path,
) -> FilesystemEvidenceStore:
    if type(evidence) is not FilesystemEvidenceStore:
        raise FinancialResearchError("a concrete filesystem evidence store is required")
    _require_valid_evidence_root(
        evidence.root,
        massive_root=massive_root,
        derived_root=derived_root,
    )
    return evidence


def _require_valid_evidence_root(
    root: Path,
    *,
    massive_root: Path,
    derived_root: Path,
) -> None:
    try:
        resolved = root.resolve(strict=True)
        if (
            resolved != root
            or not root.is_dir()
            or _has_reparse_component(root)
            or any(
                _paths_overlap(resolved, protected) for protected in _protected_roots(massive_root)
            )
            or _paths_overlap(resolved, derived_root)
        ):
            raise FinancialResearchError(
                "evidence root must be a safe directory outside repository and data roots"
            )
    except FinancialResearchError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise FinancialResearchError("evidence root is missing or unsafe") from exc


def _require_current_evidence_store(
    evidence: FilesystemEvidenceStore,
    *,
    expected_root: Path,
    massive_root: Path,
    derived_root: Path,
) -> None:
    try:
        current_root = evidence.root.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise FinancialResearchError("evidence root is missing or unsafe") from exc
    if current_root != expected_root:
        raise FinancialResearchError("evidence root changed after validation")
    _require_valid_evidence_root(
        current_root,
        massive_root=massive_root,
        derived_root=derived_root,
    )


def _require_derived_root(root: Path) -> None:
    try:
        if not root.is_dir() or _has_reparse_component(root) or root.resolve(strict=True) != root:
            raise FinancialResearchError("derived root changed or is unsafe")
    except FinancialResearchError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise FinancialResearchError("derived root changed or is unsafe") from exc


def _source_identity(root: Path, path: Path) -> _SourceIdentity:
    if not _is_safe_source_file(root, path):
        raise FinancialResearchError("market database is missing or unsafe")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise FinancialResearchError("market database is missing or unsafe") from exc
    return _SourceIdentity(
        device=metadata.st_dev,
        inode=metadata.st_ino,
        size=metadata.st_size,
        mtime_ns=metadata.st_mtime_ns,
    )


def _require_source_identity(root: Path, path: Path, expected: _SourceIdentity) -> None:
    if _source_identity(root, path) != expected:
        raise FinancialResearchError("market database changed during analysis")


def _require_stable_source(root: Path, path: Path, expected: _SourceIdentity) -> None:
    _reject_sqlite_sidecars(path)
    _require_source_identity(root, path, expected)


def _reject_sqlite_sidecars(path: Path) -> None:
    try:
        if any(
            Path(f"{path}{suffix}").exists() or Path(f"{path}{suffix}").is_symlink()
            for suffix in _SQLITE_SIDECAR_SUFFIXES
        ):
            raise FinancialResearchError("market database has an unsafe SQLite sidecar")
    except FinancialResearchError:
        raise
    except OSError as exc:
        raise FinancialResearchError(
            "market database sidecars could not be checked safely"
        ) from exc


def _stream_sha256(path: Path, root: Path, expected: _SourceIdentity) -> str:
    digest = sha256()
    try:
        _require_stable_source(root, path, expected)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_SHA256_CHUNK_SIZE), b""):
                digest.update(chunk)
        _require_stable_source(root, path, expected)
    except OSError as exc:
        raise FinancialResearchError("market database could not be hashed safely") from exc
    return digest.hexdigest()


def _write_immutable(root: Path, relative_path: str, body: bytes) -> None:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or len(relative.parts) != 2 or ".." in relative.parts:
        raise FinancialResearchError("derived output path is unsafe")
    _prepare_derived_root(root)
    path = root.joinpath(*relative.parts)
    if path.parent.parent != root:
        raise FinancialResearchError("derived output path is unsafe")
    try:
        path.parent.mkdir(parents=False, exist_ok=True)
    except OSError as exc:
        raise FinancialResearchError(
            "derived output directory could not be created safely"
        ) from exc
    _require_derived_root(root)
    if (
        _has_reparse_component(path.parent)
        or path.parent.resolve(strict=True).parent != root
        or not path.parent.is_dir()
    ):
        raise FinancialResearchError("derived output path is unsafe")
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            raise FinancialResearchError(
                "immutable derived output already exists with different content"
            )
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        _require_derived_root(root)
        if _has_reparse_component(path.parent) or path.parent.resolve(strict=True).parent != root:
            raise FinancialResearchError("derived output path changed or is unsafe")
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
                raise FinancialResearchError(
                    "immutable derived output already exists with different content"
                )
        _require_derived_root(root)
        if _has_reparse_component(path.parent) or path.parent.resolve(strict=True).parent != root:
            raise FinancialResearchError("derived output path changed or is unsafe")
    finally:
        temporary.unlink(missing_ok=True)


def _assess_coverage(dataset: DerivedDatasetReceipt, validation):
    common = {
        "run_id": dataset.run_id,
        "task_id": dataset.task_id,
        "repository_revision": dataset.repository_revision,
        "created_at": dataset.created_at,
        "event_id": dataset.event_id,
        "non_authority": FINANCIAL_RESEARCH_NON_AUTHORITY,
    }
    if dataset.null_close_count:
        gap = FinancialGapAssessment(
            **common,
            assessment_id=f"{dataset.dataset_id}-gap",
            status=FinancialResearchStatus.NEEDS_ANALYSIS,
            unresolved_gaps=(
                f"Requested coverage contains {dataset.null_close_count} null close rows.",
            ),
            contradiction_state="null-close-values",
            confidence=0.0,
            next_action="stop",
            loop_budget_used=0,
        )
        report = FinancialRecommendation(
            **common,
            recommendation_id=f"{dataset.dataset_id}-recommendation",
            status=FinancialResearchStatus.STOPPED,
            conclusions=("Coverage evidence failed null-close validation.",),
            uncertainty="The requested coverage is incomplete; no accepted conclusion is available.",
            evidence=(validation,),
        )
        return gap, report

    claim = (
        f"Requested coverage contains {dataset.row_count} rows across "
        f"{dataset.ticker_count} tickers from {dataset.coverage_start} "
        f"through {dataset.coverage_end}."
    )
    gap = FinancialGapAssessment(
        **common,
        assessment_id=f"{dataset.dataset_id}-gap",
        status=FinancialResearchStatus.COMPLETE,
        supported_claims=(claim,),
        contradiction_state="none",
        confidence=1.0,
        next_action="stop",
        loop_budget_used=0,
        content_hashes=(validation.sha256,),
        evidence=(validation,),
    )
    report = FinancialRecommendation(
        **common,
        recommendation_id=f"{dataset.dataset_id}-recommendation",
        status=FinancialResearchStatus.COMPLETE,
        conclusions=(claim,),
        uncertainty="Coverage counts do not establish price quality, returns, or model fitness.",
        evidence=(validation,),
    )
    return gap, report
