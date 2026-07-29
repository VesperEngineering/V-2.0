"""Deterministic Phase 1 financial-research intake and planning."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
import tempfile
from collections.abc import Callable
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path

from pydantic import Field
from typing_extensions import Annotated

from vesper.platform.contracts import (
    AnalysisNode,
    DerivedDatasetReceipt,
    EvidenceArtifactRef,
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
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_NON_AUTHORITY = (
    "Research evidence only; no trading, order, capital-allocation, risk, deployment, "
    "scheduler, or model-promotion authority."
)


class CoverageDatasetReceipt(DerivedDatasetReceipt):
    """Phase 1 aggregate counts attached to the generic derived-data receipt."""

    row_count: Annotated[int, Field(ge=0)]
    ticker_count: Annotated[int, Field(ge=0)]
    null_close_count: Annotated[int, Field(ge=0)]


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
            FinancialResearchStatus.REQUESTED if triggered else FinancialResearchStatus.STOPPED
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

    start, end = sorted(
        (event.occurred_at.date().isoformat(), event.observed_at.date().isoformat())
    )
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
        time_window_start=start,
        time_window_end=end,
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
        self.derived_root = _validate_derived_root(Path(derived_root), self.massive_root)
        self.evidence = evidence
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
        if not _is_safe_source_file(self.massive_root, database):
            raise FinancialResearchError("market database is missing or unsafe")
        source_sha256 = _stream_sha256(database)
        aggregate = self._coverage_aggregate(
            database,
            request.symbols,
            request.time_window_start,
            request.time_window_end,
        )
        if _stream_sha256(database) != source_sha256:
            raise FinancialResearchError("market database changed during analysis")

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
        _write_immutable(self.derived_root, relative_output, body)
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
        dataset = CoverageDatasetReceipt(
            run_id=event.run_id,
            task_id=event.task_id,
            repository_revision=event.repository_revision,
            created_at=event.created_at,
            event_id=event.event_id,
            non_authority=_NON_AUTHORITY,
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
    ) -> tuple[int, int, str | None, str | None, int]:
        placeholders = ", ".join("?" for _ in symbols)
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{database.resolve(strict=True).as_uri()}?mode=ro&immutable=1",
                uri=True,
            )
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            columns = {
                str(row[1]).casefold()
                for row in connection.execute(f'PRAGMA table_info("{_TABLE_NAME}")')
            }
            if not _REQUIRED_COLUMNS.issubset(columns):
                raise FinancialResearchError("market database schema is missing required columns")
            result = connection.execute(
                f'''SELECT COUNT(*), COUNT(DISTINCT ticker),
                           MIN(substr(date, 1, 10)), MAX(substr(date, 1, 10)),
                           SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END),
                           SUM(CASE
                                 WHEN typeof(date) <> 'text' THEN 1
                                 WHEN length(CAST(date AS BLOB)) <> 10 THEN 1
                                 WHEN date(date) IS NULL OR date(date) <> date THEN 1
                                 ELSE 0
                               END)
                    FROM "{_TABLE_NAME}"
                    WHERE ticker IN ({placeholders}) AND date >= ? AND date <= ?''',
                (*symbols, start, end),
            ).fetchone()
        except FinancialResearchError:
            raise
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            raise FinancialResearchError("market database could not be queried safely") from exc
        finally:
            if connection is not None:
                connection.close()
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
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8") + b"\n"


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


def _validate_derived_root(configured: Path, massive_root: Path) -> Path:
    if _has_reparse_component(configured):
        raise FinancialResearchError("derived root must not traverse a symlink or reparse point")
    resolved = configured.resolve()
    repository = Path(__file__).resolve().parents[2]
    protected = (
        repository,
        repository / "vesper" / "data" / "massive",
        repository / "vesper" / "data" / "model_research",
        massive_root.resolve(),
    )
    if any(resolved == root.resolve() or resolved.is_relative_to(root.resolve()) for root in protected):
        raise FinancialResearchError("derived root must be outside the repository and protected data")
    return resolved


def _stream_sha256(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_SHA256_CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError as exc:
        raise FinancialResearchError("market database could not be hashed safely") from exc
    return digest.hexdigest()


def _write_immutable(root: Path, relative_path: str, body: bytes) -> None:
    path = root.joinpath(*relative_path.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    if _has_reparse_component(path.parent) or not path.parent.resolve().is_relative_to(root):
        raise FinancialResearchError("derived output path is unsafe")
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            raise FinancialResearchError("immutable derived output already exists with different content")
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
                raise FinancialResearchError(
                    "immutable derived output already exists with different content"
                )
    finally:
        temporary.unlink(missing_ok=True)


def _assess_coverage(dataset: CoverageDatasetReceipt, validation):
    common = {
        "run_id": dataset.run_id,
        "task_id": dataset.task_id,
        "repository_revision": dataset.repository_revision,
        "created_at": dataset.created_at,
        "event_id": dataset.event_id,
        "non_authority": _NON_AUTHORITY,
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
