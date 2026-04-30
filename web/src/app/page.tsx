"use client";
import { useEffect, useState, useCallback } from "react";
import type { Portfolio, Position } from "@/lib/types";

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div
      className="rounded-xl p-5 flex flex-col gap-1"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      <span style={{ color: "var(--muted)" }} className="text-xs uppercase tracking-wider">
        {label}
      </span>
      <span className="text-2xl font-semibold" style={{ color: color ?? "white" }}>
        {value}
      </span>
      {sub && (
        <span style={{ color: "var(--muted)" }} className="text-xs">
          {sub}
        </span>
      )}
    </div>
  );
}

function fmt(n: number, decimals = 2) {
  return n.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export default function OverviewPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [pRes, posRes] = await Promise.all([
        fetch("/api/portfolio"),
        fetch("/api/positions"),
      ]);
      if (!pRes.ok || !posRes.ok) throw new Error("API error");
      const [p, pos] = await Promise.all([pRes.json(), posRes.json()]);
      if (p.error) throw new Error(p.error);
      setPortfolio(p);
      setPositions(pos.error ? [] : pos);
      setLastUpdated(new Date());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10_000);
    return () => clearInterval(t);
  }, [refresh]);

  const pnlColor = portfolio
    ? portfolio.unrealisedPnl >= 0
      ? "var(--green)"
      : "var(--red)"
    : "white";

  const totalPnl = positions.reduce((s, p) => s + p.pnl, 0);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Portfolio Overview</h1>
          {lastUpdated && (
            <p style={{ color: "var(--muted)" }} className="text-xs mt-1">
              Updated {lastUpdated.toLocaleTimeString()} · auto-refreshes every 10s
            </p>
          )}
        </div>
        <button
          onClick={refresh}
          className="px-3 py-1.5 rounded text-xs transition-opacity hover:opacity-80"
          style={{ background: "var(--border)", color: "var(--text)" }}
        >
          Refresh
        </button>
      </div>

      {error && (
        <div
          className="rounded-lg px-4 py-3 text-sm"
          style={{ background: "#1f0a0a", border: "1px solid var(--red)", color: "var(--red)" }}
        >
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Total Balance"
          value={portfolio ? `₮ ${fmt(portfolio.total)}` : "—"}
          sub="USDT"
        />
        <StatCard
          label="Available"
          value={portfolio ? `₮ ${fmt(portfolio.available)}` : "—"}
          sub="free margin"
        />
        <StatCard
          label="Margin Used"
          value={portfolio ? `₮ ${fmt(portfolio.margin)}` : "—"}
          sub={portfolio ? `${fmt((portfolio.margin / portfolio.total) * 100, 1)}% of total` : undefined}
        />
        <StatCard
          label="Unrealised PnL"
          value={portfolio ? `${portfolio.unrealisedPnl >= 0 ? "+" : ""}₮ ${fmt(portfolio.unrealisedPnl)}` : "—"}
          color={pnlColor}
        />
      </div>

      <div>
        <h2 className="text-sm font-semibold text-white mb-3">
          Open Positions{" "}
          <span style={{ color: "var(--muted)" }} className="font-normal">
            ({positions.length})
          </span>
        </h2>

        {positions.length === 0 ? (
          <div
            className="rounded-xl p-8 text-center text-sm"
            style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}
          >
            No open positions
          </div>
        ) : (
          <div
            className="rounded-xl overflow-hidden"
            style={{ border: "1px solid var(--border)" }}
          >
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
                  {["Symbol", "Side", "Qty", "Entry", "Mark", "PnL", "PnL %", "Lev"].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left font-medium"
                      style={{ color: "var(--muted)" }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => {
                  const pnlColor = p.pnl >= 0 ? "var(--green)" : "var(--red)";
                  return (
                    <tr
                      key={p.symbol + i}
                      style={{
                        background: i % 2 === 0 ? "var(--surface)" : "var(--bg)",
                        borderBottom: "1px solid var(--border)",
                      }}
                    >
                      <td className="px-4 py-3 font-medium text-white">{p.symbol}</td>
                      <td className="px-4 py-3">
                        <span
                          className="px-2 py-0.5 rounded text-xs font-medium"
                          style={{
                            background: p.side === "LONG" ? "#052e16" : "#1f0a0a",
                            color: p.side === "LONG" ? "var(--green)" : "var(--red)",
                          }}
                        >
                          {p.side}
                        </span>
                      </td>
                      <td className="px-4 py-3" style={{ color: "var(--text)" }}>
                        {p.quantity}
                      </td>
                      <td className="px-4 py-3" style={{ color: "var(--text)" }}>
                        {fmt(p.entryPrice)}
                      </td>
                      <td className="px-4 py-3" style={{ color: "var(--text)" }}>
                        {fmt(p.markPrice)}
                      </td>
                      <td className="px-4 py-3 font-medium" style={{ color: pnlColor }}>
                        {p.pnl >= 0 ? "+" : ""}₮ {fmt(p.pnl)}
                      </td>
                      <td className="px-4 py-3 font-medium" style={{ color: pnlColor }}>
                        {p.pnlPct >= 0 ? "+" : ""}
                        {fmt(p.pnlPct)}%
                      </td>
                      <td className="px-4 py-3" style={{ color: "var(--muted)" }}>
                        {p.leverage}x
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              {positions.length > 1 && (
                <tfoot>
                  <tr style={{ background: "var(--surface)", borderTop: "1px solid var(--border)" }}>
                    <td colSpan={5} className="px-4 py-3 text-xs" style={{ color: "var(--muted)" }}>
                      Total unrealised
                    </td>
                    <td
                      className="px-4 py-3 font-semibold"
                      style={{ color: totalPnl >= 0 ? "var(--green)" : "var(--red)" }}
                    >
                      {totalPnl >= 0 ? "+" : ""}₮ {fmt(totalPnl)}
                    </td>
                    <td colSpan={2} />
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
