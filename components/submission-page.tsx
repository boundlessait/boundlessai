'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { formatTimestamp, formatUsd, ratio, shortHash, titleCase } from '@/lib/format';
import { deriveLeaseState, toneForExecution, toneForOutcome, toneForTrustZone } from '@/lib/runtime';
import type { ProofPacket, RoundArtifactIndexEntry } from '@/lib/types';
import { OperatorConsole } from '@/components/operator-console';
import { TopWalletConnect } from '@/components/top-wallet-connect';

const GUIDE_STORAGE_KEY = 'boundless.dashboard.guide-seen';
const GUIDE_SESSION_DISMISSED_KEY = 'boundless.dashboard.guide-dismissed-session';

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
    detail: 'Click the wallet button on the top right to connect. Kite Passport handles delegated payment permission, while Boundless governs the resulting payment requests here.',
  },
  {
    id: 'rule-status',
    targetId: 'sidebar-rule',
    title: 'Current Policy Status',
    summary: 'Shows your active Boundless policy and budget.',
    detail: 'Displays the protected wallet address, daily budget, per-tx limit, and operator mode layered on top of a Passport-backed payment session.',
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
    summary: 'Configure Boundless policy operations.',
    detail: 'Set wallet, budget, assets, protocols. Save policy onchain. Pause/Review/Resume operator. Run governed payment checks.',
  },
  {
    id: 'activity',
    targetId: 'dashboard-activity',
    title: 'Activity Feed',
    summary: 'Recent agent actions and outcomes.',
    detail: 'Shows the last 5 actions with their outcome (Approved/Blocked/Resized). Click "View History" for full log.',
  },
];

function resolveGuideTargetElement(targetId: string): HTMLElement | null {
  return document.getElementById(targetId);
}

function clampGuideCardPosition(rect: DOMRect): { top: number; left: number } {
  const viewportPadding = 16;
  const cardWidth = Math.min(320, window.innerWidth - viewportPadding * 2);
  const cardHeight = 240;
  const nextLeft = Math.min(
    window.innerWidth - cardWidth - viewportPadding,
    Math.max(viewportPadding, rect.left),
  );
  const hasBottomSpace = rect.bottom + cardHeight + 12 < window.innerHeight;
  const nextTop = hasBottomSpace
    ? rect.bottom + 12
    : Math.max(viewportPadding, rect.top - cardHeight - 12);

  return { top: nextTop, left: nextLeft };
}

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
    vaultAddress: string | null;
    source: 'local' | 'onchain';
    latestRequestId: string | null;
    latestTxHash: string | null;
    consumerName: string | null;
    operatorName: string | null;
    chainId: number;
    actionsEnabled: boolean;
    runRoundEnabled: boolean;
    note: string | null;
  };
};

