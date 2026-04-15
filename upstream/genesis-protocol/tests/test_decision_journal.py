"""Tests for DecisionJournal - local logging and hash computation."""
import sys
import os
import tempfile
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from skills.genesis.scripts.decision_journal import DecisionJournal


class TestDecisionJournal:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        # Monkey-patch config to use temp dir and skip on-chain
        import skills.genesis.scripts.config as cfg
        self._orig_journal_path = cfg.JOURNAL_LOCAL_PATH
        self._orig_journal_chain = cfg.JOURNAL_ON_CHAIN
        self._orig_dry_run = cfg.DRY_RUN
        cfg.JOURNAL_LOCAL_PATH = self.tmpdir
        cfg.JOURNAL_ON_CHAIN = False
        cfg.DRY_RUN = True
        self.journal = DecisionJournal()

    def teardown_method(self):
        import skills.genesis.scripts.config as cfg
        cfg.JOURNAL_LOCAL_PATH = self._orig_journal_path
        cfg.JOURNAL_ON_CHAIN = self._orig_journal_chain
        cfg.DRY_RUN = self._orig_dry_run

    def test_log_decision_returns_entry(self):
        entry = self.journal.log_decision(0, "FEE_ADJUST", "test reasoning", {"fee": 3000})
        assert entry["id"] == 1
        assert entry["strategy_id"] == 0
        assert entry["decision_type"] == "FEE_ADJUST"
        assert entry["reasoning"] == "test reasoning"

    def test_reasoning_hash_deterministic(self):
        h1 = self.journal.compute_reasoning_hash("test")
        h2 = self.journal.compute_reasoning_hash("test")
        assert h1 == h2
        assert h1.startswith("0x")

    def test_reasoning_hash_different_inputs(self):
        h1 = self.journal.compute_reasoning_hash("buy")
        h2 = self.journal.compute_reasoning_hash("sell")
        assert h1 != h2

    def test_get_recent_decisions(self):
        self.journal.log_decision(0, "FEE_ADJUST", "r1")
        self.journal.log_decision(1, "REBALANCE_EXECUTE", "r2")
        self.journal.log_decision(0, "STRATEGY_CREATE", "r3")
        recent = self.journal.get_recent_decisions(2)
        assert len(recent) == 2
        assert recent[-1]["decision_type"] == "STRATEGY_CREATE"

    def test_get_decision_count(self):
        assert self.journal.get_decision_count() == 0
        self.journal.log_decision(0, "FEE_ADJUST", "test")
        assert self.journal.get_decision_count() == 1

    def test_get_decisions_by_type(self):
        self.journal.log_decision(0, "FEE_ADJUST", "r1")
        self.journal.log_decision(0, "REBALANCE_EXECUTE", "r2")
        self.journal.log_decision(1, "FEE_ADJUST", "r3")
        fee_decisions = self.journal.get_decisions_by_type("FEE_ADJUST")
        assert len(fee_decisions) == 2

    def test_get_decisions_by_strategy(self):
        self.journal.log_decision(0, "FEE_ADJUST", "r1")
        self.journal.log_decision(1, "FEE_ADJUST", "r2")
        s0 = self.journal.get_decisions_by_strategy(0)
        assert len(s0) == 1

    def test_local_journal_persistence(self):
        self.journal.log_decision(0, "FEE_ADJUST", "persisted")
        # Create new journal instance pointing to same dir
        journal2 = DecisionJournal()
        entries = journal2.get_recent_decisions(10)
        assert len(entries) == 1
        assert entries[0]["reasoning"] == "persisted"
