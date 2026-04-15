import { execFileSync } from 'node:child_process';
import { NextResponse } from 'next/server';
import crypto from 'node:crypto';
import { isAddress, type Address } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { getSiteData, writeCanonicalLatestIfNeeded } from '@/lib/site-data';
import { canWriteController, issueLeaseOnchain, readControllerConfig, readOnchainActiveLease, setLeaseStatusOnchain, setOperatorModeOnchain } from '@/lib/trust-lease-controller';
import { readBoundlessVaultConfig, setLeaseContextOnchain, setMemberPolicyOnchain } from '@/lib/boundless-vault';
import { parseCsvList, readRuntimeEnv } from '../../../src/config/env';

export const dynamic = 'force-dynamic';

type ControlAction =
  | 'issue-lease'
  | 'revoke-lease'
  | 'pause'
  | 'review'
  | 'resume'
  | 'run-round'
  | 'refresh-proof'
  | 'set-member-policy';

type LeaseOverridesInput = {
  baseAsset?: string;
  perTxUsd?: number;
  dailyBudgetUsd?: number;
  allowedAssets?: string[];
  allowedProtocols?: string[];
  expiryHours?: number;
};

type MemberPolicyInput = {
  memberAddress?: string;
  enabled?: boolean;
  perTxUsd?: number;
  dailyBudgetUsd?: number;
};

function isHostedReadonlyRuntime(): boolean {
  return Boolean(process.env.VERCEL || process.env.VERCEL_ENV);
}

function runCommand(args: string[]): string {
  return execFileSync(args[0], args.slice(1), {
    cwd: process.cwd(),
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    env: process.env,
  });
}

function normalizePrivateKey(privateKey?: string): `0x${string}` | undefined {
  if (!privateKey) {
    return undefined;
  }
  return (privateKey.startsWith('0x') ? privateKey : `0x${privateKey}`) as `0x${string}`;
}

function getHostedSettlementAddress(env: ReturnType<typeof readRuntimeEnv>): string | undefined {
  const privateKey = normalizePrivateKey(env.XLAYER_SETTLEMENT_PRIVATE_KEY || env.XLAYER_PRIVATE_KEY);
  return privateKey ? privateKeyToAccount(privateKey).address : undefined;
}

function sanitizeSymbol(symbol: string): string {
  return symbol.trim().toUpperCase().replace(/[^A-Z0-9_]/g, '');
}

function sanitizeProtocol(protocol: string): string {
  return protocol.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '');
}

function sanitizeList(values: string[] | undefined, fallback: string[], normalize: (value: string) => string): string[] {
  if (!values || values.length === 0) {
    return fallback;
  }
  const deduped = Array.from(
    new Set(
      values
        .map((value) => normalize(value))
        .filter((value) => value.length > 0),
    ),
  );
  return deduped.length > 0 ? deduped : fallback;
}

function clampPositiveNumber(value: number | undefined, fallback: number): number {
  if (typeof value !== 'number' || Number.isNaN(value) || !Number.isFinite(value) || value <= 0) {
    return fallback;
  }
  return value;
}

function buildHostedLease(
  env: ReturnType<typeof readRuntimeEnv>,
  walletAddress: string,
  note?: string,
  overrides?: LeaseOverridesInput,
) {
  const baseAsset = sanitizeSymbol(overrides?.baseAsset || env.LEASE_DEFAULT_BASE_ASSET) || env.LEASE_DEFAULT_BASE_ASSET;
  const perTxUsd = clampPositiveNumber(overrides?.perTxUsd, env.LEASE_PER_TX_USD);
  const dailyBudgetUsd = Math.max(
    clampPositiveNumber(overrides?.dailyBudgetUsd, env.LEASE_DAILY_BUDGET_USD),
    perTxUsd,
  );
  const expiryHours = Math.min(
    Math.max(clampPositiveNumber(overrides?.expiryHours, env.LEASE_EXPIRY_HOURS), 1),
    168,
  );
  const allowedAssets = sanitizeList(overrides?.allowedAssets, parseCsvList(env.LEASE_ALLOWED_ASSETS), sanitizeSymbol);
  const allowedProtocols = sanitizeList(overrides?.allowedProtocols, parseCsvList(env.LEASE_ALLOWED_PROTOCOLS), sanitizeProtocol);
  const issuedAt = new Date().toISOString();
  const expiresAt = new Date(Date.now() + expiryHours * 60 * 60 * 1000).toISOString();
  return {
    leaseId: `lease_${crypto.randomUUID()}`,
    issuedAt,
    expiresAt,
    status: 'active',
    ownerLabel: env.LEASE_ISSUER_LABEL,
    consumerName: env.LEASE_CONSUMER_NAME,
    walletAddress,
    baseAsset,
    allowedAssets,
    allowedProtocols,
    allowedActions: parseCsvList(env.LEASE_ALLOWED_ACTIONS),
    counterpartyAllowlist: parseCsvList(env.LEASE_ALLOWED_COUNTERPARTIES),
    perTxUsd,
    dailyBudgetUsd,
    trustRequirements: {
      reasonRequired: env.LEASE_REASON_REQUIRED,
      proofRequired: env.LEASE_REQUIRE_PROOF,
      operatorCanPause: true,
      degradedRequiresReview: env.LEASE_REQUIRE_HEALTHY_ROUTE,
    },
    notes: note ? [env.LEASE_NOTES, note] : [env.LEASE_NOTES],
  };
}

