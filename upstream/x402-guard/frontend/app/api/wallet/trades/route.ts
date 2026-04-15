export const dynamic = "force-dynamic";
import { NextResponse } from "next/server";
import { mockTradeRows, isDemoMode } from "@/lib/mock-data";

const BACKEND = process.env.BACKEND_URL || "https://x402-guard.fly.dev";
const RPC     = process.env.XLAYER_RPC_URL || "https://testrpc.xlayer.tech";

// Map pay_to addresses/domains to readable names
function labelRecipient(payTo: string): string {
  const map: Record<string, string> = {
    "api.openai.com":       "OpenAI API",
    "api.anthropic.com":    "Anthropic API",
    "api.stripe.com":       "Stripe",
    "api.cloudflare.com":   "Cloudflare",
    "storage.googleapis.com": "GCS Storage",
    "api.cohere.com":       "Cohere API",
  };
  if (map[payTo]) return map[payTo];
  if (payTo.startsWith("0x") && payTo.length === 42) {
    return `${payTo.slice(0, 8)}…${payTo.slice(-4)}`;
  }
  return payTo.slice(0, 20);
}

function tradeType(botType: string, txStatus: string): string {
  if (txStatus === "blocked") return "REJECTED";
  if (txStatus === "soft_alert") return "ALERT";
  const types: Record<string, string> = {
    sniper:     "SNIPE",
    arbitrage:  "ARB",
    prediction: "LONG",
    sentiment:  "BUY",
    custom:     "TX",
  };
  return types[botType] ?? "TX";
}

export async function GET(req: Request) {
  try {
    if (isDemoMode()) return NextResponse.json(mockTradeRows());
    const limit = new URL(req.url).searchParams.get("limit") ?? "20";

    // Get policies for bot name/type lookup
    const polRes  = await fetch(`${BACKEND}/policies/`, { cache: "no-store" });
    const policies: any[] = polRes.ok ? await polRes.json() : [];
    const botMap: Record<string, { name: string; bot_type: string }> = {};
    for (const p of policies) {
      botMap[p.agent_id] = { name: p.name || p.agent_id, bot_type: p.bot_type || "custom" };
    }

    // Get recent transactions across all agents
    const txRes = await fetch(
      `${BACKEND}/guard/transactions/all?limit=${limit}`,
      { cache: "no-store" }
    ).catch(() => null);
    const txs: any[] = txRes?.ok ? await txRes.json() : [];

    const trades = txs.map((tx: any) => {
      const bot  = botMap[tx.agent_id] ?? { name: tx.agent_id, bot_type: "custom" };
      const type = tradeType(bot.bot_type, tx.status);
      return {
        id:        tx.id,
        bot:       bot.name,
        bot_type:  bot.bot_type,
        agent_id:  tx.agent_id,
        action:    type,
        recipient: labelRecipient(tx.pay_to),
        amount:    tx.amount,
        asset:     "USDC",
        status:    tx.status,
        reason:    tx.reason,
        timestamp: tx.timestamp,
      };
    });

    return NextResponse.json(trades);
  } catch {
    return NextResponse.json(isDemoMode() ? mockTradeRows() : []);
  }
}
