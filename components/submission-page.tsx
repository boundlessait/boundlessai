'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { formatTimestamp, formatUsd, ratio, shortHash, titleCase } from '@/lib/format';
import { deriveLeaseState, toneForExecution, toneForOutcome, toneForTrustZone } from '@/lib/runtime';
import type { ProofPacket, RoundArtifactIndexEntry } from '@/lib/types';
import { OperatorConsole } from '@/components/operator-console';
import { TopWalletConnect } from '@/components/top-wallet-connect';

const GUIDE_STORAGE_KEY = 'boundless.dashboard.guide-seen';

type GuideStep = {
  id: string;
  targetId: string;
  title: string;
  summary: string;
  detail: string;
};

const GUIDE_STEPS: GuideStep[] = [
  {
    id: 'header',
    targetId: 'dashboard-header',
    title: 'Navigation & Wallet',
    summary: 'Connect your wallet to get started.',
    detail: 'Click the wallet button on the top right to connect. Navigation links: Home, Proof, App.',
  },
  {
    id: 'rule-status',
    targetId: 'sidebar-rule',
    title: 'Current Rule Status',
    summary: 'Shows your active rule and budget.',
    detail: 'Displays the protected wallet address, daily budget, per-tx limit, and operator mode. The progress bar shows spent vs remaining budget.',
  },
  {
    id: 'operator-mode',
    targetId: 'sidebar-operator',
    title: 'Operator Mode',
    summary: 'Control how the agent executes.',
    detail: 'Active = auto execution, Review = manual approval required, Paused = no execution allowed.',
  },
  {
    id: 'stats',
    targetId: 'dashboard-stats',
    title: 'Live Overview',
    summary: 'Key metrics at a glance.',
    detail: 'Rule Status, Budget Left, Approved count, and Blocked count. These update in real-time.',
  },
  {
    id: 'controls',
    targetId: 'controls-section',
    title: 'Controls Panel',
    summary: 'Configure and execute rule operations.',
    detail: 'Set wallet, budget, assets, protocols. Save rule onchain. Pause/Review/Resume operator. Run test rounds.',
  },
  {
    id: 'activity',
    targetId: 'dashboard-activity',
    title: 'Activity Feed',
    summary: 'Recent agent actions and outcomes.',
    detail: 'Shows the last 5 actions with their outcome (Approved/Blocked/Resized). Click "View History" for full log.',
  },
];

type SubmissionPageProps = {
  packet: ProofPacket | null;
  lease: ProofPacket['lease'] | null;
  currentOperator?: ProofPacket['operator'] | null;
  rounds: RoundArtifactIndexEntry[];
  latestSuccessRound: RoundArtifactIndexEntry | null;
  latestBlockedRound: RoundArtifactIndexEntry | null;
  latestSuccessPacket: ProofPacket | null;
  latestBlockedPacket: ProofPacket | null;
  controller: {
    address: string | null;
    source: 'local' | 'onchain';
    latestRequestId: string | null;
    latestTxHash: string | null;
    actionsEnabled: boolean;
    runRoundEnabled: boolean;
    note: string | null;
  };
};

function modeMeaning(mode?: string | null): string {
  switch (mode) {
    case 'active':
      return 'Agent may execute if each request stays inside your rule.';
    case 'review':
      return 'Every request should pause for human review before execution.';
    case 'paused':
      return 'Execution is stopped until you press Resume.';
    default:
      return 'No operator mode has been set yet.';
  }
}

function nextGateLabel(mode?: string | null, leaseStatus?: string | null): string {
  if (leaseStatus !== 'active') {
    return 'No action can execute until you issue an active rule.';
  }
  switch (mode) {
    case 'review':
      return 'Next request should wait for human review.';
    case 'paused':
      return 'Next request should be blocked by operator pause.';
    case 'active':
      return 'Next request may execute if it stays inside budget and policy.';
    default:
      return 'Operator posture is not set yet.';
  }
}

