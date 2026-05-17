"""
Confluence Engine — aggregates signals from all active strategies.

A trade fires only when:
  1. At least MIN_CONFLUENCE_SIGNALS strategies agree on direction, AND
  2. Either ADX > threshold (trending regime) OR an SR_BOUNCE vote is present
     (valid ranging setup), AND
  3. Hype filter passes (volume/OI/session) — meme-coin gate.

Funding-rate bias from the hype filter can veto a signal against the crowd.
"""
from typing import List, Dict, Optional
import pandas as pd

from strategies.base_strategy import BaseStrategy, TradeSignal, Signal
from strategies.ema_rsi_strategy import EmaRsiStrategy
from strategies.breakout_strategy import BreakoutStrategy
from strategies.mtf_trend_strategy import MtfTrendStrategy
from strategies.sr_bounce_strategy import SrBounceStrategy
from strategies.scalp_momentum_strategy import ScalpMomentumStrategy
from strategies.pump_detector import PumpDetectorStrategy
from strategies.hype_filter import HypeFilter
from config.settings import (
    STRATEGY_EMA_RSI, STRATEGY_BREAKOUT, STRATEGY_MTF_TREND, STRATEGY_SR_BOUNCE,
    STRATEGY_SCALP, STRATEGY_PUMP,
    MIN_CONFLUENCE_SIGNALS, ADX_TREND_THRESHOLD, USE_HYPE_FILTER, IS_PAPER,
    MIN_CONFLUENCE_AVG_CONFIDENCE, SOLO_SR_MIN_CONFIDENCE, SOLO_SR_MIN_VOL_RATIO,
    ALLOW_SOLO_TREND, SOLO_TREND_MIN_CONFIDENCE,
    SR_REQUIRE_TREND_ALIGNED,
    REQUIRE_DI_ALIGNMENT, USE_CHOP_FILTER, CHOP_BB_WIDTH_VS_MA_RATIO,
    CONFLUENCE_TP_MERGE_MODE, CONFLUENCE_MIN_RR, CONFLUENCE_MAX_RR,
    INCLUDE_FEES_IN_RR,
)
from core.fees import from_settings as build_fee_model
from agent.strategy_agent import get_agent
from monitoring.logger import get_logger

logger = get_logger(__name__)


