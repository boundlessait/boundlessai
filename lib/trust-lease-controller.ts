import { createPublicClient, createWalletClient, http, keccak256, stringToHex, zeroHash, type Address, type Hex } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { trustLeaseControllerAbi } from './trust-lease-controller-abi';

export type ControllerConfig = {
  rpcUrl: string;
  chainId: number;
  controllerAddress?: Address;
  writerPrivateKey?: Hex;
  consumerName: string;
  operatorName: string;
  artifactBaseUri?: string;
  chainSyncEnabled: boolean;
  deployBlock?: bigint;
};

export type OnchainLeaseSnapshot = {
  exists: boolean;
  leaseId: string;
  wallet: Address;
  consumerName: string;
  baseAsset: string;
  issuedAt: string;
  expiresAt: string;
  status: 'none' | 'active' | 'revoked' | 'expired';
  perTxUsd: number;
  dailyBudgetUsd: number;
  spentTodayUsd: number;
  spentWindowStartedAt: string | null;
  remainingDailyUsd: number;
  policyHash: Hex;
  notesHash: Hex;
};

export type OnchainOperatorSnapshot = {
  exists: boolean;
  operatorName: string;
  mode: 'none' | 'active' | 'review' | 'paused';
  updatedAt: string | null;
  noteHash: Hex;
  updater: Address;
};

export type OnchainReceiptSnapshot = {
  exists: boolean;
  leaseId: string;
  requestId: string;
  consumerName: string;
  outcome: 'none' | 'approve' | 'resize' | 'block' | 'human_approval';
  executionStatus: 'none' | 'ready' | 'simulated' | 'broadcasted' | 'failed' | 'blocked';
  spentUsd: number;
  txHash: Hex;
  proofHash: Hex;
  artifactUri: string;
  timestamp: string | null;
};

export type OnchainReceiptEvent = {
  leaseId: string;
  requestId: string;
  outcome: OnchainReceiptSnapshot['outcome'];
  executionStatus: OnchainReceiptSnapshot['executionStatus'];
  spentUsd: number;
  txHash: Hex;
  proofHash: Hex;
  txHashHex?: string;
  eventTxHash?: Hex;
  blockNumber: bigint;
  timestamp: string | null;
};

export type LeaseLike = {
  leaseId: string;
  consumerName: string;
  walletAddress?: string;
  baseAsset: string;
  issuedAt: string;
  expiresAt: string;
  status: string;
  perTxUsd: number;
  dailyBudgetUsd: number;
  notes: string[];
  allowedAssets?: string[];
  allowedProtocols?: string[];
  allowedActions?: string[];
  counterpartyAllowlist?: string[];
  trustRequirements?: unknown;
};

export type OperatorLike = {
  operatorName: string;
  mode: string;
  lastCommand?: string;
  note?: string;
  updatedAt: string;
};

export type ReceiptPacketLike = {
  lease: { leaseId: string };
  request: { requestId: string; consumerName: string };
  decision: { outcome: string };
  execution: { status: string; txHash?: string };
  receipt: { spentUsd: number };
};

const ZERO_ADDRESS = '0x0000000000000000000000000000000000000000' as Address;
let controllerWriteQueue: Promise<void> = Promise.resolve();

function parseBool(value: string | undefined, fallback = false): boolean {
  if (!value) return fallback;
  return ['1', 'true', 'yes', 'on'].includes(value.toLowerCase());
}

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

function fromUsd6(value: bigint): number {
  return Number(value) / 1_000_000;
}

function unixToIso(value: bigint): string | null {
  if (value === BigInt(0)) return null;
  return new Date(Number(value) * 1000).toISOString();
}

function hashText(value?: string): Hex {
  if (!value || value.trim().length === 0) {
    return zeroHash;
  }
  return keccak256(stringToHex(value));
}

function serializeForHash(input: unknown): string {
  return JSON.stringify(input, Object.keys(input as Record<string, unknown>).sort());
}

