'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { createPublicClient, createWalletClient, custom, formatUnits, http, isAddress, parseUnits } from 'viem';
import type { Address } from 'viem';
import { xLayer } from 'viem/chains';
import { TopWalletConnect } from '@/components/top-wallet-connect';
import { boundlessVaultAbi } from '@/lib/boundless-vault-abi';

const CONNECTED_WALLET_STORAGE_KEY = 'trust-leases.connected-wallet';
const ZERO_ADDRESS = '0x0000000000000000000000000000000000000000';
const DEMO_DEFAULT_RECEIVER = '0x3b388c85B745FbDFdc8204878A77192de7C1767D';
const DEMO_FALLBACK_LEASE_ID = 'lease_a8c4b164-9347-4792-8fba-a3d0539a9e3f';
const TOKEN_PRESETS: TokenPreset[] = [
  { key: 'USDT0', label: 'USDT0 (6)', address: '0x779ded0c9e1022225f8e0630b35a9b54be713736', decimals: '6' },
  { key: 'USDC', label: 'USDC (6)', address: '0x74b7f16337b8972027f6196a17a631ac6de26d22', decimals: '6' },
  { key: 'WOKB', label: 'WOKB (18)', address: '0xe538905cf8410324e03a5a23c1c177a474d59b2b', decimals: '18' },
];
const CONTROLLER_READ_ABI = [
  {
    type: 'function',
    name: 'getActiveLeaseByConsumer',
    stateMutability: 'view',
    inputs: [{ name: 'consumerName', type: 'string' }],
    outputs: [
      { name: 'exists', type: 'bool' },
      { name: 'leaseId', type: 'string' },
      { name: 'wallet', type: 'address' },
      { name: 'consumerName_', type: 'string' },
      { name: 'baseAsset', type: 'string' },
      { name: 'issuedAt', type: 'uint64' },
      { name: 'expiresAt', type: 'uint64' },
      { name: 'status', type: 'uint8' },
      { name: 'perTxUsd6', type: 'uint128' },
      { name: 'dailyBudgetUsd6', type: 'uint128' },
      { name: 'spentTodayUsd6', type: 'uint128' },
      { name: 'spentWindowStartedAt', type: 'uint64' },
      { name: 'remainingDailyUsd6', type: 'uint128' },
      { name: 'policyHash', type: 'bytes32' },
      { name: 'notesHash', type: 'bytes32' },
    ],
  },
] as const;

type MemberTestPageProps = {
  vaultAddress: string | null;
  defaultLeaseId: string | null;
  controllerAddress: string | null;
  consumerName: string;
  rpcUrl: string;
};

type TokenPreset = {
  key: string;
  label: string;
  address: string;
  decimals: string;
};

type BudgetState = {
  exists: boolean;
  enabled: boolean;
  perTxUsd6: bigint;
  dailyBudgetUsd6: bigint;
  spentTodayUsd6: bigint;
  remainingDailyUsd6: bigint;
};

type EthereumProvider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
};

function usd6ToText(value: bigint): string {
  return formatUnits(value, 6);
}

function toUsd6(value: string): bigint {
  return parseUnits(value || '0', 6);
}

function buildRequestId(prefix: 'ok' | 'fail'): string {
  return `demo_${prefix}_${Date.now()}`;
}

function errText(err: unknown): string {
  if (err instanceof Error) {
    return err.message;
  }
  return String(err);
}

