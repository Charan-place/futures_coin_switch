"""
Strategy 2: Support/Resistance Breakout with Volume Confirmation
─────────────────────────────────────────────────────────────────
Long:  Price closes above resistance + volume > 1.5× average + RSI > 50
Short: Price closes below support   + volume > 1.5× average + RSI < 50

SL:  just below/above the broken level
TP:  2× ATR from entry
"""
import pandas as pd
from strategies.base_strategy import BaseStrategy, TradeSignal, Signal
from indicators.technical import find_sr_levels
from config.settings import (
    ATR_SL_MULTIPLIER, ATR_TP_MULTIPLIER,
    VOLUME_BREAKOUT_MULT, ADX_TREND_THRESHOLD,
)


class BreakoutStrategy(BaseStrategy):
    name = "BREAKOUT"

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        if len(df) < 50:
            return self._no_signal(symbol, "warmup<50 bars")

        row  = df.iloc[-1]
        prev = df.iloc[-2]

        price     = row["close"]
        rsi_val   = row.get("rsi", 50)
        atr_val   = row.get("atr", price * 0.01)
        vol_ratio = row.get("vol_ratio", 1.0)

        support, resistance = find_sr_levels(df)

        # ── Bullish breakout ──────────────────────────────────────────────────
        adx_val = row.get("adx", 0)

        broke_up = prev["close"] <= resistance and row["close"] > resistance
        if (broke_up and vol_ratio >= VOLUME_BREAKOUT_MULT and rsi_val > 50
                and adx_val >= ADX_TREND_THRESHOLD):
            sl = resistance - atr_val * 0.5   # just below broken resistance
            tp = price + atr_val * ATR_TP_MULTIPLIER
            confidence = self._confidence(vol_ratio, rsi_val, "long")
            return TradeSignal(
                signal=Signal.LONG,
                strategy_name=self.name,
                symbol=symbol,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                confidence=confidence,
                reason=f"Breakout above resistance={resistance:.4f} | VolRatio={vol_ratio:.2f} | RSI={rsi_val:.1f}",
                atr=atr_val,
                extra={"support": support, "resistance": resistance},
            )

        # ── Bearish breakdown ─────────────────────────────────────────────────
        broke_dn = prev["close"] >= support and row["close"] < support
        if (broke_dn and vol_ratio >= VOLUME_BREAKOUT_MULT and rsi_val < 50
                and adx_val >= ADX_TREND_THRESHOLD):
            sl = support + atr_val * 0.5    # just above broken support
            tp = price - atr_val * ATR_TP_MULTIPLIER
            confidence = self._confidence(vol_ratio, rsi_val, "short")
            return TradeSignal(
                signal=Signal.SHORT,
                strategy_name=self.name,
                symbol=symbol,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                confidence=confidence,
                reason=f"Breakdown below support={support:.4f} | VolRatio={vol_ratio:.2f} | RSI={rsi_val:.1f}",
                atr=atr_val,
                extra={"support": support, "resistance": resistance},
            )

        # Detailed rejection reason
        if not (broke_up or broke_dn):
            return self._no_signal(
                symbol,
                f"no break (price={price:.6g} S={support:.6g} R={resistance:.6g})",
            )
        if vol_ratio < VOLUME_BREAKOUT_MULT:
            return self._no_signal(
                symbol,
                f"break but vol={vol_ratio:.2f}x < {VOLUME_BREAKOUT_MULT:.2f}x",
            )
        if adx_val < ADX_TREND_THRESHOLD:
            return self._no_signal(symbol, f"break but ADX={adx_val:.1f} < {ADX_TREND_THRESHOLD}")
        return self._no_signal(symbol, "break but RSI on wrong side")

    def _confidence(self, vol_ratio: float, rsi: float, direction: str) -> float:
        score = 0.4
        if vol_ratio >= 2.0:
            score += 0.3
        elif vol_ratio >= 1.5:
            score += 0.15
        if direction == "long":
            if rsi > 60:
                score += 0.2
            elif rsi > 50:
                score += 0.1
        else:
            if rsi < 40:
                score += 0.2
            elif rsi < 50:
                score += 0.1
        return min(score, 1.0)
