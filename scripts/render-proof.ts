import fs from "node:fs";
import path from "node:path";
import { readRuntimeEnvFromFiles } from "../src/config/env.js";
import { ProofPacket } from "../src/core/types.js";
import { writeSubmissionSite } from "../src/historian/render-site.js";

const env = readRuntimeEnvFromFiles();
const baseDir = path.resolve(env.LEASE_DATA_DIR);
const latestPath = path.resolve(baseDir, "live-proof-latest.json");
const indexPath = path.resolve(baseDir, "index.json");

if (!fs.existsSync(latestPath) || !fs.existsSync(indexPath)) {
  console.error("[render-proof] missing live-proof-latest.json or index.json");
  process.exit(1);
}

const packet = JSON.parse(fs.readFileSync(latestPath, "utf8")) as ProofPacket;
const index = JSON.parse(fs.readFileSync(indexPath, "utf8"));
const outputs = writeSubmissionSite({ packet, index, baseDir });

console.log(`dashboard=${outputs.proofDashboardPath}`);
console.log(`submission=${outputs.submissionPath}`);
console.log(`index=${outputs.indexPath}`);
