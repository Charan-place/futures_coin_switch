"""
Strategy 3: Multi-Timeframe Trend Following
────────────────────────────────────────────
Uses 3 timeframes:
  • Trend TF (4h):  50 EMA > 200 EMA = uptrend; MACD above zero
  • Confirm TF (1h): RSI > 50, price above 21 EMA
  • Entry TF (15m): EMA9 cross + RSI confirmation

All three must align before a trade is taken.
"""
import pandas as pd
from typing import Dict, Optional
from strategies.base_strategy import BaseStrategy, TradeSignal, Signal
from config.settings import (
    EMA_FAST, EMA_MID, EMA_SLOW, EMA_TREND,
    ATR_SL_MULTIPLIER, ATR_TP_MULTIPLIER,
    RSI_BULL_THRESHOLD, RSI_BEAR_THRESHOLD,
    ADX_TREND_THRESHOLD,
)


class MtfTrendStrategy(BaseStrategy):
    name = "MTF_TREND"

    def analyze(self, df: pd.DataFrame, symbol: str,
                df_confirm: Optional[pd.DataFrame] = None,
                df_trend: Optional[pd.DataFrame] = None) -> TradeSignal:
        """
        df        = entry timeframe (15m)
        df_confirm = confirmation timeframe (1h)
        df_trend   = trend timeframe (4h)
        """
        if len(df) < 50:
            return self._no_signal(symbol, "warmup<50 bars")

        # ── Trend direction from 4H ────────────────────────────────────────
        trend_bias = self._get_trend_bias(df_trend if df_trend is not None else df)

        # ── Confirm from 1H ───────────────────────────────────────────────
        confirm_ok = self._confirm_signal(df_confirm if df_confirm is not None else df,
                                          trend_bias)

        if not confirm_ok:
            if trend_bias == "neutral":
                return self._no_signal(symbol, "4H trend neutral")
            return self._no_signal(symbol, f"4H {trend_bias} but 1H not confirming")

        # ── Entry signal from 15M ─────────────────────────────────────────
        row  = df.iloc[-1]
        prev = df.iloc[-2]

        ema_fast_col = f"ema{EMA_FAST}"
        ema_mid_col  = f"ema{EMA_MID}"

        if ema_fast_col not in df.columns:
            return self._no_signal(symbol, "missing EMAs on 15m")

        cur_fast, cur_mid = row[ema_fast_col], row[ema_mid_col]
        prv_fast, prv_mid = prev[ema_fast_col], prev[ema_mid_col]

        rsi_val = row.get("rsi", 50)
        atr_val = row.get("atr", row["close"] * 0.01)
        adx_val = row.get("adx", 0)
        price   = row["close"]

        # ── Long ──────────────────────────────────────────────────────────
        if trend_bias == "up":
            ema_cross = (prv_fast <= prv_mid) and (cur_fast > cur_mid)
            ema_continuation = cur_fast > cur_mid and price > cur_fast and prev["close"] <= prev[ema_fast_col]
            ema_entry = ema_cross or ema_continuation
            if ema_entry and rsi_val > RSI_BULL_THRESHOLD and adx_val > ADX_TREND_THRESHOLD:
                sl = price - atr_val * ATR_SL_MULTIPLIER
                tp = price + atr_val * ATR_TP_MULTIPLIER
                confidence = self._confidence(adx_val, rsi_val, "long", all_tf=True)
                return TradeSignal(
                    signal=Signal.LONG,
                    strategy_name=self.name,
                    symbol=symbol,
                    entry_price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    confidence=confidence,
                    reason=f"MTF LONG: 4H uptrend + 1H confirmed + 15M EMA cross | RSI={rsi_val:.1f} | ADX={adx_val:.1f}",
                    atr=atr_val,
                )

        # ── Short ─────────────────────────────────────────────────────────
        if trend_bias == "down":
            ema_cross = (prv_fast >= prv_mid) and (cur_fast < cur_mid)
            ema_continuation = cur_fast < cur_mid and price < cur_fast and prev["close"] >= prev[ema_fast_col]
            ema_entry = ema_cross or ema_continuation
            if ema_entry and rsi_val < RSI_BEAR_THRESHOLD and adx_val > ADX_TREND_THRESHOLD:
                sl = price + atr_val * ATR_SL_MULTIPLIER
                tp = price - atr_val * ATR_TP_MULTIPLIER
                confidence = self._confidence(adx_val, rsi_val, "short", all_tf=True)
                return TradeSignal(
                    signal=Signal.SHORT,
                    strategy_name=self.name,
                    symbol=symbol,
                    entry_price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    confidence=confidence,
                    reason=f"MTF SHORT: 4H downtrend + 1H confirmed + 15M EMA cross | RSI={rsi_val:.1f} | ADX={adx_val:.1f}",
                    atr=atr_val,
                )

        # Detailed rejection
        if adx_val <= ADX_TREND_THRESHOLD:
            return self._no_signal(symbol, f"MTF aligned but ADX={adx_val:.1f} ≤ {ADX_TREND_THRESHOLD}")
        return self._no_signal(symbol, f"MTF {trend_bias} aligned, no entry trigger on 15m")

    def _get_trend_bias(self, df: pd.DataFrame) -> str:
        """Determine trend direction from higher-TF data (4h in production).

        Uses EMA stack + price vs EMA200. MACD zero-cross is laggy and often
        filters out valid trends on volatile perps; momentum from histogram
        confirms without requiring macd_line > 0 on the same bar.
        """
        if df is None or len(df) < 50:
            return "neutral"
        row = df.iloc[-1]
        prev = df.iloc[-2]
        ema50_col = f"ema{EMA_SLOW}"
        ema200_col = f"ema{EMA_TREND}"
        if ema50_col not in df.columns or ema200_col not in df.columns:
            return "neutral"
        ema50, ema200 = row[ema50_col], row[ema200_col]
        price = row["close"]
        macd_hist = row.get("macd_hist", 0)
        macd_hist_prev = prev.get("macd_hist", 0)

        stack_bull = ema50 > ema200 and price > ema200
        stack_bear = ema50 < ema200 and price < ema200
        macd_turning_bull = macd_hist > macd_hist_prev and macd_hist > 0
        macd_turning_bear = macd_hist < macd_hist_prev and macd_hist < 0

        if stack_bull and (row.get("macd", 0) > 0 or macd_turning_bull):
            return "up"
        if stack_bear and (row.get("macd", 0) < 0 or macd_turning_bear):
            return "down"
        return "neutral"

    def _confirm_signal(self, df: pd.DataFrame, bias: str) -> bool:
        """Confirm the trend bias from 1H data."""
        if df is None or len(df) < 20 or bias == "neutral":
            return False
        row = df.iloc[-1]
        ema21_col = f"ema{EMA_MID}"
        if ema21_col not in df.columns:
            return False
        rsi = row.get("rsi", 50)
        price = row["close"]
        ema21 = row[ema21_col]
        if bias == "up":
            return price > ema21 and rsi > 50
        if bias == "down":
            return price < ema21 and rsi < 50
        return False

    def _confidence(self, adx: float, rsi: float, direction: str,
                    all_tf: bool = False) -> float:
        score = 0.5
        if all_tf:
            score += 0.2   # bonus for multi-TF alignment
        if adx > 30:
            score += 0.15
        elif adx > 20:
            score += 0.05
        if direction == "long" and rsi > 60:
            score += 0.1
        if direction == "short" and rsi < 40:
            score += 0.1
        return min(score, 1.0)