export function MemberTestPage({ vaultAddress, defaultLeaseId, controllerAddress, consumerName, rpcUrl }: MemberTestPageProps) {
  const [walletAddress, setWalletAddress] = useState<string>('');
  const [leaseId, setLeaseId] = useState(defaultLeaseId ?? DEMO_FALLBACK_LEASE_ID);
  const [tokenPreset, setTokenPreset] = useState<string>('USDT0');
  const [tokenAddress, setTokenAddress] = useState('');
  const [receiver, setReceiver] = useState(DEMO_DEFAULT_RECEIVER);
  const [tokenAmount, setTokenAmount] = useState('0.01');
  const [tokenDecimals, setTokenDecimals] = useState('6');
  const [manualSpentUsd, setManualSpentUsd] = useState('1');
  const [budgetState, setBudgetState] = useState<BudgetState | null>(null);
  const [loadingBudget, setLoadingBudget] = useState(false);
  const [running, setRunning] = useState<'ok' | 'fail' | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [syncingLease, setSyncingLease] = useState(false);
  const [liveLeaseId, setLiveLeaseId] = useState<string | null>(null);
  const [vaultLeaseId, setVaultLeaseId] = useState<string | null>(null);

  const vault = useMemo(() => (vaultAddress && isAddress(vaultAddress) ? (vaultAddress as Address) : null), [vaultAddress]);
  const controller = useMemo(
    () => (controllerAddress && isAddress(controllerAddress) ? (controllerAddress as Address) : null),
    [controllerAddress],
  );
  const ethereum = (typeof window !== 'undefined' ? (window as Window & { ethereum?: EthereumProvider }).ethereum : undefined);
  const hasVault = Boolean(vault);
  const hasConnectedMember = Boolean(walletAddress && isAddress(walletAddress));
  const hasLeaseId = leaseId.trim().length > 0;
  const hasToken = isAddress(tokenAddress);
  const hasReceiver = isAddress(receiver);
  const memberPolicyReady = Boolean(budgetState?.exists && budgetState.enabled);
  const leaseSynced = Boolean(liveLeaseId && leaseId.trim() === liveLeaseId);
  const vaultLeaseSynced = Boolean(vaultLeaseId && leaseId.trim() === vaultLeaseId);
  const demoReady = hasVault && hasConnectedMember && hasLeaseId && hasToken && hasReceiver && memberPolicyReady && leaseSynced && vaultLeaseSynced;

  useEffect(() => {
    const preset = TOKEN_PRESETS.find((item) => item.key === tokenPreset);
    if (!preset) {
      return;
    }
    setTokenAddress(preset.address);
    setTokenDecimals(preset.decimals);
  }, [tokenPreset]);

  useEffect(() => {
    if (!defaultLeaseId && !leaseId) {
      setLeaseId(DEMO_FALLBACK_LEASE_ID);
    }
  }, [defaultLeaseId, leaseId]);

  async function syncLeaseFromChain() {
    if (!controller) {
      return;
    }
    setSyncingLease(true);
    try {
      const client = createPublicClient({
        chain: xLayer,
        transport: http(rpcUrl),
      });
      const row = await client.readContract({
        address: controller,
        abi: CONTROLLER_READ_ABI,
        functionName: 'getActiveLeaseByConsumer',
        args: [consumerName],
      }) as readonly [boolean, string, Address, string, string, bigint, bigint, number, bigint, bigint, bigint, bigint, bigint, `0x${string}`, `0x${string}`];

      const exists = row[0];
      const onchainLeaseId = row[1];
      if (exists && onchainLeaseId) {
        setLiveLeaseId(onchainLeaseId);
        setLeaseId(onchainLeaseId);
      }

      if (vault) {
        const activeLease = await client.readContract({
          address: vault,
          abi: boundlessVaultAbi,
          functionName: 'activeLeaseId',
          args: [],
        }) as string;
        setVaultLeaseId(activeLease || null);
      }
    } catch {
      // no-op: keep current fallback lease id
    } finally {
      setSyncingLease(false);
    }
  }

  useEffect(() => {
    void syncLeaseFromChain();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [controller, consumerName, rpcUrl]);

  useEffect(() => {
    const cached = window.localStorage.getItem(CONNECTED_WALLET_STORAGE_KEY);
    if (cached && isAddress(cached)) {
      setWalletAddress(cached);
    }
    const onWalletUpdate = (event: Event) => {
      const detail = (event as CustomEvent<{ address?: string }>).detail;
      if (detail?.address && isAddress(detail.address)) {
        setWalletAddress(detail.address);
      }
    };
    window.addEventListener('trust-leases-wallet-updated', onWalletUpdate);
    return () => window.removeEventListener('trust-leases-wallet-updated', onWalletUpdate);
  }, []);

  async function refreshBudget() {
    setError(null);
    setResult(null);
    setPendingMessage('Refreshing member budget from chain…');
    if (!vault) {
      setError('Missing BOUNDLESS_VAULT_ADDRESS.');
      return;
    }
    if (!walletAddress || !isAddress(walletAddress)) {
      setError('Connect member wallet first.');
      return;
    }
    setLoadingBudget(true);
    try {
      const client = createPublicClient({
        chain: xLayer,
        transport: http(rpcUrl),
      });
      const row = await client.readContract({
        address: vault,
        abi: boundlessVaultAbi,
        functionName: 'memberBudgetState',
        args: [walletAddress as Address],
      }) as readonly [boolean, boolean, bigint, bigint, bigint, bigint];

      const state: BudgetState = {
        exists: row[0],
        enabled: row[1],
        perTxUsd6: row[2],
        dailyBudgetUsd6: row[3],
        spentTodayUsd6: row[4],
        remainingDailyUsd6: row[5],
      };
      setBudgetState(state);

      if (state.perTxUsd6 > BigInt(0)) {
        setManualSpentUsd(
          usd6ToText(state.perTxUsd6 > BigInt(1_000_000) ? BigInt(1_000_000) : state.perTxUsd6),
        );
      }
    } catch (err) {
      setError(errText(err));
    } finally {
      setLoadingBudget(false);
      setPendingMessage(null);
    }
  }

  async function runTransfer(mode: 'ok' | 'fail') {
    setError(null);
    setResult(null);
    if (!ethereum) {
      setError('No browser wallet found.');
      return;
    }
    if (!vault) {
      setError('Vault address not configured.');
      return;
    }
    if (!leaseId.trim()) {
      setError('Lease ID is required.');
      return;
    }
    if (!isAddress(tokenAddress)) {
      setError('Token address is invalid.');
      return;
    }
    if (!isAddress(receiver)) {
      setError('Receiver address is invalid.');
      return;
    }
    if (!vaultLeaseSynced) {
      setError('Vault lease is out of sync. Click Sync Live Lease or Save Rule again from App.');
      return;
    }
    if (!walletAddress || !isAddress(walletAddress)) {
      setError('Connect member wallet first.');
      return;
    }

    const decimals = Number(tokenDecimals);
    if (!Number.isFinite(decimals) || decimals < 0 || decimals > 18) {
      setError('Token decimals must be 0-18.');
      return;
    }

    let spentUsd6: bigint;
    if (mode === 'ok') {
      const cap = budgetState?.perTxUsd6 ?? toUsd6(manualSpentUsd);
      if (cap <= BigInt(0)) {
        setError('Per-tx budget is zero. Refresh budget or set member policy first.');
        return;
      }
      spentUsd6 = cap > BigInt(1_000_000) ? BigInt(1_000_000) : cap;
    } else {
      const cap = budgetState?.perTxUsd6 ?? toUsd6(manualSpentUsd);
      spentUsd6 = cap + BigInt(1);
    }

    try {
      setRunning(mode);
      setPendingMessage(mode === 'ok' ? 'Submitting budget-pass transaction…' : 'Submitting over-budget transaction…');
      const amount = parseUnits(tokenAmount, decimals);
      const publicClient = createPublicClient({
        chain: xLayer,
        transport: http(rpcUrl),
      });
      const walletClient = createWalletClient({
        chain: xLayer,
        transport: custom(ethereum),
      });
      const accounts = await walletClient.getAddresses();
      if (!accounts[0] || accounts[0].toLowerCase() !== walletAddress.toLowerCase()) {
        throw new Error('Current wallet account does not match connected member wallet.');
      }

      const { request } = await publicClient.simulateContract({
        account: accounts[0],
        address: vault,
        abi: boundlessVaultAbi,
        functionName: 'executeTransfer',
        args: [
          buildRequestId(mode),
          leaseId.trim(),
          tokenAddress as Address,
          receiver as Address,
          amount,
          spentUsd6,
        ],
      });
      const hash = await walletClient.writeContract(request);

      await publicClient.waitForTransactionReceipt({ hash });
      if (mode === 'ok') {
        setResult(`Budget-pass success: ${hash}`);
      } else {
        setError(`Over-budget should fail, but transaction succeeded: ${hash}`);
      }
      await refreshBudget();
    } catch (err) {
      if (mode === 'fail') {
        setError(`Over-budget blocked as expected: ${errText(err)}`);
      } else {
        setError(errText(err));
      }
    } finally {
      setRunning(null);
      setPendingMessage(null);
    }
  }

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <div className="logo-icon">
            <img src="/boundless-mark.svg" alt="Boundless mark" />
          </div>
          <div>
            <div className="logo-text">Boundless</div>
            <div className="logo-sub">Member Budget Test</div>
          </div>
        </div>
        <div className="header-right">
          <nav className="nav">
            <Link href="/" className="nav-link">Home</Link>
            <Link href="/submission" className="nav-link">App</Link>
            <Link href="/proof" className="nav-link">Proof</Link>
            <Link href="/member-test" className="nav-link active">Member Test</Link>
          </nav>
          <TopWalletConnect />
        </div>
      </header>

      <main className="dashboard-shell">
        <div className="dashboard-main">
          <div className="card">
            <div className="card-header">
              <h2>Judge Quick Guide</h2>
            </div>
            <p className="section-copy">
              This page proves one thing: member spending is enforced by onchain budget rules.
            </p>
            <div className="sidebar-meta">
              <div className="meta-item"><span className="meta-label">Step 1</span><span className="meta-value">Click <strong>Refresh Member Budget</strong></span></div>
              <div className="meta-item"><span className="meta-label">Step 2</span><span className="meta-value">Fill token + receiver</span></div>
              <div className="meta-item"><span className="meta-label">Step 3</span><span className="meta-value">Run <strong>Budget-Pass</strong> (should succeed)</span></div>
              <div className="meta-item"><span className="meta-label">Step 4</span><span className="meta-value">Run <strong>Over-Budget</strong> (should fail)</span></div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h2>Ready Checks</h2>
            </div>
            <div className="console-meta">
              <span className={`pill ${hasVault ? 'ok' : 'warn'}`}>Vault {hasVault ? 'Ready' : 'Missing'}</span>
              <span className={`pill ${hasConnectedMember ? 'ok' : 'warn'}`}>Member Wallet {hasConnectedMember ? 'Connected' : 'Not Connected'}</span>
              <span className={`pill ${hasLeaseId ? 'ok' : 'warn'}`}>Lease ID {hasLeaseId ? 'Set' : 'Missing'}</span>
              <span className={`pill ${leaseSynced ? 'ok' : 'warn'}`}>Lease {leaseSynced ? 'Synced' : 'Out of Sync'}</span>
              <span className={`pill ${vaultLeaseSynced ? 'ok' : 'warn'}`}>Vault Lease {vaultLeaseSynced ? 'Synced' : 'Out of Sync'}</span>
              <span className={`pill ${memberPolicyReady ? 'ok' : 'warn'}`}>Member Policy {memberPolicyReady ? 'Ready' : 'Not Loaded'}</span>
              <span className={`pill ${hasToken ? 'ok' : 'warn'}`}>Token {hasToken ? 'Valid' : 'Invalid'}</span>
              <span className={`pill ${hasReceiver ? 'ok' : 'warn'}`}>Receiver {hasReceiver ? 'Valid' : 'Missing'}</span>
            </div>
            <p className="section-copy mono">
              Vault: {vaultAddress ?? 'not set'} | Connected member: {walletAddress || 'not connected'} | Demo: {demoReady ? 'Ready' : 'Not Ready'}
            </p>
            {liveLeaseId ? (
              <p className="section-copy mono">
                Live lease from chain: {liveLeaseId}
              </p>
            ) : null}
            {vaultLeaseId ? (
              <p className="section-copy mono">
                Vault lease context: {vaultLeaseId}
              </p>
            ) : null}
          </div>

          <div className="card">
            <div className="card-header">
              <h2>Execution Inputs</h2>
            </div>
            <div className="console-form">
              <div className="form-row">
                <div className="form-field">
                  <label htmlFor="token-preset" className="note-label">Token Preset</label>
                  <select
                    id="token-preset"
                    className="note-input"
                    value={tokenPreset}
                    onChange={(e) => setTokenPreset(e.target.value)}
                  >
                    {TOKEN_PRESETS.map((item) => (
                      <option key={item.key} value={item.key}>{item.label}</option>
                    ))}
                    <option value="custom">Custom (manual)</option>
                  </select>
                </div>
                <div className="form-field">
                  <label htmlFor="lease-id" className="note-label">Lease ID</label>
                  <input id="lease-id" className="note-input mono" value={leaseId} onChange={(e) => setLeaseId(e.target.value)} />
                  <div style={{ marginTop: 8 }}>
                    <button
                      type="button"
                      className="action-button neutral"
                      onClick={syncLeaseFromChain}
                      disabled={syncingLease || !controller}
                    >
                      {syncingLease ? 'Syncing Live Lease…' : 'Sync Live Lease'}
                    </button>
                  </div>
                </div>
                <div className="form-field">
                  <label htmlFor="token" className="note-label">Token Address</label>
                  <input
                    id="token"
                    className="note-input mono"
                    value={tokenAddress}
                    onChange={(e) => {
                      setTokenAddress(e.target.value);
                      if (tokenPreset !== 'custom') {
                        setTokenPreset('custom');
                      }
                    }}
                    placeholder={ZERO_ADDRESS}
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-field">
                  <label htmlFor="receiver" className="note-label">Receiver</label>
                  <input id="receiver" className="note-input mono" value={receiver} onChange={(e) => setReceiver(e.target.value)} placeholder="0x... receiver wallet" />
                </div>
                <div className="form-field">
                  <label htmlFor="amount" className="note-label">Token Amount</label>
                  <input id="amount" className="note-input" value={tokenAmount} onChange={(e) => setTokenAmount(e.target.value)} />
                </div>
                <div className="form-field">
                  <label htmlFor="decimals" className="note-label">Token Decimals</label>
                  <input id="decimals" className="note-input" value={tokenDecimals} onChange={(e) => setTokenDecimals(e.target.value)} />
                </div>
              </div>
              <div className="form-row">
                <div className="form-field">
                  <label htmlFor="manual-spent" className="note-label">Fallback Per-Tx USD</label>
                  <input id="manual-spent" className="note-input" value={manualSpentUsd} onChange={(e) => setManualSpentUsd(e.target.value)} />
                </div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h2>Member Budget State</h2>
            </div>
            <div className="console-actions">
              <button type="button" className="action-button neutral" onClick={refreshBudget} disabled={loadingBudget}>
                {loadingBudget ? 'Refreshing...' : 'Refresh Member Budget'}
              </button>
            </div>
            {budgetState ? (
              <div className="sidebar-meta">
                <div className="meta-item"><span className="meta-label">Exists</span><span className="meta-value">{String(budgetState.exists)}</span></div>
                <div className="meta-item"><span className="meta-label">Enabled</span><span className="meta-value">{String(budgetState.enabled)}</span></div>
                <div className="meta-item"><span className="meta-label">Per-Tx</span><span className="meta-value">${usd6ToText(budgetState.perTxUsd6)}</span></div>
                <div className="meta-item"><span className="meta-label">Daily</span><span className="meta-value">${usd6ToText(budgetState.dailyBudgetUsd6)}</span></div>
                <div className="meta-item"><span className="meta-label">Spent Today</span><span className="meta-value">${usd6ToText(budgetState.spentTodayUsd6)}</span></div>
                <div className="meta-item"><span className="meta-label">Remaining</span><span className="meta-value">${usd6ToText(budgetState.remainingDailyUsd6)}</span></div>
              </div>
            ) : (
              <p className="section-copy">No budget loaded yet.</p>
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <h2>One-Click Demo Actions</h2>
            </div>
            {running ? (
              <div className="response-banner pending">
                {running === 'ok' ? 'Running budget-pass flow…' : 'Running over-budget flow…'} Please approve signature and wait for receipt.
              </div>
            ) : null}
            <div className="console-actions">
              <button type="button" className="action-button primary" onClick={() => runTransfer('ok')} disabled={running !== null || !demoReady}>
                {running === 'ok' ? 'Running Budget-Pass…' : '1) Budget-Pass (Should Succeed)'}
              </button>
              <button type="button" className="action-button warn" onClick={() => runTransfer('fail')} disabled={running !== null || !demoReady}>
                {running === 'fail' ? 'Running Over-Budget…' : '2) Over-Budget (Should Fail)'}
              </button>
            </div>
            <p className="section-copy">
              Pass path sends <code>spentUsd6</code> within member policy. Fail path sends <code>perTx + 1</code> to force revert.
            </p>
            <p className="section-copy">
              Expected result: first action returns a tx hash. second action returns a revert message.
            </p>
          </div>

          {pendingMessage ? <div className="response-banner pending">{pendingMessage}</div> : null}
          {result ? <div className="response-banner success">{result}</div> : null}
          {error ? <div className="response-banner error">{error}</div> : null}
        </div>
      </main>
    </div>
  );
}
