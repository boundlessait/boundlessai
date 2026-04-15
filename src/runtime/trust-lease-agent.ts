import crypto from "node:crypto";
import path from "node:path";
import { parseAllocations, RuntimeEnv } from "../config/env.js";
import { blockedExecutionResult, buildExplorerUrl, createExecutionIntent, simulatedExecutionResult } from "../execution/xlayer.js";
import { createProofPacket } from "../historian/proof.js";
import { LeasePolicy, LeaseReceipt, LeaseRequest, LeaseUsageWindow, ProofPacket } from "../core/types.js";
import { OnchainOsCliClient } from "../onchainos/cli.js";
import { PortfolioManager } from "../portfolio/manager.js";
import { PortfolioOverview, TradeCandidate } from "../office/types.js";
import { evaluateLeaseRequest, issueLeaseFromEnv } from "../lease/policy.js";
import { appendReceipt, listReceipts, readActiveLease, writeActiveLease } from "../lease/store.js";
import { readOperatorState } from "./operator-state.js";
import { buildLiveTreasurySnapshot, buildSampleTreasurySnapshot, getSettlementAccountAddress } from "../treasury/xlayer.js";
import { controllerConfigFromRuntimeEnv, hasControllerAddress, readOnchainActiveLease, readOnchainOperator } from "../../lib/trust-lease-controller.js";

export class TrustLeaseAgent {
  readonly client: OnchainOsCliClient;
  readonly portfolio: PortfolioManager;

  constructor(private readonly env: RuntimeEnv) {
    const walletAddress = env.XLAYER_TREASURY_ADDRESS || getSettlementAccountAddress(env);
    this.client = new OnchainOsCliClient();
    this.portfolio = new PortfolioManager(
      this.client,
      walletAddress,
      env.XLAYER_CHAIN_ID,
      env.LEASE_DEFAULT_BASE_ASSET,
      env.XLAYER_SETTLEMENT_TOKEN_ADDRESS,
      env.LEASE_MIN_TRADE_USD
    );
  }

  private baseDir(): string {
    return path.resolve(this.env.LEASE_DATA_DIR);
  }

  private controllerConfig() {
    return controllerConfigFromRuntimeEnv(this.env);
  }

  private async mergeLeaseFromChain(localLease: LeasePolicy | null, walletAddress?: string): Promise<LeasePolicy | null> {
    const controllerConfig = this.controllerConfig();
    if (!hasControllerAddress(controllerConfig)) {
      return localLease;
    }

    const onchainLease = await readOnchainActiveLease(controllerConfig, this.env.LEASE_CONSUMER_NAME);
    if (!onchainLease) {
      return localLease;
    }

    const base = localLease ?? issueLeaseFromEnv(this.env, onchainLease.wallet || walletAddress);
    return {
      ...base,
      leaseId: onchainLease.leaseId,
      consumerName: onchainLease.consumerName,
      walletAddress: onchainLease.wallet,
      baseAsset: onchainLease.baseAsset,
      issuedAt: onchainLease.issuedAt,
      expiresAt: onchainLease.expiresAt,
      status: onchainLease.status,
      perTxUsd: onchainLease.perTxUsd,
      dailyBudgetUsd: onchainLease.dailyBudgetUsd
    };
  }

  private async resolveOperatorState() {
    const localOperator = readOperatorState(this.baseDir(), this.env.LEASE_OPERATOR_NAME);
    const controllerConfig = this.controllerConfig();
    if (!hasControllerAddress(controllerConfig)) {
      return localOperator;
    }

    const onchainOperator = await readOnchainOperator(controllerConfig, this.env.LEASE_OPERATOR_NAME);
    if (!onchainOperator) {
      return localOperator;
    }

    return {
      ...localOperator,
      operatorName: onchainOperator.operatorName,
      mode: onchainOperator.mode === "none" ? localOperator.mode : onchainOperator.mode,
      updatedAt: onchainOperator.updatedAt ?? localOperator.updatedAt,
      note: onchainOperator.noteHash !== "0x0000000000000000000000000000000000000000000000000000000000000000" ? onchainOperator.noteHash : localOperator.note
    };
  }

  private async resolveOverview(): Promise<{ overview: PortfolioOverview; source: "onchainos" | "xlayer" | "sample" }> {
    if (this.client.isAvailable()) {
      const overview = await this.portfolio.getBalances();
      if (overview.assets.length > 0 || overview.totalValueUsd > 0) {
        return { overview, source: "onchainos" };
      }
    }

    try {
      if (this.env.XLAYER_TREASURY_ADDRESS || getSettlementAccountAddress(this.env)) {
        const treasury = await buildLiveTreasurySnapshot(this.env);
        return {
          overview: {
            walletAddress: this.env.XLAYER_TREASURY_ADDRESS || getSettlementAccountAddress(this.env),
            totalValueUsd: treasury.totalUsd,
            assets: treasury.balances.map((balance) => ({
              symbol: balance.symbol,
              amount: balance.amount,
              usdValue: balance.usdValue
            }))
          },
          source: "xlayer"
        };
      }
    } catch {
      // fall through
    }

    const treasury = buildSampleTreasurySnapshot(this.env);
    return {
      overview: {
        walletAddress: this.env.XLAYER_TREASURY_ADDRESS || getSettlementAccountAddress(this.env),
        totalValueUsd: treasury.totalUsd,
        assets: treasury.balances.map((balance) => ({
          symbol: balance.symbol,
          amount: balance.amount,
          usdValue: balance.usdValue
        }))
      },
      source: "sample"
    };
  }

