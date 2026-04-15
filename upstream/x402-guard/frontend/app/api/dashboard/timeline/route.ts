export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { MOCK_POLICIES, MOCK_TIMELINE, MOCK_TRANSACTIONS, isDemoMode } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";

const parseTs = (s: unknown): number => {
  const str = String(s ?? "").replace(" ", "T").replace(/(\.\d{3})\d+/, "$1");
  const d = new Date(str);
  return isNaN(d.getTime()) ? 0 : d.getTime();
};

export async function GET(req: NextRequest) {
  const hours = parseInt(req.nextUrl.searchParams.get("hours") || "24", 10);

  try {
    if (isDemoMode()) return NextResponse.json(MOCK_TIMELINE.slice(-Math.min(hours, MOCK_TIMELINE.length)));
    const [txAllRes, polRes] = await Promise.all([
      fetch(`${BACKEND}/guard/transactions/all?limit=500`, { cache: "no-store" }).catch(() => null),
      fetch(`${BACKEND}/policies/`, { cache: "no-store" }).catch(() => null),
    ]);
    const txs: Record<string, unknown>[] = txAllRes?.ok ? await txAllRes.json() : [];
    const policies: Record<string, unknown>[] = polRes?.ok ? await polRes.json() : [];

    // Build agent_id → display name from policies (newest active policy per agent)
    const byAgent = new Map<string, Record<string, unknown>>();
    for (const p of policies) {
      const key = p.agent_id as string;
      const existing = byAgent.get(key);
      if (!existing || new Date(p.created_at as string) > new Date(existing.created_at as string)) {
        byAgent.set(key, p);
      }
    }
    // chart key = policy name (trimmed to first word for legend brevity)
    const agentMap: Record<string, string> = {};
    const chartKeys: string[] = [];
    Array.from(byAgent.entries()).forEach(([agId, p]) => {
      const name = (p.name as string) || agId;
      agentMap[agId] = name;
      chartKeys.push(name);
    });
    // Fallback if no policies
    if (chartKeys.length === 0) {
      ["agent-alpha","agent-beta","agent-gamma","agent-delta"].forEach(id => {
        agentMap[id] = id; chartKeys.push(id);
      });
    }

    const emptyBucket = () => Object.fromEntries(chartKeys.map(k => [k, 0]));

    const nowMs = Date.now();
    const bucketMs = 3600 * 1000; // 1 hour buckets

    // Build buckets aligned to UTC hours
    const buckets: Record<number, Record<string, number>> = {};
    for (let i = hours - 1; i >= 0; i--) {
      const bucketStart = Math.floor((nowMs - i * bucketMs) / bucketMs) * bucketMs;
      buckets[bucketStart] = emptyBucket();
    }

    for (const tx of txs) {
      if (tx.status === "blocked") continue;

      const tsMs = parseTs(tx.timestamp);
      if (!tsMs) continue;

      const ageMs = nowMs - tsMs;
      if (ageMs > hours * bucketMs) continue;

      const bucketStart = Math.floor(tsMs / bucketMs) * bucketMs;

      const key = agentMap[tx.agent_id as string];
      if (!key) continue;

      if (!buckets[bucketStart]) buckets[bucketStart] = emptyBucket();
      buckets[bucketStart][key] = (buckets[bucketStart][key] || 0) + Math.round((tx.amount as number) * 100);
    }

    // Sort by time, format label as HH:MM
    const result = Object.entries(buckets)
      .sort(([a], [b]) => parseInt(a) - parseInt(b))
      .map(([ts, vals]) => ({
        time: new Date(parseInt(ts)).toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
          timeZone: "UTC",
        }),
        ...vals,
      }));

    return NextResponse.json(result);
  } catch (err) {
    if (isDemoMode()) return NextResponse.json(MOCK_TIMELINE.slice(-Math.min(hours, MOCK_TIMELINE.length)));
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
