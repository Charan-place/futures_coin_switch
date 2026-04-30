import { NextResponse } from "next/server";
import { fetchPortfolio } from "@/lib/coinswitch";

export async function GET() {
  try {
    const data = await fetchPortfolio();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
