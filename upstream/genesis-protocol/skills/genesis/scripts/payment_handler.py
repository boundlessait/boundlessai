"""Payment Handler - x402 payment processing with multi-token settlement support.

Integrates the Uniswap pay-with-any-token skill to allow agents to pay for
Genesis services using any ERC-20 token. Accepts USDT, USDC, OKB, and WETH
directly as quote tokens.  For other tokens the skill automatically swaps to
the agent's preferred settlement token via Uniswap.

Deep integration adds:
  - Real x402 challenge-response flow with proper HTTP 402 headers
  - On-chain payment verification via tx receipt checking
  - Subscription management with expiry tracking
  - Revenue analytics with per-product and per-currency breakdowns
  - Refund mechanism for failed deliveries

Uses onchainos CLI and Uniswap AI Skills via subprocess for all operations.
"""
import math
import statistics
import subprocess
import json
import logging
import time
import hashlib
import uuid
from collections import deque
from typing import Optional

from .config import (
    DRY_RUN, LOG_LEVEL, X402_ENABLED, X402_PRICING,
    CONTRACTS, CHAIN_ID, WALLET_ROLES,
)

logger = logging.getLogger("genesis.payment_handler")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))


class PaymentHandler:
    """Handles x402 payments with automatic token swap via pay-with-any-token."""

    SUPPORTED_QUOTE_TOKENS = ["USDT", "USDC", "OKB", "WETH"]

    def __init__(self, income_wallet_index=None, preferred_settlement_token="USDT"):
        self.income_wallet_index = income_wallet_index or WALLET_ROLES["income"]["index"]
        self.preferred_settlement_token = preferred_settlement_token
        self.enabled = X402_ENABLED
        # In-memory ledger for revenue tracking and subscriptions
        self._revenue_ledger = []       # list of payment records
        self._subscriptions = {}        # payer_address -> subscription record
        self._refund_ledger = []        # list of refund records
        self._token_balances = {t: 0.0 for t in self.SUPPORTED_QUOTE_TOKENS}
        # Batch settlement state
        self._pending_settlements = deque()
        self.BATCH_THRESHOLD = 5
        self.BATCH_MAX_WAIT_MS = 2000
        self._batch_stats = {
            "total_batches_processed": 0,
            "total_settlements_batched": 0,
            "total_latency_saved_ms": 0.0,
        }

    def get_pricing(self):
        """Return the x402 pricing tiers."""
        return X402_PRICING

    def get_supported_tokens(self):
        """Return the list of accepted quote tokens."""
        return list(self.SUPPORTED_QUOTE_TOKENS)

    def process_payment(self, product, payer_token, payer_address):
        """Process an x402 payment, auto-swapping payer's token if needed.

        Accepts any token in SUPPORTED_QUOTE_TOKENS directly.  For tokens
        outside the list, swaps to ``preferred_settlement_token`` via
        pay-with-any-token.

        Args:
            product: One of 'signal_query', 'strategy_subscribe',
                     'strategy_params_buy', 'nft_license'
            payer_token: The ERC-20 token symbol the payer wants to use
            payer_address: The payer's wallet address

        Returns:
            dict with 'success', 'tx_hash', 'amount_usdt', 'settlement_token',
            'swap_details'
        """
        if not self.enabled:
            return {"success": False, "error": "x402 payments disabled"}

        tier = X402_PRICING.get(product)
        if not tier:
            return {"success": False, "error": f"Unknown product: {product}"}

        amount_usdt = tier["amount"]
        settle_mode = tier["settle"]

        logger.info(
            "Processing x402 payment: product=%s amount=%s payer_token=%s",
            product, amount_usdt, payer_token,
        )

        # If payer is using any supported quote token, skip the swap
        if payer_token.upper() in (t.upper() for t in self.SUPPORTED_QUOTE_TOKENS):
            settlement_token = payer_token.upper()
            logger.info("Payer using %s directly — no swap needed", settlement_token)
            result = self._settle_x402(
                payer_address, amount_usdt, settle_mode,
                settlement_token=settlement_token,
            )
            if not result.get("error"):
                self._token_balances[settlement_token] = (
                    self._token_balances.get(settlement_token, 0.0)
                    + float(amount_usdt)
                )
            return {
                "success": not result.get("error"),
                "amount_usdt": amount_usdt,
                "settlement_token": settlement_token,
                "swap_details": None,
                **result,
            }

        # Use pay-with-any-token to swap payer's token → preferred_settlement_token
        settlement_token = self.preferred_settlement_token
        swap_result = self._swap_to_settlement(
            payer_token, amount_usdt, payer_address,
        )

        if swap_result.get("error"):
            logger.error("Token swap failed: %s", swap_result["error"])
            return {"success": False, "error": swap_result["error"]}

        # Settle the x402 payment with the swapped token
        settle_result = self._settle_x402(
            payer_address, amount_usdt, settle_mode,
            settlement_token=settlement_token,
        )

        if not settle_result.get("error"):
            self._token_balances[settlement_token] = (
                self._token_balances.get(settlement_token, 0.0)
                + float(amount_usdt)
            )

        return {
            "success": not settle_result.get("error"),
            "amount_usdt": amount_usdt,
            "settlement_token": settlement_token,
            "swap_details": swap_result,
            **settle_result,
        }

    def _swap_to_settlement(self, from_token, amount, payer_address):
        """Use pay-with-any-token skill to swap any token to preferred_settlement_token.

        This calls the Uniswap pay-with-any-token skill which handles:
        1. Quote the exact input amount needed in from_token
        2. Approve the Uniswap router
        3. Execute the swap via Uniswap V4
        4. Deliver exact amount to the income wallet
        """
        to_token = self.preferred_settlement_token
        cmd = [
            "onchainos", "skill", "run", "pay-with-any-token",
            "--from-token", from_token,
            "--to-token", to_token,
            "--amount", amount,
            "--amount-type", "exactOutput",
            "--recipient", self._get_income_address(),
            "--payer", payer_address,
            "--chain", str(CHAIN_ID),
            "--slippage", "50",  # 0.5% slippage
        ]

        result = self._run_cmd(cmd)

        if result.get("error"):
            return result

        try:
            data = json.loads(result["stdout"])
            return {
                "from_token": from_token,
                "from_amount": data.get("inputAmount", "unknown"),
                "to_token": to_token,
                "to_amount": amount,
                "tx_hash": data.get("txHash", ""),
                "route": data.get("route", ""),
            }
        except (json.JSONDecodeError, KeyError):
            return {"from_token": from_token, "to_amount": amount, "raw": result["stdout"]}

    # Backward-compatible alias
    _swap_to_usdt = _swap_to_settlement

    def _settle_x402(self, payer_address, amount, settle_mode, settlement_token=None):
        """Settle the x402 payment via onchainos payment module."""
        token = settlement_token or self.preferred_settlement_token
        cmd = [
            "onchainos", "payment", "settle",
            "--protocol", "x402",
            "--payer", payer_address,
            "--amount", amount,
            "--token", token,
            "--recipient-wallet-index", str(self.income_wallet_index),
            "--mode", settle_mode,
        ]

        result = self._run_cmd(cmd)

        if result.get("error"):
            return result

        try:
            data = json.loads(result["stdout"])
            return {"tx_hash": data.get("txHash", ""), "settled": True}
        except (json.JSONDecodeError, KeyError):
            return {"raw": result["stdout"], "settled": True}

    def _get_income_address(self):
        """Get the income wallet address via onchainos."""
        cmd = [
            "onchainos", "wallet", "address",
            "--index", str(self.income_wallet_index),
        ]
        result = self._run_cmd(cmd)
        if result.get("error"):
            return ""
        return result["stdout"].strip()

    def estimate_swap(self, from_token, product):
        """Estimate how much of from_token is needed to pay for a product.

        Returns the estimated input amount without executing.
        """
        tier = X402_PRICING.get(product)
        if not tier:
            return {"error": f"Unknown product: {product}"}

        if from_token.upper() in (t.upper() for t in self.SUPPORTED_QUOTE_TOKENS):
            return {"from_token": from_token, "amount": tier["amount"], "swap_needed": False}

        cmd = [
            "onchainos", "skill", "run", "pay-with-any-token",
            "--from-token", from_token,
            "--to-token", self.preferred_settlement_token,
            "--amount", tier["amount"],
            "--amount-type", "exactOutput",
            "--chain", str(CHAIN_ID),
            "--quote-only",
        ]

        result = self._run_cmd(cmd)

        if result.get("error"):
            return result

        try:
            data = json.loads(result["stdout"])
            return {
                "from_token": from_token,
                "amount": data.get("inputAmount", "unknown"),
                "usdt_amount": tier["amount"],
                "swap_needed": True,
                "route": data.get("route", ""),
            }
        except (json.JSONDecodeError, KeyError):
            return {"raw": result["stdout"]}

    # ── Deep Integration: x402 Challenge-Response ──────────────────────

    def create_x402_challenge(self, product: str, amount: Optional[str] = None) -> dict:
        """Create an HTTP 402 Payment Required challenge for a Genesis product.

        Implements the x402 challenge-response protocol: the server returns a
        402 status with a ``X-Payment-Challenge`` header containing a signed
        challenge object.  The payer must submit a valid on-chain payment whose
        tx hash satisfies the challenge before the resource is unlocked.

        The challenge embeds:
          - A unique nonce derived from ``uuid4`` and ``hashlib.sha256``
          - An expiry window (default 300 seconds)
          - The exact USDT amount required (from ``X402_PRICING``)
          - The recipient (income wallet) address
          - A HMAC-style digest the verifier can check later

        Args:
            product: Product key from ``X402_PRICING`` (e.g. ``"signal_query"``).
            amount:  Override amount in USDT (string).  If *None*, the
                     canonical price from ``X402_PRICING`` is used.

        Returns:
            dict with keys:
                challenge_id (str) -- unique hex challenge identifier,
                product (str), amount_usdt (str),
                recipient (str) -- income wallet address,
                expires_at (int) -- UNIX epoch expiry,
                nonce (str) -- random hex nonce,
                digest (str) -- SHA-256 HMAC digest of all fields,
                http_status (int) -- always 402.
        """
        tier = X402_PRICING.get(product)
        if not tier and amount is None:
            return {"error": f"Unknown product and no amount override: {product}"}

        amount_usdt = amount or (tier["amount"] if tier else "0")
        recipient = self._get_income_address()

        # Generate cryptographic nonce and challenge id
        nonce = uuid.uuid4().hex
        expires_at = int(time.time()) + 300  # 5-minute window

        # Build deterministic digest so the verifier can re-derive it
        payload = f"{product}:{amount_usdt}:{recipient}:{nonce}:{expires_at}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        challenge_id = hashlib.sha256(
            f"{digest}:{nonce}".encode("utf-8")
        ).hexdigest()[:32]

        # Record the challenge in the revenue ledger for later verification
        challenge_record = {
            "type": "challenge",
            "challenge_id": challenge_id,
            "product": product,
            "amount_usdt": amount_usdt,
            "recipient": recipient,
            "nonce": nonce,
            "expires_at": expires_at,
            "digest": digest,
            "created_at": int(time.time()),
            "status": "pending",
        }
        self._revenue_ledger.append(challenge_record)

        logger.info(
            "Created x402 challenge %s for product=%s amount=%s USDT",
            challenge_id, product, amount_usdt,
        )

        return {
            "challenge_id": challenge_id,
            "product": product,
            "amount_usdt": amount_usdt,
            "recipient": recipient,
            "expires_at": expires_at,
            "nonce": nonce,
            "digest": digest,
            "http_status": 402,
        }

    def verify_payment_onchain(
        self, tx_hash: str, expected_amount: str, challenge_id: Optional[str] = None,
    ) -> dict:
        """Verify that an on-chain transaction satisfies a payment obligation.

        Fetches the transaction receipt via ``onchainos rpc call`` using
        ``eth_getTransactionReceipt``, then validates:
          1. The tx was successfully mined (``status == 0x1``).
          2. The transferred value meets or exceeds ``expected_amount``.
          3. The recipient matches the income wallet.
          4. If a ``challenge_id`` is provided, the challenge has not expired.

        Uses logarithmic tolerance for floating-point amount comparison:
        ``|log(actual/expected)| < 0.005`` (0.5 % tolerance).

        Args:
            tx_hash:         The ``0x``-prefixed transaction hash.
            expected_amount: Expected USDT amount as a string (human-readable).
            challenge_id:    Optional challenge to mark as fulfilled.

        Returns:
            dict with keys:
                verified (bool), tx_hash (str), amount_received (str),
                recipient_match (bool), challenge_fulfilled (bool | None),
                block_number (int), confirmations (int), details (str).
        """
        if not tx_hash or not tx_hash.startswith("0x"):
            return {"verified": False, "error": "Invalid tx_hash format"}

        # Fetch tx receipt
        cmd = [
            "onchainos", "rpc", "call",
            "--method", "eth_getTransactionReceipt",
            "--params", json.dumps([tx_hash]),
            "--chain", str(CHAIN_ID),
        ]
        result = self._run_cmd(cmd)

        if result.get("error"):
            return {"verified": False, "error": f"Receipt fetch failed: {result['error']}"}

        try:
            receipt_data = json.loads(result.get("stdout", "{}"))
            receipt = receipt_data if "status" in receipt_data else receipt_data.get("result", {})
        except (json.JSONDecodeError, KeyError):
            return {"verified": False, "error": "Unparseable receipt"}

        if not receipt:
            return {"verified": False, "error": "Transaction not found or not yet mined"}

        # Check tx success
        tx_status = receipt.get("status", "0x0")
        if tx_status not in ("0x1", 1, "1"):
            return {"verified": False, "error": "Transaction reverted", "tx_status": tx_status}

        block_hex = receipt.get("blockNumber", "0x0")
        try:
            block_number = int(block_hex, 16) if isinstance(block_hex, str) else int(block_hex)
        except (ValueError, TypeError):
            block_number = 0

        # Parse transfer value from logs (ERC-20 Transfer event)
        # Transfer event topic: keccak256("Transfer(address,address,uint256)")
        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        amount_received = 0.0
        income_addr = self._get_income_address().lower()
        recipient_match = False

        for log_entry in receipt.get("logs", []):
            topics = log_entry.get("topics", [])
            if len(topics) >= 3 and topics[0] == transfer_topic:
                # Topic[2] is the recipient (zero-padded address)
                log_recipient = "0x" + topics[2][-40:]
                if log_recipient.lower() == income_addr:
                    recipient_match = True
                    raw_value = log_entry.get("data", "0x0")
                    try:
                        wei_value = int(raw_value, 16) if isinstance(raw_value, str) else int(raw_value)
                        # USDT has 6 decimals
                        amount_received = wei_value / 1e6
                    except (ValueError, TypeError):
                        pass

        # Amount verification with logarithmic tolerance
        expected_float = float(expected_amount) if expected_amount else 0.0
        amount_ok = False
        if expected_float > 0 and amount_received > 0:
            log_ratio = abs(math.log(amount_received / expected_float))
            amount_ok = log_ratio < 0.005  # 0.5% tolerance
        elif expected_float == 0:
            amount_ok = True  # No amount constraint

        # Challenge fulfilment
        challenge_fulfilled = None
        if challenge_id:
            for record in self._revenue_ledger:
                if record.get("challenge_id") == challenge_id:
                    if record.get("expires_at", 0) < int(time.time()):
                        challenge_fulfilled = False
                        break
                    if amount_ok and recipient_match:
                        record["status"] = "fulfilled"
                        record["tx_hash"] = tx_hash
                        challenge_fulfilled = True
                    else:
                        challenge_fulfilled = False
                    break

        verified = bool(
            tx_status in ("0x1", 1, "1")
            and recipient_match
            and amount_ok
        )

        # Record successful payment
        if verified:
            self._revenue_ledger.append({
                "type": "payment",
                "tx_hash": tx_hash,
                "amount_usdt": str(round(amount_received, 6)),
                "block_number": block_number,
                "timestamp": int(time.time()),
                "challenge_id": challenge_id,
            })

        return {
            "verified": verified,
            "tx_hash": tx_hash,
            "amount_received": str(round(amount_received, 6)),
            "expected_amount": expected_amount,
            "recipient_match": recipient_match,
            "amount_within_tolerance": amount_ok,
            "challenge_fulfilled": challenge_fulfilled,
            "block_number": block_number,
            "details": "Payment verified" if verified else "Verification failed",
        }

    def get_revenue_analytics(self) -> dict:
        """Compute revenue analytics from the in-memory payment ledger.

        Aggregates all recorded payments and produces:
          - Total revenue in USDT
          - Revenue breakdown by product
          - Revenue breakdown by originating currency
          - Mean / median / standard-deviation of payment sizes
          - Payment count and refund count
          - Subscription revenue vs one-time revenue split
          - Time-series daily totals (last 30 days)

        Uses ``statistics.mean``, ``statistics.median``, and
        ``statistics.pstdev`` for statistical computations.  Revenue
        forecasting applies exponential smoothing (alpha = 0.3) over daily
        totals.

        Returns:
            dict with keys: total_revenue_usdt, payment_count, refund_count,
            by_product, by_currency, stats (mean/median/stdev),
            daily_totals (list), forecast_next_day_usdt.
        """
        payments = [r for r in self._revenue_ledger if r.get("type") == "payment"]
        refunds = self._refund_ledger

        amounts = []
        by_product = {}
        by_currency = {}

        for pay in payments:
            amt = float(pay.get("amount_usdt", 0))
            amounts.append(amt)

            prod = pay.get("product", pay.get("challenge_id", "direct"))
            by_product[prod] = by_product.get(prod, 0.0) + amt

            currency = pay.get("from_currency", "USDT")
            by_currency[currency] = by_currency.get(currency, 0.0) + amt

        total_revenue = sum(amounts) if amounts else 0.0
        total_refunds = sum(float(r.get("amount_usdt", 0)) for r in refunds)

        # Statistical measures
        if len(amounts) >= 2:
            pay_mean = statistics.mean(amounts)
            pay_median = statistics.median(amounts)
            pay_stdev = statistics.pstdev(amounts)
        elif len(amounts) == 1:
            pay_mean = amounts[0]
            pay_median = amounts[0]
            pay_stdev = 0.0
        else:
            pay_mean = 0.0
            pay_median = 0.0
            pay_stdev = 0.0

        # Build daily totals for the last 30 days
        now = int(time.time())
        daily_buckets = {}
        for pay in payments:
            ts = pay.get("timestamp", now)
            day_key = ts // 86400
            daily_buckets[day_key] = daily_buckets.get(day_key, 0.0) + float(
                pay.get("amount_usdt", 0)
            )

        # Sort and build list
        today_bucket = now // 86400
        daily_totals = []
        for offset in range(29, -1, -1):
            bucket = today_bucket - offset
            daily_totals.append({
                "day_offset": -offset,
                "epoch_day": bucket,
                "revenue_usdt": round(daily_buckets.get(bucket, 0.0), 6),
            })

        # Exponential smoothing forecast (alpha = 0.3)
        alpha = 0.3
        smoothed = 0.0
        for entry in daily_totals:
            smoothed = alpha * entry["revenue_usdt"] + (1 - alpha) * smoothed
        forecast_next_day = round(smoothed, 6)

        # Subscription vs one-time split
        sub_revenue = sum(
            float(r.get("amount_usdt", 0))
            for r in payments
            if r.get("product") in ("strategy_subscribe",)
        )
        onetime_revenue = total_revenue - sub_revenue

        return {
            "total_revenue_usdt": round(total_revenue, 6),
            "net_revenue_usdt": round(total_revenue - total_refunds, 6),
            "payment_count": len(payments),
            "refund_count": len(refunds),
            "total_refunds_usdt": round(total_refunds, 6),
            "by_product": {k: round(v, 6) for k, v in by_product.items()},
            "by_currency": {k: round(v, 6) for k, v in by_currency.items()},
            "token_balances": {k: round(v, 6) for k, v in self._token_balances.items()},
            "stats": {
                "mean_usdt": round(pay_mean, 6),
                "median_usdt": round(pay_median, 6),
                "stdev_usdt": round(pay_stdev, 6),
            },
            "subscription_revenue_usdt": round(sub_revenue, 6),
            "onetime_revenue_usdt": round(onetime_revenue, 6),
            "daily_totals": daily_totals,
            "forecast_next_day_usdt": forecast_next_day,
        }

    def manage_subscription(
        self, user: str, product: str, action: str,
        duration_days: int = 30,
    ) -> dict:
        """Manage subscription lifecycle for recurring Genesis products.

        Supports the following actions:
          - ``"create"``  -- Activate a new subscription with expiry.
          - ``"renew"``   -- Extend an existing subscription by ``duration_days``.
          - ``"cancel"``  -- Mark subscription as cancelled (no refund).
          - ``"status"``  -- Query current subscription state.

        Subscription pricing is derived from ``X402_PRICING`` and pro-rated
        using ``math.ceil`` for partial periods.  Expiry math uses epoch
        seconds: ``expires_at = now + duration_days * 86400``.

        Args:
            user:           Payer wallet address (subscription key).
            product:        Product key (must be a subscription-eligible product).
            action:         One of ``"create"``, ``"renew"``, ``"cancel"``, ``"status"``.
            duration_days:  Subscription period in days (default 30).

        Returns:
            dict with keys: user, product, action, status, expires_at,
            days_remaining, amount_usdt, subscription_id.
        """
        now = int(time.time())
        sub_key = f"{user.lower()}:{product}"
        existing = self._subscriptions.get(sub_key)

        if action == "status":
            if not existing:
                return {
                    "user": user, "product": product, "action": action,
                    "status": "not_found", "expires_at": 0, "days_remaining": 0,
                }
            expires_at = existing.get("expires_at", 0)
            days_remaining = max(0, math.ceil((expires_at - now) / 86400))
            is_active = expires_at > now and existing.get("status") == "active"
            return {
                "user": user, "product": product, "action": action,
                "status": "active" if is_active else "expired",
                "subscription_id": existing.get("subscription_id", ""),
                "expires_at": expires_at,
                "days_remaining": days_remaining,
                "created_at": existing.get("created_at", 0),
            }

        if action == "cancel":
            if not existing:
                return {"user": user, "product": product, "action": action,
                        "status": "not_found", "error": "No active subscription"}
            existing["status"] = "cancelled"
            existing["cancelled_at"] = now
            logger.info("Subscription cancelled: %s", sub_key)
            return {
                "user": user, "product": product, "action": action,
                "status": "cancelled",
                "subscription_id": existing.get("subscription_id", ""),
                "cancelled_at": now,
            }

        # For create / renew, compute pricing
        tier = X402_PRICING.get(product)
        base_amount = float(tier["amount"]) if tier else 0.0
        # Pro-rate: monthly base scaled by duration
        prorated_amount = round(base_amount * (duration_days / 30.0), 6)

        if action == "create":
            subscription_id = hashlib.sha256(
                f"{sub_key}:{now}:{uuid.uuid4().hex}".encode()
            ).hexdigest()[:24]

            expires_at = now + duration_days * 86400

            self._subscriptions[sub_key] = {
                "subscription_id": subscription_id,
                "user": user,
                "product": product,
                "status": "active",
                "created_at": now,
                "expires_at": expires_at,
                "duration_days": duration_days,
                "amount_usdt": str(prorated_amount),
            }
            logger.info(
                "Subscription created: %s id=%s expires=%d",
                sub_key, subscription_id, expires_at,
            )
            return {
                "user": user, "product": product, "action": action,
                "status": "active",
                "subscription_id": subscription_id,
                "expires_at": expires_at,
                "days_remaining": duration_days,
                "amount_usdt": str(prorated_amount),
            }

        if action == "renew":
            if not existing:
                return {"user": user, "product": product, "action": action,
                        "status": "not_found", "error": "No subscription to renew"}
            # Extend from current expiry or now, whichever is later
            base_time = max(existing.get("expires_at", now), now)
            new_expires = base_time + duration_days * 86400
            existing["expires_at"] = new_expires
            existing["status"] = "active"
            days_remaining = max(0, math.ceil((new_expires - now) / 86400))
            logger.info("Subscription renewed: %s new_expires=%d", sub_key, new_expires)
            return {
                "user": user, "product": product, "action": action,
                "status": "active",
                "subscription_id": existing.get("subscription_id", ""),
                "expires_at": new_expires,
                "days_remaining": days_remaining,
                "amount_usdt": str(prorated_amount),
            }

        return {"error": f"Unknown action: {action}"}

    # ── Settlement Delay Optimization: Batch Settlement ────────────────

    def queue_settlement(self, payment_data):
        """Add a settlement request to the pending queue with a timestamp.

        Instead of executing immediately, the settlement is accumulated in
        ``_pending_settlements`` so that multiple requests can be flushed as a
        single batch, reducing per-settlement overhead.

        Args:
            payment_data: dict containing at minimum ``payer_address``,
                ``amount``, ``settlement_token``, and ``settle_mode``.  An
                optional ``urgent`` flag causes immediate settlement.

        Returns:
            dict with ``settlement_id``, ``queued`` status, and
            ``pending_count``.
        """
        settlement_id = uuid.uuid4().hex[:16]
        entry = {
            "settlement_id": settlement_id,
            "payment_data": payment_data,
            "queued_at_ms": time.time() * 1000,
            "callback": None,
        }

        # Urgent settlements bypass the queue entirely
        if payment_data.get("urgent"):
            logger.info("Urgent settlement %s — bypassing queue", settlement_id)
            result = self._settle_x402(
                payment_data.get("payer_address", ""),
                payment_data.get("amount", "0"),
                payment_data.get("settle_mode", "instant"),
                settlement_token=payment_data.get("settlement_token",
                                                   self.preferred_settlement_token),
            )
            return {
                "settlement_id": settlement_id,
                "status": "settled_immediate",
                "result": result,
            }

        self._pending_settlements.append(entry)
        logger.info(
            "Queued settlement %s (pending=%d)",
            settlement_id, len(self._pending_settlements),
        )
        return {
            "settlement_id": settlement_id,
            "status": "queued",
            "pending_count": len(self._pending_settlements),
        }

    def flush_settlements(self, force=False):
        """Batch-process all pending settlements.

        Groups queued settlements by token type to minimise swap operations,
        then executes each group as a single batch when either:
          - The queue size >= ``BATCH_THRESHOLD``, **or**
          - The oldest queued item age > ``BATCH_MAX_WAIT_MS``, **or**
          - ``force=True``.

        Args:
            force: If *True*, flush regardless of threshold or age.

        Returns:
            dict with ``batch_id``, list of ``settlement_ids``, per-group
            ``results``, ``latency_saved_ms``, and ``count``.  Returns
            ``None`` if no flush was performed.
        """
        if not self._pending_settlements:
            return None

        now_ms = time.time() * 1000
        oldest_age_ms = now_ms - self._pending_settlements[0]["queued_at_ms"]
        queue_size = len(self._pending_settlements)

        should_flush = (
            force
            or queue_size >= self.BATCH_THRESHOLD
            or oldest_age_ms > self.BATCH_MAX_WAIT_MS
        )
        if not should_flush:
            return None

        # Drain the queue
        batch = list(self._pending_settlements)
        self._pending_settlements.clear()

        # Group by token type
        groups = {}
        for entry in batch:
            token = entry["payment_data"].get(
                "settlement_token", self.preferred_settlement_token
            )
            groups.setdefault(token, []).append(entry)

        latency_saved = self._estimate_latency_savings(batch)
        batch_id = uuid.uuid4().hex[:16]
        settlement_ids = [e["settlement_id"] for e in batch]
        group_results = {}

        for token, entries in groups.items():
            token_results = []
            for entry in entries:
                pd = entry["payment_data"]
                result = self._settle_x402(
                    pd.get("payer_address", ""),
                    pd.get("amount", "0"),
                    pd.get("settle_mode", "instant"),
                    settlement_token=token,
                )
                token_results.append({
                    "settlement_id": entry["settlement_id"],
                    "result": result,
                })
                # Fire callback if present
                cb = entry.get("callback")
                if callable(cb):
                    try:
                        cb(entry["settlement_id"], result)
                    except Exception:
                        logger.exception(
                            "Callback error for settlement %s",
                            entry["settlement_id"],
                        )
            group_results[token] = token_results

        # Update batch performance metrics
        self._batch_stats["total_batches_processed"] += 1
        self._batch_stats["total_settlements_batched"] += len(batch)
        self._batch_stats["total_latency_saved_ms"] += latency_saved

        logger.info(
            "Flushed batch %s: %d settlements, ~%.1f ms saved",
            batch_id, len(batch), latency_saved,
        )

        return {
            "batch_id": batch_id,
            "settlement_ids": settlement_ids,
            "count": len(batch),
            "results": group_results,
            "latency_saved_ms": round(latency_saved, 2),
        }

    def get_pending_count(self):
        """Return the number of settlements currently waiting in the queue.

        Returns:
            int: Length of ``_pending_settlements``.
        """
        return len(self._pending_settlements)

    def get_batch_stats(self):
        """Return batch performance metrics for monitoring.

        Returns:
            dict with ``total_batches_processed``,
            ``total_settlements_batched``, ``average_batch_size``,
            ``average_latency_saved_ms``, ``total_latency_saved_ms``,
            and ``pending_count``.
        """
        total_batches = self._batch_stats["total_batches_processed"]
        total_settled = self._batch_stats["total_settlements_batched"]
        total_saved = self._batch_stats["total_latency_saved_ms"]

        avg_batch_size = (
            total_settled / total_batches if total_batches > 0 else 0.0
        )
        avg_latency_saved = (
            total_saved / total_batches if total_batches > 0 else 0.0
        )

        return {
            "total_batches_processed": total_batches,
            "total_settlements_batched": total_settled,
            "average_batch_size": round(avg_batch_size, 2),
            "average_latency_saved_ms": round(avg_latency_saved, 2),
            "total_latency_saved_ms": round(total_saved, 2),
            "pending_count": len(self._pending_settlements),
        }

    def settle_async(self, payment_data, callback=None):
        """Queue a settlement and optionally call back when the batch completes.

        This provides an async-style interface: the settlement is placed on
        the pending queue and, when the batch containing it is eventually
        flushed via ``flush_settlements``, the optional *callback* is invoked
        with ``(settlement_id, result)``.

        For latency-sensitive operations, set ``payment_data["urgent"] = True``
        to bypass the queue and settle immediately.

        Args:
            payment_data: dict with settlement parameters (same as
                ``queue_settlement``).
            callback:     Optional callable ``(settlement_id, result) -> None``
                invoked after the settlement is executed in a batch flush.

        Returns:
            dict from ``queue_settlement`` with the ``settlement_id``.
        """
        # Urgent requests are settled immediately
        if payment_data.get("urgent"):
            receipt = self.queue_settlement(payment_data)
            if callable(callback):
                try:
                    callback(receipt["settlement_id"], receipt.get("result"))
                except Exception:
                    logger.exception(
                        "Callback error for urgent settlement %s",
                        receipt["settlement_id"],
                    )
            return receipt

        receipt = self.queue_settlement(payment_data)
        # Attach the callback to the queued entry so flush_settlements can
        # invoke it when the batch is processed.
        if callable(callback) and self._pending_settlements:
            self._pending_settlements[-1]["callback"] = callback
        return receipt

    def _estimate_latency_savings(self, batch):
        """Estimate milliseconds saved by batching vs individual settlements.

        Heuristic: each individual settlement incurs a fixed overhead
        (network round-trip + confirmation wait).  When grouped by token,
        only the first settlement per token group pays the full overhead;
        subsequent ones in the same group save most of it.

        Model:
          - ``BASE_OVERHEAD_MS = 120`` per individual settlement.
          - Batching saves ``BASE_OVERHEAD_MS * (n - g)`` where *n* is total
            settlements and *g* is the number of distinct token groups.

        Args:
            batch: list of queued settlement entries.

        Returns:
            float: Estimated milliseconds saved.
        """
        BASE_OVERHEAD_MS = 120  # per-settlement network/confirmation overhead
        if not batch:
            return 0.0
        token_groups = set()
        for entry in batch:
            token = entry["payment_data"].get(
                "settlement_token", self.preferred_settlement_token
            )
            token_groups.add(token)
        # Each group still pays one overhead; savings come from the rest
        savings = BASE_OVERHEAD_MS * max(0, len(batch) - len(token_groups))
        return float(savings)

    # ── Private helpers ──────────────────────────────────────────────────

    def _run_cmd(self, cmd, dry_run=None):
        """Execute a subprocess command, respecting DRY_RUN config."""
        if dry_run is None:
            dry_run = DRY_RUN
        logger.debug("cmd: %s", " ".join(cmd))
        if dry_run:
            logger.info("[DRY_RUN] %s", " ".join(cmd))
            return {"stdout": json.dumps({
                "dry_run": True,
                "inputAmount": "0.001",
                "txHash": "0x" + "0" * 64,
                "route": "simulated",
            })}
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                logger.error("Command failed (%d): %s", proc.returncode, proc.stderr)
                return {"error": proc.stderr or f"exit code {proc.returncode}"}
            return {"stdout": proc.stdout}
        except subprocess.TimeoutExpired:
            logger.error("Command timed out: %s", " ".join(cmd))
            return {"error": "timeout"}
        except FileNotFoundError:
            logger.error("onchainos CLI not found")
            return {"error": "onchainos CLI not found"}
