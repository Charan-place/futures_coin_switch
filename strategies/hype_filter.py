"""
Hype / Momentum filter
──────────────────────
Gates trades on meme coins using free Binance data:

1. Volume ratio      — current 15m volume / 20-bar avg (from enriched df)
2. Funding rate      — from Binance futures: extreme positive = crowd over-long
                       → fade by preferring shorts; extreme negative = prefer longs
3. Open interest     — rising OI + rising price = real breakout
4. UTC dead-zone     — skip 02:00–06:00 UTC (low liquidity, stop-hunt prone)

Returns a `HypeVerdict` with a pass/block decision + direction bias.
"""
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict

import pandas as pd
import requests

from config.settings import (
    USE_HYPE_FILTER,
    HYPE_VOL_RATIO_MIN,
    FUNDING_EXTREME_POS, FUNDING_EXTREME_NEG,
    OI_DELTA_MIN_PCT,
    DEADZONE_UTC_START, DEADZONE_UTC_END,
)
from monitoring.logger import get_logger

logger = get_logger(__name__)

BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"


@dataclass
class HypeVerdict:
    passed: bool
    bias: str              # "long", "short", or "neutral"
    vol_ratio: float
    funding_rate: float
    oi_delta_pct: float
    in_deadzone: bool
    reason: str


class HypeFilter:
    """Caches funding + OI per symbol for ~2 minutes to avoid hammering Binance."""

    def __init__(self, ttl: int = 120):
        self._cache: Dict[str, Dict] = {}
        self._ttl = ttl

    # ── External data ─────────────────────────────────────────────────────────

    def _get_funding_rate(self, symbol: str) -> Optional[float]:
        try:
            r = requests.get(f"{BINANCE_FAPI}/premiumIndex",
                             params={"symbol": symbol.upper()}, timeout=5)
            r.raise_for_status()
            return float(r.json().get("lastFundingRate", 0.0))
        except Exception as e:
            logger.debug(f"Funding fetch failed for {symbol}: {e}")
            return None

    def _get_oi_delta_pct(self, symbol: str) -> Optional[float]:
        try:
            r = requests.get(f"{BINANCE_FAPI}/openInterestHist",
                             params={"symbol": symbol.upper(),
                                     "period": "15m", "limit": 5}, timeout=5)
            r.raise_for_status()
            rows = r.json()
            if len(rows) < 2:
                return None
            first = float(rows[0]["sumOpenInterest"])
            last  = float(rows[-1]["sumOpenInterest"])
            if first <= 0:
                return None
            return (last - first) / first * 100.0
        except Exception as e:
            logger.debug(f"OI fetch failed for {symbol}: {e}")
            return None

    def _fetch_with_cache(self, symbol: str) -> Dict:
        now = time.time()
        cached = self._cache.get(symbol)
        if cached and now - cached["ts"] < self._ttl:
            return cached
        entry = {
            "ts": now,
            "funding":  self._get_funding_rate(symbol) or 0.0,
            "oi_delta": self._get_oi_delta_pct(symbol) or 0.0,
        }
        self._cache[symbol] = entry
        return entry

    # ── Decision ──────────────────────────────────────────────────────────────

    def evaluate(self, symbol: str, df_entry: pd.DataFrame) -> HypeVerdict:
        vol_ratio = float(df_entry["vol_ratio"].iloc[-1]) if "vol_ratio" in df_entry.columns else 1.0
        ext = self._fetch_with_cache(symbol)
        funding = ext["funding"]
        oi_delta = ext["oi_delta"]

        hour_utc = datetime.now(timezone.utc).hour
        in_deadzone = DEADZONE_UTC_START <= hour_utc < DEADZONE_UTC_END

        if not USE_HYPE_FILTER:
            return HypeVerdict(True, "neutral", vol_ratio, funding, oi_delta,
                               in_deadzone, "filter disabled")

        if in_deadzone:
            return HypeVerdict(False, "neutral", vol_ratio, funding, oi_delta,
                               True, f"dead-zone {DEADZONE_UTC_START}-{DEADZONE_UTC_END} UTC")

        # Block only genuine ghost-town conditions: vol << average AND no OI move.
        # A market at 60% of average volume is sleepy but still tradeable; only bail
        # when it's actually dead.
        ghost_town = vol_ratio < 0.30 and abs(oi_delta) < OI_DELTA_MIN_PCT
        if ghost_town:
            return HypeVerdict(False, "neutral", vol_ratio, funding, oi_delta,
                               False, f"ghost town: vol={vol_ratio:.2f}x oi_Δ={oi_delta:+.2f}%")

        # Funding-rate bias: crowd stretched → fade them
        bias = "neutral"
        if funding >= FUNDING_EXTREME_POS:
            bias = "short"
        elif funding <= FUNDING_EXTREME_NEG:
            bias = "long"

        return HypeVerdict(
            True, bias, vol_ratio, funding, oi_delta, False,
            f"vol={vol_ratio:.2f}x oi_Δ={oi_delta:+.2f}% fund={funding*100:.3f}% bias={bias}"
        )
