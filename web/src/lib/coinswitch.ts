import { createPrivateKey, sign as cryptoSign } from "crypto";
import type { Portfolio, Position, Transaction } from "./types";

const BASE_URL = process.env.CS_BASE_URL ?? "https://coinswitch.co";
const API_KEY = process.env.CS_API_KEY ?? "";
const SECRET_KEY = process.env.CS_SECRET_KEY ?? "";

// PKCS8 DER wrapper for a raw 32-byte Ed25519 seed
const PKCS8_PREFIX = Buffer.from("302e020100300506032b657004220420", "hex");

function getPrivateKey() {
  const seed = Buffer.from(SECRET_KEY, "hex");
  const der = Buffer.concat([PKCS8_PREFIX, seed]);
  return createPrivateKey({ key: der, format: "der", type: "pkcs8" });
}

function buildEndpoint(path: string, params?: Record<string, string>): string {
  if (!params || Object.keys(params).length === 0) return path;
  const qs = Object.entries(params)
    .map(([k, v]) => `${k}=${v}`)
    .join("&");
  return `${path}?${qs}`;
}

function makeHeaders(method: string, path: string, params?: Record<string, string>) {
  const epoch = Date.now().toString();
  const endpoint = method === "GET" ? buildEndpoint(path, params) : path;
  const msg = Buffer.from(method + endpoint + epoch);
  const signature = cryptoSign(null, msg, getPrivateKey()).toString("hex");
  return {
    "X-AUTH-APIKEY": API_KEY,
    "X-AUTH-SIGNATURE": signature,
    "X-AUTH-EPOCH": epoch,
    "Content-Type": "application/json",
  };
}

async function csGet<T>(path: string, params?: Record<string, string>): Promise<T> {
  const headers = makeHeaders("GET", path, params);
  const qs = params ? "?" + Object.entries(params).map(([k, v]) => `${k}=${v}`).join("&") : "";
  const res = await fetch(BASE_URL + path + qs, { headers, cache: "no-store" });
  if (!res.ok) throw new Error(`CoinSwitch ${path} → ${res.status}`);
  return res.json();
}

async function csPost<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const headers = makeHeaders("POST", path);
  const res = await fetch(BASE_URL + path, { method: "POST", headers, body: JSON.stringify(body), cache: "no-store" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`CoinSwitch ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

export interface OrderPayload {
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  reduceOnly?: boolean;
}

export async function placeOrder(o: OrderPayload) {
  return csPost("/trade/api/v2/futures/order", {
    exchange: "EXCHANGE_2",
    symbol: o.symbol,
    side: o.side,
    order_type: "MARKET",
    quantity: o.quantity,
    reduce_only: o.reduceOnly ?? false,
  });
}

export const PAIRS = [
  "1000PEPEUSDT","FIGHTUSDT","GALAUSDT","XANUSDT","1000BONKUSDT",
  "BLESSUSDT","JCTUSDT","TRUUSDT","PENGUUSDT","BOMEUSDT","MEMEUSDT","GPSUSDT",
];

export async function fetchPortfolio(): Promise<Portfolio> {
  const data = await csGet<{ data: { base_asset_balances: { base_asset: string; balances: Record<string, number> }[] } }>(
    "/trade/api/v2/futures/wallet_balance"
  );
  const usdt = data.data.base_asset_balances.find((b) => b.base_asset === "USDT");
  const b = usdt?.balances ?? {};
  return {
    total: b.total_balance ?? 0,
    available: b.total_available_balance ?? 0,
    margin: b.total_position_margin ?? 0,
    unrealisedPnl: b.unrealised_pnl ?? 0,
  };
}

export async function fetchPositions(): Promise<Position[]> {
  const data = await csGet<{ data: Record<string, unknown>[]; message?: string }>(
    "/trade/api/v2/futures/positions",
    { exchange: "EXCHANGE_2" }
  );
  if (!Array.isArray(data.data) || data.message?.includes("no open")) return [];
  return data.data.map((p) => ({
    symbol: String(p.symbol),
    side: String(p.side) as "LONG" | "SHORT",
    quantity: Number(p.quantity),
    entryPrice: Number(p.entry_price),
    markPrice: Number(p.mark_price),
    pnl: Number(p.pnl),
    pnlPct: Number(p.pnl_percent),
    margin: Number(p.margin),
    leverage: Number(p.leverage),
    liquidationPrice: Number(p.liquidation_price),
  }));
}

export async function fetchTransactions(): Promise<Transaction[]> {
  const results = await Promise.allSettled(
    PAIRS.map((sym) =>
      csGet<{ data: Record<string, unknown>[] }>(
        "/trade/api/v2/futures/transactions",
        { exchange: "EXCHANGE_2", symbol: sym.toLowerCase() }
      ).then((d) =>
        (d.data ?? []).slice(0, 3).map((t) => ({
          symbol: sym,
          side: String(t.side) as "BUY" | "SELL",
          quantity: Number(t.qty ?? t.quantity ?? 0),
          price: Number(t.avg_price ?? t.price ?? 0),
          fee: Number(t.fee ?? t.commission ?? 0),
          tds: Number(t.tds ?? 0),
          gst: Number(t.gst ?? 0),
        }))
      )
    )
  );
  return results
    .filter((r): r is PromiseFulfilledResult<Transaction[]> => r.status === "fulfilled")
    .flatMap((r) => r.value);
}
