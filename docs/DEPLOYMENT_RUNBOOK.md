# Deployment Runbook

## Local

1. Copy `.env.example` to `.env.local`
2. Reuse the same X Layer env values already used by `xlayer-strategy-office`
3. If local networking needs it, use proxy `7890`
4. Run:

```bash
npm install
npm run lease:issue
npm run preflight:treasury
cd ../xlayer-strategy-office
npm install
npm run round:live
```

## Server / OpenClaw

- do not set proxy
- keep `LEASE_EXECUTION_MODE=live`
- reuse the same Agentic Wallet login or settlement key path already working on the server
- schedule `cd /opt/xlayer-strategy-office && npm run round:live`

## Submission surfaces

- run the Next app in `xlayer-trust-leases`
- open `http://127.0.0.1:3000/submission`
- open `http://127.0.0.1:3000/proof`
