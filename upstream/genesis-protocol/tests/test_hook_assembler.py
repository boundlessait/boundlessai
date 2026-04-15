"""Tests for HookAssembler - module selection, param computation, deployment."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch, MagicMock
import json

import skills.genesis.scripts.config as config


class TestSelectModules:
    def setup_method(self):
        from skills.genesis.scripts.hook_assembler import HookAssembler
        self.assembler = HookAssembler()

    def test_low_vol_sideways_selects_calm(self):
        name, modules = self.assembler.select_modules({"volatility_bps": 100, "trend": "sideways"})
        assert name == "calm_accumulator"
        assert "dynamic_fee" in modules

    def test_high_vol_selects_volatile_defender(self):
        name, modules = self.assembler.select_modules({"volatility_bps": 700, "trend": "any"})
        assert name == "volatile_defender"
        assert "mev_protection" in modules

    def test_trending_mid_vol_selects_trend_rider(self):
        name, modules = self.assembler.select_modules({"volatility_bps": 400, "trend": "trending"})
        assert name == "trend_rider"

    def test_no_match_defaults_to_calm(self):
        name, modules = self.assembler.select_modules({"volatility_bps": 99999, "trend": "sideways"})
        # volatile_defender has vol_range [500, 9999], so 99999 is out of all ranges
        assert name == "calm_accumulator"

    def test_select_returns_list_of_strings(self):
        _, modules = self.assembler.select_modules({"volatility_bps": 100, "trend": "sideways"})
        assert isinstance(modules, list)
        for m in modules:
            assert isinstance(m, str)


class TestComputeParams:
    def setup_method(self):
        from skills.genesis.scripts.hook_assembler import HookAssembler
        self.assembler = HookAssembler()

    def test_compute_params_returns_all_modules(self):
        params = self.assembler.compute_params("calm_accumulator", {})
        assert "dynamic_fee" in params
        assert "auto_rebalance" in params

    def test_compute_params_applies_overrides(self):
        params = self.assembler.compute_params("calm_accumulator", {})
        # calm_accumulator overrides min_fee to 100
        assert params["dynamic_fee"]["min_fee"] == 100

    def test_compute_params_dynamic_sensitivity_scaling(self):
        params = self.assembler.compute_params("calm_accumulator",
                                               {"realised_vol_bps": 200, "implied_vol_bps": 100})
        # ratio = 200/100 = 2.0 (capped at 2.0), sensitivity = 8000 * 2.0 = 16000
        assert params["dynamic_fee"]["sensitivity"] == 16000

    def test_compute_params_no_vol_data_no_scaling(self):
        params = self.assembler.compute_params("calm_accumulator", {})
        # No realised_vol_bps, so sensitivity stays at override value 8000
        assert params["dynamic_fee"]["sensitivity"] == 8000


class TestEncodeModuleParams:
    def setup_method(self):
        from skills.genesis.scripts.hook_assembler import HookAssembler
        self.assembler = HookAssembler()

    def test_encode_dynamic_fee(self):
        params = {"base_fee": 3000, "min_fee": 500, "max_fee": 10000,
                  "sensitivity": 10000, "low_threshold": 200, "high_threshold": 800}
        encoded = self.assembler._encode_module_params("dynamic_fee", params)
        assert encoded == "3000,500,10000,10000,200,800"

    def test_encode_mev_protection_bool(self):
        params = {"swap_count_threshold": 3, "volume_threshold": 10000,
                  "penalty_fee": 5000, "block_suspicious": True}
        encoded = self.assembler._encode_module_params("mev_protection", params)
        assert encoded == "3,10000,5000,1"

    def test_encode_unknown_module_returns_empty(self):
        encoded = self.assembler._encode_module_params("nonexistent_module", {})
        assert encoded == ""


class TestDeploymentCost:
    def test_cost_estimate_structure(self):
        from skills.genesis.scripts.hook_assembler import HookAssembler
        assembler = HookAssembler()
        cost = assembler.get_deployment_cost_estimate()
        assert "total_usd" in cost
        assert cost["num_transactions"] == 7  # 3*2 + 1
        assert cost["total_usd"] > 0


class TestRunCmdDryRun:
    def setup_method(self):
        self._orig_dry_run = config.DRY_RUN

    def teardown_method(self):
        config.DRY_RUN = self._orig_dry_run

    def test_dry_run_skips_write_commands(self):
        config.DRY_RUN = True
        from skills.genesis.scripts.hook_assembler import HookAssembler
        assembler = HookAssembler()
        result = assembler._run_cmd(["onchainos", "wallet", "deploy", "--contract", "X"])
        assert result["dry_run"] is True

    @patch("skills.genesis.scripts.hook_assembler.subprocess.run")
    def test_non_dry_run_calls_subprocess(self, mock_run):
        config.DRY_RUN = False
        mock_run.return_value = MagicMock(returncode=0, stdout='{"address":"0x123"}')
        from skills.genesis.scripts.hook_assembler import HookAssembler
        assembler = HookAssembler()
        result = assembler._run_cmd(["onchainos", "wallet", "deploy", "--contract", "X"])
        assert result["address"] == "0x123"
        mock_run.assert_called_once()
