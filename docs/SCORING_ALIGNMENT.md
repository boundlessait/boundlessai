# Scoring Alignment

## Agentic Trading & Portfolio Management

Boundless is not a trading strategy. It is the runtime control layer that sits before autonomous trading or payment execution.

That still fits the track directly, because agentic trading systems need:

- bounded wallet authority
- explicit spend limits
- human review modes
- proof for both allowed and blocked actions

## Kite Fit

Kite Passport handles:

- identity
- delegated payment permission
- session scope

Boundless adds:

- per-request policy enforcement
- operator controls (`active`, `review`, `paused`)
- policy-backed payment checks
- proof and receipts after the decision

## Product Completeness

The shipped product includes:

- `/submission` for policy definition
- `/member-test` for session boundary + payment check flow
- `/proof` for session, request, decision, payment result, and receipt
- wallet-signed policy actions
- persisted proof packet artifacts

## Proof Quality

The repo includes:

- latest proof packet JSON
- current policy JSON
- live screenshots
- presentation deck
- demo script
- submission form answers

## Judge Memory Target

The strongest takeaway should be:

> Kite Passport lets the agent pay. Boundless decides the exact rules under which that payment is allowed.
