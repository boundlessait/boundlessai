'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { createPublicClient, createWalletClient, custom, http, isAddress, keccak256, stringToHex, zeroHash, type Address } from 'viem';
import { boundlessVaultAbi } from '@/lib/boundless-vault-abi';
import { sanitizeProofText } from '@/lib/format';
import {
  KITE_TESTNET_CHAIN_ID,
  KITE_TESTNET_EXPLORER_BASE_URL,
  KITE_TESTNET_RPC_URL,
  kiteChainById,
} from '@/lib/chain-config';
import { trustLeaseControllerAbi } from '@/lib/trust-lease-controller-abi';
import type { EthereumProvider } from '@/types/ethereum-provider';

const CONNECTED_WALLET_STORAGE_KEY = 'trust-leases.connected-wallet';
const GUIDE_STORAGE_KEY = 'boundless.console.guide-seen';
const GUIDE_SESSION_DISMISSED_KEY = 'boundless.console.guide-dismissed-session';

type OperatorConsoleProps = {
  leaseId?: string | null;
  leaseStatus?: string | null;
  operatorMode?: string | null;
  latestSuccessTxHash?: string | null;
  latestBlockedReason?: string | null;
  controllerAddress?: string | null;
  controllerSource?: 'local' | 'onchain';
  governedWallet?: string | null;
  baseAsset?: string | null;
  perTxUsd?: number | null;
  dailyBudgetUsd?: number | null;
  allowedAssets?: string[] | null;
  allowedProtocols?: string[] | null;
  actionsEnabled?: boolean;
  runRoundEnabled?: boolean;
  controllerNote?: string | null;
  vaultAddress?: string | null;
  consumerName?: string | null;
  operatorName?: string | null;
  chainId?: number | null;
};

type ControlAction =
  | 'issue-lease'
  | 'revoke-lease'
  | 'pause'
  | 'review'
  | 'resume'
  | 'run-round'
  | 'refresh-proof'
  | 'set-member-policy';

type GuideStep = {
  id: string;
  targetId: string;
  title: string;
  summary: string;
  detail: string;
};

const GUIDE_STEPS: GuideStep[] = [
  {
    id: 'wallet',
    targetId: 'governed-wallet',
    title: 'Set Governed Wallet',
    summary: 'Choose the wallet that Boundless policy protects.',
    detail: 'Passport handles delegated payment permission. This wallet is the treasury or vault that Boundless governs on top of that session.',
  },
  {
    id: 'budget',
    targetId: 'per-tx-usd',
    title: 'Set Boundless Budget',
    summary: 'Define the max spend per action and per day.',
    detail: 'Any Passport-backed request above these limits is blocked by Boundless before execution.',
  },
  {
    id: 'member',
    targetId: 'member-wallet',
    title: 'Set Member Budget',
    summary: 'Assign budget per member wallet.',
    detail: 'Member limits are separate from global limits. Exceeding either side reverts before the payment settles.',
  },
  {
    id: 'save-rule',
    targetId: 'action-issue-lease',
    title: 'Write Policy Onchain',
    summary: 'Save the current Boundless policy to the controller contract.',
    detail: 'This makes the latest budget and operator gate active above the Passport session.',
  },
  {
    id: 'run-round',
    targetId: 'action-run-round',
    title: 'Run And Verify',
    summary: 'Run a governed payment check and inspect the result.',
    detail: 'Use this to demo success and failure paths with proof.',
  },
];

const ACTION_GROUPS: Array<{
  label: string;
  actions: Array<{ action: ControlAction; label: string; help: string; tone?: 'primary' | 'warn' | 'neutral' }>;
}> = [
  {
    label: 'Policy',
    actions: [
      { action: 'issue-lease', label: 'Save Policy', help: 'Write or replace this Boundless policy onchain with the settings above.', tone: 'primary' },
      { action: 'revoke-lease', label: 'Disable', help: 'Cancel the current Boundless policy immediately.', tone: 'warn' },
    ],
  },
  {
    label: 'Operator',
    actions: [
      { action: 'pause', label: 'Pause', help: 'Stop autonomous execution until resumed.', tone: 'warn' },
      { action: 'review', label: 'Review', help: 'Force manual review before execution.', tone: 'warn' },
      { action: 'resume', label: 'Resume', help: 'Return to active governed execution.', tone: 'primary' },
    ],
  },
  {
    label: 'Runtime',
    actions: [
      { action: 'run-round', label: 'Run Payment Check', help: 'Ask the runner to create the next governed request.', tone: 'primary' },
      { action: 'refresh-proof', label: 'Refresh', help: 'Reload lease, receipt, and dashboard proof.', tone: 'neutral' },
    ],
  },
];

