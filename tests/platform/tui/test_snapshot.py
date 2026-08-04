from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from vesper.platform.tui.contracts import MessageType, SnapshotPayload, WireEnvelope
from vesper.platform.tui.ports import (
    AgentFacts,
    ConfiguredAgentFact,
    DataFacts,
    LegacyPositionFact,
    MemoryFacts,
    ModelFacts,
    OrderFacts,
    PortfolioFacts,
    RiskFacts,
    SourceSample,
    SystemFacts,
    TimelineFacts,
)
from vesper.platform.tui.protocol import encode_frame
from vesper.platform.tui.snapshot import (
    ControlStateBuilder,
    SnapshotBuilder,
    diff_snapshots,
    requires_full_snapshot,
)
from vesper.platform.tui.views import (
    AccountSummaryView,
    AgentCard,
    CandidateRow,
    EvidenceRow,
    Freshness,
    MemoryRow,
    MetricRow,
    ModelOpinionRow,
    OrderRow,
    PortfolioRow,
    RepositoryRow,
    ServiceRow,
    SourceRow,
    TimelineRow,
    TransitionPlanView,
)


NOW = datetime(2026, 8, 3, 16, 0, tzinfo=timezone.utc)
SHA = "a" * 40
SHA256 = "a" * 64


def _sample(
    value: object,
    *,
    source: str,
    freshness: Freshness = Freshness.FRESH,
    error: str | None = None,
    observed_at: datetime = NOW,
) -> SourceSample[object]:
    return SourceSample[object](
        value=value,
        freshness=freshness,
        observed_at_utc=observed_at,
        source=source,
        error=error,
    )


def _unavailable(source: str, reason: str) -> SourceSample[object]:
    return SourceSample[object](
        value=None,
        freshness=Freshness.UNAVAILABLE,
        observed_at_utc=None,
        source=source,
        error=reason,
    )


def _metric(metric_id: str, value: float, *, observed_at: datetime = NOW) -> MetricRow:
    return MetricRow(
        metric_id=metric_id,
        value=value,
        unit="percent",
        freshness=Freshness.FRESH,
        observed_at_utc=observed_at,
        error=None,
    )


def _repository(*, clean: bool = True) -> RepositoryRow:
    return RepositoryRow(
        repository_id="repository:v20",
        freshness=Freshness.FRESH,
        as_of_utc=NOW,
        source="git",
        error=None,
        branch="codex/vesper/ratatui-console",
        revision=SHA,
        clean=clean,
        worktrees=("C:/Users/bgonn/Desktop/v20",),
        unpushed_commit_count=0,
    )


def _service(state: str = "running") -> ServiceRow:
    return ServiceRow(
        service_id="service:qwen",
        state=state,
        health_reason=None,
        observed_at_utc=NOW,
    )


def _system_samples(*, metric_value: float = 12.5) -> dict[str, SourceSample[object]]:
    repository = SystemFacts(
        services=None,
        services_error="Repository projection does not provide services.",
        metrics=None,
        metrics_error="Repository projection does not provide metrics.",
        repositories=(_repository(),),
        repositories_error=None,
    )
    windows = SystemFacts(
        services=(_service(),),
        services_error=None,
        metrics=(_metric("system.cpu.percent", metric_value),),
        metrics_error=None,
        repositories=None,
        repositories_error="Windows projection does not provide repositories.",
    )
    return {
        "repository.system": _sample(repository, source="git"),
        "windows.system": _sample(windows, source="windows"),
    }


def _risk_sample(
    *,
    breaker: bool = False,
    daily_pnl: float = -25.5,
    starting_equity: float = 10_000.0,
    peak_equity: float = 10_100.0,
    current_price: str | None = None,
) -> SourceSample[object]:
    positions = (
        (
            LegacyPositionFact(
                symbol="AAPL",
                quantity="10",
                entry_price="100",
                current_price=current_price,
            ),
        )
        if current_price is not None
        else ()
    )
    facts = RiskFacts(
        session_date=None,
        daily_pnl=daily_pnl,
        starting_equity=starting_equity,
        peak_equity=peak_equity,
        breaker_tripped=breaker,
        positions=(),
        broker_reconciled=False,
    )
    return _sample(facts, source="legacy saved engine state")


