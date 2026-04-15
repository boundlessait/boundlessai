export const dynamic = "force-dynamic";
import { NextResponse } from "next/server";
import { MOCK_DOMAINS, MOCK_TRANSACTIONS, isDemoMode } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";
const AGENTS = ["agent-alpha", "agent-beta", "agent-gamma", "agent-delta"];

export async function GET() {
  try {
    if (isDemoMode()) return NextResponse.json(MOCK_DOMAINS);
    // Fetch all transactions and aggregate by domain (pay_to)
    const results = await Promise.all(
      AGENTS.map(id =>
        fetch(`${BACKEND}/guard/transactions/${id}?limit=100`, { cache: "no-store" })
          .then(r => r.ok ? r.json() : null)
          .catch(() => null)
      )
    );

    const domainMap = new Map<string, { amount: number; txs: number }>();

    for (const result of results) {
      if (!result?.transactions) continue;
      for (const tx of result.transactions) {
        if (tx.status === "blocked") continue;
        const raw = tx.pay_to || "unknown";
        // If looks like a proper domain (has dots, not a hex address)
        const stripped = raw.replace(/^0x/, "");
        let clean: string;
        if (stripped.includes(".") && !/^[0-9a-fA-F]{38,}$/.test(stripped)) {
          clean = stripped.split("/")[0];          // e.g. "api.openai.com"
        } else if (/^[0-9a-fA-F]{38,40}$/.test(stripped)) {
          clean = `0x${stripped.slice(0, 6)}…${stripped.slice(-4)}`;  // contract address
        } else {
          clean = stripped.slice(0, 20);
        }
        const existing = domainMap.get(clean) || { amount: 0, txs: 0 };
        domainMap.set(clean, {
          amount: existing.amount + (tx.amount ?? 0),
          txs: existing.txs + 1,
        });
      }
    }

    const sorted = Array.from(domainMap.entries())
      .sort((a, b) => b[1].amount - a[1].amount)
      .slice(0, 5)
      .map(([domain, { amount, txs }]) => ({
        domain,
        amount: Math.round(amount * 100),  // cents
        txs,
      }));

    return NextResponse.json(sorted);
  } catch {
    return NextResponse.json(isDemoMode() ? MOCK_DOMAINS : []);
  }
}