const ACTION_PENDING_LABEL: Record<ControlAction, string> = {
  'issue-lease': 'Saving policy…',
  'revoke-lease': 'Disabling policy…',
  pause: 'Applying pause mode…',
  review: 'Applying review mode…',
  resume: 'Resuming active mode…',
  'run-round': 'Running governed payment check…',
  'refresh-proof': 'Refreshing proof…',
  'set-member-policy': 'Saving member policy…',
};

function hashText(value?: string): `0x${string}` {
  if (!value || value.trim().length === 0) {
    return zeroHash;
  }
  return keccak256(stringToHex(value));
}

function serializeForHash(input: unknown): string {
  return JSON.stringify(input, Object.keys(input as Record<string, unknown>).sort());
}

function policyHashForLease(input: {
  consumerName: string;
  walletAddress?: string;
  baseAsset: string;
  allowedAssets: string[];
  allowedProtocols: string[];
  allowedActions: string[];
  counterpartyAllowlist: string[];
  perTxUsd: number;
  dailyBudgetUsd: number;
}): `0x${string}` {
  const policySeed = {
    consumerName: input.consumerName,
    walletAddress: input.walletAddress ?? null,
    baseAsset: input.baseAsset,
    allowedAssets: input.allowedAssets,
    allowedProtocols: input.allowedProtocols,
    allowedActions: input.allowedActions,
    counterpartyAllowlist: input.counterpartyAllowlist,
    perTxUsd: input.perTxUsd,
    dailyBudgetUsd: input.dailyBudgetUsd,
    trustRequirements: {
      reasonRequired: true,
      proofRequired: true,
      operatorCanPause: true,
      degradedRequiresReview: true,
    },
  };
  return keccak256(stringToHex(serializeForHash(policySeed)));
}

function toUsd6(value: number): bigint {
  return BigInt(Math.max(0, Math.round(value * 1_000_000)));
}

function statusCode(value: 'revoked'): number {
  switch (value) {
    case 'revoked':
      return 2;
  }
}

function operatorModeCode(value: 'active' | 'review' | 'paused'): number {
  switch (value) {
    case 'active':
      return 1;
    case 'review':
      return 2;
    case 'paused':
      return 3;
  }
}

