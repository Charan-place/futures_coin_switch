"""
Scalp Momentum Strategy — fast 5m entries on meme coin moves
─────────────────────────────────────────────────────────────
Inspired by how Dan Conway / Kane Ellis trade momentum:
  • Only trade in direction of Supertrend (fast trend flip indicator)
  • VWAP is the key intraday level — price above = bullish, below = bearish
  • Volume surge (>2x avg) confirms real move, not noise
  • StochRSI timing: enter when oscillator turns from oversold/overbought
  • Tight SL (0.6 ATR) — cut losers FAST on scalps
  • TP at 2.0 ATR — quick, realistic targets that clear India TDS + fees

Fee reality check (India):
  • Round-trip cost ≈ 1.12% of notional (fee 0.118% + TDS 1%)
  • With 10x leverage: need ≥1.2% price move to profit
  • This strategy targets 2.0 ATR ≈ 1.5-3% on meme coins = viable

Use PRIMARY_TF = "5m" in main for this strategy.
"""
import pandas as pd
import numpy as np
from strategies.base_strategy import BaseStrategy, TradeSignal, Signal
from config.settings import ATR_PERIOD


SCALP_SL_ATR   = 0.6    # tight stop — if wrong, exit fast
SCALP_TP_ATR   = 2.0    # reasonable scalp target
SCALP_VOL_MIN  = 1.8    # volume must be ≥ 1.8x avg (real move)
STOCH_OVERSOLD  = 25    # StochK below this = oversold → long opportunity
STOCH_OVERBOUGHT= 75    # StochK above this = overbought → short opportunity