def _holding(
    symbol: str,
    *,
    price: str,
    weight: float,
    rank: int | None = None,
) -> PortfolioRow:
    return PortfolioRow(
        symbol=symbol,
        description=None,
        asset_type="stock",
        quantity="10",
        price=price,
        market_value="1000",
        current_weight=weight,
        proposed_weight=None,
        approved_weight=None,
        change_state="unchanged",
        confirmed_rank=rank,
        reconciliation="matched" if rank is not None else "unavailable",
    )


def _portfolio_sample(
    rows: tuple[PortfolioRow, ...],
    *,
    rank_source: str | None = None,
) -> SourceSample[object]:
    return _sample(
        PortfolioFacts(rows=rows, rank_source=rank_source),
        source="native portfolio",
    )


def _agent_sample(*, model: str | None) -> SourceSample[object]:
    return _sample(
        AgentFacts(
            configured_roster=(
                ConfiguredAgentFact(
                    agent_id="v20-model-researcher",
                    purpose="Research approved V20 model work.",
                    model="qwen:64k",
                    skills=(),
                ),
            ),
            active_work=(
                AgentCard(
                    work_id="work:1",
                    agent="v20-model-researcher",
                    title="Inspect one bounded task.",
                    stage="running",
                    priority=50,
                    urgent=False,
                    elapsed_seconds=1.0,
                    model=model,
                    affected_areas=("models",),
                ),
            ),
            active_work_error=None,
        ),
        source="native agent profiles",
    )


def _event(index: int, *, impact: bool = False, symbol: str | None = None) -> TimelineRow:
    return TimelineRow(
        event_id=f"event:{index}",
        occurred_at_utc=NOW + timedelta(seconds=index),
        impact=impact,
        severity="active",
        summary=f"Bounded timeline event {index} " + ("x" * 300),
        agent_id=None,
        symbol=symbol,
        model_id=None,
        approval_id=None,
        order_id=None,
        evidence_ids=(),
    )


def _timeline_sample(rows: tuple[TimelineRow, ...]) -> SourceSample[object]:
    return _sample(
        TimelineFacts(
            rows=rows,
            hidden_event_count=3,
            hidden_impact_event_count=2,
            last_sequence=100,
        ),
        source="tui event ledger",
    )


def _order(order_id: str) -> OrderRow:
    return OrderRow(
        order_id=order_id,
        symbol="AAPL",
        side="buy",
        quantity="1",
        status="proposed",
        submitted_at_utc=None,
        broker_order_id=None,
        fills=(),
        expected_price=None,
        actual_price=None,
        reconciliation="unavailable",
    )


def _opinion(model_id: str, *, as_of: datetime = NOW) -> ModelOpinionRow:
    return ModelOpinionRow(
        model_id=model_id,
        regime="risk-on",
        confidence=0.8,
        as_of_utc=as_of,
    )


def _candidate(candidate_id: str) -> CandidateRow:
    return CandidateRow(
        candidate_id=candidate_id,
        family="approved-family",
        strategy="ml_model",
        status="evaluating",
        evidence_ids=(),
        created_at_utc=NOW,
    )


def _evidence(evidence_id: str) -> EvidenceRow:
    return EvidenceRow(
        evidence_id=evidence_id,
        evidence_type="receipt",
        source="test",
        created_at_utc=NOW,
        sha256=SHA256,
    )


def _source(source_id: str) -> SourceRow:
    return SourceRow(
        source_id=source_id,
        freshness=Freshness.FRESH,
        as_of_utc=NOW,
        age_seconds=0.0,
        coverage="S&P 500",
        error=None,
        consumers=("ml_model",),
    )


