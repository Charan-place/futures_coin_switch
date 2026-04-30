"""
Risk Manager — position sizing, drawdown guards, circuit breakers.
Uses Kelly Criterion with conservative half-Kelly for position sizing.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime, date

from config.settings import (
    RISK_PER_TRADE_PCT, MAX_PORTFOLIO_RISK_PCT,
    MAX_DAILY_LOSS_PCT, MAX_DRAWDOWN_PCT,
    MAX_CONCURRENT_TRADES, MAX_CONSECUTIVE_LOSSES,
    DEFAULT_LEVERAGE, MAX_LEVERAGE, MIN_ORDER_SIZE_USDT,
    INCLUDE_FEES_IN_SIZING,
)
from core.fees import from_settings as build_fee_model
from agent.strategy_agent import get_agent
from monitoring.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TradeRecord:
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    strategy: str = ""
    risk_amount: float = 0.0   # USDT risked at SL — used for R-multiple math


class RiskManager:
    def __init__(self, initial_balance: float = 1000.0):
        self.initial_balance = initial_balance
        self.peak_balance = initial_balance
        self.current_balance = initial_balance

        self.daily_pnl: float = 0.0
        self.daily_date: date = datetime.utcnow().date()

        self.open_risk: float = 0.0          # total % at risk in open trades
        self.open_positions: int = 0
        self.consecutive_losses: int = 0

        self.trade_history: List[TradeRecord] = []
        self._trading_halted: bool = False
        self._halt_reason: str = ""

        self.fee_model = build_fee_model()
        self.agent = get_agent()

    # ─── Balance Updates ──────────────────────────────────────────────────────

    def update_balance(self, new_balance: float):
        self._reset_daily_if_new_day()
        self.current_balance = new_balance
        if new_balance > self.peak_balance:
            self.peak_balance = new_balance
        self._check_circuit_breakers()

    def record_trade(self, record: TradeRecord):
        self.trade_history.append(record)
        self._reset_daily_if_new_day()
        self.daily_pnl += record.pnl
        self.current_balance += record.pnl

        if record.pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        self.open_positions = max(0, self.open_positions - 1)
        self._check_circuit_breakers()

        # Feed the online learner. Each strategy that voted in confluence
        # gets credit/blame proportional to the trade's R-multiple.
        try:
            risk = record.risk_amount or (
                abs(record.entry_price - record.exit_price) * record.quantity or 1e-9
            )
            r_multiple = record.pnl / risk if risk > 0 else 0.0
            for sname in [s.strip() for s in record.strategy.split("+") if s.strip()]:
                self.agent.record_outcome(
                    strategy=sname, symbol=record.symbol,
                    r_multiple=r_multiple, pnl=record.pnl,
                )
        except Exception as e:
            logger.warning(f"agent update skipped: {e}")

    def _reset_daily_if_new_day(self):
        today = datetime.utcnow().date()
        if today != self.daily_date:
            self.daily_pnl = 0.0
            self.daily_date = today
            if self._trading_halted and "daily" in self._halt_reason:
                self._trading_halted = False
                self._halt_reason = ""
                logger.info("Daily reset — trading resumed")

    # ─── Position Sizing ──────────────────────────────────────────────────────

    def calculate_position_size(self, entry: float, stop_loss: float,
                                 leverage: int = DEFAULT_LEVERAGE,
                                 side: str = "LONG") -> float:
        """
        Returns quantity to trade.

        Risk model:
          loss_at_stop = qty × |entry − stop_loss|        (price move)
                       + qty × cost_per_unit_at_stop      (fees + GST + TDS)
        We solve qty so that this total = RISK_PER_TRADE_PCT × balance.

        This is critical for India: TDS (1% of notional) by itself can dwarf
        the price-risk component on tight stops, turning a "1% risk" trade
        into a multi-% loss if costs are ignored.
        """
        balance = self.current_balance
        risk_amount = balance * (RISK_PER_TRADE_PCT / 100.0)
        price_risk = abs(entry - stop_loss)

        if price_risk <= 0:
            return 0.0

        cost_per_unit = (
            self.fee_model.stop_loss_cost_per_unit(entry, stop_loss, side)
            if INCLUDE_FEES_IN_SIZING
            else 0.0
        )
        denom = price_risk + cost_per_unit
        if denom <= 0:
            return 0.0

        quantity = risk_amount / denom

        # Apply leverage cap: don't let notional value exceed balance × max_leverage
        max_notional = balance * leverage
        max_qty_by_leverage = max_notional / entry
        quantity = min(quantity, max_qty_by_leverage)

        # Minimum order size check
        if quantity * entry < MIN_ORDER_SIZE_USDT:
            logger.warning(f"Position too small (${quantity * entry:.2f}). Min is ${MIN_ORDER_SIZE_USDT}")
            return 0.0

        if INCLUDE_FEES_IN_SIZING and cost_per_unit > 0:
            logger.debug(
                f"Sized w/ costs: price_risk/u=${price_risk:.6f} cost/u=${cost_per_unit:.6f} "
                f"qty={quantity:.6f} (cost share = {cost_per_unit/denom*100:.1f}% of risk budget)"
            )

        return round(quantity, 6)

    def kelly_position_size(self, win_rate: float, rr_ratio: float,
                            entry: float) -> float:
        """
        Half-Kelly criterion.
        win_rate: 0.0–1.0
        rr_ratio: reward/risk (e.g. 2.0 for 1:2 R:R)
        """
        kelly = (win_rate * rr_ratio - (1 - win_rate)) / rr_ratio
        half_kelly_pct = max(0, kelly / 2) * 100   # use half-Kelly for safety
        capped = min(half_kelly_pct, RISK_PER_TRADE_PCT)
        risk_amount = self.current_balance * (capped / 100.0)
        return risk_amount / entry

    # ─── Guards ───────────────────────────────────────────────────────────────

    def can_trade(self) -> tuple[bool, str]:
        """Returns (allowed, reason). Reason is empty string if allowed."""
        if self._trading_halted:
            return False, self._halt_reason

        # Circuit breakers
        checks = self._check_circuit_breakers()
        if checks:
            return False, checks

        # Max concurrent trades
        if self.open_positions >= MAX_CONCURRENT_TRADES:
            return False, f"Max concurrent trades reached ({MAX_CONCURRENT_TRADES})"

        # Portfolio heat
        if self.open_risk >= MAX_PORTFOLIO_RISK_PCT:
            return False, f"Portfolio risk limit hit ({self.open_risk:.1f}% / {MAX_PORTFOLIO_RISK_PCT}%)"

        return True, ""

    def _check_circuit_breakers(self) -> str:
        """Returns halt reason string or '' if OK."""
        # Daily loss limit
        daily_loss_pct = abs(self.daily_pnl) / self.initial_balance * 100
        if self.daily_pnl < 0 and daily_loss_pct >= MAX_DAILY_LOSS_PCT:
            reason = f"Daily loss limit hit: {daily_loss_pct:.1f}% (limit {MAX_DAILY_LOSS_PCT}%)"
            self._halt(reason)
            return reason

        # Max drawdown
        if self.peak_balance > 0:
            drawdown_pct = (self.peak_balance - self.current_balance) / self.peak_balance * 100
            if drawdown_pct >= MAX_DRAWDOWN_PCT:
                reason = f"Max drawdown hit: {drawdown_pct:.1f}% (limit {MAX_DRAWDOWN_PCT}%)"
                self._halt(reason)
                return reason

        # Consecutive losses
        if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            reason = f"Max consecutive losses hit: {self.consecutive_losses}"
            self._halt(reason)
            return reason

        return ""

    def _halt(self, reason: str):
        if not self._trading_halted:
            self._trading_halted = True
            self._halt_reason = reason
            logger.critical(f"TRADING HALTED: {reason}")

    def resume(self):
        self._trading_halted = False
        self._halt_reason = ""
        self.consecutive_losses = 0
        logger.info("Trading resumed manually")

    def open_trade(self, risk_pct: float):
        self.open_positions += 1
        self.open_risk += risk_pct

    def close_trade(self, risk_pct: float):
        self.open_positions = max(0, self.open_positions - 1)
        self.open_risk = max(0.0, self.open_risk - risk_pct)

    # ─── Stats ────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        wins   = [t for t in self.trade_history if t.pnl > 0]
        losses = [t for t in self.trade_history if t.pnl <= 0]
        total  = len(self.trade_history)
        win_rate = len(wins) / total if total else 0
        avg_win  = sum(t.pnl for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0

        drawdown = 0.0
        if self.peak_balance > 0:
            drawdown = (self.peak_balance - self.current_balance) / self.peak_balance * 100

        return {
            "balance": round(self.current_balance, 2),
            "peak_balance": round(self.peak_balance, 2),
            "total_trades": total,
            "win_rate": round(win_rate * 100, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "drawdown_pct": round(drawdown, 2),
            "consecutive_losses": self.consecutive_losses,
            "open_positions": self.open_positions,
            "trading_halted": self._trading_halted,
            "halt_reason": self._halt_reason,
        }