function publicControlError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  if (/nonce too low|nonce provided|tx nonce|next nonce|already been used|nonce has already been used/i.test(message)) {
    return 'X Layer controller nonce moved while writing. The app now retries with the pending nonce; wait a few seconds and click once more if this request was already in flight.';
  }
  if (/insufficient funds|exceeds the balance|fee cap/i.test(message)) {
    return 'The controller wallet needs more OKB for X Layer gas before this action can be written onchain.';
  }
  if (/user rejected|denied transaction/i.test(message)) {
    return 'Wallet signature was rejected.';
  }
  if (/Hosted run-round is not enabled/i.test(message)) {
    return message;
  }
  return message.split('\n')[0]?.slice(0, 320) || 'Control action failed.';
}

async function runHostedControlAction(
  action: ControlAction,
  note?: string,
  requestedWalletAddress?: string,
  leaseOverrides?: LeaseOverridesInput,
  memberPolicy?: MemberPolicyInput,
) {
  const env = readRuntimeEnv(process.env);
  const controllerConfig = readControllerConfig(process.env);

  if (!canWriteController(controllerConfig)) {
    throw new Error('Hosted control requires a configured X Layer controller writer.');
  }

  switch (action) {
    case 'issue-lease': {
      const activeLease = await readOnchainActiveLease(controllerConfig, env.LEASE_CONSUMER_NAME);
      const walletAddress = requestedWalletAddress && isAddress(requestedWalletAddress)
        ? requestedWalletAddress
        : env.XLAYER_TREASURY_ADDRESS || getHostedSettlementAddress(env);
      if (!walletAddress) {
        throw new Error('Missing treasury wallet address for hosted lease issuance.');
      }
      const issuedLease = buildHostedLease(env, walletAddress, note, leaseOverrides);
      const txHash = await issueLeaseOnchain(controllerConfig, issuedLease);
      const vaultConfig = readBoundlessVaultConfig(process.env);
      if (vaultConfig.vaultAddress && vaultConfig.writerPrivateKey) {
        await setLeaseContextOnchain(vaultConfig, {
          leaseId: issuedLease.leaseId,
          consumerName: env.LEASE_CONSUMER_NAME,
          operatorName: env.LEASE_OPERATOR_NAME,
        });
      }
      if (activeLease?.status === 'active') {
        try {
          await setLeaseStatusOnchain(controllerConfig, activeLease.leaseId, 'revoked', 'superseded by new hosted lease');
        } catch (error) {
          console.warn('[trust-leases] old lease revoke failed after replacement', publicControlError(error));
        }
      }
      return `controller_tx=${txHash}`;
    }
    case 'revoke-lease': {
      const activeLease = await readOnchainActiveLease(controllerConfig, env.LEASE_CONSUMER_NAME);
      if (!activeLease) {
        throw new Error('No active onchain lease to revoke.');
      }
      const txHash = await setLeaseStatusOnchain(controllerConfig, activeLease.leaseId, 'revoked', note);
      return `controller_tx=${txHash}`;
    }
    case 'pause':
    case 'review':
    case 'resume': {
      const mode = action === 'pause' ? 'paused' : action === 'review' ? 'review' : 'active';
      const txHash = await setOperatorModeOnchain(controllerConfig, {
        operatorName: env.LEASE_OPERATOR_NAME,
        mode,
        note,
        updatedAt: new Date().toISOString(),
        lastCommand: action === 'resume' ? 'resume' : action,
      });
      return `controller_tx=${txHash}`;
    }
    case 'refresh-proof':
      return 'refreshed=controller-state';
    case 'set-member-policy': {
      const vaultConfig = readBoundlessVaultConfig(process.env);
      if (!vaultConfig.vaultAddress || !vaultConfig.writerPrivateKey) {
        throw new Error('Hosted member policy requires BOUNDLESS_VAULT_ADDRESS and writer key.');
      }
      const member = memberPolicy?.memberAddress;
      if (!member || !isAddress(member)) {
        throw new Error('Set a valid member wallet address.');
      }
      const perTxUsd = Number(memberPolicy?.perTxUsd ?? 0);
      const dailyBudgetUsd = Number(memberPolicy?.dailyBudgetUsd ?? 0);
      const enabled = Boolean(memberPolicy?.enabled ?? true);
      if (enabled && (!Number.isFinite(perTxUsd) || perTxUsd <= 0 || !Number.isFinite(dailyBudgetUsd) || dailyBudgetUsd <= 0)) {
        throw new Error('Member per-tx and daily budgets must be positive.');
      }
      const txHash = await setMemberPolicyOnchain(vaultConfig, {
        member: member as Address,
        enabled,
        perTxUsd,
        dailyBudgetUsd,
      });
      return `vault_tx=${txHash}`;
    }
    case 'run-round':
      throw new Error('Hosted run-round is not enabled yet. Use a writable runner for live or simulated round execution.');
    default:
      throw new Error('Unsupported hosted action.');
  }
}

