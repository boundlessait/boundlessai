import Link from 'next/link';
import { formatTimestamp, formatUsd, sanitizeProofText, shortHash, titleCase } from '@/lib/format';
import { deriveLeaseState, toneForExecution, toneForOutcome, toneForTrustZone } from '@/lib/runtime';
import type { ProofPacket, RoundArtifactIndexEntry } from '@/lib/types';

type LandingPageProps = {
  packet: ProofPacket | null;
  lease: ProofPacket['lease'] | null;
  currentOperator?: ProofPacket['operator'] | null;
  rounds: RoundArtifactIndexEntry[];
  latestSuccessRound?: RoundArtifactIndexEntry | null;
  latestBlockedRound?: RoundArtifactIndexEntry | null;
  latestSuccessPacket?: ProofPacket | null;
  latestBlockedPacket?: ProofPacket | null;
  controller?: {
    address: string | null;
    source: 'local' | 'onchain';
    latestRequestId: string | null;
    latestTxHash: string | null;
  };
};

export default function LandingPage({ packet, lease, currentOperator, rounds, controller }: LandingPageProps) {
  const liveLease = lease ?? packet?.lease ?? null;
  const leaseState = deriveLeaseState(liveLease, currentOperator?.mode ?? packet?.operator.mode);
  const remainingBudget = packet?.usage.remainingDailyUsd ?? liveLease?.dailyBudgetUsd ?? 0;
  const outcomeTone = toneForOutcome(packet?.decision.outcome);
  const executionTone = toneForExecution(packet?.execution.status);
  const zoneTone = toneForTrustZone(packet?.decision.trustZone);

  const boundAgentName = liveLease?.consumerName ? 'Bound Agent' : 'No agent bound';

  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          <div className="logo-icon">
            <img src="/boundless-mark.svg" alt="Boundless mark" />
          </div>
          <div>
            <div className="logo-text">Boundless</div>
            <div className="logo-sub">Governed Agent Finance</div>
          </div>
        </div>
        <nav className="nav">
          <Link href="/" className="nav-link active">Home</Link>
          <Link href="/proof" className="nav-link">Proof</Link>
          <Link href="/submission" className="nav-link">App</Link>
        </nav>
      </header>

      <section className="hero">
        <h1>
          <span>Boundless</span><br />
          Passport First, Policy Enforced
        </h1>
        <p className="animate-fade-in-up delay-2">
          Boundless is the governance layer for Kite Passport-powered agent payments.
          Kite Passport handles identity and delegated payment permission. Boundless adds policy, operator controls, and verifiable proof.
        </p>
        <div className="hero-buttons animate-fade-in-up delay-4">
          <Link href="/submission" className="btn-lime">
            Open App
          </Link>
          <Link href="/proof" className="btn-outline">
            View Proof
          </Link>
        </div>
      </section>

      <div className="grid-2">
        <div className="card animate-fade-in-up delay-1">
          <h2>How This Fits Kite Passport</h2>
          <p>
            The user creates a delegated payment session through Kite Passport, then uses Boundless to define the exact spend envelope:
            budget, assets, counterparties, and operator mode. The agent never receives unlimited wallet authority from Boundless.
          </p>
          <div className="info-grid">
            <div className="info-card">
              <div className="k">Passport Layer</div>
              <div className="v">Identity + delegated payment permission</div>
            </div>
            <div className="info-card">
              <div className="k">Boundless Layer</div>
              <div className="v">{formatUsd(liveLease?.perTxUsd ?? 0)} max per request</div>
            </div>
            <div className="info-card">
              <div className="k">Live Result</div>
              <div className="v">{packet ? titleCase(packet.decision.outcome) : 'No payment checked yet'}</div>
            </div>
          </div>
        </div>

        <div className="card animate-fade-in-up delay-2">
          <h2>What Boundless Adds</h2>
          <p>
            Boundless writes the active policy, operator mode, and receipt anchor to the controller contract.
            This is the governance layer above Passport: approval boundaries are visible onchain and proof survives outside the local app.
          </p>
          <div className="info-grid">
            <div className="info-card">
              <div className="k">Controller</div>
              <div className="v mono">{shortHash(controller?.address ?? undefined)}</div>
            </div>
            <div className="info-card">
              <div className="k">Latest Request</div>
              <div className="v mono">{shortHash(controller?.latestRequestId ?? undefined)}</div>
            </div>
            <div className="info-card">
              <div className="k">Source</div>
              <div className="v">{titleCase(controller?.source ?? 'local')}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="stats-bar">
        <div className="stat-card">
          <div className="stat-label">Rule State</div>
          <div className={`stat-value ${leaseState.tone === 'ok' ? 'green' : leaseState.tone === 'warn' ? 'amber' : ''}`}>
            {leaseState.label}
          </div>
          <div className="stat-note">{liveLease ? shortHash(liveLease.leaseId) : 'No policy file yet'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Per-Tx Limit</div>
          <div className="stat-value lime">{formatUsd(liveLease?.perTxUsd ?? 0)}</div>
          <div className="stat-note">{boundAgentName}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Daily Budget</div>
          <div className="stat-value">{formatUsd(liveLease?.dailyBudgetUsd ?? 0)}</div>
          <div className="stat-note">Remaining {formatUsd(remainingBudget)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Latest Outcome</div>
          <div className={`stat-value ${outcomeTone === 'ok' ? 'green' : outcomeTone === 'warn' ? 'amber' : ''}`}>
            {packet ? titleCase(packet.decision.outcome) : 'No Round'}
          </div>
          <div className="stat-note">{packet ? formatTimestamp(packet.generatedAt) : 'Create a Passport-backed policy and run the first payment check'}</div>
        </div>
      </div>

      {packet ? (
        <>
          <div className="status-row">
            <span className="pill ok">Chain {packet.treasury.chainId}</span>
            <span className="pill ok">Agent: Bound Request</span>
            <span className={`pill ${outcomeTone}`}>Decision: {titleCase(packet.decision.outcome)}</span>
            <span className={`pill ${zoneTone}`}>Zone: {titleCase(packet.decision.trustZone)}</span>
            <span className={`pill ${executionTone}`}>Execution: {titleCase(packet.execution.status)}</span>
          </div>

          <div className="grid-2">
            <div className="card">
              <h2>Current Round</h2>
              <div className="info-grid">
                <div className="info-card">
                  <div className="k">Request</div>
                  <div className="v">{packet.request.fromToken} → {packet.request.toToken}</div>
                </div>
                <div className="info-card">
                  <div className="k">Requested</div>
                  <div className="v">{formatUsd(packet.request.notionalUsd)}</div>
                </div>
                <div className="info-card">
                  <div className="k">Allowed</div>
                  <div className="v">{formatUsd(packet.decision.finalNotionalUsd)}</div>
                </div>
                <div className="info-card">
                  <div className="k">Wallet</div>
                  <div className="v mono">{shortHash(packet.lease.walletAddress)}</div>
                </div>
                <div className="info-card">
                  <div className="k">Operator</div>
                  <div className="v">{titleCase(packet.operator.mode)}</div>
                </div>
                <div className="info-card">
                  <div className="k">Tx Hash</div>
                  <div className="v mono">{shortHash(packet.execution.txHash)}</div>
                </div>
              </div>
            </div>

            <div className="card">
              <h2>What Is Real Right Now</h2>
              <p>{sanitizeProofText(packet.decision.rationale)}</p>
              <p>{sanitizeProofText(packet.execution.note)}</p>
              <p style={{ marginBottom: 0 }}>
                Latest artifact: {formatTimestamp(packet.generatedAt)}. Recent governed payment rounds recorded: {rounds.length}.
              </p>
            </div>
          </div>
        </>
      ) : (
        <div className="card" style={{ borderColor: 'var(--lime)', background: 'linear-gradient(135deg, rgba(217, 249, 157, 0.05) 0%, var(--card) 100%)' }}>
          <h2>No Live Proof Yet</h2>
          <p>
            {liveLease
              ? 'A Boundless policy exists, but no payment check has written a live proof packet yet.'
              : 'This app has no generated policy or round data yet.'}
          </p>
          <div className="info-grid">
            <div className="info-card">
              <div className="k">Rule</div>
              <div className="v mono">{shortHash(liveLease?.leaseId)}</div>
            </div>
            <div className="info-card">
              <div className="k">Agent Scope</div>
              <div className="v">{liveLease ? 'Passport-backed policy active' : 'Not set'}</div>
            </div>
            <div className="info-card">
              <div className="k">Next Step</div>
              <div className="v">Open App to save a policy and run a governed payment check</div>
            </div>
          </div>
        </div>
      )}

      <div className="features-grid"></div>

      <div className="footer">
        Kite Passport for delegation · Boundless for policy and proof · Latest round {packet ? formatTimestamp(packet.generatedAt) : 'not generated'}
      </div>
    </div>
  );
}
