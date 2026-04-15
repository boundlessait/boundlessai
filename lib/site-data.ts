import fs from 'node:fs';
import path from 'node:path';
import type { ProofPacket, RoundArtifactIndexEntry } from './types';
import { canWriteController, readControllerConfig, readOnchainActiveLease, readOnchainLatestReceipt, readOnchainOperator, readRecentOnchainReceipts, type OnchainReceiptEvent } from './trust-lease-controller';
import { loadLocalEnvFiles, parseCsvList, readRuntimeEnv } from '../src/config/env';

export type SiteData = {
  packet: ProofPacket | null;
  lease: ProofPacket['lease'] | null;
  currentOperator: ProofPacket['operator'] | null;
  rounds: RoundArtifactIndexEntry[];
  latestSuccessRound: RoundArtifactIndexEntry | null;
  latestBlockedRound: RoundArtifactIndexEntry | null;
  latestSuccessPacket: ProofPacket | null;
  latestBlockedPacket: ProofPacket | null;
  controller: {
    address: string | null;
    source: 'local' | 'onchain';
    latestRequestId: string | null;
    latestTxHash: string | null;
    actionsEnabled: boolean;
    runRoundEnabled: boolean;
    note: string | null;
  };
};

type SiteDataOptions = {
  requestId?: string | null;
};

function getDataPath(...segments: string[]): string {
  return path.join(process.cwd(), 'data', 'trust-leases', ...segments);
}

