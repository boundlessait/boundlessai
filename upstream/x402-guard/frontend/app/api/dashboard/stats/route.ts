export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { MOCK_POLICIES, MOCK_STATS, MOCK_TRANSACTIONS, isDemoMode } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";

// Fix Python timestamp: "2026-04-10 05:48:43.510394+00:00" -> valid JS Date
const parseTs = (s: unknown): Date => {
  const str = String(s ?? "").replace(" ", "T").replace(/(\.\d{3})\d+/, "$1");
  const d = new Date(str);
  return isNaN(d.getTime()) ? new Date(0) : d;
};

export async function GET() {
  try {
    if (isDemoMode()) return NextResponse.json(MOCK_STATS);
    const [policiesRes, txAllRes] = await Promise.all([
      fetch(`${BACKEND}/policies/`, { cache: "no-store" }),
      fetch(`${BACKEND}/guard/transactions/all?limit=500`, { cache: "no-store" }).catch(() => null),
    ]);

    if (!policiesRes.ok) throw new Error(`Policies ${policiesRes.status}`);

    const policies: Record<string, unknown>[] = await policiesRes.json();
    const txs: Record<string, unknown>[] = txAllRes?.ok
      ? await (txAllRes as Response).json()
      : [];

    // Only count transactions from agents that have a policy
    const validAgents = new Set(policies.map((p) => p.agent_id as string));
    const validTxs = txs.filter((t) => validAgents.has(t.agent_id as string));

    const now = new Date();
    // UTC calendar day start
    const todayStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
    const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));

    const isSpend = (t: Record<string, unknown>) =>
      t.status === "approved" || t.status === "soft_alert";

    const todayTxs = validTxs.filter(
      (t) => parseTs(t.timestamp) >= todayStart
    );
    const monthTxs = validTxs.filter(
      (t) => parseTs(t.timestamp) >= monthStart
    );

    const agentIdSet = new Set(policies.map((p) => p.agent_id as string));
    const agentIds = Array.from(agentIdSet);

    const approvedToday = todayTxs.filter((t) => t.status === "approved");
    const softToday     = todayTxs.filter((t) => t.status === "soft_alert");
    const blockedToday  = todayTxs.filter((t) => t.status === "blocked");

    // spentToday = approved + soft_alert only (blocked = prevented, not actual spend)
    const spentToday = todayTxs
      .filter((t) => isSpend(t))
      .reduce((s, t) => s + Math.round((t.amount as number) * 100), 0);

    const spentMonth = monthTxs
      .filter((t) => isSpend(t))
      .reduce((s, t) => s + Math.round((t.amount as number) * 100), 0);

    // Compute per-agent spend to determine actual status
    const agentSpend = new Map<string, number>();
    for (const p of policies) {
      const agId = p.agent_id as string;
      const limit = Math.round((p.daily_limit as number) * 100);
      const agTxs = validTxs.filter(
        (t) => t.agent_id === agId &&
        parseTs(t.timestamp) >= todayStart &&
        isSpend(t)
      );
      const spent = agTxs.reduce((s, t) => s + Math.round((t.amount as number) * 100), 0);
      agentSpend.set(agId, limit > 0 ? spent / limit : 0);
    }

    const activeCount  = policies.filter((p) => {
      if (!p.active) return false;
      const pct = agentSpend.get(p.agent_id as string) ?? 0;
      return pct < 0.95;
    }).length;
    const pausedCount  = policies.filter((p) => {
      if (!p.active) return false;
      const pct = agentSpend.get(p.agent_id as string) ?? 0;
      return pct >= 0.95 && pct < 1.0;
    }).length;
    const blockedCount = policies.filter((p) => {
      if (!p.active) return true;
      const pct = agentSpend.get(p.agent_id as string) ?? 0;
      return pct >= 1.0;
    }).length;

    return NextResponse.json({
      totalAgents:     agentIds.length,
      activeAgents:    activeCount,
      pausedAgents:    pausedCount,
      blockedAgents:   blockedCount,
      totalSpentToday: spentToday,
      totalSpentMonth: spentMonth,
      txApprovedToday: approvedToday.length,
      txDeniedToday:   blockedToday.length,
      txFlaggedToday:  softToday.length,
      alertsCount:     softToday.length + blockedToday.length,
    });
  } catch (err) {
    if (isDemoMode()) return NextResponse.json(MOCK_STATS);
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
