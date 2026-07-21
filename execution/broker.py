"""Broker abstraction. PaperBroker for simulation, AlpacaBroker for real."""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger("vesper.execution")


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    id: str
    symbol: str
    side: OrderSide
    qty: float
    order_type: OrderType
    limit_price: float | None
    status: OrderStatus
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    submitted_at: datetime | None = None
    filled_at: datetime | None = None


@dataclass
class Position:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float

    @property
    def market_value(self) -> float:
        return abs(self.qty) * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.avg_entry_price) * self.qty

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.avg_entry_price == 0:
            return 0.0
        return (self.current_price - self.avg_entry_price) / self.avg_entry_price


class BrokerBase(ABC):
    @abstractmethod
    def submit_order(self, symbol, qty, side, order_type=OrderType.MARKET,
                     limit_price=None) -> Order: ...
    @abstractmethod
    def get_order(self, order_id) -> Order | None: ...
    @abstractmethod
    def get_positions(self) -> dict[str, Position]: ...
    @abstractmethod
    def get_account(self) -> dict: ...
    @abstractmethod
    def close_position(self, symbol) -> Order | None: ...
    @abstractmethod
    def close_all_positions(self) -> list[Order]: ...


# ── Paper Broker ────────────────────────────────────────────

class PaperBroker(BrokerBase):
    """Simulated broker. Fills instantly at last known price."""

    def __init__(self, initial_cash: float = 100_000):
        self.cash = initial_cash
        self.positions: dict[str, Position] = {}
        self.orders: list[Order] = []
        self._counter = 0
        self._prices: dict[str, float] = {}
        logger.info("PaperBroker initialized with $%,.0f", initial_cash)

    def update_prices(self, prices: dict[str, float]):
        self._prices.update(prices)
        for sym, pos in self.positions.items():
            if sym in prices:
                pos.current_price = prices[sym]

    def submit_order(self, symbol, qty, side, order_type=OrderType.MARKET,
                     limit_price=None):
        self._counter += 1
        oid = f"PAPER-{self._counter}"
        price = limit_price or self._prices.get(symbol, 0)

        if price <= 0:
            return Order(oid, symbol, side, qty, order_type, limit_price,
                         OrderStatus.REJECTED)

        cost = price * qty

        if side == OrderSide.BUY:
            if cost > self.cash:
                logger.warning("Insufficient cash for %d %s ($%,.0f > $%,.0f)",
                               qty, symbol, cost, self.cash)
                return Order(oid, symbol, side, qty, order_type, limit_price,
                             OrderStatus.REJECTED)
            self.cash -= cost
            if symbol in self.positions:
                p = self.positions[symbol]
                total = p.qty + qty
                p.avg_entry_price = (p.avg_entry_price * p.qty + price * qty) / total
                p.qty = total
            else:
                self.positions[symbol] = Position(symbol, qty, price, price)

        else:  # SELL
            if symbol not in self.positions:
                return Order(oid, symbol, side, qty, order_type, limit_price,
                             OrderStatus.REJECTED)
            self.cash += price * qty
            self.positions[symbol].qty -= qty
            if self.positions[symbol].qty <= 0:
                del self.positions[symbol]

        order = Order(oid, symbol, side, qty, order_type, limit_price,
                      OrderStatus.FILLED, qty, price,
                      datetime.utcnow(), datetime.utcnow())
        self.orders.append(order)
        logger.info("Paper fill: %s %d %s @ $%.2f", side.value, qty, symbol, price)
        return order

    def get_order(self, order_id):
        for o in self.orders:
            if o.id == order_id:
                return o
        return None

    def get_positions(self):
        return dict(self.positions)

    def get_account(self):
        pv = sum(p.market_value for p in self.positions.values())
        return {
            "cash": self.cash,
            "equity": self.cash + pv,
            "buying_power": self.cash,
            "portfolio_value": self.cash + pv,
        }

    def close_position(self, symbol):
        if symbol not in self.positions:
            return None
        return self.submit_order(symbol, self.positions[symbol].qty, OrderSide.SELL)

    def close_all_positions(self):
        results = []
        for sym in list(self.positions.keys()):
            o = self.close_position(sym)
            if o:
                results.append(o)
        return results


# ── Alpaca Broker ───────────────────────────────────────────

