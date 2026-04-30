"use client";
import { useEffect, useState, useCallback } from "react";
import type { Portfolio, Position } from "@/lib/types";

function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-xl p-5 flex flex-col gap-1" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <span style={{ color: "var(--muted)" }} className="text-xs uppercase tracking-wider">{label}</span>
      <span className="text-2xl font-semibold" style={{ color: color ?? "white" }}>{value}</span>
      {sub && <span style={{ color: "var(--muted)" }} className="text-xs">{sub}</span>}
    </div>
  );
}

function fmt(n: number, decimals = 2) {
  return n.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

type BotStatus = { running: boolean; pid: number | null; mode: "paper" | "live" | null; startedAt: string | null };

function BotControl() {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [mode, setMode] = useState<"paper" | "live">("paper");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch("/api/bot/status");
      setStatus(await r.json());
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    fetchStatus();
    const t = setInterval(fetchStatus, 5_000);
    return () => clearInterval(t);
  }, [fetchStatus]);

  async function start() {
    setLoading(true); setErr(null);
    try {
      const r = await fetch("/api/bot/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode }) });
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      setStatus(d);
    } catch (e) { setErr(String(e)); }
    setLoading(false);
  }

  async function stop() {
    setLoading(true); setErr(null);
    try {
      await fetch("/api/bot/stop", { method: "POST" });
      setStatus({ running: false, pid: null, mode: null, startedAt: null });
    } catch (e) { setErr(String(e)); }
    setLoading(false);
  }

  const running = status?.running ?? false;

  return (
    <div className="rounded-xl p-5 flex flex-col gap-4" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full" style={{ background: running ? "var(--green)" : "var(--muted)" }} />
          <span className="font-semibold text-white text-sm">Bot</span>
          {running && status?.mode && (
            <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ background: status.mode === "live" ? "#1f0a0a" : "#0c1a0c", color: status.mode === "live" ? "var(--red)" : "var(--green)" }}>
              {status.mode.toUpperCase()}
            </span>
          )}
          {running && status?.pid && (
            <span className="text-xs" style={{ color: "var(--muted)" }}>PID {status.pid}</span>
          )}
        </div>
        {running && status?.startedAt && (
          <span className="text-xs" style={{ color: "var(--muted)" }}>
            Started {new Date(status.startedAt).toLocaleTimeString()}
          </span>
        )}
      </div>

      {err && (
        <div className="rounded px-3 py-2 text-xs" style={{ background: "#1f0a0a", color: "var(--red)", border: "1px solid var(--red)" }}>{err}</div>
      )}

      {!running ? (
        <div className="flex items-center gap-3">
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as "paper" | "live")}
            className="rounded px-3 py-2 text-sm flex-1"
            style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)" }}
          >
            <option value="paper">Paper Trading (Simulated)</option>
            <option value="live">Live Trading (Real Money)</option>
          </select>
          <button
            onClick={start}
            disabled={loading}
            className="px-5 py-2 rounded text-sm font-medium transition-opacity hover:opacity-80 disabled:opacity-40"
            style={{ background: "var(--green)", color: "#000" }}
          >
            {loading ? "Starting…" : "Start Bot"}
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <div className="flex-1 text-sm" style={{ color: "var(--muted)" }}>
            Running in <span style={{ color: status?.mode === "live" ? "var(--red)" : "var(--green)" }}>{status?.mode}</span> mode
          </div>
          <button
            onClick={stop}
            disabled={loading}
            className="px-5 py-2 rounded text-sm font-medium transition-opacity hover:opacity-80 disabled:opacity-40"
            style={{ background: "var(--red)", color: "#fff" }}
          >
            {loading ? "Stopping…" : "Stop Bot"}
          </button>
        </div>
      )}

      {mode === "live" && !running && (
        <p className="text-xs" style={{ color: "var(--red)" }}>
          Live mode places real orders. Confirm keys are valid and risk settings are correct before starting.
        </p>
      )}
    </div>
  );
}