export function policyHashForLease(lease: LeaseLike): Hex {
  const policySeed = {
    consumerName: lease.consumerName,
    walletAddress: lease.walletAddress ?? null,
    baseAsset: lease.baseAsset,
    allowedAssets: lease.allowedAssets ?? [],
    allowedProtocols: lease.allowedProtocols ?? [],
    allowedActions: lease.allowedActions ?? [],
    counterpartyAllowlist: lease.counterpartyAllowlist ?? [],
    perTxUsd: lease.perTxUsd,
    dailyBudgetUsd: lease.dailyBudgetUsd,
    trustRequirements: lease.trustRequirements ?? null,
  };
  return keccak256(stringToHex(serializeForHash(policySeed)));
}

function outcomeCode(value: string): number {
  switch (value) {
    case 'approve': return 1;
    case 'resize': return 2;
    case 'block': return 3;
    case 'human_approval': return 4;
    default: return 0;
  }
}

function executionCode(value: string): number {
  switch (value) {
    case 'ready': return 1;
    case 'simulated': return 2;
    case 'broadcasted': return 3;
    case 'failed': return 4;
    case 'blocked': return 5;
    default: return 0;
  }
}

function leaseStatusCode(value: string): number {
  switch (value) {
    case 'active': return 1;
    case 'revoked': return 2;
    case 'expired': return 3;
    default: return 0;
  }
}

function operatorModeCode(value: string): number {
  switch (value) {
    case 'active': return 1;
    case 'review': return 2;
    case 'paused': return 3;
    default: return 0;
  }
}

function leaseStatusLabel(code: bigint): OnchainLeaseSnapshot['status'] {
  switch (Number(code)) {
    case 1: return 'active';
    case 2: return 'revoked';
    case 3: return 'expired';
    default: return 'none';
  }
}

function operatorModeLabel(code: bigint): OnchainOperatorSnapshot['mode'] {
  switch (Number(code)) {
    case 1: return 'active';
    case 2: return 'review';
    case 3: return 'paused';
    default: return 'none';
  }
}

function outcomeLabel(code: bigint): OnchainReceiptSnapshot['outcome'] {
  switch (Number(code)) {
    case 1: return 'approve';
    case 2: return 'resize';
    case 3: return 'block';
    case 4: return 'human_approval';
    default: return 'none';
  }
}

function executionLabel(code: bigint): OnchainReceiptSnapshot['executionStatus'] {
  switch (Number(code)) {
    case 1: return 'ready';
    case 2: return 'simulated';
    case 3: return 'broadcasted';
    case 4: return 'failed';
    case 5: return 'blocked';
    default: return 'none';
  }
}

export function readControllerConfig(env: NodeJS.ProcessEnv = process.env): ControllerConfig {
  return {
    rpcUrl: env.XLAYER_RPC_URL || 'https://xlayer.drpc.org',
    chainId: Number(env.XLAYER_CHAIN_ID || 196),
    controllerAddress: asAddress(env.LEASE_CONTROLLER_ADDRESS),
    writerPrivateKey: asHexKey(env.LEASE_CONTROLLER_WRITER_PRIVATE_KEY || env.XLAYER_PRIVATE_KEY || env.XLAYER_SETTLEMENT_PRIVATE_KEY),
    consumerName: env.LEASE_CONSUMER_NAME || 'strategy-office',
    operatorName: env.LEASE_OPERATOR_NAME || 'human-principal',
    artifactBaseUri: env.LEASE_CONTROLLER_ARTIFACT_BASE_URI || undefined,
    chainSyncEnabled: parseBool(env.LEASE_CHAIN_SYNC_ENABLED, false),
    deployBlock: env.LEASE_CONTROLLER_DEPLOY_BLOCK ? BigInt(env.LEASE_CONTROLLER_DEPLOY_BLOCK) : undefined,
  };
}

export function controllerConfigFromRuntimeEnv(env: {
  XLAYER_RPC_URL: string;
  XLAYER_CHAIN_ID: number;
  LEASE_CONTROLLER_ADDRESS?: string;
  LEASE_CONTROLLER_WRITER_PRIVATE_KEY?: string;
  XLAYER_PRIVATE_KEY?: string;
  XLAYER_SETTLEMENT_PRIVATE_KEY?: string;
  LEASE_CONSUMER_NAME: string;
  LEASE_OPERATOR_NAME: string;
  LEASE_CONTROLLER_ARTIFACT_BASE_URI?: string;
  LEASE_CHAIN_SYNC_ENABLED: boolean;
}): ControllerConfig {
  return {
    rpcUrl: env.XLAYER_RPC_URL,
    chainId: env.XLAYER_CHAIN_ID,
    controllerAddress: asAddress(env.LEASE_CONTROLLER_ADDRESS),
    writerPrivateKey: asHexKey(env.LEASE_CONTROLLER_WRITER_PRIVATE_KEY || env.XLAYER_PRIVATE_KEY || env.XLAYER_SETTLEMENT_PRIVATE_KEY),
    consumerName: env.LEASE_CONSUMER_NAME,
    operatorName: env.LEASE_OPERATOR_NAME,
    artifactBaseUri: env.LEASE_CONTROLLER_ARTIFACT_BASE_URI || undefined,
    chainSyncEnabled: env.LEASE_CHAIN_SYNC_ENABLED,
    deployBlock: undefined,
  };
}

