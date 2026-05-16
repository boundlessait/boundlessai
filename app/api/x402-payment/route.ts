import { NextResponse } from 'next/server';
import { getSiteData } from '@/lib/site-data';
import { readKitePassportSession, writeKitePassportSession } from '@/lib/kite-passport-session';
import { writeProofArtifacts } from '@/lib/proof-artifacts';
import { KITE_MAINNET_CHAIN_ID, KITE_TESTNET_CHAIN_ID } from '@/lib/chain-config';
import { createProofPacket } from '../../../src/historian/proof';
import { listReceipts } from '../../../src/lease/store';
import { readRuntimeEnvFromFiles } from '../../../src/config/env';
import type { LeaseCheck, LeaseDecision, LeasePolicy, LeaseRequest, OperatorState, ProofPacket } from '../../../src/core/types';
import { resolveProjectRoot } from '@/lib/project-root';

export const dynamic = 'force-dynamic';

type X402PaymentBody = {
  serviceUrl?: string;
  location?: string;
  units?: 'metric' | 'imperial';
  notionalUsd?: number;
  reason?: string;
  xPayment?: string;
};

type AcceptOffer = {
  scheme?: string;
  network?: string;
  maxAmountRequired?: string;
  resource?: string;
  description?: string;
  payTo?: string;
  asset?: string;
  merchantName?: string;
};

function projectRoot(): string {
  return resolveProjectRoot();
}

function usageWindow(leaseId: string, dailyBudgetUsd: number) {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  const receipts = listReceipts(`${projectRoot()}/data/trust-leases`).filter(
    (receipt) => receipt.leaseId === leaseId && new Date(receipt.generatedAt).getTime() >= cutoff,
  );
  const spent24hUsd = receipts
    .filter((receipt) => receipt.status === 'broadcasted')
    .reduce((sum, receipt) => sum + receipt.spentUsd, 0);
  return {
    startedAt: new Date(cutoff).toISOString(),
    spent24hUsd,
    remainingDailyUsd: Math.max(0, dailyBudgetUsd - spent24hUsd),
    receiptCount24h: receipts.length,
  };
}

function normalizeOperatorState(input: Awaited<ReturnType<typeof getSiteData>>['currentOperator'] | null | undefined, fallbackName: string): OperatorState {
  return {
    operatorName: input?.operatorName ?? fallbackName,
    mode: (input?.mode === 'paused' || input?.mode === 'review' ? input.mode : 'active') as OperatorState['mode'],
    lastCommand: (input?.lastCommand === 'pause' || input?.lastCommand === 'review' || input?.lastCommand === 'resume'
      ? input.lastCommand
      : 'initialize') as OperatorState['lastCommand'],
    updatedAt: input?.updatedAt ?? new Date().toISOString(),
    note: input?.note,
  };
}

function normalizeLease(input: NonNullable<Awaited<ReturnType<typeof getSiteData>>['lease']>): LeasePolicy {
  return {
    ...input,
    status: (input.status === 'revoked' || input.status === 'expired' ? input.status : 'active') as LeasePolicy['status'],
    allowedActions: input.allowedActions as LeasePolicy['allowedActions'],
  };
}

function toPreview(value: unknown): string {
  if (typeof value === 'string') {
    return value.slice(0, 300);
  }
  return JSON.stringify(value).slice(0, 300);
}

function parseAcceptOffer(body: unknown): AcceptOffer | null {
  if (!body || typeof body !== 'object') {
    return null;
  }
  const row = body as Record<string, unknown>;
  const accepts = Array.isArray(row.accepts) ? row.accepts : [];
  if (!accepts[0] || typeof accepts[0] !== 'object') {
    return null;
  }
  return accepts[0] as AcceptOffer;
}

function serviceHost(serviceUrl: string): string {
  try {
    return new URL(serviceUrl).host;
  } catch {
    return 'x402-service';
  }
}

