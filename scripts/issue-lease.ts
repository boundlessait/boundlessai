import path from "node:path";
import { readRuntimeEnvFromFiles } from "../src/config/env.js";
import { issueLeaseFromEnv } from "../src/lease/policy.js";
import type { LeasePolicy } from "../src/core/types.js";
import { writeActiveLease } from "../src/lease/store.js";
import { getSettlementAccountAddress } from "../src/treasury/xlayer.js";
import { canWriteController, controllerConfigFromRuntimeEnv, issueLeaseOnchain } from "../lib/trust-lease-controller.js";

const env = readRuntimeEnvFromFiles();
const note = process.argv.slice(2).join(" ").trim();
const walletAddress = env.XLAYER_TREASURY_ADDRESS || getSettlementAccountAddress(env);
const baseLease = issueLeaseFromEnv(env, walletAddress);
const lease: LeasePolicy = note ? { ...baseLease, notes: [...baseLease.notes, note] } : baseLease;
const filePath = writeActiveLease(path.resolve(env.LEASE_DATA_DIR), lease);
const controllerConfig = controllerConfigFromRuntimeEnv(env);

console.log(`lease=${lease.leaseId}`);
console.log(`consumer=${lease.consumerName}`);
console.log(`wallet=${lease.walletAddress ?? "unscoped"}`);
console.log(`per_tx_usd=${lease.perTxUsd}`);
console.log(`daily_budget_usd=${lease.dailyBudgetUsd}`);
console.log(`expires_at=${lease.expiresAt}`);
console.log(`path=${filePath}`);

if (canWriteController(controllerConfig)) {
  const txHash = await issueLeaseOnchain(controllerConfig, lease);
  console.log(`controller_tx=${txHash}`);
  console.log(`controller=${controllerConfig.controllerAddress}`);
}