def _memory(memory_id: str) -> MemoryRow:
    return MemoryRow(
        memory_id=memory_id,
        status="core",
        summary="Keep controller truth.",
        evidence_ids=(),
        updated_at_utc=NOW,
    )


def _model_facts(
    *,
    opinions: tuple[ModelOpinionRow, ...] = (),
    candidates: tuple[CandidateRow, ...] = (),
    evidence: tuple[EvidenceRow, ...] = (),
) -> ModelFacts:
    return ModelFacts(
        configured_strategy="ml_model",
        configured_model_id="model:active",
        opinions=opinions,
        candidates=candidates,
        evidence=evidence,
    )


def _stale(
    sample: SourceSample[object], reason: str = "Source read failed."
) -> SourceSample[object]:
    return SourceSample[object](
        value=sample.value,
        freshness=Freshness.STALE,
        observed_at_utc=sample.observed_at_utc,
        source=sample.source,
        error=reason,
    )


def _build(
    samples: dict[str, SourceSample[object]],
    *,
    previous=None,
    generated_at: datetime = NOW,
    max_frame_bytes: int | None = None,
):
    builder = (
        SnapshotBuilder()
        if max_frame_bytes is None
        else SnapshotBuilder(max_frame_bytes=max_frame_bytes)
    )
    return builder.build(
        samples=samples,
        generated_at_utc=generated_at,
        previous=previous,
    )


def test_snapshot_maps_system_and_legacy_risk_without_inventing_other_truth() -> None:
    snapshot = _build({**_system_samples(), "legacy.risk": _risk_sample()})

    assert snapshot.system.freshness is Freshness.FRESH
    assert tuple(row.service_id for row in snapshot.system.services) == ("service:qwen",)
    assert tuple(row.metric_id for row in snapshot.system.metrics) == ("system.cpu.percent",)
    assert tuple(row.repository_id for row in snapshot.system.repositories) == ("repository:v20",)
    assert snapshot.system.source == "git + windows"

    assert snapshot.risk.freshness is Freshness.STALE
    assert "not broker-reconciled" in (snapshot.risk.error or "")
    assert [(row.limit_id, row.current_value, row.status) for row in snapshot.risk.limits] == [
        ("risk.breaker", "0", "within"),
        ("risk.broker-reconciled", "0", "unavailable"),
    ]
    assert [(row.metric_id, row.value) for row in snapshot.risk.metrics] == [
        ("risk.daily-pnl", -25.5),
        ("risk.starting-equity", 10_000.0),
        ("risk.peak-equity", 10_100.0),
        ("risk.legacy-position-count", 0.0),
    ]

    for view in (
        snapshot.impact,
        snapshot.portfolio,
        snapshot.orders,
        snapshot.agents,
        snapshot.models,
        snapshot.timeline,
        snapshot.data,
        snapshot.memory,
    ):
        assert view.freshness is Freshness.UNAVAILABLE
        assert view.error
    assert snapshot.portfolio.rows == ()
    assert snapshot.shell.header.operating_mode.value == "unknown"
    assert snapshot.shell.header.operating_mode_freshness is Freshness.UNAVAILABLE
    assert snapshot.shell.header.agent_queue_length is None
    assert snapshot.shell.alerts is None
    assert snapshot.command_specs == ()


def test_system_merge_is_order_independent_and_conflicts_fail_closed() -> None:
    samples = _system_samples()
    forward = _build(samples)
    reverse = _build(dict(reversed(tuple(samples.items()))))
    assert forward.system == reverse.system

    conflicting = SystemFacts(
        services=(_service("stopped"),),
        services_error=None,
        metrics=None,
        metrics_error="No metrics.",
        repositories=(_repository(),),
        repositories_error=None,
    )
    failed = _build(
        {
            "repository.system": _sample(conflicting, source="conflicting source"),
            "windows.system": samples["windows.system"],
        }
    )
    assert failed.system.freshness is Freshness.UNAVAILABLE
    assert failed.system.services == ()
    assert failed.system.metrics == ()
    assert failed.system.repositories == ()
    assert "conflict" in (failed.system.error or "").lower()


