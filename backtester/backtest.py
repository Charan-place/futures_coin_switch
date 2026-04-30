"""
Backtester — run strategies against historical OHLCV data.
Use this BEFORE going live to validate strategy performance.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

from indicators.technical import enrich
from strategies.base_strategy import TradeSignal, Signal
from strategies.ema_rsi_strategy import EmaRsiStrategy
from strategies.breakout_strategy import BreakoutStrategy
from strategies.mtf_trend_strategy import MtfTrendStrategy
from strategies.confluence_engine import ConfluenceEngine
from config.settings import (
    ATR_SL_MULTIPLIER, ATR_TP_MULTIPLIER, RISK_PER_TRADE_PCT,
    BACKTEST_APPLY_FEES, INCLUDE_FEES_IN_SIZING,
)
from core.fees import from_settings as build_fee_model


@dataclass
class BacktestTrade:
    signal: str
    entry_idx: int
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    qty: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    strategy: str


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    trades: List[BacktestTrade]
    initial_balance: float
    final_balance: float

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.pnl > 0)
        return wins / len(self.trades) * 100

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss   = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        return gross_profit / gross_loss if gross_loss else float("inf")

    @property
    def max_drawdown(self) -> float:
        balance = self.initial_balance
        peak = balance
        max_dd = 0.0
        for t in self.trades:
            balance += t.pnl
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @property
    def sharpe_ratio(self) -> float:
        if not self.trades:
            return 0.0
        rets = [t.pnl_pct for t in self.trades]
        mean = np.mean(rets)
        std  = np.std(rets)
        return (mean / std * np.sqrt(252)) if std > 0 else 0.0

    def summary(self) -> Dict:
        return {
            "symbol":         self.symbol,
            "timeframe":      self.timeframe,
            "total_trades":   self.total_trades,
            "win_rate":       f"{self.win_rate:.1f}%",
            "profit_factor":  f"{self.profit_factor:.2f}",
            "max_drawdown":   f"{self.max_drawdown:.1f}%",
            "sharpe_ratio":   f"{self.sharpe_ratio:.2f}",
            "initial_balance":f"${self.initial_balance:,.2f}",
            "final_balance":  f"${self.final_balance:,.2f}",
            "total_return":   f"{(self.final_balance/self.initial_balance - 1)*100:.1f}%",
        }


class Backtester:
    def __init__(self, initial_balance: float = 1000.0):
        self.initial_balance = initial_balance
        self.engine = ConfluenceEngine()
        self.fee_model = build_fee_model()

    def run(self, df: pd.DataFrame, symbol: str, timeframe: str = "15m") -> BacktestResult:
        """
        Run a full backtest on historical OHLCV data.
        df must have open/high/low/close/volume columns.
        """
        df = enrich(df.copy())
        trades: List[BacktestTrade] = []
        balance = self.initial_balance
        warmup = 50   # skip first N candles for indicator warmup

        i = warmup
        while i < len(df) - 1:
            window = df.iloc[:i+1]
            data = {"15m": window, "1h": window, "4h": window}
            signal = self.engine.evaluate(symbol, data)

            if signal and signal.signal != Signal.NONE:
                side = signal.signal.value
                # Match live sizing: include round-trip costs in the risk budget
                # so SL loss ≈ RISK_PER_TRADE_PCT after fees + TDS.
                risk_amount = balance * (RISK_PER_TRADE_PCT / 100.0)
                price_risk  = abs(signal.entry_price - signal.stop_loss)
                cost_per_unit = (
                    self.fee_model.stop_loss_cost_per_unit(
                        signal.entry_price, signal.stop_loss, side,
                    ) if INCLUDE_FEES_IN_SIZING else 0.0
                )
                denom = price_risk + cost_per_unit
                qty = risk_amount / denom if denom > 0 else 0

                if qty > 0:
                    exit_price, exit_reason, exit_i = self._find_exit(
                        df, i + 1, signal
                    )
                    gross_pnl = (exit_price - signal.entry_price) * qty
                    if signal.signal == Signal.SHORT:
                        gross_pnl = -gross_pnl

                    if BACKTEST_APPLY_FEES:
                        costs = self.fee_model.round_trip_cost(
                            signal.entry_price, exit_price, qty, side,
                        )
                        pnl = gross_pnl - costs.total
                    else:
                        pnl = gross_pnl

                    pnl_pct = pnl / (signal.entry_price * qty) * 100

                    trade = BacktestTrade(
                        signal=signal.signal.value,
                        entry_idx=i,
                        entry_price=signal.entry_price,
                        exit_price=exit_price,
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit,
                        qty=qty,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        exit_reason=exit_reason,
                        strategy=signal.strategy_name,
                    )
                    trades.append(trade)
                    balance += pnl
                    i = exit_i + 1
                    continue

            i += 1

        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            trades=trades,
            initial_balance=self.initial_balance,
            final_balance=balance,
        )

    @staticmethod
    def _find_exit(df: pd.DataFrame, start: int,
                    signal: TradeSignal) -> tuple[float, str, int]:
        """Scan forward candles to find when SL or TP is hit."""
        is_long = signal.signal == Signal.LONG
        max_bars = min(start + 200, len(df))   # 200 bar max hold time

        for j in range(start, max_bars):
            row = df.iloc[j]
            if is_long:
                if row["low"] <= signal.stop_loss:
                    return signal.stop_loss, "STOP_LOSS", j
                if row["high"] >= signal.take_profit:
                    return signal.take_profit, "TAKE_PROFIT", j
            else:
                if row["high"] >= signal.stop_loss:
                    return signal.stop_loss, "STOP_LOSS", j
                if row["low"] <= signal.take_profit:
                    return signal.take_profit, "TAKE_PROFIT", j

        # Timeout — close at last candle close
        return df.iloc[max_bars - 1]["close"], "TIMEOUT", max_bars - 1
