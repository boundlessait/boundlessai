import path from "node:path";
import { readRuntimeEnvFromFiles } from "../src/config/env.js";
import { applyOperatorCommand, readOperatorState } from "../src/runtime/operator-state.js";
import { canWriteController, controllerConfigFromRuntimeEnv, setOperatorModeOnchain } from "../lib/trust-lease-controller.js";

const env = readRuntimeEnvFromFiles();
const baseDir = path.resolve(env.LEASE_DATA_DIR);
const rawCommand = process.argv[2];
const note = process.argv.slice(3).join(" ").trim() || undefined;

if (!rawCommand || !["status", "pause", "resume", "review"].includes(rawCommand)) {
  console.error("usage: npm run operator:<status|pause|resume|review> [note]");
  process.exit(1);
}

if (rawCommand === "status") {
  const state = readOperatorState(baseDir, env.LEASE_OPERATOR_NAME);
  console.log(`operator=${state.operatorName} | mode=${state.mode} | last_command=${state.lastCommand} | updated_at=${state.updatedAt}`);
  if (state.note) {
    console.log(`note=${state.note}`);
  }
  process.exit(0);
}

const commandMap = {
  pause: { mode: "paused", lastCommand: "pause" },
  resume: { mode: "active", lastCommand: "resume" },
  review: { mode: "review", lastCommand: "review" }
} as const;

const mapped = commandMap[rawCommand as keyof typeof commandMap];
const result = applyOperatorCommand({ baseDir, operatorName: env.LEASE_OPERATOR_NAME, mode: mapped.mode, lastCommand: mapped.lastCommand, note });
console.log(`operator=${result.state.operatorName} | mode=${result.state.mode} | last_command=${result.state.lastCommand} | updated_at=${result.state.updatedAt}`);
console.log(`state=${result.statePath}`);
console.log(`event=${result.eventPath}`);

const controllerConfig = controllerConfigFromRuntimeEnv(env);
if (canWriteController(controllerConfig)) {
  const txHash = await setOperatorModeOnchain(controllerConfig, result.state);
  console.log(`controller_tx=${txHash}`);
  console.log(`controller=${controllerConfig.controllerAddress}`);
}
