export const dynamic = "force-dynamic";
import { NextResponse } from "next/server";
import { MOCK_BALANCES, isDemoMode } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";

export async function GET() {
  try {
    if (isDemoMode()) return NextResponse.json(MOCK_BALANCES);
    const res = await fetch(`${BACKEND}/wallet/balances`, {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),  // RPC calls can be slow
    });
    if (!res.ok) return NextResponse.json([], { status: 200 });
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(isDemoMode() ? MOCK_BALANCES : [], { status: 200 });
  }
}