export function SubmissionPage({
  packet,
  lease,
  currentOperator,
  rounds,
  latestSuccessRound,
  latestBlockedRound,
  latestSuccessPacket,
  latestBlockedPacket,
  controller,
}: SubmissionPageProps) {
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideStepIndex, setGuideStepIndex] = useState(0);
  const [guideTargetRect, setGuideTargetRect] = useState<DOMRect | null>(null);
  const [guideCardPosition, setGuideCardPosition] = useState<{ top: number; left: number } | null>(null);

  // Show guide on first load
  useEffect(() => {
    const seen = window.localStorage.getItem(GUIDE_STORAGE_KEY);
    if (!seen) {
      setGuideStepIndex(0);
      setGuideOpen(true);
    }
  }, []);

  // Update highlight position
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
        setGuideCardPosition({ top: 100, left: 24 });
        return;
      }

      target.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
      const rect = target.getBoundingClientRect();
      setGuideTargetRect(rect);

      const cardWidth = 340;
      const viewportPadding = 16;
      const nextLeft = Math.min(
        window.innerWidth - cardWidth - viewportPadding,
        Math.max(viewportPadding, rect.left),
      );
      const hasBottomSpace = rect.bottom + 240 < window.innerHeight;
      const nextTop = hasBottomSpace
        ? rect.bottom + 12
        : Math.max(viewportPadding, rect.top - 240);

      setGuideCardPosition({ top: nextTop, left: nextLeft });
    };

    const timer = window.setTimeout(refresh, 150);
    window.addEventListener('resize', refresh);
    window.addEventListener('scroll', refresh, true);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('resize', refresh);
      window.removeEventListener('scroll', refresh, true);
    };
  }, [guideOpen, guideStepIndex]);

  function closeGuide(markSeen = true) {
    setGuideOpen(false);
    if (markSeen) {
      window.localStorage.setItem(GUIDE_STORAGE_KEY, '1');
    }
  }

  function nextGuideStep() {
    if (guideStepIndex >= GUIDE_STEPS.length - 1) {
      closeGuide(true);
      return;
    }
    setGuideStepIndex((prev) => prev + 1);
  }

  function openGuide() {
    setGuideStepIndex(0);
    setGuideOpen(true);
  }

  const liveLease = lease ?? packet?.lease ?? null;
  const currentMode = currentOperator?.mode ?? packet?.operator.mode ?? null;
  const leaseState = deriveLeaseState(liveLease, currentMode ?? undefined);
  const spentUsd = packet?.usage.spent24hUsd ?? 0;
  const dailyBudgetUsd = liveLease?.dailyBudgetUsd ?? 0;
  const remainingDailyUsd = packet?.usage.remainingDailyUsd ?? dailyBudgetUsd;
  const spentPercent = ratio(spentUsd, dailyBudgetUsd);
  const remainingPercent = ratio(remainingDailyUsd, dailyBudgetUsd);

  const historicalReferencePacket = latestSuccessPacket ?? latestBlockedPacket ?? packet;
  const historicalLeaseId = historicalReferencePacket?.lease.leaseId ?? latestSuccessRound?.leaseId ?? latestBlockedRound?.leaseId ?? null;
  const historicalWallet = historicalReferencePacket?.lease.walletAddress ?? null;
  const historicalProofMatchesLiveLease = Boolean(
    liveLease?.leaseId &&
    historicalLeaseId &&
    liveLease.leaseId === historicalLeaseId
  );
  const showHistoricalMismatch = Boolean(
    liveLease &&
    historicalLeaseId &&
    !historicalProofMatchesLiveLease
  );

  const proofOutcomeTone = toneForOutcome(historicalReferencePacket?.decision.outcome);
  const proofZoneTone = toneForTrustZone(historicalReferencePacket?.decision.trustZone);
  const proofExecutionTone = toneForExecution(historicalReferencePacket?.execution.status);
  const approvedCount = rounds.filter((round) => round.outcome === 'approve').length;
  const blockedCount = rounds.filter((round) => round.outcome === 'block').length;
  const resizeCount = rounds.filter((round) => round.outcome === 'resize').length;

  return (
    <div className="app">
      <header className="header" id="dashboard-header">
        <div className="brand">
          <div className="logo-icon">
            <img src="/boundless-mark.svg" alt="Boundless mark" />
          </div>
          <div>
            <div className="logo-text">Boundless</div>
            <div className="logo-sub">Agent Execution Guard</div>
          </div>
        </div>
        <div className="header-right">
          <nav className="nav">
            <Link href="/" className="nav-link">Home</Link>
            <Link href="/proof" className="nav-link">Proof</Link>
            <Link href="/submission" className="nav-link active">App</Link>
            <Link href="/member-test" className="nav-link">Member Test</Link>
          </nav>
          <button className="guide-btn-header" onClick={openGuide} title="Open Guide">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
          </button>
          <TopWalletConnect />
        </div>
      </header>

      <div className="dashboard-shell">
        <aside className="dashboard-sidebar">
          <div className="card sidebar-card" id="sidebar-rule">
            <div className="card-header">
              <h2>Current Rule</h2>
              <span className={`status-badge ${leaseState.tone}`}>{leaseState.label}</span>
            </div>
            <div className="sidebar-meta">
              <div className="meta-item">
                <span className="meta-label">Wallet</span>
                <span className="meta-value mono">{shortHash(liveLease?.walletAddress)}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Daily Budget</span>
                <span className="meta-value">{formatUsd(dailyBudgetUsd)}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Per-Tx Limit</span>
                <span className="meta-value">{formatUsd(liveLease?.perTxUsd ?? 0)}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Operator</span>
                <span className="meta-value">{titleCase(currentMode ?? 'idle')}</span>
              </div>
            </div>
            <div className="budget-bar">
              <div className="bar-segment spent" style={{ width: `${spentPercent}%` }} />
              <div className="bar-segment left" style={{ width: `${remainingPercent}%` }} />
            </div>
            <div className="budget-labels">
              <span>Spent {formatUsd(spentUsd)}</span>
              <span className="remaining">{formatUsd(remainingDailyUsd)} left</span>
            </div>
          </div>

          <div className="card sidebar-card compact" id="sidebar-operator">
            <div className="card-header">
              <h2>Operator Mode</h2>
            </div>
            <div className="mode-selector">
              <button className={`mode-btn ${currentMode === 'active' ? 'active' : ''}`}>
                <span className="mode-dot green"></span>
                Active
              </button>
              <button className={`mode-btn ${currentMode === 'review' ? 'active' : ''}`}>
                <span className="mode-dot amber"></span>
                Review
              </button>
              <button className={`mode-btn ${currentMode === 'paused' ? 'active' : ''}`}>
                <span className="mode-dot red"></span>
                Paused
              </button>
            </div>
            <p className="mode-hint">{modeMeaning(currentMode)}</p>
          </div>
        </aside>

        <main className="dashboard-main">
          <div className="stats-bar" id="dashboard-stats">
            <div className="stat-card">
              <div className="stat-label">Rule Status</div>
              <div className={`stat-value ${leaseState.tone === 'ok' ? 'green' : 'amber'}`}>{leaseState.label}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Budget Left</div>
              <div className="stat-value lime">{formatUsd(remainingDailyUsd)}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Approved</div>
              <div className="stat-value green">{approvedCount}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Blocked</div>
              <div className="stat-value amber">{blockedCount}</div>
            </div>
          </div>

          <div id="controls-section">
            <OperatorConsole
            leaseId={liveLease?.leaseId}
            leaseStatus={liveLease?.status}
            operatorMode={currentMode}
            latestSuccessTxHash={latestSuccessRound?.txHash}
            latestBlockedReason={latestBlockedPacket?.decision.rationale}
            controllerAddress={controller.address}
            controllerSource={controller.source}
            governedWallet={liveLease?.walletAddress}
            baseAsset={liveLease?.baseAsset}
            perTxUsd={liveLease?.perTxUsd}
            dailyBudgetUsd={liveLease?.dailyBudgetUsd}
            allowedAssets={liveLease?.allowedAssets}
            allowedProtocols={liveLease?.allowedProtocols}
            actionsEnabled={controller.actionsEnabled}
            runRoundEnabled={controller.runRoundEnabled}
            controllerNote={controller.note}
          />

          {showHistoricalMismatch ? (
            <div className="response-banner error">
              Historical proof is from an older rule. Live wallet: {shortHash(liveLease?.walletAddress)}
            </div>
          ) : null}
          </div>

          <div className="card">
            <div className="card-header">
              <h2>Latest Activity</h2>
            </div>
            <div className="activity-feed" id="dashboard-activity">
              {rounds.length > 0 ? (
                rounds.slice(0, 5).map((round) => (
                  <div key={`${round.generatedAt}-${round.requestId}-feed`} className="activity-row">
                    <div className="activity-main">
                      <span className={`pill ${toneForOutcome(round.outcome)}`}>{titleCase(round.outcome)}</span>
                      <span className="activity-summary">{round.summary}</span>
                    </div>
                    <div className="activity-meta">
                      <span>{formatTimestamp(round.generatedAt)}</span>
                      <span className="mono">{shortHash(round.txHash)}</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="empty-state">No activity yet</div>
              )}
            </div>
          </div>

          <details className="card advanced-panel">
            <summary>View History</summary>
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Outcome</th>
                  <th>Tx</th>
                  <th>Summary</th>
                </tr>
              </thead>
              <tbody>
                {rounds.length > 0 ? (
                  rounds.map((round) => (
                    <tr key={`${round.generatedAt}-${round.requestId}`}>
                      <td>{formatTimestamp(round.generatedAt)}</td>
                      <td>
                        <span className={`pill ${toneForOutcome(round.outcome)}`}>
                          {titleCase(round.outcome)}
                        </span>
                      </td>
                      <td className="mono">{shortHash(round.txHash)}</td>
                      <td className="history-summary-cell">{round.summary}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} style={{ color: 'var(--s2)' }}>No rounds recorded yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </details>
        </main>
      </div>

      <div className="footer">
        Built on <a href="#">X Layer</a> · Reads the controller contract plus runtime proof artifacts
      </div>

      {/* Guide Overlay */}
      {guideOpen && (
        <div className="guide-overlay">
          {guideTargetRect && (
            <div
              className="guide-highlight"
              style={{
                top: guideTargetRect.top,
                left: guideTargetRect.left,
                width: guideTargetRect.width,
                height: guideTargetRect.height,
              }}
            />
          )}
          {guideCardPosition && (
            <div
              className="guide-card"
              style={{
                top: guideCardPosition.top,
                left: guideCardPosition.left,
              }}
            >
              <div className="guide-step-meta">
                Step {guideStepIndex + 1} of {GUIDE_STEPS.length}
              </div>
              <h3 className="guide-title">{GUIDE_STEPS[guideStepIndex].title}</h3>
              <p className="guide-summary">{GUIDE_STEPS[guideStepIndex].summary}</p>
              <p className="guide-detail">{GUIDE_STEPS[guideStepIndex].detail}</p>
              <div className="guide-actions">
                <button className="guide-btn-secondary" onClick={() => closeGuide(false)}>
                  Skip
                </button>
                <button className="guide-btn-primary" onClick={nextGuideStep}>
                  {guideStepIndex >= GUIDE_STEPS.length - 1 ? 'Finish' : 'Next'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
