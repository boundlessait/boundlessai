export const dynamic = "force-dynamic";
import { NextResponse } from "next/server";
import { MOCK_TRANSACTIONS, isDemoMode } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";

interface PnlPoint {
  time: string;
  approved: number;
  blocked: number;
  cumApproved: number;
  cumBlocked: number;
}

export async function GET() {
  try {
    // Fetch raw transactions from backend (this endpoint is fast + reliable)
    const res = await fetch(
      `${BACKEND}/guard/transactions/all?limit=500`,
      { cache: "no-store", signal: AbortSignal.timeout(12000) }
    ).catch(() => null);

    const txs: any[] = isDemoMode() ? MOCK_TRANSACTIONS : ((res?.ok ? await res.json().catch(() => []) : []) ?? []);

    const now   = Date.now();
    const buckets: PnlPoint[] = [];

    for (let h = 23; h >= 0; h--) {
      const startMs = now - (h + 1) * 3_600_000;
      const endMs   = now - h        * 3_600_000;
      const label   = new Date(endMs).toISOString().slice(11, 16); // HH:MM UTC

      let approved = 0;
      let blocked  = 0;

      for (const tx of txs) {
        // Fix Python timestamp format: space→T, truncate microseconds to ms
        const tsStr = String(tx.timestamp ?? "").replace(" ", "T").replace(/(\.\d{3})\d+/, "$1");
        const ts = new Date(tsStr).getTime();
        if (isNaN(ts) || ts < startMs || ts >= endMs) continue;
        const amt = parseFloat(tx.amount) || 0;
        if (tx.status === "blocked") blocked  += amt;
        else                         approved += amt;
      }

      buckets.push({
        time:        label,
        approved:    Math.round(approved  * 100) / 100,
        blocked:     Math.round(blocked   * 100) / 100,
        cumApproved: 0,
        cumBlocked:  0,
      });
    }

    // Cumulative sums
    let cumA = 0, cumB = 0;
    for (const b of buckets) {
      cumA += b.approved;  b.cumApproved = Math.round(cumA * 100) / 100;
      cumB += b.blocked;   b.cumBlocked  = Math.round(cumB * 100) / 100;
    }

    return NextResponse.json(buckets);
  } catch {
    return NextResponse.json([]);
  }
}
