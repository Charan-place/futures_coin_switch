"""Base class for all trading strategies."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict
import pandas as pd


class Signal(Enum):
    LONG  = "LONG"
    SHORT = "SHORT"
    NONE  = "NONE"


@dataclass
class TradeSignal:
    signal: Signal
    strategy_name: str
    symbol: str
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float          # 0.0 – 1.0
    reason: str = ""
    atr: float = 0.0
    extra: Dict = field(default_factory=dict)

    @property
    def risk_reward(self) -> float:
        if self.signal == Signal.LONG:
            risk   = self.entry_price - self.stop_loss
            reward = self.take_profit  - self.entry_price
        elif self.signal == Signal.SHORT:
            risk   = self.stop_loss  - self.entry_price
            reward = self.entry_price - self.take_profit
        else:
            return 0.0
        return reward / risk if risk > 0 else 0.0

    def is_valid(self) -> bool:
        return (
            self.signal != Signal.NONE
            and self.stop_loss > 0
            and self.take_profit > 0
            and self.risk_reward >= 1.5    # minimum 1:1.5 R:R
        )


class BaseStrategy(ABC):
    name: str = "base"

    def __init__(self):
        self.last_signal: Optional[TradeSignal] = None

    @abstractmethod
    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        """
        Analyze a candle DataFrame and return a TradeSignal.
        df must be enriched (indicators already calculated).
        """
        ...

    def _no_signal(self, symbol: str, reason: str = "") -> TradeSignal:
        return TradeSignal(
            signal=Signal.NONE,
            strategy_name=self.name,
            symbol=symbol,
            entry_price=0,
            stop_loss=0,
            take_profit=0,
            confidence=0,
            reason=reason,
        )
