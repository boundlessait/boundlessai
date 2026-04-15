import fs from "node:fs";
import path from "node:path";
import { readRuntimeEnvFromFiles } from "../src/config/env.js";
import { ProofPacket } from "../src/core/types.js";
import { summarizeProofPacket } from "../src/historian/proof.js";

const env = readRuntimeEnvFromFiles();
const latestPath = path.resolve(env.LEASE_DATA_DIR, "live-proof-latest.json");

if (!fs.existsSync(latestPath)) {
  console.error(`[status-latest] missing ${latestPath}`);
  process.exit(1);
}

const packet = JSON.parse(fs.readFileSync(latestPath, "utf8")) as ProofPacket;
console.log(`[status-latest] ${summarizeProofPacket(packet)}`);
console.log(`[status-latest] generatedAt=${packet.generatedAt}`);
console.log(`[status-latest] wallet=${packet.lease.walletAddress ?? "unscoped"}`);
console.log(`[status-latest] request=${packet.request.assetPair} requested=$${packet.request.notionalUsd} final=$${packet.decision.finalNotionalUsd}`);
console.log(`[status-latest] usage spent24h=$${packet.usage.spent24hUsd.toFixed(2)} remaining=$${packet.usage.remainingDailyUsd.toFixed(2)} receipts=${packet.usage.receiptCount24h}`);
console.log(`[status-latest] rationale=${packet.decision.rationale}`);
console.log(`[status-latest] explorer=${packet.execution.explorerUrl ?? "none"}`);
