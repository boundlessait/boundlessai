import fs from "node:fs";
import path from "node:path";
import { ProofPacket } from "../core/types.js";
import { summarizeProofPacket } from "../historian/proof.js";

export interface RoundArtifactIndexEntry {
  generatedAt: string;
  leaseId: string;
  requestId: string;
  outcome: string;
  txHash?: string;
  summary: string;
  relativePath: string;
}

function ensureDir(dirPath: string): void {
  fs.mkdirSync(dirPath, { recursive: true });
}

function readIndex(indexPath: string): RoundArtifactIndexEntry[] {
  if (!fs.existsSync(indexPath)) {
    return [];
  }

  return JSON.parse(fs.readFileSync(indexPath, "utf8")) as RoundArtifactIndexEntry[];
}

export function writeRoundArtifacts(input: {
  baseDir: string;
  packet: ProofPacket;
  mirrorLatestPaths?: string[];
}): {
  roundPath: string;
  latestPath: string;
  indexPath: string;
} {
  const roundsDir = path.resolve(input.baseDir, "rounds");
  ensureDir(roundsDir);

  const safeTimestamp = input.packet.generatedAt.replace(/[:.]/g, "-");
  const fileName = `${safeTimestamp}-${input.packet.request.requestId}.json`;
  const roundPath = path.resolve(roundsDir, fileName);
  const latestPath = path.resolve(input.baseDir, "live-proof-latest.json");
  const indexPath = path.resolve(input.baseDir, "index.json");

  fs.writeFileSync(roundPath, `${JSON.stringify(input.packet, null, 2)}\n`);
  fs.writeFileSync(latestPath, `${JSON.stringify(input.packet, null, 2)}\n`);

  const nextEntry: RoundArtifactIndexEntry = {
    generatedAt: input.packet.generatedAt,
    leaseId: input.packet.lease.leaseId,
    requestId: input.packet.request.requestId,
    outcome: input.packet.decision.outcome,
    txHash: input.packet.execution.txHash,
    summary: summarizeProofPacket(input.packet),
    relativePath: path.relative(input.baseDir, roundPath)
  };

  const nextIndex = [nextEntry, ...readIndex(indexPath)].slice(0, 50);
  fs.writeFileSync(indexPath, `${JSON.stringify(nextIndex, null, 2)}\n`);

  for (const mirrorPath of input.mirrorLatestPaths ?? []) {
    ensureDir(path.dirname(mirrorPath));
    fs.writeFileSync(mirrorPath, `${JSON.stringify(input.packet, null, 2)}\n`);
  }

  return { roundPath, latestPath, indexPath };
}
