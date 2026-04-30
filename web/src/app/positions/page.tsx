"use client";
import { useEffect, useState, useCallback } from "react";
import type { Position } from "@/lib/types";

function fmt(n: number, d = 2) {
  return n.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
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
          <h1 className="text-xl font-bold text-white">Open Positions</h1>
          {lastUpdated && (
            <p style={{ color: "var(--muted)" }} className="text-xs mt-1">
              Updated {lastUpdated.toLocaleTimeString()} · refreshes every 5s
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span
            className="text-xs px-2 py-1 rounded"
            style={{ background: "var(--border)", color: "var(--muted)" }}
          >
            {positions.length} open
          </span>
          <button
            onClick={refresh}
            className="px-3 py-1.5 rounded text-xs hover:opacity-80"
            style={{ background: "var(--border)", color: "var(--text)" }}
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div
          className="rounded-lg px-4 py-3 text-sm"
          style={{ background: "#1f0a0a", border: "1px solid var(--red)", color: "var(--red)" }}
        >
          {error}
        </div>
      )}

      {loading ? (
        <div
          className="rounded-xl p-12 text-center text-sm"
          style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}
        >
          Loading…
        </div>
      ) : positions.length === 0 ? (
        <div
          className="rounded-xl p-12 text-center text-sm"
          style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}
        >
          No open positions
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {positions.map((p, i) => {
            const isLong = p.side === "LONG";
            const pnlColor = p.pnl >= 0 ? "var(--green)" : "var(--red)";
            const sideColor = isLong ? "var(--green)" : "var(--red)";
            const sideBg = isLong ? "#052e16" : "#1f0a0a";
            return (
              <div
                key={p.symbol + i}
                className="rounded-xl p-5 flex flex-col gap-4"
                style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-white">{p.symbol}</span>
                    <span
                      className="px-2 py-0.5 rounded text-xs font-medium"
                      style={{ background: sideBg, color: sideColor }}
                    >
                      {p.side}
                    </span>
                    <span
                      className="px-2 py-0.5 rounded text-xs"
                      style={{ background: "var(--border)", color: "var(--muted)" }}
                    >
                      {p.leverage}x
                    </span>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold" style={{ color: pnlColor }}>
                      {p.pnl >= 0 ? "+" : ""}₮ {fmt(p.pnl)}
                    </div>
                    <div className="text-xs" style={{ color: pnlColor }}>
                      {p.pnlPct >= 0 ? "+" : ""}
                      {fmt(p.pnlPct)}%
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[
                    { label: "Qty", value: String(p.quantity) },
                    { label: "Entry Price", value: `${fmt(p.entryPrice)}` },
                    { label: "Mark Price", value: `${fmt(p.markPrice)}` },
                    { label: "Margin", value: `₮ ${fmt(p.margin)}` },
                    { label: "Liquidation", value: `${fmt(p.liquidationPrice)}`, color: "var(--yellow)" },
                    {
                      label: "Distance to Liq",
                      value: `${fmt(Math.abs(((p.markPrice - p.liquidationPrice) / p.markPrice) * 100), 1)}%`,
                      color: "var(--muted)",
                    },
                  ].map(({ label, value, color }) => (
                    <div key={label}>
                      <div className="text-xs mb-1" style={{ color: "var(--muted)" }}>
                        {label}
                      </div>
                      <div className="text-sm font-medium" style={{ color: color ?? "white" }}>
                        {value}
                      </div>
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
