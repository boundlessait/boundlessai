import fs from "node:fs";
import path from "node:path";
import { z } from "zod";

const RuntimeEnvSchema = z.object({
  XLAYER_RPC_URL: z.string().default("https://xlayer.drpc.org"),
  XLAYER_CHAIN_ID: z.coerce.number().int().positive().default(196),
  XLAYER_EXPLORER_BASE_URL: z.string().default("https://www.oklink.com/xlayer"),
  XLAYER_SETTLEMENT_PRIVATE_KEY: z.string().optional(),
  XLAYER_PRIVATE_KEY: z.string().optional(),
  XLAYER_TREASURY_ADDRESS: z.string().optional(),
  XLAYER_SETTLEMENT_TOKEN_ADDRESS: z.string().optional(),
  XLAYER_SETTLEMENT_TOKEN_SYMBOL: z.string().default("USDC"),
  XLAYER_SETTLEMENT_TOKEN_DECIMALS: z.coerce.number().int().nonnegative().default(6),
  LEASE_CHAIN_SYNC_ENABLED: z.coerce.boolean().default(false),
  LEASE_CONTROLLER_ADDRESS: z.string().optional(),
  LEASE_CONTROLLER_WRITER_PRIVATE_KEY: z.string().optional(),
  LEASE_CONTROLLER_ARTIFACT_BASE_URI: z.string().optional(),
  LEASE_CONTROLLER_DEPLOY_BLOCK: z.string().optional(),
  LEASE_PUBLIC_PROOF_URL: z.string().optional(),
  BOUNDLESS_VAULT_ADDRESS: z.string().optional(),
  BOUNDLESS_VAULT_WRITER_PRIVATE_KEY: z.string().optional(),
  LEASE_ENV: z.enum(["development", "staging", "production"]).default("development"),
  LEASE_NAME: z.string().default("xlayer-trust-leases"),
  LEASE_DATA_DIR: z.string().default("data/trust-leases"),
  LEASE_OPERATOR_NAME: z.string().default("human-principal"),
  LEASE_EXECUTION_MODE: z.enum(["simulate", "live"]).default("simulate"),
  LEASE_DEFAULT_BASE_ASSET: z.string().default("USDT0"),
  LEASE_CONSUMER_NAME: z.string().default("strategy-office"),
  LEASE_TARGET_ALLOCATIONS: z.string().default("USDT0:65,USDC:25,OKB:10"),
  LEASE_ALLOWED_ASSETS: z.string().default("USDT0,USDC,OKB"),
  LEASE_ALLOWED_PROTOCOLS: z.string().default("okx-aggregator,quickswap"),
  LEASE_ALLOWED_ACTIONS: z.string().default("buy,sell,rebalance"),
  LEASE_ALLOWED_COUNTERPARTIES: z.string().default("okx-aggregator,quickswap"),
  LEASE_PER_TX_USD: z.coerce.number().positive().default(5),
  LEASE_DAILY_BUDGET_USD: z.coerce.number().positive().default(20),
  LEASE_EXPIRY_HOURS: z.coerce.number().positive().default(24),
  LEASE_MIN_TRADE_USD: z.coerce.number().positive().default(3),
  LEASE_MAX_PRICE_IMPACT_PCT: z.coerce.number().positive().default(2),
  LEASE_REASON_REQUIRED: z.coerce.boolean().default(true),
  LEASE_REQUIRE_PROOF: z.coerce.boolean().default(true),
  LEASE_REQUIRE_HEALTHY_ROUTE: z.coerce.boolean().default(false),
  LEASE_ISSUER_LABEL: z.string().default("human-principal"),
  LEASE_NOTES: z
    .string()
    .default("Bounded X Layer execution lease for treasury rebalance and low-notional agent actions.")
});

export type RuntimeEnv = z.infer<typeof RuntimeEnvSchema>;

function parseEnvFile(content: string): Record<string, string> {
  const pairs: Record<string, string> = {};

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const separator = line.indexOf("=");
    if (separator === -1) {
      continue;
    }

    const key = line.slice(0, separator).trim();
    let value = line.slice(separator + 1).trim();

    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }

    pairs[key] = value;
  }

  return pairs;
}

function withCompatAliases(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const next = { ...env };

  next.LEASE_EXECUTION_MODE ??= env.OFFICE_EXECUTION_MODE;
  next.LEASE_DEFAULT_BASE_ASSET ??= env.OFFICE_DEFAULT_BASE_ASSET;
  next.LEASE_DATA_DIR ??= env.OFFICE_DATA_DIR;
  next.LEASE_OPERATOR_NAME ??= env.OFFICE_OPERATOR_NAME;
  next.LEASE_MIN_TRADE_USD ??= env.OFFICE_MIN_TRADE_USD;
  next.LEASE_NAME ??= env.OFFICE_NAME;

  return next;
}

export function loadLocalEnvFiles(cwd = process.cwd(), env: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const fileEnv: Record<string, string> = {};

  for (const fileName of [".env", ".env.local"]) {
    const filePath = path.resolve(cwd, fileName);
    if (!fs.existsSync(filePath)) {
      continue;
    }

    Object.assign(fileEnv, parseEnvFile(fs.readFileSync(filePath, "utf8")));
  }

  return withCompatAliases({
    ...fileEnv,
    ...env
  });
}

export function readRuntimeEnv(env: NodeJS.ProcessEnv = process.env): RuntimeEnv {
  return RuntimeEnvSchema.parse(withCompatAliases(env));
}

export function readRuntimeEnvFromFiles(cwd = process.cwd(), env: NodeJS.ProcessEnv = process.env): RuntimeEnv {
  return readRuntimeEnv(loadLocalEnvFiles(cwd, env));
}

export function parseCsvList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseAllocations(value: string): Record<string, number> {
  const entries = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const [symbol, pct] = item.split(":").map((part) => part.trim());
      return [symbol, Number(pct)] as const;
    })
    .filter((entry) => entry[0] && Number.isFinite(entry[1]));

  return Object.fromEntries(entries);
}
