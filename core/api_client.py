"""
CoinSwitch Futures API Client — correctly implemented.

Auth:
  Signature = (METHOD + path + epoch_ms)  for GET with no params
  Signature = (METHOD + unquote(path?querystring) + epoch_ms)  for GET with params
  Signature = (METHOD + path + epoch_ms)  for POST/DELETE  (body NOT in signature)
  Signature is ED25519 signed, returned as HEX (not base64).

Futures exchange identifier: "EXCHANGE_2"
Futures symbols: BTCUSDT, ETHUSDT, SOLUSDT, etc. (USDT pairs)
"""
import time
import json
import requests
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode, unquote_plus
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from config.settings import API_KEY, SECRET_KEY, BASE_URL
from monitoring.logger import get_logger

logger = get_logger(__name__)

FUTURES_EXCHANGE = "EXCHANGE_2"


class CoinSwitchAPIError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"[{code}] {message}")


class CoinSwitchClient:
    def __init__(self, api_key: str = API_KEY, secret_key: str = SECRET_KEY):
        self.api_key = api_key
        self._private_key: Optional[Ed25519PrivateKey] = None
        if secret_key:
            self._private_key = Ed25519PrivateKey.from_private_bytes(
                bytes.fromhex(secret_key)
            )
        self.session = requests.Session()

    # ── Signature ─────────────────────────────────────────────────────────────

    def _sign(self, method: str, path: str, params: Dict = None) -> tuple[str, str]:
        """
        Returns (signature_hex, epoch_ms_str).
        GET with params: sign over unquoted path+querystring+epoch
        All others:      sign over path+epoch  (body excluded)
        """
        epoch = str(int(time.time() * 1000))
        endpoint = path
        if method == "GET" and params:
            endpoint = unquote_plus(path + "?" + urlencode(params))
        msg = method + endpoint + epoch
        sig = self._private_key.sign(msg.encode("utf-8")).hex()
        return sig, epoch

    def _request(self, method: str, path: str, params: Dict = None,
                  body: Dict = None) -> Dict:
        sig, epoch = self._sign(method, path, params)
        url = f"{BASE_URL}{path}"
        body_str = (
            json.dumps(body, sort_keys=True, separators=(",", ":")) if body else None
        )
        try:
            resp = self.session.request(
                method=method, url=url,
                params=params, data=body_str,
                headers={
                    "X-AUTH-APIKEY": self.api_key,
                    "X-AUTH-SIGNATURE": sig,
                    "X-AUTH-EPOCH": epoch,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            result = resp.json()
            if resp.status_code not in (200, 201) and not (
                resp.status_code == 400 and "balance" in str(result).lower()
            ):
                msg = result.get("message", str(result)) if isinstance(result, dict) else str(result)
                raise CoinSwitchAPIError(resp.status_code, msg, result)
            return result
        except requests.RequestException as e:
            raise CoinSwitchAPIError(0, f"Network error: {e}")

    # ── Futures: Account ──────────────────────────────────────────────────────

    def get_futures_wallet(self) -> Dict:
        """Returns USDT balance in futures wallet."""
        return self._request("GET", "/trade/api/v2/futures/wallet_balance")

    def get_futures_balance_usdt(self) -> float:
        """Convenience: returns available USDT as float."""
        data = self.get_futures_wallet()
        balances = data.get("data", {}).get("base_asset_balances", [])
        for b in balances:
            if b.get("base_asset") == "USDT":
                return float(b["balances"].get("total_available_balance", 0))
        return 0.0

    # ── Futures: Market Data ──────────────────────────────────────────────────

    def get_futures_ticker(self, symbol: str) -> Dict:
        """symbol e.g. BTCUSDT"""
        return self._request("GET", "/trade/api/v2/futures/ticker",
                             params={"exchange": FUTURES_EXCHANGE, "symbol": symbol.upper()})

    def get_futures_price(self, symbol: str) -> Optional[float]:
        try:
            data = self.get_futures_ticker(symbol)
            price = data["data"][FUTURES_EXCHANGE]["last_price"]
            return float(price)
        except Exception:
            return None

    def get_futures_candles(self, symbol: str, interval: str = "15m",
                             limit: int = 200) -> Dict:
        """Candle data via the v2 candles endpoint (USDT symbol)."""
        end_time = int(time.time() * 1000)
        interval_ms = {
            "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
            "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
        }.get(interval, 900_000)
        start_time = end_time - interval_ms * limit
        return self._request("GET", "/trade/api/v2/candles", params={
            "symbol": symbol.upper(),
            "exchange": FUTURES_EXCHANGE,
            "interval": int(interval_ms / 60_000),   # in minutes
            "start_time": start_time,
            "end_time": end_time,
        })

    # ── Futures: Positions ────────────────────────────────────────────────────

    def get_futures_positions(self, symbol: str = None) -> Dict:
        params = {"exchange": FUTURES_EXCHANGE}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request("GET", "/trade/api/v2/futures/positions", params=params)

    def get_futures_transactions(self, symbol: str) -> Dict:
        return self._request("GET", "/trade/api/v2/futures/transactions",
                             params={"exchange": FUTURES_EXCHANGE,
                                     "symbol": symbol.lower()})

    # ── Futures: Instrument info / fees ──────────────────────────────────────

    def get_instrument_info(self, symbol: str) -> Dict:
        """Tick size, min qty, fee tiers per market.

        CoinSwitch publishes per-instrument metadata that often includes
        `taker_commission`, `maker_commission`, etc. Endpoint name has
        changed across API versions, so we try a few; the first that
        responds 2xx wins.
        """
        candidates = [
            ("/trade/api/v2/futures/instrument_info",
             {"exchange": FUTURES_EXCHANGE, "symbol": symbol.upper()}),
            ("/trade/api/v2/futures/instrument-info",
             {"exchange": FUTURES_EXCHANGE, "symbol": symbol.upper()}),
            ("/trade/api/v2/instrument_info",
             {"exchange": FUTURES_EXCHANGE, "symbol": symbol.upper()}),
        ]
        last_err: Optional[Exception] = None
        for path, params in candidates:
            try:
                return self._request("GET", path, params=params)
            except CoinSwitchAPIError as e:
                last_err = e
                continue
        raise last_err if last_err else CoinSwitchAPIError(0, "instrument_info: no endpoint found")

    def get_fee_schedule(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        Best-effort: pull commission % from instrument_info.
        Returns dict like {"taker_pct": 0.05, "maker_pct": 0.05} or None.

        We accept several common field names because CoinSwitch's response
        shape has shifted across versions.
        """
        try:
            raw = self.get_instrument_info(symbol)
        except CoinSwitchAPIError as e:
            logger.debug(f"instrument_info failed for {symbol}: {e}")
            return None
        data = raw.get("data") if isinstance(raw, dict) else None
        if data is None:
            return None
        if isinstance(data, dict) and FUTURES_EXCHANGE in data:
            data = data[FUTURES_EXCHANGE]
        if isinstance(data, list) and data:
            data = data[0]
        if not isinstance(data, dict):
            return None
        taker_keys = ["taker_commission", "taker_fee", "taker_fee_rate", "taker"]
        maker_keys = ["maker_commission", "maker_fee", "maker_fee_rate", "maker"]
        taker = next((data[k] for k in taker_keys if k in data), None)
        maker = next((data[k] for k in maker_keys if k in data), None)
        if taker is None and maker is None:
            return None
        out: Dict[str, float] = {}
        try:
            if taker is not None:
                out["taker_pct"] = float(taker) * 100.0 if float(taker) < 1 else float(taker)
            if maker is not None:
                out["maker_pct"] = float(maker) * 100.0 if float(maker) < 1 else float(maker)
        except (TypeError, ValueError):
            return None
        return out

    def parse_fees_from_transactions(self, symbol: str,
                                     limit_trades: int = 5) -> Optional[Dict[str, float]]:
        """
        Inspect the most recent fills and back out the *actual* effective
        cost % charged: (sum of fee + tds + gst) / sum(notional). This is
        the ground truth — beats anything published in instrument_info.
        Returns {"effective_cost_pct": x, "samples": n} or None.
        """
        try:
            raw = self.get_futures_transactions(symbol)
        except CoinSwitchAPIError as e:
            logger.debug(f"transactions failed for {symbol}: {e}")
            return None
        data = raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(data, list):
            return None
        rows = data[:limit_trades]
        total_cost = 0.0
        total_notional = 0.0
        n = 0
        for r in rows:
            if not isinstance(r, dict):
                continue
            qty = float(r.get("qty") or r.get("quantity") or 0.0)
            price = float(r.get("price") or r.get("avg_price") or 0.0)
            fee = float(r.get("fee") or r.get("commission") or 0.0)
            tds = float(r.get("tds") or 0.0)
            gst = float(r.get("gst") or 0.0)
            notional = qty * price
            if notional <= 0:
                continue
            total_cost += fee + tds + gst
            total_notional += notional
            n += 1
        if n == 0 or total_notional <= 0:
            return None
        return {
            "effective_cost_pct": total_cost / total_notional * 100.0,
            "samples": n,
        }

    # ── Futures: Leverage ─────────────────────────────────────────────────────

    def get_leverage(self, symbol: str) -> Dict:
        return self._request("GET", "/trade/api/v2/futures/leverage",
                             params={"exchange": FUTURES_EXCHANGE,
                                     "symbol": symbol.upper()})

    def set_leverage(self, symbol: str, leverage: int) -> Dict:
        return self._request("POST", "/trade/api/v2/futures/leverage", body={
            "exchange": FUTURES_EXCHANGE,
            "symbol": symbol.upper(),
            "leverage": leverage,
        })

    # ── Futures: Orders ───────────────────────────────────────────────────────

    def place_order(self, symbol: str, side: str, order_type: str,
                    quantity: float, price: float = None,
                    trigger_price: float = None,
                    reduce_only: bool = False) -> Dict:
        """
        side:       BUY | SELL
        order_type: MARKET | LIMIT | STOP_MARKET | TAKE_PROFIT_MARKET
        """
        body = {
            "exchange": FUTURES_EXCHANGE,
            "symbol": symbol.upper(),
            "side": side.upper(),
            "order_type": order_type.upper(),
            "quantity": quantity,
        }
        if price is not None:
            body["price"] = price
        if trigger_price is not None:
            body["trigger_price"] = trigger_price
        if reduce_only:
            body["reduce_only"] = True

        logger.info(f"Order: {side} {quantity} {symbol} {order_type}"
                    f"{f' @ {price}' if price else ''}")
        return self._request("POST", "/trade/api/v2/futures/order", body=body)

    def place_market_order(self, symbol: str, side: str,
                            quantity: float, reduce_only: bool = False) -> Dict:
        return self.place_order(symbol, side, "MARKET", quantity,
                                reduce_only=reduce_only)

    def place_limit_order(self, symbol: str, side: str,
                           quantity: float, price: float,
                           reduce_only: bool = False) -> Dict:
        return self.place_order(symbol, side, "LIMIT", quantity, price=price,
                                reduce_only=reduce_only)

    def place_stop_loss(self, symbol: str, side: str,
                         quantity: float, trigger_price: float) -> Dict:
        return self.place_order(symbol, side, "STOP_MARKET", quantity,
                                trigger_price=trigger_price, reduce_only=True)

    def place_take_profit(self, symbol: str, side: str,
                           quantity: float, trigger_price: float) -> Dict:
        return self.place_order(symbol, side, "TAKE_PROFIT_MARKET", quantity,
                                trigger_price=trigger_price, reduce_only=True)

    def get_order(self, order_id: str) -> Dict:
        return self._request("GET", "/trade/api/v2/futures/order",
                             params={"order_id": order_id})

    def cancel_order(self, order_id: str) -> Dict:
        return self._request("DELETE", "/trade/api/v2/futures/order",
                             body={"order_id": order_id, "exchange": FUTURES_EXCHANGE})

    def cancel_all_orders(self, symbol: str = None) -> Dict:
        body = {"exchange": FUTURES_EXCHANGE}
        if symbol:
            body["symbol"] = symbol.upper()
        return self._request("POST", "/trade/api/v2/futures/cancel_all", body=body)

    def add_margin(self, symbol: str, margin: float) -> Dict:
        return self._request("POST", "/trade/api/v2/futures/add_margin", body={
            "exchange": FUTURES_EXCHANGE,
            "symbol": symbol.upper(),
            "margin": margin,
        })

    def close_position(self, symbol: str, side: str, quantity: float) -> Dict:
        """Close an open position with a market order in the opposite direction."""
        close_side = "SELL" if side.upper() == "BUY" else "BUY"
        return self.place_market_order(symbol, close_side, quantity, reduce_only=True)

    # ── Bracket order helper ───────────────────────────────────────────────────

    def place_bracket_order(self, symbol: str, side: str, quantity: float,
                             stop_loss: float, take_profit: float,
                             entry_price: float = None) -> Dict:
        """Entry + SL + TP in sequence."""
        results = {}
        if entry_price:
            results["entry"] = self.place_limit_order(symbol, side, quantity, entry_price)
        else:
            results["entry"] = self.place_market_order(symbol, side, quantity)

        close_side = "SELL" if side.upper() == "BUY" else "BUY"
        try:
            results["stop_loss"] = self.place_stop_loss(symbol, close_side, quantity, stop_loss)
        except CoinSwitchAPIError as e:
            logger.warning(f"SL order failed: {e}")
            results["stop_loss"] = None
        try:
            results["take_profit"] = self.place_take_profit(symbol, close_side, quantity, take_profit)
        except CoinSwitchAPIError as e:
            logger.warning(f"TP order failed: {e}")
            results["take_profit"] = None
        return results