def test_system_merge_bounds_combined_source_labels() -> None:
    samples = _system_samples()
    long_repository_source = "r" * 512
    long_windows_source = "w" * 512
    snapshot = _build(
        {
            "repository.system": samples["repository.system"].model_copy(
                update={"source": long_repository_source}
            ),
            "windows.system": samples["windows.system"].model_copy(
                update={"source": long_windows_source}
            ),
        }
    )

    assert snapshot.system.source == "repository.system + windows.system"


def test_builder_rejects_unknown_source_keys_instead_of_ignoring_wiring_errors() -> None:
    with pytest.raises(ValueError, match="Unknown projection source"):
        _build({"windwos.system": _unavailable("typo", "Unavailable.")})


def test_portfolio_order_is_stable_until_a_confirmed_rank_arrives() -> None:
    first = _build(
        {
            "native.portfolio": _portfolio_sample(
                (
                    _holding("MSFT", price="100", weight=0.4),
                    _holding("AAPL", price="100", weight=0.6),
                )
            )
        }
    )
    assert [row.symbol for row in first.portfolio.rows] == ["AAPL", "MSFT"]
    assert first.portfolio.rank_source is None

    second = _build(
        {
            "native.portfolio": _portfolio_sample(
                (
                    _holding("NVDA", price="200", weight=0.1),
                    _holding("MSFT", price="90", weight=0.35),
                    _holding("AAPL", price="150", weight=0.55),
                )
            )
        },
        previous=first,
        generated_at=NOW + timedelta(seconds=1),
    )
    assert [row.symbol for row in second.portfolio.rows] == ["AAPL", "MSFT", "NVDA"]
    assert second.portfolio.rank_source is None

    confirmed = _build(
        {
            "native.portfolio": _portfolio_sample(
                (
                    _holding("AAPL", price="150", weight=0.45, rank=2),
                    _holding("NVDA", price="200", weight=0.55, rank=1),
                ),
                rank_source="broker-confirmed executed weights",
            )
        },
        previous=second,
        generated_at=NOW + timedelta(seconds=2),
    )
    assert [row.symbol for row in confirmed.portfolio.rows] == ["NVDA", "AAPL"]
    assert confirmed.portfolio.rank_source == "broker-confirmed executed weights"


def test_duplicate_portfolio_identity_fails_the_view_closed() -> None:
    duplicate = _holding("AAPL", price="100", weight=0.5)
    snapshot = _build({"native.portfolio": _portfolio_sample((duplicate, duplicate))})

    assert snapshot.portfolio.freshness is Freshness.UNAVAILABLE
    assert snapshot.portfolio.rows == ()
    assert "duplicate" in (snapshot.portfolio.error or "").lower()


def test_partial_or_unreconciled_rank_never_reorders_confirmed_holdings() -> None:
    first = _build(
        {
            "native.portfolio": _portfolio_sample(
                (
                    _holding("AAPL", price="100", weight=0.6),
                    _holding("MSFT", price="100", weight=0.4),
                )
            )
        }
    )
    partial = _build(
        {
            "native.portfolio": _portfolio_sample(
                (
                    _holding("NVDA", price="100", weight=0.2, rank=1),
                    _holding("MSFT", price="100", weight=0.3),
                    _holding("AAPL", price="100", weight=0.5, rank=2),
                ),
                rank_source="incomplete proposed ranks",
            )
        },
        previous=first,
        generated_at=NOW + timedelta(seconds=1),
    )

    assert [row.symbol for row in partial.portfolio.rows] == ["AAPL", "MSFT", "NVDA"]
    assert partial.portfolio.rank_source is None

    cash = _holding("CASH", price="1", weight=0.2, rank=1).model_copy(
        update={"asset_type": "cash", "reconciliation": "not-required"}
    )
    confirmed_with_cash = _build(
        {
            "native.portfolio": _portfolio_sample(
                (
                    _holding("AAPL", price="100", weight=0.8, rank=2),
                    cash,
                ),
                rank_source="confirmed executed ranks",
            )
        },
        previous=first,
        generated_at=NOW + timedelta(seconds=2),
    )
    assert [row.symbol for row in confirmed_with_cash.portfolio.rows] == ["CASH", "AAPL"]
    assert confirmed_with_cash.portfolio.rank_source == "confirmed executed ranks"


