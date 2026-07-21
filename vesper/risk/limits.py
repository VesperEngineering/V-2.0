"""Pre-trade risk checks. Every signal passes through here before reaching the broker."""

import logging
from dataclasses import dataclass

from vesper.execution.broker import Position
from vesper.strategy.base import Signal, SignalAction

logger = logging.getLogger("vesper.risk")


@dataclass
class RiskCheckResult:
    approved: bool
    reason: str
    adjusted_qty: float | None = None


class RiskLimits:
    def __init__(self, config: dict):
        r = config.get("risk", {})
        self.max_position_pct = r.get("max_position_pct", 0.10)
        self.max_portfolio_exposure = r.get("max_portfolio_exposure", 50_000)
        self.max_order_size = r.get("max_order_size", 10_000)
        self.max_open_positions = r.get("max_open_positions", 10)
        self.min_cash_reserve = r.get("min_cash_reserve", 5_000)
        self.max_daily_loss = r.get("max_daily_loss", -2_000)
        logger.info(
            "RiskLimits: pos=%.0f%% exposure=$%,.0f order=$%,.0f "
            "max_pos=%d cash=$%,.0f daily_loss=$%,.0f",
            self.max_position_pct * 100, self.max_portfolio_exposure,
            self.max_order_size, self.max_open_positions,
            self.min_cash_reserve, self.max_daily_loss,
        )

    def check_signal(self, signal: Signal, account: dict,
                     positions: dict[str, Position],
                     current_price: float, daily_pnl: float) -> RiskCheckResult:

        # Selling / closing is always allowed (reduces risk)
        if signal.action in (SignalAction.SELL, SignalAction.CLOSE):
            return RiskCheckResult(True, "risk-reducing order")

        # Circuit breaker
        if daily_pnl <= self.max_daily_loss:
            return RiskCheckResult(False,
                f"circuit breaker: P&L ${daily_pnl:,.0f} <= limit ${self.max_daily_loss:,.0f}")

        # Max positions
        if len(positions) >= self.max_open_positions:
            return RiskCheckResult(False,
                f"max positions reached ({len(positions)})")

        cash = account.get("cash", 0)
        pv = account.get("portfolio_value", 0)

        # Cash reserve
        if cash < self.min_cash_reserve:
            return RiskCheckResult(False,
                f"cash ${cash:,.0f} below reserve ${self.min_cash_reserve:,.0f}")

        # Compute target qty
        target = min(pv * self.max_position_pct * signal.strength, self.max_order_size)
        qty = int(target / current_price) if current_price > 0 else 0
        if qty <= 0:
            return RiskCheckResult(False, "computed qty is 0")

        notional = qty * current_price

        # Cap order size
        if notional > self.max_order_size:
            qty = int(self.max_order_size / current_price)
            notional = qty * current_price

        # Position concentration
        existing = positions.get(signal.symbol)
        existing_val = existing.market_value if existing else 0
        if pv > 0 and (existing_val + notional) / pv > self.max_position_pct:
            allowed = pv * self.max_position_pct - existing_val
            qty = max(0, int(allowed / current_price))
            if qty <= 0:
                return RiskCheckResult(False, "position concentration exceeded")
            notional = qty * current_price

        # Portfolio exposure
        total_exp = sum(p.market_value for p in positions.values())
        if total_exp + notional > self.max_portfolio_exposure:
            allowed = self.max_portfolio_exposure - total_exp
            qty = max(0, int(allowed / current_price))
            if qty <= 0:
                return RiskCheckResult(False, "portfolio exposure at limit")
            notional = qty * current_price

        # Cash sufficiency
        if notional > (cash - self.min_cash_reserve):
            qty = max(0, int((cash - self.min_cash_reserve) / current_price))
            if qty <= 0:
                return RiskCheckResult(False, "insufficient cash")

        return RiskCheckResult(True, f"approved qty={qty}", adjusted_qty=qty)