class ConfluenceEngine:
    def __init__(self):
        self.strategies: List[BaseStrategy] = []
        if STRATEGY_EMA_RSI:
            self.strategies.append(EmaRsiStrategy())
        if STRATEGY_BREAKOUT:
            self.strategies.append(BreakoutStrategy())
        if STRATEGY_MTF_TREND:
            self.strategies.append(MtfTrendStrategy())
        if STRATEGY_SR_BOUNCE:
            self.strategies.append(SrBounceStrategy())

        # Fast-path strategies: operate on 5m and have solo-fire privileges
        # when their confidence is very high. They bypass the 2-strategy
        # confluence gate because they are already multi-factor internally.
        self.scalp_strategy = ScalpMomentumStrategy() if STRATEGY_SCALP else None
        self.pump_strategy  = PumpDetectorStrategy()  if STRATEGY_PUMP  else None
        self._fast_strategies: List[BaseStrategy] = [
            s for s in [self.scalp_strategy, self.pump_strategy] if s is not None
        ]

        # Standalone helper used to compute 4H trend bias for the SR-alignment
        # filter, even when MTF_TREND itself is disabled.
        self._mtf_helper = MtfTrendStrategy()

        # Hype filter is only strict in LIVE mode. In paper mode we want to see
        # the bot execute so we can observe its behavior — the filter becomes
        # informational (logged but non-blocking).
        self.hype_filter = HypeFilter() if USE_HYPE_FILTER else None
        self.hype_strict = USE_HYPE_FILTER and not IS_PAPER
        self.fee_model = build_fee_model()
        self.agent = get_agent()
        logger.info(
            f"ConfluenceEngine ready: strategies={[s.name for s in self.strategies]} "
            f"hype_strict={self.hype_strict} agent_arms={len(self.agent.arms)} "
            f"agent_trades={self.agent.global_trades}"
        )

    def evaluate_fast(self, symbol: str, df_5m: pd.DataFrame) -> Optional[TradeSignal]:
        """Fast-path evaluation for 5m scalp/pump strategies.
        These strategies are internally multi-factor (VWAP+Supertrend+Volume+StochRSI)
        so they fire solo without the swing-strategy confluence gate.
        Hype filter still applies (volume/funding/deadzone gate).
        """
        if not self._fast_strategies:
            return None

        best: Optional[TradeSignal] = None

        for strategy in self._fast_strategies:
            try:
                sig = strategy.analyze(df_5m, symbol)
                if sig.signal == Signal.NONE:
                    rsn = (sig.reason or "").strip()
                    logger.info(f"[{symbol}] {strategy.name} fast → ∅ ({rsn})")
                    continue

                # Agent confidence multiplier
                mult = self.agent.confidence_multiplier(strategy.name, symbol)
                if mult != 1.0:
                    sig.confidence = max(0.0, min(1.0, sig.confidence * mult))

                logger.info(
                    f"[{symbol}] {strategy.name} fast → {sig.signal.value} "
                    f"conf={sig.confidence:.2f} | {sig.reason[:70]}"
                )

                # Hype filter
                if self.hype_filter is not None:
                    verdict = self.hype_filter.evaluate(symbol, df_5m)
                    logger.info(f"[{symbol}] hype {'OK' if verdict.passed else 'BLOCK'} — {verdict.reason}")
                    if self.hype_strict:
                        if not verdict.passed:
                            continue
                        if verdict.bias == "short" and sig.signal == Signal.LONG:
                            logger.info(f"[{symbol}] funding bias SHORT vetoes LONG (fast)")
                            continue
                        if verdict.bias == "long" and sig.signal == Signal.SHORT:
                            logger.info(f"[{symbol}] funding bias LONG vetoes SHORT (fast)")
                            continue

                # Fee-aware R:R check
                side_str = sig.signal.value
                cost_per_unit = (
                    sig.entry_price * self.fee_model.round_trip_cost_pct(side_str)
                    if INCLUDE_FEES_IN_RR else 0.0
                )
                if sig.signal == Signal.LONG:
                    risk = sig.entry_price - sig.stop_loss + cost_per_unit
                    reward = sig.take_profit - sig.entry_price - cost_per_unit
                else:
                    risk = sig.stop_loss - sig.entry_price + cost_per_unit
                    reward = sig.entry_price - sig.take_profit - cost_per_unit

                net_rr = (reward / risk) if risk > 0 else 0.0
                if net_rr < CONFLUENCE_MIN_RR:
                    logger.info(
                        f"[{symbol}] {strategy.name} fast reject — net R:R={net_rr:.2f} < {CONFLUENCE_MIN_RR}"
                    )
                    continue

                if best is None or sig.confidence > best.confidence:
                    best = sig

            except Exception as e:
                logger.error(f"Fast strategy {strategy.name} error on {symbol}: {e}")

        return best

    def evaluate(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[TradeSignal]:
        df_entry   = data.get("15m") if data.get("15m") is not None else data.get("5m")
        df_confirm = data.get("1h")
        df_trend   = data.get("4h")

        if df_entry is None:
            return None

        signals: List[TradeSignal] = []
        votes_summary: List[str] = []
        for strategy in self.strategies:
            try:
                if strategy.name == "MTF_TREND":
                    sig = strategy.analyze(df_entry, symbol,
                                           df_confirm=df_confirm, df_trend=df_trend)
                else:
                    sig = strategy.analyze(df_entry, symbol)
                if sig.signal != Signal.NONE:
                    mult = self.agent.confidence_multiplier(strategy.name, symbol)
                    if mult != 1.0:
                        sig.confidence = max(0.0, min(1.0, sig.confidence * mult))
                        logger.info(
                            f"[{symbol}] agent → {strategy.name} confidence "
                            f"× {mult:.2f} (now {sig.confidence:.2f})"
                        )
                    signals.append(sig)
                    votes_summary.append(f"{strategy.name}={sig.signal.value}({sig.confidence:.2f})")
                    logger.info(f"[{symbol}] {strategy.name} → {sig.signal.value} "
                                f"conf={sig.confidence:.2f} | {sig.reason}")
                else:
                    rsn = (sig.reason or "").strip()
                    votes_summary.append(f"{strategy.name}=∅" + (f"({rsn})" if rsn else ""))
            except Exception as e:
                logger.error(f"Strategy {strategy.name} error on {symbol}: {e}")
        logger.info(f"[{symbol}] votes: {' '.join(votes_summary) or '(none)'}")

        if not signals:
            return None

        long_sigs  = [s for s in signals if s.signal == Signal.LONG]
        short_sigs = [s for s in signals if s.signal == Signal.SHORT]

        direction: Optional[Signal] = None
        winners: List[TradeSignal] = []
        if len(long_sigs) >= MIN_CONFLUENCE_SIGNALS:
            direction, winners = Signal.LONG, long_sigs
        elif len(short_sigs) >= MIN_CONFLUENCE_SIGNALS:
            direction, winners = Signal.SHORT, short_sigs
        else:
            # Solo SR_BOUNCE: only when level + momentum context is strong enough.
            vol_last = float(df_entry["vol_ratio"].iloc[-1]) if "vol_ratio" in df_entry.columns else 1.0
            solo_sr = next(
                (s for s in signals
                 if s.strategy_name == "SR_BOUNCE"
                 and s.confidence >= SOLO_SR_MIN_CONFIDENCE
                 and vol_last >= SOLO_SR_MIN_VOL_RATIO),
                None,
            )
            # Solo trend escape hatch: a single high-conviction trend strategy
            # gets to fire so the agent can collect outcome data and learn.
            solo_trend = None
            if ALLOW_SOLO_TREND:
                trend_names = {"EMA_RSI", "MTF_TREND", "BREAKOUT"}
                trend_candidates = [
                    s for s in signals
                    if s.strategy_name in trend_names
                    and s.confidence >= SOLO_TREND_MIN_CONFIDENCE
                ]
                if trend_candidates:
                    solo_trend = max(trend_candidates, key=lambda s: s.confidence)

            solo = solo_sr or solo_trend
            if solo is None:
                logger.info(
                    f"[{symbol}] reject — no confluence "
                    f"(L={len(long_sigs)} S={len(short_sigs)} "
                    f"need ≥{MIN_CONFLUENCE_SIGNALS}; "
                    f"solo_SR={'yes' if solo_sr else 'no'} "
                    f"solo_trend={'yes' if solo_trend else 'no'})"
                )
                return None

            # Trend-aligned SR filter: don't fade a strong higher-TF trend.
            if solo is solo_sr and SR_REQUIRE_TREND_ALIGNED:
                trend_bias = self._mtf_helper._get_trend_bias(df_trend if df_trend is not None else df_entry)
                bad_long  = solo_sr.signal == Signal.LONG  and trend_bias == "down"
                bad_short = solo_sr.signal == Signal.SHORT and trend_bias == "up"
                if bad_long or bad_short:
                    logger.info(
                        f"[{symbol}] reject — SR {solo_sr.signal.value} fights 4H {trend_bias} trend"
                    )
                    return None

            direction, winners = solo.signal, [solo]
            logger.info(
                f"[{symbol}] solo path → {solo.strategy_name} {direction.value} "
                f"conf={solo.confidence:.2f}"
            )

        avg_conf = sum(s.confidence for s in winners) / len(winners)
        if avg_conf < MIN_CONFLUENCE_AVG_CONFIDENCE:
            logger.info(
                f"[{symbol}] reject — avg confidence {avg_conf:.2f} < {MIN_CONFLUENCE_AVG_CONFIDENCE}"
            )
            return None

        # Regime check: require a trending tape OR an SR_BOUNCE vote in the mix
        adx_val = float(df_entry["adx"].iloc[-1]) if "adx" in df_entry.columns else 0.0
        has_sr = any(s.strategy_name == "SR_BOUNCE" for s in winners)
        if adx_val < ADX_TREND_THRESHOLD and not has_sr:
            logger.info(f"[{symbol}] reject — ADX={adx_val:.1f}<{ADX_TREND_THRESHOLD}, no SR vote")
            return None

        if USE_CHOP_FILTER and not has_sr:
            if self._is_chop_compression(df_entry):
                logger.info(f"[{symbol}] reject — BB compression (chop), no SR vote")
                return None

        # DMI alignment is a *trend-following* check (DI+ dominant for longs,
        # DI- dominant for shorts). SR_BOUNCE is counter-trend by design — when
        # we're shorting into resistance, DI+ is necessarily still in control.
        # Applying DMI alignment to a solo SR vote vetoes 100% of counter-trend
        # bounces, which is exactly the trade SR_BOUNCE exists to take.
        only_sr_winner = all(s.strategy_name == "SR_BOUNCE" for s in winners)
        if REQUIRE_DI_ALIGNMENT and not only_sr_winner:
            if not self._di_aligns(df_entry, direction):
                dp = float(df_entry["di_plus"].iloc[-1])  if "di_plus"  in df_entry.columns else float("nan")
                dm = float(df_entry["di_minus"].iloc[-1]) if "di_minus" in df_entry.columns else float("nan")
                logger.info(
                    f"[{symbol}] reject — DMI not aligned with {direction.value} "
                    f"(DI+={dp:.1f} DI-={dm:.1f})"
                )
                return None

        # Hype filter gate (meme coin specific). In paper mode it's informational.
        if self.hype_filter is not None:
            verdict = self.hype_filter.evaluate(symbol, df_entry)
            logger.info(f"[{symbol}] hype {'OK' if verdict.passed else 'BLOCK'} — {verdict.reason}")
            if self.hype_strict:
                if not verdict.passed:
                    return None
                if verdict.bias == "short" and direction == Signal.LONG:
                    logger.info(f"[{symbol}] funding bias SHORT vetoes LONG")
                    return None
                if verdict.bias == "long" and direction == Signal.SHORT:
                    logger.info(f"[{symbol}] funding bias LONG vetoes SHORT")
                    return None

        return self._merge(winners, direction)

    @staticmethod
    def _is_chop_compression(df: pd.DataFrame) -> bool:
        if "bb_width" not in df.columns or len(df) < 25:
            return False
        bw = df["bb_width"]
        last = float(bw.iloc[-1])
        ref = float(bw.rolling(20).mean().iloc[-1])
        if ref <= 0 or last <= 0:
            return False
        return last < ref * CHOP_BB_WIDTH_VS_MA_RATIO

    @staticmethod
    def _di_aligns(df: pd.DataFrame, direction: Signal) -> bool:
        if "di_plus" not in df.columns or "di_minus" not in df.columns:
            return True
        dp = float(df["di_plus"].iloc[-1])
        dm = float(df["di_minus"].iloc[-1])
        if direction == Signal.LONG:
            return dp >= dm
        if direction == Signal.SHORT:
            return dm >= dp
        return True

    def _merge(self, signals: List[TradeSignal], direction: Signal) -> TradeSignal:
        base = signals[0]
        entry = base.entry_price
        avg_confidence = sum(s.confidence for s in signals) / len(signals)

        if direction == Signal.LONG:
            sl = min(s.stop_loss for s in signals)
        else:
            sl = max(s.stop_loss for s in signals)

        if CONFLUENCE_TP_MERGE_MODE == "conservative":
            if direction == Signal.LONG:
                tp = min(s.take_profit for s in signals)
            else:
                tp = max(s.take_profit for s in signals)
        else:
            tp = self._weighted_take_profit(signals, direction, entry, sl)

        strategy_names = " + ".join(s.strategy_name for s in signals)
        reasons = " | ".join(s.reason for s in signals)

        return TradeSignal(
            signal=direction,
            strategy_name=strategy_names,
            symbol=base.symbol,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            confidence=min(avg_confidence + 0.1 * (len(signals) - 1), 1.0),
            reason=f"[CONFLUENCE x{len(signals)}] {reasons}",
            atr=base.atr,
            extra={"signal_count": len(signals), "tp_merge": CONFLUENCE_TP_MERGE_MODE},
        )

    def _weighted_take_profit(
        self,
        signals: List[TradeSignal],
        direction: Signal,
        entry: float,
        sl: float,
    ) -> float:
        """Blend targets by strategy confidence; clamp to [min_rr, max_rr] × risk.

        When `INCLUDE_FEES_IN_RR` is on, push TP outward enough that the
        **post-cost** R:R hits the floor — otherwise a 1:1.5 raw R:R becomes
        a losing trade after fees + GST + TDS on an Indian futures account.
        """
        weights = [max(s.confidence, 0.05) for s in signals]
        wtot = sum(weights)
        raw_tp = sum(s.take_profit * w for s, w in zip(signals, weights)) / wtot

        side_str = "LONG" if direction == Signal.LONG else "SHORT"
        # Approx round-trip cost as fraction of notional, expressed in price units.
        cost_per_unit = (
            entry * self.fee_model.round_trip_cost_pct(side_str)
            if INCLUDE_FEES_IN_RR
            else 0.0
        )

        if direction == Signal.LONG:
            risk = entry - sl
            if risk <= 0:
                return raw_tp
            net_risk = risk + cost_per_unit
            min_tp = entry + CONFLUENCE_MIN_RR * net_risk + cost_per_unit
            max_tp = entry + CONFLUENCE_MAX_RR * net_risk + cost_per_unit
            return max(min_tp, min(raw_tp, max_tp))

        risk = sl - entry
        if risk <= 0:
            return raw_tp
        net_risk = risk + cost_per_unit
        # Short TP is below entry; furthest target = entry − max_rr·net_risk.
        lower = entry - CONFLUENCE_MAX_RR * net_risk - cost_per_unit
        upper = entry - CONFLUENCE_MIN_RR * net_risk - cost_per_unit
        return max(lower, min(upper, raw_tp))