export function hasControllerAddress(config: ControllerConfig): boolean {
  return Boolean(config.controllerAddress);
}

export function canWriteController(config: ControllerConfig): boolean {
  return Boolean(config.chainSyncEnabled && config.controllerAddress && config.writerPrivateKey);
}

function publicClient(config: ControllerConfig) {
  return createPublicClient({
    transport: http(config.rpcUrl),
  });
}

function walletClient(config: ControllerConfig) {
  if (!config.writerPrivateKey || !config.controllerAddress) {
    throw new Error('Missing controller writer configuration.');
  }
  const account = privateKeyToAccount(config.writerPrivateKey);
  return createWalletClient({
    account,
    transport: http(config.rpcUrl),
  });
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function parseNextNonce(message: string): number | null {
  const match = message.match(/next nonce\s+(\d+)/i);
  if (!match?.[1]) {
    return null;
  }
  const nonce = Number(match[1]);
  return Number.isInteger(nonce) && nonce >= 0 ? nonce : null;
}

function isRecoverableNonceError(error: unknown): boolean {
  const message = errorMessage(error);
  return /nonce too low|nonce provided|tx nonce|next nonce|already been used|nonce has already been used/i.test(message);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function enqueueControllerWrite<T>(operation: () => Promise<T>): Promise<T> {
  const next = controllerWriteQueue.then(operation, operation);
  controllerWriteQueue = next.then(
    () => undefined,
    () => undefined,
  );
  return next;
}

async function writeController(
  config: ControllerConfig,
  functionName: 'issueLease' | 'setLeaseStatus' | 'setOperatorMode' | 'setExecutor' | 'anchorReceipt',
  args: readonly unknown[],
): Promise<Hex> {
  return enqueueControllerWrite(() => writeControllerNow(config, functionName, args));
}

async function writeControllerNow(
  config: ControllerConfig,
  functionName: 'issueLease' | 'setLeaseStatus' | 'setOperatorMode' | 'setExecutor' | 'anchorReceipt',
  args: readonly unknown[],
): Promise<Hex> {
  if (!config.controllerAddress) {
    throw new Error('Missing LEASE_CONTROLLER_ADDRESS.');
  }
  const pub = publicClient(config);
  const wallet = walletClient(config);
  const account = privateKeyToAccount(config.writerPrivateKey!);
  const { request } = await pub.simulateContract({
    account,
    address: config.controllerAddress,
    abi: trustLeaseControllerAbi,
    functionName: functionName as never,
    args: args as never,
  } as never);

  let lastError: unknown;
  let nonce = await pub.getTransactionCount({ address: account.address, blockTag: 'pending' });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const hash = await wallet.writeContract({ ...(request as object), nonce } as never);
      try {
        await pub.waitForTransactionReceipt({ hash });
      } catch (error) {
        console.warn(
          '[trust-leases] controller tx broadcasted but receipt polling failed',
          hash,
          error instanceof Error ? error.message : error,
        );
      }
      return hash;
    } catch (error) {
      lastError = error;
      if (!isRecoverableNonceError(error) || attempt === 2) {
        break;
      }
      const parsedNonce = parseNextNonce(errorMessage(error));
      await sleep(250 * (attempt + 1));
      nonce = parsedNonce ?? await pub.getTransactionCount({ address: account.address, blockTag: 'pending' });
    }
  }

  throw lastError instanceof Error ? lastError : new Error('Controller write failed.');
}

