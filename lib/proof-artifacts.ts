import fs from 'node:fs';
import path from 'node:path';
import type { ProofPacket } from '../src/core/types';
import { resolveProjectRoot } from '@/lib/project-root';

type RoundArtifactIndexEntry = {
  generatedAt: string;
  leaseId: string;
  requestId: string;
  outcome: string;
  txHash?: string;
  summary: string;
  relativePath: string;
};

function baseDir(): string {
  return path.join(resolveProjectRoot(), 'data', 'trust-leases');
}

function ensureDir(dirPath: string) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function readIndex(indexPath: string): RoundArtifactIndexEntry[] {
  if (!fs.existsSync(indexPath)) {
    return [];
  }
  return JSON.parse(fs.readFileSync(indexPath, 'utf8')) as RoundArtifactIndexEntry[];
}

function summarizePacket(packet: ProofPacket): string {
  return [
    `product=${packet.product}`,
    `operator=${packet.operator.mode}`,
    `lease=${packet.lease.leaseId}`,
    `consumer=${packet.lease.consumerName}`,
    `outcome=${packet.decision.outcome}`,
    `zone=${packet.decision.trustZone}`,
    `notional=${packet.decision.finalNotionalUsd}`,
    `tx=${packet.execution.txHash ?? 'none'}`,
  ].join(' | ');
}

export function writeProofArtifacts(packet: ProofPacket) {
  const dir = baseDir();
  const roundsDir = path.join(dir, 'rounds');
  ensureDir(roundsDir);
  const safeTimestamp = packet.generatedAt.replace(/[:.]/g, '-');
  const fileName = `${safeTimestamp}-${packet.request.requestId}.json`;
  const roundPath = path.join(roundsDir, fileName);
  const latestPath = path.join(dir, 'live-proof-latest.json');
  const indexPath = path.join(dir, 'index.json');

  fs.writeFileSync(roundPath, `${JSON.stringify(packet, null, 2)}\n`);
  fs.writeFileSync(latestPath, `${JSON.stringify(packet, null, 2)}\n`);
  ensureDir(path.join(resolveProjectRoot(), 'examples'));
  fs.writeFileSync(path.join(resolveProjectRoot(), 'examples', 'live-proof-latest.json'), `${JSON.stringify(packet, null, 2)}\n`);

  const nextEntry: RoundArtifactIndexEntry = {
    generatedAt: packet.generatedAt,
    leaseId: packet.lease.leaseId,
    requestId: packet.request.requestId,
    outcome: packet.decision.outcome,
    txHash: packet.execution.txHash,
    summary: summarizePacket(packet),
    relativePath: path.relative(dir, roundPath),
  };
  const nextIndex = [nextEntry, ...readIndex(indexPath)].slice(0, 50);
  fs.writeFileSync(indexPath, `${JSON.stringify(nextIndex, null, 2)}\n`);

  return { roundPath, latestPath, indexPath };
}