def test_qwen_status_requires_an_explicit_qwen_running_card() -> None:
    unknown_model = _build({"native.agents": _agent_sample(model=None)})
    explicit_qwen = _build(
        {"native.agents": _agent_sample(model="qwen:64k")},
        previous=unknown_model,
        generated_at=NOW + timedelta(seconds=1),
    )

    assert unknown_model.shell.header.active_agent == "v20-model-researcher"
    assert unknown_model.shell.header.qwen_state == "Configured"
    assert explicit_qwen.shell.header.qwen_state == "Running"


def test_model_linked_timeline_events_are_not_relabelled_as_memory_history() -> None:
    row = _event(1).model_copy(update={"model_id": "model:active"})
    snapshot = _build({"events.timeline": _timeline_sample((row,))})

    assert snapshot.timeline.rows == (row,)
    assert snapshot.memory.history == ()


def test_duplicate_timeline_identity_fails_the_affected_views_closed() -> None:
    row = _event(1, impact=True, symbol="AAPL")
    snapshot = _build({"events.timeline": _timeline_sample((row, row))})

    assert snapshot.timeline.freshness is Freshness.UNAVAILABLE
    assert snapshot.timeline.rows == ()
    assert snapshot.impact.freshness is Freshness.UNAVAILABLE
    assert "duplicate" in (snapshot.timeline.error or "").lower()


@pytest.mark.parametrize(
    ("source_id", "facts", "view_name", "row_fields"),
    (
        (
            "native.orders",
            OrderFacts(rows=(_order("order:1"), _order("order:1"))),
            "orders",
            ("rows",),
        ),
        (
            "native.agents",
            AgentFacts(
                configured_roster=(),
                active_work=(
                    _agent_sample(model="qwen:64k").value.active_work[0],
                    _agent_sample(model="qwen:64k").value.active_work[0],
                ),
                active_work_error=None,
            ),
            "agents",
            ("rows",),
        ),
        (
            "native.models",
            _model_facts(opinions=(_opinion("model:1"), _opinion("model:1"))),
            "models",
            ("opinions", "candidates", "evidence"),
        ),
        (
            "native.models",
            _model_facts(candidates=(_candidate("candidate:1"), _candidate("candidate:1"))),
            "models",
            ("opinions", "candidates", "evidence"),
        ),
        (
            "native.models",
            _model_facts(evidence=(_evidence("evidence:1"), _evidence("evidence:1"))),
            "models",
            ("opinions", "candidates", "evidence"),
        ),
        (
            "native.data",
            DataFacts(
                sources=(_source("source:1"), _source("source:1")),
                evidence=(),
            ),
            "data",
            ("sources", "evidence"),
        ),
        (
            "native.data",
            DataFacts(
                sources=(),
                evidence=(_evidence("evidence:1"), _evidence("evidence:1")),
            ),
            "data",
            ("sources", "evidence"),
        ),
        (
            "native.memory",
            MemoryFacts(rows=(_memory("memory:1"), _memory("memory:1"))),
            "memory",
            ("rows",),
        ),
    ),
)
def test_duplicate_indexed_source_id_fails_its_view_closed(
    source_id: str,
    facts: object,
    view_name: str,
    row_fields: tuple[str, ...],
) -> None:
    snapshot = _build({source_id: _sample(facts, source="duplicate fixture")})
    view = getattr(snapshot, view_name)

    assert view.freshness is Freshness.UNAVAILABLE
    assert "duplicate" in (view.error or "").lower()
    assert all(getattr(view, field) == () for field in row_fields)


