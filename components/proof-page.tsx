import Link from 'next/link';
import { formatTimestamp, formatUsd, sanitizeProofText, shortHash, titleCase } from '@/lib/format';
import { deriveLeaseState, toneForExecution, toneForOutcome, toneForTrustZone } from '@/lib/runtime';
import type { ProofPacket, RoundArtifactIndexEntry } from '@/lib/types';
import { OperatorConsole } from '@/components/operator-console';

type ProofPageProps = {
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

function EmptyProof({ lease }: { lease: ProofPacket['lease'] | null }) {
  const leaseState = deriveLeaseState(lease, undefined);

  return (
    <div className="card">
      <h2>No Proof Packet Yet</h2>
      <p>
        {lease
          ? 'A policy exists, but there is no generated proof packet to inspect yet.'
          : 'The proof view has no policy or payment-check artifacts to render.'}
      </p>
      <div className="info-grid">
        <div className="info-card">
          <div className="k">Policy Status</div>
          <div className="v">{leaseState.label}</div>
        </div>
        <div className="info-card">
          <div className="k">Policy ID</div>
          <div className="v mono">{shortHash(lease?.leaseId)}</div>
        </div>
        <div className="info-card">
          <div className="k">Next Step</div>
          <div className="v">Use the Operator Console to save a policy and run a governed payment check</div>
        </div>
      </div>
    </div>
  );
}

function humanizeExecutionNetwork(value?: string | null): string {
  if (!value) return 'Onchain';
  if (value.includes('mainnet')) return 'Mainnet';
  if (value.includes('testnet')) return 'Testnet';
  return 'Onchain';
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

export function ProofPage({ packet, lease, currentOperator, rounds, latestSuccessRound, latestBlockedRound, latestSuccessPacket, latestBlockedPacket, controller }: ProofPageProps) {
  const liveLease = lease ?? packet?.lease ?? null;
  const leaseState = deriveLeaseState(liveLease, currentOperator?.mode ?? packet?.operator.mode);
  const outcomeTone = toneForOutcome(packet?.decision.outcome);
  const zoneTone = toneForTrustZone(packet?.decision.trustZone);
  const executionTone = toneForExecution(packet?.execution.status);
  const flow = [
    { step: '1', title: 'Passport Session', desc: 'User delegates payment permission to the agent' },
    { step: '2', title: 'Boundless Policy', desc: 'Budget, assets, counterparties, and operator mode are enforced' },
    { step: '3', title: 'Agent Request', desc: 'The payment or execution request enters the policy gate' },
    { step: '4', title: 'Decision', desc: 'Approve, resize, block, or require review' },
    { step: '5', title: 'Receipt', desc: 'Round writes proof and optional tx hash' }
  ];

  return (
    <div className="app">
      <div className="topbar">
        <div className="topbar-left">
          <span className="topbar-label">Chain</span>
          <span className="topbar-value">{packet?.treasury.chainId ?? 196}</span>
        </div>
        <div className="topbar-left">
          <span className="topbar-label">Operator</span>
          <span className="topbar-value">{titleCase(currentOperator?.mode ?? packet?.operator.mode ?? 'idle')}</span>
        </div>
      </div>

      <header className="header">
        <div className="logo">
          <Link href="/" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div className="logo-icon">
              <img src="/boundless-mark.svg" alt="Boundless mark" />
            </div>
            <div>
              <div className="logo-text">Boundless</div>
              <div className="logo-sub">Proof Dashboard for Passport-Governed Payments</div>
            </div>
          </Link>
        </div>
        <nav className="nav">
          <Link href="/" className="nav-link">Home</Link>
          <Link href="/proof" className="nav-link active">Proof</Link>
          <Link href="/submission" className="nav-link">App</Link>
        </nav>
      </header>

      <OperatorConsole
        leaseId={liveLease?.leaseId}
        leaseStatus={liveLease?.status}
        operatorMode={currentOperator?.mode ?? packet?.operator.mode}
        latestSuccessTxHash={latestSuccessRound?.txHash}
        latestBlockedReason={latestBlockedPacket?.decision.rationale}
        controllerAddress={controller.address}
        controllerSource={controller.source}
        governedWallet={liveLease?.walletAddress}
        actionsEnabled={controller.actionsEnabled}
        runRoundEnabled={controller.runRoundEnabled}
        controllerNote={controller.note}
        vaultAddress={controller.vaultAddress}
        consumerName={controller.consumerName}
        operatorName={controller.operatorName}
        chainId={controller.chainId}
      />

      <div className="card">
        <h2>Onchain Controller State</h2>
        <p>
          This is where Boundless shows its job in the stack: Kite Passport handles delegated payment permission,
          while the dashboard reads the active Boundless policy, operator posture, and latest receipt anchor from the controller contract.
        </p>
        <div className="info-grid">
          <div className="info-card">
            <div className="k">Controller</div>
            <div className="v mono">{shortHash(controller.address ?? undefined)}</div>
          </div>
          <div className="info-card">
            <div className="k">Source</div>
            <div className="v">{titleCase(controller.source)}</div>
          </div>
          <div className="info-card">
            <div className="k">Latest Request</div>
            <div className="v mono">{shortHash(controller.latestRequestId ?? undefined)}</div>
          </div>
          <div className="info-card">
            <div className="k">Latest Tx</div>
            <div className="v mono">{shortHash(controller.latestTxHash ?? undefined)}</div>
          </div>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <h2>Latest Approved Evidence</h2>
          <p>{latestSuccessPacket?.execution.note ? sanitizeProofText(latestSuccessPacket.execution.note) : 'No successful Passport-governed payment has been recorded yet.'}</p>
          <div className="info-grid">
            <div className="info-card">
              <div className="k">Round</div>
              <div className="v">{formatTimestamp(latestSuccessPacket?.generatedAt ?? latestSuccessRound?.generatedAt)}</div>
            </div>
            <div className="info-card">
              <div className="k">Tx Hash</div>
              <div className="v mono">{shortHash(latestSuccessPacket?.execution.txHash ?? latestSuccessRound?.txHash)}</div>
            </div>
            <div className="info-card">
              <div className="k">Notional</div>
              <div className="v">{formatUsd(latestSuccessPacket?.decision.finalNotionalUsd ?? 0)}</div>
            </div>
          </div>
        </div>

        <div className="card">
          <h2>Latest Blocked Evidence</h2>
          <p>{latestBlockedPacket?.decision.rationale ? sanitizeProofText(latestBlockedPacket.decision.rationale) : 'No blocked round is currently available.'}</p>
          <div className="info-grid">
            <div className="info-card">
              <div className="k">Round</div>
              <div className="v">{formatTimestamp(latestBlockedPacket?.generatedAt ?? latestBlockedRound?.generatedAt)}</div>
            </div>
            <div className="info-card">
              <div className="k">Outcome</div>
              <div className="v">{titleCase(latestBlockedPacket?.decision.outcome ?? latestBlockedRound?.outcome ?? 'none')}</div>
            </div>
            <div className="info-card">
              <div className="k">Policy Hit</div>
              <div className="v">{titleCase((latestBlockedPacket?.decision.policyHits?.[0] ?? 'n/a').replaceAll('_', ' '))}</div>
            </div>
          </div>
        </div>
      </div>

      {packet?.passportSession || packet?.paymentAttempt ? (
        <div className="grid-2">
          <div className="card">
            <h2>Passport Session Boundary</h2>
            {packet?.passportSession ? (
              <div className="info-grid">
                <div className="info-card">
                  <div className="k">Session ID</div>
                  <div className="v mono">{shortHash(packet.passportSession.sessionId)}</div>
                </div>
                <div className="info-card">
                  <div className="k">Payer</div>
                  <div className="v mono">{shortHash(packet.passportSession.payerAddress)}</div>
                </div>
                <div className="info-card">
                  <div className="k">Budget Left</div>
                  <div className="v">{formatUsd(packet.passportSession.remainingBudgetUsd)}</div>
                </div>
                <div className="info-card">
                  <div className="k">Expiry</div>
                  <div className="v">{formatTimestamp(packet.passportSession.expiresAt)}</div>
                </div>
              </div>
            ) : (
              <p>No Passport session metadata was attached to this proof packet.</p>
            )}
          </div>
          <div className="card">
            <h2>x402 Payment Result</h2>
            {packet?.paymentAttempt ? (
              <div className="info-grid">
                <div className="info-card">
                  <div className="k">Service</div>
                  <div className="v">{packet.paymentAttempt.merchantName ?? packet.paymentAttempt.serviceHost}</div>
                </div>
                <div className="info-card">
                  <div className="k">HTTP Status</div>
                  <div className="v">{packet.paymentAttempt.httpStatus}</div>
                </div>
                <div className="info-card">
                  <div className="k">Network</div>
                  <div className="v">{packet.paymentAttempt.network ?? 'kite-testnet'}</div>
                </div>
                <div className="info-card">
                  <div className="k">X-PAYMENT</div>
                  <div className="v">{packet.paymentAttempt.xPaymentPresent ? 'Present' : 'Missing'}</div>
                </div>
              </div>
            ) : (
              <p>No x402 attempt metadata was attached to this proof packet.</p>
            )}
            {packet?.paymentAttempt?.responsePreview ? (
              <p className="section-copy mono" style={{ marginTop: 12 }}>
                {packet.paymentAttempt.responsePreview}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="status-row">
        <span className={`pill ${leaseState.tone}`}>Policy: {leaseState.label}</span>
        <span className={`pill ${executionTone}`}>Execution: {packet ? titleCase(packet.execution.status) : 'Pending'}</span>
        <span className={`pill ${outcomeTone}`}>Decision: {packet ? titleCase(packet.decision.outcome) : 'None'}</span>
        <span className={`pill ${zoneTone}`}>Zone: {packet ? titleCase(packet.decision.trustZone) : 'Unknown'}</span>
      </div>

      {packet ? (
        <>
          <div className="stats-bar">
            <div className="stat-card">
              <div className="stat-label">Policy ID</div>
              <div className="stat-value">{shortHash(packet.lease.leaseId)}</div>
              <div className="stat-note">Bound agent policy</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Request</div>
              <div className="stat-value lime">{formatUsd(packet.request.notionalUsd)}</div>
              <div className="stat-note">{packet.request.fromToken} → {packet.request.toToken}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Allowed</div>
              <div className="stat-value amber">{formatUsd(packet.decision.finalNotionalUsd)}</div>
              <div className="stat-note">{titleCase(packet.decision.outcome)}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Tx Hash</div>
              <div className={`stat-value ${executionTone === 'ok' ? 'green' : executionTone === 'warn' ? 'amber' : ''}`}>
                {shortHash(packet.execution.txHash)}
              </div>
              <div className="stat-note">{formatTimestamp(packet.generatedAt)}</div>
            </div>
          </div>

          <div className="card">
            <h2>Execution Flow</h2>
            <div className="steps-container">
              {flow.map((item) => (
                <div key={item.step} className="step-item">
                  <div className="step-num">{item.step}</div>
                  <h4>{item.title}</h4>
                  <p>{item.desc}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h2>Boundless Policy Envelope</h2>
            <div className="info-grid">
              <div className="info-card">
                <div className="k">Policy ID</div>
                <div className="v mono">{shortHash(packet.lease.leaseId)}</div>
              </div>
              <div className="info-card">
              <div className="k">Consumer</div>
              <div className="v">Passport-powered Bound Agent</div>
              </div>
              <div className="info-card">
                <div className="k">Wallet</div>
                <div className="v mono">{shortHash(packet.lease.walletAddress)}</div>
              </div>
              <div className="info-card">
                <div className="k">Per-Tx Limit</div>
                <div className="v">{formatUsd(packet.lease.perTxUsd)}</div>
              </div>
              <div className="info-card">
                <div className="k">Daily Budget</div>
                <div className="v">{formatUsd(packet.lease.dailyBudgetUsd)}</div>
              </div>
              <div className="info-card">
                <div className="k">Expires</div>
                <div className="v">{formatTimestamp(packet.lease.expiresAt)}</div>
              </div>
              <div className="info-card">
                <div className="k">Allowed Assets</div>
                <div className="v">{packet.lease.allowedAssets.join(', ')}</div>
              </div>
              <div className="info-card">
                <div className="k">Allowed Protocols</div>
                <div className="v">{packet.lease.allowedProtocols.join(', ')}</div>
              </div>
              <div className="info-card">
                <div className="k">Allowed Actions</div>
                <div className="v">{packet.lease.allowedActions.join(', ')}</div>
              </div>
            </div>
          </div>

          <div className="card">
            <h2>Policy Checks ({packet.checks.filter((check) => check.ok).length}/{packet.checks.length} Passed)</h2>
            <div className="check-list">
              {packet.checks.map((check) => (
                <div key={check.id} className={`check-item ${check.ok ? 'pass' : 'fail'}`}>
                  <div className="check-header">
                    <span className="check-icon">{check.ok ? '✓' : '✗'}</span>
                    <span className="check-label">{check.label}</span>
                  </div>
                  <div className="check-note">{check.note}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h2>Execution Receipt</h2>
            <div className="info-grid">
              <div className="info-card">
                <div className="k">Status</div>
                <div className="v">{titleCase(packet.receipt.status)}</div>
              </div>
              <div className="info-card">
              <div className="k">Network</div>
              <div className="v">{humanizeExecutionNetwork(packet.execution.network)}</div>
              </div>
              <div className="info-card">
                <div className="k">Spent This Tx</div>
                <div className="v">{formatUsd(packet.receipt.spentUsd)}</div>
              </div>
              <div className="info-card">
                <div className="k">Spent 24h</div>
                <div className="v">{formatUsd(packet.usage.spent24hUsd)}</div>
              </div>
              <div className="info-card">
                <div className="k">Tx Hash</div>
                <div className="v mono">{shortHash(packet.execution.txHash)}</div>
              </div>
              <div className="info-card">
                <div className="k">Explorer</div>
                <div className="v">
                  {packet.execution.explorerUrl ? (
                    <a href={packet.execution.explorerUrl} style={{ color: 'var(--lime)' }}>View Tx</a>
                  ) : (
                    '—'
                  )}
                </div>
              </div>
            </div>
          </div>
        </>
      ) : (
        <EmptyProof lease={lease} />
      )}

      <div className="card">
        <h2>Recent Rounds</h2>
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
              rounds.slice(0, 8).map((round) => (
                <tr key={`${round.generatedAt}-${round.requestId}`}>
                  <td>{formatTimestamp(round.generatedAt)}</td>
                  <td>
                    <span className={`pill ${toneForOutcome(round.outcome)}`}>
                      {titleCase(round.outcome)}
                    </span>
                  </td>
                  <td className="mono">{shortHash(round.txHash)}</td>
                  <td style={{ fontSize: '11px', color: 'var(--s1)' }}>{roundSummaryLabel(round)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={4} style={{ color: 'var(--s2)' }}>No rounds recorded yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="footer">
        Contract-backed proof · {packet?.execution.explorerUrl ? <a href={packet.execution.explorerUrl}>View latest tx</a> : 'No broadcasted tx in the latest packet'}
      </div>
    </div>
  );
}
