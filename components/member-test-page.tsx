'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { createPublicClient, createWalletClient, custom, formatUnits, http, isAddress, parseUnits } from 'viem';
import type { Address } from 'viem';
import { KITE_TESTNET_USDT_ADDRESS, kiteTestnetChain } from '@/lib/chain-config';
import { TopWalletConnect } from '@/components/top-wallet-connect';
import { boundlessVaultAbi } from '@/lib/boundless-vault-abi';

const CONNECTED_WALLET_STORAGE_KEY = 'trust-leases.connected-wallet';
const ZERO_ADDRESS = '0x0000000000000000000000000000000000000000';
const DEMO_DEFAULT_RECEIVER = '0x3b388c85B745FbDFdc8204878A77192de7C1767D';
const DEMO_FALLBACK_LEASE_ID = 'lease_a8c4b164-9347-4792-8fba-a3d0539a9e3f';
const LOCAL_DEMO_X402_PATH = '/api/demo-x402-weather';
const REMOTE_DEMO_X402_URL = 'https://x402.dev.gokite.ai/api/weather';
const LOCAL_DEMO_X_PAYMENT = 'demo-paid';
const TOKEN_PRESETS: TokenPreset[] = [
  { key: 'USDT', label: 'Test USDT (6)', address: KITE_TESTNET_USDT_ADDRESS, decimals: '6' },
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

type KitePassportSession = {
  sessionId: string;
  payerAddress: string;
  agentName?: string;
  agentId?: string;
  network: 'kite-testnet' | 'kite-mainnet';
  createdAt?: string;
  expiresAt: string;
  dailyBudgetUsd: number;
  spentUsd: number;
  remainingBudgetUsd: number;
  portalUrl?: string;
  notes?: string;
};

type X402Challenge = {
  error?: string;
  accepts?: Array<{
    scheme?: string;
    network?: string;
    maxAmountRequired?: string;
    resource?: string;
    description?: string;
    payTo?: string;
    asset?: string;
    merchantName?: string;
  }>;
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
  const [tokenPreset, setTokenPreset] = useState<string>('USDT');
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
  const [passportSession, setPassportSession] = useState<KitePassportSession | null>(null);
  const [sessionIdInput, setSessionIdInput] = useState('');
  const [sessionPayerInput, setSessionPayerInput] = useState('');
  const [sessionAgentNameInput, setSessionAgentNameInput] = useState('Boundless by Miraix AI');
  const [sessionAgentIdInput, setSessionAgentIdInput] = useState('');
  const [sessionBudgetInput, setSessionBudgetInput] = useState('5');
  const [sessionSpentInput, setSessionSpentInput] = useState('0');
  const [sessionExpiryInput, setSessionExpiryInput] = useState('');
  const [sessionPortalUrlInput, setSessionPortalUrlInput] = useState('https://portal.gokite.ai');
  const [sessionNotesInput, setSessionNotesInput] = useState('Created in Kite Portal and enforced by Boundless before x402 payment.');
  const [savingSession, setSavingSession] = useState(false);
  const [serviceUrl, setServiceUrl] = useState('');
  const [serviceLocation, setServiceLocation] = useState('Singapore');
  const [serviceUnits, setServiceUnits] = useState<'metric' | 'imperial'>('metric');
  const [serviceNotionalUsd, setServiceNotionalUsd] = useState('1');
  const [serviceReason, setServiceReason] = useState('Boundless weather fetch inside the active Passport session.');
  const [xPaymentHeader, setXPaymentHeader] = useState('');
  const [challenge, setChallenge] = useState<X402Challenge | null>(null);
  const [proofLink, setProofLink] = useState<string | null>(null);
  const [paymentPreview, setPaymentPreview] = useState<string | null>(null);
  const [runningPayment, setRunningPayment] = useState<'prepare' | 'pay' | null>(null);

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
  const localDemoServiceEnabled = serviceUrl.includes(LOCAL_DEMO_X402_PATH);

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

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    if (!serviceUrl) {
      setServiceUrl(`${window.location.origin}${LOCAL_DEMO_X402_PATH}`);
    }
  }, [serviceUrl]);

  async function syncLeaseFromChain() {
    if (!controller) {
      return;
    }
    setSyncingLease(true);
    try {
        const client = createPublicClient({
        chain: kiteTestnetChain,
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
      // no-op: keep current fallback policy id
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

  async function loadPassportSession() {
    try {
      const response = await fetch('/api/passport-session', { cache: 'no-store' });
      const payload = await response.json() as { session?: KitePassportSession | null };
      if (!payload.session) {
        return;
      }
      setPassportSession(payload.session);
      setSessionIdInput(payload.session.sessionId);
      setSessionPayerInput(payload.session.payerAddress);
      setSessionAgentNameInput(payload.session.agentName ?? 'Boundless by Miraix AI');
      setSessionAgentIdInput(payload.session.agentId ?? '');
      setSessionBudgetInput(String(payload.session.dailyBudgetUsd));
      setSessionSpentInput(String(payload.session.spentUsd));
      setSessionExpiryInput(payload.session.expiresAt);
      setSessionPortalUrlInput(payload.session.portalUrl ?? 'https://portal.gokite.ai');
      setSessionNotesInput(payload.session.notes ?? 'Created in Kite Portal and enforced by Boundless before x402 payment.');
    } catch {
      // ignore local session bootstrap failure
    }
  }

  useEffect(() => {
    void loadPassportSession();
  }, []);

  useEffect(() => {
    if (!sessionExpiryInput) {
      setSessionExpiryInput(new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString());
    }
  }, [sessionExpiryInput]);

  async function savePassportSession() {
    setSavingSession(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch('/api/passport-session', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          sessionId: sessionIdInput,
          payerAddress: sessionPayerInput,
          agentName: sessionAgentNameInput,
          agentId: sessionAgentIdInput,
          network: 'kite-testnet',
          expiresAt: sessionExpiryInput,
          dailyBudgetUsd: Number(sessionBudgetInput),
          spentUsd: Number(sessionSpentInput),
          portalUrl: sessionPortalUrlInput,
          notes: sessionNotesInput,
        }),
      });
      const payload = await response.json() as { ok?: boolean; error?: string; session?: KitePassportSession };
      if (!response.ok || !payload.session) {
        throw new Error(payload.error || 'Failed to save Kite Passport session.');
      }
      setPassportSession(payload.session);
      setResult(`Saved Kite Passport session ${payload.session.sessionId}.`);
    } catch (err) {
      setError(errText(err));
    } finally {
      setSavingSession(false);
    }
  }

  async function runX402Payment(mode: 'prepare' | 'pay') {
    setError(null);
    setResult(null);
    setProofLink(null);
    setRunningPayment(mode);
    try {
      const response = await fetch('/api/x402-payment', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          serviceUrl,
          location: serviceLocation,
          units: serviceUnits,
          notionalUsd: Number(serviceNotionalUsd),
          reason: serviceReason,
          xPayment: mode === 'pay' ? xPaymentHeader : undefined,
        }),
      });
      const payload = await response.json() as {
        ok?: boolean;
        blocked?: boolean;
        paymentRequired?: boolean;
        requestId?: string;
        proofUrl?: string;
        rationale?: string;
        challenge?: X402Challenge;
        response?: unknown;
        error?: string;
        packet?: { execution?: { note?: string } };
      };

      if (payload.paymentRequired) {
        setChallenge((payload.challenge as X402Challenge) ?? null);
        if (localDemoServiceEnabled && !xPaymentHeader.trim()) {
          setXPaymentHeader(LOCAL_DEMO_X_PAYMENT);
        }
        setResult(
          localDemoServiceEnabled
            ? `Policy approved. Local demo x402 challenge received for request ${payload.requestId}. The X-PAYMENT field has been prefilled for recording.`
            : `Policy approved. x402 challenge received for request ${payload.requestId}. Paste a Kite Passport X-PAYMENT header and run Complete Paid Request.`,
        );
        return;
      }

      if (!response.ok || !payload.ok) {
        setChallenge(null);
        setProofLink(payload.proofUrl ?? null);
        setPaymentPreview(payload.response ? JSON.stringify(payload.response, null, 2) : null);
        throw new Error(payload.error || payload.rationale || 'x402 payment flow failed.');
      }

      setChallenge(null);
      setProofLink(payload.proofUrl ?? null);
      setPaymentPreview(payload.response ? JSON.stringify(payload.response, null, 2) : null);
      setResult(`Paid x402 request completed and proof written for ${payload.requestId}.`);
      await loadPassportSession();
    } catch (err) {
      setError(errText(err));
    } finally {
      setRunningPayment(null);
    }
  }

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
        chain: kiteTestnetChain,
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
      setError('Policy ID is required.');
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
      setError('Vault policy is out of sync. Click Sync Live Policy or Save Policy again from App.');
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
        chain: kiteTestnetChain,
        transport: http(rpcUrl),
      });
      const walletClient = createWalletClient({
        chain: kiteTestnetChain,
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
            <div className="logo-sub">Passport + Member Budget Test</div>
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
              This page proves one thing: once Kite Passport gives the agent delegated payment permission, Boundless can still enforce member spending limits onchain.
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
              <h2>Kite Passport Session Boundary</h2>
            </div>
            <p className="section-copy">
              Create the Passport session in Kite Portal first, then mirror the live session boundary here. Boundless uses this boundary before it allows any real x402 payment to leave the session.
            </p>
            <div className="console-form">
              <div className="form-row">
                <div className="form-field">
                  <label htmlFor="session-id" className="note-label">Session ID</label>
                  <input id="session-id" className="note-input mono" value={sessionIdInput} onChange={(e) => setSessionIdInput(e.target.value)} placeholder="sess_..." />
                </div>
                <div className="form-field">
                  <label htmlFor="session-payer" className="note-label">Payer Address</label>
                  <input id="session-payer" className="note-input mono" value={sessionPayerInput} onChange={(e) => setSessionPayerInput(e.target.value)} placeholder="0x..." />
                </div>
              </div>
              <div className="form-row">
                <div className="form-field">
                  <label htmlFor="session-budget" className="note-label">Session Budget USD</label>
                  <input id="session-budget" className="note-input" value={sessionBudgetInput} onChange={(e) => setSessionBudgetInput(e.target.value)} />
                </div>
                <div className="form-field">
                  <label htmlFor="session-spent" className="note-label">Session Spent USD</label>
                  <input id="session-spent" className="note-input" value={sessionSpentInput} onChange={(e) => setSessionSpentInput(e.target.value)} />
                </div>
                <div className="form-field">
                  <label htmlFor="session-expiry" className="note-label">Session Expiry</label>
                  <input id="session-expiry" className="note-input mono" value={sessionExpiryInput} onChange={(e) => setSessionExpiryInput(e.target.value)} />
                </div>
              </div>
              <div className="form-row">
                <div className="form-field">
                  <label htmlFor="session-agent-name" className="note-label">Agent Name</label>
                  <input id="session-agent-name" className="note-input" value={sessionAgentNameInput} onChange={(e) => setSessionAgentNameInput(e.target.value)} />
                </div>
                <div className="form-field">
                  <label htmlFor="session-agent-id" className="note-label">Agent ID</label>
                  <input id="session-agent-id" className="note-input mono" value={sessionAgentIdInput} onChange={(e) => setSessionAgentIdInput(e.target.value)} placeholder="optional" />
                </div>
                <div className="form-field">
                  <label htmlFor="session-portal-url" className="note-label">Portal URL</label>
                  <input id="session-portal-url" className="note-input" value={sessionPortalUrlInput} onChange={(e) => setSessionPortalUrlInput(e.target.value)} />
                </div>
              </div>
              <div className="form-row">
                <div className="form-field">
                  <label htmlFor="session-notes" className="note-label">Notes</label>
                  <input id="session-notes" className="note-input" value={sessionNotesInput} onChange={(e) => setSessionNotesInput(e.target.value)} />
                </div>
              </div>
            </div>
            <div className="console-actions">
              <button type="button" className="action-button primary" onClick={savePassportSession} disabled={savingSession}>
                {savingSession ? 'Saving Session…' : 'Save Session Boundary'}
              </button>
            </div>
            {passportSession ? (
              <div className="sidebar-meta">
                <div className="meta-item"><span className="meta-label">Saved Session</span><span className="meta-value mono">{passportSession.sessionId}</span></div>
                <div className="meta-item"><span className="meta-label">Remaining</span><span className="meta-value">${passportSession.remainingBudgetUsd.toFixed(2)}</span></div>
                <div className="meta-item"><span className="meta-label">Network</span><span className="meta-value">{passportSession.network}</span></div>
              </div>
            ) : (
              <p className="section-copy">No Passport session boundary saved yet.</p>
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <h2>Real x402 Payment Check</h2>
            </div>
            <p className="section-copy">
              Boundless can run against a real external x402 service or the built-in local demo resource. For recording, use the local demo service. For Passport validation, switch back to the external Kite-aligned endpoint.
            </p>
            <div className="console-form">
              <div className="console-actions">
                <button
                  type="button"
                  className="action-button neutral"
                  onClick={() => {
                    if (typeof window !== 'undefined') {
                      setServiceUrl(`${window.location.origin}${LOCAL_DEMO_X402_PATH}`);
                    }
                  }}
                >
                  Use Local Demo x402
                </button>
                <button
                  type="button"
                  className="action-button neutral"
                  onClick={() => setServiceUrl(REMOTE_DEMO_X402_URL)}
                >
                  Use External Kite x402
                </button>
              </div>
              <div className="form-row">
                <div className="form-field">
                  <label htmlFor="service-url" className="note-label">x402 Service URL</label>
                  <input id="service-url" className="note-input mono" value={serviceUrl} onChange={(e) => setServiceUrl(e.target.value)} />
                </div>
                <div className="form-field">
                  <label htmlFor="service-location" className="note-label">Location</label>
                  <input id="service-location" className="note-input" value={serviceLocation} onChange={(e) => setServiceLocation(e.target.value)} />
                </div>
                <div className="form-field">
                  <label htmlFor="service-units" className="note-label">Units</label>
                  <select id="service-units" className="note-input" value={serviceUnits} onChange={(e) => setServiceUnits(e.target.value as 'metric' | 'imperial')}>
                    <option value="metric">metric</option>
                    <option value="imperial">imperial</option>
                  </select>
                </div>
              </div>
              <div className="form-row">
                <div className="form-field">
                  <label htmlFor="service-notional" className="note-label">Expected Spend USD</label>
                  <input id="service-notional" className="note-input" value={serviceNotionalUsd} onChange={(e) => setServiceNotionalUsd(e.target.value)} />
                </div>
                <div className="form-field">
                  <label htmlFor="service-reason" className="note-label">Reason</label>
                  <input id="service-reason" className="note-input" value={serviceReason} onChange={(e) => setServiceReason(e.target.value)} />
                </div>
              </div>
              <div className="form-row">
                <div className="form-field">
                  <label htmlFor="x-payment" className="note-label">Kite X-PAYMENT Header</label>
                  <textarea
                    id="x-payment"
                    className="note-input mono"
                    rows={4}
                    value={xPaymentHeader}
                    onChange={(e) => setXPaymentHeader(e.target.value)}
                    placeholder={
                      localDemoServiceEnabled
                        ? LOCAL_DEMO_X_PAYMENT
                        : 'Paste the X-PAYMENT header returned by Kite Passport / MCP after approving the x402 challenge.'
                    }
                  />
                </div>
              </div>
            </div>
            {localDemoServiceEnabled ? (
              <p className="section-copy">
                Local recording mode is active. The built-in demo x402 resource returns a real 402-style challenge and accepts <code>{LOCAL_DEMO_X_PAYMENT}</code> for the paid step.
              </p>
            ) : (
              <p className="section-copy">
                External mode is active. Prepare the request first, then use Kite Passport / MCP to produce the final <code>X-PAYMENT</code> header.
              </p>
            )}
            <div className="console-actions">
              <button type="button" className="action-button neutral" onClick={() => runX402Payment('prepare')} disabled={runningPayment !== null || !passportSession}>
                {runningPayment === 'prepare' ? 'Preparing…' : '3) Prepare x402 Request'}
              </button>
              <button type="button" className="action-button primary" onClick={() => runX402Payment('pay')} disabled={runningPayment !== null || !passportSession || !xPaymentHeader.trim()}>
                {runningPayment === 'pay' ? 'Completing Payment…' : '4) Complete Paid Request'}
              </button>
            </div>
            {challenge ? (
              <div className="sidebar-meta">
                <div className="meta-item"><span className="meta-label">Challenge</span><span className="meta-value">{challenge.error ?? '402 payment challenge returned'}</span></div>
                <div className="meta-item"><span className="meta-label">Merchant</span><span className="meta-value">{challenge.accepts?.[0]?.merchantName ?? 'n/a'}</span></div>
                <div className="meta-item"><span className="meta-label">Max Amount</span><span className="meta-value mono">{challenge.accepts?.[0]?.maxAmountRequired ?? 'n/a'}</span></div>
                <div className="meta-item"><span className="meta-label">Pay To</span><span className="meta-value mono">{challenge.accepts?.[0]?.payTo ?? 'n/a'}</span></div>
              </div>
            ) : null}
            {proofLink ? (
              <p className="section-copy">
                Proof written: <Link href={proofLink} className="nav-link active">Open latest payment proof</Link>
              </p>
            ) : null}
            {paymentPreview ? (
              <pre className="note-input mono" style={{ whiteSpace: 'pre-wrap', overflowX: 'auto' }}>{paymentPreview}</pre>
            ) : null}
          </div>

          <div className="card">
            <div className="card-header">
              <h2>Ready Checks</h2>
            </div>
            <div className="console-meta">
              <span className={`pill ${hasVault ? 'ok' : 'warn'}`}>Vault {hasVault ? 'Ready' : 'Missing'}</span>
              <span className={`pill ${hasConnectedMember ? 'ok' : 'warn'}`}>Member Wallet {hasConnectedMember ? 'Connected' : 'Not Connected'}</span>
                <span className={`pill ${hasLeaseId ? 'ok' : 'warn'}`}>Policy ID {hasLeaseId ? 'Set' : 'Missing'}</span>
              <span className={`pill ${leaseSynced ? 'ok' : 'warn'}`}>Policy {leaseSynced ? 'Synced' : 'Out of Sync'}</span>
              <span className={`pill ${vaultLeaseSynced ? 'ok' : 'warn'}`}>Vault Policy {vaultLeaseSynced ? 'Synced' : 'Out of Sync'}</span>
              <span className={`pill ${memberPolicyReady ? 'ok' : 'warn'}`}>Member Policy {memberPolicyReady ? 'Ready' : 'Not Loaded'}</span>
              <span className={`pill ${hasToken ? 'ok' : 'warn'}`}>Token {hasToken ? 'Valid' : 'Invalid'}</span>
              <span className={`pill ${hasReceiver ? 'ok' : 'warn'}`}>Receiver {hasReceiver ? 'Valid' : 'Missing'}</span>
            </div>
            <p className="section-copy mono">
              Vault: {vaultAddress ?? 'not set'} | Connected member: {walletAddress || 'not connected'} | Demo: {demoReady ? 'Ready' : 'Not Ready'}
            </p>
            {liveLeaseId ? (
              <p className="section-copy mono">
                Live policy from chain: {liveLeaseId}
              </p>
            ) : null}
            {vaultLeaseId ? (
              <p className="section-copy mono">
                Vault policy context: {vaultLeaseId}
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
                  <label htmlFor="lease-id" className="note-label">Policy ID</label>
                  <input id="lease-id" className="note-input mono" value={leaseId} onChange={(e) => setLeaseId(e.target.value)} />
                  <div style={{ marginTop: 8 }}>
                    <button
                      type="button"
                      className="action-button neutral"
                      onClick={syncLeaseFromChain}
                      disabled={syncingLease || !controller}
                    >
                      {syncingLease ? 'Syncing Live Policy…' : 'Sync Live Policy'}
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
