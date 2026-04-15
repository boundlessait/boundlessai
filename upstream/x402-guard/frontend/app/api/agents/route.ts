export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { MOCK_POLICIES, MOCK_TRANSACTIONS, isDemoMode } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";

const parseTs = (s: unknown): Date => {
  const str = String(s ?? "").replace(" ", "T").replace(/(\.\d{3})\d+/, "$1");
  const d = new Date(str);
  return isNaN(d.getTime()) ? new Date(0) : d;
};

function policyToAgent(
  p: Record<string, unknown>,
  txs: Record<string, unknown>[]
) {
  const agentTxs = txs.filter((t) => t.agent_id === p.agent_id);

  // UTC day start (midnight UTC)
  const now = new Date();
  const todayStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));

  // Only count approved + soft_alert as actual spend (blocked = prevented, not spent)
  const isSpend = (t: Record<string, unknown>) =>
    t.status === "approved" || t.status === "soft_alert";

  const spentToday = agentTxs
    .filter((t) => isSpend(t) && parseTs(t.timestamp) >= todayStart)
    .reduce((s, t) => s + Math.round((t.amount as number) * 100), 0);

  const spentTotal = agentTxs
    .filter((t) => isSpend(t))
    .reduce((s, t) => s + Math.round((t.amount as number) * 100), 0);

  const dailyLimitCents = Math.round((p.daily_limit as number) * 100);
  const pct = dailyLimitCents > 0 ? spentToday / dailyLimitCents : 0;

  const active = p.active as boolean;
  const status = pct >= 1.0
    ? "blocked"           // budget exhausted = blocked
    : !active
    ? "paused"            // manually stopped = paused (not blocked)
    : pct >= 0.95
    ? "paused"            // approaching limit = paused
    : "active";

  const rawId  = p.agent_id as string;
  // Use policy name if set, otherwise derive from agent_id
  const policyName = p.name as string;
  const derivedName = rawId.split(/[-_]/).map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
  const finalName = (policyName && policyName !== "Default Policy") ? policyName : derivedName;

  return {
    id:          rawId,
    name:        finalName,
    description: (p.description as string) || `x402 Guard — ${finalName}`,
    bot_type:    p.bot_type  ?? null,
    status,
    walletAddress: (p.wallet_address as string) || null,
    spentToday,
    dailyLimit: dailyLimitCents,
    spentTotal,
    totalLimit: dailyLimitCents * 30,
    txCount: agentTxs.length,
    lastActive: agentTxs.length > 0 ? (agentTxs[0].timestamp as string) : (p.created_at as string),
    createdAt: p.created_at as string,
    tags: ["x402", "xlayer", (p.bot_type as string) ?? "custom"],
    policyId: p.id,
  };
}

export async function GET() {
  try {
    if (isDemoMode()) {
      const agents = MOCK_POLICIES.map((p) => policyToAgent(p as unknown as Record<string, unknown>, MOCK_TRANSACTIONS as unknown as Record<string, unknown>[]));
      const order: Record<string, number> = { active: 0, paused: 1, blocked: 2 };
      agents.sort((a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3));
      return NextResponse.json(agents);
    }
    const [policiesRes, txRes] = await Promise.all([
      fetch(`${BACKEND}/policies/`, { cache: "no-store" }),
      fetch(`${BACKEND}/guard/transactions/all?limit=500`, { cache: "no-store" }).catch(() => null),
    ]);

    if (!policiesRes.ok) throw new Error(`Policies ${policiesRes.status}`);

    const policies: Record<string, unknown>[] = await policiesRes.json();
    const txs: Record<string, unknown>[] = txRes?.ok
      ? await (txRes as Response).json()
      : [];

    // Deduplicate: newest active policy per agent
    const byAgent = new Map<string, Record<string, unknown>>();
    for (const p of policies) {
      const key = p.agent_id as string;
      const existing = byAgent.get(key);
      if (
        !existing ||
        new Date(p.created_at as string) >
          new Date(existing.created_at as string)
      ) {
        byAgent.set(key, p);
      }
    }

    const agents = Array.from(byAgent.values()).map((p) =>
      policyToAgent(p, txs)
    );

    // Sort: active first, then paused, then blocked
    const order: Record<string, number> = { active: 0, paused: 1, blocked: 2 };
    agents.sort((a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3));

    return NextResponse.json(agents);
  } catch (err) {
    if (isDemoMode()) {
      const agents = MOCK_POLICIES.map((p) => policyToAgent(p as unknown as Record<string, unknown>, MOCK_TRANSACTIONS as unknown as Record<string, unknown>[]));
      return NextResponse.json(agents);
    }
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
