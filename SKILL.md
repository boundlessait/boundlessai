---
name: xlayer-trust-leases
description: Use this skill when an agent needs bounded authority with pre-execution governance — enforce budget limits, asset/protocol whitelists, and policy checks before allowing any on-chain action on X Layer.
---

# X Layer Trust Leases

Use this skill to enforce bounded authority for AI agents on X Layer.

## When to use it

- An agent wants to execute a trade but needs pre-authorization.
- The caller wants to enforce daily/transaction budget limits.
- The caller wants asset, protocol, or action whitelists.
- The caller wants a complete audit trail of every agent decision.
- The caller wants "human-in-the-loop" oversight for high-risk actions.

## Required capabilities

Use X Layer as the factual layer:

- OnchainOS for token resolution and quote fetching
- Controller contract for lease state and receipt tracking
- Local or on-chain proof artifacts for audit

Do not invent lease terms, budget limits, or policy rules.

## Workflow

1. **Extract lease context:**
   - lease ID (if already issued)
   - proposed action (swap, bridge, stake, etc.)
   - from token, to token, amount
   - target protocol
   - counterparty address
2. **Load or issue lease:**
   - If lease exists, verify it's valid and not expired.
   - If no lease, prompt caller for lease issuance parameters.
3. **Run policy checks:**
   - Budget check: per-tx limit and daily budget
   - Asset check: from/to tokens in allowed list
   - Protocol check: target venue in allowed list
   - Action check: operation type in allowed list
   - Counterparty check: recipient in allowlist
4. **Compute decision:**
   - `approve` - all checks pass, proceed
   - `resize` - within budget but exceeds per-tx limit
   - `block` - policy violation or budget exceeded
   - `review` - ambiguous case, needs human review
5. **Return proof packet:**
   - Full lease envelope
   - Policy check results
   - Decision rationale
   - Execution receipt (if approved)

## Fixed output

Always return these sections in order:

1. `Lease envelope` - full terms, budget, whitelists
2. `Proposed action` - trade details, amount, venue
3. `Policy checks` - budget, asset, protocol, action, counterparty
4. `Decision` - approve / resize / block / review
5. `Rationale` - why the decision was made
6. `Proof packet` - complete audit trail
7. `Agent-ready summary` - one-line decision with next step

## Decision guidance

- Use `approve` only when all policy checks pass within budget.
- Use `resize` when the trade exceeds per-tx limit but fits daily budget.
- Use `block` when any policy check fails or budget is exhausted.
- Use `review` when the operator is in "review" mode or action is ambiguous.

## Integration with other skills

- **Route Referee** → Evaluate which route is best BEFORE trust lease check
- **Execution Proof Kit** → Generate proof AFTER execution succeeds
- **Wallet Risk Sentinel** → Check wallet posture BEFORE trust lease check

Workflow: Route Referee → **Trust Leases** → Execution Proof Kit