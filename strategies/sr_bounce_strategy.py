"""
Strategy 4: Support / Resistance Bounce
────────────────────────────────────────
Long:  price within SR_PROXIMITY_PCT of support AND RSI < 45 AND bullish candle
Short: price within SR_PROXIMITY_PCT of resistance AND RSI > 55 AND bearish candle

SL: beyond the level by SR_SL_BUFFER_PCT
TP: toward the opposite level (capped at 3× risk for safety)
"""
import pandas as pd
from strategies.base_strategy import BaseStrategy, TradeSignal, Signal
from config.settings import (
    SR_PROXIMITY_PCT, SR_SL_BUFFER_PCT,
    RSI_BULL_THRESHOLD, RSI_BEAR_THRESHOLD,
    ATR_TP_MULTIPLIER,
)


class SrBounceStrategy(BaseStrategy):
    name = "SR_BOUNCE"

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        if len(df) < 30 or "sr_support" not in df.columns:
            return self._no_signal(symbol, "warmup<30 or SR not enriched")

        row = df.iloc[-1]
        price = row["close"]
        support = row["sr_support"]
        resistance = row["sr_resistance"]
        rsi_val = row.get("rsi", 50)
        atr_val = row.get("atr", price * 0.01)
        vol_ratio = row.get("vol_ratio", 1.0)

        bullish_candle = row["close"] > row["open"]
        bearish_candle = row["close"] < row["open"]

        dist_sup_pct = row.get("sr_dist_sup_pct", 1.0)
        dist_res_pct = row.get("sr_dist_res_pct", 1.0)

        # ── Long bounce off support ───────────────────────────────────────────
        # At support: RSI below 55 is acceptable; strong bullish candle not required,
        # just not a big red one. Meme-coin S/R bounces rarely have clean setups.
        if (dist_sup_pct <= SR_PROXIMITY_PCT
                and rsi_val < 55
                and not (bearish_candle and (row["open"] - row["close"]) > atr_val * 0.5)
                and support > 0):
            sl = support * (1 - SR_SL_BUFFER_PCT)
            risk = price - sl
            # Target resistance, but cap at 3x ATR
            tp = min(resistance, price + ATR_TP_MULTIPLIER * atr_val)
            if tp <= price + risk:
                tp = price + 2 * risk    # force minimum 1:2 R:R
            confidence = self._confidence(dist_sup_pct, rsi_val, vol_ratio, "long")
            return TradeSignal(
                signal=Signal.LONG,
                strategy_name=self.name,
                symbol=symbol,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                confidence=confidence,
                reason=f"Bounce off support {support:.6f} | RSI={rsi_val:.1f} | vol={vol_ratio:.1f}x",
                atr=atr_val,
            )

        # ── Short rejection from resistance ───────────────────────────────────
        if (dist_res_pct <= SR_PROXIMITY_PCT
                and rsi_val > 45
                and not (bullish_candle and (row["close"] - row["open"]) > atr_val * 0.5)
                and resistance > 0):
            sl = resistance * (1 + SR_SL_BUFFER_PCT)
            risk = sl - price
            tp = max(support, price - ATR_TP_MULTIPLIER * atr_val)
            if tp >= price - risk:
                tp = price - 2 * risk
            confidence = self._confidence(dist_res_pct, rsi_val, vol_ratio, "short")
            return TradeSignal(
                signal=Signal.SHORT,
                strategy_name=self.name,
                symbol=symbol,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                confidence=confidence,
                reason=f"Reject at resistance {resistance:.6f} | RSI={rsi_val:.1f} | vol={vol_ratio:.1f}x",
                atr=atr_val,
            )

        # Detailed rejection
        near_sup = dist_sup_pct <= SR_PROXIMITY_PCT
        near_res = dist_res_pct <= SR_PROXIMITY_PCT
        if not (near_sup or near_res):
            return self._no_signal(
                symbol,
                f"price not near SR (Δsup={dist_sup_pct*100:.1f}% Δres={dist_res_pct*100:.1f}%)",
            )
        if near_sup and rsi_val >= 55:
            return self._no_signal(symbol, f"at support but RSI={rsi_val:.1f} ≥ 55")
        if near_res and rsi_val <= 45:
            return self._no_signal(symbol, f"at resistance but RSI={rsi_val:.1f} ≤ 45")
        return self._no_signal(symbol, "SR-bounce filters not met")

    def _confidence(self, dist_pct: float, rsi: float,
                    vol_ratio: float, direction: str) -> float:
        score = 0.5
        # Closer to the level → higher confidence
        if dist_pct <= SR_PROXIMITY_PCT * 0.3:
            score += 0.2
        elif dist_pct <= SR_PROXIMITY_PCT * 0.6:
            score += 0.1
        # RSI extremes add weight
        if direction == "long" and rsi < 30:
            score += 0.15
        elif direction == "short" and rsi > 70:
            score += 0.15
        # Volume confirmation
        if vol_ratio >= 1.5:
            score += 0.1
        return min(score, 1.0)
