"""
Trade Executor — takes a TradeSignal and executes it with proper
entry + stop-loss + take-profit orders on CoinSwitch Futures.

In paper mode, simulates execution without real orders.
"""
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from datetime import datetime

from core.api_client import CoinSwitchClient, CoinSwitchAPIError
from strategies.base_strategy import TradeSignal, Signal
from risk.risk_manager import RiskManager, TradeRecord
from config.settings import (
    IS_PAPER, DEFAULT_LEVERAGE, PARTIAL_TP_RATIO,
    PARTIAL_TP_AT_1R, MOVE_SL_TO_BE_AT_1R, PARTIAL_TP_AT_1R_RATIO,
)
from monitoring.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OpenTrade:
    trade_id: str
    symbol: str
    side: str                   # LONG or SHORT
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_order_id: str = ""
    sl_order_id: str = ""
    tp_order_id: str = ""
    strategy: str = ""
    opened_at: datetime = field(default_factory=datetime.utcnow)
    risk_pct: float = 0.0
    atr: float = 0.0
    # Win-rate management state
    initial_quantity: float = 0.0       # snapshot at entry, before any partial fills
    initial_stop_loss: float = 0.0      # original SL — used to compute the 1R level
    partial_taken_at_1r: bool = False   # have we already scaled out at 1R?
    breakeven_active: bool = False      # has SL been moved to entry?
    realised_pnl: float = 0.0           # cumulative net PnL from partial closes so far

    @property
    def is_long(self) -> bool:
        return self.side == "LONG"

    def pnl(self, current_price: float) -> float:
        if self.is_long:
            return (current_price - self.entry_price) * self.quantity
        return (self.entry_price - current_price) * self.quantity

    def pnl_pct(self, current_price: float) -> float:
        return self.pnl(current_price) / (self.entry_price * self.quantity) * 100


