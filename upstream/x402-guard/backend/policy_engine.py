from datetime import datetime, timedelta, timezone
from typing import Optional
import logging

from models import GuardRequest, GuardResponse, Policy, Transaction, SpendingStats
import storage

logger = logging.getLogger(__name__)

# X Layer defaults
X_LAYER_CHAIN_ID = 1952
X_LAYER_CAIP2 = "eip155:1952"
DEFAULT_ASSET = "0xcB8BF24c6cE16Ad21D707c9505421a17f2bec79D"  # USDC_TEST on X Layer testnet


class PolicyEngine:
    """
    Core guard logic for x402 payments.

    Decision flow per transaction:
      1. Blacklist check  -> block immediately
      2. Whitelist check  -> approve immediately (bypasses limits)
      3. Auto-approve-under threshold -> approve immediately
      4. Per-transaction limit check
      5. Hourly limit check  (with soft-alert tier)
      6. Daily limit check   (with soft-alert tier)

    Tiered response (soft_alert_threshold defaults to 0.80):
      - spent < threshold * limit  -> approve
      - threshold * limit <= spent < limit  -> soft_alert (still allowed)
      - spent >= limit  -> block
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def check_and_approve(self, request: GuardRequest) -> GuardResponse:
        policy = self._resolve_policy(request)

        if policy is None:
            # No policy found — deny by default for safety
            return GuardResponse(
                allowed=False,
                action="block",
                reason="No active policy found for this agent. Create a policy first.",
                remaining_daily=0.0,
                remaining_hourly=0.0,
            )

        # Normalise pay_to for comparisons
        pay_to = request.pay_to.lower().strip()

        # 1. Blacklist
        blacklist_lower = [addr.lower().strip() for addr in policy.blacklist]
        if pay_to in blacklist_lower:
            tx = self._build_transaction(request, policy, "blocked",
                                         "Recipient address is blacklisted.")
            storage.store_transaction(tx.model_dump())
            return GuardResponse(
                allowed=False,
                action="block",
                reason="Recipient address is blacklisted.",
                remaining_daily=self._remaining_daily(request.agent_id, policy),
                remaining_hourly=self._remaining_hourly(request.agent_id, policy),
                policy_id=policy.id,
                transaction_id=tx.id,
            )

        # 2. Whitelist — bypass all limit checks
        whitelist_lower = [addr.lower().strip() for addr in policy.whitelist]
        if pay_to in whitelist_lower:
            tx = self._build_transaction(request, policy, "approved",
                                         "Recipient address is whitelisted.")
            storage.store_transaction(tx.model_dump())
            return GuardResponse(
                allowed=True,
                action="approve",
                reason="Recipient address is whitelisted — limits bypassed.",
                remaining_daily=self._remaining_daily(request.agent_id, policy, extra=request.amount),
                remaining_hourly=self._remaining_hourly(request.agent_id, policy, extra=request.amount),
                policy_id=policy.id,
                transaction_id=tx.id,
            )

        # 3. Auto-approve below micro-threshold
        if request.amount <= policy.auto_approve_under:
            tx = self._build_transaction(request, policy, "approved",
                                         f"Amount {request.amount} is below auto-approve threshold "
                                         f"{policy.auto_approve_under}.")
            storage.store_transaction(tx.model_dump())
            return GuardResponse(
                allowed=True,
                action="approve",
                reason=tx.reason,
                remaining_daily=self._remaining_daily(request.agent_id, policy, extra=request.amount),
                remaining_hourly=self._remaining_hourly(request.agent_id, policy, extra=request.amount),
                policy_id=policy.id,
                transaction_id=tx.id,
            )

        # 4. Per-transaction limit
        if request.amount > policy.per_tx_limit:
            tx = self._build_transaction(request, policy, "blocked",
                                         f"Amount {request.amount} exceeds per-transaction limit "
                                         f"{policy.per_tx_limit}.")
            storage.store_transaction(tx.model_dump())
            return GuardResponse(
                allowed=False,
                action="block",
                reason=tx.reason,
                remaining_daily=self._remaining_daily(request.agent_id, policy),
                remaining_hourly=self._remaining_hourly(request.agent_id, policy),
                policy_id=policy.id,
                transaction_id=tx.id,
            )

        # 5. Hourly limit
        hourly_result = self._check_limit(
            spent=self._spent_last_hour(request.agent_id),
            limit=policy.hourly_limit,
            amount=request.amount,
            threshold=policy.soft_alert_threshold,
            window="hourly",
        )
        if hourly_result is not None:
            action, reason = hourly_result
            allowed = action != "block"
            status = "blocked" if action == "block" else "soft_alert"
            tx = self._build_transaction(request, policy, status, reason)
            storage.store_transaction(tx.model_dump())
            return GuardResponse(
                allowed=allowed,
                action=action,
                reason=reason,
                remaining_daily=self._remaining_daily(request.agent_id, policy),
                remaining_hourly=max(0.0, policy.hourly_limit - self._spent_last_hour(request.agent_id)),
                policy_id=policy.id,
                transaction_id=tx.id,
            )

        # 6. Daily limit
        daily_result = self._check_limit(
            spent=self._spent_last_day(request.agent_id),
            limit=policy.daily_limit,
            amount=request.amount,
            threshold=policy.soft_alert_threshold,
            window="daily",
        )
        if daily_result is not None:
            action, reason = daily_result
            allowed = action != "block"
            status = "blocked" if action == "block" else "soft_alert"
            tx = self._build_transaction(request, policy, status, reason)
            storage.store_transaction(tx.model_dump())
            return GuardResponse(
                allowed=allowed,
                action=action,
                reason=reason,
                remaining_daily=max(0.0, policy.daily_limit - self._spent_last_day(request.agent_id)),
                remaining_hourly=self._remaining_hourly(request.agent_id, policy),
                policy_id=policy.id,
                transaction_id=tx.id,
            )

        # All checks passed -> approve
        tx = self._build_transaction(request, policy, "approved",
                                     "Transaction approved within all policy limits.")
        storage.store_transaction(tx.model_dump())
        return GuardResponse(
            allowed=True,
            action="approve",
            reason="Transaction approved within all policy limits.",
            remaining_daily=self._remaining_daily(request.agent_id, policy, extra=request.amount),
            remaining_hourly=self._remaining_hourly(request.agent_id, policy, extra=request.amount),
            policy_id=policy.id,
            transaction_id=tx.id,
        )

    def get_stats(self, agent_id: str, policy_id: Optional[str] = None) -> SpendingStats:
        policy = None
        if policy_id:
            p = storage.get_policy(policy_id)
            if p:
                policy = Policy(**p)
        if policy is None:
            p = storage.get_policy_for_agent(agent_id)
            if p:
                policy = Policy(**p)

        if policy is None:
            # Return zeroed stats
            return SpendingStats(
                agent_id=agent_id,
                daily_spent=0.0,
                hourly_spent=0.0,
                daily_limit=0.0,
                hourly_limit=0.0,
                per_tx_limit=0.0,
                remaining_daily=0.0,
                remaining_hourly=0.0,
                total_transactions=0,
                blocked_transactions=0,
                approved_transactions=0,
                soft_alert_transactions=0,
                policy_id=None,
            )

        txs = storage.get_transactions_for_agent(agent_id)
        total = len(txs)
        blocked = sum(1 for t in txs if t.get("status") == "blocked")
        approved = sum(1 for t in txs if t.get("status") == "approved")
        soft = sum(1 for t in txs if t.get("status") == "soft_alert")

        daily_spent = self._spent_last_day(agent_id)
        hourly_spent = self._spent_last_hour(agent_id)

        return SpendingStats(
            agent_id=agent_id,
            daily_spent=round(daily_spent, 6),
            hourly_spent=round(hourly_spent, 6),
            daily_limit=policy.daily_limit,
            hourly_limit=policy.hourly_limit,
            per_tx_limit=policy.per_tx_limit,
            remaining_daily=round(max(0.0, policy.daily_limit - daily_spent), 6),
            remaining_hourly=round(max(0.0, policy.hourly_limit - hourly_spent), 6),
            total_transactions=total,
            blocked_transactions=blocked,
            approved_transactions=approved,
            soft_alert_transactions=soft,
            policy_id=policy.id,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolve_policy(self, request: GuardRequest) -> Optional[Policy]:
        if request.policy_id:
            p = storage.get_policy(request.policy_id)
            if p:
                return Policy(**p)
        p = storage.get_policy_for_agent(request.agent_id)
        if p:
            return Policy(**p)
        return None

    def _spent_last_hour(self, agent_id: str) -> float:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        total = 0.0
        for t in storage.get_transactions_for_agent(agent_id):
            if t.get("status") == "blocked":
                continue
            ts_raw = t.get("timestamp")
            if ts_raw is None:
                continue
            try:
                ts_str = str(ts_raw).replace("Z", "+00:00")
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if ts >= cutoff:
                total += float(t.get("amount", 0))
        return total

    def _spent_last_day(self, agent_id: str) -> float:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        total = 0.0
        for t in storage.get_transactions_for_agent(agent_id):
            if t.get("status") == "blocked":
                continue
            ts_raw = t.get("timestamp")
            if ts_raw is None:
                continue
            try:
                ts_str = str(ts_raw).replace("Z", "+00:00")
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if ts >= cutoff:
                total += float(t.get("amount", 0))
        return total

    def _remaining_daily(self, agent_id: str, policy: Policy, extra: float = 0.0) -> float:
        return round(max(0.0, policy.daily_limit - self._spent_last_day(agent_id) - extra), 6)

    def _remaining_hourly(self, agent_id: str, policy: Policy, extra: float = 0.0) -> float:
        return round(max(0.0, policy.hourly_limit - self._spent_last_hour(agent_id) - extra), 6)

    def _check_limit(
        self,
        spent: float,
        limit: float,
        amount: float,
        threshold: float,
        window: str,
    ) -> Optional[tuple]:
        """
        Returns (action, reason) tuple if the limit check triggers a non-approve result,
        otherwise returns None (meaning proceed to next check).
        """
        projected = spent + amount
        soft_mark = threshold * limit

        if projected > limit:
            return (
                "block",
                f"{window.capitalize()} spending limit exceeded: projected {projected:.4f} > limit {limit:.4f}.",
            )
        if projected >= soft_mark:
            pct = (projected / limit) * 100
            return (
                "soft_alert",
                f"Approaching {window} limit: {pct:.1f}% used after this transaction "
                f"({projected:.4f}/{limit:.4f}).",
            )
        return None

    def _build_transaction(
        self,
        request: GuardRequest,
        policy: Policy,
        status: str,
        reason: str,
    ) -> Transaction:
        return Transaction(
            agent_id=request.agent_id,
            amount=request.amount,
            asset=request.asset,
            pay_to=request.pay_to,
            network=request.network,
            timestamp=datetime.now(timezone.utc),
            status=status,
            reason=reason,
            policy_id=policy.id,
        )


# Singleton instance shared across routes
engine = PolicyEngine()