def test_rejected_duplicate_facts_do_not_leak_into_the_header() -> None:
    agent = _agent_sample(model="qwen:64k").value.active_work[0]
    snapshot = _build(
        {
            "native.agents": _sample(
                AgentFacts(
                    configured_roster=_agent_sample(model="qwen:64k").value.configured_roster,
                    active_work=(agent, agent),
                    active_work_error=None,
                ),
                source="duplicate agents",
            ),
            "native.data": _sample(
                DataFacts(sources=(_source("source:1"), _source("source:1")), evidence=()),
                source="duplicate data",
            ),
        }
    )

    header = snapshot.shell.header
    assert header.data_freshness is Freshness.UNAVAILABLE
    assert header.data_age_seconds is None
    assert header.active_agent is None
    assert header.agent_queue_length is None
    assert header.qwen_state == "Unavailable"


def test_stale_samples_do_not_leak_unmarked_facts_into_the_header() -> None:
    snapshot = _build(
        {
            "native.portfolio": _stale(
                _portfolio_sample((_holding("AAPL", price="100", weight=1.0),))
            ),
            "native.agents": _stale(_agent_sample(model="qwen:64k")),
            "native.models": _stale(
                _sample(
                    _model_facts(opinions=(_opinion("model:active"),)),
                    source="native models",
                )
            ),
        }
    )

    header = snapshot.shell.header
    assert header.portfolio_value is None
    assert header.regime_label == "Unavailable"
    assert header.regime_confidence is None
    assert header.active_agent is None
    assert header.agent_queue_length is None
    assert header.qwen_state == "Unavailable"


def test_model_opinions_do_not_invent_a_controller_final_regime() -> None:
    snapshot = _build(
        {
            "native.models": _sample(
                _model_facts(
                    opinions=(
                        _opinion("model:one"),
                        _opinion("model:two"),
                    )
                ),
                source="native models",
            )
        }
    )

    assert len(snapshot.models.opinions) == 2
    assert snapshot.shell.header.regime_label == "Unavailable"
    assert snapshot.shell.header.regime_confidence is None


def test_state_and_control_versions_change_for_their_separate_inputs() -> None:
    first = _build(
        {
            **_system_samples(metric_value=10.0),
            "native.portfolio": _portfolio_sample((_holding("AAPL", price="100", weight=1.0),)),
        }
    )
    identical = _build(
        {
            **_system_samples(metric_value=10.0),
            "native.portfolio": _portfolio_sample((_holding("AAPL", price="100", weight=1.0),)),
        },
        previous=first,
    )
    assert identical.shell.state_version == first.shell.state_version == 0
    assert identical.control_version == first.control_version == 0
    assert identical.control_hash == first.control_hash

    metrics_and_clock = _build(
        {
            **_system_samples(metric_value=20.0),
            "native.portfolio": _portfolio_sample((_holding("AAPL", price="110", weight=1.0),)),
        },
        previous=identical,
        generated_at=NOW + timedelta(seconds=1),
    )
    assert metrics_and_clock.shell.state_version == 1
    assert metrics_and_clock.control_version == 0
    assert metrics_and_clock.control_hash == first.control_hash

    authority_change = _build(
        {
            **_system_samples(metric_value=20.0),
            "native.portfolio": _portfolio_sample((_holding("AAPL", price="110", weight=0.9),)),
        },
        previous=metrics_and_clock,
        generated_at=NOW + timedelta(seconds=2),
    )
    assert authority_change.shell.state_version == 2
    assert authority_change.control_version == 1
    assert authority_change.control_hash != first.control_hash


