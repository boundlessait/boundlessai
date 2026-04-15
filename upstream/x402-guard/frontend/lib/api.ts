// ─── Types ────────────────────────────────────────────────────────────────────

export type AgentStatus = "active" | "paused" | "blocked";
export type TransactionStatus = "approved" | "soft_alert" | "blocked";

export interface Agent {
  id:            string;
  name:          string;
  description:   string;
  bot_type:      string | null;
  status:        AgentStatus;
  walletAddress: string | null;
  spentToday:    number;   // cents
  dailyLimit:    number;   // cents
  spentTotal:    number;   // cents
  totalLimit:    number;   // cents
  txCount:       number;
  lastActive:    string;
  createdAt:     string;
  tags:          string[];
  policyId:      string;
}

export interface Transaction {
  id:        string;
  agent_id:  string;
  amount:    number;
  asset:     string;
  pay_to:    string;
  network:   string;
  timestamp: string;
  status:    TransactionStatus;
  reason:    string;
}

export interface DashboardStats {
  totalAgents:     number;
  activeAgents:    number;
  pausedAgents:    number;
  blockedAgents:   number;
  totalSpentToday: number;   // cents
  totalSpentMonth: number;   // cents
  txApprovedToday: number;
  txDeniedToday:   number;
  txFlaggedToday:  number;
  alertsCount:     number;
}

// ─── Formatters ───────────────────────────────────────────────────────────────

export function formatUSD(cents: number): string {
  const dollars = cents / 100;
  if (dollars >= 1000) return `$${(dollars / 1000).toFixed(1)}k`;
  return `$${dollars.toFixed(2)}`;
}

export function formatTimestamp(ts: string): string {
  const date = new Date(ts);
  if (isNaN(date.getTime())) return ts;
  const diffMs  = Date.now() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr  = Math.floor(diffMin / 60);
  if (diffMin < 1)  return "now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24)  return `${diffHr}h ago`;
  return date.toLocaleDateString();
}
