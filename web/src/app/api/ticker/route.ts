import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const PAIRS = [
  "1000PEPEUSDT","FIGHTUSDT","GALAUSDT","XANUSDT","1000BONKUSDT",
  "BLESSUSDT","JCTUSDT","TRUUSDT","PENGUUSDT","BOMEUSDT","MEMEUSDT","GPSUSDT",
];

export async function GET() {
  try {
    const url = `https://fapi.binance.com/fapi/v1/ticker/24hr?symbols=${JSON.stringify(PAIRS)}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error("Binance error");
    const data: { symbol: string; lastPrice: string; priceChangePercent: string }[] = await res.json();
    return NextResponse.json(
      data.map((d) => ({
        symbol: d.symbol,
        price: parseFloat(d.lastPrice),
        changePct: parseFloat(d.priceChangePercent),
      }))
    );
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
