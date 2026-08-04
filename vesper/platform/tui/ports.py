"""Truthful, read-only source contracts for TUI projections."""

from __future__ import annotations

from datetime import date
from typing import Generic, Literal, Protocol, TypeVar, cast, runtime_checkable

from pydantic import model_validator

from vesper.platform.tui.views import (
    AgentCard,
    CandidateRow,
    DecimalString,
    EvidenceRow,
    FiniteFloat,
    Freshness,
    MemoryRow,
    MetricRow,
    ModelOpinionRow,
    NonEmptyStr,
    NonNegativeFiniteFloat,
    OrderRow,
    PortfolioRow,
    RepositoryRow,
    SafeId,
    ServiceRow,
    SourceRow,
    StrictModel,
    UtcDateTime,
)


T = TypeVar("T")


class SourceSample(StrictModel, Generic[T]):
    """One source observation with an explicit freshness contract."""

    value: T | None
    freshness: Freshness
    observed_at_utc: UtcDateTime | None
    source: NonEmptyStr
    error: NonEmptyStr | None

    @model_validator(mode="after")
    def require_truthful_state(self) -> SourceSample[T]:
        if self.freshness is Freshness.FRESH:
            if self.value is None or self.observed_at_utc is None or self.error is not None:
                raise ValueError("fresh samples require a value and UTC time without an error")
        elif self.freshness is Freshness.STALE:
            if self.value is None or self.observed_at_utc is None or self.error is None:
                raise ValueError("stale samples require a value, UTC time, and reason")
        elif self.freshness is Freshness.UNAVAILABLE:
            if self.value is not None or self.observed_at_utc is not None or self.error is None:
                raise ValueError("unavailable samples require only an error reason")
        elif any(
            item is not None for item in (self.value, self.observed_at_utc, self.error)
        ):
            raise ValueError("loading samples cannot report a value, time, or error")
        return self


class ConfiguredAgentFact(StrictModel):
    agent_id: SafeId
    purpose: NonEmptyStr
    model: Literal["qwen:64k"]
    skills: tuple[NonEmptyStr, ...]


class AgentFacts(StrictModel):
    configured_roster: tuple[ConfiguredAgentFact, ...]
    active_work: tuple[AgentCard, ...] | None
    active_work_error: NonEmptyStr | None

    @model_validator(mode="after")
    def explain_active_work(self) -> AgentFacts:
        if (self.active_work is None) == (self.active_work_error is None):
            raise ValueError("unavailable active work requires one reason")
        return self


class PortfolioFacts(StrictModel):
    rows: tuple[PortfolioRow, ...]
    rank_source: NonEmptyStr | None


class OrderFacts(StrictModel):
    rows: tuple[OrderRow, ...]


class ModelFacts(StrictModel):
    configured_strategy: Literal["ml_model", "momentum"] | None
    configured_model_id: SafeId | None
    opinions: tuple[ModelOpinionRow, ...]
    candidates: tuple[CandidateRow, ...]
    evidence: tuple[EvidenceRow, ...]


class LegacyPositionFact(StrictModel):
    symbol: SafeId
    quantity: DecimalString
    entry_price: DecimalString
    current_price: DecimalString


class RiskFacts(StrictModel):
    session_date: date | None
    daily_pnl: FiniteFloat
    starting_equity: NonNegativeFiniteFloat
    peak_equity: NonNegativeFiniteFloat
    breaker_tripped: bool
    positions: tuple[LegacyPositionFact, ...]
    broker_reconciled: Literal[False] = False


class DataFacts(StrictModel):
    sources: tuple[SourceRow, ...]
    evidence: tuple[EvidenceRow, ...]


class MemoryFacts(StrictModel):
    rows: tuple[MemoryRow, ...]


class SystemFacts(StrictModel):
    services: tuple[ServiceRow, ...] | None
    services_error: NonEmptyStr | None
    metrics: tuple[MetricRow, ...] | None
    metrics_error: NonEmptyStr | None
    repositories: tuple[RepositoryRow, ...] | None
    repositories_error: NonEmptyStr | None

    @model_validator(mode="after")
    def explain_each_component(self) -> SystemFacts:
        for label, value, error in (
            ("services", self.services, self.services_error),
            ("metrics", self.metrics, self.metrics_error),
            ("repositories", self.repositories, self.repositories_error),
        ):
            if (value is None) == (error is None):
                raise ValueError(f"{label} must be present or have one unavailable reason")
        return self


class _UnavailableConfiguration(StrictModel):
    reason: NonEmptyStr
    source: NonEmptyStr


class UnavailablePort(Generic[T]):
    """Read port for a source that has no truthful adapter yet."""

    def __init__(self, reason: NonEmptyStr, source: NonEmptyStr = "unconfigured") -> None:
        configuration = _UnavailableConfiguration(reason=reason, source=source)
        self._reason = configuration.reason
        self._source = configuration.source

    def read(self) -> SourceSample[T]:
        return cast(
            SourceSample[T],
            SourceSample(
                value=None,
                freshness=Freshness.UNAVAILABLE,
                observed_at_utc=None,
                source=self._source,
                error=self._reason,
            ),
        )


@runtime_checkable
class AgentReadPort(Protocol):
    def read(self) -> SourceSample[AgentFacts]: ...


@runtime_checkable
class PortfolioReadPort(Protocol):
    def read(self) -> SourceSample[PortfolioFacts]: ...


@runtime_checkable
class OrderReadPort(Protocol):
    def read(self) -> SourceSample[OrderFacts]: ...


@runtime_checkable
class ModelReadPort(Protocol):
    def read(self) -> SourceSample[ModelFacts]: ...


@runtime_checkable
class RiskReadPort(Protocol):
    def read(self) -> SourceSample[RiskFacts]: ...


@runtime_checkable
class DataReadPort(Protocol):
    def read(self) -> SourceSample[DataFacts]: ...


@runtime_checkable
class MemoryReadPort(Protocol):
    def read(self) -> SourceSample[MemoryFacts]: ...


@runtime_checkable
class SystemReadPort(Protocol):
    def read(self) -> SourceSample[SystemFacts]: ...
