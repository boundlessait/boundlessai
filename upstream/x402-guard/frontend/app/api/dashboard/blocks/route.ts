export const dynamic = "force-dynamic";
import { NextResponse } from "next/server";
import { MOCK_BLOCK_REASONS, MOCK_TRANSACTIONS, isDemoMode } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";
const AGENTS = ["agent-alpha", "agent-beta", "agent-gamma", "agent-delta"];

export async function GET() {
  try {
    if (isDemoMode()) return NextResponse.json(MOCK_BLOCK_REASONS);
    const results = await Promise.all(
      AGENTS.map(id =>
        fetch(`${BACKEND}/guard/transactions/${id}?limit=100`, { cache: "no-store" })
          .then(r => r.ok ? r.json() : null)
          .catch(() => null)
      )
    );

    const reasons = new Map<string, number>();

    for (const result of results) {
      if (!result?.transactions) continue;
      for (const tx of result.transactions) {
        if (tx.status !== "blocked" && tx.status !== "soft_alert") continue;
        const r = tx.reason || "unknown";
        // Normalize reason to category
        let cat = "other";
        if (r.toLowerCase().includes("daily"))   cat = "daily limit exceeded";
        else if (r.toLowerCase().includes("per-tx") || r.toLowerCase().includes("transaction limit")) cat = "per-tx limit exceeded";
        else if (r.toLowerCase().includes("blacklist")) cat = "blacklisted domain";
        else if (r.toLowerCase().includes("approaching") || r.toLowerCase().includes("soft")) cat = "approaching limit";
        else if (r.toLowerCase().includes("anomaly") || r.toLowerCase().includes("pattern")) cat = "anomaly detected";
        reasons.set(cat, (reasons.get(cat) ?? 0) + 1);
      }
    }

    const total = Array.from(reasons.values()).reduce((a, b) => a + b, 0);
    const sorted = Array.from(reasons.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([reason, count]) => ({
        reason,
        count,
        pct: total > 0 ? Math.round((count / total) * 100) : 0,
        amber: reason.includes("approaching") || reason.includes("anomaly"),
      }));

    return NextResponse.json(sorted);
  } catch {
    return NextResponse.json(isDemoMode() ? MOCK_BLOCK_REASONS : []);
  }
}
