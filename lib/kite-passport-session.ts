import fs from 'node:fs';
import path from 'node:path';
import { isAddress } from 'viem';
import { resolveProjectRoot } from '@/lib/project-root';

export type KitePassportSessionRecord = {
  sessionId: string;
  payerAddress: string;
  agentName?: string;
  agentId?: string;
  network: 'kite-testnet' | 'kite-mainnet';
  createdAt?: string;
  expiresAt: string;
  dailyBudgetUsd: number;
  spentUsd: number;
  remainingBudgetUsd: number;
  portalUrl?: string;
  notes?: string;
};

function sessionFilePath(): string {
  return path.join(resolveProjectRoot(), 'data', 'trust-leases', 'kite-passport-session.json');
}

function isPositiveNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

function normalizeNumber(value: unknown): number {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0;
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

export function isKitePassportSessionRecord(value: unknown): value is KitePassportSessionRecord {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const row = value as Record<string, unknown>;
  return (
    typeof row.sessionId === 'string' &&
    row.sessionId.trim().length > 0 &&
    typeof row.payerAddress === 'string' &&
    isAddress(row.payerAddress) &&
    (row.network === 'kite-testnet' || row.network === 'kite-mainnet') &&
    typeof row.expiresAt === 'string' &&
    row.expiresAt.trim().length > 0 &&
    isPositiveNumber(row.dailyBudgetUsd) &&
    isPositiveNumber(row.spentUsd) &&
    isPositiveNumber(row.remainingBudgetUsd)
  );
}

export function readKitePassportSession(): KitePassportSessionRecord | null {
  const filePath = sessionFilePath();
  if (!fs.existsSync(filePath)) {
    return null;
  }
  try {
    const parsed = JSON.parse(fs.readFileSync(filePath, 'utf8')) as unknown;
    return isKitePassportSessionRecord(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function writeKitePassportSession(input: Omit<KitePassportSessionRecord, 'remainingBudgetUsd'> & { remainingBudgetUsd?: number }): KitePassportSessionRecord {
  const normalized: KitePassportSessionRecord = {
    sessionId: input.sessionId.trim(),
    payerAddress: input.payerAddress,
    agentName: input.agentName?.trim() || undefined,
    agentId: input.agentId?.trim() || undefined,
    network: input.network,
    createdAt: input.createdAt?.trim() || undefined,
    expiresAt: input.expiresAt,
    dailyBudgetUsd: normalizeNumber(input.dailyBudgetUsd),
    spentUsd: normalizeNumber(input.spentUsd),
    remainingBudgetUsd: Math.max(
      0,
      normalizeNumber(input.remainingBudgetUsd) || normalizeNumber(input.dailyBudgetUsd) - normalizeNumber(input.spentUsd),
    ),
    portalUrl: input.portalUrl?.trim() || undefined,
    notes: input.notes?.trim() || undefined,
  };

  const filePath = sessionFilePath();
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(normalized, null, 2)}\n`);
  return normalized;
}
