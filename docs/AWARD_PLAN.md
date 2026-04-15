# Award Plan

## Goal

Turn X Layer Trust Leases from a strong idea with partial proof into a judge-ready submission that can compete for placement.

## What is real now

- `xlayer-strategy-office` now reads the trust lease before it can execute.
- A `strategy-office` round now writes fresh trust-lease artifacts back into `data/trust-leases/`.
- An expired lease now stays expired and blocks execution until a new lease is issued.
- The Next.js dashboard reads current runtime files instead of fixed demo states.

## What judges need to see

1. A human issues a lease.
2. `strategy-office` submits a real round against that lease.
3. The lease can block an expired request and can allow a valid request.
4. The dashboard and proof page immediately reflect the new round.
5. At least one recent lease-approved X Layer tx remains visible as proof of successful execution.

## Submission-critical checklist

1. Re-issue a fresh lease before recording final demo.
2. Run one blocked round with an expired or paused lease.
3. Run one successful round with an active lease.
4. Capture fresh screenshots from `/submission` and `/proof`.
5. Update README proof snapshot with the exact latest blocked round date and latest successful tx date.
6. Record a 60-90 second demo using the real bridge flow.
7. Keep all dates, tx hashes, and wallet addresses exact and consistent across README, form answers, and video.

## Scoring priorities

- **Product completeness:** show issuance, gate, decision, receipt, proof UI.
- **X Layer fit:** keep chain ID 196, wallet, explorer links, and OnchainOS path explicit.
- **Human track differentiation:** emphasize bounded authority, not another trading bot.
- **Proof credibility:** show both success and failure states from the same runtime.

## Nice-to-have before deadline

- Regenerate static HTML artifacts after each live round.
- Add a judge table to the README with live dashboard route, repo, wallet, tx proof, and docs.
- Add one architecture diagram that explicitly shows `strategy-office -> trust lease gate -> X Layer execution`.
