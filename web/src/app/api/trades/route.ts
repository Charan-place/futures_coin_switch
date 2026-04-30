import { NextResponse } from "next/server";
import { fetchTransactions } from "@/lib/coinswitch";

export async function GET() {
  try {
    const data = await fetchTransactions();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
