import { NextRequest, NextResponse } from "next/server";
import { placeOrder } from "@/lib/coinswitch";

export const dynamic = "force-dynamic";

// Close a position by placing a reduce-only opposite order
export async function POST(req: NextRequest) {
  try {
    const { symbol, side, quantity } = await req.json();
    if (!symbol || !side || !quantity) {
      return NextResponse.json({ error: "symbol, side, quantity required" }, { status: 400 });
    }
    // To close: LONG → SELL reduce_only, SHORT → BUY reduce_only
    const closeSide = side === "LONG" ? "SELL" : "BUY";
    const result = await placeOrder({ symbol, side: closeSide, quantity: Number(quantity), reduceOnly: true });
    return NextResponse.json(result);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
