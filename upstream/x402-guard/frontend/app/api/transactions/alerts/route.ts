export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { mockAlertTransactions, isDemoMode } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";

export async function GET(req: NextRequest) {
  const limit = parseInt(req.nextUrl.searchParams.get("limit") || "10", 10);

  try {
    if (isDemoMode()) return NextResponse.json(mockAlertTransactions().slice(0, limit));
    const res = await fetch(`${BACKEND}/guard/transactions/all`, { cache: "no-store" });
    if (!res.ok) throw new Error(`Backend ${res.status}`);

    const txs: Record<string, unknown>[] = await res.json();

    // Sort newest first, return limited set
    const sorted = txs
      .sort((a, b) =>
        new Date(b.timestamp as string).getTime() -
        new Date(a.timestamp as string).getTime()
      )
      .slice(0, limit);

    return NextResponse.json(sorted);
  } catch (err) {
    if (isDemoMode()) return NextResponse.json(mockAlertTransactions().slice(0, limit));
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
