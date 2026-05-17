"""
Technical indicator calculations using pandas/numpy.
All functions accept a DataFrame with open/high/low/close/volume columns.
"""
import numpy as np
import pandas as pd
from typing import Tuple

from config.settings import (
    EMA_FAST, EMA_MID, EMA_SLOW, EMA_TREND,
    RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    ATR_PERIOD, ADX_PERIOD, BB_PERIOD, BB_STD,
    VOLUME_MA_PERIOD, SR_LOOKBACK,
)


# ─── EMA ──────────────────────────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def add_emas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df[f"ema{EMA_FAST}"]  = ema(df["close"], EMA_FAST)
    df[f"ema{EMA_MID}"]   = ema(df["close"], EMA_MID)
    df[f"ema{EMA_SLOW}"]  = ema(df["close"], EMA_SLOW)
    df[f"ema{EMA_TREND}"] = ema(df["close"], EMA_TREND)
    return df


# ─── RSI ──────────────────────────────────────────────────────────────────────

def rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def add_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = rsi(df["close"], period)
    return df


# ─── MACD ─────────────────────────────────────────────────────────────────────

def macd(series: pd.Series, fast: int = MACD_FAST, slow: int = MACD_SLOW,
         signal: int = MACD_SIGNAL) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def add_macd(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["macd"], df["macd_signal"], df["macd_hist"] = macd(df["close"])
    return df


# ─── ATR ──────────────────────────────────────────────────────────────────────

def atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def add_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.DataFrame:
    df = df.copy()
    df["atr"] = atr(df, period)
    return df


# ─── ADX / DMI ────────────────────────────────────────────────────────────────

def adx(df: pd.DataFrame, period: int = ADX_PERIOD) -> Tuple[pd.Series, pd.Series, pd.Series]:
    high, low, close = df["high"], df["low"], df["close"]
    prev_high = high.shift(1)
    prev_low  = low.shift(1)
    prev_close = close.shift(1)

    up_move   = high - prev_high
    down_move = prev_low - low

    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr_s  = tr.ewm(alpha=1/period, adjust=False).mean()
    pos_di = 100 * pd.Series(pos_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr_s
    neg_di = 100 * pd.Series(neg_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr_s

    dx = (100 * (pos_di - neg_di).abs() / (pos_di + neg_di).replace(0, np.nan))
    adx_s = dx.ewm(alpha=1/period, adjust=False).mean()

    return adx_s, pos_di, neg_di


def add_adx(df: pd.DataFrame, period: int = ADX_PERIOD) -> pd.DataFrame:
    df = df.copy()
    df["adx"], df["di_plus"], df["di_minus"] = adx(df, period)
    return df


# ─── Bollinger Bands ──────────────────────────────────────────────────────────

def bollinger_bands(series: pd.Series, period: int = BB_PERIOD,
                    std: float = BB_STD) -> Tuple[pd.Series, pd.Series, pd.Series]:
    mid = series.rolling(period).mean()
    std_s = series.rolling(period).std()
    upper = mid + std * std_s
    lower = mid - std * std_s
    return upper, mid, lower


def add_bollinger(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger_bands(df["close"])
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
    df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
    return df


# ─── VWAP ────────────────────────────────────────────────────────────────────

def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """VWAP with ±1σ and ±2σ bands. Key intraday reference for scalping."""
    df = df.copy()
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cum_vol  = df["volume"].cumsum()
    cum_tpv  = (typical * df["volume"]).cumsum()
    vwap_s   = cum_tpv / cum_vol.replace(0, np.nan)

    # Rolling std of typical price × volume weight (approximate VWAP bands)
    deviation  = (typical - vwap_s) ** 2
    cum_dev    = (deviation * df["volume"]).cumsum()
    vwap_std   = np.sqrt(cum_dev / cum_vol.replace(0, np.nan))

    df["vwap"]       = vwap_s
    df["vwap_upper"] = vwap_s + vwap_std
    df["vwap_lower"] = vwap_s - vwap_std
    # Distance from VWAP as fraction — positive = above, negative = below
    df["vwap_dist_pct"] = (df["close"] - vwap_s) / vwap_s.replace(0, np.nan)
    return df


# ─── Supertrend ───────────────────────────────────────────────────────────────

def add_supertrend(df: pd.DataFrame, period: int = 10,
                   multiplier: float = 3.0) -> pd.DataFrame:
    """Supertrend direction: +1 = bullish, -1 = bearish.
    Fast-flipping trend indicator ideal for momentum scalping."""
    df = df.copy()
    atr_s = atr(df, period)
    hl2   = (df["high"] + df["low"]) / 2
    raw_upper = hl2 + multiplier * atr_s
    raw_lower = hl2 - multiplier * atr_s

    close  = df["close"].values
    up_v   = raw_upper.values.copy()
    lo_v   = raw_lower.values.copy()
    st_v   = np.full(len(df), np.nan)
    dir_v  = np.zeros(len(df), dtype=int)

    for i in range(1, len(df)):
        # Final upper: only tighten if current bar's raw upper is lower (or prior close broke above)
        up_v[i] = raw_upper.iloc[i] if (raw_upper.iloc[i] < up_v[i-1] or close[i-1] > up_v[i-1]) else up_v[i-1]
        lo_v[i] = raw_lower.iloc[i] if (raw_lower.iloc[i] > lo_v[i-1] or close[i-1] < lo_v[i-1]) else lo_v[i-1]

        if close[i] > up_v[i-1]:
            dir_v[i] = 1
        elif close[i] < lo_v[i-1]:
            dir_v[i] = -1
        else:
            dir_v[i] = dir_v[i-1]

        st_v[i] = lo_v[i] if dir_v[i] == 1 else up_v[i]

    df["supertrend"]     = st_v
    df["supertrend_dir"] = dir_v
    return df


# ─── Stochastic RSI ───────────────────────────────────────────────────────────

def add_stoch_rsi(df: pd.DataFrame, rsi_period: int = 14,
                  stoch_period: int = 14, smooth_k: int = 3,
                  smooth_d: int = 3) -> pd.DataFrame:
    """StochRSI oscillator [0-100]. Faster signal than plain RSI.
    stoch_k < 20 = oversold, > 80 = overbought."""
    df  = df.copy()
    rsi_s    = rsi(df["close"], rsi_period)
    rsi_min  = rsi_s.rolling(stoch_period).min()
    rsi_max  = rsi_s.rolling(stoch_period).max()
    raw      = (rsi_s - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan)
    df["stoch_k"] = raw.rolling(smooth_k).mean() * 100
    df["stoch_d"] = df["stoch_k"].rolling(smooth_d).mean()
    return df


# ─── Volume ───────────────────────────────────────────────────────────────────

def add_volume_indicators(df: pd.DataFrame,
                          period: int = VOLUME_MA_PERIOD) -> pd.DataFrame:
    df = df.copy()
    df["vol_ma"] = df["volume"].rolling(period).mean()
    df["vol_ratio"] = df["volume"] / df["vol_ma"]
    # On-balance volume
    direction = np.sign(df["close"].diff())
    df["obv"] = (direction * df["volume"]).cumsum()
    return df


# ─── Support / Resistance ─────────────────────────────────────────────────────

def find_sr_levels(df: pd.DataFrame, lookback: int = 50,
                   tolerance_pct: float = 0.005) -> Tuple[float, float]:
    """
    Returns the nearest support and resistance levels based on recent price action.
    Uses swing highs/lows within the lookback window.
    """
    recent = df.tail(lookback)
    current_price = df["close"].iloc[-1]

    # Swing highs: local max within 5-bar window
    highs = recent["high"].values
    lows  = recent["low"].values

    resistance_candidates = []
    support_candidates = []

    for i in range(2, len(highs) - 2):
        if highs[i] == max(highs[i-2:i+3]):
            resistance_candidates.append(highs[i])
        if lows[i] == min(lows[i-2:i+3]):
            support_candidates.append(lows[i])

    # Find nearest above (resistance) and below (support)
    resistances_above = [r for r in resistance_candidates if r > current_price * (1 + tolerance_pct)]
    supports_below    = [s for s in support_candidates  if s < current_price * (1 - tolerance_pct)]

    resistance = min(resistances_above) if resistances_above else current_price * 1.03
    support    = max(supports_below)    if supports_below    else current_price * 0.97

    return support, resistance


def add_sr_columns(df: pd.DataFrame, lookback: int = SR_LOOKBACK) -> pd.DataFrame:
    """Attach nearest support/resistance + distance-% columns to each row."""
    df = df.copy()
    if len(df) < 10:
        df["sr_support"] = df["low"]
        df["sr_resistance"] = df["high"]
        df["sr_dist_sup_pct"] = 0.0
        df["sr_dist_res_pct"] = 0.0
        return df

    support, resistance = find_sr_levels(df, lookback=lookback)
    last = df["close"].iloc[-1]
    df["sr_support"] = support
    df["sr_resistance"] = resistance
    df["sr_dist_sup_pct"] = (last - support) / last if last > 0 else 0.0
    df["sr_dist_res_pct"] = (resistance - last) / last if last > 0 else 0.0
    return df


# ─── All-in-one enrichment ────────────────────────────────────────────────────

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicators to a DataFrame in one call."""
    df = add_emas(df)
    df = add_rsi(df)
    df = add_macd(df)
    df = add_atr(df)
    df = add_adx(df)
    df = add_bollinger(df)
    df = add_volume_indicators(df)
    df = add_sr_columns(df)
    df = add_vwap(df)
    df = add_supertrend(df)
    df = add_stoch_rsi(df)
    return df
