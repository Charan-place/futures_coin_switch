"""
Strategy 1: Dual EMA Crossover + RSI Confirmation
──────────────────────────────────────────────────
Long:  EMA9 crosses above EMA21 AND RSI > 55 AND ADX > 20
Short: EMA9 crosses below EMA21 AND RSI < 45 AND ADX > 20

SL:  entry ± 1.5 × ATR
TP:  entry ± 3.0 × ATR  (1:2 R:R)
"""
import pandas as pd
from strategies.base_strategy import BaseStrategy, TradeSignal, Signal
from config.settings import (
    EMA_FAST, EMA_MID, ATR_SL_MULTIPLIER, ATR_TP_MULTIPLIER,
    RSI_BULL_THRESHOLD, RSI_BEAR_THRESHOLD, ADX_TREND_THRESHOLD,
)


class EmaRsiStrategy(BaseStrategy):
    name = "EMA_RSI"

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        if len(df) < 30:
            return self._no_signal(symbol, "warmup<30 bars")

        row  = df.iloc[-1]
        prev = df.iloc[-2]

        ema_fast_col = f"ema{EMA_FAST}"
        ema_mid_col  = f"ema{EMA_MID}"

        if ema_fast_col not in df.columns or ema_mid_col not in df.columns:
            return self._no_signal(symbol, "missing EMAs")

        cur_fast, cur_mid = row[ema_fast_col],  row[ema_mid_col]
        prv_fast, prv_mid = prev[ema_fast_col], prev[ema_mid_col]

        rsi_val = row.get("rsi", 50)
        adx_val = row.get("adx", 0)
        atr_val = row.get("atr", row["close"] * 0.01)
        price   = row["close"]

        # ── Long signal: fresh cross OR established stack with momentum ───────
        ema_cross_up = (prv_fast <= prv_mid) and (cur_fast > cur_mid)
        # Pullback-continuation: EMAs already stacked bullish, price reclaimed
        # the fast EMA after a dip. Catches the move when you missed the cross.
        ema_stack_up = cur_fast > cur_mid and price > cur_fast
        pulled_back  = prev["close"] <= prev[ema_fast_col]   # last bar dipped under
        ema_continuation_up = ema_stack_up and pulled_back
        ema_long_trigger = ema_cross_up or ema_continuation_up

        if ema_long_trigger and rsi_val > RSI_BULL_THRESHOLD and adx_val > ADX_TREND_THRESHOLD:
            sl = price - atr_val * ATR_SL_MULTIPLIER
            tp = price + atr_val * ATR_TP_MULTIPLIER
            confidence = self._confidence(adx_val, rsi_val, "long")
            return TradeSignal(
                signal=Signal.LONG,
                strategy_name=self.name,
                symbol=symbol,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                confidence=confidence,
                reason=f"EMA{EMA_FAST} crossed above EMA{EMA_MID} | RSI={rsi_val:.1f} | ADX={adx_val:.1f}",
                atr=atr_val,
            )

        # ── Short signal: fresh cross OR established bearish stack rejection ─
        ema_cross_dn = (prv_fast >= prv_mid) and (cur_fast < cur_mid)
        ema_stack_dn = cur_fast < cur_mid and price < cur_fast
        pulled_up    = prev["close"] >= prev[ema_fast_col]
        ema_continuation_dn = ema_stack_dn and pulled_up
        ema_short_trigger = ema_cross_dn or ema_continuation_dn

        if ema_short_trigger and rsi_val < RSI_BEAR_THRESHOLD and adx_val > ADX_TREND_THRESHOLD:
            sl = price + atr_val * ATR_SL_MULTIPLIER
            tp = price - atr_val * ATR_TP_MULTIPLIER
            confidence = self._confidence(adx_val, rsi_val, "short")
            return TradeSignal(
                signal=Signal.SHORT,
                strategy_name=self.name,
                symbol=symbol,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                confidence=confidence,
                reason=f"EMA{EMA_FAST} crossed below EMA{EMA_MID} | RSI={rsi_val:.1f} | ADX={adx_val:.1f}",
                atr=atr_val,
            )

        # Detailed rejection reason
        if adx_val <= ADX_TREND_THRESHOLD:
            return self._no_signal(symbol, f"ADX={adx_val:.1f} ≤ {ADX_TREND_THRESHOLD}")
        if not (ema_long_trigger or ema_short_trigger):
            return self._no_signal(symbol, "no EMA cross/continuation")
        if ema_long_trigger and rsi_val <= RSI_BULL_THRESHOLD:
            return self._no_signal(symbol, f"long trigger but RSI={rsi_val:.1f} ≤ {RSI_BULL_THRESHOLD}")
        if ema_short_trigger and rsi_val >= RSI_BEAR_THRESHOLD:
            return self._no_signal(symbol, f"short trigger but RSI={rsi_val:.1f} ≥ {RSI_BEAR_THRESHOLD}")
        return self._no_signal(symbol, "filters not met")

    def _confidence(self, adx: float, rsi: float, direction: str) -> float:
        score = 0.5
        if adx > 30:
            score += 0.2
        elif adx > 20:
            score += 0.1
        if direction == "long":
            if rsi > 65:
                score += 0.2
            elif rsi > 55:
                score += 0.1
        else:
            if rsi < 35:
                score += 0.2
            elif rsi < 45:
                score += 0.1
        return min(score, 1.0)
