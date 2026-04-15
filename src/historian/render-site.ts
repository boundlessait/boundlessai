import fs from "node:fs";
import path from "node:path";
import { ProofPacket } from "../core/types.js";
import { RoundArtifactIndexEntry } from "../runtime/store.js";
import { buildProofDashboardHtml, writeProofDashboardHtml } from "./render-html.js";

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderRecentRounds(index: RoundArtifactIndexEntry[]): string {
  return index
    .slice(0, 8)
    .map(
      (entry) => `
        <tr>
          <td>${escapeHtml(entry.generatedAt)}</td>
          <td>${escapeHtml(entry.outcome)}</td>
          <td class="mono">${escapeHtml(entry.txHash ?? "none")}</td>
          <td>${escapeHtml(entry.summary)}</td>
        </tr>
      `
    )
    .join("");
}

export function buildSubmissionHtml(input: {
  packet: ProofPacket;
  index: RoundArtifactIndexEntry[];
  proofDashboardFileName?: string;
}): string {
  const { packet, index } = input;
  const proofDashboardFileName = input.proofDashboardFileName ?? "proof-dashboard.html";

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${escapeHtml(packet.product)} Submission Surface</title>
    <style>
      :root { --bg: #f5f2ea; --panel: #fffaf0; --ink: #1a1916; --muted: #656055; --line: #d7cfbe; --accent: #9b3d24; }
      * { box-sizing: border-box; }
      body { margin: 0; font-family: Georgia, "Times New Roman", serif; color: var(--ink); background: radial-gradient(circle at top right, #fff5dc 0, transparent 36%), linear-gradient(180deg, #ede4d3 0%, var(--bg) 100%); }
      .wrap { width: min(1220px, calc(100vw - 36px)); margin: 24px auto 56px; }
      .hero, .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 24px; box-shadow: 0 12px 36px rgba(40, 31, 15, 0.08); }
      .hero { padding: 32px; }
      .eyebrow { display: inline-block; padding: 7px 12px; border: 1px solid var(--line); border-radius: 999px; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
      h1, h2 { margin: 0; }
      h1 { margin-top: 16px; font-size: 48px; line-height: 0.95; }
      h2 { font-size: 22px; margin-bottom: 12px; }
      p, li { color: var(--muted); line-height: 1.6; }
      .hero-grid, .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; }
      .hero-grid { margin-top: 24px; }
      .metric { grid-column: span 3; padding: 16px; border-radius: 18px; background: #fff; border: 1px solid var(--line); }
      .metric .value { font-size: 28px; font-weight: 700; color: var(--accent); }
      .metric .label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }
      .grid { margin-top: 18px; }
      .panel { padding: 24px; }
      .span-5 { grid-column: span 5; }
      .span-6 { grid-column: span 6; }
      .span-7 { grid-column: span 7; }
      .span-12 { grid-column: 1 / -1; }
      table { width: 100%; border-collapse: collapse; font-size: 14px; }
      th, td { padding: 10px 8px; border-top: 1px solid var(--line); text-align: left; vertical-align: top; }
      th { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
      .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
      .link-row a { display: inline-block; margin-right: 10px; margin-bottom: 10px; padding: 10px 14px; border-radius: 999px; text-decoration: none; border: 1px solid var(--line); background: #fff; color: var(--ink); }
      @media (max-width: 960px) { .metric, .span-5, .span-6, .span-7 { grid-column: 1 / -1; } h1 { font-size: 34px; } }
    </style>
  </head>
  <body>
    <div class="wrap">
      <section class="hero">
        <div class="eyebrow">X Layer Human Track Submission</div>
        <h1>${escapeHtml(packet.product)}</h1>
        <p>
          A human-issued lease defines exactly what an agent can do on X Layer: which wallet, which assets, which protocols,
          how much per tx, how much per day, and when the authority expires. Each round produces a receipt with policy checks,
          the lease decision, and optional onchain proof.
        </p>
        <div class="hero-grid">
          <div class="metric"><div class="label">Consumer</div><div class="value">${escapeHtml(packet.lease.consumerName)}</div></div>
          <div class="metric"><div class="label">Outcome</div><div class="value">${escapeHtml(packet.decision.outcome)}</div></div>
          <div class="metric"><div class="label">Trust Zone</div><div class="value">${escapeHtml(packet.decision.trustZone)}</div></div>
          <div class="metric"><div class="label">Execution</div><div class="value">${escapeHtml(packet.execution.status)}</div></div>
        </div>
      </section>

      <section class="grid">
        <article class="panel span-7">
          <h2>What This Project Is</h2>
          <p>
            This is not another bot. It is a lease layer for autonomous execution. Humans issue short-lived authority envelopes,
            and agents only execute while the request stays inside those constraints.
          </p>
          <ul>
            <li>Lease envelope covers wallet, budget, assets, protocols, counterparty, and expiry.</li>
            <li>Execution is gated before funds move, not only after logs exist.</li>
            <li>The same lease can be audited by operators, judges, and downstream services.</li>
            <li>Every round writes a receipt plus a proof packet.</li>
          </ul>
        </article>

        <article class="panel span-5">
          <h2>Latest Round</h2>
          <p><strong>Request:</strong> ${escapeHtml(packet.request.assetPair)} via ${escapeHtml(packet.request.venueHint)}</p>
          <p><strong>Requested:</strong> $${packet.request.notionalUsd}</p>
          <p><strong>Final:</strong> $${packet.decision.finalNotionalUsd}</p>
          <p><strong>Rationale:</strong> ${escapeHtml(packet.decision.rationale)}</p>
          <div class="link-row" style="margin-top:14px;">
            <a href="./${escapeHtml(proofDashboardFileName)}">Open Proof Dashboard</a>
            <a href="./live-proof-latest.json">Open Latest JSON</a>
          </div>
        </article>

        <article class="panel span-6">
          <h2>Lease Envelope</h2>
          <p><strong>Lease ID:</strong> <span class="mono">${escapeHtml(packet.lease.leaseId)}</span></p>
          <p><strong>Wallet:</strong> <span class="mono">${escapeHtml(packet.lease.walletAddress ?? "unscoped")}</span></p>
          <p><strong>Assets:</strong> ${packet.lease.allowedAssets.map(escapeHtml).join(", ")}</p>
          <p><strong>Protocols:</strong> ${packet.lease.allowedProtocols.map(escapeHtml).join(", ")}</p>
          <p><strong>Budget:</strong> $${packet.lease.perTxUsd} per tx / $${packet.lease.dailyBudgetUsd} per day</p>
          <p><strong>Expires:</strong> ${escapeHtml(packet.lease.expiresAt)}</p>
        </article>

        <article class="panel span-6">
          <h2>How Judges Should Read It</h2>
          <ul>
            <li><strong>OnchainOS path:</strong> wallet, quote, trade, and receipt flow are in the main path.</li>
            <li><strong>X Layer fit:</strong> the lease specifically scopes X Layer routes and produces X Layer receipts.</li>
            <li><strong>Human interaction:</strong> humans issue, pause, review, and revoke authority without giving full wallet access.</li>
            <li><strong>Completeness:</strong> lease file, request, decision, receipt, proof dashboard, and submission site all exist.</li>
          </ul>
        </article>

        <article class="panel span-12">
          <h2>Recent Lease Rounds</h2>
          <table>
            <thead><tr><th>Generated</th><th>Outcome</th><th>Tx</th><th>Summary</th></tr></thead>
            <tbody>${renderRecentRounds(index)}</tbody>
          </table>
        </article>
      </section>
    </div>
  </body>
</html>`;
}

export function buildSiteIndexHtml(): string {
  return `<!doctype html>
<html lang="en">
  <head><meta charset="utf-8" /><meta http-equiv="refresh" content="0; url=./submission.html" /><title>Boundless</title></head>
  <body><p>Redirecting to <a href="./submission.html">submission.html</a>...</p></body>
</html>`;
}

export function writeSubmissionSite(input: { packet: ProofPacket; index: RoundArtifactIndexEntry[]; baseDir: string }): { proofDashboardPath: string; submissionPath: string; indexPath: string } {
  const proofDashboardPath = writeProofDashboardHtml({ packet: input.packet, index: input.index, outputPath: path.resolve(input.baseDir, "proof-dashboard.html") });
  const submissionPath = path.resolve(input.baseDir, "submission.html");
  fs.writeFileSync(submissionPath, `${buildSubmissionHtml({ packet: input.packet, index: input.index, proofDashboardFileName: path.basename(proofDashboardPath) })}\n`);
  const indexPath = path.resolve(input.baseDir, "index.html");
  fs.writeFileSync(indexPath, `${buildSiteIndexHtml()}\n`);
  return { proofDashboardPath, submissionPath, indexPath };
}