export async function issueLeaseOnchain(config: ControllerConfig, lease: LeaseLike): Promise<Hex> {
  return writeController(config, 'issueLease', [
    lease.leaseId,
    lease.consumerName,
    asAddress(lease.walletAddress) ?? ZERO_ADDRESS,
    lease.baseAsset,
    BigInt(Math.floor(new Date(lease.expiresAt).getTime() / 1000)),
    toUsd6(lease.perTxUsd),
    toUsd6(lease.dailyBudgetUsd),
    policyHashForLease(lease),
    hashText(lease.notes.join(' | ')),
  ] as const);
}

export async function setLeaseStatusOnchain(config: ControllerConfig, leaseId: string, status: 'revoked' | 'expired', note?: string): Promise<Hex> {
  return writeController(config, 'setLeaseStatus', [leaseId, leaseStatusCode(status), hashText(note)] as const);
}

export async function setOperatorModeOnchain(config: ControllerConfig, operator: OperatorLike): Promise<Hex> {
  return writeController(config, 'setOperatorMode', [operator.operatorName, operatorModeCode(operator.mode), hashText(operator.note)] as const);
}

export async function setExecutorOnchain(config: ControllerConfig, executor: Address, allowed: boolean): Promise<Hex> {
  return writeController(config, 'setExecutor', [executor, allowed] as const);
}

