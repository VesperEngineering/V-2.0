"""Pure, deterministic shadow-plan attribution without persistence or authority."""

import math
from dataclasses import InitVar, dataclass, field, fields, is_dataclass, replace
from datetime import datetime

from vesper.portfolio.shadow_delta import ShadowDeltaPlan
from vesper.portfolio.shadow_target import _canonical_sha256
from vesper.strategy.base import Signal, SignalAction


_ACTIONS = {action.value for action in SignalAction}


def _content(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {
            item.name: _content(getattr(value, item.name))
            for item in fields(value)
            if not item.metadata.get("computed_digest")
        }
    if isinstance(value, dict):
        return {key: _content(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(_content(item) for item in value)
    return value


def _require_datetime(name, value):
    if type(value) is not datetime:
        raise ValueError(f"{name} must be a datetime")


def _require_symbol(value):
    if type(value) is not str or not value.strip():
        raise ValueError("symbol must be a nonblank string")


@dataclass(frozen=True, slots=True)
class CurrentSignalObservation:
    symbol: str
    action: str
    strength: float
    reason: str
    timestamp: datetime

    def __post_init__(self):
        _require_symbol(self.symbol)
        if type(self.action) is not str or self.action not in _ACTIONS:
            raise ValueError("action must be a declared SignalAction value")
        if type(self.strength) is not float or not math.isfinite(self.strength):
            raise ValueError("strength must be a finite float")
        if type(self.reason) is not str or not self.reason.strip():
            raise ValueError("reason must be a nonblank string")
        _require_datetime("timestamp", self.timestamp)


@dataclass(frozen=True, slots=True)
class CurrentSignalSnapshot:
    as_of_timestamp: datetime
    observations: tuple[CurrentSignalObservation, ...]
    snapshot_sha256: str = field(init=False, metadata={"computed_digest": True})

    def __post_init__(self):
        _require_datetime("as_of_timestamp", self.as_of_timestamp)
        if not isinstance(self.observations, tuple):
            raise ValueError("observations must be an immutable tuple")
        if any(type(item) is not CurrentSignalObservation for item in self.observations):
            raise ValueError("observations must be CurrentSignalObservation values")
        if tuple(item.symbol for item in self.observations) != tuple(
            sorted(item.symbol for item in self.observations)
        ):
            raise ValueError("observations must be symbol-sorted")
        if len({item.symbol for item in self.observations}) != len(self.observations):
            raise ValueError("observations must not contain duplicate symbols")
        if any(item.timestamp != self.as_of_timestamp for item in self.observations):
            raise ValueError("observation timestamp must match as_of_timestamp")
        object.__setattr__(
            self,
            "snapshot_sha256",
            _canonical_sha256(
                "vesper.shadow.current-signal-snapshot.v1",
                {
                    "as_of_timestamp": self.as_of_timestamp.isoformat(),
                    "observations": _content(self.observations),
                },
            ),
        )

    @classmethod
    def from_signals(cls, *, as_of_timestamp, signals):
        _require_datetime("as_of_timestamp", as_of_timestamp)
        observations = []
        for signal in signals:
            if type(signal) is not Signal:
                raise ValueError("current signal must be a Signal")
            if type(signal.action) is not SignalAction:
                raise ValueError("current signal action must be a SignalAction")
            if signal.timestamp != as_of_timestamp:
                raise ValueError("current signal timestamp must match as_of_timestamp")
            if (
                type(signal.strength) is not float
                or not math.isfinite(signal.strength)
                or not 0.0 <= signal.strength <= 1.0
            ):
                raise ValueError("current signal strength must be a finite float in [0, 1]")
            observations.append(
                CurrentSignalObservation(
                    symbol=signal.symbol,
                    action=signal.action.value,
                    strength=signal.strength,
                    reason=signal.reason,
                    timestamp=signal.timestamp,
                )
            )
        return cls(as_of_timestamp, tuple(sorted(observations, key=lambda item: item.symbol)))


@dataclass(frozen=True, slots=True)
class ShadowAttribution:
    symbol: str
    current_action: str | None
    shadow_action: str | None
    shadow_constraint_outcome: str
    shadow_reason: str
    shadow_urgency: str
    disposition: str

    def __post_init__(self):
        _require_symbol(self.symbol)
        for name in ("current_action", "shadow_action"):
            value = getattr(self, name)
            if value is not None and (type(value) is not str or value not in _ACTIONS):
                raise ValueError(f"{name} must be a declared action or None")
        if self.shadow_constraint_outcome not in {"actionable", "suppressed", "blocked"}:
            raise ValueError("shadow_constraint_outcome is not declared")
        if type(self.shadow_reason) is not str or not self.shadow_reason:
            raise ValueError("shadow_reason must be nonblank")
        if self.shadow_urgency not in {"increase", "reduce", "close", "none"}:
            raise ValueError("shadow_urgency is not declared")
        if self.shadow_constraint_outcome != "actionable" and self.shadow_action is not None:
            raise ValueError("non-actionable shadow line must not declare an action")
        if self.shadow_constraint_outcome == "actionable" and self.shadow_action is None:
            raise ValueError("actionable shadow line must declare an action")
        if self.current_action is None and self.shadow_action is None:
            expected = "both_inactive"
        elif self.current_action is None:
            expected = "shadow_delta_only"
        elif self.shadow_action is None:
            expected = "current_signal_only"
        elif self.current_action == self.shadow_action:
            expected = "aligned"
        else:
            expected = "divergent_action"
        if self.disposition != expected:
            raise ValueError("disposition does not match actions")


def _shadow_action(line):
    if line.constraint_outcome != "actionable":
        return None
    if line.urgency == "increase":
        return "BUY"
    if line.urgency == "reduce":
        return "SELL"
    if line.urgency == "close":
        return "CLOSE"
    raise ValueError("actionable shadow line has no declared action")


def _validated_plan(plan):
    if not isinstance(plan, ShadowDeltaPlan):
        raise ValueError("plan must be a ShadowDeltaPlan")
    try:
        validated_plan = replace(plan)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"plan is not derivation-closed: {exc}") from exc
    if validated_plan.plan_sha256 != plan.plan_sha256:
        raise ValueError("plan content does not match plan_sha256")
    return validated_plan


@dataclass(frozen=True, slots=True)
class ShadowEvidence:
    as_of_timestamp: datetime
    plan: InitVar[ShadowDeltaPlan]
    signal_snapshot: CurrentSignalSnapshot
    plan_sha256: str
    attributions: tuple[ShadowAttribution, ...] = field(
        init=False, metadata={"derived_claim": True}
    )
    evidence_sha256: str = field(init=False, metadata={"computed_digest": True})
    research_only: bool = True
    authority_state: str = "shadow"
    execution_authority: bool = False
    broker_authority: bool = False
    order_submission_authority: bool = False
    persistence_authority: bool = False

    def __post_init__(self, plan):
        _require_datetime("as_of_timestamp", self.as_of_timestamp)
        validated_plan = _validated_plan(plan)
        if self.as_of_timestamp != validated_plan.as_of_timestamp:
            raise ValueError("as_of_timestamp must match plan")
        if self.plan_sha256 != validated_plan.plan_sha256:
            raise ValueError("plan_sha256 does not match plan")
        if not isinstance(self.signal_snapshot, CurrentSignalSnapshot):
            raise ValueError("signal_snapshot must be a CurrentSignalSnapshot")
        snapshot = replace(self.signal_snapshot)
        if snapshot.snapshot_sha256 != self.signal_snapshot.snapshot_sha256:
            raise ValueError("signal snapshot content does not match snapshot_sha256")
        if snapshot.as_of_timestamp != self.as_of_timestamp:
            raise ValueError("signal snapshot timestamp must match plan")
        plan_symbols = {line.symbol for line in validated_plan.lines}
        current_actions = {item.symbol: item.action for item in snapshot.observations}
        if set(current_actions) - plan_symbols:
            raise ValueError("current signal symbol is unknown to plan")
        attributions = tuple(
            ShadowAttribution(
                symbol=line.symbol,
                current_action=current_actions.get(line.symbol),
                shadow_action=_shadow_action(line),
                shadow_constraint_outcome=line.constraint_outcome,
                shadow_reason=line.reason,
                shadow_urgency=line.urgency,
                disposition=(
                    "both_inactive"
                    if current_actions.get(line.symbol) is None and _shadow_action(line) is None
                    else "shadow_delta_only"
                    if current_actions.get(line.symbol) is None
                    else "current_signal_only"
                    if _shadow_action(line) is None
                    else "aligned"
                    if current_actions[line.symbol] == _shadow_action(line)
                    else "divergent_action"
                ),
            )
            for line in validated_plan.lines
        )
        if self.research_only is not True:
            raise ValueError("research_only must be True")
        if self.authority_state != "shadow":
            raise ValueError("authority_state must be shadow")
        for name in (
            "execution_authority",
            "broker_authority",
            "order_submission_authority",
            "persistence_authority",
        ):
            if getattr(self, name) is not False:
                raise ValueError(f"{name} must be False")
        object.__setattr__(self, "attributions", attributions)
        object.__setattr__(
            self,
            "evidence_sha256",
            _canonical_sha256(
                "vesper.shadow.evidence.v1",
                {
                    "as_of_timestamp": self.as_of_timestamp.isoformat(),
                    "plan_sha256": self.plan_sha256,
                    "signal_snapshot_sha256": snapshot.snapshot_sha256,
                    "attributions": _content(attributions),
                    "research_only": True,
                    "authority_state": "shadow",
                    "execution_authority": False,
                    "broker_authority": False,
                    "order_submission_authority": False,
                    "persistence_authority": False,
                },
            ),
        )


def build_shadow_evidence(plan, signals):
    """Compare current strategy signals with one validated inert shadow plan."""
    validated_plan = _validated_plan(plan)
    snapshot = CurrentSignalSnapshot.from_signals(
        as_of_timestamp=validated_plan.as_of_timestamp,
        signals=signals,
    )
    return ShadowEvidence(
        as_of_timestamp=validated_plan.as_of_timestamp,
        plan=validated_plan,
        signal_snapshot=snapshot,
        plan_sha256=validated_plan.plan_sha256,
    )
