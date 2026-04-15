import { createPublicClient, erc20Abi, formatEther, formatUnits, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { RuntimeEnv } from "../config/env.js";
import { TreasurySnapshot } from "../core/types.js";

function normalizePrivateKey(privateKey?: string): `0x${string}` | undefined {
  if (!privateKey) {
    return undefined;
  }

  return (privateKey.startsWith("0x") ? privateKey : `0x${privateKey}`) as `0x${string}`;
}

function inferStableUsdValue(symbol: string, amount: number): number {
  return ["USDT0", "USDT", "USDC"].includes(symbol.toUpperCase()) ? amount : 0;
}

export function getSettlementAccountAddress(env: RuntimeEnv): string | undefined {
  const privateKey = normalizePrivateKey(env.XLAYER_SETTLEMENT_PRIVATE_KEY || env.XLAYER_PRIVATE_KEY);
  if (!privateKey) {
    return undefined;
  }

  return privateKeyToAccount(privateKey).address;
}

export async function runTreasuryPreflight(env: RuntimeEnv): Promise<{
  chainId: number;
  blockNumber: bigint;
  signerAddress?: string;
  treasuryAddress?: string;
  balances: TreasurySnapshot["balances"];
}> {
  const client = createPublicClient({
    transport: http(env.XLAYER_RPC_URL)
  });
  const signerAddress = getSettlementAccountAddress(env);
  const treasuryAddress = env.XLAYER_TREASURY_ADDRESS || signerAddress;
  const chainId = await client.getChainId();
  const blockNumber = await client.getBlockNumber();
  const balances: TreasurySnapshot["balances"] = [];

  if (treasuryAddress) {
    const nativeBalance = await client.getBalance({
      address: treasuryAddress as `0x${string}`
    });
    const nativeAmount = Number(formatEther(nativeBalance));
    balances.push({ symbol: "OKB", amount: nativeAmount, usdValue: 0 });
  }

  if (treasuryAddress && env.XLAYER_SETTLEMENT_TOKEN_ADDRESS) {
    const tokenBalance = await client.readContract({
      address: env.XLAYER_SETTLEMENT_TOKEN_ADDRESS as `0x${string}`,
      abi: erc20Abi,
      functionName: "balanceOf",
      args: [treasuryAddress as `0x${string}`]
    });
    const tokenAmount = Number(formatUnits(tokenBalance, env.XLAYER_SETTLEMENT_TOKEN_DECIMALS));
    balances.push({
      symbol: env.XLAYER_SETTLEMENT_TOKEN_SYMBOL,
      amount: tokenAmount,
      usdValue: inferStableUsdValue(env.XLAYER_SETTLEMENT_TOKEN_SYMBOL, tokenAmount)
    });
  }

  return { chainId, blockNumber, signerAddress, treasuryAddress, balances };
}

export function buildSampleTreasurySnapshot(env: RuntimeEnv): TreasurySnapshot {
  return {
    timestamp: new Date().toISOString(),
    network: env.XLAYER_CHAIN_ID === 196 ? "xlayer-mainnet" : "xlayer-custom",
    chainId: env.XLAYER_CHAIN_ID,
    baseAsset: env.LEASE_DEFAULT_BASE_ASSET,
    totalUsd: 18270,
    liquidUsd: 13840,
    capitalAtRiskUsd: 2200,
    balances: [
      { symbol: env.LEASE_DEFAULT_BASE_ASSET, amount: 12480, usdValue: 12480 },
      { symbol: "USDC", amount: 3920, usdValue: 3920 },
      { symbol: "OKB", amount: 26, usdValue: 1870 }
    ]
  };
}

export async function buildLiveTreasurySnapshot(env: RuntimeEnv): Promise<TreasurySnapshot> {
  const preflight = await runTreasuryPreflight(env);
  const stableUsd = preflight.balances.reduce((total, balance) => total + balance.usdValue, 0);

  return {
    timestamp: new Date().toISOString(),
    network: preflight.chainId === 196 ? "xlayer-mainnet" : "xlayer-custom",
    chainId: preflight.chainId,
    baseAsset: env.LEASE_DEFAULT_BASE_ASSET,
    totalUsd: stableUsd,
    liquidUsd: stableUsd,
    capitalAtRiskUsd: 0,
    balances: preflight.balances
  };
}
