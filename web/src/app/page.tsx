"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import type { Portfolio, Position } from "@/lib/types";

type BotStatus = { running: boolean; pid: number | null; mode: "paper" | "live" | null; startedAt: string | null; balance: number | null };

function fmt(n: number, d = 2) {
  return n.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
}

function Uptime({ startedAt }: { startedAt: string }) {
  const [elapsed, setElapsed] = useState("");
  useEffect(() => {
    const tick = () => {
      const s = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
      setElapsed(`${h}h ${m}m ${sec}s`);
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [startedAt]);
  return <span>{elapsed}</span>;
}

function BotControl() {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [mode, setMode] = useState<"paper" | "live">("paper");
  const [balance, setBalance] = useState<string>("1000");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const poll = useCallback(async () => {
    try {
      const r = await fetch("/api/bot/status");
      setStatus(await r.json());
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    poll();
    const t = setInterval(poll, 4_000);
    return () => clearInterval(t);
  }, [poll]);

  async function start() {
    if (mode === "live" && !confirm("Start bot in LIVE mode? Real orders will be placed.")) return;
    setBusy(true); setErr(null);
    try {
      const r = await fetch("/api/bot/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode, balance: parseFloat(balance) || 1000 }) });
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      setStatus(d);
    } catch (e) { setErr(String(e)); }
    setBusy(false);
  }

  async function stop() {
    setBusy(true); setErr(null);
    try {
      await fetch("/api/bot/stop", { method: "POST" });
      setStatus({ running: false, pid: null, mode: null, startedAt: null, balance: null });
    } catch (e) { setErr(String(e)); }
    setBusy(false);
  }

  const running = status?.running ?? false;
  const isLive = status?.mode === "live";

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ border: `1px solid ${running ? (isLive ? "var(--red)" : "var(--green)") : "var(--border)"}`, transition: "border-color 0.4s" }}
    >
      {/* Header bar */}
      <div
        className="px-5 py-3 flex items-center justify-between"
        style={{ background: running ? (isLive ? "rgba(239,68,68,0.08)" : "rgba(34,197,94,0.06)") : "var(--surface)", transition: "background 0.4s" }}
      >
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-6 h-6">
            {running && (
              <span
                className="absolute inline-flex w-full h-full rounded-full opacity-60 animate-ping"
                style={{ background: isLive ? "var(--red)" : "var(--green)" }}
              />
            )}
            <span
              className="relative w-3 h-3 rounded-full"
              style={{ background: running ? (isLive ? "var(--red)" : "var(--green)") : "var(--muted)" }}
            />
          </div>
          <span className="font-semibold text-white text-sm tracking-wide">TRADING BOT</span>
          {running && status?.mode && (
            <span
              className="px-2 py-0.5 rounded text-xs font-bold tracking-widest"
              style={{ background: isLive ? "rgba(239,68,68,0.15)" : "rgba(34,197,94,0.12)", color: isLive ? "var(--red)" : "var(--green)" }}
            >
              {status.mode.toUpperCase()}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 text-xs" style={{ color: "var(--muted)" }}>
          {running && status?.pid && <span>PID {status.pid}</span>}
          {running && status?.startedAt && (
            <span className="font-mono">
              <Uptime startedAt={status.startedAt} />
            </span>
          )}
          <span className={`font-medium ${running ? (isLive ? "text-red-400" : "text-green-400") : ""}`}>
            {running ? "RUNNING" : "STOPPED"}
          </span>
        </div>
      </div>

      {/* Controls */}
      <div className="px-5 py-4 flex items-center gap-3" style={{ background: "var(--bg)", borderTop: "1px solid var(--border)" }}>
        {!running ? (
          <>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as "paper" | "live")}
              className="rounded-lg px-3 py-2 text-sm outline-none"
              style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)", flex: 2 }}
            >
              <option value="paper">📄 Paper Trading — Simulated</option>
              <option value="live">⚡ Live Trading — Real Money</option>
            </select>
            <div className="flex items-center rounded-lg overflow-hidden" style={{ border: "1px solid var(--border)", flex: 1 }}>
              <span className="px-3 py-2 text-sm" style={{ background: "var(--surface)", color: "var(--muted)", borderRight: "1px solid var(--border)" }}>₮</span>
              <input
                type="number"
                value={balance}
                onChange={(e) => setBalance(e.target.value)}
                min={100}
                step={100}
                placeholder="1000"
                className="px-3 py-2 text-sm w-full outline-none font-mono"
                style={{ background: "var(--bg)", color: "var(--text)" }}
              />
            </div>
            <button
              onClick={start}
              disabled={busy}
              className="px-6 py-2 rounded-lg text-sm font-semibold transition-all hover:scale-105 active:scale-95 disabled:opacity-40"
              style={{ background: mode === "live" ? "var(--red)" : "var(--green)", color: mode === "live" ? "#fff" : "#000", minWidth: 120 }}
            >
              {busy ? "Starting…" : "▶  Start Bot"}
            </button>
          </>
        ) : (
          <>
            <div className="flex-1 text-sm flex items-center gap-3" style={{ color: "var(--muted)" }}>
              Running in{" "}
              <span className="font-semibold" style={{ color: isLive ? "var(--red)" : "var(--green)" }}>
                {status?.mode}
              </span>
              {status?.balance != null && (
                <span className="px-2 py-0.5 rounded text-xs font-mono" style={{ background: "var(--border)", color: "var(--text)" }}>
                  ₮ {fmt(status.balance)} capital
                </span>
              )}
            </div>
            <button
              onClick={stop}
              disabled={busy}
              className="px-6 py-2 rounded-lg text-sm font-semibold transition-all hover:scale-105 active:scale-95 disabled:opacity-40"
              style={{ background: "#1f1f1f", border: "1px solid var(--red)", color: "var(--red)", minWidth: 120 }}
            >
              {busy ? "Stopping…" : "■  Stop Bot"}
            </button>
          </>
        )}
      </div>

      {err && (
        <div className="px-5 py-2 text-xs" style={{ background: "#1f0a0a", color: "var(--red)", borderTop: "1px solid var(--border)" }}>
          {err}
        </div>
      )}
      {mode === "live" && !running && (
        <div className="px-5 py-2 text-xs" style={{ background: "#1a0a00", color: "#f97316", borderTop: "1px solid #7c2d12" }}>
          ⚠ Live mode places real orders on CoinSwitch. Ensure API keys are valid and risk limits are set correctly.
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, sub, color, delta }: { label: string; value: string; sub?: string; color?: string; delta?: number }) {
  return (
    <div className="rounded-xl p-5 flex flex-col gap-2 transition-all hover:scale-[1.02]" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <span style={{ color: "var(--muted)" }} className="text-xs uppercase tracking-widest">{label}</span>
      <span className="text-2xl font-bold font-mono" style={{ color: color ?? "white" }}>{value}</span>
      <div className="flex items-center gap-2">
        {sub && <span style={{ color: "var(--muted)" }} className="text-xs">{sub}</span>}
        {delta !== undefined && (
          <span className="text-xs font-medium" style={{ color: delta >= 0 ? "var(--green)" : "var(--red)" }}>
            {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(2)}%
          </span>
        )}
      </div>
    </div>
  );
}

export default function OverviewPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const prevPnl = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [pRes, posRes] = await Promise.all([fetch("/api/portfolio"), fetch("/api/positions")]);
      const [p, pos] = await Promise.all([pRes.json(), posRes.json()]);
      if (p.error) throw new Error(p.error);
      setPortfolio(p);
      setPositions(Array.isArray(pos) ? pos : []);
      setLastUpdated(new Date());
      setError(null);
    } catch (e) { setError(String(e)); }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 8_000);
    return () => clearInterval(t);
  }, [refresh]);

  const pnlColor = portfolio ? (portfolio.unrealisedPnl >= 0 ? "var(--green)" : "var(--red)") : "white";
  const totalPnl = positions.reduce((s, p) => s + p.pnl, 0);
  const marginPct = portfolio && portfolio.total > 0 ? (portfolio.margin / portfolio.total) * 100 : 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-white tracking-tight">Portfolio Overview</h1>
          {lastUpdated && (
            <p style={{ color: "var(--muted)" }} className="text-xs mt-0.5">
              Last sync {lastUpdated.toLocaleTimeString()} · refreshes every 8s
            </p>
          )}
        </div>
        <button
          onClick={refresh}
          className="px-3 py-1.5 rounded-lg text-xs hover:opacity-80 transition-opacity"
          style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}
        >
          ↻ Refresh
        </button>
      </div>

      {/* Bot control */}
      <BotControl />

      {/* Error */}
      {error && (
        <div className="rounded-lg px-4 py-3 text-sm" style={{ background: "#1f0a0a", border: "1px solid var(--red)", color: "var(--red)" }}>
          {error}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Total Equity" value={portfolio ? `₮ ${fmt(portfolio.total)}` : "—"} sub="USDT" />
        <StatCard label="Available" value={portfolio ? `₮ ${fmt(portfolio.available)}` : "—"} sub="free margin" />
        <StatCard
          label="Margin Used"
          value={portfolio ? `₮ ${fmt(portfolio.margin)}` : "—"}
          sub={portfolio ? `${fmt(marginPct, 1)}% of equity` : undefined}
          color={marginPct > 80 ? "var(--red)" : marginPct > 50 ? "var(--yellow)" : "white"}
        />
        <StatCard
          label="Unrealised PnL"
          value={portfolio ? `${portfolio.unrealisedPnl >= 0 ? "+" : ""}₮ ${fmt(portfolio.unrealisedPnl)}` : "—"}
          color={pnlColor}
        />
      </div>

      {/* Positions */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-white">
            Open Positions{" "}
            <span
              className="ml-1 px-1.5 py-0.5 rounded text-xs font-normal"
              style={{ background: "var(--border)", color: "var(--muted)" }}
            >
              {positions.length}
            </span>
          </h2>
          {positions.length > 0 && (
            <span className="text-xs font-mono" style={{ color: totalPnl >= 0 ? "var(--green)" : "var(--red)" }}>
              Total {totalPnl >= 0 ? "+" : ""}₮ {fmt(totalPnl)}
            </span>
          )}
        </div>

        {positions.length === 0 ? (
          <div
            className="rounded-xl p-10 text-center text-sm"
            style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}
          >
            No open positions
          </div>
        ) : (
          <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
                  {["Symbol", "Side", "Qty", "Entry", "Mark", "PnL", "PnL %", "Lev", "Liq"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold tracking-wider" style={{ color: "var(--muted)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => {
                  const c = p.pnl >= 0 ? "var(--green)" : "var(--red)";
                  const distToLiq = Math.abs(((p.markPrice - p.liquidationPrice) / p.markPrice) * 100);
                  return (
                    <tr
                      key={p.symbol + i}
                      className="transition-colors"
                      style={{ background: i % 2 === 0 ? "var(--surface)" : "var(--bg)", borderBottom: "1px solid var(--border)" }}
                    >
                      <td className="px-4 py-3 font-bold text-white">{p.symbol}</td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded text-xs font-bold tracking-wide" style={{ background: p.side === "LONG" ? "#052e16" : "#1f0a0a", color: p.side === "LONG" ? "var(--green)" : "var(--red)" }}>
                          {p.side}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs" style={{ color: "var(--text)" }}>{p.quantity}</td>
                      <td className="px-4 py-3 font-mono text-xs" style={{ color: "var(--text)" }}>{fmt(p.entryPrice)}</td>
                      <td className="px-4 py-3 font-mono text-xs font-semibold" style={{ color: "white" }}>{fmt(p.markPrice)}</td>
                      <td className="px-4 py-3 font-mono font-bold" style={{ color: c }}>{p.pnl >= 0 ? "+" : ""}₮ {fmt(p.pnl)}</td>
                      <td className="px-4 py-3 font-mono font-bold" style={{ color: c }}>{p.pnlPct >= 0 ? "+" : ""}{fmt(p.pnlPct)}%</td>
                      <td className="px-4 py-3 font-mono text-xs" style={{ color: "var(--muted)" }}>{p.leverage}x</td>
                      <td className="px-4 py-3 font-mono text-xs" style={{ color: distToLiq < 10 ? "var(--red)" : distToLiq < 25 ? "var(--yellow)" : "var(--muted)" }}>
                        {fmt(distToLiq, 1)}% away
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