function modeMeaning(mode?: string | null): string {
  switch (mode) {
    case 'active':
      return 'Agent may execute if each request stays inside the active Boundless policy.';
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
    return 'No action can execute until you save an active policy.';
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

function roundSummaryLabel(round: RoundArtifactIndexEntry): string {
  const parts = [
    `Policy ${shortHash(round.leaseId)}`,
    `Request ${shortHash(round.requestId)}`,
    `Decision ${titleCase(round.outcome)}`,
  ];
  if (round.txHash) {
    parts.push(`Tx ${shortHash(round.txHash)}`);
  }
  return parts.join(' · ');
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
    const dismissedForSession = window.sessionStorage.getItem(GUIDE_SESSION_DISMISSED_KEY);
    if (!seen && !dismissedForSession) {
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

    const measure = () => {
      const step = GUIDE_STEPS[guideStepIndex];
      const target = resolveGuideTargetElement(step.targetId);
      if (!target) {
        setGuideTargetRect(null);
        setGuideCardPosition({ top: 100, left: 24 });
        return;
      }
      const rect = target.getBoundingClientRect();
      setGuideTargetRect(rect);
      setGuideCardPosition(clampGuideCardPosition(rect));
    };

    const step = GUIDE_STEPS[guideStepIndex];
    const target = resolveGuideTargetElement(step.targetId);
    target?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });

    const timer = window.setTimeout(measure, 180);
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
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
        setGuideStepIndex((prev) => prev - 1);
      } else if (event.key === 'ArrowRight') {
        nextGuideStep();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [guideOpen, guideStepIndex]);

  function closeGuide(markSeen = true) {
    setGuideOpen(false);
    window.sessionStorage.setItem(GUIDE_SESSION_DISMISSED_KEY, '1');
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
    window.sessionStorage.removeItem(GUIDE_SESSION_DISMISSED_KEY);
    setGuideStepIndex(0);
    setGuideOpen(true);
  }

  function previousGuideStep() {
    setGuideStepIndex((prev) => Math.max(0, prev - 1));
  }

  const liveLease = lease ?? packet?.lease ?? null;
  const currentMode = currentOperator?.mode ?? packet?.operator.mode ?? null;
  const leaseState = deriveLeaseState(liveLease, currentMode ?? undefined);
  const currentLeaseId = liveLease?.leaseId ?? null;
  const packetMatchesLiveLease = Boolean(
    currentLeaseId &&
    packet?.lease.leaseId &&
    packet.lease.leaseId === currentLeaseId,
  );
  const currentLeaseRounds = currentLeaseId
    ? rounds.filter((round) => round.leaseId === currentLeaseId)
    : rounds;
  const spentUsd = packetMatchesLiveLease ? (packet?.usage.spent24hUsd ?? 0) : 0;
  const dailyBudgetUsd = liveLease?.dailyBudgetUsd ?? 0;
  const remainingDailyUsd = packetMatchesLiveLease
    ? (packet?.usage.remainingDailyUsd ?? dailyBudgetUsd)
    : dailyBudgetUsd;
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
  const approvedCount = currentLeaseRounds.filter((round) => round.outcome === 'approve').length;
  const blockedCount = currentLeaseRounds.filter((round) => round.outcome === 'block').length;
  const resizeCount = currentLeaseRounds.filter((round) => round.outcome === 'resize').length;

  return (
    <div className="app">
      <header className="header" id="dashboard-header">
        <div className="brand">
          <div className="logo-icon">
            <img src="/boundless-mark.svg" alt="Boundless mark" />
          </div>
          <div>
            <div className="logo-text">Boundless</div>
            <div className="logo-sub">Governed Agent Finance for Kite Passport</div>
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
              <h2>Current Boundless Policy</h2>
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
            <p className="mode-hint" style={{ marginTop: 10 }}>
              Passport handles delegated payment permission. Operator Mode is the extra human control layer that Boundless adds before execution.
            </p>
          </div>
        </aside>

        <main className="dashboard-main">
          <div className="card">
            <div className="card-header">
              <h2>Architecture</h2>
            </div>
            <div className="sidebar-meta">
              <div className="meta-item">
                <span className="meta-label">1. Kite Passport</span>
                <span className="meta-value">Identity, delegated payment permission, session scope</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">2. Boundless Policy</span>
                <span className="meta-value">Per-action limit, daily budget, allowed assets, operator review</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">3. Execution</span>
                <span className="meta-value">Allowed requests continue, blocked requests stop before settlement</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">4. Proof</span>
                <span className="meta-value">Both outcomes are written as receipts and evidence</span>
              </div>
            </div>
          </div>

          <div className="stats-bar" id="dashboard-stats">
            <div className="stat-card">
              <div className="stat-label">Policy Status</div>
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
            latestBlockedReason={
              latestBlockedPacket?.lease.leaseId === currentLeaseId
                ? latestBlockedPacket?.decision.rationale
                : null
            }
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
            vaultAddress={controller.vaultAddress}
            consumerName={controller.consumerName}
            operatorName={controller.operatorName}
            chainId={controller.chainId}
          />

          {showHistoricalMismatch ? (
            <div className="response-banner error">
              Historical proof is from an older policy. Live wallet: {shortHash(liveLease?.walletAddress)}
            </div>
          ) : null}
          </div>

          <div className="card">
            <div className="card-header">
              <h2>Latest Activity</h2>
            </div>
            <div className="activity-feed" id="dashboard-activity">
              {currentLeaseRounds.length > 0 ? (
                currentLeaseRounds.slice(0, 5).map((round) => (
                  <div key={`${round.generatedAt}-${round.requestId}-feed`} className="activity-row">
                    <div className="activity-main">
                      <span className={`pill ${toneForOutcome(round.outcome)}`}>{titleCase(round.outcome)}</span>
                      <span className="activity-summary">{roundSummaryLabel(round)}</span>
                    </div>
                    <div className="activity-meta">
                      <span>{formatTimestamp(round.generatedAt)}</span>
                      <span className="mono">{shortHash(round.txHash)}</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="empty-state">No activity yet for the current policy</div>
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
                {currentLeaseRounds.length > 0 ? (
                  currentLeaseRounds.map((round) => (
                    <tr key={`${round.generatedAt}-${round.requestId}`}>
                      <td>{formatTimestamp(round.generatedAt)}</td>
                      <td>
                        <span className={`pill ${toneForOutcome(round.outcome)}`}>
                          {titleCase(round.outcome)}
                        </span>
                      </td>
                      <td className="mono">{shortHash(round.txHash)}</td>
                      <td className="history-summary-cell">{roundSummaryLabel(round)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} style={{ color: 'var(--s2)' }}>No rounds recorded yet for the current policy.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </details>
        </main>
      </div>

      <div className="footer">
        Kite Passport for delegation · Boundless for policy and proof
      </div>

      {/* Guide Overlay */}
      {guideOpen && (
        <div
          className="guide-overlay"
          onClick={() => closeGuide(false)}
          role="presentation"
        >
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
              onClick={(event) => event.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-label="Boundless guide"
            >
              <div className="guide-step-meta">
                Step {guideStepIndex + 1} of {GUIDE_STEPS.length}
              </div>
              <h3 className="guide-title">{GUIDE_STEPS[guideStepIndex].title}</h3>
              <p className="guide-summary">{GUIDE_STEPS[guideStepIndex].summary}</p>
              <p className="guide-detail">{GUIDE_STEPS[guideStepIndex].detail}</p>
              <div className="guide-actions">
                <button className="guide-btn-secondary" onClick={() => closeGuide(false)}>
                  Close
                </button>
                <button
                  className="guide-btn-secondary"
                  onClick={previousGuideStep}
                  disabled={guideStepIndex === 0}
                >
                  Back
                </button>
                <button className="guide-btn-secondary" onClick={() => closeGuide(true)}>
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
