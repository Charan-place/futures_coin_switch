"""
Data Fetcher for CoinSwitch Futures Bot.

Live prices  → CoinSwitch Futures ticker (EXCHANGE_2, USDT pairs)
OHLCV candles → Binance public API (no auth, same USDT pairs, identical price)
Portfolio     → CoinSwitch futures wallet balance
"""
import time
import requests
import pandas as pd
from typing import Dict, List, Optional

from core.api_client import CoinSwitchClient, CoinSwitchAPIError, FUTURES_EXCHANGE
from config.settings import CANDLE_LIMIT, TRADING_PAIRS
from monitoring.logger import get_logger

logger = get_logger(__name__)

BINANCE_BASE  = "https://api.binance.com/api/v3"
BINANCE_FAPI  = "https://fapi.binance.com/fapi/v1"   # futures candles (no auth)

INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}


class DataFetcher:
    def __init__(self, client: CoinSwitchClient):
        self.client = client
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl = 30  # seconds

    def _is_cached(self, key: str) -> bool:
        if key not in self._cache:
            return False
        return time.time() - self._cache[key]["ts"] < self._cache_ttl

    # ── OHLCV via Binance (free, no auth) ─────────────────────────────────────

    def get_ohlcv(self, symbol: str, interval: str = "15m",
                  limit: int = CANDLE_LIMIT, use_cache: bool = True) -> Optional[pd.DataFrame]:
        key = f"{symbol}_{interval}"
        if use_cache and self._is_cached(key):
            return self._cache[key]["df"].copy()

        df = self._binance_candles(symbol.upper(), interval, limit)
        if df is not None and not df.empty:
            self._cache[key] = {"df": df, "ts": time.time()}
        return df

    def _binance_candles(self, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        iv = INTERVAL_MAP.get(interval, interval)
        # Try spot first; many new/micro coins only exist on futures
        for base_url in [f"{BINANCE_BASE}/klines", f"{BINANCE_FAPI}/klines"]:
            try:
                resp = requests.get(base_url,
                                    params={"symbol": symbol, "interval": iv, "limit": limit},
                                    timeout=10)
                if resp.status_code == 400:
                    continue          # symbol not on this endpoint, try next
                resp.raise_for_status()
                records = [{"timestamp": int(c[0]), "open": float(c[1]),
                            "high": float(c[2]),  "low": float(c[3]),
                            "close": float(c[4]), "volume": float(c[5])}
                           for c in resp.json()]
                df = pd.DataFrame(records)
                df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                df = df.sort_values("datetime").set_index("datetime")
                return df[["open", "high", "low", "close", "volume"]].astype(float).dropna()
            except Exception:
                continue
        logger.error(f"Candles unavailable for {symbol} {interval} on both spot and futures")
        return None

    def get_multi_tf(self, symbol: str, timeframes: List[str]) -> Dict[str, pd.DataFrame]:
        return {tf: df for tf in timeframes
                if (df := self.get_ohlcv(symbol, tf)) is not None}

    # ── Live prices via CoinSwitch Futures ────────────────────────────────────

    def get_current_price(self, symbol: str) -> Optional[float]:
        try:
            return self.client.get_futures_price(symbol)
        except Exception as e:
            logger.error(f"Price fetch failed for {symbol}: {e}")
            return None

    def get_all_prices(self) -> Dict[str, float]:
        prices = {}
        for sym in TRADING_PAIRS:
            p = self.get_current_price(sym)
            if p:
                prices[sym] = p
        return prices

    # ── Portfolio ─────────────────────────────────────────────────────────────

    def get_portfolio_value(self) -> Dict:
        try:
            raw = self.client.get_futures_wallet()
            balances = raw.get("data", {}).get("base_asset_balances", [])
            for b in balances:
                if b.get("base_asset") == "USDT":
                    bal = b["balances"]
                    return {
                        "total":     float(bal.get("total_balance", 0)),
                        "available": float(bal.get("total_available_balance", 0)),
                        "margin":    float(bal.get("total_position_margin", 0)),
                        "unrealised_pnl": float(bal.get("unrealised_pnl", 0)),
                    }
        except Exception as e:
            logger.error(f"Wallet fetch failed: {e}")
        return {"total": 0, "available": 0, "margin": 0, "unrealised_pnl": 0}

    def get_open_positions(self) -> List[Dict]:
        try:
            out = []
            for sym in TRADING_PAIRS:
                data = self.client.get_futures_positions(sym)
                msg = data.get("message", "")
                if "no open" in msg.lower():
                    continue
                positions = data.get("data", [])
                if isinstance(positions, list):
                    out.extend(positions)
            return out
        except Exception as e:
            logger.error(f"Positions fetch failed: {e}")
            return []


class PaperDataFetcher(DataFetcher):
    """Real market data + simulated order execution."""
    def __init__(self, client: CoinSwitchClient, initial_balance: float = 1000.0):
        super().__init__(client)
        self.paper_balance = initial_balance
        self.paper_positions: Dict = {}

    def get_portfolio_value(self) -> Dict:
        return {
            "total": self.paper_balance,
            "available": self.paper_balance,
            "margin": 0,
            "unrealised_pnl": 0,
        }

    def get_open_positions(self) -> List[Dict]:
        return list(self.paper_positions.values())
