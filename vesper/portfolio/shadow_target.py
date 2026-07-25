"""Deterministic in-memory top-N/equal-weight shadow portfolio targets."""

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime

from vesper.strategy.forecast import ForecastRecord


_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_COMMON_FORECAST_FIELDS = (
    "as_of_timestamp",
    "valid_until_timestamp",
    "horizon_sessions",
    "model_artifact_path",
    "model_artifact_sha256",
    "dataset_identity_sha256",
    "adjustment_identity_sha256",
    "feature_identity_sha256",
    "universe_identity_sha256",
    "expert_version",
    "feature_version",
    "run_manifest_sha256",
    "schema_version",
    "expert_id",
    "target_definition",
    "raw_score_units",
    "score_units",
    "direction",
    "data_freshness_status",
    "research_only",
    "execution_authority",
    "authority_state",
)


def _float_hex(value):
    normalized = 0.0 if value == 0 else float(value)
    return normalized.hex()


def _canonical_float(value):
    return 0.0 if value == 0 else float(value)


def _canonical_value(value):
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return {"type": "int", "value": str(value)}
    if isinstance(value, float):
        return _float_hex(value)
    if isinstance(value, dict):
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _canonical_sha256(domain, value) -> str:
    encoded = json.dumps(
        {"domain": domain, "payload": _canonical_value(value)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_sha256(name, value):
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a 64-character hexadecimal SHA-256")


def _is_number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _close(left, right):
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)


def _holdings_hash(holdings, cash_weight):
    normalized_holdings = tuple(
        (symbol, _canonical_float(weight)) for symbol, weight in holdings
    )
    return _canonical_sha256(
        "vesper.shadow.holdings.v1",
        {
            "holdings": normalized_holdings,
            "cash_weight": _canonical_float(cash_weight),
        },
    )


def _cash_hash(cash_weight):
    return _canonical_sha256(
        "vesper.shadow.cash.v1",
        {"cash_weight": _canonical_float(cash_weight)},
    )


def _cost_assumption_hash(rate):
    return _canonical_sha256(
        "vesper.shadow.transaction-cost.v1",
        {
            "transaction_cost_rate": (
                _canonical_float(rate) if rate is not None else None
            )
        },
    )


def _constraint_hash(top_n, entry_threshold, long_only, equal_weight):
    return _canonical_sha256(
        "vesper.shadow.constraints.v1",
        {
            "top_n": top_n,
            "entry_threshold": _canonical_float(entry_threshold),
            "long_only": long_only,
            "equal_weight": equal_weight,
        },
    )


@dataclass(frozen=True, slots=True)
class ShadowTargetLine:
    symbol: str
    target_weight: float
    target_notional: float
    reason: str
    raw_forecast_contribution: float | None
    standardized_forecast_contribution: float | None
    confidence: None
    estimated_cost: float | None

    def __post_init__(self):
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        for field in ("target_weight", "target_notional"):
            value = getattr(self, field)
            if not _is_number(value) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{field} must be finite and nonnegative")
        if self.estimated_cost is not None and (
            not _is_number(self.estimated_cost)
            or not math.isfinite(self.estimated_cost)
            or self.estimated_cost < 0
        ):
            raise ValueError("estimated_cost must be finite and nonnegative when supplied")
        if self.confidence is not None:
            raise ValueError("confidence must be unavailable (None)")
        reasons = {
            "selected_top_n",
            "outside_top_n",
            "below_or_equal_entry_threshold",
            "liquidation_no_forecast",
        }
        if self.reason not in reasons:
            raise ValueError("reason is not a declared shadow-target reason")
        contributions = (
            self.raw_forecast_contribution,
            self.standardized_forecast_contribution,
        )
        if self.reason == "liquidation_no_forecast":
            if any(value is not None for value in contributions):
                raise ValueError("liquidation forecast contribution must be unavailable")
        elif any(
            not _is_number(value) or not math.isfinite(value)
            for value in contributions
        ):
            raise ValueError("forecast contribution must be finite when a forecast exists")
        if self.reason == "selected_top_n":
            if self.target_weight <= 0 or self.target_notional <= 0:
                raise ValueError("selected_top_n line must have positive target values")
        elif self.target_weight != 0 or self.target_notional != 0:
            raise ValueError("non-selected line must have zero target values")


@dataclass(frozen=True, slots=True)
class ShadowPortfolioTarget:
    as_of_timestamp: datetime
    valid_until_timestamp: datetime
    forecasts: tuple[ForecastRecord, ...]
    eligible_forecast_set_sha256: str
    current_holdings_weights: tuple[tuple[str, float], ...]
    current_cash_weight: float
    holdings_snapshot_sha256: str
    cash_snapshot_sha256: str
    portfolio_value: float
    transaction_cost_assumption: tuple[tuple[str, float | None], ...]
    transaction_cost_assumption_sha256: str
    transaction_cost_rate: float | None
    universe_identity_sha256: str
    classification_identity_sha256: str
    constraint_identity_sha256: str
    target_generation_version: str
    top_n: int
    entry_threshold: float
    long_only: bool
    equal_weight: bool
    lines: tuple[ShadowTargetLine, ...]
    turnover: float
    gross_exposure: float
    net_exposure: float
    concentration: float
    selected_count: int
    blocked: bool
    infeasible: bool
    diagnostic_reason: str | None
    research_only: bool = True
    authority_state: str = "shadow"
    execution_authority: bool = False
    risk_authority: bool = False
    broker_authority: bool = False
    persistence_authority: bool = False

    def __post_init__(self):
        if not isinstance(self.as_of_timestamp, datetime):
            raise ValueError("as_of_timestamp must be a datetime")
        if not isinstance(self.valid_until_timestamp, datetime):
            raise ValueError("valid_until_timestamp must be a datetime")
        if self.valid_until_timestamp < self.as_of_timestamp:
            raise ValueError("valid_until_timestamp must not precede as_of_timestamp")
        for field in (
            "eligible_forecast_set_sha256",
            "holdings_snapshot_sha256",
            "cash_snapshot_sha256",
            "transaction_cost_assumption_sha256",
            "universe_identity_sha256",
            "classification_identity_sha256",
            "constraint_identity_sha256",
        ):
            _require_sha256(field, getattr(self, field))

        if not isinstance(self.forecasts, tuple):
            raise ValueError("forecasts must be an immutable tuple")
        validated_forecasts = tuple(_validated_forecasts(self.forecasts))
        canonical_forecasts = tuple(
            sorted(validated_forecasts, key=lambda forecast: forecast.symbol)
        )
        if self.forecasts != canonical_forecasts:
            raise ValueError("forecasts must be in symbol order")
        if any(
            forecast.as_of_timestamp != self.as_of_timestamp
            for forecast in validated_forecasts
        ):
            raise ValueError("forecast as_of_timestamp does not match target")
        if any(
            forecast.valid_until_timestamp != self.valid_until_timestamp
            for forecast in validated_forecasts
        ):
            raise ValueError("forecast valid_until_timestamp does not match target")
        if any(
            forecast.universe_identity_sha256 != self.universe_identity_sha256
            for forecast in validated_forecasts
        ):
            raise ValueError("forecast universe_identity_sha256 does not match target")
        if self.eligible_forecast_set_sha256 != _forecast_set_sha256(
            validated_forecasts
        ):
            raise ValueError(
                "eligible_forecast_set_sha256 does not match embedded forecasts"
            )
        forecasts_by_symbol = {
            forecast.symbol: forecast for forecast in validated_forecasts
        }

        if not _is_number(self.portfolio_value) or not math.isfinite(
            self.portfolio_value
        ) or self.portfolio_value <= 0:
            raise ValueError("portfolio_value must be finite and positive")
        if (
            isinstance(self.top_n, bool)
            or not isinstance(self.top_n, int)
            or self.top_n < 1
        ):
            raise ValueError("top_n must be a positive integer")
        if not _is_number(self.entry_threshold) or not math.isfinite(self.entry_threshold):
            raise ValueError("entry_threshold must be finite")
        if (
            not isinstance(self.target_generation_version, str)
            or not self.target_generation_version.strip()
        ):
            raise ValueError("target_generation_version must not be blank")
        if self.long_only is not True:
            raise ValueError("long_only must be True")
        if self.equal_weight is not True:
            raise ValueError("equal_weight must be True")
        if self.transaction_cost_rate is not None and (
            not _is_number(self.transaction_cost_rate)
            or not math.isfinite(self.transaction_cost_rate)
            or self.transaction_cost_rate < 0
        ):
            raise ValueError("transaction_cost_rate must be finite and nonnegative")

        if not isinstance(self.current_holdings_weights, tuple):
            raise ValueError("current_holdings_weights must be an immutable tuple")
        holdings = {}
        for item in self.current_holdings_weights:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("current_holdings_weights entries must be pairs")
            symbol, weight = item
            if not isinstance(symbol, str) or not symbol.strip() or symbol in holdings:
                raise ValueError("current_holdings_weights symbols must be unique and nonblank")
            if not _is_number(weight) or not math.isfinite(weight) or not 0 <= weight <= 1:
                raise ValueError("current_holdings_weights must be finite values in [0, 1]")
            holdings[symbol] = float(weight)
        if tuple(holdings) != tuple(sorted(holdings)):
            raise ValueError("current_holdings_weights must be symbol-sorted")
        if not _is_number(self.current_cash_weight) or not math.isfinite(
            self.current_cash_weight
        ) or not 0 <= self.current_cash_weight <= 1:
            raise ValueError("current cash weight must be finite and in [0, 1]")
        if not _close(sum(holdings.values()) + self.current_cash_weight, 1.0):
            raise ValueError("current cash weight must equal 1 minus holdings weights")
        normalized_holdings = tuple((symbol, holdings[symbol]) for symbol in sorted(holdings))
        if self.holdings_snapshot_sha256 != _holdings_hash(
            normalized_holdings, self.current_cash_weight
        ):
            raise ValueError("holdings_snapshot_sha256 does not match embedded holdings/cash")
        if self.cash_snapshot_sha256 != _cash_hash(self.current_cash_weight):
            raise ValueError("cash_snapshot_sha256 does not match embedded cash")

        expected_assumption = (("transaction_cost_rate", self.transaction_cost_rate),)
        if self.transaction_cost_assumption != expected_assumption:
            raise ValueError("transaction_cost_assumption does not match transaction_cost_rate")
        if self.transaction_cost_assumption_sha256 != _cost_assumption_hash(
            self.transaction_cost_rate
        ):
            raise ValueError("transaction_cost_assumption_sha256 does not match assumption")
        if self.constraint_identity_sha256 != _constraint_hash(
            self.top_n, self.entry_threshold, self.long_only, self.equal_weight
        ):
            raise ValueError("constraint_identity_sha256 does not match fixed constraints")

        if not isinstance(self.lines, tuple) or not self.lines:
            raise ValueError("lines must be a nonempty immutable tuple")
        if any(not isinstance(line, ShadowTargetLine) for line in self.lines):
            raise ValueError("lines must contain ShadowTargetLine values")
        for line in self.lines:
            try:
                ShadowTargetLine(**asdict(line))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid target line: {exc}") from exc
        symbols = tuple(line.symbol for line in self.lines)
        if len(symbols) != len(set(symbols)):
            raise ValueError("line symbols must be unique")
        if symbols != tuple(sorted(symbols)):
            raise ValueError("lines must be in symbol order")
        expected_symbols = set(holdings) | set(forecasts_by_symbol)
        if set(symbols) != expected_symbols:
            raise ValueError("lines must cover exactly all forecasts and current holdings")

        for line in self.lines:
            forecast = forecasts_by_symbol.get(line.symbol)
            if forecast is None:
                if line.reason != "liquidation_no_forecast":
                    raise ValueError(
                        "symbol absent from forecasts must be liquidation_no_forecast"
                    )
                continue
            if line.reason == "liquidation_no_forecast":
                raise ValueError(
                    "liquidation_no_forecast requires symbol absent from forecasts"
                )
            if _float_hex(line.raw_forecast_contribution) != _float_hex(
                forecast.raw_model_score
            ) or _float_hex(line.standardized_forecast_contribution) != _float_hex(
                forecast.standardized_score
            ):
                raise ValueError(
                    "target line forecast contribution does not match embedded forecast"
                )

        selected = [line for line in self.lines if line.reason == "selected_top_n"]
        if (
            isinstance(self.selected_count, bool)
            or not isinstance(self.selected_count, int)
            or self.selected_count < 0
        ):
            raise ValueError("selected_count must be a nonnegative integer")
        if self.selected_count != len(selected) or self.selected_count > self.top_n:
            raise ValueError("selected_count must match selected lines and top_n")
        expected_selected = {
            line.symbol
            for line in sorted(
                (
                    line
                    for line in self.lines
                    if line.raw_forecast_contribution is not None
                    and line.raw_forecast_contribution > self.entry_threshold
                ),
                key=lambda line: (-line.raw_forecast_contribution, line.symbol),
            )[: self.top_n]
        }
        if {line.symbol for line in selected} != expected_selected:
            raise ValueError("selected lines must match deterministic top_n constraints")
        selected_weight = 1.0 / self.selected_count if self.selected_count else 0.0
        for line in self.lines:
            if line.reason == "selected_top_n" and not _close(
                line.target_weight, selected_weight
            ):
                raise ValueError("selected line must have equal weight")
            if line.reason == "below_or_equal_entry_threshold" and not (
                line.raw_forecast_contribution <= self.entry_threshold
            ):
                raise ValueError("threshold reason contradicts forecast contribution")
            if line.reason == "outside_top_n" and not (
                line.raw_forecast_contribution > self.entry_threshold
            ):
                raise ValueError("outside_top_n reason contradicts forecast contribution")
            expected_notional = line.target_weight * self.portfolio_value
            if not _close(line.target_notional, expected_notional):
                raise ValueError("target_notional does not match target weight and portfolio value")
            expected_cost = None
            if self.transaction_cost_rate is not None:
                expected_cost = (
                    abs(line.target_weight - holdings.get(line.symbol, 0.0))
                    * self.portfolio_value
                    * self.transaction_cost_rate
                )
            if expected_cost is None:
                if line.estimated_cost is not None:
                    raise ValueError("estimated_cost must be unavailable without a cost rate")
            elif line.estimated_cost is None or not _close(
                line.estimated_cost, expected_cost
            ):
                raise ValueError("estimated_cost does not match the complete trade")

        target_weights = {line.symbol: line.target_weight for line in self.lines}
        expected_gross = sum(abs(weight) for weight in target_weights.values())
        expected_net = sum(target_weights.values())
        expected_concentration = max(abs(weight) for weight in target_weights.values())
        target_cash_weight = 1.0 - expected_net
        asset_change = sum(
            abs(target_weights[symbol] - holdings.get(symbol, 0.0))
            for symbol in symbols
        )
        expected_turnover = 0.5 * (
            asset_change + abs(target_cash_weight - self.current_cash_weight)
        )
        for field, value, expected in (
            ("turnover", self.turnover, expected_turnover),
            ("gross_exposure", self.gross_exposure, expected_gross),
            ("net_exposure", self.net_exposure, expected_net),
            ("concentration", self.concentration, expected_concentration),
        ):
            if not _is_number(value) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{field} must be finite and nonnegative")
            if not _close(value, expected):
                raise ValueError(f"{field} does not match target content")
        if any(
            value > 1 + 1e-12
            for value in (
                self.gross_exposure,
                self.net_exposure,
                self.concentration,
                self.turnover,
            )
        ):
            raise ValueError("portfolio metrics must not exceed one")

        if not isinstance(self.blocked, bool) or not isinstance(self.infeasible, bool):
            raise ValueError("blocked and infeasible must be booleans")
        has_diagnostic = isinstance(self.diagnostic_reason, str) and bool(
            self.diagnostic_reason.strip()
        )
        if (self.blocked or self.infeasible) != has_diagnostic:
            raise ValueError("diagnostic_reason must exactly match blocked/infeasible state")
        if (self.blocked or self.infeasible) and self.selected_count:
            raise ValueError("blocked or infeasible target cannot select holdings")
        if self.diagnostic_reason is not None and not has_diagnostic:
            raise ValueError("diagnostic_reason must be None or nonblank")
        if self.research_only is not True:
            raise ValueError("research_only must be True")
        if self.authority_state != "shadow":
            raise ValueError("authority_state must be shadow")
        for field in (
            "execution_authority",
            "risk_authority",
            "broker_authority",
            "persistence_authority",
        ):
            if getattr(self, field) is not False:
                raise ValueError(f"{field} must be False")


def _validated_forecasts(forecasts):
    if not forecasts:
        raise ValueError("forecasts must not be empty")
    validated = []
    for forecast in forecasts:
        if not isinstance(forecast, ForecastRecord):
            raise ValueError("forecasts must contain ForecastRecord values")
        try:
            validated.append(ForecastRecord(**asdict(forecast)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid forecast: {exc}") from exc

    symbols = [forecast.symbol for forecast in validated]
    if len(symbols) != len(set(symbols)):
        raise ValueError("duplicate forecast symbol")
    expected = tuple(getattr(validated[0], field) for field in _COMMON_FORECAST_FIELDS)
    if any(
        tuple(getattr(forecast, field) for field in _COMMON_FORECAST_FIELDS) != expected
        for forecast in validated[1:]
    ):
        raise ValueError("forecasts must share complete common provenance")
    ranked = sorted(validated, key=lambda forecast: (-forecast.raw_model_score, forecast.symbol))
    if [forecast.rank for forecast in ranked] != list(range(1, len(ranked) + 1)):
        raise ValueError("forecast ranks must be contiguous and match deterministic raw-score rank")
    return validated


def _forecast_set_sha256(forecasts):
    records = []
    for forecast in sorted(forecasts, key=lambda item: item.symbol):
        record = asdict(forecast)
        record["as_of_timestamp"] = forecast.as_of_timestamp.isoformat()
        record["valid_until_timestamp"] = forecast.valid_until_timestamp.isoformat()
        record["raw_model_score"] = _canonical_float(forecast.raw_model_score)
        record["standardized_score"] = _canonical_float(forecast.standardized_score)
        records.append(record)
    return _canonical_sha256("vesper.shadow.forecast-set.v1", records)


def build_shadow_portfolio_target(
    *,
    forecasts,
    as_of_timestamp,
    valid_until_timestamp,
    current_holdings_weights,
    portfolio_value,
    classification_identity_sha256,
    target_generation_version,
    top_n,
    entry_threshold,
    transaction_cost_rate=None,
):
    """Build an inert shadow target; this function has no side effects or authority."""
    validated = _validated_forecasts(forecasts)
    if not isinstance(as_of_timestamp, datetime):
        raise ValueError("as_of_timestamp must be a datetime")
    if not isinstance(valid_until_timestamp, datetime):
        raise ValueError("valid_until_timestamp must be a datetime")
    if any(forecast.as_of_timestamp != as_of_timestamp for forecast in validated):
        raise ValueError("forecast as_of_timestamp does not match target as_of_timestamp")
    if any(
        forecast.valid_until_timestamp != valid_until_timestamp for forecast in validated
    ):
        raise ValueError(
            "forecast valid_until_timestamp does not match target valid_until_timestamp"
        )
    _require_sha256("classification_identity_sha256", classification_identity_sha256)
    if (
        not _is_number(portfolio_value)
        or not math.isfinite(portfolio_value)
        or portfolio_value <= 0
    ):
        raise ValueError("portfolio_value must be finite and positive")
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    if not _is_number(entry_threshold) or not math.isfinite(entry_threshold):
        raise ValueError("entry_threshold must be finite")
    if (
        not isinstance(target_generation_version, str)
        or not target_generation_version.strip()
    ):
        raise ValueError("target_generation_version must not be blank")
    if transaction_cost_rate is not None and (
        not _is_number(transaction_cost_rate)
        or not math.isfinite(transaction_cost_rate)
        or transaction_cost_rate < 0
    ):
        raise ValueError("transaction_cost_rate must be finite and nonnegative")
    normalized_rate = (
        0.0 if transaction_cost_rate == 0 else float(transaction_cost_rate)
    ) if transaction_cost_rate is not None else None
    normalized_threshold = 0.0 if entry_threshold == 0 else float(entry_threshold)

    try:
        holdings_input = dict(current_holdings_weights)
    except (TypeError, ValueError) as exc:
        raise ValueError("current_holdings_weights must be a symbol-to-weight mapping") from exc
    if len(holdings_input) != len(current_holdings_weights):
        raise ValueError("current_holdings_weights symbols must be unique")
    if any(not isinstance(symbol, str) or not symbol.strip() for symbol in holdings_input):
        raise ValueError("current_holdings_weights symbols must be nonblank strings")
    if any(
        not _is_number(weight)
        or not math.isfinite(weight)
        or weight < 0
        or weight > 1
        for weight in holdings_input.values()
    ) or sum(holdings_input.values()) > 1:
        raise ValueError(
            "current_holdings_weights must be finite values in [0, 1] "
            "summing to at most 1"
        )
    holdings = tuple(
        (
            symbol,
            0.0 if holdings_input[symbol] == 0 else float(holdings_input[symbol]),
        )
        for symbol in sorted(holdings_input)
    )
    holdings_map = dict(holdings)
    current_cash_weight = 1.0 - sum(holdings_map.values())

    ranked = sorted(validated, key=lambda forecast: (-forecast.raw_model_score, forecast.symbol))
    eligible = [
        forecast
        for forecast in ranked
        if forecast.raw_model_score > normalized_threshold
    ]
    selected_symbols = {forecast.symbol for forecast in eligible[:top_n]}
    selected_count = len(selected_symbols)
    selected_weight = 1.0 / selected_count if selected_count else 0.0
    forecasts_by_symbol = {forecast.symbol: forecast for forecast in validated}
    all_symbols = sorted(set(forecasts_by_symbol) | set(holdings_map))

    lines = []
    target_weights = {}
    for symbol in all_symbols:
        forecast = forecasts_by_symbol.get(symbol)
        weight = selected_weight if symbol in selected_symbols else 0.0
        target_weights[symbol] = weight
        if forecast is None:
            reason = "liquidation_no_forecast"
            raw_contribution = None
            standardized_contribution = None
        else:
            raw_contribution = forecast.raw_model_score
            standardized_contribution = forecast.standardized_score
            if symbol in selected_symbols:
                reason = "selected_top_n"
            elif forecast.raw_model_score <= normalized_threshold:
                reason = "below_or_equal_entry_threshold"
            else:
                reason = "outside_top_n"
        estimated_cost = None
        if normalized_rate is not None:
            estimated_cost = (
                abs(weight - holdings_map.get(symbol, 0.0))
                * portfolio_value
                * normalized_rate
            )
        lines.append(
            ShadowTargetLine(
                symbol=symbol,
                target_weight=weight,
                target_notional=weight * portfolio_value,
                reason=reason,
                raw_forecast_contribution=raw_contribution,
                standardized_forecast_contribution=standardized_contribution,
                confidence=None,
                estimated_cost=estimated_cost,
            )
        )

    asset_change = sum(
        abs(target_weights[symbol] - holdings_map.get(symbol, 0.0))
        for symbol in all_symbols
    )
    target_cash_weight = 1.0 - sum(target_weights.values())
    turnover = 0.5 * (
        asset_change + abs(target_cash_weight - current_cash_weight)
    )
    gross_exposure = sum(abs(weight) for weight in target_weights.values())
    net_exposure = sum(target_weights.values())
    rate = normalized_rate
    long_only = True
    equal_weight = True

    return ShadowPortfolioTarget(
        as_of_timestamp=as_of_timestamp,
        valid_until_timestamp=valid_until_timestamp,
        forecasts=tuple(sorted(validated, key=lambda forecast: forecast.symbol)),
        eligible_forecast_set_sha256=_forecast_set_sha256(validated),
        current_holdings_weights=holdings,
        current_cash_weight=current_cash_weight,
        holdings_snapshot_sha256=_holdings_hash(holdings, current_cash_weight),
        cash_snapshot_sha256=_cash_hash(current_cash_weight),
        portfolio_value=float(portfolio_value),
        transaction_cost_assumption=(("transaction_cost_rate", rate),),
        transaction_cost_assumption_sha256=_cost_assumption_hash(rate),
        transaction_cost_rate=rate,
        universe_identity_sha256=validated[0].universe_identity_sha256,
        classification_identity_sha256=classification_identity_sha256,
        constraint_identity_sha256=_constraint_hash(
            top_n, normalized_threshold, long_only, equal_weight
        ),
        target_generation_version=target_generation_version,
        top_n=top_n,
        entry_threshold=normalized_threshold,
        long_only=long_only,
        equal_weight=equal_weight,
        lines=tuple(lines),
        turnover=turnover,
        gross_exposure=gross_exposure,
        net_exposure=net_exposure,
        concentration=max((abs(weight) for weight in target_weights.values()), default=0.0),
        selected_count=selected_count,
        blocked=False,
        infeasible=False,
        diagnostic_reason=None,
    )
