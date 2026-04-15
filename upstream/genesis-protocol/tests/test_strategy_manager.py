"""Tests for StrategyManager - lifecycle, monitoring, deactivation."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import tempfile
import json
import time
from unittest.mock import patch, MagicMock

import skills.genesis.scripts.config as config


def _make_strategy_manager():
    """Create a StrategyManager with all external deps mocked."""
    with patch("skills.genesis.scripts.strategy_manager.HookAssembler") as mock_ha, \
         patch("skills.genesis.scripts.strategy_manager.DecisionJournal") as mock_dj, \
         patch("skills.genesis.scripts.strategy_manager.NFTMinter") as mock_nft, \
         patch("skills.genesis.scripts.strategy_manager.SecurityScanner") as mock_sec, \
         patch("skills.genesis.scripts.strategy_manager.os.path.isfile", return_value=False):
        from skills.genesis.scripts.strategy_manager import StrategyManager
        sm = StrategyManager()
    return sm


class TestCreateStrategy:
    def test_create_strategy_success(self):
        sm = _make_strategy_manager()
        sm.assembler.compose_and_deploy.return_value = {
            "strategy_id": "s1",
            "modules": {"dynamic_fee": "0xA", "auto_rebalance": "0xB"},
        }
        sm._save_local_registry = MagicMock()
        record = sm.create_strategy("low_vol", {"volatility_bps": 100})
        assert record["id"] == "s1"
        assert record["status"] == "active"
        assert "s1" in sm.strategies

    def test_create_strategy_deploy_error(self):
        sm = _make_strategy_manager()
        sm.assembler.compose_and_deploy.return_value = {"error": "deploy_failed:dynamic_fee"}
        record = sm.create_strategy("low_vol", {})
        assert "error" in record

    def test_create_strategy_security_fail(self):
        sm = _make_strategy_manager()
        sm.security.is_safe_for_strategy.return_value = (False, "risky token")
        orig_paused = config.PAUSED
        config.PAUSED = False
        try:
            record = sm.create_strategy("low_vol", {"token0": "0xA", "token1": "0xB"})
            assert "error" in record
            assert "Security" in record["error"]
        finally:
            config.PAUSED = orig_paused


class TestMonitorStrategy:
    def test_monitor_unknown_strategy(self):
        sm = _make_strategy_manager()
        result = sm.monitor_strategy("nonexistent")
        assert result["healthy"] is False

    def test_monitor_healthy_strategy(self):
        sm = _make_strategy_manager()
        sm.strategies["s1"] = {
            "id": "s1", "status": "active", "created_at": int(time.time()) - 3600,
            "pnl_bps": 100, "modules": ["dynamic_fee"],
            "total_swaps": 50, "total_volume": 1000,
        }
        result = sm.monitor_strategy("s1")
        assert result["healthy"] is True

    def test_monitor_inactive_strategy(self):
        sm = _make_strategy_manager()
        sm.strategies["s1"] = {
            "id": "s1", "status": "inactive", "created_at": int(time.time()) - 3600,
            "pnl_bps": 100, "modules": ["dynamic_fee"],
        }
        result = sm.monitor_strategy("s1")
        assert result["healthy"] is False


class TestShouldDeactivate:
    def test_persistent_loss(self):
        sm = _make_strategy_manager()
        should, reason = sm.should_deactivate("s1", {"pnl_bps": -600, "total_swaps": 100})
        assert should is True
        assert "loss" in reason

    def test_underperforming_benchmark(self):
        sm = _make_strategy_manager()
        should, reason = sm.should_deactivate("s1", {"pnl_bps": 0, "vs_benchmark_bps": -1100, "total_swaps": 100})
        assert should is True

    def test_idle_negative_pnl(self):
        sm = _make_strategy_manager()
        should, reason = sm.should_deactivate("s1", {"pnl_bps": -10, "total_swaps": 2, "annualised_bps": -50})
        assert should is True
        assert "idle" in reason

    def test_acceptable_performance(self):
        sm = _make_strategy_manager()
        should, reason = sm.should_deactivate("s1", {"pnl_bps": 50, "total_swaps": 100, "vs_benchmark_bps": 0, "annualised_bps": 100})
        assert should is False


class TestShouldRebalance:
    def test_vol_below_range(self):
        sm = _make_strategy_manager()
        sm.strategies["s1"] = {
            "id": "s1", "status": "active", "preset_name": "volatile_defender",
            "market_regime_at_creation": "high_vol",
        }
        # volatile_defender vol_range is [500, 9999], shift threshold 300
        # vol 100 < 500 - 300 = 200 -> triggers rebalance
        should, reason = sm.should_rebalance("s1", {"volatility_bps": 100})
        assert should is True

    def test_vol_within_range(self):
        sm = _make_strategy_manager()
        sm.strategies["s1"] = {
            "id": "s1", "status": "active", "preset_name": "calm_accumulator",
            "market_regime_at_creation": "low_vol",
        }
        should, reason = sm.should_rebalance("s1", {"volatility_bps": 150})
        assert should is False
        assert "within bounds" in reason

    def test_regime_shift(self):
        sm = _make_strategy_manager()
        sm.strategies["s1"] = {
            "id": "s1", "status": "active", "preset_name": "calm_accumulator",
            "market_regime_at_creation": "low_vol",
        }
        should, reason = sm.should_rebalance("s1", {"volatility_bps": 150, "regime": "high_vol"})
        assert should is True

    def test_inactive_strategy(self):
        sm = _make_strategy_manager()
        sm.strategies["s1"] = {"id": "s1", "status": "inactive", "preset_name": "calm_accumulator"}
        should, reason = sm.should_rebalance("s1", {"volatility_bps": 100})
        assert should is False


class TestGetStrategySummary:
    def test_empty_summary(self):
        sm = _make_strategy_manager()
        summary = sm.get_strategy_summary()
        assert summary["active_count"] == 0

    def test_summary_with_strategies(self):
        sm = _make_strategy_manager()
        sm.strategies["s1"] = {"id": "s1", "status": "active", "pnl_bps": 100, "total_volume": 500}
        sm.strategies["s2"] = {"id": "s2", "status": "active", "pnl_bps": -50, "total_volume": 300}
        sm.strategies["s3"] = {"id": "s3", "status": "inactive", "pnl_bps": 200, "total_volume": 100}
        summary = sm.get_strategy_summary()
        assert summary["active_count"] == 2
        assert summary["total_volume"] == 800
        assert summary["best_pnl_bps"] == 100
        assert summary["worst_pnl_bps"] == -50


class TestSelectPreset:
    def test_string_regime_mapping(self):
        sm = _make_strategy_manager()
        assert sm._select_preset("low_vol") == "calm_accumulator"
        assert sm._select_preset("high_vol") == "volatile_defender"
        assert sm._select_preset("trending") == "trend_rider"

    def test_unknown_regime_defaults(self):
        sm = _make_strategy_manager()
        assert sm._select_preset("unknown_regime") == "calm_accumulator"

    def test_dict_regime_with_preset_name(self):
        sm = _make_strategy_manager()
        assert sm._select_preset({"preset_name": "volatile_defender"}) == "volatile_defender"
