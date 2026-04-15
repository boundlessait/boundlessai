"""Tests for GenesisEngine - 5-layer cognitive architecture."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, patch, PropertyMock
import time

import skills.genesis.scripts.config as config


class TestGenesisEngineInit:
    """Test engine initialization."""

    @patch("skills.genesis.scripts.genesis_engine.StrategyManager")
    @patch("skills.genesis.scripts.genesis_engine.DecisionJournal")
    @patch("skills.genesis.scripts.genesis_engine.WalletManager")
    @patch("skills.genesis.scripts.genesis_engine.MarketOracle")
    def test_init_defaults(self, mock_oracle, mock_wallet, mock_journal, mock_sm):
        from skills.genesis.scripts.genesis_engine import GenesisEngine
        engine = GenesisEngine()
        assert engine._cycle_count == 0
        assert engine._running is False
        assert engine._prediction_accuracy == 0.5
        assert engine._preferences["risk_tolerance"] == 0.5

    @patch("skills.genesis.scripts.genesis_engine.StrategyManager")
    @patch("skills.genesis.scripts.genesis_engine.DecisionJournal")
    @patch("skills.genesis.scripts.genesis_engine.WalletManager")
    @patch("skills.genesis.scripts.genesis_engine.MarketOracle")
    def test_init_world_state_empty(self, mock_oracle, mock_wallet, mock_journal, mock_sm):
        from skills.genesis.scripts.genesis_engine import GenesisEngine
        engine = GenesisEngine()
        assert engine._world_state == {}


class TestPerceive:
    """Test Layer 1 - Perception."""

    @patch("skills.genesis.scripts.genesis_engine.StrategyManager")
    @patch("skills.genesis.scripts.genesis_engine.DecisionJournal")
    @patch("skills.genesis.scripts.genesis_engine.WalletManager")
    @patch("skills.genesis.scripts.genesis_engine.MarketOracle")
    def setup_method(self, method, mock_oracle, mock_wallet, mock_journal, mock_sm):
        from skills.genesis.scripts.genesis_engine import GenesisEngine
        self.engine = GenesisEngine()
        self.engine.oracle = MagicMock()
        self.engine.wallet = MagicMock()
        self.engine.strategy_mgr = MagicMock()

    def test_perceive_returns_world_state(self):
        self.engine.oracle.fetch_all_prices.return_value = {("ETH", "USDC"): 3000.0}
        self.engine.wallet.get_all_balances.return_value = {"master": {"balance": "10"}}
        self.engine.strategy_mgr.get_active_strategies.return_value = []
        self.engine.strategy_mgr.get_strategy_summary.return_value = {"active_count": 0}

        state = self.engine.perceive()
        assert "timestamp" in state
        assert "prices" in state
        assert "ETH/USDC" in state["prices"]
        assert state["prices"]["ETH/USDC"] == 3000.0
        assert state["balances"]["master"]["balance"] == "10"

    def test_perceive_handles_exception(self):
        self.engine.oracle.fetch_all_prices.side_effect = RuntimeError("network error")
        state = self.engine.perceive()
        assert "error" in state


class TestAnalyze:
    """Test Layer 2 - Analysis."""

    @patch("skills.genesis.scripts.genesis_engine.StrategyManager")
    @patch("skills.genesis.scripts.genesis_engine.DecisionJournal")
    @patch("skills.genesis.scripts.genesis_engine.WalletManager")
    @patch("skills.genesis.scripts.genesis_engine.MarketOracle")
    def setup_method(self, method, mock_oracle, mock_wallet, mock_journal, mock_sm):
        from skills.genesis.scripts.genesis_engine import GenesisEngine
        self.engine = GenesisEngine()
        self.engine.oracle = MagicMock()

    def test_analyze_returns_regimes(self):
        self.engine.oracle.get_market_regime.return_value = {
            "regime_name": "mean_reversion", "volatility": 0.02, "confidence": 0.7
        }
        self.engine._world_state = {"active_strategies": []}
        result = self.engine.analyze()
        assert "regimes" in result
        assert "mismatches" in result
        assert "anomalies" in result

    def test_analyze_detects_mismatch(self):
        self.engine.oracle.get_market_regime.return_value = {
            "regime_name": "momentum", "volatility": 0.02, "confidence": 0.8
        }
        self.engine._world_state = {
            "active_strategies": [{"id": "s1", "market_regime_at_creation": "mean_reversion"}],
            "balances": {},
        }
        result = self.engine.analyze()
        assert len(result["mismatches"]) == 1
        assert result["mismatches"][0]["strategy_id"] == "s1"

    def test_detect_anomalies_vol_spike(self):
        regimes = {"ETH/USDC": {"volatility": 0.15}}
        self.engine._world_state = {"balances": {}}
        anomalies = self.engine._detect_anomalies(regimes)
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "vol_spike"

    def test_detect_anomalies_balance_drain(self):
        regimes = {}
        self.engine._world_state = {"balances": {"reserve": {"balance": "0"}}}
        anomalies = self.engine._detect_anomalies(regimes)
        assert any(a["type"] == "balance_drain" for a in anomalies)

    def test_analyze_handles_exception(self):
        self.engine.oracle.get_market_regime.side_effect = RuntimeError("fail")
        self.engine._world_state = {"active_strategies": []}
        result = self.engine.analyze()
        assert "error" in result


class TestPlan:
    """Test Layer 3 - Planning."""

    @patch("skills.genesis.scripts.genesis_engine.StrategyManager")
    @patch("skills.genesis.scripts.genesis_engine.DecisionJournal")
    @patch("skills.genesis.scripts.genesis_engine.WalletManager")
    @patch("skills.genesis.scripts.genesis_engine.MarketOracle")
    def setup_method(self, method, mock_oracle, mock_wallet, mock_journal, mock_sm):
        from skills.genesis.scripts.genesis_engine import GenesisEngine
        self.engine = GenesisEngine()
        self.engine.strategy_mgr = MagicMock()

    def test_plan_hold_when_no_actions(self):
        self.engine._analysis_cache = {"regimes": {}, "mismatches": [], "anomalies": []}
        self.engine._world_state = {"active_strategies": []}
        actions = self.engine.plan()
        assert len(actions) == 1
        assert actions[0]["type"] == "hold"

    def test_plan_critical_anomaly_generates_hold(self):
        self.engine._analysis_cache = {
            "regimes": {}, "mismatches": [],
            "anomalies": [{"type": "balance_drain", "severity": "critical", "wallet": "reserve"}],
        }
        self.engine._world_state = {"active_strategies": []}
        actions = self.engine.plan()
        assert any(a["type"] == "hold" and a["confidence"] == 0.95 for a in actions)

    def test_plan_rebalance_on_mismatch(self):
        self.engine._analysis_cache = {
            "regimes": {}, "anomalies": [],
            "mismatches": [{"strategy_id": "s1", "was": "low_vol", "now": "high_vol"}],
        }
        self.engine._world_state = {"active_strategies": []}
        actions = self.engine.plan()
        assert any(a["type"] == "rebalance" for a in actions)

    def test_plan_deactivate_strategy(self):
        self.engine._analysis_cache = {"regimes": {}, "mismatches": [], "anomalies": []}
        self.engine._world_state = {"active_strategies": [{"id": "s1"}]}
        self.engine.strategy_mgr.evaluate_performance.return_value = {"pnl_bps": -600}
        self.engine.strategy_mgr.should_deactivate.return_value = (True, "persistent loss")
        actions = self.engine.plan()
        assert any(a["type"] == "deactivate" for a in actions)


class TestEvolve:
    """Test Layer 4 - Evolution."""

    @patch("skills.genesis.scripts.genesis_engine.StrategyManager")
    @patch("skills.genesis.scripts.genesis_engine.DecisionJournal")
    @patch("skills.genesis.scripts.genesis_engine.WalletManager")
    @patch("skills.genesis.scripts.genesis_engine.MarketOracle")
    def setup_method(self, method, mock_oracle, mock_wallet, mock_journal, mock_sm):
        from skills.genesis.scripts.genesis_engine import GenesisEngine
        self.engine = GenesisEngine()
        self.engine.strategy_mgr = MagicMock()
        self.engine.journal = MagicMock()

    def test_evolve_increases_risk_on_positive_pnl(self):
        self.engine.strategy_mgr.get_strategy_summary.return_value = {"avg_pnl_bps": 200, "active_count": 1}
        self.engine.journal.get_recent_decisions.return_value = []
        old_risk = self.engine._preferences["risk_tolerance"]
        self.engine.evolve()
        assert self.engine._preferences["risk_tolerance"] > old_risk

    def test_evolve_decreases_risk_on_negative_pnl(self):
        self.engine.strategy_mgr.get_strategy_summary.return_value = {"avg_pnl_bps": -200, "active_count": 1}
        self.engine.journal.get_recent_decisions.return_value = []
        old_risk = self.engine._preferences["risk_tolerance"]
        self.engine.evolve()
        assert self.engine._preferences["risk_tolerance"] < old_risk

    def test_evolve_reduces_risk_on_low_accuracy(self):
        self.engine._prediction_accuracy = 0.3
        self.engine.strategy_mgr.get_strategy_summary.return_value = {"avg_pnl_bps": 0, "active_count": 1}
        self.engine.journal.get_recent_decisions.return_value = []
        old_risk = self.engine._preferences["risk_tolerance"]
        self.engine.evolve()
        assert self.engine._preferences["risk_tolerance"] < old_risk


class TestReflect:
    """Test Layer 5 - Meta-Cognition."""

    @patch("skills.genesis.scripts.genesis_engine.StrategyManager")
    @patch("skills.genesis.scripts.genesis_engine.DecisionJournal")
    @patch("skills.genesis.scripts.genesis_engine.WalletManager")
    @patch("skills.genesis.scripts.genesis_engine.MarketOracle")
    def setup_method(self, method, mock_oracle, mock_wallet, mock_journal, mock_sm):
        from skills.genesis.scripts.genesis_engine import GenesisEngine
        self.engine = GenesisEngine()
        self.engine.journal = MagicMock()

    def test_reflect_no_predictions(self):
        self.engine.journal.get_recent_decisions.return_value = []
        result = self.engine.reflect()
        assert result["total_predictions"] == 0
        assert result["prediction_accuracy"] == 0.5

    def test_reflect_trims_predictions(self):
        self.engine._predictions = [(time.time(), {"action": "hold", "confidence": 0.9}, None)] * 120
        self.engine.journal.get_recent_decisions.return_value = []
        self.engine.reflect()
        assert len(self.engine._predictions) <= 100


class TestExecutePlan:
    """Test orchestration - execute_plan."""

    @patch("skills.genesis.scripts.genesis_engine.StrategyManager")
    @patch("skills.genesis.scripts.genesis_engine.DecisionJournal")
    @patch("skills.genesis.scripts.genesis_engine.WalletManager")
    @patch("skills.genesis.scripts.genesis_engine.MarketOracle")
    def setup_method(self, method, mock_oracle, mock_wallet, mock_journal, mock_sm):
        from skills.genesis.scripts.genesis_engine import GenesisEngine
        self.engine = GenesisEngine()
        self.engine.strategy_mgr = MagicMock()
        self._orig_paused = config.PAUSED
        self._orig_threshold = config.CONFIDENCE_THRESHOLD

    def teardown_method(self):
        config.PAUSED = self._orig_paused
        config.CONFIDENCE_THRESHOLD = self._orig_threshold

    def test_execute_skips_low_confidence(self):
        config.PAUSED = False
        config.CONFIDENCE_THRESHOLD = 0.7
        actions = [{"type": "create_strategy", "confidence": 0.3, "params": {}}]
        results = self.engine.execute_plan(actions)
        assert results[0]["status"] == "skipped_low_confidence"

    def test_execute_paused_returns_paused(self):
        config.PAUSED = True
        config.CONFIDENCE_THRESHOLD = 0.1
        actions = [{"type": "hold", "confidence": 1.0, "params": {}}]
        results = self.engine.execute_plan(actions)
        assert results[0]["status"] == "paused"

    def test_execute_hold_action(self):
        config.PAUSED = False
        config.CONFIDENCE_THRESHOLD = 0.1
        actions = [{"type": "hold", "confidence": 1.0, "params": {}}]
        results = self.engine.execute_plan(actions)
        assert results[0]["status"] == "ok"

    def test_execute_unknown_action_type(self):
        config.PAUSED = False
        config.CONFIDENCE_THRESHOLD = 0.1
        actions = [{"type": "unknown_xyz", "confidence": 1.0, "params": {}}]
        results = self.engine.execute_plan(actions)
        assert results[0]["status"] == "unknown_type"


class TestRunCycleAndStatus:
    """Test full cycle and status reporting."""

    @patch("skills.genesis.scripts.genesis_engine.StrategyManager")
    @patch("skills.genesis.scripts.genesis_engine.DecisionJournal")
    @patch("skills.genesis.scripts.genesis_engine.WalletManager")
    @patch("skills.genesis.scripts.genesis_engine.MarketOracle")
    def setup_method(self, method, mock_oracle, mock_wallet, mock_journal, mock_sm):
        from skills.genesis.scripts.genesis_engine import GenesisEngine
        self.engine = GenesisEngine()
        self.engine.oracle = MagicMock()
        self.engine.wallet = MagicMock()
        self.engine.strategy_mgr = MagicMock()
        self.engine.journal = MagicMock()
        self._orig_paused = config.PAUSED
        self._orig_evolution = config.EVOLUTION_INTERVAL_SEC

    def teardown_method(self):
        config.PAUSED = self._orig_paused
        config.EVOLUTION_INTERVAL_SEC = self._orig_evolution

    def test_run_cycle_increments_count(self):
        config.PAUSED = True
        config.EVOLUTION_INTERVAL_SEC = 0
        self.engine.oracle.fetch_all_prices.return_value = {}
        self.engine.wallet.get_all_balances.return_value = {}
        self.engine.strategy_mgr.get_active_strategies.return_value = []
        self.engine.strategy_mgr.get_strategy_summary.return_value = {"active_count": 0, "avg_pnl_bps": 0}
        self.engine.oracle.get_market_regime.return_value = {"regime_name": "mean_reversion", "volatility": 0.01, "confidence": 0.5}
        self.engine.journal.get_recent_decisions.return_value = []
        result = self.engine.run_cycle()
        assert result["cycle"] == 1
        assert "elapsed_sec" in result

    def test_get_status(self):
        self.engine.strategy_mgr.get_strategy_summary.return_value = {"active_count": 0}
        status = self.engine.get_status()
        assert status["running"] is False
        assert status["cycle_count"] == 0
        assert "preferences" in status

    def test_stop_sets_running_false(self):
        self.engine._running = True
        self.engine.stop()
        assert self.engine._running is False
