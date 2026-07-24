"""Tests for risk limits and circuit breaker."""

import pytest
from datetime import datetime

from vesper.execution.broker import Position
from vesper.risk.circuit_breaker import CircuitBreaker
from vesper.risk.limits import RiskLimits
from vesper.strategy.base import Signal, SignalAction


@pytest.fixture
def config():
    return {"risk": {
        "max_position_pct": 0.10,
        "max_portfolio_exposure": 50_000,
        "max_order_size": 10_000,
        "max_open_positions": 5,
        "min_cash_reserve": 5_000,
        "max_daily_loss": -2_000,
    }}


@pytest.fixture
def risk(config):
    return RiskLimits(config)


def _sig(sym="AAPL", action=SignalAction.BUY, strength=0.5):
    return Signal(sym, action, strength, "test")


def test_buy_approved(risk):
    r = risk.check_signal(
        _sig(), {"cash": 50_000, "portfolio_value": 100_000}, {}, 150.0, 0)
    assert r.approved
    assert r.adjusted_qty > 0


def test_circuit_breaker_blocks(risk):
    r = risk.check_signal(
        _sig(), {"cash": 50_000, "portfolio_value": 100_000}, {}, 150.0, -2500)
    assert not r.approved
    assert "circuit breaker" in r.reason


def test_max_positions_blocks(risk):
    pos = {f"S{i}": Position(f"S{i}", 10, 100, 100) for i in range(5)}
    r = risk.check_signal(
        _sig(), {"cash": 50_000, "portfolio_value": 100_000}, pos, 150.0, 0)
    assert not r.approved


def test_sell_always_approved(risk):
    r = risk.check_signal(
        _sig(action=SignalAction.SELL),
        {"cash": 0, "portfolio_value": 100_000}, {}, 150.0, -5000)
    assert r.approved


def test_breaker_trips_and_resets():
    cb = CircuitBreaker(-2000)
    d1 = datetime(2026, 7, 22, 10, 0)
    d2 = datetime(2026, 7, 23, 10, 0)

    assert not cb.check(-1000, d1)
    assert cb.check(-2500, d1)
    assert cb.is_tripped

    # Still tripped same day
    assert cb.check(0, d1)

    # Resets next day
    assert not cb.check(0, d2)
    assert not cb.is_tripped