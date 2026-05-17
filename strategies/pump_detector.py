"""
Pump Detector Strategy — catch early-stage meme coin pumps
────────────────────────────────────────────────────────────
Meme coins can pump 10-50% in minutes. The key is catching the move EARLY
before the crowd piles in and RSI gets extended.

Entry conditions (LONG-ONLY — meme pumps are directional):
  1. Volume spike: current bar volume > 3× 20-bar average (unusual accumulation)
  2. Price velocity: last 3 bars gained ≥ 0.8% total (momentum confirmed)
  3. RSI window: 40-68 — has momentum, NOT yet extended/overbought
  4. VWAP reclaim OR price accelerating above VWAP (institutions buying)
  5. Supertrend just flipped bullish OR already bullish (trend confirming)
  6. No massive wick down on current bar (not a fakeout spike)

SHORT pumps (dump detector):
  Same logic inverted — price velocity negative, RSI 32-60, below VWAP.
  Meme dumps are faster and more violent than pumps.

SL: Low of the pump trigger bar (or 0.8 ATR, whichever is tighter)
TP: 4.0 ATR — ride the pump, memes run hard once confirmed

Dan Conway principle: "You don't scalp meme coins, you ride the wave."
Pentoshi principle: "Enter early, size right, let it run. Cut if wrong FAST."
"""
import pandas as pd
import numpy as np
from strategies.base_strategy import BaseStrategy, TradeSignal, Signal


PUMP_VOL_SPIKE     = 3.0    # current volume > 3x avg = real pump, not noise
PUMP_VELOCITY_PCT  = 0.008  # last 3 bars gained ≥ 0.8% = real price momentum
DUMP_VELOCITY_PCT  = -0.008 # last 3 bars lost ≥ 0.8% = real dump
PUMP_RSI_LOW       = 40     # RSI floor — below this = no momentum
PUMP_RSI_HIGH      = 68     # RSI ceiling — above this = extended, miss the entry
DUMP_RSI_LOW       = 32     # RSI floor for dump entry
DUMP_RSI_HIGH      = 60     # RSI ceiling for dump entry (coming off overbought)
PUMP_SL_ATR        = 0.8    # slightly wider stop — pump entries need room
PUMP_TP_ATR        = 4.0    # big TP — pump target, Pentoshi-style 3-5R