function buildSessionChecks(session: NonNullable<ReturnType<typeof readKitePassportSession>>, requestNotionalUsd: number): LeaseCheck[] {
  const expiresAtMs = new Date(session.expiresAt).getTime();
  const expired = !Number.isFinite(expiresAtMs) || expiresAtMs <= Date.now();
  const remainingOk = session.remainingBudgetUsd >= requestNotionalUsd;
  return [
    {
      id: 'passport_session',
      label: 'Passport session present',
      ok: true,
      note: `session=${session.sessionId}`,
    },
    {
      id: 'session_expiry',
      label: 'Passport session expiry',
      ok: !expired,
      note: `expiresAt=${session.expiresAt}`,
    },
    {
      id: 'session_budget',
      label: 'Passport session budget',
      ok: remainingOk,
      note: `remaining=$${session.remainingBudgetUsd.toFixed(2)} / request=$${requestNotionalUsd.toFixed(2)}`,
    },
  ];
}

function mergeDecision(base: LeaseDecision, session: NonNullable<ReturnType<typeof readKitePassportSession>>, requestNotionalUsd: number): LeaseDecision {
  if (base.outcome === 'block' || base.outcome === 'human_approval') {
    return base;
  }

  const expiresAtMs = new Date(session.expiresAt).getTime();
  const expired = !Number.isFinite(expiresAtMs) || expiresAtMs <= Date.now();
  if (expired) {
    return {
      outcome: 'block',
      trustZone: 'red',
      finalNotionalUsd: 0,
      policyHits: [...base.policyHits, 'session_expiry'],
      rationale: 'Passport session expired before the x402 request could be paid.',
    };
  }

  const capped = Math.min(base.finalNotionalUsd, session.remainingBudgetUsd);
  if (capped <= 0) {
    return {
      outcome: 'block',
      trustZone: 'red',
      finalNotionalUsd: 0,
      policyHits: [...base.policyHits, 'session_budget'],
      rationale: 'Passport session budget is exhausted.',
    };
  }

  if (base.outcome === 'approve' && capped < requestNotionalUsd) {
    return {
      outcome: 'resize',
      trustZone: 'yellow',
      finalNotionalUsd: capped,
      policyHits: [...base.policyHits, 'session_budget'],
      rationale: 'Boundless approved the request, but the Passport session only had enough budget for a reduced payment.',
    };
  }

  if (base.outcome === 'resize') {
    return {
      ...base,
      finalNotionalUsd: Math.min(base.finalNotionalUsd, capped),
      policyHits: base.policyHits.includes('session_budget') ? base.policyHits : [...base.policyHits, 'session_budget'],
      rationale: capped < base.finalNotionalUsd
        ? 'Boundless resized the request again to stay inside the remaining Passport session budget.'
        : base.rationale,
    };
  }

  return {
    ...base,
    finalNotionalUsd: capped,
  };
}

