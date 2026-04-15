export const DEMO_CONTRACT = "0xaC4bbC6A7bA52622c1dF942A309CB6D835D363bB";
export const DEMO_EXPLORER = `https://www.oklink.com/x-layer-testnet/address/${DEMO_CONTRACT}`;
export const DEMO_URL = "https://x402-guard-deploy.vercel.app";

export const MOCK_POLICIES = [
  {
    id: "mock-pol-alpha",
    agent_id: "agent-alpha",
    name: "Sniper Bot #1",
    description: "Launch sniping strategy",
    bot_type: "sniper",
    wallet_address: "0x5672E35370b9ED17Cd9bC4f280078444429bE666",
    daily_limit: 500,
    hourly_limit: 200,
    per_tx_limit: 25,
    auto_approve_under: 1,
    soft_alert_threshold: 0.8,
    whitelist: ["0xSnipePool01", "0xSnipeTarget002"],
    blacklist: ["0xSnipePool99"],
    active: true,
    created_at: "2026-04-10T00:00:00.000Z",
  },
  {
    id: "mock-pol-beta",
    agent_id: "agent-beta",
    name: "Arbitrage Bot",
    description: "Cross-pool arbitrage strategy",
    bot_type: "arbitrage",
    wallet_address: "0xAb96ea0B4c3F1Fb90A5cA96b248a3dC561c976E2",
    daily_limit: 1000,
    hourly_limit: 400,
    per_tx_limit: 50,
    auto_approve_under: 2,
    soft_alert_threshold: 0.8,
    whitelist: ["0xArbPool001", "0xArbPool002"],
    blacklist: ["0xArbPool005"],
    active: true,
    created_at: "2026-04-10T00:01:00.000Z",
  },
  {
    id: "mock-pol-gamma",
    agent_id: "agent-gamma",
    name: "Prediction Bot",
    description: "Signal-driven prediction trading",
    bot_type: "prediction",
    wallet_address: "0xfA4cA6e03799BA7F207fcEFa50399C21c1376382",
    daily_limit: 400,
    hourly_limit: 120,
    per_tx_limit: 10,
    auto_approve_under: 0.5,
    soft_alert_threshold: 0.8,
    whitelist: ["0xPredOracle01", "0xPredOracle02"],
    blacklist: [],
    active: true,
    created_at: "2026-04-10T00:02:00.000Z",
  },
  {
    id: "mock-pol-delta",
    agent_id: "agent-delta",
    name: "Sentiment Bot",
    description: "Social sentiment execution bot",
    bot_type: "sentiment",
    wallet_address: "0x16067377bb02b3A86Eb3aC341d24Dd70C2C17a05",
    daily_limit: 300,
    hourly_limit: 100,
    per_tx_limit: 8,
    auto_approve_under: 0.5,
    soft_alert_threshold: 0.8,
    whitelist: ["0xSentFeed001", "0xSentFeed002"],
    blacklist: ["0xSentFeed009"],
    active: true,
    created_at: "2026-04-10T00:03:00.000Z",
  },
];

export const MOCK_TRANSACTIONS = [
  { id: "mock-tx-01", agent_id: "agent-beta", amount: 32.0, asset: "USDC", pay_to: "0xArbPool003", network: "eip155:1952", timestamp: "2026-04-11T02:58:00.000Z", status: "blocked", reason: "Recipient 0xArbPool003 not on whitelist." },
  { id: "mock-tx-02", agent_id: "agent-alpha", amount: 14.0, asset: "USDC", pay_to: "0xSnipeTarget002", network: "eip155:1952", timestamp: "2026-04-11T02:57:00.000Z", status: "approved", reason: "Transaction approved within all policy limits." },
  { id: "mock-tx-03", agent_id: "agent-delta", amount: 9.5, asset: "USDC", pay_to: "0xSentFeed003", network: "eip155:1952", timestamp: "2026-04-11T02:56:00.000Z", status: "blocked", reason: "Amount $9.50 exceeds per-tx limit $8.00 USDC" },
  { id: "mock-tx-04", agent_id: "agent-gamma", amount: 8.0, asset: "USDC", pay_to: "0xPredOracle01", network: "eip155:1952", timestamp: "2026-04-11T02:55:00.000Z", status: "approved", reason: "Transaction approved within all policy limits." },
  { id: "mock-tx-05", agent_id: "agent-beta", amount: 28.0, asset: "USDC", pay_to: "0xArbPool001", network: "eip155:1952", timestamp: "2026-04-11T02:54:00.000Z", status: "approved", reason: "Transaction approved within all policy limits." },
  { id: "mock-tx-06", agent_id: "agent-alpha", amount: 25.5, asset: "USDC", pay_to: "0xSnipePool99", network: "eip155:1952", timestamp: "2026-04-11T02:53:00.000Z", status: "blocked", reason: "Amount $25.50 exceeds per-tx limit $25.00 USDC" },
  { id: "mock-tx-07", agent_id: "agent-delta", amount: 7.0, asset: "USDC", pay_to: "0xSentFeed002", network: "eip155:1952", timestamp: "2026-04-11T02:52:00.000Z", status: "approved", reason: "Transaction approved within all policy limits." },
  { id: "mock-tx-08", agent_id: "agent-gamma", amount: 10.5, asset: "USDC", pay_to: "0xPredOracle05", network: "eip155:1952", timestamp: "2026-04-11T02:51:00.000Z", status: "blocked", reason: "Amount $10.50 exceeds per-tx limit $10.00 USDC" },
  { id: "mock-tx-09", agent_id: "agent-beta", amount: 21.5, asset: "USDC", pay_to: "0xArbPool002", network: "eip155:1952", timestamp: "2026-04-11T02:50:00.000Z", status: "approved", reason: "Transaction approved within all policy limits." },
  { id: "mock-tx-10", agent_id: "agent-delta", amount: 6.0, asset: "USDC", pay_to: "0xSentFeed001", network: "eip155:1952", timestamp: "2026-04-11T02:49:00.000Z", status: "approved", reason: "Transaction approved within all policy limits." },
];