class TradeExecutor:
    def __init__(self, client: CoinSwitchClient, risk_mgr: RiskManager):
        self.client = client
        self.risk_mgr = risk_mgr
        self.open_trades: Dict[str, OpenTrade] = {}   # trade_id → OpenTrade
        self._trade_counter = 0

    def execute_signal(self, signal: TradeSignal, leverage: int = DEFAULT_LEVERAGE) -> Optional[OpenTrade]:
        """Main entry: validate → size → place orders → record."""
        allowed, reason = self.risk_mgr.can_trade()
        if not allowed:
            logger.warning(f"Trade blocked: {reason}")
            return None

        if not signal.is_valid():
            logger.warning(f"Invalid signal for {signal.symbol}: R:R={signal.risk_reward:.2f}")
            return None

        side = signal.signal.value
        qty = self.risk_mgr.calculate_position_size(
            signal.entry_price, signal.stop_loss, leverage, side=side,
        )
        if qty <= 0:
            logger.warning(f"Quantity is 0 for {signal.symbol} — skipping")
            return None

        # Cost preview — what the round-trip would actually cost on this trade.
        sl_costs = self.risk_mgr.fee_model.round_trip_cost(
            signal.entry_price, signal.stop_loss, qty, side,
        )
        tp_costs = self.risk_mgr.fee_model.round_trip_cost(
            signal.entry_price, signal.take_profit, qty, side,
        )
        gross_loss_at_sl   = abs(signal.entry_price - signal.stop_loss) * qty
        gross_win_at_tp    = abs(signal.take_profit - signal.entry_price) * qty
        net_loss_at_sl     = gross_loss_at_sl + sl_costs.total
        net_win_at_tp      = gross_win_at_tp - tp_costs.total
        risk_pct = net_loss_at_sl / self.risk_mgr.current_balance * 100
        net_rr   = (net_win_at_tp / net_loss_at_sl) if net_loss_at_sl > 0 else 0.0

        logger.info(
            f"Executing {side} {signal.symbol} | qty={qty:.6f} "
            f"entry={signal.entry_price:.6f} SL={signal.stop_loss:.6f} TP={signal.take_profit:.6f}"
        )
        logger.info(
            f"  Costs SL: fee=${sl_costs.entry_fee + sl_costs.exit_fee:.4f} "
            f"GST=${sl_costs.gst:.4f} TDS=${sl_costs.tds:.4f} "
            f"({sl_costs.pct_of_notional:.2f}% of notional)"
        )
        logger.info(
            f"  Net @ SL: -${net_loss_at_sl:.4f} ({risk_pct:.2f}% of bal) | "
            f"Net @ TP: +${net_win_at_tp:.4f} | Net R:R={net_rr:.2f}"
        )

        if net_win_at_tp <= 0:
            logger.warning(
                f"Skipping {signal.symbol}: TP barely covers fees+TDS "
                f"(net_win=${net_win_at_tp:.4f}). Widen TP or reduce leverage."
            )
            return None

        if IS_PAPER:
            return self._paper_execute(signal, qty, risk_pct)
        return self._live_execute(signal, qty, leverage, risk_pct)

    # ─── Live Execution ───────────────────────────────────────────────────────

    def _live_execute(self, signal: TradeSignal, qty: float,
                      leverage: int, risk_pct: float) -> Optional[OpenTrade]:
        try:
            # Set leverage
            self.client.set_leverage(signal.symbol, leverage)

            side       = "BUY"  if signal.signal == Signal.LONG else "SELL"
            close_side = "SELL" if signal.signal == Signal.LONG else "BUY"

            # Entry market order
            entry_resp     = self.client.place_market_order(signal.symbol, side, qty)
            entry_order_id = self._extract_order_id(entry_resp)

            time.sleep(0.5)  # brief pause for fill

            # Stop loss
            sl_order_id = ""
            try:
                sl_resp     = self.client.place_stop_loss(signal.symbol, close_side, qty, signal.stop_loss)
                sl_order_id = self._extract_order_id(sl_resp)
            except CoinSwitchAPIError as e:
                logger.error(f"SL order failed {signal.symbol}: {e}")

            # Take profit
            tp_order_id = ""
            try:
                tp_resp     = self.client.place_take_profit(signal.symbol, close_side, qty, signal.take_profit)
                tp_order_id = self._extract_order_id(tp_resp)
            except CoinSwitchAPIError as e:
                logger.error(f"TP order failed {signal.symbol}: {e}")

            trade = self._register_trade(signal, qty, risk_pct,
                                          entry_order_id, sl_order_id, tp_order_id)
            self.risk_mgr.open_trade(risk_pct)
            return trade

        except CoinSwitchAPIError as e:
            logger.error(f"Execution failed {signal.symbol}: {e}")
            return None

    # ─── Paper Execution ──────────────────────────────────────────────────────

    def _paper_execute(self, signal: TradeSignal, qty: float,
                       risk_pct: float) -> OpenTrade:
        trade = self._register_trade(
            signal, qty, risk_pct,
            f"PAPER-ENTRY-{self._trade_counter}",
            f"PAPER-SL-{self._trade_counter}",
            f"PAPER-TP-{self._trade_counter}",
        )
        self.risk_mgr.open_trade(risk_pct)
        logger.info(f"[PAPER] Trade opened: {trade.trade_id}")
        return trade

    # ─── Position Management ──────────────────────────────────────────────────

    def check_and_close_positions(self, current_prices: Dict[str, float]):
        """
        Monitor open paper trades and close them when SL or TP is hit.
        Also handles win-rate management:
          • partial close at 1R
          • SL move to breakeven after 1R
        In live mode, the exchange handles SL/TP orders automatically (partial-
        TP / breakeven-move for live is not yet implemented — single SL/TP only).
        """
        if not IS_PAPER:
            return

        for trade_id, trade in list(self.open_trades.items()):
            price = current_prices.get(trade.symbol)
            if price is None:
                continue

            # ── 1R milestone: scale out + move SL to breakeven (paper only) ──
            if PARTIAL_TP_AT_1R and not trade.partial_taken_at_1r:
                risk_unit = abs(trade.entry_price - trade.initial_stop_loss)
                if risk_unit > 0:
                    one_r_price = (
                        trade.entry_price + risk_unit if trade.is_long
                        else trade.entry_price - risk_unit
                    )
                    hit_1r = (
                        (trade.is_long and price >= one_r_price)
                        or (not trade.is_long and price <= one_r_price)
                    )
                    if hit_1r:
                        self._take_partial_at_1r(trade, price)
                        # After partial, re-check the (possibly new) SL/TP this
                        # tick in case price already gapped past the new BE stop.

            if trade.quantity <= 0:
                # Should not happen, but guard against zero-qty residue.
                del self.open_trades[trade_id]
                continue

            hit_sl = False
            hit_tp = False

            if trade.is_long:
                hit_sl = price <= trade.stop_loss
                hit_tp = price >= trade.take_profit
            else:
                hit_sl = price >= trade.stop_loss
                hit_tp = price <= trade.take_profit

            if hit_sl:
                reason = "BREAKEVEN" if trade.breakeven_active else "STOP_LOSS"
                self._close_paper_trade(trade, price, reason)
            elif hit_tp:
                self._close_paper_trade(trade, price, "TAKE_PROFIT")

    def _take_partial_at_1r(self, trade: OpenTrade, price: float) -> None:
        """Close PARTIAL_TP_AT_1R_RATIO of the position and (optionally) move
        the SL to a *cost-aware* breakeven. The partial PnL is tracked on the
        trade itself and posted as part of the final close to keep R-multiple
        math clean for the agent learner."""
        ratio = max(0.0, min(PARTIAL_TP_AT_1R_RATIO, 1.0))
        if ratio <= 0:
            trade.partial_taken_at_1r = True
            return

        close_qty = trade.quantity * ratio
        if close_qty <= 0:
            trade.partial_taken_at_1r = True
            return

        if trade.is_long:
            gross = (price - trade.entry_price) * close_qty
        else:
            gross = (trade.entry_price - price) * close_qty
        costs = self.risk_mgr.fee_model.round_trip_cost(
            trade.entry_price, price, close_qty, trade.side,
        )
        net = gross - costs.total
        trade.realised_pnl += net
        remaining_qty = trade.quantity - close_qty
        trade.quantity = remaining_qty
        trade.partial_taken_at_1r = True

        if MOVE_SL_TO_BE_AT_1R:
            trade.stop_loss = self._compute_smart_be(
                trade.side, trade.entry_price, remaining_qty, net
            )
            trade.breakeven_active = True

        be_label = (
            f"smart-BE {trade.stop_loss:.6g}" if trade.breakeven_active
            else f"{trade.stop_loss:.6g}"
        )
        logger.info(
            f"[PAPER] 1R partial: {trade.symbol} {trade.side} "
            f"closed {close_qty:.6g} @ {price:.6g} (net=${net:+.4f}) | "
            f"remaining={remaining_qty:.6g} | SL→{be_label}"
        )

    def _compute_smart_be(
        self, side: str, entry_price: float,
        remaining_qty: float, partial_net_pnl: float,
    ) -> float:
        """SL price such that the *total* trade PnL is non-negative even if the
        remaining leg closes at the new SL — accounting for fee + GST + TDS on
        the remaining leg. Required because India's 1% TDS lands on every sell
        regardless of price move; a naive entry-price BE still bleeds ~1% on
        the remaining leg.

        Math (LONG): partial + (new_SL − entry)·qty − cost_per_unit·qty ≥ 0
                  ⇒ new_SL ≥ entry + cost_per_unit − partial/qty
        Mirrored for SHORT. A +5% safety factor on costs absorbs the 2nd-order
        error from cost depending on the (unknown) exit price.
        """
        if remaining_qty <= 0:
            return entry_price
        # round_trip_cost_pct returns a *fraction* (e.g. 0.01118 for 1.118%),
        # already in the right form to multiply against price.
        cost_frac = self.risk_mgr.fee_model.round_trip_cost_pct(side)
        cost_per_unit = entry_price * cost_frac * 1.05   # 5% safety buffer
        delta = cost_per_unit - (partial_net_pnl / remaining_qty)
        if side == "LONG":
            # delta>0 → SL above entry (cushion); delta<0 → SL below entry (lock-in profit)
            return max(entry_price + delta, 0.0)
        return entry_price - delta

    def _close_paper_trade(self, trade: OpenTrade, exit_price: float, reason: str):
        gross_pnl = trade.pnl(exit_price)   # remaining qty only
        costs = self.risk_mgr.fee_model.round_trip_cost(
            trade.entry_price, exit_price, trade.quantity, trade.side,
        )
        leg_pnl = gross_pnl - costs.total
        total_pnl = leg_pnl + trade.realised_pnl

        # Use *original* qty + *original* SL for accounting so the R-multiple
        # and risk_amount reflect the full intended trade — this is what the
        # agent learner uses to credit/blame the strategy.
        notional = trade.entry_price * trade.initial_quantity
        pnl_pct  = (total_pnl / notional * 100) if notional > 0 else 0.0
        risk_amount = abs(trade.entry_price - trade.initial_stop_loss) * trade.initial_quantity

        record = TradeRecord(
            symbol=trade.symbol,
            side=trade.side,
            entry_price=trade.entry_price,
            exit_price=exit_price,
            quantity=trade.initial_quantity,
            pnl=total_pnl,
            pnl_pct=pnl_pct,
            strategy=trade.strategy,
            risk_amount=risk_amount,
        )
        self.risk_mgr.record_trade(record)
        self.risk_mgr.close_trade(trade.risk_pct)
        del self.open_trades[trade.trade_id]

        if total_pnl > 0:
            emoji = "✅"
        elif reason == "BREAKEVEN":
            emoji = "➖"
        else:
            emoji = "❌"
        partial_note = (
            f" (incl. ${trade.realised_pnl:+.4f} 1R partial)"
            if trade.partial_taken_at_1r else ""
        )
        logger.info(
            f"{emoji} [PAPER] {reason}: {trade.symbol} {trade.side} "
            f"entry={trade.entry_price:.6g} exit={exit_price:.6g} "
            f"net=${total_pnl:+.4f}{partial_note} ({pnl_pct:+.2f}%)"
        )

    def close_live_position(self, trade: OpenTrade, current_price: float):
        """Manually close a live position."""
        try:
            side = "LONG" if trade.is_long else "SHORT"
            self.client.close_position(trade.symbol, side, trade.quantity)

            # Cancel remaining SL/TP orders
            for oid in [trade.sl_order_id, trade.tp_order_id]:
                if oid and not oid.startswith("PAPER"):
                    try:
                        self.client.cancel_order(oid)
                    except Exception:
                        pass

            pnl = trade.pnl(current_price)
            record = TradeRecord(
                symbol=trade.symbol, side=trade.side,
                entry_price=trade.entry_price, exit_price=current_price,
                quantity=trade.quantity, pnl=pnl,
                pnl_pct=trade.pnl_pct(current_price), strategy=trade.strategy,
                risk_amount=abs(trade.entry_price - trade.stop_loss) * trade.quantity,
            )
            self.risk_mgr.record_trade(record)
            self.risk_mgr.close_trade(trade.risk_pct)
            del self.open_trades[trade.trade_id]

        except CoinSwitchAPIError as e:
            logger.error(f"Failed to close position {trade.trade_id}: {e}")

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _register_trade(self, signal: TradeSignal, qty: float, risk_pct: float,
                         entry_oid: str, sl_oid: str, tp_oid: str) -> OpenTrade:
        self._trade_counter += 1
        trade_id = f"T{self._trade_counter:04d}_{signal.symbol.replace('/', '')}"
        trade = OpenTrade(
            trade_id=trade_id,
            symbol=signal.symbol,
            side=signal.signal.value,
            quantity=qty,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            entry_order_id=entry_oid,
            sl_order_id=sl_oid,
            tp_order_id=tp_oid,
            strategy=signal.strategy_name,
            risk_pct=risk_pct,
            atr=signal.atr,
            initial_quantity=qty,
            initial_stop_loss=signal.stop_loss,
        )
        self.open_trades[trade_id] = trade
        return trade

    @staticmethod
    def _extract_order_id(resp: Dict) -> str:
        if isinstance(resp, dict):
            return (resp.get("data", {}) or {}).get("orderId",
                    resp.get("orderId", resp.get("order_id", "")))
        return ""
