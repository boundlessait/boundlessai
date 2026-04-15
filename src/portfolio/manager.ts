import { OnchainOsCliClient, OnchainOsResponse } from "../onchainos/cli.js";
import {
  AllocationDrift,
  PortfolioAsset,
  PortfolioOverview,
  SwapExecutionSummary,
  SwapRouteSummary,
  TradeCandidate
} from "../office/types.js";
import { TreasurySnapshot } from "../core/types.js";

const TOKEN_REGISTRY: Record<string, { address?: string; decimals: number; priceUsd?: number }> = {
  USDT0: { decimals: 6 },
  USDT: { address: "0x779ded0c9e1022225f8e0630b35a9b54be713736", decimals: 6, priceUsd: 1 },
  USDC: { address: "0x74b7f16337b8972027f6196a17a631ac6de26d22", decimals: 6, priceUsd: 1 },
  OKB: { address: "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", decimals: 18 },
  WOKB: { address: "0xe538905cf8410324e03a5a23c1c177a474d59b2b", decimals: 18 },
  ETH: { decimals: 18 },
  WETH: { decimals: 18 },
  WBTC: { decimals: 8 }
};

function firstArray(value: unknown): unknown[] | undefined {
  if (Array.isArray(value)) {
    return value;
  }
  return undefined;
}

