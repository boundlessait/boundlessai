"""Tests for WalletManager - wallet roles, sub-wallet creation, balances."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch, MagicMock
import skills.genesis.scripts.config as config
from skills.genesis.scripts.wallet_manager import WalletManager


class TestWalletRoles:
    def test_all_roles_loaded(self):
        wm = WalletManager()
        for role in ["master", "strategy", "income", "reserve", "rebalance"]:
            assert role in wm.roles

    def test_role_index_returns_int(self):
        wm = WalletManager()
        assert wm._role_index("master") == 0
        assert wm._role_index("strategy") == 1
        assert wm._role_index("rebalance") == 4

    def test_role_index_unknown_returns_none(self):
        wm = WalletManager()
        assert wm._role_index("nonexistent") is None


class TestGetBalance:
    def setup_method(self):
        self._orig_dry_run = config.DRY_RUN

    def teardown_method(self):
        config.DRY_RUN = self._orig_dry_run

    def test_balance_unknown_role_returns_error(self):
        wm = WalletManager()
        result = wm.get_balance("nonexistent")
        assert "error" in result

    @patch("skills.genesis.scripts.wallet_manager.subprocess.run")
    def test_balance_calls_subprocess(self, mock_run):
        config.DRY_RUN = False
        mock_run.return_value = MagicMock(returncode=0, stdout='{"balance":"1.5"}')
        wm = WalletManager()
        result = wm.get_balance("master", token="OKB")
        assert result["balance"] == "1.5"


class TestTransfer:
    def setup_method(self):
        self._orig_dry_run = config.DRY_RUN

    def teardown_method(self):
        config.DRY_RUN = self._orig_dry_run

    def test_transfer_invalid_roles(self):
        wm = WalletManager()
        result = wm.transfer("nonexistent", "master", "1.0")
        assert "error" in result

    def test_transfer_dry_run(self):
        config.DRY_RUN = True
        wm = WalletManager()
        result = wm.transfer("master", "strategy", "1.0")
        assert result["dry_run"] is True


class TestInitializeWallets:
    def setup_method(self):
        self._orig_dry_run = config.DRY_RUN

    def teardown_method(self):
        config.DRY_RUN = self._orig_dry_run

    def test_initialize_wallets_dry_run(self):
        config.DRY_RUN = True
        wm = WalletManager()
        results = wm.initialize_wallets()
        assert len(results) == len(config.WALLET_ROLES)
        for role, out in results.items():
            assert out["dry_run"] is True

    def test_initialize_marks_roles(self):
        config.DRY_RUN = True
        wm = WalletManager()
        wm.initialize_wallets()
        assert len(wm.initialized) == len(config.WALLET_ROLES)


class TestCollectIncome:
    def setup_method(self):
        self._orig_dry_run = config.DRY_RUN

    def teardown_method(self):
        config.DRY_RUN = self._orig_dry_run

    @patch.object(WalletManager, "get_balance", return_value={"balance": "0"})
    def test_collect_income_empty(self, mock_bal):
        wm = WalletManager()
        result = wm.collect_income()
        assert result["status"] == "empty"

    @patch.object(WalletManager, "transfer", return_value={"status": "ok"})
    @patch.object(WalletManager, "get_balance", return_value={"balance": "5.0"})
    def test_collect_income_transfers(self, mock_bal, mock_transfer):
        wm = WalletManager()
        result = wm.collect_income()
        mock_transfer.assert_called_once_with("income", "master", "5.0", token="USDT")


class TestGetAllBalances:
    @patch.object(WalletManager, "get_balance", return_value={"balance": "0"})
    def test_get_all_balances(self, mock_bal):
        wm = WalletManager()
        balances = wm.get_all_balances()
        assert len(balances) == len(config.WALLET_ROLES)


class TestRunCmdErrors:
    def setup_method(self):
        self._orig_dry_run = config.DRY_RUN

    def teardown_method(self):
        config.DRY_RUN = self._orig_dry_run

    @patch("skills.genesis.scripts.wallet_manager.subprocess.run", side_effect=FileNotFoundError)
    def test_cli_not_found(self, mock_run):
        config.DRY_RUN = False
        wm = WalletManager()
        result = wm._run_cmd(["onchainos", "wallet", "balance", "--index", "0"])
        assert result["error"] == "cli_not_found"
