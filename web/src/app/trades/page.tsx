"use client";
import { useEffect, useState, useCallback } from "react";
import type { Transaction } from "@/lib/types";

function fmt(n: number, d = 4) {
  return n.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
}

export default function TradesPage() {
  const [trades, setTrades] = useState<Transaction[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/trades");
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setTrades(data);
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
  }, [refresh]);

  const totalFees = trades.reduce((s, t) => s + t.fee + t.tds + t.gst, 0);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Recent Transactions</h1>
          {lastUpdated && (
            <p style={{ color: "var(--muted)" }} className="text-xs mt-1">
              Fetched {lastUpdated.toLocaleTimeString()} · last 3 fills per pair
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {trades.length > 0 && (
            <span
              className="text-xs px-2 py-1 rounded"
              style={{ background: "var(--border)", color: "var(--muted)" }}
            >
              Total fees ₮ {fmt(totalFees, 2)}
            </span>
          )}
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
      ) : trades.length === 0 ? (
        <div
          className="rounded-xl p-12 text-center text-sm"
          style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}
        >
          No recent transactions
        </div>
      ) : (
        <div
          className="rounded-xl overflow-hidden"
          style={{ border: "1px solid var(--border)" }}
        >
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
                {["Symbol", "Side", "Qty", "Price", "Fee", "TDS", "GST", "Total Cost"].map((h) => (
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
              {trades.map((t, i) => {
                const totalCost = t.fee + t.tds + t.gst;
                const isBuy = t.side === "BUY";
                return (
                  <tr
                    key={i}
                    style={{
                      background: i % 2 === 0 ? "var(--surface)" : "var(--bg)",
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <td className="px-4 py-3 font-medium text-white">{t.symbol}</td>
                    <td className="px-4 py-3">
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{
                          background: isBuy ? "#052e16" : "#1f0a0a",
                          color: isBuy ? "var(--green)" : "var(--red)",
                        }}
                      >
                        {t.side}
                      </span>
                    </td>
                    <td className="px-4 py-3" style={{ color: "var(--text)" }}>
                      {t.quantity}
                    </td>
                    <td className="px-4 py-3" style={{ color: "var(--text)" }}>
                      ₮ {fmt(t.price, 4)}
                    </td>
                    <td className="px-4 py-3" style={{ color: "var(--muted)" }}>
                      ₮ {fmt(t.fee)}
                    </td>
                    <td className="px-4 py-3" style={{ color: "var(--muted)" }}>
                      ₮ {fmt(t.tds)}
                    </td>
                    <td className="px-4 py-3" style={{ color: "var(--muted)" }}>
                      ₮ {fmt(t.gst)}
                    </td>
                    <td className="px-4 py-3 font-medium" style={{ color: "var(--red)" }}>
                      ₮ {fmt(totalCost)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
