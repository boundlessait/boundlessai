import path from "node:path";
import fs from "node:fs";
import { readRuntimeEnvFromFiles } from "../src/config/env.js";
import { summarizeProofPacket } from "../src/historian/proof.js";
import { writeSubmissionSite } from "../src/historian/render-site.js";
import { writeRoundArtifacts } from "../src/runtime/store.js";
import { TrustLeaseAgent } from "../src/runtime/trust-lease-agent.js";
import { anchorReceiptOnchain, buildArtifactUri, canWriteController, controllerConfigFromRuntimeEnv } from "../lib/trust-lease-controller.js";

async function main(): Promise<void> {
  const env = readRuntimeEnvFromFiles();
  const agent = new TrustLeaseAgent(env);
  const { packet, source, candidate, lease } = await agent.runTick();

  const artifacts = writeRoundArtifacts({
    baseDir: path.resolve(env.LEASE_DATA_DIR),
    packet,
    mirrorLatestPaths: [path.resolve("examples/live-proof-latest.json")]
  });
  const index = JSON.parse(fs.readFileSync(artifacts.indexPath, "utf8"));
  const siteOutputs = writeSubmissionSite({ packet, index, baseDir: path.resolve(env.LEASE_DATA_DIR) });
  const controllerConfig = controllerConfigFromRuntimeEnv(env);
  let controllerTx: string | undefined;
  const artifactUri =
    buildArtifactUri(controllerConfig, path.relative(path.resolve(env.LEASE_DATA_DIR), artifacts.roundPath)) ||
    (env.LEASE_PUBLIC_PROOF_URL
      ? `${env.LEASE_PUBLIC_PROOF_URL.replace(/\/$/, "")}?requestId=${encodeURIComponent(packet.request.requestId)}`
      : "");

  if (canWriteController(controllerConfig)) {
    controllerTx = await anchorReceiptOnchain(
      controllerConfig,
      packet,
      artifactUri
    );
  }

  console.log(summarizeProofPacket(packet));
  console.log(`source=${source}`);
  console.log(`lease=${lease.leaseId}`);
  console.log(`candidate=${candidate ? `${candidate.fromToken}->${candidate.toToken}` : "none"}`);
  console.log(`round=${artifacts.roundPath}`);
  console.log(`latest=${artifacts.latestPath}`);
  console.log(`index=${artifacts.indexPath}`);
  console.log(`dashboard=${siteOutputs.proofDashboardPath}`);
  console.log(`submission=${siteOutputs.submissionPath}`);
  if (controllerTx) {
    console.log(`controller_tx=${controllerTx}`);
    console.log(`controller=${controllerConfig.controllerAddress}`);
  }
}

await main();