export const MOCK_BALANCES = [
  { address: "0x5672E35370b9ED17Cd9bC4f280078444429bE666", okb: 0.67, usdc: 128.25, total_usd: 128.25, agent_id: "agent-alpha", name: "Sniper Bot #1" },
  { address: "0xAb96ea0B4c3F1Fb90A5cA96b248a3dC561c976E2", okb: 1.385, usdc: 176.80, total_usd: 176.80, agent_id: "agent-beta", name: "Arbitrage Bot" },
  { address: "0xfA4cA6e03799BA7F207fcEFa50399C21c1376382", okb: 0.305, usdc: 96.90, total_usd: 96.90, agent_id: "agent-gamma", name: "Prediction Bot" },
  { address: "0x16067377bb02b3A86Eb3aC341d24Dd70C2C17a05", okb: 0.303, usdc: 110.29, total_usd: 110.29, agent_id: "agent-delta", name: "Sentiment Bot" },
];

export const MOCK_STATS = {
  totalAgents: 4,
  activeAgents: 4,
  pausedAgents: 0,
  blockedAgents: 0,
  totalSpentToday: 8450,
  totalSpentMonth: 8450,
  txApprovedToday: 6,
  txDeniedToday: 4,
  txFlaggedToday: 0,
  alertsCount: 4,
};

export const MOCK_TIMELINE = [
  { time: "20:00", "Sniper Bot #1": 0, "Arbitrage Bot": 0, "Prediction Bot": 0, "Sentiment Bot": 0 },
  { time: "21:00", "Sniper Bot #1": 0, "Arbitrage Bot": 0, "Prediction Bot": 0, "Sentiment Bot": 0 },
  { time: "22:00", "Sniper Bot #1": 0, "Arbitrage Bot": 0, "Prediction Bot": 0, "Sentiment Bot": 0 },
  { time: "23:00", "Sniper Bot #1": 0, "Arbitrage Bot": 0, "Prediction Bot": 0, "Sentiment Bot": 0 },
  { time: "00:00", "Sniper Bot #1": 0, "Arbitrage Bot": 0, "Prediction Bot": 0, "Sentiment Bot": 0 },
  { time: "01:00", "Sniper Bot #1": 0, "Arbitrage Bot": 0, "Prediction Bot": 0, "Sentiment Bot": 0 },
  { time: "02:00", "Sniper Bot #1": 0, "Arbitrage Bot": 0, "Prediction Bot": 0, "Sentiment Bot": 0 },
  { time: "02:49", "Sniper Bot #1": 0, "Arbitrage Bot": 0, "Prediction Bot": 0, "Sentiment Bot": 600 },
  { time: "02:50", "Sniper Bot #1": 0, "Arbitrage Bot": 2150, "Prediction Bot": 0, "Sentiment Bot": 0 },
  { time: "02:52", "Sniper Bot #1": 0, "Arbitrage Bot": 0, "Prediction Bot": 0, "Sentiment Bot": 700 },
  { time: "02:54", "Sniper Bot #1": 0, "Arbitrage Bot": 2800, "Prediction Bot": 0, "Sentiment Bot": 0 },
  { time: "02:55", "Sniper Bot #1": 0, "Arbitrage Bot": 0, "Prediction Bot": 800, "Sentiment Bot": 0 },
  { time: "02:57", "Sniper Bot #1": 1400, "Arbitrage Bot": 0, "Prediction Bot": 0, "Sentiment Bot": 0 },
];

export const MOCK_DOMAINS = [
  { domain: "0xArbPool001", amount: 2800, txs: 1 },
  { domain: "0xArbPool002", amount: 2150, txs: 1 },
  { domain: "0xSnipeTarget002", amount: 1400, txs: 1 },
  { domain: "0xPredOracle01", amount: 800, txs: 1 },
  { domain: "0xSentFeed002", amount: 700, txs: 1 },
];

export const MOCK_BLOCK_REASONS = [
  { reason: "per-tx limit exceeded", count: 3, pct: 75, amber: false },
  { reason: "not on whitelist", count: 1, pct: 25, amber: false },
];

