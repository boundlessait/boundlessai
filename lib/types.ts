export interface ProofPacket {
  generatedAt: string;
  product: string;
  operator: {
    operatorName: string;
    mode: string;
    lastCommand: string;
    updatedAt: string;
    note?: string;
  };
  passportSession?: {
    sessionId: string;
    payerAddress: string;
    agentName?: string;
    agentId?: string;
    network: string;
    createdAt?: string;
    expiresAt: string;
    dailyBudgetUsd: number;
    spentUsd: number;
    remainingBudgetUsd: number;
    portalUrl?: string;
    notes?: string;
  };
  lease: {
    leaseId: string;
    issuedAt: string;
    expiresAt: string;
    status: string;
    ownerLabel: string;
    consumerName: string;
    walletAddress?: string;
    baseAsset: string;
    allowedAssets: string[];
    allowedProtocols: string[];
    allowedActions: string[];
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
  };
  treasury: {
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
  };
  request: {
    requestId: string;
    createdAt: string;
    sourceProject: string;
    consumerName: string;
    leaseId: string;
    action: string;
    assetPair: string;
    fromToken: string;
    toToken: string;
    venueHint: string;
    counterparty: string;
    notionalUsd: number;
    reason: string;
  };
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
  checks: Array<{
    id: string;
    label: string;
    ok: boolean;
    note: string;
  }>;
  usage: {
    startedAt: string;
    spent24hUsd: number;
    remainingDailyUsd: number;
    receiptCount24h: number;
  };
  decision: {
    outcome: string;
    trustZone: string;
    finalNotionalUsd: number;
    policyHits: string[];
    rationale: string;
  };
  execution: {
    status: string;
    network: string;
    chainId: number;
    txHash?: string;
    explorerUrl?: string;
    note: string;
  };
  receipt: {
    generatedAt: string;
    leaseId: string;
    requestId: string;
    consumerName: string;
    status: string;
    spentUsd: number;
    txHash?: string;
    explorerUrl?: string;
    note: string;
  };
}

export interface RoundArtifactIndexEntry {
  generatedAt: string;
  leaseId?: string;
  requestId: string;
  outcome: string;
  txHash?: string;
  summary: string;
  relativePath?: string;
}
