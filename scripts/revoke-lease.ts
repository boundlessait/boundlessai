import path from "node:path";
import { readRuntimeEnvFromFiles } from "../src/config/env.js";
import { readActiveLease, writeActiveLease } from "../src/lease/store.js";
import { LeasePolicy } from "../src/core/types.js";
import { canWriteController, controllerConfigFromRuntimeEnv, setLeaseStatusOnchain } from "../lib/trust-lease-controller.js";

const env = readRuntimeEnvFromFiles();
const note = process.argv.slice(2).join(" ").trim() || undefined;
const baseDir = path.resolve(env.LEASE_DATA_DIR);
const lease = readActiveLease(baseDir);

if (!lease) {
  console.error("no_active_lease");
  process.exit(1);
}

const revoked: LeasePolicy = {
  ...lease,
  status: "revoked",
  notes: note ? [...lease.notes, note] : lease.notes
};
const filePath = writeActiveLease(baseDir, revoked);
const controllerConfig = controllerConfigFromRuntimeEnv(env);
console.log(`lease=${revoked.leaseId}`);
console.log(`status=${revoked.status}`);
console.log(`path=${filePath}`);

if (canWriteController(controllerConfig)) {
  const txHash = await setLeaseStatusOnchain(controllerConfig, revoked.leaseId, "revoked", note);
  console.log(`controller_tx=${txHash}`);
  console.log(`controller=${controllerConfig.controllerAddress}`);
}
