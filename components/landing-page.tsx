import Link from 'next/link';
import { formatTimestamp, formatUsd, shortHash, titleCase } from '@/lib/format';
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

  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          <div className="logo-icon">
            <img src="/boundless-mark.svg" alt="Boundless mark" />
          </div>
          <div>
            <div className="logo-text">Boundless</div>
            <div className="logo-sub">Agent Execution Guard</div>
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
          Rules First, Agents Run
        </h1>
        <p className="animate-fade-in-up delay-2">
          Boundless — Let agents run, within your rules, budget, and verifiable proof.
          Give an agent bounded permission without giving away full wallet control.
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
          <h2>What the user actually does</h2>
          <p>
            The user picks a governed wallet, issues a rule with budget and route limits, then lets the agent submit requests.
            The agent never gets unlimited wallet authority from this app.
          </p>
          <div className="info-grid">
            <div className="info-card">
              <div className="k">Governed Wallet</div>
              <div className="v mono">{shortHash(liveLease?.walletAddress)}</div>
            </div>
            <div className="info-card">
              <div className="k">Rule Limit</div>
              <div className="v">{formatUsd(liveLease?.perTxUsd ?? 0)} per request</div>
            </div>
            <div className="info-card">
              <div className="k">Agent Result</div>
              <div className="v">{packet ? titleCase(packet.decision.outcome) : 'No round yet'}</div>
            </div>
          </div>
        </div>

        <div className="card animate-fade-in-up delay-2">
          <h2>What is onchain</h2>
          <p>
            The X Layer controller records the active lease, operator mode, and latest receipt anchor.
            That makes the guardrail visible outside the local proof files.
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
          <div className="stat-note">{liveLease ? shortHash(liveLease.leaseId) : 'No rule file yet'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Per-Tx Limit</div>
          <div className="stat-value lime">{formatUsd(liveLease?.perTxUsd ?? 0)}</div>
          <div className="stat-note">{liveLease?.consumerName ?? 'No consumer bound'}</div>
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
          <div className="stat-note">{packet ? formatTimestamp(packet.generatedAt) : 'Issue a lease and run the first round'}</div>
        </div>
      </div>

      {packet ? (
        <>
          <div className="status-row">
            <span className="pill ok">Chain {packet.treasury.chainId}</span>
            <span className="pill ok">Consumer: {packet.request.consumerName}</span>
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
              <p>{packet.decision.rationale}</p>
              <p>{packet.execution.note}</p>
              <p style={{ marginBottom: 0 }}>
                Latest artifact: {formatTimestamp(packet.generatedAt)}. Recent rounds recorded: {rounds.length}.
              </p>
            </div>
          </div>
        </>
      ) : (
        <div className="card" style={{ borderColor: 'var(--lime)', background: 'linear-gradient(135deg, rgba(217, 249, 157, 0.05) 0%, var(--card) 100%)' }}>
          <h2>No Live Proof Yet</h2>
          <p>
            {liveLease
              ? 'A rule exists, but no round has written a live proof packet yet.'
              : 'This app has no generated rule or round data yet.'}
          </p>
          <div className="info-grid">
            <div className="info-card">
              <div className="k">Rule</div>
              <div className="v mono">{shortHash(liveLease?.leaseId)}</div>
            </div>
            <div className="info-card">
              <div className="k">Consumer</div>
              <div className="v">{liveLease?.consumerName ?? 'Not set'}</div>
            </div>
            <div className="info-card">
              <div className="k">Next Step</div>
              <div className="v">Open App to issue a rule and run a governed round</div>
            </div>
          </div>
        </div>
      )}

      <div className="features-grid"></div>

      <div className="footer">
        Built on <a href="#">X Layer</a> · Latest round {packet ? formatTimestamp(packet.generatedAt) : 'not generated'}
      </div>
    </div>
  );
}
