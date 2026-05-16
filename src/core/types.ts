export type OperatorMode = "active" | "review" | "paused";
export type TrustZone = "green" | "yellow" | "red";
export type LeaseOutcome = "approve" | "resize" | "block" | "human_approval";
export type LeaseAction = "buy" | "sell" | "rebalance";
export type LeaseStatus = "active" | "revoked" | "expired";

export interface OperatorState {
  operatorName: string;
  mode: OperatorMode;
  lastCommand: "initialize" | "resume" | "review" | "pause";
  note?: string;
  updatedAt: string;
}

export interface TreasurySnapshot {
  timestamp: string;
  network: string;
  chainId: number;
  baseAsset: string;
  totalUsd: number;
  liquidUsd: number;
  capitalAtRiskUsd: number;
  balances: Array<{
    symbol: string;
    amount: number;
    usdValue: number;
  }>;
}

export interface LeasePolicy {
  leaseId: string;
  issuedAt: string;
  expiresAt: string;
  status: LeaseStatus;
  ownerLabel: string;
  consumerName: string;
  walletAddress?: string;
  baseAsset: string;
  allowedAssets: string[];
  allowedProtocols: string[];
  allowedActions: LeaseAction[];
  counterpartyAllowlist: string[];
  perTxUsd: number;
  dailyBudgetUsd: number;
  trustRequirements: {
    reasonRequired: boolean;
    proofRequired: boolean;
    operatorCanPause: boolean;
    degradedRequiresReview: boolean;
  };
  notes: string[];
}

export interface LeaseRequest {
  requestId: string;
  createdAt: string;
  sourceProject: string;
  consumerName: string;
  leaseId: string;
  action: LeaseAction;
  assetPair: string;
  fromToken: string;
  toToken: string;
  venueHint: string;
  counterparty: string;
  notionalUsd: number;
  reason: string;
}

export interface LeaseCheck {
  id:
    | "operator_mode"
    | "lease_status"
    | "lease_expiry"
    | "wallet_scope"
    | "reason_required"
    | "action_allowed"
    | "asset_allowed"
    | "protocol_allowed"
    | "counterparty_allowed"
    | "per_tx_limit"
    | "daily_budget"
    | "passport_session"
    | "session_expiry"
    | "session_budget"
    | "route_available"
    | "price_impact"
    | "token_safety";
  label: string;
  ok: boolean;
  note: string;
}

export interface LeaseUsageWindow {
  startedAt: string;
  spent24hUsd: number;
  remainingDailyUsd: number;
  receiptCount24h: number;
}

export interface LeaseDecision {
  outcome: LeaseOutcome;
  trustZone: TrustZone;
  finalNotionalUsd: number;
  policyHits: string[];
  rationale: string;
}

export interface ExecutionIntent {
  network: "kite-mainnet" | "kite-testnet" | "kite-custom";
  chainId: number;
  venueHint: string;
  assetPair: string;
  action: LeaseAction;
  notionalUsd: number;
}

export interface ExecutionResult {
  status: "ready" | "simulated" | "broadcasted" | "failed" | "blocked";
  network: ExecutionIntent["network"];
  chainId: number;
  txHash?: string;
  explorerUrl?: string;
  note: string;
}

export interface LeaseReceipt {
  generatedAt: string;
  leaseId: string;
  requestId: string;
  consumerName: string;
  status: "recorded" | "broadcasted" | "failed" | "blocked";
  spentUsd: number;
  txHash?: string;
  explorerUrl?: string;
  note: string;
}

export interface ProofPacket {
  generatedAt: string;
  product: string;
  operator: OperatorState;
  passportSession?: {
    sessionId: string;
    payerAddress: string;
    agentName?: string;
    agentId?: string;
    network: "kite-mainnet" | "kite-testnet";
    createdAt?: string;
    expiresAt: string;
    dailyBudgetUsd: number;
    spentUsd: number;
    remainingBudgetUsd: number;
    portalUrl?: string;
    notes?: string;
  };
  lease: LeasePolicy;
  treasury: TreasurySnapshot;
  request: LeaseRequest;
  paymentAttempt?: {
    serviceUrl: string;
    serviceHost: string;
    resource: string;
    httpMethod: string;
    httpStatus: number;
    merchantName?: string;
    network?: string;
    asset?: string;
    maxAmountRequired?: string;
    xPaymentPresent: boolean;
    challengeSummary?: string;
    responsePreview?: string;
  };
  checks: LeaseCheck[];
  usage: LeaseUsageWindow;
  decision: LeaseDecision;
  execution: ExecutionResult;
  receipt: LeaseReceipt;
}
