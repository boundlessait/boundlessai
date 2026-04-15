import { readRuntimeEnvFromFiles } from "../src/config/env.js";
import { OnchainOsCliClient } from "../src/onchainos/cli.js";
import { PortfolioManager } from "../src/portfolio/manager.js";
import { runTreasuryPreflight } from "../src/treasury/xlayer.js";

function fail(message: string): never {
  console.error(`[treasury-preflight] FAIL ${message}`);
  process.exit(1);
}

const env = readRuntimeEnvFromFiles();
const privateKey = env.XLAYER_SETTLEMENT_PRIVATE_KEY || env.XLAYER_PRIVATE_KEY;
const treasuryAddress = env.XLAYER_TREASURY_ADDRESS;

if (!privateKey && !treasuryAddress) {
  fail("missing XLAYER_SETTLEMENT_PRIVATE_KEY, XLAYER_PRIVATE_KEY, or XLAYER_TREASURY_ADDRESS");
}

if (!env.XLAYER_SETTLEMENT_TOKEN_ADDRESS) {
  fail("missing XLAYER_SETTLEMENT_TOKEN_ADDRESS");
}

if (!privateKey && treasuryAddress) {
  const client = new OnchainOsCliClient();
  if (!client.isAvailable()) {
    fail("onchainos CLI unavailable and no private key provided");
  }

  const status = client.walletStatus();
  const statusRoot = (status.data ?? status.raw) as Record<string, unknown> | undefined;
  if (!status.ok || statusRoot?.loggedIn !== true) {
    fail("Agentic Wallet is not logged in for the shared fight-club wallet flow");
  }

  const portfolio = new PortfolioManager(client, treasuryAddress, env.XLAYER_CHAIN_ID, env.LEASE_DEFAULT_BASE_ASSET, env.XLAYER_SETTLEMENT_TOKEN_ADDRESS, env.LEASE_MIN_TRADE_USD);
  const overview = await portfolio.getBalances();
  if (!overview.assets.length) {
    fail("wallet balance lookup returned no assets");
  }

  console.log(`[treasury-preflight] env=${env.LEASE_ENV}`);
  console.log(`[treasury-preflight] chainId=${env.XLAYER_CHAIN_ID}`);
  console.log("[treasury-preflight] source=onchainos-agentic-wallet");
  console.log(`[treasury-preflight] treasury=${treasuryAddress}`);
  console.log(`[treasury-preflight] token=${env.XLAYER_SETTLEMENT_TOKEN_SYMBOL} @ ${env.XLAYER_SETTLEMENT_TOKEN_ADDRESS}`);
  console.log(`[treasury-preflight] totalUsd=${overview.totalValueUsd}`);
  for (const balance of overview.assets) {
    console.log(`[treasury-preflight] balance ${balance.symbol} amount=${balance.amount} usd=${balance.usdValue}`);
  }
  console.log("[treasury-preflight] PASS agentic wallet checks completed");
  process.exit(0);
}

const report = await runTreasuryPreflight(env);
if (report.chainId !== env.XLAYER_CHAIN_ID) {
  fail(`RPC returned chainId=${report.chainId}, expected ${env.XLAYER_CHAIN_ID}`);
}

console.log(`[treasury-preflight] env=${env.LEASE_ENV}`);
console.log(`[treasury-preflight] chainId=${report.chainId}`);
console.log(`[treasury-preflight] block=${report.blockNumber.toString()}`);
console.log(`[treasury-preflight] rpc=${env.XLAYER_RPC_URL}`);
console.log(`[treasury-preflight] signer=${report.signerAddress ?? "missing"}`);
console.log(`[treasury-preflight] treasury=${report.treasuryAddress ?? "missing"}`);
for (const balance of report.balances) {
  console.log(`[treasury-preflight] balance ${balance.symbol} amount=${balance.amount} usd=${balance.usdValue}`);
}
console.log("[treasury-preflight] PASS connectivity and treasury read checks completed");
