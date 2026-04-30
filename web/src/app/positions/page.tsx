"use client";
import { useEffect, useState, useCallback } from "react";
import type { Position } from "@/lib/types";

const PAIRS = [
  "1000PEPEUSDT","FIGHTUSDT","GALAUSDT","XANUSDT","1000BONKUSDT",
  "BLESSUSDT","JCTUSDT","TRUUSDT","PENGUUSDT","BOMEUSDT","MEMEUSDT","GPSUSDT",
];

function fmt(n: number, d = 2) {
  return n.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
}

function ManualOrder({ onDone }: { onDone: () => void }) {
  const [symbol, setSymbol] = useState(PAIRS[0]);
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  async function submit() {
    if (!qty || isNaN(Number(qty))) return;
    if (!confirm(`Place ${side} ${qty} ${symbol} at market?`)) return;
    setBusy(true); setMsg(null);
    try {
      const r = await fetch("/api/order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, side, quantity: Number(qty) }),
      });
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      setMsg({ text: `Order placed — ${d.data?.orderId ?? "OK"}`, ok: true });
      setQty("");
      onDone();
    } catch (e) {
      setMsg({ text: String(e), ok: false });
    }
    setBusy(false);
  }

  return (
    <div className="rounded-xl p-5 flex flex-col gap-4" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold tracking-widest" style={{ color: "var(--muted)" }}>MANUAL ORDER</span>
        <span className="text-xs px-2 py-0.5 rounded" style={{ background: "#1a0a00", color: "#f97316", border: "1px solid #7c2d12" }}>
          LIVE ONLY
        </span>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        {/* Symbol */}
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded-lg px-3 py-2 text-sm outline-none"
          style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", flex: 2, minWidth: 160 }}
        >
          {PAIRS.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>

        {/* Side toggle */}
        <div className="flex rounded-lg overflow-hidden" style={{ border: "1px solid var(--border)" }}>
          {(["BUY", "SELL"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSide(s)}
              className="px-5 py-2 text-sm font-bold transition-colors"
              style={{
                background: side === s ? (s === "BUY" ? "var(--green)" : "var(--red)") : "var(--bg)",
                color: side === s ? (s === "BUY" ? "#000" : "#fff") : "var(--muted)",
              }}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Qty */}
        <div className="flex items-center rounded-lg overflow-hidden" style={{ border: "1px solid var(--border)", flex: 1, minWidth: 120 }}>
          <span className="px-3 py-2 text-xs" style={{ background: "var(--surface)", color: "var(--muted)", borderRight: "1px solid var(--border)" }}>QTY</span>
          <input
            type="number"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            placeholder="0.00"
            step="any"
            min={0}
            className="px-3 py-2 text-sm w-full outline-none font-mono"
            style={{ background: "var(--bg)", color: "var(--text)" }}
          />
        </div>

        <button
          onClick={submit}
          disabled={busy || !qty}
          className="px-6 py-2 rounded-lg text-sm font-bold transition-all hover:scale-105 active:scale-95 disabled:opacity-40"
          style={{ background: side === "BUY" ? "var(--green)" : "var(--red)", color: side === "BUY" ? "#000" : "#fff", minWidth: 130 }}
        >
          {busy ? "Placing…" : `▶ ${side} Market`}
        </button>
      </div>

      {msg && (
        <div
          className="rounded px-3 py-2 text-xs"
          style={{ background: msg.ok ? "#052e16" : "#1f0a0a", color: msg.ok ? "var(--green)" : "var(--red)", border: `1px solid ${msg.ok ? "var(--green)" : "var(--red)"}` }}
        >
          {msg.text}
        </div>
      )}
    </div>
  );
}

function CloseButton({ symbol, side, quantity, onDone }: { symbol: string; side: "LONG" | "SHORT"; quantity: number; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function close() {
    if (!confirm(`Close entire ${side} position on ${symbol}?`)) return;
    setBusy(true); setErr(null);
    try {
      const r = await fetch("/api/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, side, quantity }),
      });
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      onDone();
    } catch (e) {
      setErr(String(e));
    }
    setBusy(false);
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={close}
        disabled={busy}
        className="px-4 py-1.5 rounded-lg text-xs font-bold transition-all hover:scale-105 active:scale-95 disabled:opacity-40"
        style={{ background: "rgba(239,68,68,0.12)", border: "1px solid var(--red)", color: "var(--red)" }}
      >
        {busy ? "Closing…" : "✕ Close Position"}
      </button>
      {err && <span className="text-xs" style={{ color: "var(--red)" }}>{err}</span>}
    </div>
  );
}

export default function PositionsPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/positions");
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setPositions(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5_000);
    return () => clearInterval(t);
  }, [refresh]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Positions</h1>
          {lastUpdated && (
            <p style={{ color: "var(--muted)" }} className="text-xs mt-0.5">
              Updated {lastUpdated.toLocaleTimeString()} · refreshes every 5s
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs px-2 py-1 rounded" style={{ background: "var(--border)", color: "var(--muted)" }}>
            {positions.length} open
          </span>
          <button onClick={refresh} className="px-3 py-1.5 rounded-lg text-xs hover:opacity-80" style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Manual order panel */}
      <ManualOrder onDone={refresh} />

      {error && (
        <div className="rounded-lg px-4 py-3 text-sm" style={{ background: "#1f0a0a", border: "1px solid var(--red)", color: "var(--red)" }}>
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-xl p-12 text-center text-sm" style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}>
          Loading…
        </div>
      ) : positions.length === 0 ? (
        <div className="rounded-xl p-12 text-center text-sm" style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}>
          No open positions
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {positions.map((p, i) => {
            const isLong = p.side === "LONG";
            const pnlColor = p.pnl >= 0 ? "var(--green)" : "var(--red)";
            const distToLiq = Math.abs(((p.markPrice - p.liquidationPrice) / p.markPrice) * 100);
            return (
              <div
                key={p.symbol + i}
                className="rounded-xl p-5 flex flex-col gap-4"
                style={{ background: "var(--surface)", border: `1px solid ${p.pnl >= 0 ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}` }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-white text-base">{p.symbol}</span>
                    <span className="px-2 py-0.5 rounded text-xs font-bold" style={{ background: isLong ? "#052e16" : "#1f0a0a", color: isLong ? "var(--green)" : "var(--red)" }}>
                      {p.side}
                    </span>
                    <span className="px-2 py-0.5 rounded text-xs" style={{ background: "var(--border)", color: "var(--muted)" }}>
                      {p.leverage}x
                    </span>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <div className="font-bold font-mono" style={{ color: pnlColor }}>
                        {p.pnl >= 0 ? "+" : ""}₮ {fmt(p.pnl)}
                      </div>
                      <div className="text-xs font-mono" style={{ color: pnlColor }}>
                        {p.pnlPct >= 0 ? "+" : ""}{fmt(p.pnlPct)}%
                      </div>
                    </div>
                    <CloseButton symbol={p.symbol} side={p.side} quantity={p.quantity} onDone={refresh} />
                  </div>
                </div>

                <div className="grid grid-cols-3 md:grid-cols-6 gap-4">
                  {[
                    { label: "Qty", value: String(p.quantity) },
                    { label: "Entry", value: fmt(p.entryPrice) },
                    { label: "Mark", value: fmt(p.markPrice), bold: true },
                    { label: "Margin", value: `₮ ${fmt(p.margin)}` },
                    { label: "Liq Price", value: fmt(p.liquidationPrice), color: "var(--yellow)" },
                    { label: "Dist to Liq", value: `${fmt(distToLiq, 1)}%`, color: distToLiq < 10 ? "var(--red)" : distToLiq < 25 ? "var(--yellow)" : "var(--muted)" },
                  ].map(({ label, value, color, bold }) => (
                    <div key={label}>
                      <div className="text-xs mb-1" style={{ color: "var(--muted)" }}>{label}</div>
                      <div className={`text-sm font-mono ${bold ? "font-bold" : ""}`} style={{ color: color ?? "white" }}>{value}</div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
