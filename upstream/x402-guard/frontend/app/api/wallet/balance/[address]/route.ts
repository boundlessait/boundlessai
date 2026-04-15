export const dynamic = "force-dynamic";
import { NextResponse } from "next/server";
import { MOCK_BALANCES, isDemoMode } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";

export async function GET(_: Request, { params }: { params: { address: string } }) {
  try {
    if (isDemoMode()) {
      const found = MOCK_BALANCES.find((b) => b.address.toLowerCase() === params.address.toLowerCase());
      return NextResponse.json(found || { okb: 0, usdc: 0, total_usd: 0 });
    }
    const res = await fetch(`${BACKEND}/wallet/balance/${params.address}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) return NextResponse.json({ error: "RPC error" }, { status: res.status });
    return NextResponse.json(await res.json());
  } catch {
    if (isDemoMode()) {
      const found = MOCK_BALANCES.find((b) => b.address.toLowerCase() === params.address.toLowerCase());
      return NextResponse.json(found || { okb: 0, usdc: 0, total_usd: 0 });
    }
    return NextResponse.json({ error: "unavailable" }, { status: 503 });
  }
}
