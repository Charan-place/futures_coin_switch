import { NextRequest, NextResponse } from "next/server";
import { startBot } from "@/lib/bot-process";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    const { mode, balance } = await req.json();
    if (mode !== "paper" && mode !== "live") {
      return NextResponse.json({ error: "mode must be paper or live" }, { status: 400 });
    }
    const s = startBot(mode, balance);
    return NextResponse.json(s);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
