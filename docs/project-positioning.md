# Project Positioning

X Layer Trust Leases is a reusable pre-execution governance skill for X Layer agents.

## Core Claim

AI agents need bounded authority. Before any on-chain action, the agent must present a lease with explicit budget limits, asset whitelists, and policy rules. Without a valid lease, no execution happens.

## What The Skill Does

- receives one agent action intent
- checks against active lease budget (daily limit, per-tx limit)
- validates asset, protocol, action, and counterparty whitelists
- runs policy checks (reason required, proof required)
- returns one final decision: `approve`, `resize`, `block`, or `review`
- emits a complete proof packet with audit trail

## Why It Fits Skills Arena

This project is not a consumer app.
It is a modular governance layer that any agent can call before execution.

## Why It Is Stronger Than A Simple Budget Wrapper

A simple budget wrapper only checks if amount < limit.
Trust Leases returns:

- a complete lease envelope with all terms
- policy check results (asset, protocol, action, counterparty)
- a decision with rationale
- a proof packet for audit trail
- integration with other skills (Route Referee, Execution Proof Kit)

## Prize Strategy

Primary target:

- `Skills Arena`

Strong special-prize angles:

- `Best governance / compliance tool` - trust leases as pre-execution guardrails
- `Best security integration` - bounded authority prevents unauthorized spending
- `Best X Layer integration` - on-chain lease state + off-chain proof artifacts

The project can explicitly demonstrate how agents get bounded authority on X Layer, with live proof of budget enforcement and policy checks.