  private async ensureLease(walletAddress?: string): Promise<LeasePolicy> {
    const baseDir = this.baseDir();
    const existing = readActiveLease(baseDir);
    const mergedExisting = await this.mergeLeaseFromChain(existing, walletAddress);
    if (mergedExisting) {
      writeActiveLease(baseDir, mergedExisting);
      if (mergedExisting.status === "active") {
        const expiresAt = new Date(mergedExisting.expiresAt).getTime();
        if (Number.isFinite(expiresAt) && expiresAt <= Date.now()) {
          const expiredLease: LeasePolicy = {
            ...mergedExisting,
            status: "expired"
          };
          writeActiveLease(baseDir, expiredLease);
          return expiredLease;
        }
      }
      return mergedExisting;
    }

    if (existing) {
      const expiresAt = new Date(existing.expiresAt).getTime();
      if (existing.status === "active" && Number.isFinite(expiresAt) && expiresAt <= Date.now()) {
        const expiredLease: LeasePolicy = {
          ...existing,
          status: "expired"
        };
        writeActiveLease(baseDir, expiredLease);
        return expiredLease;
      }

      return existing;
    }

    const lease = issueLeaseFromEnv(this.env, walletAddress);
    writeActiveLease(baseDir, lease);
    return lease;
  }

  private async usageWindow(leaseId: string): Promise<LeaseUsageWindow> {
    const controllerConfig = this.controllerConfig();
    if (hasControllerAddress(controllerConfig)) {
      const onchainLease = await readOnchainActiveLease(controllerConfig, this.env.LEASE_CONSUMER_NAME);
      if (onchainLease?.leaseId === leaseId) {
        return {
          startedAt: onchainLease.spentWindowStartedAt ?? new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
          spent24hUsd: onchainLease.spentTodayUsd,
          remainingDailyUsd: onchainLease.remainingDailyUsd,
          receiptCount24h: 0
        };
      }
    }

    const cutoff = Date.now() - 24 * 60 * 60 * 1000;
    const receipts = listReceipts(this.baseDir()).filter((receipt) => receipt.leaseId === leaseId && new Date(receipt.generatedAt).getTime() >= cutoff);
    const spent24hUsd = receipts
      .filter((receipt) => receipt.status === "broadcasted")
      .reduce((sum, receipt) => sum + receipt.spentUsd, 0);

    return {
      startedAt: new Date(cutoff).toISOString(),
      spent24hUsd,
      remainingDailyUsd: Math.max(0, this.env.LEASE_DAILY_BUDGET_USD - spent24hUsd),
      receiptCount24h: receipts.length
    };
  }

  private buildRequest(lease: LeasePolicy, candidate: TradeCandidate | null): LeaseRequest {
    if (!candidate) {
      return {
        requestId: `req_${crypto.randomUUID()}`,
        createdAt: new Date().toISOString(),
        sourceProject: this.env.LEASE_CONSUMER_NAME,
        consumerName: lease.consumerName,
        leaseId: lease.leaseId,
        action: "rebalance",
        assetPair: `${this.env.LEASE_DEFAULT_BASE_ASSET}/USDC`,
        fromToken: this.env.LEASE_DEFAULT_BASE_ASSET,
        toToken: "USDC",
        venueHint: "okx-aggregator",
        counterparty: "okx-aggregator",
        notionalUsd: 0,
        reason: "No material allocation drift exceeded the minimum trade threshold for this lease round."
      };
    }

    return {
      requestId: `req_${crypto.randomUUID()}`,
      createdAt: new Date().toISOString(),
      sourceProject: this.env.LEASE_CONSUMER_NAME,
      consumerName: lease.consumerName,
      leaseId: lease.leaseId,
      action: candidate.action,
      assetPair: `${candidate.toToken}/${candidate.fromToken}`,
      fromToken: candidate.fromToken,
      toToken: candidate.toToken,
      venueHint: "okx-aggregator",
      counterparty: "okx-aggregator",
      notionalUsd: Number(candidate.notionalUsd.toFixed(2)),
      reason: candidate.reason
    };
  }

