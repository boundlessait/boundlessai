# Contract Runbook

## Goal

Deploy the `TrustLeaseController` contract to X Layer and enable contract-driven lease, operator, and receipt state.

## Current mainnet deployment

- Controller: `0xc2220b67264cd7582bbccb8a62ef4e34228fa0ca`
- Controller owner: `0x3f665386b41Fa15c5ccCeE983050a236E6a10108`
- Lease issue mirror timestamp: `2026-04-15T03:04:47Z`
- Latest receipt anchor tx: `0x6e5b357ca20ccd6deea39437a3b959b5af299b4115cbb8ae772739b3c4df39b7`

## Contract project

The Solidity project lives under:

`contracts/`

Useful commands from the repo root:

```bash
npm run contracts:compile
npm run contracts:test
npm run contracts:deploy:testnet
npm run contracts:deploy:mainnet
npm run contracts:deploy:guard:testnet
npm run contracts:deploy:guard:mainnet
```

## Required environment

Add to `.env.local`:

```bash
LEASE_CHAIN_SYNC_ENABLED=true
LEASE_CONTROLLER_ADDRESS=0x...
LEASE_CONTROLLER_WRITER_PRIVATE_KEY=0x...
LEASE_CONTROLLER_DEPLOY_BLOCK=57453029
LEASE_CONTROLLER_ARTIFACT_BASE_URI=https://your-proof-host.example/trust-leases
```

Fallback behavior:
- if `LEASE_CHAIN_SYNC_ENABLED=false`, the project stays in local artifact mode
- if `LEASE_CONTROLLER_ADDRESS` is missing, the dashboard falls back to local runtime state only

Hosted behavior:
- Vercel can issue leases and change operator posture directly through `app/api/control/route.ts` when `LEASE_CONTROLLER_WRITER_PRIVATE_KEY` is configured
- hosted `run-round` is still intentionally disabled, because live execution and artifact writes still require a writable runner

## What syncs onchain

1. Lease issuance
- `scripts/issue-lease.ts`
- mirrors the newly issued lease into `TrustLeaseController.issueLease`

2. Lease revoke / expire
- `scripts/revoke-lease.ts`
- mirrors revoke into `TrustLeaseController.setLeaseStatus`

3. Operator posture
- `scripts/operator-command.ts`
- mirrors pause / review / resume into `TrustLeaseController.setOperatorMode`

4. Receipt anchor
- `scripts/live-round.ts`
- after writing the latest local proof packet, anchors:
  - leaseId
  - requestId
  - decision outcome
  - execution status
  - spentUsd
  - txHash
  - proofHash
  - artifactUri

## Hard-Guard Contract Mode (Vault)

If you want strict spend control (funds locked in contract, not loose EOA wallet), deploy guard mode:

1. Set env:

```bash
BOUNDLESS_VAULT_OWNER=0xYourEOA
LEASE_CONSUMER_NAME=strategy-office
LEASE_OPERATOR_NAME=human-principal
```

2. Deploy:

```bash
npm run contracts:deploy:guard:mainnet
```

This deploys:
- `TrustLeaseController`
- `BoundlessVault`
- and auto-authorizes vault as controller executor (`setExecutor(vault, true)`).

3. Configure vault after deploy:
- set member wallet policy (`setMemberPolicy`) with per-tx and daily budget
- allow token contracts (`setAllowedAsset`)
- allow protocol target contracts (`setAllowedProtocol`)
- set lease context to active lease id (`setLeaseContext`)
- deposit funds into vault (`depositToken`)

In this mode, budget checks are enforced by `enforceAndConsume` onchain before each vault execution.

## Current architecture split

Onchain:
- active lease state
- operator posture
- latest receipt anchor per consumer
- budget usage counters

Offchain:
- full proof packet JSON
- full checks array
- rendered proof dashboard HTML
- submission page HTML
- live round execution orchestration

This split is intentional. The chain stores the primitive and immutable anchors. The app and artifact layer keep the high-density proof surface.

## Smoke-test flow

After deployment and env setup:

```bash
npm run lease:issue
npm run operator:review -- \"smoke test\"
npm run operator:resume -- \"restore\"
npm run round:live
```

Expected result:
- local files update under `data/trust-leases`
- controller tx hashes are printed in script output
- dashboard reads controller-backed lease/operator state on the next page load