export function isDemoMode() {
  return process.env.X402_DEMO_MODE === "1" || process.env.NEXT_PUBLIC_DEMO_MODE === "1";
}

export function mockTradeRows() {
  const nameMap = Object.fromEntries(MOCK_POLICIES.map((p) => [p.agent_id, p.name]));
  const typeMap = Object.fromEntries(MOCK_POLICIES.map((p) => [p.agent_id, p.bot_type]));
  const actionMap: Record<string, string> = {
    "mock-tx-01": "REJECTED",
    "mock-tx-02": "SNIPE",
    "mock-tx-03": "REJECTED",
    "mock-tx-04": "LONG",
    "mock-tx-05": "ARB",
    "mock-tx-06": "REJECTED",
    "mock-tx-07": "BUY",
    "mock-tx-08": "REJECTED",
    "mock-tx-09": "ARB",
    "mock-tx-10": "BUY",
  };
  return MOCK_TRANSACTIONS.map((tx) => ({
    id: tx.id,
    bot: nameMap[tx.agent_id],
    bot_type: typeMap[tx.agent_id],
    agent_id: tx.agent_id,
    action: actionMap[tx.id] || "TX",
    recipient: tx.pay_to,
    amount: tx.amount,
    asset: tx.asset,
    status: tx.status,
    reason: tx.reason,
    timestamp: tx.timestamp,
  }));
}

export function mockAlertTransactions() {
  const nameMap = Object.fromEntries(MOCK_POLICIES.map((p) => [p.agent_id, p.name]));
  return MOCK_TRANSACTIONS.map((tx) => ({
    ...tx,
    amount: Math.round(tx.amount * 100),
    agentName: nameMap[tx.agent_id],
    recipient: tx.pay_to,
    url: `${DEMO_EXPLORER}`,
  }));
}


export function mockOnchainStats() {
  return { approved: 6, soft_alerts: 0, blocked: 4, contract_address: DEMO_CONTRACT, explorer_url: DEMO_EXPLORER, verified: true };
}

export function mockAnalysis(agentId: string) {
  const map: Record<string, any> = {
    "agent-alpha": {
      anomalies: [
        { type: "per-tx spike", severity: "high", description: "Repeated sniper attempts are hitting the configured per-tx ceiling.", amount: 25.5, domain: "0xSnipePool99" },
      ],
      suggested_policy: { daily_limit: 500, per_tx_limit: 25, whitelist: ["0xSnipePool01", "0xSnipeTarget002"], blacklist: ["0xSnipePool99"] },
      reasoning: ["Sniper bot shows healthy approved flow but occasional oversized attempts.", "Keep current daily cap, preserve block on known bad pool."],
      confidence_score: 0.84,
    },
    "agent-beta": {
      anomalies: [
        { type: "whitelist mismatch", severity: "medium", description: "Arbitrage bot keeps probing pools that are not approved for execution.", amount: 32.0, domain: "0xArbPool003" },
      ],
      suggested_policy: { daily_limit: 1000, per_tx_limit: 50, whitelist: ["0xArbPool001", "0xArbPool002"], blacklist: ["0xArbPool005"] },
      reasoning: ["Execution volume is healthy, but route validation should be tightened.", "Keep broad budget while limiting unapproved destinations."],
      confidence_score: 0.79,
    },
    "agent-gamma": {
      anomalies: [
        { type: "oracle oversize", severity: "medium", description: "Prediction bot occasionally exceeds safe single-order size.", amount: 10.5, domain: "0xPredOracle05" },
      ],
      suggested_policy: { daily_limit: 400, per_tx_limit: 10, whitelist: ["0xPredOracle01", "0xPredOracle02"], blacklist: [] },
      reasoning: ["Prediction bot is stable overall.", "Per-tx cap is the right control and is already catching outliers."],
      confidence_score: 0.77,
    },
    "agent-delta": {
      anomalies: [
        { type: "sentiment spam", severity: "low", description: "Sentiment bot emits many small buys; keep close watch on repeated retries.", amount: 9.5, domain: "0xSentFeed003" },
      ],
      suggested_policy: { daily_limit: 300, per_tx_limit: 8, whitelist: ["0xSentFeed001", "0xSentFeed002"], blacklist: ["0xSentFeed009"] },
      reasoning: ["Bot is low-risk but noisy.", "Strict per-tx cap remains effective."],
      confidence_score: 0.72,
    },
  };
  const chosen = map[agentId] || { anomalies: [], suggested_policy: { daily_limit: 100, per_tx_limit: 10, whitelist: [], blacklist: [] }, reasoning: ["No anomaly data available."], confidence_score: 0.5 };
  return { agent_id: agentId, ...chosen };
}

export function mockSimulation() {
  return {
    approved: 41,
    soft_alerted: 6,
    blocked: 12,
    total_saved: 143.5,
    false_positive_rate: 0.08,
    recommendation: "Current policy catches outsized requests while keeping the false-positive rate low. Tighten only whitelist entries that still produce blocked trades.",
    total_transactions_replayed: 59,
  };
}