async function buildSummary() {
  const site = await getSiteData();
  if (site.packet) {
    writeCanonicalLatestIfNeeded(site.packet);
  }

  return {
    leaseId: site.lease?.leaseId ?? null,
    leaseStatus: site.lease?.status ?? null,
    operatorMode: site.currentOperator?.mode ?? site.packet?.operator.mode ?? null,
    latestGeneratedAt: site.packet?.generatedAt ?? null,
    latestOutcome: site.packet?.decision.outcome ?? null,
    latestExecutionStatus: site.packet?.execution.status ?? null,
    latestTxHash: site.packet?.execution.txHash ?? site.latestSuccessRound?.txHash ?? null,
    latestBlockedReason: site.latestBlockedPacket?.decision.rationale ?? null,
    latestSuccessTxHash: site.latestSuccessRound?.txHash ?? null,
    rounds: site.rounds.length,
  };
}

function humanMessage(action: ControlAction, summary: Awaited<ReturnType<typeof buildSummary>>): string {
  switch (action) {
    case 'issue-lease':
      return summary.leaseId ? `Lease issued: ${summary.leaseId}` : 'Lease issued.';
    case 'revoke-lease':
      return summary.leaseId ? `Lease revoked: ${summary.leaseId}` : 'Lease revoked.';
    case 'pause':
      return 'Operator moved to pause mode.';
    case 'review':
      return 'Operator moved to review mode.';
    case 'resume':
      return 'Operator resumed active mode.';
    case 'run-round':
      if (summary.latestOutcome === 'block' && summary.latestBlockedReason) {
        return `Round completed with guardrail block: ${summary.latestBlockedReason}`;
      }
      if (summary.latestSuccessTxHash) {
        return `Governed round complete. Latest success tx: ${summary.latestSuccessTxHash}`;
      }
      return 'Governed round complete.';
    case 'refresh-proof':
      return 'Visible proof refreshed from current artifacts.';
    case 'set-member-policy':
      return 'Member budget policy updated onchain.';
    default:
      return 'Action complete.';
  }
}

export async function GET() {
  return NextResponse.json({ ok: true, summary: await buildSummary() });
}

export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => ({}))) as {
      action?: ControlAction;
      note?: string;
      walletAddress?: string;
      leaseOverrides?: LeaseOverridesInput;
      memberPolicy?: MemberPolicyInput;
    };
    const action = body.action;
    const note = body.note?.trim();
    const walletAddress = body.walletAddress?.trim();
    const leaseOverrides = body.leaseOverrides;
    const memberPolicy = body.memberPolicy;

    if (!action) {
      return NextResponse.json({ ok: false, error: 'Missing action.' }, { status: 400 });
    }

    let output = '';
    const canDirectWriteOnchain = canWriteController(readControllerConfig(process.env));
    const shouldPreferOnchain = canDirectWriteOnchain && action !== 'run-round';

    if (isHostedReadonlyRuntime() || shouldPreferOnchain) {
      output = await runHostedControlAction(action, note, walletAddress, leaseOverrides, memberPolicy);
    } else {
      switch (action) {
        case 'issue-lease':
          output = runCommand(note ? ['npm', 'run', 'lease:issue', '--', note] : ['npm', 'run', 'lease:issue']);
          break;
        case 'revoke-lease':
          output = runCommand(note ? ['npm', 'run', 'lease:revoke', '--', note] : ['npm', 'run', 'lease:revoke']);
          break;
        case 'pause':
        case 'review':
        case 'resume':
          output = runCommand(note ? ['npm', 'run', `operator:${action}`, '--', note] : ['npm', 'run', `operator:${action}`]);
          break;
        case 'run-round':
          output = runCommand(['npm', 'run', 'round:live']);
          break;
        case 'refresh-proof':
          output = 'refreshed=current-artifacts';
          break;
        case 'set-member-policy':
          output = await runHostedControlAction(action, note, walletAddress, leaseOverrides, memberPolicy);
          break;
        default:
          return NextResponse.json({ ok: false, error: 'Unsupported action.' }, { status: 400 });
      }
    }

    const summary = await buildSummary();

    return NextResponse.json({
      ok: true,
      message: humanMessage(action, summary),
      output,
      summary,
    });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: publicControlError(error) },
      { status: 500 }
    );
  }
}
