# Submission Form Answers

## Project Name & One-Line Description

X Layer Trust Leases — A pre-execution lease layer for X Layer agents that bounds wallet scope, budget, protocol, counterparty, and expiry before autonomous execution is allowed.

## Project Highlights

X Layer Trust Leases is not another trading bot. It is a human-track primitive for bounded agent authority.

A human issues a lease. The lease defines wallet scope, allowed assets, allowed protocols, allowed counterparties, per-tx limits, daily budget, and expiry. The agent submits a request against that lease. Only requests that stay inside the lease envelope can execute.

The project now wires the trust lease directly into the live `xlayer-strategy-office` round path. A strategy-office round reads the trust lease before it can broadcast, and the same round writes explicit trust-lease receipts plus a judge-facing proof dashboard and submission page. The web app now also exposes an in-app Operator Console for issue, pause, review, resume, revoke, run, and proof refresh actions, so the governance loop is operable inside the product instead of being trapped in CLI-only demos.

The project also now includes a dedicated X Layer controller contract. In contract-driven mode, lease state, operator posture, and the latest receipt anchor are mirrored onchain, while the dashboard reads that controller state back into the live UI. That means the product is no longer only a local proof generator; it can operate as a hybrid web app with X Layer as the state authority for the core governance primitive.

## Your Track

X Layer Arena

## Team Members & Contact Information

Richard — builder — ritsuyan4763@gmail.com

## Agentic Wallet Address

0xdbc8e35ea466f85d57c0cc1517a81199b8549f04

## GitHub Repository Link

https://github.com/richard7463/xlayer-trust-leases

## OnchainOS Usage

This project uses the same OnchainOS-backed X Layer execution path already proven in local live projects in this workspace.

- OnchainOS wallet balance lookup for treasury state
- OnchainOS swap quote for route viability
- OnchainOS swap execute for live X Layer execution when the lease approves the request
- X Layer tx hash and explorer-linked receipt as proof output

The lease is the pre-execution gate sitting above that path, and the latest runtime proof shows that an expired lease now blocks strategy-office execution before broadcast.

## Demo Video Link

Fill after upload.

## X Post Link

Fill after posting.