function parseCsvText(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

export function OperatorConsole({
  leaseId,
  leaseStatus,
  operatorMode,
  latestSuccessTxHash,
  latestBlockedReason,
  controllerAddress,
  controllerSource,
  governedWallet,
  baseAsset,
  perTxUsd,
  dailyBudgetUsd,
  allowedAssets,
  allowedProtocols,
  actionsEnabled = true,
  runRoundEnabled = true,
  controllerNote,
  vaultAddress,
  consumerName,
  operatorName,
  chainId,
}: OperatorConsoleProps) {
  const router = useRouter();
  const [note, setNote] = useState('');
  const [walletAddress, setWalletAddress] = useState(governedWallet ?? '');
  const [baseAssetInput, setBaseAssetInput] = useState((baseAsset ?? 'USDT').toUpperCase());
  const [perTxUsdInput, setPerTxUsdInput] = useState(String(perTxUsd ?? 3));
  const [dailyBudgetUsdInput, setDailyBudgetUsdInput] = useState(String(dailyBudgetUsd ?? 15));
  const [expiryHoursInput, setExpiryHoursInput] = useState('24');
  const [allowedAssetsInput, setAllowedAssetsInput] = useState((allowedAssets && allowedAssets.length > 0 ? allowedAssets : ['USDT']).join(','));
  const [allowedProtocolsInput, setAllowedProtocolsInput] = useState((allowedProtocols && allowedProtocols.length > 0 ? allowedProtocols : ['x402', 'mcp']).join(','));
  const [memberAddressInput, setMemberAddressInput] = useState('');
  const [memberPerTxInput, setMemberPerTxInput] = useState('1');
  const [memberDailyInput, setMemberDailyInput] = useState('5');
  const [memberEnabled, setMemberEnabled] = useState(true);
  const [busyAction, setBusyAction] = useState<ControlAction | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metaExpanded, setMetaExpanded] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideStepIndex, setGuideStepIndex] = useState(0);
  const [guideTargetRect, setGuideTargetRect] = useState<DOMRect | null>(null);
  const [guideCardPosition, setGuideCardPosition] = useState<{ top: number; left: number } | null>(null);
  const [connectedWallet, setConnectedWallet] = useState<string | null>(null);

  useEffect(() => {
    if (governedWallet) {
      setWalletAddress(governedWallet);
    }
  }, [governedWallet]);

  useEffect(() => {
    if (baseAsset) {
      setBaseAssetInput(baseAsset.toUpperCase());
    }
  }, [baseAsset]);

  useEffect(() => {
    if (typeof perTxUsd === 'number' && Number.isFinite(perTxUsd)) {
      setPerTxUsdInput(String(perTxUsd));
    }
  }, [perTxUsd]);

  useEffect(() => {
    if (typeof dailyBudgetUsd === 'number' && Number.isFinite(dailyBudgetUsd)) {
      setDailyBudgetUsdInput(String(dailyBudgetUsd));
    }
  }, [dailyBudgetUsd]);

  useEffect(() => {
    if (allowedAssets && allowedAssets.length > 0) {
      setAllowedAssetsInput(allowedAssets.join(','));
    }
  }, [allowedAssets]);

  useEffect(() => {
    if (allowedProtocols && allowedProtocols.length > 0) {
      setAllowedProtocolsInput(allowedProtocols.join(','));
    }
  }, [allowedProtocols]);

  useEffect(() => {
    const shouldFollowConnectedWallet = !governedWallet;
    const cachedWallet = window.localStorage.getItem(CONNECTED_WALLET_STORAGE_KEY);
    if (shouldFollowConnectedWallet && cachedWallet) {
      setWalletAddress(cachedWallet);
    }
    if (cachedWallet) {
      setConnectedWallet(cachedWallet);
    }

    const handleWalletUpdated = (event: Event) => {
      if (!shouldFollowConnectedWallet) {
        return;
      }
      const detail = (event as CustomEvent<{ address?: string }>).detail;
      if (!detail?.address) {
        return;
      }
      setConnectedWallet(detail.address);
      setWalletAddress(detail.address);
    };

    window.addEventListener('trust-leases-wallet-updated', handleWalletUpdated);
    return () => {
      window.removeEventListener('trust-leases-wallet-updated', handleWalletUpdated);
    };
  }, [governedWallet]);

  // Guide: update highlight position
  useEffect(() => {
    if (!guideOpen) {
      setGuideTargetRect(null);
      setGuideCardPosition(null);
      return;
    }

    const refresh = () => {
      const step = GUIDE_STEPS[guideStepIndex];
      const target = document.getElementById(step.targetId);
      if (!target) {
        setGuideTargetRect(null);
        setGuideCardPosition({ top: 96, left: 24 });
        return;
      }
      const rect = target.getBoundingClientRect();
      setGuideTargetRect(rect);

      const cardWidth = 320;
      const viewportPadding = 16;
      const nextLeft = Math.min(
        window.innerWidth - cardWidth - viewportPadding,
        Math.max(viewportPadding, rect.left),
      );
      const hasBottomSpace = rect.bottom + 220 < window.innerHeight;
      const nextTop = hasBottomSpace
        ? rect.bottom + 12
        : Math.max(viewportPadding, rect.top - 220);

      setGuideCardPosition({ top: nextTop, left: nextLeft });
    };

    const step = GUIDE_STEPS[guideStepIndex];
    const target = document.getElementById(step.targetId);
    target?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });

    const timer = window.setTimeout(refresh, 120);
    window.addEventListener('resize', refresh);
    window.addEventListener('scroll', refresh, true);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('resize', refresh);
      window.removeEventListener('scroll', refresh, true);
    };
  }, [guideOpen, guideStepIndex]);

  useEffect(() => {
    if (!guideOpen) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeGuide(false);
      } else if (event.key === 'ArrowLeft' && guideStepIndex > 0) {
        setGuideStepIndex((prev) => Math.max(0, prev - 1));
      } else if (event.key === 'ArrowRight') {
        nextGuideStep();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [guideOpen, guideStepIndex]);

  const meta = useMemo(
    () => [
      `Policy: ${leaseId ? leaseId.slice(0, 8) + '...' : 'none'}`,
      `Status: ${leaseStatus ?? 'not issued'}`,
      `Operator: ${operatorMode ?? 'idle'}`,
    ],
    [leaseId, leaseStatus, operatorMode],
  );

  const fullMeta = useMemo(
    () => [
      `Policy: ${leaseId ?? 'none'}`,
      `Status: ${leaseStatus ?? 'not issued'}`,
      `Operator: ${operatorMode ?? 'idle'}`,
      controllerAddress ? `Controller: ${controllerSource === 'onchain' ? 'Onchain' : 'Local'} ${controllerAddress}` : 'Controller: local runtime',
      latestSuccessTxHash ? `Latest success: ${latestSuccessTxHash}` : 'Latest success: none yet',
      connectedWallet ? `Admin wallet: ${connectedWallet}` : 'Admin wallet: not connected',
    ],
    [leaseId, leaseStatus, operatorMode, controllerAddress, controllerSource, latestSuccessTxHash, connectedWallet],
  );

  async function getWalletClients() {
    if (!window.ethereum) {
      throw new Error('No browser wallet found.');
    }

    const targetChainId = chainId ?? KITE_TESTNET_CHAIN_ID;
    const hexChainId = `0x${targetChainId.toString(16)}`;
    const activeChain = kiteChainById(targetChainId);
    const rpcUrl = activeChain.rpcUrls.default.http[0] ?? KITE_TESTNET_RPC_URL;
    const explorerUrl = activeChain.blockExplorers?.default.url ?? KITE_TESTNET_EXPLORER_BASE_URL;
    try {
      await window.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: hexChainId }],
      });
    } catch {
      await window.ethereum.request({
        method: 'wallet_addEthereumChain',
        params: [{
          chainId: hexChainId,
          chainName: activeChain.name,
          nativeCurrency: activeChain.nativeCurrency,
          rpcUrls: [rpcUrl],
          blockExplorerUrls: [explorerUrl],
        }],
      });
    }

    const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' }) as string[];
    const account = accounts[0];
    if (!account || !isAddress(account)) {
      throw new Error('Wallet did not return a valid admin address.');
    }

    setConnectedWallet(account);
    window.localStorage.setItem(CONNECTED_WALLET_STORAGE_KEY, account);
    if (!governedWallet) {
      setWalletAddress(account);
    }

    const publicClient = createPublicClient({
      chain: activeChain,
      transport: http(rpcUrl),
    });
    const walletClient = createWalletClient({
      chain: activeChain,
      account: account as Address,
      transport: custom(window.ethereum),
    });

    return { publicClient, walletClient, account: account as Address };
  }

  async function writeControllerContract(input: {
    functionName: 'issueLease' | 'setLeaseStatus' | 'setOperatorMode';
    args: readonly unknown[];
  }) {
    if (!controllerAddress || !isAddress(controllerAddress)) {
      throw new Error('Missing controller contract address.');
    }
    const { publicClient, walletClient, account } = await getWalletClients();
    const { request } = await publicClient.simulateContract({
      account,
      address: controllerAddress as Address,
      abi: trustLeaseControllerAbi,
      functionName: input.functionName as never,
      args: input.args as never,
    } as never);
    const hash = await walletClient.writeContract(request as never);
    await publicClient.waitForTransactionReceipt({ hash });
    return hash;
  }

  async function writeVaultContract(input: {
    functionName: 'setMemberPolicy' | 'setLeaseContext';
    args: readonly unknown[];
  }) {
    if (!vaultAddress || !isAddress(vaultAddress)) {
      throw new Error('Missing vault contract address.');
    }
    const { publicClient, walletClient, account } = await getWalletClients();
    const { request } = await publicClient.simulateContract({
      account,
      address: vaultAddress as Address,
      abi: boundlessVaultAbi,
      functionName: input.functionName as never,
      args: input.args as never,
    } as never);
    const hash = await walletClient.writeContract(request as never);
    await publicClient.waitForTransactionReceipt({ hash });
    return hash;
  }

  async function runAction(action: ControlAction) {
    setBusyAction(action);
    setMessage(null);
    setError(null);

    const perTxValue = Number(perTxUsdInput);
    const dailyValue = Number(dailyBudgetUsdInput);
    const expiryValue = Number(expiryHoursInput);

    if (action === 'issue-lease') {
      if (!walletAddress.trim().startsWith('0x')) {
        setBusyAction(null);
        setError('Set a valid wallet address before saving the policy.');
        return;
      }
      if (!Number.isFinite(perTxValue) || perTxValue <= 0 || !Number.isFinite(dailyValue) || dailyValue <= 0) {
        setBusyAction(null);
        setError('Per-tx and daily budget must be positive numbers.');
        return;
      }
      if (!Number.isFinite(expiryValue) || expiryValue <= 0) {
        setBusyAction(null);
        setError('Expiry hours must be a positive number.');
        return;
      }
    }
    if (action === 'set-member-policy') {
      const memberPerTxValue = Number(memberPerTxInput);
      const memberDailyValue = Number(memberDailyInput);
      if (!memberAddressInput.trim().startsWith('0x')) {
        setBusyAction(null);
        setError('Set a valid member wallet address.');
        return;
      }
      if (memberEnabled) {
        if (!Number.isFinite(memberPerTxValue) || memberPerTxValue <= 0 || !Number.isFinite(memberDailyValue) || memberDailyValue <= 0) {
          setBusyAction(null);
          setError('Member per-tx and daily budgets must be positive numbers.');
          return;
        }
      }
    }

    try {
      const walletActions = new Set<ControlAction>([
        'issue-lease',
        'revoke-lease',
        'pause',
        'review',
        'resume',
        'set-member-policy',
      ]);

      if (walletActions.has(action)) {
        if (action === 'issue-lease') {
          const nextLeaseId = `lease_${crypto.randomUUID()}`;
          const nextConsumerName = consumerName?.trim() || 'bound-agent';
          const nextOperatorName = operatorName?.trim() || 'human-principal';
          const nextBaseAsset = baseAssetInput.trim().toUpperCase();
          const nextAllowedAssets = parseCsvText(allowedAssetsInput).map((value) => value.toUpperCase());
          const nextAllowedProtocols = parseCsvText(allowedProtocolsInput).map((value) => value.toLowerCase());
          const nextAllowedActions = ['buy', 'sell', 'rebalance'];
          const nextCounterparties = nextAllowedProtocols;
          const expiresAtUnix = BigInt(Math.floor(Date.now() / 1000) + expiryValue * 60 * 60);
          const policyHash = policyHashForLease({
            consumerName: nextConsumerName,
            walletAddress: walletAddress.trim(),
            baseAsset: nextBaseAsset,
            allowedAssets: nextAllowedAssets,
            allowedProtocols: nextAllowedProtocols,
            allowedActions: nextAllowedActions,
            counterpartyAllowlist: nextCounterparties,
            perTxUsd: perTxValue,
            dailyBudgetUsd: dailyValue,
          });
          const notesHash = hashText(note.trim() || 'Boundless policy for Passport-governed agent payments.');

          await writeControllerContract({
            functionName: 'issueLease',
            args: [
              nextLeaseId,
              nextConsumerName,
              walletAddress.trim() as Address,
              nextBaseAsset,
              expiresAtUnix,
              toUsd6(perTxValue),
              toUsd6(dailyValue),
              policyHash,
              notesHash,
            ] as const,
          });

          if (vaultAddress) {
            await writeVaultContract({
              functionName: 'setLeaseContext',
              args: [nextLeaseId, nextConsumerName, nextOperatorName] as const,
            });
          }

          if (leaseId && leaseStatus === 'active') {
            await writeControllerContract({
              functionName: 'setLeaseStatus',
              args: [leaseId, statusCode('revoked'), hashText('superseded by wallet-signed policy update')] as const,
            });
          }
        } else if (action === 'revoke-lease') {
          if (!leaseId) {
            throw new Error('No active policy to disable.');
          }
          await writeControllerContract({
            functionName: 'setLeaseStatus',
            args: [leaseId, statusCode('revoked'), hashText(note)] as const,
          });
        } else if (action === 'pause' || action === 'review' || action === 'resume') {
          const nextMode = action === 'pause' ? 'paused' : action === 'review' ? 'review' : 'active';
          await writeControllerContract({
            functionName: 'setOperatorMode',
            args: [operatorName?.trim() || 'human-principal', operatorModeCode(nextMode), hashText(note)] as const,
          });
        } else if (action === 'set-member-policy') {
          await writeVaultContract({
            functionName: 'setMemberPolicy',
            args: [
              memberAddressInput.trim() as Address,
              memberEnabled,
              toUsd6(Number(memberPerTxInput)),
              toUsd6(Number(memberDailyInput)),
            ] as const,
          });
        }

        setMessage('Wallet-signed action confirmed onchain.');
        if (action !== 'refresh-proof') {
          setNote('');
        }
        router.refresh();
        return;
      }

      const response = await fetch('/api/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          note,
          walletAddress,
          leaseOverrides: action === 'issue-lease'
            ? {
                baseAsset: baseAssetInput.trim().toUpperCase(),
                perTxUsd: perTxValue,
                dailyBudgetUsd: dailyValue,
                allowedAssets: parseCsvText(allowedAssetsInput),
                allowedProtocols: parseCsvText(allowedProtocolsInput),
                expiryHours: expiryValue,
              }
            : undefined,
          memberPolicy: action === 'set-member-policy'
            ? {
                memberAddress: memberAddressInput.trim(),
                enabled: memberEnabled,
                perTxUsd: Number(memberPerTxInput),
                dailyBudgetUsd: Number(memberDailyInput),
              }
            : undefined,
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || 'Action failed');
      }
      setMessage(payload.message || 'Done');
      if (action !== 'refresh-proof') {
        setNote('');
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed');
    } finally {
      setBusyAction(null);
    }
  }

  // Guide functions
  function closeGuide(markSeen = true) {
    setGuideOpen(false);
    window.sessionStorage.setItem(GUIDE_SESSION_DISMISSED_KEY, '1');
    if (markSeen) {
      window.localStorage.setItem(GUIDE_STORAGE_KEY, '1');
    }
  }

  function openGuide() {
    window.sessionStorage.removeItem(GUIDE_SESSION_DISMISSED_KEY);
    setGuideStepIndex(0);
    setGuideOpen(true);
  }

  function nextGuideStep() {
    if (guideStepIndex >= GUIDE_STEPS.length - 1) {
      closeGuide(true);
      return;
    }
    setGuideStepIndex((prev) => prev + 1);
  }

  return (
    <div className="card console-card">
      <div className="console-header">
        <h2>Controls</h2>
        <div className="console-meta">
          {meta.map((item) => (
            <span key={item} className="pill ok">{item}</span>
          ))}
          <button
            type="button"
            className="pill-btn"
            onClick={() => setMetaExpanded(!metaExpanded)}
          >
            {metaExpanded ? 'Less' : 'More'}
          </button>
          <button
            type="button"
            className="pill-btn"
            onClick={openGuide}
          >
            Guide
          </button>
          {metaExpanded && (
            <div className="meta-expanded">
              {fullMeta.map((item) => (
                <span key={item} className="pill">{item}</span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="response-banner pending" style={{ marginBottom: 16 }}>
        Kite Passport handles identity and delegated payment permission. Boundless adds the policy gate, operator controls, and proof shown below.
      </div>

      <div className="response-banner pending" style={{ marginBottom: 16 }}>
        Admin actions are wallet-signed. Boundless never requires the treasury owner to give the app a private key.
      </div>

      <div className="console-form">
        <div className="form-row">
          <div className="form-field">
            <label htmlFor="governed-wallet" className="note-label">Governed Wallet</label>
            <input
              id="governed-wallet"
              value={walletAddress}
              onChange={(event) => setWalletAddress(event.target.value)}
              placeholder="0x..."
              className="note-input mono"
            />
          </div>
          <div className="form-field">
            <label htmlFor="per-tx-usd" className="note-label">Per-Tx Limit</label>
            <input
              id="per-tx-usd"
              value={perTxUsdInput}
              onChange={(event) => setPerTxUsdInput(event.target.value)}
              placeholder="3"
              className="note-input"
            />
          </div>
          <div className="form-field">
            <label htmlFor="daily-budget-usd" className="note-label">Daily Budget</label>
            <input
              id="daily-budget-usd"
              value={dailyBudgetUsdInput}
              onChange={(event) => setDailyBudgetUsdInput(event.target.value)}
              placeholder="15"
              className="note-input"
            />
          </div>
        </div>

        <details className="settings-advanced">
          <summary>Advanced Settings</summary>
          <div className="form-row">
            <div className="form-field">
              <label htmlFor="base-asset" className="note-label">Base Asset</label>
              <input
                id="base-asset"
                value={baseAssetInput}
                onChange={(event) => setBaseAssetInput(event.target.value.toUpperCase())}
                placeholder="USDT"
                className="note-input"
              />
            </div>
            <div className="form-field">
              <label htmlFor="allowed-assets" className="note-label">Allowed Assets</label>
              <input
                id="allowed-assets"
                value={allowedAssetsInput}
                onChange={(event) => setAllowedAssetsInput(event.target.value)}
                placeholder="USDT"
                className="note-input"
              />
            </div>
            <div className="form-field">
              <label htmlFor="allowed-protocols" className="note-label">Allowed Protocols</label>
              <input
                id="allowed-protocols"
                value={allowedProtocolsInput}
                onChange={(event) => setAllowedProtocolsInput(event.target.value)}
                placeholder="x402,mcp"
                className="note-input"
              />
            </div>
            <div className="form-field">
              <label htmlFor="expiry-hours" className="note-label">Expiry Hours</label>
              <input
                id="expiry-hours"
                value={expiryHoursInput}
                onChange={(event) => setExpiryHoursInput(event.target.value)}
                placeholder="24"
                className="note-input"
              />
            </div>
          </div>
        </details>

        <div className="form-field note-field">
          <label htmlFor="operator-note" className="note-label">Note (optional)</label>
          <input
            id="operator-note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="optional policy note or operator command reason"
            className="note-input"
          />
        </div>
      </div>

      <div className="console-actions">
        {busyAction ? (
          <div className="response-banner pending">
            {ACTION_PENDING_LABEL[busyAction]} Please confirm wallet signature and wait for chain receipt.
          </div>
        ) : null}
        <div className="action-group">
          <div className="action-group-label">Policy</div>
          <div className="action-buttons">
            {ACTION_GROUPS[0].actions.map((item) => (
              <button
                key={item.action}
                id={item.action === 'issue-lease' ? 'action-issue-lease' : undefined}
                type="button"
                className={`action-button ${item.tone ?? 'neutral'}`}
                disabled={busyAction !== null || !actionsEnabled}
                onClick={() => runAction(item.action)}
              >
                {busyAction === item.action ? ACTION_PENDING_LABEL[item.action] : item.label}
              </button>
            ))}
          </div>
        </div>
        <div className="action-group">
          <div className="action-group-label">Operator</div>
          <div className="action-buttons">
            {ACTION_GROUPS[1].actions.map((item) => (
              <button
                key={item.action}
                type="button"
                className={`action-button ${item.tone ?? 'neutral'}`}
                disabled={busyAction !== null || !actionsEnabled}
                onClick={() => runAction(item.action)}
              >
                {busyAction === item.action ? ACTION_PENDING_LABEL[item.action] : item.label}
              </button>
            ))}
          </div>
        </div>
        <div className="action-group">
          <div className="action-group-label">Runtime</div>
          <div className="action-buttons">
            {ACTION_GROUPS[2].actions.map((item) => (
              <button
                key={item.action}
                id={item.action === 'run-round' ? 'action-run-round' : undefined}
                type="button"
                className={`action-button ${item.tone ?? 'neutral'}`}
                disabled={
                  busyAction !== null ||
                  !actionsEnabled ||
                  (item.action === 'run-round' && !runRoundEnabled)
                }
                onClick={() => runAction(item.action)}
              >
                {busyAction === item.action ? ACTION_PENDING_LABEL[item.action] : item.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <details className="settings-advanced member-section">
        <summary>Member Budget Policy</summary>
        <div className="form-row">
          <div className="form-field">
            <label htmlFor="member-wallet" className="note-label">Member Wallet</label>
            <input
              id="member-wallet"
              value={memberAddressInput}
              onChange={(event) => setMemberAddressInput(event.target.value)}
              placeholder="0x..."
              className="note-input mono"
            />
          </div>
          <div className="form-field">
            <label htmlFor="member-per-tx" className="note-label">Per-Tx</label>
            <input
              id="member-per-tx"
              value={memberPerTxInput}
              onChange={(event) => setMemberPerTxInput(event.target.value)}
              placeholder="1"
              className="note-input"
            />
          </div>
          <div className="form-field">
            <label htmlFor="member-daily" className="note-label">Daily</label>
            <input
              id="member-daily"
              value={memberDailyInput}
              onChange={(event) => setMemberDailyInput(event.target.value)}
              placeholder="5"
              className="note-input"
            />
          </div>
          <div className="form-field">
            <label className="note-label">Status</label>
            <div className="checkbox-wrap">
              <input
                id="member-enabled"
                type="checkbox"
                checked={memberEnabled}
                onChange={(event) => setMemberEnabled(event.target.checked)}
              />
              <span>{memberEnabled ? 'Enabled' : 'Disabled'}</span>
            </div>
          </div>
        </div>
        <button
          type="button"
          className="action-button primary"
          disabled={busyAction !== null || !actionsEnabled}
          onClick={() => runAction('set-member-policy')}
        >
          {busyAction === 'set-member-policy' ? ACTION_PENDING_LABEL['set-member-policy'] : 'Save Member Policy'}
        </button>
      </details>

      {message ? <div className="response-banner success">{message}</div> : null}
      {error ? <div className="response-banner error">{error}</div> : null}

      {latestBlockedReason ? (
        <div className="control-footnote">
          Latest guardrail: {sanitizeProofText(latestBlockedReason)}
        </div>
      ) : null}

      {guideOpen ? (
        <div
          className="guide-overlay"
          role="presentation"
          onClick={() => closeGuide(false)}
        >
          {guideTargetRect ? (
            <div
              className="guide-highlight"
              style={{
                top: `${guideTargetRect.top - 6}px`,
                left: `${guideTargetRect.left - 6}px`,
                width: `${guideTargetRect.width + 12}px`,
                height: `${guideTargetRect.height + 12}px`,
              }}
            />
          ) : null}
          <div
            className="guide-card"
            style={{
              top: `${guideCardPosition?.top ?? 96}px`,
              left: `${guideCardPosition?.left ?? 24}px`,
            }}
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Boundless quick guide"
          >
            <div className="guide-step-meta">
              Step {guideStepIndex + 1} / {GUIDE_STEPS.length}
            </div>
            <div className="guide-title">{GUIDE_STEPS[guideStepIndex].title}</div>
            <div className="guide-summary">{GUIDE_STEPS[guideStepIndex].summary}</div>
            <div className="guide-detail">{GUIDE_STEPS[guideStepIndex].detail}</div>
            <div className="guide-actions">
              <button
                type="button"
                className="action-button neutral"
                onClick={() => closeGuide(false)}
              >
                Close
              </button>
              <button
                type="button"
                className="action-button neutral"
                onClick={() => setGuideStepIndex((prev) => Math.max(0, prev - 1))}
                disabled={guideStepIndex === 0}
              >
                Back
              </button>
              <button
                type="button"
                className="action-button neutral"
                onClick={() => closeGuide(true)}
              >
                Skip
              </button>
              <button
                type="button"
                className="action-button primary"
                onClick={nextGuideStep}
              >
                {guideStepIndex === GUIDE_STEPS.length - 1 ? 'Finish' : 'Next'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
