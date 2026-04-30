import { NextResponse } from "next/server";
import { fetchPositions } from "@/lib/coinswitch";

export async function GET() {
  try {
    const data = await fetchPositions();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