def test_control_pair_ignores_legacy_risk_metrics_but_tracks_breaker_state() -> None:
    builder = ControlStateBuilder()
    first = builder.build({"legacy.risk": _risk_sample(current_price="101")})
    metrics_only = builder.build(
        {
            "legacy.risk": _risk_sample(
                daily_pnl=-500.0,
                starting_equity=9_500.0,
                peak_equity=10_500.0,
                current_price="125",
            )
        },
        previous=first,
    )
    breaker = builder.build(
        {"legacy.risk": _risk_sample(breaker=True, current_price="125")},
        previous=metrics_only,
    )

    assert metrics_only == first
    assert breaker.version == first.version + 1
    assert breaker.hash != first.hash


def test_control_hash_is_canonical_across_mapping_order() -> None:
    samples = {**_system_samples(), "legacy.risk": _risk_sample()}
    builder = ControlStateBuilder()
    forward = builder.build(samples)
    reverse = builder.build(dict(reversed(tuple(samples.items()))))
    assert forward == reverse

    first_rows = (
        _holding("MSFT", price="100", weight=0.4),
        _holding("AAPL", price="100", weight=0.6),
    )
    reverse_rows = tuple(reversed(first_rows))
    ordered = builder.build({"native.portfolio": _portfolio_sample(first_rows)})
    reordered = builder.build({"native.portfolio": _portfolio_sample(reverse_rows)})
    assert ordered == reordered


def test_control_pair_tracks_freshness_but_not_error_text_or_entity_order() -> None:
    builder = ControlStateBuilder()
    portfolio = _portfolio_sample((_holding("AAPL", price="100", weight=1.0),))
    fresh = builder.build({"native.portfolio": portfolio})
    stale = builder.build(
        {"native.portfolio": _stale(portfolio, "first safe reason")},
        previous=fresh,
    )
    stale_new_text = builder.build(
        {"native.portfolio": _stale(portfolio, "different safe reason")},
        previous=stale,
    )
    assert stale.hash != fresh.hash
    assert stale.version == 1
    assert stale_new_text == stale

    orders = (_order("order:2"), _order("order:1"))
    ordered_orders = builder.build(
        {"native.orders": _sample(OrderFacts(rows=orders), source="native orders")}
    )
    reversed_orders = builder.build(
        {
            "native.orders": _sample(
                OrderFacts(rows=tuple(reversed(orders))),
                source="native orders",
            )
        }
    )
    assert ordered_orders == reversed_orders

    models = _model_facts(
        opinions=(_opinion("model:2"), _opinion("model:1")),
        candidates=(_candidate("candidate:2"), _candidate("candidate:1")),
        evidence=(_evidence("evidence:2"), _evidence("evidence:1")),
    )
    reversed_models = _model_facts(
        opinions=tuple(reversed(models.opinions)),
        candidates=tuple(reversed(models.candidates)),
        evidence=tuple(reversed(models.evidence)),
    )
    assert builder.build(
        {"native.models": _sample(models, source="native models")}
    ) == builder.build({"native.models": _sample(reversed_models, source="native models")})

    later_opinion = _model_facts(opinions=(_opinion("model:1", as_of=NOW + timedelta(seconds=1)),))
    earlier_opinion = _model_facts(opinions=(_opinion("model:1"),))
    assert builder.build(
        {"native.models": _sample(later_opinion, source="native models")}
    ) == builder.build({"native.models": _sample(earlier_opinion, source="native models")})


def test_timeline_windows_are_bounded_and_report_all_known_omissions() -> None:
    rows = tuple(_event(index, impact=index % 2 == 0, symbol="AAPL") for index in range(200))
    snapshot = _build(
        {"events.timeline": _timeline_sample(rows)},
        max_frame_bytes=32_000,
    )

    envelope = WireEnvelope(
        schema_version=1,
        message_id="snapshot:1",
        sequence=1,
        state_version=snapshot.shell.state_version,
        timestamp_utc=NOW,
        message_type=MessageType.SNAPSHOT,
        payload=SnapshotPayload(snapshot=snapshot).model_dump(mode="json"),
    )
    encoded_size = len(encode_frame(envelope)) - 4
    assert encoded_size <= 32_000
    omissions = {row.target: row.omitted_count for row in snapshot.window_omissions}
    assert omissions["timeline.rows"] == 3 + (200 - len(snapshot.timeline.rows))
    assert omissions["impact.events"] == 2 + (100 - len(snapshot.impact.events))
    assert snapshot.timeline.hidden_event_count == omissions["timeline.rows"]
    assert all(row.impact for row in snapshot.impact.events)
    assert snapshot.timeline.rows[-1].event_id == "event:199"