class AlpacaBroker(BrokerBase):
    """Alpaca Markets broker (paper and live)."""

    def __init__(self, config: dict):
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderSide as _AS, TimeInForce as _TIF

        self._MOR = MarketOrderRequest
        self._LOR = LimitOrderRequest
        self._AS = _AS
        self._TIF = _TIF

        api_key = os.environ.get("ALPACA_API_KEY", "")
        api_secret = os.environ.get("ALPACA_API_SECRET", "")

        base_url = config.get("broker", {}).get("base_url", "")
        paper = "paper" in base_url

        self.client = TradingClient(api_key, api_secret, paper=paper)
        self._orders: dict[str, Order] = {}
        logger.info("AlpacaBroker initialized (paper=%s)", paper)

    def submit_order(self, symbol, qty, side, order_type=OrderType.MARKET,
                     limit_price=None):
        try:
            a_side = self._AS.BUY if side == OrderSide.BUY else self._AS.SELL
            if order_type == OrderType.MARKET:
                req = self._MOR(symbol=symbol, qty=qty, side=a_side,
                                time_in_force=self._TIF.DAY)
            else:
                req = self._LOR(symbol=symbol, qty=qty, side=a_side,
                                limit_price=limit_price,
                                time_in_force=self._TIF.DAY)
            resp = self.client.submit_order(req)
            order = Order(str(resp.id), symbol, side, qty, order_type,
                          limit_price, OrderStatus.SUBMITTED,
                          submitted_at=datetime.utcnow())
            self._orders[order.id] = order
            logger.info("Submitted: %s %d %s -> %s", side.value, qty, symbol, order.id)
            return order
        except Exception as e:
            logger.error("Order failed for %s: %s", symbol, e)
            return Order("FAILED", symbol, side, qty, order_type, limit_price,
                         OrderStatus.REJECTED)

    def get_order(self, order_id):
        try:
            r = self.client.get_order_by_id(order_id)
            return self._map(r)
        except Exception:
            return self._orders.get(order_id)

    def get_positions(self):
        try:
            return {
                p.symbol: Position(p.symbol, float(p.qty),
                                   float(p.avg_entry_price),
                                   float(p.current_price))
                for p in self.client.get_all_positions()
            }
        except Exception as e:
            logger.error("Failed to get positions: %s", e)
            return {}

    def get_account(self):
        try:
            a = self.client.get_account()
            return {
                "cash": float(a.cash),
                "equity": float(a.equity),
                "buying_power": float(a.buying_power),
                "portfolio_value": float(a.portfolio_value),
            }
        except Exception as e:
            logger.error("Failed to get account: %s", e)
            return {"cash": 0, "equity": 0, "buying_power": 0, "portfolio_value": 0}

    def close_position(self, symbol):
        try:
            return self._map(self.client.close_position(symbol))
        except Exception as e:
            logger.error("Failed to close %s: %s", symbol, e)
            return None

    def close_all_positions(self):
        try:
            return [self._map(o) for o in
                    self.client.close_all_positions(cancel_orders=True)]
        except Exception as e:
            logger.error("Failed to close all: %s", e)
            return []

    def _map(self, r) -> Order:
        status_map = {
            "new": OrderStatus.SUBMITTED,
            "accepted": OrderStatus.SUBMITTED,
            "filled": OrderStatus.FILLED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "canceled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
        }
        return Order(
            id=str(r.id),
            symbol=r.symbol,
            side=OrderSide.BUY if r.side == "buy" else OrderSide.SELL,
            qty=float(r.qty),
            order_type=OrderType.MARKET if r.type == "market" else OrderType.LIMIT,
            limit_price=float(r.limit_price) if r.limit_price else None,
            status=status_map.get(str(r.status), OrderStatus.PENDING),
            filled_qty=float(r.filled_qty or 0),
            avg_fill_price=float(r.filled_avg_price or 0),
            submitted_at=r.submitted_at,
            filled_at=r.filled_at,
        )


def create_broker(config: dict) -> BrokerBase:
    mode = config.get("mode", "paper")
    if mode == "backtest":
        logger.info("Broker: PaperBroker (backtest)")
        return PaperBroker()
    provider = config.get("broker", {}).get("provider", "alpaca")
    if provider == "alpaca":
        logger.info("Broker: Alpaca (%s)", mode)
        return AlpacaBroker(config)
    raise ValueError(f"Unknown broker: {provider}")