export default function OverviewPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [pRes, posRes] = await Promise.all([fetch("/api/portfolio"), fetch("/api/positions")]);
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

  const pnlColor = portfolio ? (portfolio.unrealisedPnl >= 0 ? "var(--green)" : "var(--red)") : "white";
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
        <button onClick={refresh} className="px-3 py-1.5 rounded text-xs hover:opacity-80" style={{ background: "var(--border)", color: "var(--text)" }}>
          Refresh
        </button>
      </div>

      <BotControl />

      {error && (
        <div className="rounded-lg px-4 py-3 text-sm" style={{ background: "#1f0a0a", border: "1px solid var(--red)", color: "var(--red)" }}>
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Balance" value={portfolio ? `₮ ${fmt(portfolio.total)}` : "—"} sub="USDT" />
        <StatCard label="Available" value={portfolio ? `₮ ${fmt(portfolio.available)}` : "—"} sub="free margin" />
        <StatCard label="Margin Used" value={portfolio ? `₮ ${fmt(portfolio.margin)}` : "—"} sub={portfolio ? `${fmt((portfolio.margin / portfolio.total) * 100, 1)}% of total` : undefined} />
        <StatCard label="Unrealised PnL" value={portfolio ? `${portfolio.unrealisedPnl >= 0 ? "+" : ""}₮ ${fmt(portfolio.unrealisedPnl)}` : "—"} color={pnlColor} />
      </div>

      <div>
        <h2 className="text-sm font-semibold text-white mb-3">
          Open Positions <span style={{ color: "var(--muted)" }} className="font-normal">({positions.length})</span>
        </h2>
        {positions.length === 0 ? (
          <div className="rounded-xl p-8 text-center text-sm" style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}>
            No open positions
          </div>
        ) : (
          <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
                  {["Symbol", "Side", "Qty", "Entry", "Mark", "PnL", "PnL %", "Lev"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left font-medium" style={{ color: "var(--muted)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => {
                  const c = p.pnl >= 0 ? "var(--green)" : "var(--red)";
                  return (
                    <tr key={p.symbol + i} style={{ background: i % 2 === 0 ? "var(--surface)" : "var(--bg)", borderBottom: "1px solid var(--border)" }}>
                      <td className="px-4 py-3 font-medium text-white">{p.symbol}</td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ background: p.side === "LONG" ? "#052e16" : "#1f0a0a", color: p.side === "LONG" ? "var(--green)" : "var(--red)" }}>
                          {p.side}
                        </span>
                      </td>
                      <td className="px-4 py-3" style={{ color: "var(--text)" }}>{p.quantity}</td>
                      <td className="px-4 py-3" style={{ color: "var(--text)" }}>{fmt(p.entryPrice)}</td>
                      <td className="px-4 py-3" style={{ color: "var(--text)" }}>{fmt(p.markPrice)}</td>
                      <td className="px-4 py-3 font-medium" style={{ color: c }}>{p.pnl >= 0 ? "+" : ""}₮ {fmt(p.pnl)}</td>
                      <td className="px-4 py-3 font-medium" style={{ color: c }}>{p.pnlPct >= 0 ? "+" : ""}{fmt(p.pnlPct)}%</td>
                      <td className="px-4 py-3" style={{ color: "var(--muted)" }}>{p.leverage}x</td>
                    </tr>
                  );
                })}
              </tbody>
              {positions.length > 1 && (
                <tfoot>
                  <tr style={{ background: "var(--surface)", borderTop: "1px solid var(--border)" }}>
                    <td colSpan={5} className="px-4 py-3 text-xs" style={{ color: "var(--muted)" }}>Total unrealised</td>
                    <td className="px-4 py-3 font-semibold" style={{ color: totalPnl >= 0 ? "var(--green)" : "var(--red)" }}>
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