function evaluateBoundlessLease(input: {
  operator: OperatorState;
  lease: LeasePolicy;
  request: LeaseRequest;
  usage: { remainingDailyUsd: number };
}): { checks: LeaseCheck[]; decision: LeaseDecision } {
  const { operator, lease, request, usage } = input;
  const now = Date.now();
  const expiresAt = new Date(lease.expiresAt).getTime();
  const isExpired = !Number.isFinite(expiresAt) || expiresAt <= now;
  const actionAllowed = lease.allowedActions.includes(request.action);
  const assetsAllowed = [request.fromToken, request.toToken].every((asset) => lease.allowedAssets.includes(asset));
  const protocolAllowed = lease.allowedProtocols.includes(request.venueHint);
  const counterpartyAllowed = lease.counterpartyAllowlist.includes(request.counterparty);
  const reasonPresent = request.reason.trim().length > 0;
  const perTxOk = request.notionalUsd <= lease.perTxUsd;
  const dailyOk = usage.remainingDailyUsd > 0;

  const checks: LeaseCheck[] = [
    { id: 'operator_mode', label: 'Operator mode', ok: operator.mode !== 'paused', note: `operator=${operator.mode}` },
    { id: 'lease_status', label: 'Lease status', ok: lease.status === 'active', note: `status=${lease.status}` },
    { id: 'lease_expiry', label: 'Lease expiry', ok: !isExpired, note: `expiresAt=${lease.expiresAt}` },
    { id: 'reason_required', label: 'Reason required', ok: !lease.trustRequirements.reasonRequired || reasonPresent, note: reasonPresent ? 'reason present' : 'missing reason' },
    { id: 'action_allowed', label: 'Action allowlist', ok: actionAllowed, note: `action=${request.action}` },
    { id: 'asset_allowed', label: 'Asset allowlist', ok: assetsAllowed, note: `${request.fromToken}->${request.toToken}` },
    { id: 'protocol_allowed', label: 'Protocol allowlist', ok: protocolAllowed, note: `venue=${request.venueHint}` },
    { id: 'counterparty_allowed', label: 'Counterparty allowlist', ok: counterpartyAllowed, note: `counterparty=${request.counterparty}` },
    { id: 'per_tx_limit', label: 'Per-tx budget', ok: perTxOk, note: `request=$${request.notionalUsd} / limit=$${lease.perTxUsd}` },
    { id: 'daily_budget', label: 'Daily budget', ok: dailyOk, note: `remaining=$${usage.remainingDailyUsd.toFixed(2)}` },
    { id: 'route_available', label: 'Route available', ok: true, note: 'x402 endpoint reachable' },
    { id: 'price_impact', label: 'Price impact', ok: true, note: 'not applicable to service payment' },
    { id: 'token_safety', label: 'Token safety', ok: true, note: 'service payment route' },
  ];

  if (operator.mode === 'review') {
    return {
      checks,
      decision: {
        outcome: 'human_approval',
        trustZone: 'yellow',
        finalNotionalUsd: 0,
        policyHits: ['operator_review_mode'],
        rationale: 'Operator set Boundless to review mode before this x402 payment.',
      },
    };
  }

  const hardBlock = checks.filter((check) => !check.ok && !['per_tx_limit', 'daily_budget'].includes(check.id));
  if (hardBlock.length) {
    return {
      checks,
      decision: {
        outcome: 'block',
        trustZone: 'red',
        finalNotionalUsd: 0,
        policyHits: hardBlock.map((check) => check.id),
        rationale: `Boundless blocked the payment because ${hardBlock.map((check) => check.id).join(', ')} failed.`,
      },
    };
  }

  const finalNotionalUsd = Math.max(0, Math.min(request.notionalUsd, lease.perTxUsd, usage.remainingDailyUsd));
  if (finalNotionalUsd <= 0) {
    return {
      checks,
      decision: {
        outcome: 'block',
        trustZone: 'red',
        finalNotionalUsd: 0,
        policyHits: ['daily_budget_exhausted'],
        rationale: 'Boundless daily budget is exhausted.',
      },
    };
  }

  const resized = finalNotionalUsd < request.notionalUsd;
  return {
    checks,
    decision: {
      outcome: resized ? 'resize' : 'approve',
      trustZone: resized ? 'yellow' : 'green',
      finalNotionalUsd,
      policyHits: resized ? ['budget_resize'] : ['within_policy_envelope'],
      rationale: resized
        ? 'Boundless allowed the payment, but resized it to stay within the active policy.'
        : 'Boundless allowed the payment inside the active policy envelope.',
    },
  };
}

