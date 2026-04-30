"use client";
import { useEffect, useState, useRef } from "react";

type Tick = { symbol: string; price: number; changePct: number };

export default function TickerBar() {
  const [ticks, setTicks] = useState<Tick[]>([]);
  const [prev, setPrev] = useState<Record<string, number>>({});
  const [flash, setFlash] = useState<Record<string, "up" | "down">>({});

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch("/api/ticker");
        if (!r.ok) return;
        const data: Tick[] = await r.json();
        if (!Array.isArray(data)) return;

        setFlash((old) => {
          const next: Record<string, "up" | "down"> = {};
          data.forEach((t) => {
            if (prev[t.symbol] !== undefined) {
              if (t.price > prev[t.symbol]) next[t.symbol] = "up";
              else if (t.price < prev[t.symbol]) next[t.symbol] = "down";
            }
          });
          return { ...old, ...next };
        });

        setTimeout(() => setFlash({}), 600);

        setPrev((p) => {
          const next = { ...p };
          data.forEach((t) => { next[t.symbol] = t.price; });
          return next;
        });

        setTicks(data);
      } catch { /* silent */ }
    };
    load();
    const t = setInterval(load, 5_000);
    return () => clearInterval(t);
  }, []);

  if (ticks.length === 0) return null;

  const repeated = [...ticks, ...ticks]; // duplicate for seamless loop

  return (
    <div
      style={{ background: "#080d16", borderBottom: "1px solid var(--border)", overflow: "hidden" }}
      className="relative h-8 flex items-center"
    >
      <style>{`
        @keyframes ticker-scroll {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .ticker-track {
          display: flex;
          gap: 0;
          animation: ticker-scroll 40s linear infinite;
          will-change: transform;
          white-space: nowrap;
        }
        .ticker-track:hover { animation-play-state: paused; }
        .flash-up { color: #22c55e !important; }
        .flash-down { color: #ef4444 !important; }
      `}</style>
      <div className="ticker-track">
        {repeated.map((t, i) => {
          const pos = t.changePct >= 0;
          const f = flash[t.symbol];
          return (
            <span
              key={t.symbol + i}
              className={`inline-flex items-center gap-2 px-4 text-xs ${f === "up" ? "flash-up" : f === "down" ? "flash-down" : ""}`}
              style={{ borderRight: "1px solid var(--border)", height: "2rem" }}
            >
              <span style={{ color: "var(--muted)" }}>{t.symbol.replace("USDT", "")}</span>
              <span style={{ color: "white", fontVariantNumeric: "tabular-nums" }}>
                {t.price < 0.01 ? t.price.toFixed(6) : t.price < 1 ? t.price.toFixed(4) : t.price.toFixed(2)}
              </span>
              <span style={{ color: pos ? "var(--green)" : "var(--red)" }}>
                {pos ? "▲" : "▼"} {Math.abs(t.changePct).toFixed(2)}%
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
