import fs from 'node:fs';
import path from 'node:path';
import { RuntimeEnv } from '../config/env.js';
import { issueLeaseFromEnv } from '../lease/policy.js';
import { readActiveLease, writeActiveLease } from '../lease/store.js';
import { applyOperatorCommand } from './operator-state.js';
import { getSettlementAccountAddress } from '../treasury/xlayer.js';
import { TrustLeaseAgent } from './trust-lease-agent.js';
import { writeRoundArtifacts } from './store.js';
import { writeSubmissionSite } from '../historian/render-site.js';
import type { LeasePolicy, ProofPacket } from '../core/types.js';

function baseDir(env: RuntimeEnv): string {
  return path.resolve(env.LEASE_DATA_DIR);
}

function appendLeaseNote(lease: LeasePolicy, note?: string): LeasePolicy {
  if (!note?.trim()) return lease;
  return {
    ...lease,
    notes: [...lease.notes, note.trim()],
  };
}

export function issueLease(env: RuntimeEnv, note?: string) {
  const walletAddress = env.XLAYER_TREASURY_ADDRESS || getSettlementAccountAddress(env);
  const lease = appendLeaseNote(issueLeaseFromEnv(env, walletAddress), note);
  const filePath = writeActiveLease(baseDir(env), lease);
  return { lease, filePath };
}

export function revokeLease(env: RuntimeEnv, note?: string) {
  const dir = baseDir(env);
  const existing = readActiveLease(dir);
  if (!existing) {
    throw new Error('No active lease to revoke.');
  }

  const revoked: LeasePolicy = {
    ...existing,
    status: 'revoked',
    notes: note?.trim() ? [...existing.notes, note.trim()] : existing.notes,
  };
  const filePath = writeActiveLease(dir, revoked);
  return { lease: revoked, filePath };
}

export function changeOperatorMode(env: RuntimeEnv, action: 'pause' | 'resume' | 'review', note?: string) {
  const commandMap = {
    pause: { mode: 'paused', lastCommand: 'pause' },
    resume: { mode: 'active', lastCommand: 'resume' },
    review: { mode: 'review', lastCommand: 'review' },
  } as const;

  const mapped = commandMap[action];
  return applyOperatorCommand({
    baseDir: baseDir(env),
    operatorName: env.LEASE_OPERATOR_NAME,
    mode: mapped.mode,
    lastCommand: mapped.lastCommand,
    note,
  });
}

export async function runRound(env: RuntimeEnv) {
  const agent = new TrustLeaseAgent(env);
  const result = await agent.runTick();
  const artifacts = writeRoundArtifacts({
    baseDir: baseDir(env),
    packet: result.packet,
    mirrorLatestPaths: [path.resolve('examples/live-proof-latest.json')],
  });
  const index = JSON.parse(fs.readFileSync(artifacts.indexPath, 'utf8'));
  const siteOutputs = writeSubmissionSite({ packet: result.packet, index, baseDir: baseDir(env) });

  return { ...result, artifacts, siteOutputs };
}

export function renderCurrentSite(env: RuntimeEnv, packet: ProofPacket) {
  const indexPath = path.resolve(baseDir(env), 'index.json');
  const index = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
  return writeSubmissionSite({ packet, index, baseDir: baseDir(env) });
}