  private async buildExecution(input: {
    packet: ProofPacket;
    candidate: TradeCandidate | null;
    source: "onchainos" | "xlayer" | "sample";
  }) {
    const intent = createExecutionIntent({ request: input.packet.request, chainId: this.env.XLAYER_CHAIN_ID });

    if (input.packet.decision.outcome === "block" || input.packet.decision.outcome === "human_approval") {
      return blockedExecutionResult({ intent, note: input.packet.decision.rationale });
    }

    if (!input.candidate) {
      return simulatedExecutionResult({ intent, note: "No trade candidate met the lease threshold for this round." });
    }

    if (this.env.LEASE_EXECUTION_MODE !== "live" || input.source === "sample") {
      return simulatedExecutionResult({ intent, note: "Lease decision passed, but execution mode is simulate or live treasury is unavailable." });
    }

    const adjustedCandidate: TradeCandidate = {
      ...input.candidate,
      notionalUsd: input.packet.decision.finalNotionalUsd
    };

    const execution = await this.portfolio.executeCandidate(adjustedCandidate, true);
    if (execution.status === "broadcasted") {
      const txHash = execution.txHash ?? execution.orderId;
      return {
        status: "broadcasted" as const,
        network: intent.network,
        chainId: intent.chainId,
        txHash,
        explorerUrl: txHash ? buildExplorerUrl(this.env.XLAYER_EXPLORER_BASE_URL, txHash) : undefined,
        note: `Executed ${adjustedCandidate.fromToken} -> ${adjustedCandidate.toToken} via ${execution.route}.`
      };
    }

    return {
      status: "failed" as const,
      network: intent.network,
      chainId: intent.chainId,
      note: execution.note
    };
  }

  async runTick(): Promise<{ packet: ProofPacket; source: "onchainos" | "xlayer" | "sample"; candidate: TradeCandidate | null; lease: LeasePolicy; }> {
    const baseDir = this.baseDir();
    const operator = await this.resolveOperatorState();
    const { overview, source } = await this.resolveOverview();
    const lease = await this.ensureLease(overview.walletAddress);
    const treasury = this.portfolio.toTreasurySnapshot(overview);
    const candidate = this.portfolio.buildTradeCandidate(overview, parseAllocations(this.env.LEASE_TARGET_ALLOCATIONS));
    const request = this.buildRequest(lease, candidate);
    const usage = await this.usageWindow(lease.leaseId);
    const quote = candidate
      ? source === "onchainos"
        ? await this.portfolio.quoteCandidate(candidate)
        : this.portfolio.syntheticQuote(candidate)
      : { ok: false, route: "none", priceImpactPct: 0, toAmount: 0, note: "no candidate" };
    const tokenSafe = candidate ? await this.portfolio.isTokenSafe(candidate.toToken, candidate.toTokenAddress) : true;
    const review = evaluateLeaseRequest({
      operator,
      lease,
      request,
      usage,
      walletAddress: overview.walletAddress,
      routeAvailable: candidate ? quote.ok : false,
      tokenSafe,
      priceImpactPct: quote.priceImpactPct,
      maxPriceImpactPct: this.env.LEASE_MAX_PRICE_IMPACT_PCT
    });

    const packet = createProofPacket({
      generatedAt: new Date().toISOString(),
      product: this.env.LEASE_NAME,
      operator,
      lease,
      treasury,
      request,
      checks: review.checks,
      usage,
      decision: candidate
        ? review.decision
        : {
            outcome: "block",
            trustZone: "yellow",
            finalNotionalUsd: 0,
            policyHits: ["no_trade_candidate"],
            rationale: "No material allocation drift produced a leaseable request in this round."
          },
      execution: {
        status: "ready",
        network: this.env.XLAYER_CHAIN_ID === 196 ? "xlayer-mainnet" : "xlayer-custom",
        chainId: this.env.XLAYER_CHAIN_ID,
        note: "pending execution"
      },
      receipt: {
        generatedAt: new Date().toISOString(),
        leaseId: lease.leaseId,
        requestId: request.requestId,
        consumerName: lease.consumerName,
        status: "recorded",
        spentUsd: 0,
        note: "receipt pending execution"
      }
    });

    const execution = await this.buildExecution({ packet, candidate, source });
    packet.execution = execution;
    const receipt: LeaseReceipt = {
      generatedAt: packet.generatedAt,
      leaseId: lease.leaseId,
      requestId: request.requestId,
      consumerName: lease.consumerName,
      status:
        packet.decision.outcome === "block" || packet.decision.outcome === "human_approval"
          ? "blocked"
          : execution.status === "broadcasted"
            ? "broadcasted"
            : execution.status === "failed"
              ? "failed"
              : "recorded",
      spentUsd: execution.status === "broadcasted" ? packet.decision.finalNotionalUsd : 0,
      txHash: execution.txHash,
      explorerUrl: execution.explorerUrl,
      note: execution.note
    };
    packet.receipt = receipt;
    appendReceipt(baseDir, receipt);
    packet.usage = this.usageWindow(lease.leaseId);

    return { packet, source, candidate, lease };
  }
}
