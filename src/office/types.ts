export interface PortfolioAsset {
  symbol: string;
  amount: number;
  usdValue: number;
  tokenAddress?: string;
}

export interface PortfolioOverview {
  walletAddress?: string;
  totalValueUsd: number;
  assets: PortfolioAsset[];
  raw?: unknown;
}

export interface AllocationDrift {
  symbol: string;
  currentPct: number;
  targetPct: number;
  driftPct: number;
  usdGap: number;
}

export interface TradeCandidate {
  fromToken: string;
  toToken: string;
  fromTokenAddress?: string;
  toTokenAddress?: string;
  fromTokenDecimals: number;
  toTokenDecimals: number;
  fromTokenPriceUsd: number;
  notionalUsd: number;
  action: "buy" | "sell" | "rebalance";
  reason: string;
}

export interface SwapRouteSummary {
  ok: boolean;
  route: string;
  priceImpactPct: number;
  toAmount: number;
  note: string;
  raw?: unknown;
}

export interface SwapExecutionSummary extends SwapRouteSummary {
  status: "simulated" | "broadcasted" | "failed";
  txHash?: string;
  orderId?: string;
}
