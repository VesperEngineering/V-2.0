"""Strategy base class. All strategies inherit from this."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import pandas as pd

logger = logging.getLogger("vesper.strategy")


class SignalAction(Enum):
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"


@dataclass
class Signal:
    symbol: str
    action: SignalAction
    strength: float       # 0.0 – 1.0, used for position sizing
    reason: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)

    def __repr__(self):
        return f"Signal({self.action.value} {self.symbol} str={self.strength:.2f})"


class Strategy(ABC):
    def __init__(self, name: str, params: dict):
        self.name = name
        self.params = params
        logger.info("Strategy '%s' initialized: %s", name, params)

    @abstractmethod
    def generate_signals(
        self,
        data: dict[str, pd.DataFrame],
        current_positions: dict,
        timestamp: datetime,
    ) -> list[Signal]:
        ...

    def on_market_open(self, timestamp: datetime):
        logger.info("[%s] Market open", self.name)

    def on_market_close(self, timestamp: datetime):
        logger.info("[%s] Market close", self.name)