export function buildArtifactUri(config: ControllerConfig, relativePath?: string): string {
  if (!relativePath || !config.artifactBaseUri) {
    return '';
  }
  const base = config.artifactBaseUri.replace(/\/$/, '');
  const rel = relativePath.replace(/^\//, '');
  return `${base}/${rel}`;
}

export async function anchorReceiptOnchain(config: ControllerConfig, packet: ReceiptPacketLike, artifactUri = ''): Promise<Hex> {
  const proofHash = keccak256(stringToHex(JSON.stringify(packet)));
  const txHash = packet.execution.txHash && packet.execution.txHash.startsWith('0x') && packet.execution.txHash.length === 66
    ? packet.execution.txHash as Hex
    : zeroHash;

  return writeController(config, 'anchorReceipt', [
    packet.lease.leaseId,
    packet.request.requestId,
    packet.request.consumerName,
    outcomeCode(packet.decision.outcome),
    executionCode(packet.execution.status),
    toUsd6(packet.receipt.spentUsd),
    txHash,
    proofHash,
    artifactUri,
  ] as const);
}

export async function readOnchainActiveLease(config: ControllerConfig, consumerName = config.consumerName): Promise<OnchainLeaseSnapshot | null> {
  if (!config.controllerAddress) {
    return null;
  }

  const result = await publicClient(config).readContract({
    address: config.controllerAddress,
    abi: trustLeaseControllerAbi,
    functionName: 'getActiveLeaseByConsumer',
    args: [consumerName],
  }) as unknown as readonly [boolean, string, Address, string, string, bigint, bigint, number, bigint, bigint, bigint, bigint, bigint, Hex, Hex];

  if (!result[0]) {
    return null;
  }

  return {
    exists: result[0],
    leaseId: result[1],
    wallet: result[2],
    consumerName: result[3],
    baseAsset: result[4],
    issuedAt: unixToIso(result[5]) ?? new Date(0).toISOString(),
    expiresAt: unixToIso(result[6]) ?? new Date(0).toISOString(),
    status: leaseStatusLabel(BigInt(result[7])),
    perTxUsd: fromUsd6(result[8]),
    dailyBudgetUsd: fromUsd6(result[9]),
    spentTodayUsd: fromUsd6(result[10]),
    spentWindowStartedAt: unixToIso(result[11]),
    remainingDailyUsd: fromUsd6(result[12]),
    policyHash: result[13],
    notesHash: result[14],
  };
}

export async function readOnchainOperator(config: ControllerConfig, operatorName = config.operatorName): Promise<OnchainOperatorSnapshot | null> {
  if (!config.controllerAddress) {
    return null;
  }

  const result = await publicClient(config).readContract({
    address: config.controllerAddress,
    abi: trustLeaseControllerAbi,
    functionName: 'getOperator',
    args: [operatorName],
  }) as unknown as readonly [boolean, string, number, bigint, Hex, Address];

  if (!result[0]) {
    return null;
  }

  return {
    exists: result[0],
    operatorName: result[1],
    mode: operatorModeLabel(BigInt(result[2])),
    updatedAt: unixToIso(result[3]),
    noteHash: result[4],
    updater: result[5],
  };
}

export async function readOnchainLatestReceipt(config: ControllerConfig, consumerName = config.consumerName): Promise<OnchainReceiptSnapshot | null> {
  if (!config.controllerAddress) {
    return null;
  }

  const result = await publicClient(config).readContract({
    address: config.controllerAddress,
    abi: trustLeaseControllerAbi,
    functionName: 'getLatestReceiptByConsumer',
    args: [consumerName],
  }) as unknown as readonly [boolean, string, string, string, number, number, bigint, Hex, Hex, string, bigint];

  if (!result[0]) {
    return null;
  }

  return {
    exists: result[0],
    leaseId: result[1],
    requestId: result[2],
    consumerName: result[3],
    outcome: outcomeLabel(BigInt(result[4])),
    executionStatus: executionLabel(BigInt(result[5])),
    spentUsd: fromUsd6(result[6]),
    txHash: result[7],
    proofHash: result[8],
    artifactUri: result[9],
    timestamp: unixToIso(result[10]),
  };
}

export async function readRecentOnchainReceipts(
  config: ControllerConfig,
  options: {
    limit?: number;
    fromBlock?: bigint;
  } = {},
): Promise<OnchainReceiptEvent[]> {
  if (!config.controllerAddress) {
    return [];
  }

  const pub = publicClient(config);
  const eventAbi = trustLeaseControllerAbi.find(
    (entry) => entry.type === 'event' && entry.name === 'ReceiptAnchored',
  );
  if (!eventAbi) {
    return [];
  }

  const limit = options.limit ?? 10;
  const latestBlock = await pub.getBlockNumber();
  const absoluteFromBlock = options.fromBlock ?? config.deployBlock ?? (latestBlock > BigInt(8000) ? latestBlock - BigInt(8000) : BigInt(0));
  const chunkSize = BigInt(8000);
  const collected: Awaited<ReturnType<typeof pub.getLogs>> = [];

  let cursor = latestBlock;
  while (cursor >= absoluteFromBlock && collected.length < limit) {
    const chunkFrom = cursor >= chunkSize ? cursor - chunkSize + BigInt(1) : BigInt(0);
    const fromBlock = chunkFrom > absoluteFromBlock ? chunkFrom : absoluteFromBlock;
    const logs = await pub.getLogs({
      address: config.controllerAddress,
      event: eventAbi,
      fromBlock,
      toBlock: cursor,
    });
    if (logs.length > 0) {
      collected.push(...logs);
    }
    if (fromBlock === BigInt(0) || fromBlock === absoluteFromBlock) {
      break;
    }
    cursor = fromBlock - BigInt(1);
  }

  const logs = collected as unknown as Array<{
    args: {
      leaseId: string;
      requestId: string;
      outcome: number | bigint;
      executionStatus: number | bigint;
      spentUsd6: bigint;
      txHash: Hex;
      proofHash: Hex;
    };
    transactionHash: Hex | null;
    blockNumber: bigint | null;
  }>;
  const blockNumbers = Array.from(new Set(logs.map((log) => log.blockNumber).filter((value): value is bigint => typeof value === 'bigint')));
  const blocks = new Map<bigint, string>();
  await Promise.all(
    blockNumbers.map(async (blockNumber) => {
      const block = await pub.getBlock({ blockNumber });
      blocks.set(blockNumber, new Date(Number(block.timestamp) * 1000).toISOString());
    }),
  );

  return logs
    .slice()
    .reverse()
    .slice(0, limit)
    .map((log): OnchainReceiptEvent => {
      const args = log.args;
      const txHash = args.txHash;
      const eventTxHash = log.transactionHash ?? undefined;
      return {
        leaseId: args.leaseId,
        requestId: args.requestId,
        outcome: outcomeLabel(BigInt(args.outcome)),
        executionStatus: executionLabel(BigInt(args.executionStatus)),
        spentUsd: fromUsd6(args.spentUsd6),
        txHash,
        proofHash: args.proofHash,
        txHashHex: txHash !== zeroHash ? txHash : undefined,
        eventTxHash,
        blockNumber: log.blockNumber ?? BigInt(0),
        timestamp: log.blockNumber ? (blocks.get(log.blockNumber) ?? null) : null,
      };
    });
}