class PumpDetectorStrategy(BaseStrategy):
    name = "PUMP_DETECTOR"

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        if len(df) < 30:
            return self._no_signal(symbol, "warmup<30 bars")

        required = {"vol_ratio", "vwap", "supertrend_dir", "atr", "rsi"}
        if not required.issubset(df.columns):
            return self._no_signal(symbol, "missing pump indicators")

        row     = df.iloc[-1]
        prev    = df.iloc[-2]
        prev2   = df.iloc[-3] if len(df) >= 3 else prev

        price     = float(row["close"])
        atr_val   = float(row["atr"]) if float(row["atr"]) > 0 else price * 0.01
        vol_ratio = float(row["vol_ratio"])
        vwap      = float(row["vwap"])
        st_dir    = int(row["supertrend_dir"])
        rsi_val   = float(row["rsi"])

        if np.isnan(vwap) or np.isnan(atr_val):
            return self._no_signal(symbol, "NaN in pump indicators")

        # Price velocity: % change over last 3 bars
        close3 = float(prev2["close"])
        velocity = (price - close3) / close3 if close3 > 0 else 0.0

        # Wick ratio — large lower wick on "pump" bar = fakeout risk
        bar_range  = float(row["high"]) - float(row["low"])
        lower_wick = float(row["close"]) - float(row["low"])
        upper_wick = float(row["high"]) - float(row["close"])
        wick_ok_long  = bar_range > 0 and (lower_wick / bar_range) < 0.5
        wick_ok_short = bar_range > 0 and (upper_wick / bar_range) < 0.5

        # Candle body quality — real pump has body, not just wick spike
        body = abs(float(row["close"]) - float(row["open"]))
        real_body = (body / bar_range) > 0.40 if bar_range > 0 else False

        # RSI direction
        rsi_prev = float(prev.get("rsi", rsi_val))
        rsi_rising  = rsi_val > rsi_prev
        rsi_falling = rsi_val < rsi_prev

        # Volume sustained: previous bar must also be elevated (not 1-bar noise spike)
        vol_ratio_prev = float(prev.get("vol_ratio", 0))
        vol_sustained = vol_ratio >= PUMP_VOL_SPIKE and vol_ratio_prev >= 1.5

        # Volume gate — hard requirement for pump detection
        if not vol_sustained:
            return self._no_signal(symbol, f"vol={vol_ratio:.2f}x (prev={vol_ratio_prev:.2f}x) — need sustained volume, not 1-bar spike")

        # ── PUMP (LONG) ───────────────────────────────────────────────────────
        above_vwap   = price > vwap
        vwap_reclaim = float(prev["close"]) < vwap <= price   # just crossed above
        st_ok_long   = st_dir >= 0   # neutral or bullish (don't fight strong downtrend)

        if (velocity >= PUMP_VELOCITY_PCT
                and PUMP_RSI_LOW <= rsi_val <= PUMP_RSI_HIGH
                and rsi_rising
                and (above_vwap or vwap_reclaim)
                and st_ok_long
                and wick_ok_long
                and real_body):
            # SL: below current bar's low OR 0.8 ATR, whichever is LOWER (tighter)
            low_sl = float(row["low"])
            atr_sl = price - PUMP_SL_ATR * atr_val
            sl     = max(low_sl, atr_sl)   # take the higher = closer to price = tighter
            sl     = min(sl, price * 0.985)  # never wider than 1.5% from price
            tp     = price + PUMP_TP_ATR * atr_val

            vwap_note = "VWAP reclaim" if vwap_reclaim else "above VWAP"
            conf = self._confidence(vol_ratio, velocity, rsi_val, "long", vwap_reclaim)
            return TradeSignal(
                signal=Signal.LONG,
                strategy_name=self.name,
                symbol=symbol,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                confidence=conf,
                reason=(
                    f"PUMP LONG: vol={vol_ratio:.1f}x spike | "
                    f"velocity={velocity*100:.2f}% (3 bars) | "
                    f"RSI={rsi_val:.0f} | {vwap_note}"
                ),
                atr=atr_val,
            )

        # ── DUMP (SHORT) ──────────────────────────────────────────────────────
        below_vwap    = price < vwap
        vwap_loss     = float(prev["close"]) > vwap >= price   # just lost VWAP
        st_ok_short   = st_dir <= 0   # neutral or bearish

        if (velocity <= DUMP_VELOCITY_PCT
                and DUMP_RSI_LOW <= rsi_val <= DUMP_RSI_HIGH
                and rsi_falling
                and (below_vwap or vwap_loss)
                and st_ok_short
                and wick_ok_short
                and real_body):
            high_sl = float(row["high"])
            atr_sl  = price + PUMP_SL_ATR * atr_val
            sl      = min(high_sl, atr_sl)
            sl      = max(sl, price * 1.015)  # never wider than 1.5%
            tp      = price - PUMP_TP_ATR * atr_val

            vwap_note = "VWAP loss" if vwap_loss else "below VWAP"
            conf = self._confidence(vol_ratio, abs(velocity), rsi_val, "short", vwap_loss)
            return TradeSignal(
                signal=Signal.SHORT,
                strategy_name=self.name,
                symbol=symbol,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                confidence=conf,
                reason=(
                    f"DUMP SHORT: vol={vol_ratio:.1f}x spike | "
                    f"velocity={velocity*100:.2f}% (3 bars) | "
                    f"RSI={rsi_val:.0f} | {vwap_note}"
                ),
                atr=atr_val,
            )

        # Detailed rejection
        if velocity >= PUMP_VELOCITY_PCT and vol_ratio >= PUMP_VOL_SPIKE:
            if rsi_val > PUMP_RSI_HIGH:
                return self._no_signal(symbol, f"pump vol+vel OK but RSI={rsi_val:.0f} extended")
            if not (above_vwap or vwap_reclaim):
                return self._no_signal(symbol, "pump vol+vel OK but price below VWAP")
        if velocity <= DUMP_VELOCITY_PCT and vol_ratio >= PUMP_VOL_SPIKE:
            if rsi_val < DUMP_RSI_LOW:
                return self._no_signal(symbol, f"dump vol+vel OK but RSI={rsi_val:.0f} oversold")
        return self._no_signal(symbol,
            f"velocity={velocity*100:.2f}% vol={vol_ratio:.1f}x RSI={rsi_val:.0f} — no pump/dump")

    def _confidence(self, vol: float, velocity: float, rsi: float,
                    direction: str, vwap_event: bool) -> float:
        score = 0.50
        # Volume strength
        if vol >= 6.0:
            score += 0.25
        elif vol >= 4.0:
            score += 0.15
        elif vol >= 3.0:
            score += 0.08
        # Velocity strength
        if abs(velocity) >= 0.02:   # 2%+ in 3 bars = strong
            score += 0.10
        elif abs(velocity) >= 0.01:
            score += 0.05
        # VWAP event (reclaim/loss) is highest quality signal
        if vwap_event:
            score += 0.10
        # RSI in sweet spot
        if direction == "long" and 48 <= rsi <= 60:
            score += 0.05   # ideal early momentum zone
        if direction == "short" and 40 <= rsi <= 52:
            score += 0.05
        return min(score, 0.95)