function readJsonIfExists<T>(filePath: string): T | null {
  if (!fs.existsSync(filePath)) {
    return null;
  }

  return JSON.parse(fs.readFileSync(filePath, 'utf-8')) as T;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function hasString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isUsablePacket(value: unknown): value is ProofPacket {
  if (!isObject(value)) return false;
  if (!hasString(value.generatedAt) || !hasString(value.product)) return false;

  const lease = value.lease;
  const request = value.request;
  const decision = value.decision;
  const execution = value.execution;
  const receipt = value.receipt;
  const treasury = value.treasury;
  const operator = value.operator;

  return (
    isObject(lease) &&
    hasString(lease.leaseId) &&
    hasString(lease.consumerName) &&
    hasString(lease.status) &&
    hasString(lease.expiresAt) &&
    isObject(request) &&
    hasString(request.requestId) &&
    hasString(request.consumerName) &&
    hasString(request.fromToken) &&
    hasString(request.toToken) &&
    isObject(decision) &&
    hasString(decision.outcome) &&
    hasString(decision.trustZone) &&
    hasString(decision.rationale) &&
    isObject(execution) &&
    hasString(execution.status) &&
    hasString(execution.note) &&
    isObject(receipt) &&
    hasString(receipt.status) &&
    isObject(treasury) &&
    typeof treasury.chainId === 'number' &&
    isObject(operator) &&
    hasString(operator.mode)
  );
}

function readRoundPacket(relativePath?: string): ProofPacket | null {
  if (!relativePath) return null;
  const packet = readJsonIfExists<unknown>(getDataPath(relativePath));
  return isUsablePacket(packet) ? packet : null;
}

function packetTime(packet: ProofPacket | null): number {
  if (!packet) return -1;
  const time = new Date(packet.generatedAt).getTime();
  return Number.isFinite(time) ? time : -1;
}

function roundTime(round: RoundArtifactIndexEntry | null | undefined): number {
  if (!round) return -1;
  const time = new Date(round.generatedAt).getTime();
  return Number.isFinite(time) ? time : -1;
}

function sortRounds(rounds: RoundArtifactIndexEntry[]): RoundArtifactIndexEntry[] {
  return [...rounds].sort((left, right) => roundTime(right) - roundTime(left));
}

function dedupeRounds(rounds: RoundArtifactIndexEntry[]): RoundArtifactIndexEntry[] {
  const seen = new Set<string>();
  return sortRounds(
    rounds.filter((round) => {
      const key = round.requestId || `${round.generatedAt}-${round.txHash ?? 'none'}`;
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    }),
  );
}

function resolvePrimaryPacket(rounds: RoundArtifactIndexEntry[]): ProofPacket | null {
  const latestFilePacket = readJsonIfExists<unknown>(getDataPath('live-proof-latest.json'));
  const primaryFromFile = isUsablePacket(latestFilePacket) ? latestFilePacket : null;
  const primaryFromIndex = sortRounds(rounds)
    .map((round) => readRoundPacket(round.relativePath))
    .find(Boolean) ?? null;

  return packetTime(primaryFromIndex) > packetTime(primaryFromFile) ? primaryFromIndex : primaryFromFile;
}

function resolveRequestedPacket(rounds: RoundArtifactIndexEntry[], requestId?: string | null): ProofPacket | null {
  if (!requestId) {
    return null;
  }

  const requestedRound = rounds.find((round) => round.requestId === requestId);
  return readRoundPacket(requestedRound?.relativePath);
}

function buildSyntheticRoundFromReceipt(receipt: OnchainReceiptEvent): RoundArtifactIndexEntry {
  return {
    generatedAt: receipt.timestamp ?? new Date().toISOString(),
    leaseId: receipt.leaseId,
    requestId: receipt.requestId,
    outcome: receipt.outcome,
    txHash: receipt.txHashHex,
    summary: `onchain receipt | lease=${receipt.leaseId} | outcome=${receipt.outcome} | execution=${receipt.executionStatus} | tx=${receipt.txHashHex ?? 'none'}`,
    relativePath: '',
  };
}

function buildSyntheticPacketFromOnchain(input: {
  env: ReturnType<typeof readRuntimeEnv>;
  lease: ProofPacket['lease'] | null;
  operator: ProofPacket['operator'] | null;
  receipt: OnchainReceiptEvent | null;
}): ProofPacket | null {
  if (!input.lease || !input.operator || !input.receipt) {
    return null;
  }

  const txHash = input.receipt.txHashHex;
  return {
    generatedAt: input.receipt.timestamp ?? new Date().toISOString(),
    product: input.env.LEASE_NAME,
    operator: input.operator,
    lease: {
      ...input.lease,
      allowedAssets: input.lease.allowedAssets.length > 0 ? input.lease.allowedAssets : parseCsvList(input.env.LEASE_ALLOWED_ASSETS),
      allowedProtocols: input.lease.allowedProtocols.length > 0 ? input.lease.allowedProtocols : parseCsvList(input.env.LEASE_ALLOWED_PROTOCOLS),
      allowedActions: input.lease.allowedActions.length > 0 ? input.lease.allowedActions : parseCsvList(input.env.LEASE_ALLOWED_ACTIONS) as ProofPacket['lease']['allowedActions'],
      counterpartyAllowlist: input.lease.counterpartyAllowlist.length > 0 ? input.lease.counterpartyAllowlist : parseCsvList(input.env.LEASE_ALLOWED_COUNTERPARTIES),
      notes: input.lease.notes.length > 0 ? input.lease.notes : [input.env.LEASE_NOTES],
    },
    treasury: {
      timestamp: input.receipt.timestamp ?? new Date().toISOString(),
      network: input.env.XLAYER_CHAIN_ID === 196 ? 'xlayer-mainnet' : 'xlayer-custom',
      chainId: input.env.XLAYER_CHAIN_ID,
      baseAsset: input.lease.baseAsset,
      totalUsd: input.lease.dailyBudgetUsd,
      liquidUsd: Math.max(input.lease.dailyBudgetUsd - input.receipt.spentUsd, 0),
      capitalAtRiskUsd: input.receipt.spentUsd,
      balances: [],
    },
    request: {
      requestId: input.receipt.requestId,
      createdAt: input.receipt.timestamp ?? new Date().toISOString(),
      sourceProject: input.lease.consumerName,
      consumerName: input.lease.consumerName,
      leaseId: input.lease.leaseId,
      action: 'rebalance',
      assetPair: `${input.lease.baseAsset}/managed`,
      fromToken: input.lease.baseAsset,
      toToken: txHash ? 'executed' : 'blocked',
      venueHint: 'controller-anchored',
      counterparty: 'controller-anchored',
      notionalUsd: input.receipt.spentUsd,
      reason: 'Recovered from controller-backed receipt anchor when no local artifact was available.',
    },
    checks: [
      {
        id: 'operator_mode',
        label: 'Controller-backed proof',
        ok: true,
        note: 'Recovered from X Layer controller state and receipt anchors.',
      },
    ],
    usage: {
      startedAt: input.receipt.timestamp ?? new Date().toISOString(),
      spent24hUsd: input.receipt.spentUsd,
      remainingDailyUsd: Math.max(input.lease.dailyBudgetUsd - input.receipt.spentUsd, 0),
      receiptCount24h: 1,
    },
    decision: {
      outcome: input.receipt.outcome,
      trustZone: input.receipt.outcome === 'approve' ? 'green' : input.receipt.outcome === 'resize' ? 'yellow' : 'red',
      finalNotionalUsd: input.receipt.spentUsd,
      policyHits: ['controller_anchor'],
      rationale: txHash
        ? 'Recovered from a controller-anchored execution receipt on X Layer.'
        : 'Recovered from a controller-anchored blocked or simulated receipt on X Layer.',
    },
    execution: {
      status: input.receipt.executionStatus,
      network: input.env.XLAYER_CHAIN_ID === 196 ? 'xlayer-mainnet' : 'xlayer-custom',
      chainId: input.env.XLAYER_CHAIN_ID,
      txHash,
      explorerUrl: txHash ? `${input.env.XLAYER_EXPLORER_BASE_URL.replace(/\/+$/, '')}/tx/${txHash}` : undefined,
      note: txHash
        ? 'Execution reconstructed from X Layer controller receipt anchor.'
        : 'Execution state reconstructed from X Layer controller receipt anchor.',
    },
    receipt: {
      generatedAt: input.receipt.timestamp ?? new Date().toISOString(),
      leaseId: input.lease.leaseId,
      requestId: input.receipt.requestId,
      consumerName: input.lease.consumerName,
      status: input.receipt.executionStatus === 'broadcasted' ? 'broadcasted' : input.receipt.executionStatus === 'failed' ? 'failed' : 'blocked',
      spentUsd: input.receipt.spentUsd,
      txHash,
      explorerUrl: txHash ? `${input.env.XLAYER_EXPLORER_BASE_URL.replace(/\/+$/, '')}/tx/${txHash}` : undefined,
      note: 'Recovered from controller anchor.',
    },
  };
}

function commandForOperatorMode(mode: string): ProofPacket['operator']['lastCommand'] {
  switch (mode) {
    case 'active':
      return 'resume';
    case 'review':
      return 'review';
    case 'paused':
      return 'pause';
    default:
      return 'initialize';
  }
}

function buildLeaseFromOnchain(snapshot: NonNullable<Awaited<ReturnType<typeof readOnchainActiveLease>>>): ProofPacket['lease'] {
  return {
    leaseId: snapshot.leaseId,
    issuedAt: snapshot.issuedAt,
    expiresAt: snapshot.expiresAt,
    status: snapshot.status,
    ownerLabel: 'onchain-controller',
    consumerName: snapshot.consumerName,
    walletAddress: snapshot.wallet,
    baseAsset: snapshot.baseAsset,
    allowedAssets: [],
    allowedProtocols: [],
    allowedActions: [],
    counterpartyAllowlist: [],
    perTxUsd: snapshot.perTxUsd,
    dailyBudgetUsd: snapshot.dailyBudgetUsd,
    trustRequirements: {
      reasonRequired: true,
      proofRequired: true,
      operatorCanPause: true,
      degradedRequiresReview: false,
    },
    notes: [],
  };
}

function buildSyntheticRound(receipt: NonNullable<Awaited<ReturnType<typeof readOnchainLatestReceipt>>>): RoundArtifactIndexEntry {
  return {
    generatedAt: receipt.timestamp ?? new Date().toISOString(),
    leaseId: receipt.leaseId,
    requestId: receipt.requestId,
    outcome: receipt.outcome,
    txHash: receipt.txHash !== '0x0000000000000000000000000000000000000000000000000000000000000000' ? receipt.txHash : undefined,
    summary: `onchain receipt | consumer=${receipt.consumerName} | outcome=${receipt.outcome} | execution=${receipt.executionStatus}`,
    relativePath: '',
  };
}

function clonePacket(packet: ProofPacket | null): ProofPacket | null {
  return packet ? JSON.parse(JSON.stringify(packet)) as ProofPacket : null;
}

export async function getSiteData(options: SiteDataOptions = {}): Promise<SiteData> {
  const rounds = sortRounds(readJsonIfExists<RoundArtifactIndexEntry[]>(getDataPath('index.json')) ?? []);
  const hostedRuntime = Boolean(process.env.VERCEL || process.env.VERCEL_ENV);
  const loadedEnv = hostedRuntime ? process.env : loadLocalEnvFiles(process.cwd(), process.env);
  const runtimeEnv = readRuntimeEnv(loadedEnv);
  const controllerConfig = readControllerConfig(loadedEnv);
  const controllerWritable = canWriteController(controllerConfig);
  let onchainLease: Awaited<ReturnType<typeof readOnchainActiveLease>> = null;
  let onchainOperator: Awaited<ReturnType<typeof readOnchainOperator>> = null;
  let onchainReceipt: Awaited<ReturnType<typeof readOnchainLatestReceipt>> = null;
  let onchainReceipts: OnchainReceiptEvent[] = [];
  let controllerReadError: string | null = null;

  if (controllerConfig.controllerAddress) {
    try {
      [onchainLease, onchainOperator, onchainReceipt, onchainReceipts] = await Promise.all([
        readOnchainActiveLease(controllerConfig),
        readOnchainOperator(controllerConfig),
        readOnchainLatestReceipt(controllerConfig),
        readRecentOnchainReceipts(controllerConfig, { limit: 12 }),
      ]);
    } catch (error) {
      controllerReadError = error instanceof Error ? error.message : 'Unknown controller read error.';
      console.error('[trust-leases] controller read fallback', controllerReadError);
    }
  }
  const mergedRounds = dedupeRounds([...rounds, ...onchainReceipts.map(buildSyntheticRoundFromReceipt)]);
  const requestedPacket = clonePacket(resolveRequestedPacket(mergedRounds, options.requestId));
  let packet = requestedPacket ?? clonePacket(resolvePrimaryPacket(mergedRounds));
  const activeLease = readJsonIfExists<ProofPacket['lease']>(getDataPath('leases', 'active-lease.json'));
  const localOperator = readJsonIfExists<ProofPacket['operator']>(getDataPath('operator-state.json')) ?? packet?.operator ?? null;
  let currentOperator = localOperator;
  if (onchainOperator) {
    currentOperator = {
      operatorName: onchainOperator.operatorName,
      mode: onchainOperator.mode === 'none' ? localOperator?.mode ?? 'active' : onchainOperator.mode,
      lastCommand: commandForOperatorMode(onchainOperator.mode),
      updatedAt: onchainOperator.updatedAt ?? localOperator?.updatedAt ?? new Date().toISOString(),
      note: onchainOperator.noteHash !== '0x0000000000000000000000000000000000000000000000000000000000000000' ? onchainOperator.noteHash : localOperator?.note,
    };
  }

  let lease = activeLease ?? packet?.lease ?? null;
  if (onchainLease) {
    lease = {
      ...(lease ?? buildLeaseFromOnchain(onchainLease)),
      leaseId: onchainLease.leaseId,
      issuedAt: onchainLease.issuedAt,
      expiresAt: onchainLease.expiresAt,
      status: onchainLease.status,
      consumerName: onchainLease.consumerName,
      walletAddress: onchainLease.wallet,
      baseAsset: onchainLease.baseAsset,
      perTxUsd: onchainLease.perTxUsd,
      dailyBudgetUsd: onchainLease.dailyBudgetUsd,
    };
  }

  if (packet && lease && packet.lease.leaseId === lease.leaseId) {
    packet.lease = { ...packet.lease, ...lease };
    if (onchainLease) {
      packet.usage.spent24hUsd = onchainLease.spentTodayUsd;
      packet.usage.remainingDailyUsd = onchainLease.remainingDailyUsd;
    }
    if (currentOperator) {
      packet.operator = currentOperator;
    }
  }

  if (packet && onchainReceipt && packet.request.requestId === onchainReceipt.requestId) {
    packet.decision.outcome = onchainReceipt.outcome === 'none' ? packet.decision.outcome : onchainReceipt.outcome;
    packet.execution.status = onchainReceipt.executionStatus === 'none' ? packet.execution.status : onchainReceipt.executionStatus;
    if (onchainReceipt.txHash !== '0x0000000000000000000000000000000000000000000000000000000000000000') {
      packet.execution.txHash = onchainReceipt.txHash;
      packet.receipt.txHash = onchainReceipt.txHash;
    }
    packet.receipt.spentUsd = onchainReceipt.spentUsd;
  }

  let latestSuccessRound = mergedRounds.find((round) => Boolean(round.txHash)) ?? null;
  let latestBlockedRound = mergedRounds.find((round) => round.outcome === 'block') ?? null;
  if (onchainReceipt) {
    const syntheticRound = buildSyntheticRound(onchainReceipt);
    if (!latestSuccessRound && syntheticRound.txHash) {
      latestSuccessRound = syntheticRound;
    }
    if (!latestBlockedRound && syntheticRound.outcome === 'block') {
      latestBlockedRound = syntheticRound;
    }
  }
  const latestSuccessPacket =
    readRoundPacket(latestSuccessRound?.relativePath) ??
    buildSyntheticPacketFromOnchain({
      env: runtimeEnv,
      lease,
      operator: currentOperator,
      receipt: onchainReceipts.find((item) => item.requestId === latestSuccessRound?.requestId) ?? null,
    });
  const latestBlockedPacket =
    readRoundPacket(latestBlockedRound?.relativePath) ??
    buildSyntheticPacketFromOnchain({
      env: runtimeEnv,
      lease,
      operator: currentOperator,
      receipt: onchainReceipts.find((item) => item.requestId === latestBlockedRound?.requestId) ?? null,
    });

  if (!requestedPacket && options.requestId) {
    packet = buildSyntheticPacketFromOnchain({
      env: runtimeEnv,
      lease,
      operator: currentOperator,
      receipt: onchainReceipts.find((item) => item.requestId === options.requestId) ?? null,
    }) ?? packet;
  }

  if (!packet) {
    packet = buildSyntheticPacketFromOnchain({
      env: runtimeEnv,
      lease,
      operator: currentOperator,
      receipt: onchainReceipts[0] ?? null,
    });
  }

  return {
    packet,
    lease,
    currentOperator,
    rounds: mergedRounds,
    latestSuccessRound,
    latestBlockedRound,
    latestSuccessPacket,
    latestBlockedPacket,
    controller: {
      address: controllerConfig.controllerAddress ?? null,
      source: controllerConfig.controllerAddress ? 'onchain' : 'local',
      latestRequestId: onchainReceipt?.requestId ?? null,
      latestTxHash: onchainReceipt?.txHash && onchainReceipt.txHash !== '0x0000000000000000000000000000000000000000000000000000000000000000'
        ? onchainReceipt.txHash
        : null,
      actionsEnabled: hostedRuntime ? controllerWritable : true,
      runRoundEnabled: !hostedRuntime,
      note: hostedRuntime
        ? controllerReadError
          ? `Controller reads temporarily unavailable. Falling back to bundled proof data. ${controllerReadError}`
          : controllerWritable
            ? 'Hosted deployment can issue, revoke, and change operator posture directly on X Layer. Live round execution still requires a writable runner.'
            : 'Hosted deployment is read-only. Control actions require a configured X Layer controller writer or a writable runner.'
        : controllerReadError
          ? `Controller read fallback: ${controllerReadError}`
          : null,
    },
  };
}

export function writeCanonicalLatestIfNeeded(packet: ProofPacket): void {
  if (process.env.VERCEL || process.env.VERCEL_ENV) {
    return;
  }
  const latestPath = getDataPath('live-proof-latest.json');
  fs.writeFileSync(latestPath, `${JSON.stringify(packet, null, 2)}\n`);
}
