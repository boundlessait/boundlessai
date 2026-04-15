"""Tests for MultiAgentOrchestrator - agent creation, dispatch, coordination."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, patch
import skills.genesis.scripts.config as config


def _make_orchestrator():
    """Create orchestrator with module-level singletons reset."""
    import skills.genesis.scripts.multi_agent as ma
    # Reset lazy singletons so tests are isolated
    ma._strategy_manager = None
    ma._decision_journal = None
    ma._hook_assembler = None
    ma._wallet_manager = None
    ma._payment_handler = None
    ma._market_oracle = None
    return ma.MultiAgentOrchestrator()


class TestAgentCreation:
    def test_four_agents_registered(self):
        orch = _make_orchestrator()
        assert len(orch.agents) == 4
        assert "SentinelAgent" in orch.agents
        assert "StrategyAgent" in orch.agents
        assert "IncomeAgent" in orch.agents
        assert "RebalanceAgent" in orch.agents

    def test_agent_wallet_indices(self):
        orch = _make_orchestrator()
        assert orch.agents["SentinelAgent"].wallet_index == 0
        assert orch.agents["StrategyAgent"].wallet_index == 1
        assert orch.agents["IncomeAgent"].wallet_index == 2
        assert orch.agents["RebalanceAgent"].wallet_index == 4

    def test_get_agent_returns_state(self):
        orch = _make_orchestrator()
        agent = orch.get_agent("SentinelAgent")
        assert agent is not None
        assert agent.name == "SentinelAgent"
        assert agent.status == "idle"

    def test_get_agent_unknown_returns_none(self):
        orch = _make_orchestrator()
        assert orch.get_agent("FakeAgent") is None


class TestAgentCapabilities:
    def test_sentinel_capabilities(self):
        orch = _make_orchestrator()
        caps = orch.get_agent_capabilities("SentinelAgent")
        assert "health_check" in caps
        assert "approve_operation" in caps
        assert "emergency_stop" in caps

    def test_unknown_agent_capabilities_empty(self):
        orch = _make_orchestrator()
        assert orch.get_agent_capabilities("FakeAgent") == []


class TestDispatch:
    def setup_method(self):
        self._orig_paused = config.PAUSED
        self._orig_dry_run = config.DRY_RUN

    def teardown_method(self):
        config.PAUSED = self._orig_paused
        config.DRY_RUN = self._orig_dry_run

    def test_dispatch_unknown_agent(self):
        orch = _make_orchestrator()
        result = orch.dispatch("FakeAgent", "do_stuff", {})
        assert "error" in result

    def test_dispatch_paused_blocks_non_sentinel(self):
        config.PAUSED = True
        orch = _make_orchestrator()
        result = orch.dispatch("StrategyAgent", "create_strategy", {})
        assert result["status"] == "paused"

    def test_dispatch_paused_allows_sentinel(self):
        config.PAUSED = True
        orch = _make_orchestrator()
        result = orch.dispatch("SentinelAgent", "health_check", {})
        assert result.get("status") != "paused"

    def test_dispatch_unsupported_action(self):
        config.PAUSED = False
        orch = _make_orchestrator()
        result = orch.dispatch("SentinelAgent", "fly_to_moon", {})
        assert "error" in result
        assert "Unsupported action" in result["error"]

    def test_dispatch_increments_action_count(self):
        config.PAUSED = False
        orch = _make_orchestrator()
        orch.dispatch("SentinelAgent", "health_check", {})
        assert orch.agents["SentinelAgent"].action_count == 1

    def test_dispatch_exception_sets_error_state(self):
        config.PAUSED = False
        orch = _make_orchestrator()
        # Monkey-patch handler to raise
        orch._handle_sentinel = MagicMock(side_effect=RuntimeError("boom"))
        result = orch.dispatch("SentinelAgent", "health_check", {})
        assert "error" in result
        assert orch.agents["SentinelAgent"].error_count == 1
        assert orch.agents["SentinelAgent"].status == "error"


class TestSentinelActions:
    def setup_method(self):
        self._orig_paused = config.PAUSED
        self._orig_dry_run = config.DRY_RUN

    def teardown_method(self):
        config.PAUSED = self._orig_paused
        config.DRY_RUN = self._orig_dry_run

    def test_health_check_healthy(self):
        config.PAUSED = False
        orch = _make_orchestrator()
        result = orch.dispatch("SentinelAgent", "health_check", {})
        assert result["status"] == "healthy"
        assert result["total_errors"] == 0

    def test_approve_operation_within_limit(self):
        config.PAUSED = False
        orch = _make_orchestrator()
        result = orch.dispatch("SentinelAgent", "approve_operation",
                               {"position_size_pct": 10, "operation_type": "create"})
        assert result["approved"] is True

    def test_approve_operation_exceeds_limit(self):
        config.PAUSED = False
        orch = _make_orchestrator()
        result = orch.dispatch("SentinelAgent", "approve_operation",
                               {"position_size_pct": 99, "operation_type": "create"})
        assert result["approved"] is False
        assert result["status"] == "rejected"

    @patch("skills.genesis.scripts.multi_agent._get_decision_journal")
    def test_emergency_stop(self, mock_journal_fn):
        config.PAUSED = False
        mock_journal_fn.return_value = MagicMock()
        orch = _make_orchestrator()
        result = orch.dispatch("SentinelAgent", "emergency_stop", {"reason": "test"})
        assert result["status"] == "emergency_stopped"
        assert len(result["stopped_agents"]) == 4
        # SentinelAgent status resets to idle after dispatch completes;
        # other agents should be stopped
        for name, agent in orch.agents.items():
            if name == "SentinelAgent":
                assert agent.status == "idle"
            else:
                assert agent.status == "stopped"


class TestHealthCheckTopLevel:
    def test_health_check_method(self):
        orch = _make_orchestrator()
        result = orch.health_check()
        assert result["total_agents"] == 4
        assert result["total_errors"] == 0
        assert result["all_idle"] is True

    def test_get_all_status(self):
        orch = _make_orchestrator()
        status = orch.get_all_status()
        assert len(status) == 4
        for name, info in status.items():
            assert "wallet_role" in info
            assert "status" in info
