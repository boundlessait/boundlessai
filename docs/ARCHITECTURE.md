# Boundless Architecture

## Core Thesis

Boundless inserts a runtime governance layer between delegated payment permission and settlement.

```text
Kite Passport session
-> Boundless policy envelope
-> payment check
-> allow or block
-> proof packet
```

## System Layers

### 1. Kite Passport

Handles:

- identity
- delegated payment permission
- session scope

### 2. Boundless Policy Layer

Handles:

- governed wallet
- per-transaction limit
- daily budget
- allowed assets
- allowed protocols
- operator mode
- expiry

### 3. Member Payment Check

`/member-test` mirrors the active session boundary and prepares a real x402 request.

Before the paid path continues, Boundless checks:

- lease status
- lease expiry
- wallet scope
- reason required
- action allowlist
- asset allowlist
- protocol allowlist
- counterparty allowlist
- per-tx budget
- daily budget

### 4. Proof Layer

`/proof` renders:

- session boundary
- request
- decision
- payment result
- receipt / proof

## Main Modules

### `app/api/passport-session/route.ts`

Stores the Kite Passport session boundary used by the product surfaces.

### `app/api/x402-payment/route.ts`

Runs Boundless policy checks before the payment path is allowed to continue.

### `app/api/demo-x402-weather/route.ts`

Provides a demo x402 relay route so the paid flow can be exercised in product.

### `components/submission-page.tsx`

Operator-facing policy console.

### `components/member-test-page.tsx`

Session boundary, request preparation, and paid request flow.

### `components/proof-page.tsx`

Unified proof surface for session, decision, and receipt state.

### `lib/kite-passport-session.ts`

Local persistence for saved session boundary metadata.

### `lib/proof-artifacts.ts`

Writes proof packets and receipt artifacts.

### `lib/site-data.ts`

Merges current proof data, operator state, controller state, and the current lease snapshot for rendering.

## Artifact Outputs

Generated state lives under `data/trust-leases/`:

- `leases/active-lease.json`
- `live-proof-latest.json`
- `proof-dashboard.html`
- `submission.html`

Committed examples live under `examples/`.

## Engineering Choice

Boundless does not rebuild Passport. It layers policy and proof above Passport.

That is the correct product boundary:

- Passport owns delegated permission
- Boundless owns runtime governance
- Proof makes both outcomes legible to humans
