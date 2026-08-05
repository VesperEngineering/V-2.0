from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from vesper.platform.tui.ports import (
    AgentFacts,
    AgentReadPort,
    ConfiguredAgentFact,
    RiskFacts,
    SourceSample,
    SystemFacts,
    TimelineFacts,
    UnavailablePort,
)
from vesper.platform.tui.views import CircuitBreakerView, Freshness


NOW = datetime(2026, 8, 3, 16, 0, tzinfo=timezone.utc)


def test_source_sample_enforces_the_exact_freshness_truth_table() -> None:
    fresh = SourceSample[int](
        value=1,
        freshness=Freshness.FRESH,
        observed_at_utc=NOW,
        source="test",
        error=None,
    )
    stale = SourceSample[int](
        value=1,
        freshness=Freshness.STALE,
        observed_at_utc=NOW,
        source="test",
        error="Source is old.",
    )
    unavailable = SourceSample[int](
        value=None,
        freshness=Freshness.UNAVAILABLE,
        observed_at_utc=None,
        source="test",
        error="Source is missing.",
    )
    loading = SourceSample[int](
        value=None,
        freshness=Freshness.LOADING,
        observed_at_utc=None,
        source="test",
        error=None,
    )

    assert (fresh.value, stale.error, unavailable.value, loading.error) == (
        1,
        "Source is old.",
        None,
        None,
    )

    invalid = (
        (Freshness.FRESH, None, NOW, None),
        (Freshness.FRESH, 1, None, None),
        (Freshness.FRESH, 1, NOW, "error"),
        (Freshness.STALE, 1, NOW, None),
        (Freshness.UNAVAILABLE, 1, None, "error"),
        (Freshness.UNAVAILABLE, None, NOW, "error"),
        (Freshness.LOADING, 1, None, None),
        (Freshness.LOADING, None, NOW, None),
        (Freshness.LOADING, None, None, "error"),
    )
    for freshness, value, observed_at, error in invalid:
        with pytest.raises(ValidationError):
            SourceSample[int](
                value=value,
                freshness=freshness,
                observed_at_utc=observed_at,
                source="test",
                error=error,
            )


def test_source_sample_is_strict_closed_and_requires_canonical_utc() -> None:
    with pytest.raises(ValidationError):
        SourceSample[int].model_validate(
            {
                "value": "1",
                "freshness": Freshness.FRESH,
                "observed_at_utc": NOW,
                "source": "test",
                "error": None,
            }
        )
    with pytest.raises(ValidationError):
        SourceSample[int].model_validate(
            {
                "value": 1,
                "freshness": Freshness.FRESH,
                "observed_at_utc": "2026-08-03T12:00:00-04:00",
                "source": "test",
                "error": None,
            }
        )
    with pytest.raises(ValidationError):
        SourceSample[int].model_validate(
            {
                "value": 1,
                "freshness": Freshness.FRESH,
                "observed_at_utc": NOW,
                "source": "test",
                "error": None,
                "unknown": True,
            }
        )


def test_unavailable_port_returns_one_exact_explicit_sample() -> None:
    port: UnavailablePort[AgentFacts] = UnavailablePort(
        "No controller-owned agent work feed is configured.",
        "agent-work",
    )

    assert isinstance(port, AgentReadPort)
    assert port.read() == SourceSample[AgentFacts](
        value=None,
        freshness=Freshness.UNAVAILABLE,
        observed_at_utc=None,
        source="agent-work",
        error="No controller-owned agent work feed is configured.",
    )
    with pytest.raises(ValidationError):
        UnavailablePort("   ")


def test_fact_bundles_distinguish_unavailable_from_observed_empty() -> None:
    profile = ConfiguredAgentFact(
        agent_id="v20-model-researcher",
        purpose="Research bounded model candidates.",
        model="qwen:64k",
        skills=(),
    )
    facts = AgentFacts(
        configured_roster=(profile,),
        active_work=None,
        active_work_error="No read-only work feed is configured.",
    )
    empty = AgentFacts(
        configured_roster=(profile,),
        active_work=(),
        active_work_error=None,
    )
    assert facts.active_work is None
    assert empty.active_work == ()

    for active_work, reason in ((None, None), ((), "wrong")):
        with pytest.raises(ValidationError):
            AgentFacts(
                configured_roster=(profile,),
                active_work=active_work,
                active_work_error=reason,
            )

    with pytest.raises(ValidationError):
        SystemFacts(
            services=None,
            services_error=None,
            metrics=(),
            metrics_error=None,
            repositories=None,
            repositories_error="No repository source.",
            qwen=None,
            qwen_error="No Qwen source.",
            health=None,
            health_error="No system health source.",
        )


def test_legacy_risk_facts_can_never_claim_broker_reconciliation() -> None:
    valid = RiskFacts(
        session_date=None,
        daily_pnl=0.0,
        starting_equity=0.0,
        peak_equity=0.0,
        breaker_tripped=False,
        positions=(),
        broker_reconciled=False,
        blocked_actions=None,
        blocked_actions_error="No blocked-action source.",
        circuit_breaker=CircuitBreakerView(
            state="armed",
            reason=None,
            observed_at_utc=NOW,
        ),
        circuit_breaker_error=None,
    )
    assert valid.broker_reconciled is False
    with pytest.raises(ValidationError):
        RiskFacts.model_validate({**valid.model_dump(mode="python"), "broker_reconciled": True})


def test_timeline_facts_carry_exact_window_and_admission_cursor() -> None:
    facts = TimelineFacts(
        rows=(),
        hidden_event_count=7,
        hidden_impact_event_count=3,
        last_sequence=12,
    )

    assert facts.hidden_event_count == 7
    assert facts.hidden_impact_event_count == 3
    assert facts.last_sequence == 12

    with pytest.raises(ValidationError):
        TimelineFacts(
            rows=(),
            hidden_event_count=1,
            hidden_impact_event_count=2,
            last_sequence=12,
        )
