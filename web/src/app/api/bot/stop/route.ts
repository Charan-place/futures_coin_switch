import { NextResponse } from "next/server";
import { stopBot } from "@/lib/bot-process";

export const dynamic = "force-dynamic";

export async function POST() {
  try {
    stopBot();
    return NextResponse.json({ running: false });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