def test_snapshot_diff_emits_canonical_upserts_and_removals() -> None:
    first = _build(
        {
            "native.portfolio": _portfolio_sample(
                (
                    _holding("AAPL", price="100", weight=0.6),
                    _holding("MSFT", price="100", weight=0.4),
                )
            )
        }
    )
    second = _build(
        {
            "native.portfolio": _portfolio_sample(
                (
                    _holding("AAPL", price="105", weight=0.7),
                    _holding("NVDA", price="100", weight=0.3),
                )
            )
        },
        previous=first,
        generated_at=NOW + timedelta(seconds=1),
    )

    events = diff_snapshots(first, second)
    assert [
        (event.entity_type, event.entity_id, event.operation, event.targets) for event in events
    ] == [
        ("portfolio-row", "AAPL", "upsert", ("portfolio.rows",)),
        ("portfolio-row", "MSFT", "remove", ("portfolio.rows",)),
        ("portfolio-row", "NVDA", "upsert", ("portfolio.rows",)),
    ]
    assert events[0].entity == second.portfolio.rows[0]
    assert events[1].entity is None
    presentation = events[0].presentation
    assert presentation.control_hash == second.control_hash
    assert presentation.portfolio_rank_source is None
    assert json.loads(presentation.model_dump_json())["generated_at_utc"].endswith("Z")

    duplicate_view = first.portfolio.model_copy(
        update={"rows": (first.portfolio.rows[0], first.portfolio.rows[0])}
    )
    duplicate_snapshot = first.model_copy(update={"portfolio": duplicate_view})
    with pytest.raises(ValueError, match="Duplicate entity ID"):
        diff_snapshots(first, duplicate_snapshot)


@pytest.mark.parametrize("live_field", ["live_readiness", "live_account", "live_transition_plan"])
def test_live_field_changes_require_a_full_snapshot(live_field: str) -> None:
    first = _build({})
    if live_field == "live_readiness":
        readiness = first.system.live_readiness.model_copy(
            update={
                "broker": first.system.live_readiness.broker.model_copy(
                    update={"reason": "New reviewed broker readiness evidence."}
                )
            }
        )
        value = readiness
    elif live_field == "live_account":
        value = AccountSummaryView(
            name="Primary brokerage",
            number="123456789",
            balance="1000",
            capital="900",
        )
    else:
        value = TransitionPlanView(
            broker_positions_as_of_utc=NOW,
            desired_portfolio_id="portfolio:candidate",
            orders=(),
        )
    current = first.model_copy(
        update={"system": first.system.model_copy(update={live_field: value})}
    )

    assert requires_full_snapshot(first, current) is True


def test_snapshot_diff_coalesces_identical_entity_changes_across_targets() -> None:
    timeline = _timeline_sample((_event(1, impact=True, symbol="AAPL"),))
    first = _build(
        {
            "native.portfolio": _portfolio_sample((_holding("AAPL", price="100", weight=1.0),)),
            "events.timeline": timeline,
        }
    )
    second = _build(
        {
            "native.portfolio": _portfolio_sample((_holding("AAPL", price="105", weight=1.0),)),
            "events.timeline": timeline,
        },
        previous=first,
        generated_at=NOW + timedelta(seconds=1),
    )

    portfolio_events = [
        event
        for event in diff_snapshots(first, second)
        if event.entity_type == "portfolio-row" and event.entity_id == "AAPL"
    ]
    assert len(portfolio_events) == 1
    assert portfolio_events[0].targets == ("impact.holdings", "portfolio.rows")