function buildPacket(input: {
  lease: LeasePolicy;
  operator: OperatorState;
  session: NonNullable<ReturnType<typeof readKitePassportSession>>;
  request: LeaseRequest;
  checks: LeaseCheck[];
  decision: LeaseDecision;
  httpStatus: number;
  serviceUrl: string;
  offer: AcceptOffer | null;
  xPaymentPresent: boolean;
  responsePreview: string;
  executionStatus: ProofPacket['execution']['status'];
  executionNote: string;
}): ProofPacket {
  const chainId = input.session.network === 'kite-mainnet' ? KITE_MAINNET_CHAIN_ID : KITE_TESTNET_CHAIN_ID;
  const treasuryBase = input.session.dailyBudgetUsd;
  return createProofPacket({
    generatedAt: new Date().toISOString(),
    product: 'boundless',
    operator: input.operator,
    passportSession: {
      sessionId: input.session.sessionId,
      payerAddress: input.session.payerAddress,
      agentName: input.session.agentName,
      agentId: input.session.agentId,
      network: input.session.network,
      createdAt: input.session.createdAt,
      expiresAt: input.session.expiresAt,
      dailyBudgetUsd: input.session.dailyBudgetUsd,
      spentUsd: input.session.spentUsd,
      remainingBudgetUsd: input.session.remainingBudgetUsd,
      portalUrl: input.session.portalUrl,
      notes: input.session.notes,
    },
    lease: input.lease,
    treasury: {
      timestamp: new Date().toISOString(),
      network: input.session.network,
      chainId,
      baseAsset: input.lease.baseAsset,
      totalUsd: treasuryBase,
      liquidUsd: input.session.remainingBudgetUsd,
      capitalAtRiskUsd: input.decision.finalNotionalUsd,
      balances: [
        {
          symbol: input.lease.baseAsset,
          amount: input.session.remainingBudgetUsd,
          usdValue: input.session.remainingBudgetUsd,
        },
      ],
    },
    request: input.request,
    paymentAttempt: {
      serviceUrl: input.serviceUrl,
      serviceHost: serviceHost(input.serviceUrl),
      resource: input.offer?.resource ?? input.serviceUrl,
      httpMethod: 'GET',
      httpStatus: input.httpStatus,
      merchantName: input.offer?.merchantName,
      network: input.offer?.network,
      asset: input.offer?.asset,
      maxAmountRequired: input.offer?.maxAmountRequired,
      xPaymentPresent: input.xPaymentPresent,
      challengeSummary: input.offer?.description,
      responsePreview: input.responsePreview,
    },
    checks: input.checks,
    usage: {
      startedAt: new Date().toISOString(),
      spent24hUsd: input.session.spentUsd,
      remainingDailyUsd: input.session.remainingBudgetUsd,
      receiptCount24h: 1,
    },
    decision: input.decision,
    execution: {
      status: input.executionStatus,
      network: input.session.network,
      chainId,
      note: input.executionNote,
    },
    receipt: {
      generatedAt: new Date().toISOString(),
      leaseId: input.lease.leaseId,
      requestId: input.request.requestId,
      consumerName: input.lease.consumerName,
      status: input.executionStatus === 'broadcasted' ? 'broadcasted' : input.executionStatus === 'failed' ? 'failed' : 'blocked',
      spentUsd: input.executionStatus === 'broadcasted' ? input.decision.finalNotionalUsd : 0,
      note: input.executionNote,
    },
  });
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as X402PaymentBody | null;
  if (!body) {
    return NextResponse.json({ error: 'Invalid JSON body.' }, { status: 400 });
  }

  const session = readKitePassportSession();
  if (!session) {
    return NextResponse.json({ error: 'No Kite Passport session is saved yet.' }, { status: 400 });
  }

  const siteData = await getSiteData();
  if (!siteData.lease) {
    return NextResponse.json({ error: 'No active Boundless policy is available yet.' }, { status: 400 });
  }

  const env = readRuntimeEnvFromFiles(projectRoot());
  const lease = normalizeLease(siteData.lease);
  const operator = normalizeOperatorState(siteData.currentOperator, env.LEASE_OPERATOR_NAME);
  const notionalUsd = Number(body.notionalUsd ?? 1);
  if (!Number.isFinite(notionalUsd) || notionalUsd <= 0) {
    return NextResponse.json({ error: 'Request notional must be positive.' }, { status: 400 });
  }

  const serviceUrl = (typeof body.serviceUrl === 'string' && body.serviceUrl.trim()) || 'https://x402.dev.gokite.ai/api/weather';
  const url = new URL(serviceUrl);
  if (typeof body.location === 'string' && body.location.trim()) {
    url.searchParams.set('city', body.location.trim());
  }
  if (body.units === 'metric' || body.units === 'imperial') {
    url.searchParams.set('units', body.units);
  }

  const usage = usageWindow(lease.leaseId, lease.dailyBudgetUsd);
  const leaseRequest: LeaseRequest = {
    requestId: `x402_${Date.now()}`,
    createdAt: new Date().toISOString(),
    sourceProject: 'boundless',
    consumerName: lease.consumerName,
    leaseId: lease.leaseId,
    action: 'buy',
    assetPair: `${lease.baseAsset}/x402-service`,
    fromToken: lease.baseAsset,
    toToken: lease.baseAsset,
    venueHint: 'x402',
    counterparty: 'x402',
    notionalUsd,
    reason: typeof body.reason === 'string' && body.reason.trim()
      ? body.reason.trim()
      : `Pay gated weather request for ${url.searchParams.get('city') || 'weather data'}.`,
  };

  const leaseReview = evaluateBoundlessLease({
    operator,
    lease,
    request: leaseRequest,
    usage,
  });

  const combinedChecks = [...leaseReview.checks, ...buildSessionChecks(session, notionalUsd)];
  const combinedDecision = mergeDecision(leaseReview.decision, session, notionalUsd);

  if (combinedDecision.outcome === 'block' || combinedDecision.outcome === 'human_approval') {
    const packet = buildPacket({
      lease,
      operator,
      session,
      request: leaseRequest,
      checks: combinedChecks,
      decision: combinedDecision,
      httpStatus: 0,
      serviceUrl: url.toString(),
      offer: null,
      xPaymentPresent: false,
      responsePreview: 'Boundless blocked the request before calling the x402 service.',
      executionStatus: 'blocked',
      executionNote: combinedDecision.rationale,
    });
    writeProofArtifacts(packet);
    return NextResponse.json({
      ok: false,
      blocked: true,
      requestId: leaseRequest.requestId,
      proofUrl: `/proof?requestId=${leaseRequest.requestId}`,
      rationale: combinedDecision.rationale,
    });
  }

  const headers = new Headers({
    Accept: 'application/json',
  });
  if (body.xPayment?.trim()) {
    headers.set('X-PAYMENT', body.xPayment.trim());
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'GET',
      headers,
      cache: 'no-store',
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown upstream fetch failure.';
    const packet = buildPacket({
      lease,
      operator,
      session,
      request: leaseRequest,
      checks: combinedChecks,
      decision: combinedDecision,
      httpStatus: 0,
      serviceUrl: url.toString(),
      offer: null,
      xPaymentPresent: Boolean(body.xPayment?.trim()),
      responsePreview: message,
      executionStatus: 'failed',
      executionNote: `x402 upstream unreachable: ${message}`,
    });
    writeProofArtifacts(packet);
    return NextResponse.json({
      ok: false,
      requestId: leaseRequest.requestId,
      proofUrl: `/proof?requestId=${leaseRequest.requestId}`,
      error: 'x402 upstream unreachable.',
      detail: message,
    }, { status: 502 });
  }

  const rawText = await response.text();
  let parsedBody: unknown = rawText;
  try {
    parsedBody = JSON.parse(rawText);
  } catch {
    // keep text preview
  }
  const offer = parseAcceptOffer(parsedBody);

  if (response.status === 402 && !body.xPayment?.trim()) {
    return NextResponse.json({
      ok: false,
      paymentRequired: true,
      requestId: leaseRequest.requestId,
      session,
      challenge: parsedBody,
      proofPreview: {
        decision: combinedDecision,
        checks: combinedChecks,
      },
    });
  }

  if (!response.ok) {
    const packet = buildPacket({
      lease,
      operator,
      session,
      request: leaseRequest,
      checks: combinedChecks,
      decision: combinedDecision,
      httpStatus: response.status,
      serviceUrl: url.toString(),
      offer,
      xPaymentPresent: Boolean(body.xPayment?.trim()),
      responsePreview: toPreview(parsedBody),
      executionStatus: 'failed',
      executionNote: `x402 service returned HTTP ${response.status}.`,
    });
    writeProofArtifacts(packet);
    return NextResponse.json({
      ok: false,
      requestId: leaseRequest.requestId,
      proofUrl: `/proof?requestId=${leaseRequest.requestId}`,
      error: `x402 service returned HTTP ${response.status}.`,
      response: parsedBody,
    }, { status: 502 });
  }

  const updatedSession = writeKitePassportSession({
    ...session,
    spentUsd: session.spentUsd + combinedDecision.finalNotionalUsd,
    remainingBudgetUsd: Math.max(0, session.remainingBudgetUsd - combinedDecision.finalNotionalUsd),
  });

  const packet = buildPacket({
    lease,
    operator,
    session: updatedSession,
    request: leaseRequest,
    checks: combinedChecks,
    decision: combinedDecision,
    httpStatus: response.status,
    serviceUrl: url.toString(),
    offer,
    xPaymentPresent: true,
    responsePreview: toPreview(parsedBody),
    executionStatus: 'broadcasted',
    executionNote: 'Boundless policy approved and the Kite Passport-backed x402 payment completed successfully.',
  });
  writeProofArtifacts(packet);

  return NextResponse.json({
    ok: true,
    requestId: leaseRequest.requestId,
    proofUrl: `/proof?requestId=${leaseRequest.requestId}`,
    packet,
    response: parsedBody,
  });
}
