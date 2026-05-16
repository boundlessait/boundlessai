# Boundless Submission Form Answers

## Project Name

Boundless

## One-Line Description

Boundless is the control layer between Kite Passport delegation and real-money execution: policy first, agent runs second, proof always.

## Detailed Explanation

Boundless exists for one specific gap in the agent stack.

Kite Passport gives an agent delegated payment permission and session scope. That solves identity and authorization. It does not fully answer whether a specific request should continue under the current budget, venue, operator posture, and proof requirements.

Boundless adds that missing runtime governance layer.

The product flow is:

1. A human defines a policy envelope in `/submission`
   - governed wallet
   - per-transaction limit
   - daily budget
   - allowed assets
   - allowed protocols
   - operator mode
   - expiry

2. In `/member-test`, the user mirrors the active Kite Passport session boundary
   - session id
   - payer
   - budget
   - expiry

3. Boundless runs the request through local policy checks before the payment continues
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

4. If the request is inside policy, the paid path can continue. If it is outside policy, the request is blocked before settlement.

5. `/proof` shows the full chain in one place
   - session boundary
   - request
   - decision
   - payment result
   - receipt / proof

What we built in this submission:

- a deployed Boundless web app with three surfaces:
  - `/submission`
  - `/member-test`
  - `/proof`
- wallet-signed policy actions for the operator surface
- persisted Kite Passport session boundary handling
- local policy enforcement before x402 execution continues
- proof packet generation for both allowed and blocked outcomes
- a judge-ready presentation deck and updated submission assets

What is important technically is that Boundless does not pretend to replace Kite Passport. It is layered above Passport.

Kite Passport handles delegated payment permission.
Boundless decides the exact rules under which that payment is allowed.

That is why the project fits agentic trading and portfolio management: it is the missing control layer before autonomous financial actions execute.

## Repository Link

https://github.com/boundlessait/boundlessai

## Live Demo

https://unboundai.xyz

## Key Routes

- https://unboundai.xyz/submission
- https://unboundai.xyz/member-test
- https://unboundai.xyz/proof

## Presentation Deck

`deliverables/boundless-kite-hackathon-deck.pptx`

## Demo Video

Add your uploaded public video URL here before submitting the form.

## Track Fit

Boundless is a runtime governance layer for agentic finance. It sits directly before autonomous trading or payment execution and turns broad delegated authority into bounded, reviewable, and provable execution rules.

## Repo Proof Pointers

- Judge README: `README.md`
- Proof packet: `examples/live-proof-latest.json`
- Architecture notes: `docs/ARCHITECTURE.md`
- Demo script: `docs/DEMO_VIDEO_SCRIPT.md`
- Deck: `deliverables/boundless-kite-hackathon-deck.pptx`
