import crypto from "node:crypto";
import { parseAllocations, parseCsvList, RuntimeEnv } from "../config/env.js";
import { LeaseCheck, LeaseDecision, LeasePolicy, LeaseRequest, LeaseUsageWindow, OperatorState } from "../core/types.js";

export function issueLeaseFromEnv(env: RuntimeEnv, walletAddress?: string): LeasePolicy {
  const issuedAt = new Date().toISOString();
  const expiresAt = new Date(Date.now() + env.LEASE_EXPIRY_HOURS * 60 * 60 * 1000).toISOString();

  return {
    leaseId: `lease_${crypto.randomUUID()}`,
    issuedAt,
    expiresAt,
    status: "active",
    ownerLabel: env.LEASE_ISSUER_LABEL,
    consumerName: env.LEASE_CONSUMER_NAME,
    walletAddress,
    baseAsset: env.LEASE_DEFAULT_BASE_ASSET,
    allowedAssets: parseCsvList(env.LEASE_ALLOWED_ASSETS),
    allowedProtocols: parseCsvList(env.LEASE_ALLOWED_PROTOCOLS),
    allowedActions: parseCsvList(env.LEASE_ALLOWED_ACTIONS) as LeasePolicy["allowedActions"],
    counterpartyAllowlist: parseCsvList(env.LEASE_ALLOWED_COUNTERPARTIES),
    perTxUsd: env.LEASE_PER_TX_USD,
    dailyBudgetUsd: env.LEASE_DAILY_BUDGET_USD,
    trustRequirements: {
      reasonRequired: env.LEASE_REASON_REQUIRED,
      proofRequired: env.LEASE_REQUIRE_PROOF,
      operatorCanPause: true,
      degradedRequiresReview: env.LEASE_REQUIRE_HEALTHY_ROUTE
    },
    notes: [env.LEASE_NOTES]
  };
}

export function currentTargetAllocations(env: RuntimeEnv): Record<string, number> {
  return parseAllocations(env.LEASE_TARGET_ALLOCATIONS);
}

export function evaluateLeaseRequest(input: {
  operator: OperatorState;
  lease: LeasePolicy;
  request: LeaseRequest;
  usage: LeaseUsageWindow;
  walletAddress?: string;
  routeAvailable: boolean;
  tokenSafe: boolean;
  priceImpactPct: number;
  maxPriceImpactPct: number;
}): { checks: LeaseCheck[]; decision: LeaseDecision } {
  const { operator, lease, request, usage } = input;
  const checks: LeaseCheck[] = [];
  const now = Date.now();
  const expiresAt = new Date(lease.expiresAt).getTime();
  const isExpired = !Number.isFinite(expiresAt) || expiresAt <= now;
  const actionAllowed = lease.allowedActions.includes(request.action);
  const assetsAllowed = [request.fromToken, request.toToken].every((asset) => lease.allowedAssets.includes(asset));
  const protocolAllowed = lease.allowedProtocols.includes(request.venueHint);
  const counterpartyAllowed = lease.counterpartyAllowlist.includes(request.counterparty);
  const reasonPresent = request.reason.trim().length > 0;
  const walletScoped = !lease.walletAddress || !input.walletAddress || lease.walletAddress.toLowerCase() === input.walletAddress.toLowerCase();
  const perTxOk = request.notionalUsd <= lease.perTxUsd;
  const dailyOk = usage.remainingDailyUsd > 0;
  const routeOk = input.routeAvailable;
  const priceOk = input.priceImpactPct <= input.maxPriceImpactPct;
  const tokenSafe = input.tokenSafe;

  checks.push({ id: "operator_mode", label: "Operator mode", ok: operator.mode !== "paused", note: `operator=${operator.mode}` });
  checks.push({ id: "lease_status", label: "Lease status", ok: lease.status === "active", note: `status=${lease.status}` });
  checks.push({ id: "lease_expiry", label: "Lease expiry", ok: !isExpired, note: `expiresAt=${lease.expiresAt}` });
  checks.push({ id: "wallet_scope", label: "Wallet scope", ok: walletScoped, note: lease.walletAddress ? `wallet=${lease.walletAddress}` : "unscoped" });
  checks.push({ id: "reason_required", label: "Reason required", ok: !lease.trustRequirements.reasonRequired || reasonPresent, note: reasonPresent ? "reason present" : "missing reason" });
  checks.push({ id: "action_allowed", label: "Action allowlist", ok: actionAllowed, note: `action=${request.action}` });
  checks.push({ id: "asset_allowed", label: "Asset allowlist", ok: assetsAllowed, note: `${request.fromToken}->${request.toToken}` });
  checks.push({ id: "protocol_allowed", label: "Protocol allowlist", ok: protocolAllowed, note: `venue=${request.venueHint}` });
  checks.push({ id: "counterparty_allowed", label: "Counterparty allowlist", ok: counterpartyAllowed, note: `counterparty=${request.counterparty}` });
  checks.push({ id: "per_tx_limit", label: "Per-tx budget", ok: perTxOk, note: `request=$${request.notionalUsd} / limit=$${lease.perTxUsd}` });
  checks.push({ id: "daily_budget", label: "Daily budget", ok: dailyOk, note: `remaining=$${usage.remainingDailyUsd.toFixed(2)}` });
  checks.push({ id: "route_available", label: "Route available", ok: routeOk, note: routeOk ? "route ready" : "quote failed" });
  checks.push({ id: "price_impact", label: "Price impact", ok: priceOk, note: `impact=${input.priceImpactPct.toFixed(2)}% / max=${input.maxPriceImpactPct}%` });
  checks.push({ id: "token_safety", label: "Token safety", ok: tokenSafe, note: tokenSafe ? "token scan passed" : "token failed scan" });

  if (operator.mode === "review") {
    return {
      checks,
      decision: {
        outcome: "human_approval",
        trustZone: "yellow",
        finalNotionalUsd: 0,
        policyHits: ["operator_review_mode"],
        rationale: "Operator set the lease runtime to manual review mode."
      }
    };
  }

  const hardBlock = checks.filter((check) => !check.ok && !["per_tx_limit", "daily_budget", "price_impact"].includes(check.id));
  if (hardBlock.length) {
    return {
      checks,
      decision: {
        outcome: "block",
        trustZone: "red",
        finalNotionalUsd: 0,
        policyHits: hardBlock.map((check) => check.id),
        rationale: `Lease blocked the request because ${hardBlock.map((check) => check.id).join(", ")} failed.`
      }
    };
  }

  const finalNotionalUsd = Math.max(0, Math.min(request.notionalUsd, lease.perTxUsd, usage.remainingDailyUsd));
  if (finalNotionalUsd <= 0) {
    return {
      checks,
      decision: {
        outcome: "block",
        trustZone: "red",
        finalNotionalUsd: 0,
        policyHits: ["daily_budget_exhausted"],
        rationale: "Lease daily budget is exhausted."
      }
    };
  }

  const resized = finalNotionalUsd < request.notionalUsd || !priceOk;
  return {
    checks,
    decision: {
      outcome: resized ? "resize" : "approve",
      trustZone: resized ? "yellow" : "green",
      finalNotionalUsd,
      policyHits: resized ? ["budget_resize"] : ["within_policy_envelope"],
      rationale: resized
        ? "Lease allowed the request but reduced size to stay inside budget and route quality limits."
        : "Lease allowed the request inside the current authority envelope."
    }
  };
}
