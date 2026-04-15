import { NextRequest, NextResponse } from "next/server";
import { isDemoMode, mockSimulation } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    if (isDemoMode()) return NextResponse.json(mockSimulation());
    const res = await fetch(`${BACKEND}/ai/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    if (isDemoMode()) return NextResponse.json(mockSimulation());
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
