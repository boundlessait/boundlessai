#!/usr/bin/env python3
"""
Unit tests for PolicyEngine
----------------------------
Tests the core guard decision logic without starting a server.

Run with:
    python3 tests/test_policy_engine.py           (from repo root)
    cd backend && python3 -m unittest ../tests/test_policy_engine  (direct)
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

# ── Path setup ────────────────────────────────────────────────────────────────
# Add backend/ to sys.path so we can import policy_engine, models, storage
TESTS_DIR   = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(os.path.dirname(TESTS_DIR), "backend")
sys.path.insert(0, BACKEND_DIR)

from models import GuardRequest, Policy, Transaction


# ── Test helpers ───────────────────────────────────────────────────────────────

def _make_policy(**kwargs) -> Policy:
    """Return a Policy with sensible defaults, overridden by kwargs."""
    defaults = dict(
        id                    = "test-policy-001",
        name                  = "Test Policy",
        agent_id              = "agent-test",
        daily_limit           = 100.0,
        hourly_limit          = 20.0,
        per_tx_limit          = 10.0,
        auto_approve_under    = 0.01,
        soft_alert_threshold  = 0.80,
        whitelist             = [],
        blacklist             = [],
        active                = True,
    )
    defaults.update(kwargs)
    return Policy(**defaults)


def _make_request(**kwargs) -> GuardRequest:
    """Return a GuardRequest with sensible defaults, overridden by kwargs."""
    defaults = dict(
        agent_id   = "agent-test",
        network    = "eip155:196",
        amount     = 1.0,
        asset      = "0x4ae46a509f6b1d9056937ba4500cb143933d2dc8",
        pay_to     = "0xRecipient0000000000000000000000000000000",
        policy_id  = "test-policy-001",
    )
    defaults.update(kwargs)
    return GuardRequest(**defaults)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_ago(h: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()


# ── Base test class with shared mock setup ─────────────────────────────────────

class PolicyEngineTestBase(unittest.TestCase):
    """
    Patches storage so every test starts with a clean slate.
    Each test can freely manipulate self.mock_txs and self.mock_policy.
    """

    def setUp(self):
        self.mock_policy = _make_policy()
        self.mock_txs: list = []

        # Patch storage functions used by PolicyEngine
        patcher_get_policy = patch(
            "policy_engine.storage.get_policy",
            side_effect=lambda pid: self.mock_policy.model_dump() if pid == self.mock_policy.id else None,
        )
        patcher_get_policy_agent = patch(
            "policy_engine.storage.get_policy_for_agent",
            side_effect=lambda aid: self.mock_policy.model_dump() if aid == self.mock_policy.agent_id else None,
        )
        patcher_get_txs = patch(
            "policy_engine.storage.get_transactions_for_agent",
            side_effect=lambda aid: [t for t in self.mock_txs if t.get("agent_id") == aid],
        )
        patcher_store = patch(
            "policy_engine.storage.store_transaction",
            side_effect=self._capture_tx,
        )

        self.addCleanup(patcher_get_policy.stop)
        self.addCleanup(patcher_get_policy_agent.stop)
        self.addCleanup(patcher_get_txs.stop)
        self.addCleanup(patcher_store.stop)

        patcher_get_policy.start()
        patcher_get_policy_agent.start()
        patcher_get_txs.start()
        patcher_store.start()

        # Import fresh engine after patches are active
        import policy_engine
        self.engine = policy_engine.PolicyEngine()

    def _capture_tx(self, tx_dict: dict):
        """Side-effect: capture stored transactions so spending counters work."""
        self.mock_txs.append(tx_dict)

    def _add_past_tx(self, amount: float, hours_ago: float = 0.5, status: str = "approved"):
        """Inject a historical transaction into the mock storage."""
        self.mock_txs.append({
            "agent_id":   self.mock_policy.agent_id,
            "amount":     amount,
            "asset":      "0x4ae46a509f6b1d9056937ba4500cb143933d2dc8",
            "pay_to":     "0xSomePastRecipient00000000000000000000000",
            "network":    "eip155:196",
            "timestamp":  _hours_ago(hours_ago),
            "status":     status,
            "reason":     "past test transaction",
            "policy_id":  self.mock_policy.id,
        })


# ── Individual test cases ──────────────────────────────────────────────────────

class TestApproveNormalTx(PolicyEngineTestBase):
    """A standard transaction well within all limits must be approved."""

    def test_approve_normal_tx(self):
        req  = _make_request(amount=1.0)
        resp = self.engine.check_and_approve(req)

        self.assertTrue(resp.allowed,            "Transaction should be allowed")
        self.assertEqual(resp.action, "approve", "Action should be 'approve'")
        self.assertGreater(resp.remaining_daily,  0.0)
        self.assertGreater(resp.remaining_hourly, 0.0)
        self.assertIsNotNone(resp.transaction_id)


class TestBlockOverDailyLimit(PolicyEngineTestBase):
    """A transaction that would push spending past the daily cap must be blocked."""

    def test_block_over_daily_limit(self):
        # Pre-fill 99 USDC of spending within the last 24 h (daily_limit=100)
        self._add_past_tx(amount=99.0, hours_ago=1.0)

        req  = _make_request(amount=5.0)   # 99 + 5 = 104 > 100
        resp = self.engine.check_and_approve(req)

        self.assertFalse(resp.allowed,           "Over-daily-limit tx must be blocked")
        self.assertEqual(resp.action,  "block",  "Action should be 'block'")
        self.assertIn("daily", resp.reason.lower())


class TestSoftAlertAt80Percent(PolicyEngineTestBase):
    """
    A transaction that pushes projected daily spend into the
    soft_alert zone (80-100 % of limit) should return soft_alert.
    """

    def test_soft_alert_at_80_percent(self):
        # daily_limit=100, threshold=0.80 => soft zone starts at 80 USDC
        # Spend 78 USDC first, then try 5 USDC => projected 83 (83%) => soft_alert
        self._add_past_tx(amount=78.0, hours_ago=1.0)

        req  = _make_request(amount=5.0)
        resp = self.engine.check_and_approve(req)

        # allowed=True because soft_alert is still permitted
        self.assertTrue(resp.allowed,                "Soft-alert tx should still be allowed")
        self.assertEqual(resp.action, "soft_alert",  "Action should be 'soft_alert'")
        self.assertIn("daily", resp.reason.lower())


class TestWhitelistBypass(PolicyEngineTestBase):
    """A pay_to address on the whitelist bypasses ALL limit checks."""

    def test_whitelist_bypass(self):
        white_addr = "0xWhitelisted000000000000000000000000000"
        self.mock_policy = _make_policy(
            whitelist = [white_addr],
            daily_limit = 5.0,    # very tight limit
            per_tx_limit = 0.50,  # per-tx limit would normally block $2
        )

        # Pre-spend right up to the daily limit
        self._add_past_tx(amount=4.99, hours_ago=0.5)

        # This $2 tx would normally be blocked by both per_tx and daily limits
        req  = _make_request(amount=2.0, pay_to=white_addr)
        resp = self.engine.check_and_approve(req)

        self.assertTrue(resp.allowed,            "Whitelisted address should always be approved")
        self.assertEqual(resp.action, "approve", "Action should be 'approve'")
        self.assertIn("whitelist", resp.reason.lower())


class TestBlacklistBlock(PolicyEngineTestBase):
    """A pay_to address on the blacklist must always be blocked."""

    def test_blacklist_block(self):
        bad_addr = "0xMalicious000000000000000000000000000000"
        self.mock_policy = _make_policy(blacklist=[bad_addr])

        req  = _make_request(amount=0.01, pay_to=bad_addr)
        resp = self.engine.check_and_approve(req)

        self.assertFalse(resp.allowed,          "Blacklisted address must be blocked")
        self.assertEqual(resp.action, "block",  "Action should be 'block'")
        self.assertIn("blacklist", resp.reason.lower())


class TestPerTxLimit(PolicyEngineTestBase):
    """A single transaction exceeding per_tx_limit must be blocked."""

    def test_per_tx_limit(self):
        self.mock_policy = _make_policy(per_tx_limit=3.0, daily_limit=1000.0, hourly_limit=500.0)

        req  = _make_request(amount=5.0)   # 5 > per_tx_limit of 3
        resp = self.engine.check_and_approve(req)

        self.assertFalse(resp.allowed,          "Over-per-tx-limit tx must be blocked")
        self.assertEqual(resp.action, "block",  "Action should be 'block'")
        self.assertIn("per-transaction", resp.reason.lower())


class TestHourlyLimit(PolicyEngineTestBase):
    """A transaction that exceeds the hourly cap must be blocked."""

    def test_hourly_limit(self):
        # hourly_limit=20, spend 18 within the last hour, try 5 more => 23 > 20
        self._add_past_tx(amount=18.0, hours_ago=0.5)

        req  = _make_request(amount=5.0)
        resp = self.engine.check_and_approve(req)

        self.assertFalse(resp.allowed,          "Over-hourly-limit tx must be blocked")
        self.assertEqual(resp.action, "block",  "Action should be 'block'")
        self.assertIn("hourly", resp.reason.lower())


class TestAutoApproveUnderThreshold(PolicyEngineTestBase):
    """
    Transactions at or below auto_approve_under are instantly approved,
    even if per_tx and limit checks would otherwise be skipped or tight.
    """

    def test_auto_approve_under_threshold(self):
        # auto_approve_under=0.01; request exactly at the threshold
        self.mock_policy = _make_policy(
            auto_approve_under = 0.05,
            per_tx_limit       = 0.01,   # would normally block $0.05
            hourly_limit       = 0.001,  # absurdly tight
            daily_limit        = 0.001,
        )

        req  = _make_request(amount=0.05)
        resp = self.engine.check_and_approve(req)

        self.assertTrue(resp.allowed,            "Amount at auto-approve threshold should be approved")
        self.assertEqual(resp.action, "approve", "Action should be 'approve'")
        self.assertIn("auto-approve", resp.reason.lower())


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    loader  = unittest.TestLoader()
    suite   = unittest.TestSuite()

    test_classes = [
        TestApproveNormalTx,
        TestBlockOverDailyLimit,
        TestSoftAlertAt80Percent,
        TestWhitelistBypass,
        TestBlacklistBlock,
        TestPerTxLimit,
        TestHourlyLimit,
        TestAutoApproveUnderThreshold,
    ]
    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
