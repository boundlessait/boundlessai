# Boundless Demo Video Script

## Length

60 to 90 seconds.

## Goal

Show that Boundless is the runtime governance layer that sits between Kite Passport delegation and real-money execution.

## Route Order

1. `/submission`
2. `/member-test`
3. `/proof`

## Shot 1 - Submission / policy envelope

Open:

- `https://unboundai.xyz/submission`

Narration:

> Boundless is the control layer between agent intent and real-money execution.
> Before an agent can spend, a human defines the policy envelope first.

What to point at:

- governed wallet
- per-tx limit
- daily budget
- operator mode
- `Save Policy`

## Shot 2 - Member Test / session boundary

Open:

- `https://unboundai.xyz/member-test`

Narration:

> Here we mirror the active Kite Passport session boundary: session budget, payer, and expiry.

What to point at:

- session boundary section
- service URL
- expected spend
- reason field

## Shot 3 - Prepare x402 request

Action:

- click `Prepare x402 Request`

Narration:

> Boundless checks the payment locally before it allows the request to continue.

What to point at:

- returned challenge
- merchant
- amount
- payTo

## Shot 4 - Complete paid request

Action:

- click `Complete Paid Request`

Narration:

> Once the request is inside policy, the paid action completes and Boundless writes proof.

## Shot 5 - Proof

Open:

- `https://unboundai.xyz/proof`

Narration:

> The proof page shows the full chain: session, request, decision, payment result, and receipt.

What to point at:

- Passport Session Boundary
- request
- decision
- payment result
- proof / receipt

## Closing Line

> Kite Passport lets the agent pay. Boundless decides the exact rules under which that payment is allowed.
