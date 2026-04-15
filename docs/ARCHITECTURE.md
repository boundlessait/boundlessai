# Architecture

## Core idea

X Layer Trust Leases inserts a bounded authority envelope into the execution path:

```text
human issues lease
-> consumer proposes request
-> lease validates scope and budget
-> approved request uses reused X Layer execution path
-> receipt and proof are written
```

## Main modules

### `src/lease/policy.ts`

Builds and evaluates the lease envelope:
- wallet scope
- asset allowlist
- protocol allowlist
- counterparty allowlist
- per-tx budget
- daily budget
- expiry
- route quality and token safety gates

### `src/runtime/trust-lease-agent.ts`

Runs one lease round:
- loads operator posture
- reads treasury state
- derives a trade candidate
- builds a structured request
- runs lease checks
- executes if allowed
- writes receipt and proof packet

### `src/onchainos/cli.ts`

Reused from `xlayer-strategy-office`.

Provides:
- wallet status
- wallet balance
- token scan
- swap quote
- swap execute

### `src/portfolio/manager.ts`

Reused from `xlayer-strategy-office`.

Provides:
- wallet parsing
- drift detection
- trade candidate construction
- route quoting
- live execution

### `src/historian/*`

Produces:
- latest proof JSON
- round history
- proof dashboard HTML
- submission HTML

## Runtime artifacts

Generated under `data/trust-leases/`:

- `leases/active-lease.json`
- `receipts/*.json`
- `rounds/*.json`
- `live-proof-latest.json`
- `proof-dashboard.html`
- `submission.html`

Committed submission samples under `examples/`:

- `active-lease.sample.json`
- `latest-receipt.sample.json`
- `latest-round.sample.json`
- `live-proof-latest.json`
- `proof-dashboard.sample.html`
- `submission.sample.html`

## Design choice

This project intentionally reuses working execution code instead of rebuilding X Layer execution from scratch.

That is the correct engineering tradeoff for a hackathon submission:
- less integration risk
- more real proof
- faster path to a submission-grade repo
