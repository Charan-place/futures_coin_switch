import { NextRequest, NextResponse } from "next/server";
import { placeOrder } from "@/lib/coinswitch";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    const { symbol, side, quantity } = await req.json();
    if (!symbol || !side || !quantity) {
      return NextResponse.json({ error: "symbol, side, quantity required" }, { status: 400 });
    }
    if (side !== "BUY" && side !== "SELL") {
      return NextResponse.json({ error: "side must be BUY or SELL" }, { status: 400 });
    }
    const result = await placeOrder({ symbol, side, quantity: Number(quantity) });
    return NextResponse.json(result);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