function numberFromUnknown(value: unknown): number {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : 0;
  }
  if (typeof value === "string") {
    const parsed = Number(value.replace(/,/g, ""));
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function stringFromUnknown(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

export class PortfolioManager {
  constructor(
    private readonly client: OnchainOsCliClient,
    private readonly walletAddress: string | undefined,
    private readonly chainId: number,
    private readonly baseAssetSymbol: string,
    private readonly baseAssetAddress?: string,
    private readonly minTradeUsd = 10
  ) {}

  private normalizeSymbol(symbol: string, tokenAddress?: string): string {
    const upper = symbol.toUpperCase();
    const normalizedBase = this.baseAssetSymbol.toUpperCase();
    const normalizedAddress = tokenAddress?.toLowerCase();
    const baseAddress = this.baseAssetAddress?.toLowerCase();

    if (normalizedAddress && baseAddress && normalizedAddress === baseAddress) {
      return normalizedBase;
    }

    if (["USD₮0", "USDT0"].includes(upper)) {
      return normalizedBase;
    }

    if (upper === "USDT" && normalizedBase === "USDT0") {
      return normalizedBase;
    }

    return upper;
  }

  private resolveKnownToken(symbol: string): { address?: string; decimals: number; priceUsd?: number } {
    const upper = this.normalizeSymbol(symbol);
    if (upper === this.baseAssetSymbol.toUpperCase()) {
      return {
        address: this.baseAssetAddress,
        decimals: 6,
        priceUsd: 1
      };
    }

    return TOKEN_REGISTRY[upper] ?? { decimals: 18 };
  }

  private parseWalletAssets(response: OnchainOsResponse): PortfolioAsset[] {
    const root = response.data as Record<string, unknown> | undefined;
    const detailAssets = firstArray(root?.details)
      ?.flatMap((item) => firstArray((item as Record<string, unknown>).tokenAssets) ?? []);
    const tokenAssets =
      detailAssets ??
      firstArray(root?.assets) ??
      firstArray(root?.balances) ??
      firstArray(root?.tokenAssets) ??
      firstArray(response.raw);

    const normalized = (tokenAssets ?? [])
      .map((item) => item as Record<string, unknown>)
      .map((item) => {
        const tokenAddress =
          stringFromUnknown(item.tokenContractAddress) ??
          stringFromUnknown(item.contractAddress) ??
          stringFromUnknown(item.address);

        return {
          symbol: this.normalizeSymbol(
            stringFromUnknown(item.tokenSymbol) ??
              stringFromUnknown(item.symbol) ??
              stringFromUnknown(item.assetSymbol) ??
              "UNKNOWN",
            tokenAddress
          ),
        amount:
          numberFromUnknown(item.balance) ||
          numberFromUnknown(item.amount) ||
          numberFromUnknown(item.tokenAmount),
        usdValue:
          numberFromUnknown(item.valueUsd) ||
          numberFromUnknown(item.usdValue) ||
          numberFromUnknown(item.balanceUsd) ||
          numberFromUnknown(item.usd),
          tokenAddress
        };
      })
      .filter((asset) => asset.amount > 0 || asset.usdValue > 0);

    const deduped = new Map<string, PortfolioAsset>();
    for (const asset of normalized) {
      const key = `${asset.symbol}:${asset.tokenAddress ?? ""}`;
      if (!deduped.has(key)) {
        deduped.set(key, asset);
      }
    }

    return [...deduped.values()];
  }

  async getBalances(): Promise<PortfolioOverview> {
    const response = this.client.walletBalance(this.chainId);
    if (!response.ok) {
      return {
        walletAddress: this.walletAddress,
        totalValueUsd: 0,
        assets: [],
        raw: response
      };
    }

    const root = response.data as Record<string, unknown> | undefined;
    const assets = this.parseWalletAssets(response);
    const totalValueUsd =
      numberFromUnknown(root?.totalValueUsd) ||
      numberFromUnknown(root?.valueUsd) ||
      assets.reduce((sum, asset) => sum + asset.usdValue, 0);

    return {
      walletAddress:
        this.walletAddress ??
        stringFromUnknown(root?.walletAddress) ??
        stringFromUnknown(root?.address),
      totalValueUsd,
      assets,
      raw: response.raw
    };
  }

  async getPositions(): Promise<unknown[]> {
    if (!this.walletAddress) {
      return [];
    }

    const response = this.client.defiPositions(this.walletAddress, this.chainId);
    if (!response.ok) {
      return [];
    }

    const root = response.data as Record<string, unknown> | undefined;
    return (
      firstArray(root?.details) ??
      firstArray(root?.positions) ??
      firstArray(response.raw) ??
      []
    );
  }

  toTreasurySnapshot(overview: PortfolioOverview): TreasurySnapshot {
    const liquidUsd = overview.assets.reduce((sum, asset) => sum + asset.usdValue, 0);

    return {
      timestamp: new Date().toISOString(),
      network: this.chainId === 196 ? "xlayer-mainnet" : "xlayer-custom",
      chainId: this.chainId,
      baseAsset: this.baseAssetSymbol,
      totalUsd: overview.totalValueUsd || liquidUsd,
      liquidUsd,
      capitalAtRiskUsd: 0,
      balances: overview.assets.map((asset) => ({
        symbol: asset.symbol,
        amount: asset.amount,
        usdValue: asset.usdValue
      }))
    };
  }

  detectAllocationDrift(overview: PortfolioOverview, targets: Record<string, number>): AllocationDrift[] {
    const total = overview.totalValueUsd || overview.assets.reduce((sum, asset) => sum + asset.usdValue, 0);
    const normalizedTargets = Object.entries(targets).reduce<Record<string, number>>((result, [symbol, targetPct]) => {
      const normalizedSymbol = this.normalizeSymbol(symbol);
      result[normalizedSymbol] = (result[normalizedSymbol] ?? 0) + targetPct;
      return result;
    }, {});

    return Object.entries(normalizedTargets)
      .map(([symbol, targetPct]) => {
        const currentUsd = overview.assets
          .filter((asset) => this.normalizeSymbol(asset.symbol, asset.tokenAddress) === symbol)
          .reduce((sum, asset) => sum + asset.usdValue, 0);
        const currentPct = total > 0 ? (currentUsd / total) * 100 : 0;

        return {
          symbol,
          currentPct,
          targetPct,
          driftPct: currentPct - targetPct,
          usdGap: total * ((targetPct - currentPct) / 100)
        };
      })
      .sort((left, right) => Math.abs(right.usdGap) - Math.abs(left.usdGap));
  }

  buildTradeCandidate(
    overview: PortfolioOverview,
    targets: Record<string, number>
  ): TradeCandidate | null {
    if (overview.totalValueUsd <= 0 || overview.assets.length === 0) {
      return null;
    }

    const minTradeUsd = Math.max(this.minTradeUsd, 1);
    const drift = this.detectAllocationDrift(overview, targets);
    const underweight = drift
      .filter((item) => item.usdGap > minTradeUsd)
      .sort((left, right) => right.usdGap - left.usdGap)[0];
    const overweight = drift
      .filter((item) => item.usdGap < -minTradeUsd)
      .sort((left, right) => left.usdGap - right.usdGap)[0];

    const fallbackSource = overview.assets
      .filter((asset) => asset.usdValue > minTradeUsd)
      .sort((left, right) => right.usdValue - left.usdValue)[0];

    const fromToken = overweight?.symbol ?? fallbackSource?.symbol ?? this.baseAssetSymbol;
    const toToken = underweight?.symbol ?? "OKB";

    if (!fromToken || !toToken || fromToken === toToken) {
      return null;
    }

    const sourceAsset =
      overview.assets.find((asset) => asset.symbol.toUpperCase() === fromToken.toUpperCase()) ?? fallbackSource;
    const notionalUsd = Math.max(
      0,
      Math.min(
        Math.abs(underweight?.usdGap ?? overview.totalValueUsd * 0.1),
        sourceAsset?.usdValue ?? overview.totalValueUsd * 0.25,
        320
      )
    );

    if (notionalUsd < minTradeUsd) {
      return null;
    }

    const fromMeta = this.resolveKnownToken(fromToken);
    const toMeta = this.resolveKnownToken(toToken);
    const fromPriceUsd =
      fromMeta.priceUsd ??
      (sourceAsset && sourceAsset.amount > 0 ? sourceAsset.usdValue / sourceAsset.amount : 1);

    return {
      fromToken,
      toToken,
      fromTokenAddress: fromMeta.address ?? sourceAsset?.tokenAddress,
      toTokenAddress: toMeta.address,
      fromTokenDecimals: fromMeta.decimals,
      toTokenDecimals: toMeta.decimals,
      fromTokenPriceUsd: fromPriceUsd > 0 ? fromPriceUsd : 1,
      notionalUsd,
      action: overweight ? "rebalance" : "buy",
      reason:
        underweight && overweight
          ? `${toToken} is underweight and ${fromToken} is overweight relative to the office target allocation.`
          : `${toToken} is the highest-priority target asset under the current office strategy.`
    };
  }

  async isTokenSafe(symbol: string, tokenAddress?: string): Promise<boolean> {
    if (TOKEN_REGISTRY[symbol.toUpperCase()] || symbol.toUpperCase() === this.baseAssetSymbol.toUpperCase()) {
      return true;
    }
    if (!tokenAddress) {
      return false;
    }

    const response = this.client.tokenScan(tokenAddress, this.chainId);
    if (!response.ok) {
      return false;
    }

    const root = (response.data ?? response.raw) as Record<string, unknown> | undefined;
    const level =
      stringFromUnknown(root?.riskControlLevel) ??
      stringFromUnknown((root?.result as Record<string, unknown> | undefined)?.riskControlLevel) ??
      "";

    return !["3", "high", "danger", "unsafe"].includes(level.toLowerCase());
  }

  private toRawTokenAmount(candidate: TradeCandidate): string {
    const tokenAmount = candidate.notionalUsd / Math.max(candidate.fromTokenPriceUsd, 0.000001);
    return Math.floor(tokenAmount * Math.pow(10, candidate.fromTokenDecimals)).toString();
  }

  private toReadableTokenAmount(candidate: TradeCandidate): string {
    const tokenAmount = candidate.notionalUsd / Math.max(candidate.fromTokenPriceUsd, 0.000001);
    const precision = Math.min(candidate.fromTokenDecimals, 8);
    const fixed = tokenAmount.toFixed(precision);
    return fixed.replace(/(?:\.0+|(\.\d*?)0+)$/, "$1");
  }

  private parseRouteSummary(response: OnchainOsResponse): SwapRouteSummary {
    if (!response.ok) {
      return {
        ok: false,
        route: "none",
        priceImpactPct: 9.99,
        toAmount: 0,
        note: response.error ?? "quote failed",
        raw: response.raw
      };
    }

    const root = response.data as Record<string, unknown> | unknown[] | undefined;
    const quote =
      firstArray(root)?.[0] ??
      firstArray((root as Record<string, unknown> | undefined)?.data)?.[0] ??
      root;
    const item = quote as Record<string, unknown> | undefined;
    const routerList = firstArray(item?.dexRouterList) ?? [];
    const route = routerList
      .map((entry) =>
        stringFromUnknown((entry as Record<string, unknown>).dexName) ??
        stringFromUnknown(((entry as Record<string, unknown>).dexProtocol as Record<string, unknown> | undefined)?.dexName) ??
        "route"
      )
      .join(" -> ");

    return {
      ok: true,
      route: route || "okx-aggregator",
      priceImpactPct:
        numberFromUnknown(item?.priceImpactPercent) ||
        numberFromUnknown(item?.priceImpact) ||
        0,
      toAmount:
        numberFromUnknown(item?.toTokenAmount) ||
        numberFromUnknown(item?.toAmount) ||
        0,
      note: "quote ready",
      raw: response.raw
    };
  }

  async quoteCandidate(candidate: TradeCandidate): Promise<SwapRouteSummary> {
    if (!candidate.fromTokenAddress || !candidate.toTokenAddress) {
      return {
        ok: false,
        route: "none",
        priceImpactPct: 9.99,
        toAmount: 0,
        note: "missing token address"
      };
    }

    const response = this.client.swapQuote({
      fromAddress: candidate.fromTokenAddress,
      toAddress: candidate.toTokenAddress,
      amount: this.toRawTokenAmount(candidate),
      chainId: this.chainId
    });

    return this.parseRouteSummary(response);
  }

  syntheticQuote(candidate: TradeCandidate): SwapRouteSummary {
    return {
      ok: true,
      route: "synthetic-sample-route",
      priceImpactPct: 0.35,
      toAmount: candidate.notionalUsd,
      note: "synthetic quote used because live quote is unavailable"
    };
  }

  async executeCandidate(candidate: TradeCandidate, live: boolean): Promise<SwapExecutionSummary> {
    if (!live) {
      return {
        ...this.syntheticQuote(candidate),
        status: "simulated",
        txHash: undefined
      };
    }

    if (!candidate.fromTokenAddress || !candidate.toTokenAddress) {
      return {
        ok: false,
        route: "none",
        priceImpactPct: 9.99,
        toAmount: 0,
        note: "missing token address",
        status: "failed"
      };
    }

    const quote = await this.quoteCandidate(candidate);
    if (!quote.ok) {
      return {
        ...quote,
        status: "failed"
      };
    }

    const response = this.client.swapExecute({
      fromAddress: candidate.fromTokenAddress,
      toAddress: candidate.toTokenAddress,
      amount: this.toRawTokenAmount(candidate),
      readableAmount: this.toReadableTokenAmount(candidate),
      chainId: this.chainId,
      chainName: this.chainId === 196 ? "xlayer" : String(this.chainId),
      walletAddress: this.walletAddress
    });

    if (!response.ok) {
      return {
        ...quote,
        note: response.error ?? "swap execute failed",
        status: "failed"
      };
    }

    const root = (response.data ?? response.raw) as Record<string, unknown> | undefined;
    const txHash =
      stringFromUnknown(root?.swapTxHash) ??
      stringFromUnknown(root?.tx_hash) ??
      stringFromUnknown(root?.txHash) ??
      stringFromUnknown(root?.orderId) ??
      stringFromUnknown(root?.tx_order_id);

    return {
      ...quote,
      status: "broadcasted",
      txHash,
      orderId: stringFromUnknown(root?.orderId)
    };
  }
}