class ScalpMomentumStrategy(BaseStrategy):
    name = "SCALP_MOMENTUM"

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        if len(df) < 50:
            return self._no_signal(symbol, "warmup<50 bars")

        required = {"supertrend_dir", "vwap", "stoch_k", "stoch_d", "vol_ratio", "atr"}
        if not required.issubset(df.columns):
            return self._no_signal(symbol, "missing scalp indicators")

        row  = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3] if len(df) >= 3 else prev

        price     = float(row["close"])
        atr_val   = float(row["atr"]) if float(row["atr"]) > 0 else price * 0.01
        vwap      = float(row["vwap"])
        st_dir    = int(row["supertrend_dir"])
        stoch_k   = float(row["stoch_k"])
        stoch_k_p = float(prev["stoch_k"])
        stoch_d   = float(row["stoch_d"])
        stoch_d_p = float(prev["stoch_d"])
        vol_ratio = float(row["vol_ratio"])
        macd_hist = float(row.get("macd_hist", 0))
        rsi_val   = float(row.get("rsi", 50))
        rsi_prev  = float(prev.get("rsi", 50))

        if np.isnan(vwap) or np.isnan(stoch_k) or np.isnan(stoch_d):
            return self._no_signal(symbol, "NaN in scalp indicators")

        # Volume gate — must have real momentum, not ghost town
        if vol_ratio < SCALP_VOL_MIN:
            return self._no_signal(symbol, f"vol={vol_ratio:.2f}x < {SCALP_VOL_MIN}x (no momentum)")

        # False breakout filter: candle body must be >35% of range (real move, not wick spike)
        candle_range = float(row["high"]) - float(row["low"])
        body = abs(float(row["close"]) - float(row["open"]))
        real_body = (body / candle_range) > 0.35 if candle_range > 0 else False
        if not real_body:
            return self._no_signal(symbol, f"wick-dominated bar (body={body/candle_range*100:.0f}% of range) — skip false breakout")

        # ── LONG: Supertrend bullish + price above VWAP + StochK turning up ──
        above_vwap   = price > vwap
        st_bullish   = st_dir == 1
        # StochK crossed above StochD = real turn, not noise
        stoch_cross_up   = stoch_k > stoch_d and stoch_k_p <= stoch_d_p
        stoch_turning_up = stoch_k > stoch_k_p and stoch_k < STOCH_OVERBOUGHT
        stoch_was_low = stoch_k_p < STOCH_OVERSOLD      # tighter: was truly oversold
        macd_pos     = macd_hist > 0
        rsi_ok_long  = 40 < rsi_val < 72
        rsi_rising   = rsi_val > rsi_prev               # RSI must be building momentum

        if (st_bullish and above_vwap and (stoch_cross_up or (stoch_turning_up and stoch_was_low))
                and rsi_ok_long and rsi_rising):
            sl = max(price - SCALP_SL_ATR * atr_val, float(row["low"]))
            tp = price + SCALP_TP_ATR * atr_val
            conf = self._confidence(vol_ratio, stoch_k, "long", macd_pos, above_vwap)
            return TradeSignal(
                signal=Signal.LONG,
                strategy_name=self.name,
                symbol=symbol,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                confidence=conf,
                reason=(
                    f"SCALP LONG: Supertrend↑ + above VWAP({vwap:.6g}) + "
                    f"StochK turning up {stoch_k_p:.0f}→{stoch_k:.0f} | "
                    f"vol={vol_ratio:.1f}x RSI={rsi_val:.0f}"
                ),
                atr=atr_val,
            )

        # ── SHORT: Supertrend bearish + price below VWAP + StochK turning down ──
        below_vwap   = price < vwap
        st_bearish   = st_dir == -1
        # StochK crossed below StochD = real turn, not noise
        stoch_cross_dn    = stoch_k < stoch_d and stoch_k_p >= stoch_d_p
        stoch_turning_dn  = stoch_k < stoch_k_p and stoch_k > STOCH_OVERSOLD
        stoch_was_high    = stoch_k_p > STOCH_OVERBOUGHT   # tighter: was truly overbought
        macd_neg          = macd_hist < 0
        rsi_ok_short      = 28 < rsi_val < 60
        rsi_falling       = rsi_val < rsi_prev              # RSI must be losing momentum

        if (st_bearish and below_vwap and (stoch_cross_dn or (stoch_turning_dn and stoch_was_high))
                and rsi_ok_short and rsi_falling):
            sl = min(price + SCALP_SL_ATR * atr_val, float(row["high"]))
            tp = price - SCALP_TP_ATR * atr_val
            conf = self._confidence(vol_ratio, stoch_k, "short", macd_neg, below_vwap)
            return TradeSignal(
                signal=Signal.SHORT,
                strategy_name=self.name,
                symbol=symbol,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                confidence=conf,
                reason=(
                    f"SCALP SHORT: Supertrend↓ + below VWAP({vwap:.6g}) + "
                    f"StochK turning dn {stoch_k_p:.0f}→{stoch_k:.0f} | "
                    f"vol={vol_ratio:.1f}x RSI={rsi_val:.0f}"
                ),
                atr=atr_val,
            )

        # Detailed rejection
        if not (st_bullish or st_bearish):
            return self._no_signal(symbol, "Supertrend direction=0 (initializing)")
        if st_bullish and not above_vwap:
            vwap_dist = (vwap - price) / vwap * 100
            return self._no_signal(symbol, f"Supertrend↑ but price {vwap_dist:.2f}% below VWAP")
        if st_bearish and not below_vwap:
            return self._no_signal(symbol, "Supertrend↓ but price above VWAP")
        if st_bullish and not stoch_was_low:
            return self._no_signal(symbol, f"ST↑+VWAP OK but StochK={stoch_k:.0f} not recovering from low")
        if st_bearish and not stoch_was_high:
            return self._no_signal(symbol, f"ST↓+VWAP OK but StochK={stoch_k:.0f} not falling from high")
        return self._no_signal(symbol, "scalp conditions not aligned")

    def _confidence(self, vol: float, stoch: float, direction: str,
                    macd_aligned: bool, vwap_aligned: bool) -> float:
        score = 0.45
        if vol >= 3.0:
            score += 0.20
        elif vol >= 2.0:
            score += 0.10
        if macd_aligned:
            score += 0.10
        if vwap_aligned:
            score += 0.10
        if direction == "long":
            if stoch < 20:
                score += 0.15   # deeply oversold → high-quality entry
            elif stoch < 35:
                score += 0.05
        else:
            if stoch > 80:
                score += 0.15
            elif stoch > 65:
                score += 0.05
        return min(score, 0.95)
