# OpenClaw Runbook

## Goal

Run X Layer Trust Leases as a lease issuer and pre-execution gateway for the shared `xlayer-strategy-office` Agentic Wallet flow.

## Environment

- Server / OpenClaw: **no proxy**
- Local machine: proxy `7890` is acceptable if GitHub or OKX routing needs it
- Reuse the same X Layer / Agentic Wallet setup already working for `xlayer-strategy-office`

## Required env

- `XLAYER_RPC_URL`
- `XLAYER_CHAIN_ID=196`
- `XLAYER_EXPLORER_BASE_URL`
- `XLAYER_SETTLEMENT_TOKEN_ADDRESS`
- `XLAYER_SETTLEMENT_TOKEN_SYMBOL`
- `XLAYER_SETTLEMENT_TOKEN_DECIMALS`
- one of:
  - `XLAYER_TREASURY_ADDRESS` with logged-in Agentic Wallet
  - or `XLAYER_SETTLEMENT_PRIVATE_KEY`

## Lease-specific env

- `LEASE_EXECUTION_MODE=live`
- `LEASE_CONSUMER_NAME=strategy-office`
- `LEASE_TARGET_ALLOCATIONS=USDT0:65,USDC:25,OKB:10`
- `LEASE_PER_TX_USD=5`
- `LEASE_DAILY_BUDGET_USD=20`
- `LEASE_ALLOWED_PROTOCOLS=okx-aggregator,quickswap`
- `LEASE_ALLOWED_COUNTERPARTIES=okx-aggregator,quickswap`

## Commands

```bash
cd /path/to/xlayer-trust-leases
npm install
npm run check
npm run lease:issue
npm run preflight:treasury
npm run operator:resume -- "openclaw runtime"

cd /path/to/xlayer-strategy-office
npm install
npm run check
npm run round:live
```

## Runtime loop

A practical OpenClaw loop is:

```bash
cd /path/to/xlayer-strategy-office
npm run round:live
```

Run it every 10-15 minutes.

## Outputs

- `data/trust-leases/live-proof-latest.json`
- `data/trust-leases/receipts/*.json`
- `../xlayer-strategy-office/data/office/live-proof-latest.json`

For interactive review, run the Next app in `xlayer-trust-leases` and open `/submission` plus `/proof`.
