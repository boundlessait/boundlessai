import { createPublicClient, createWalletClient, http, type Address, type Hex } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { boundlessVaultAbi } from './boundless-vault-abi';

function asAddress(value?: string): Address | undefined {
  if (!value || !value.startsWith('0x') || value.length !== 42) {
    return undefined;
  }
  return value as Address;
}

function asHexKey(value?: string): Hex | undefined {
  if (!value || !value.startsWith('0x')) {
    return undefined;
  }
  return value as Hex;
}

function toUsd6(value: number): bigint {
  return BigInt(Math.max(0, Math.round(value * 1_000_000)));
}

export type BoundlessVaultConfig = {
  rpcUrl: string;
  vaultAddress?: Address;
  writerPrivateKey?: Hex;
};

export function readBoundlessVaultConfig(env: NodeJS.ProcessEnv = process.env): BoundlessVaultConfig {
  return {
    rpcUrl: env.XLAYER_RPC_URL || 'https://xlayer.drpc.org',
    vaultAddress: asAddress(env.BOUNDLESS_VAULT_ADDRESS),
    writerPrivateKey: asHexKey(
      env.BOUNDLESS_VAULT_WRITER_PRIVATE_KEY
      || env.LEASE_CONTROLLER_WRITER_PRIVATE_KEY
      || env.XLAYER_PRIVATE_KEY
      || env.XLAYER_SETTLEMENT_PRIVATE_KEY,
    ),
  };
}

function publicClient(config: BoundlessVaultConfig) {
  return createPublicClient({
    transport: http(config.rpcUrl),
  });
}

function walletClient(config: BoundlessVaultConfig) {
  if (!config.writerPrivateKey || !config.vaultAddress) {
    throw new Error('Missing boundless vault writer configuration.');
  }
  const account = privateKeyToAccount(config.writerPrivateKey);
  return createWalletClient({
    account,
    transport: http(config.rpcUrl),
  });
}

async function writeVault(config: BoundlessVaultConfig, functionName: 'setMemberPolicy' | 'setAllowedAsset' | 'setAllowedProtocol' | 'setLeaseContext', args: readonly unknown[]): Promise<Hex> {
  if (!config.vaultAddress) {
    throw new Error('Missing BOUNDLESS_VAULT_ADDRESS.');
  }
  if (!config.writerPrivateKey) {
    throw new Error('Missing vault writer private key.');
  }
  const pub = publicClient(config);
  const wallet = walletClient(config);
  const account = privateKeyToAccount(config.writerPrivateKey);
  const { request } = await pub.simulateContract({
    account,
    address: config.vaultAddress,
    abi: boundlessVaultAbi,
    functionName: functionName as never,
    args: args as never,
  } as never);

  const hash = await wallet.writeContract(request as never);
  await pub.waitForTransactionReceipt({ hash });
  return hash;
}

export async function setLeaseContextOnchain(
  config: BoundlessVaultConfig,
  payload: {
    leaseId: string;
    consumerName: string;
    operatorName: string;
  },
): Promise<Hex> {
  if (!payload.leaseId.trim()) {
    throw new Error('Lease id is required for vault context sync.');
  }
  if (!payload.consumerName.trim()) {
    throw new Error('Consumer name is required for vault context sync.');
  }
  if (!payload.operatorName.trim()) {
    throw new Error('Operator name is required for vault context sync.');
  }
  return writeVault(config, 'setLeaseContext', [
    payload.leaseId.trim(),
    payload.consumerName.trim(),
    payload.operatorName.trim(),
  ] as const);
}

export async function setMemberPolicyOnchain(
  config: BoundlessVaultConfig,
  payload: {
    member: Address;
    enabled: boolean;
    perTxUsd: number;
    dailyBudgetUsd: number;
  },
): Promise<Hex> {
  const perTxUsd = Math.max(0, payload.perTxUsd);
  const dailyBudgetUsd = Math.max(perTxUsd, payload.dailyBudgetUsd);
  return writeVault(config, 'setMemberPolicy', [
    payload.member,
    payload.enabled,
    toUsd6(perTxUsd),
    toUsd6(dailyBudgetUsd),
  ] as const);
}

export async function readMemberBudgetState(config: BoundlessVaultConfig, member: Address): Promise<{
  exists: boolean;
  enabled: boolean;
  perTxUsd: number;
  dailyBudgetUsd: number;
  spentTodayUsd: number;
  remainingDailyUsd: number;
}> {
  if (!config.vaultAddress) {
    throw new Error('Missing BOUNDLESS_VAULT_ADDRESS.');
  }
  const result = await publicClient(config).readContract({
    address: config.vaultAddress,
    abi: boundlessVaultAbi,
    functionName: 'memberBudgetState',
    args: [member],
  }) as unknown as readonly [boolean, boolean, bigint, bigint, bigint, bigint];

  return {
    exists: result[0],
    enabled: result[1],
    perTxUsd: Number(result[2]) / 1_000_000,
    dailyBudgetUsd: Number(result[3]) / 1_000_000,
    spentTodayUsd: Number(result[4]) / 1_000_000,
    remainingDailyUsd: Number(result[5]) / 1_000_000,
  };
}
