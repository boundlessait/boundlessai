"""Tests for Uniswap AI Skill integration module."""
import unittest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestUniswapSkillClient(unittest.TestCase):
    """Tests for UniswapSkillClient."""

    def setUp(self):
        from skills.genesis.scripts.uniswap_skill import UniswapSkillClient
        self.client = UniswapSkillClient(chain_id=196)

    def test_validate_hook_permissions_correct_flags(self):
        """Hook address ending in 0xC0 should have BEFORE_SWAP | AFTER_SWAP."""
        # Address ending in C0 = 1100_0000 = BEFORE_SWAP(0x80) | AFTER_SWAP(0x40)
        result = self.client.validate_hook_permissions("0x0000000000000000000000000000000000000aC0")
        self.assertTrue(result["valid"])
        self.assertTrue(result["flags"]["BEFORE_SWAP"])
        self.assertTrue(result["flags"]["AFTER_SWAP"])
        self.assertFalse(result["flags"]["beforeSwapReturnDelta"])
        self.assertEqual(result["security"], "PASS")

    def test_validate_hook_permissions_missing_flags(self):
        """Hook address without correct flags should fail validation."""
        result = self.client.validate_hook_permissions("0x0000000000000000000000000000000000000a00")
        self.assertFalse(result["valid"])
        self.assertFalse(result["flags"]["BEFORE_SWAP"])
        self.assertFalse(result["flags"]["AFTER_SWAP"])

    def test_validate_hook_permissions_return_delta_flag(self):
        """Hook with beforeSwapReturnDelta flag should fail security check."""
        # 0xD0 = 1101_0000 = BEFORE_SWAP | AFTER_SWAP | beforeSwapReturnDelta
        result = self.client.validate_hook_permissions("0x0000000000000000000000000000000000000aD0")
        self.assertFalse(result["valid"])
        self.assertTrue(result["flags"]["beforeSwapReturnDelta"])
        self.assertIn("FAIL", result["security"])

    def test_get_pool_key_sorts_currencies(self):
        """PoolKey should always have currency0 < currency1."""
        addr_low = "0x0000000000000000000000000000000000000001"
        addr_high = "0x0000000000000000000000000000000000000002"

        # Pass in wrong order
        key = self.client.get_pool_key(addr_high, addr_low)
        self.assertEqual(key["currency0"], addr_low)
        self.assertEqual(key["currency1"], addr_high)
        self.assertEqual(key["fee"], 0x800000)  # DYNAMIC_FEE_FLAG
        self.assertEqual(key["tickSpacing"], 60)

    def test_get_pool_key_correct_order(self):
        """PoolKey should preserve correct order."""
        addr_low = "0x0000000000000000000000000000000000000001"
        addr_high = "0x0000000000000000000000000000000000000002"

        key = self.client.get_pool_key(addr_low, addr_high)
        self.assertEqual(key["currency0"], addr_low)
        self.assertEqual(key["currency1"], addr_high)

    def test_estimate_hook_gas_within_budget(self):
        """3 modules should be within the 200k gas budget."""
        result = self.client.estimate_hook_gas(num_modules=3)
        self.assertTrue(result["within_budget"])
        self.assertEqual(result["num_modules"], 3)
        self.assertLess(result["total_estimated_gas"], 200_000)

    def test_estimate_hook_gas_exceeds_budget(self):
        """Too many modules should exceed the gas budget."""
        result = self.client.estimate_hook_gas(num_modules=10)
        self.assertFalse(result["within_budget"])

    def test_get_integration_summary(self):
        """Integration summary should list all Uniswap AI skills."""
        summary = self.client.get_integration_summary()
        skills = summary["uniswap_ai_skills"]
        self.assertIn("uniswap-v4-hooks", skills)
        self.assertIn("swap-integration", skills)
        self.assertIn("pay-with-any-token", skills)
        self.assertEqual(skills["uniswap-v4-hooks"]["status"], "integrated")
        self.assertIn("pool_manager", summary["v4_contracts"])

    def test_v4_contract_addresses(self):
        """V4 contract addresses should be set."""
        self.assertTrue(self.client.POOL_MANAGER.startswith("0x"))
        self.assertTrue(self.client.QUOTER.startswith("0x"))
        self.assertTrue(self.client.UNIVERSAL_ROUTER.startswith("0x"))


class TestMultiAgentOrchestrator(unittest.TestCase):
    """Tests for MultiAgentOrchestrator."""

    def setUp(self):
        from skills.genesis.scripts.multi_agent import MultiAgentOrchestrator
        self.orchestrator = MultiAgentOrchestrator()

    def test_all_agents_initialized(self):
        """Should have 4 specialized agents."""
        self.assertEqual(len(self.orchestrator.agents), 4)
        self.assertIn("SentinelAgent", self.orchestrator.agents)
        self.assertIn("StrategyAgent", self.orchestrator.agents)
        self.assertIn("IncomeAgent", self.orchestrator.agents)
        self.assertIn("RebalanceAgent", self.orchestrator.agents)

    def test_agent_wallet_isolation(self):
        """Each agent should have a unique wallet index."""
        indices = [a.wallet_index for a in self.orchestrator.agents.values()]
        self.assertEqual(len(indices), len(set(indices)))

    def test_sentinel_uses_master_wallet(self):
        """SentinelAgent should use the master wallet (index 0)."""
        sentinel = self.orchestrator.get_agent("SentinelAgent")
        self.assertEqual(sentinel.wallet_role, "master")
        self.assertEqual(sentinel.wallet_index, 0)

    def test_strategy_uses_strategy_wallet(self):
        """StrategyAgent should use the strategy wallet (index 1)."""
        agent = self.orchestrator.get_agent("StrategyAgent")
        self.assertEqual(agent.wallet_role, "strategy")
        self.assertEqual(agent.wallet_index, 1)

    def test_dispatch_unknown_agent(self):
        """Dispatching to unknown agent should return error."""
        result = self.orchestrator.dispatch("UnknownAgent", "test", {})
        self.assertIn("error", result)

    def test_health_check_initial(self):
        """Initial health check should show all agents healthy."""
        health = self.orchestrator.health_check()
        self.assertTrue(health["healthy"])
        self.assertEqual(health["total_agents"], 4)
        self.assertEqual(health["total_errors"], 0)
        self.assertTrue(health["all_idle"])

    def test_dispatch_increments_action_count(self):
        """Dispatching should increment the agent's action count."""
        from skills.genesis.scripts import config
        original_paused = config.PAUSED
        config.PAUSED = False
        try:
            self.orchestrator.dispatch("StrategyAgent", "create_strategy", {"preset": "calm_accumulator"})
            agent = self.orchestrator.get_agent("StrategyAgent")
            self.assertEqual(agent.action_count, 1)
        finally:
            config.PAUSED = original_paused


if __name__ == "__main__":
    unittest.main()
