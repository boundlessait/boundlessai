"""Tests for NFTMinter eligibility checks."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from skills.genesis.scripts.nft_minter import NFTMinter


def test_eligible_strategy():
    minter = NFTMinter()
    eligible, reasons = minter.check_mint_eligibility({
        "pnl_bps": 200, "total_swaps": 100, "run_hours": 72
    })
    assert eligible is True
    assert len(reasons) == 0


def test_ineligible_low_pnl():
    minter = NFTMinter()
    eligible, reasons = minter.check_mint_eligibility({
        "pnl_bps": 50, "total_swaps": 100, "run_hours": 72
    })
    assert eligible is False
    assert any("PnL" in r for r in reasons)


def test_ineligible_low_swaps():
    minter = NFTMinter()
    eligible, reasons = minter.check_mint_eligibility({
        "pnl_bps": 200, "total_swaps": 10, "run_hours": 72
    })
    assert eligible is False
    assert any("Swaps" in r for r in reasons)


def test_ineligible_low_runtime():
    minter = NFTMinter()
    eligible, reasons = minter.check_mint_eligibility({
        "pnl_bps": 200, "total_swaps": 100, "run_hours": 24
    })
    assert eligible is False
    assert any("Runtime" in r for r in reasons)


def test_all_ineligible():
    minter = NFTMinter()
    eligible, reasons = minter.check_mint_eligibility({
        "pnl_bps": 0, "total_swaps": 0, "run_hours": 0
    })
    assert eligible is False
    assert len(reasons) == 3


def test_config_hash_deterministic():
    minter = NFTMinter()
    h1 = minter.compute_config_hash(["0xAAA", "0xBBB"], {"fee": 3000})
    h2 = minter.compute_config_hash(["0xAAA", "0xBBB"], {"fee": 3000})
    assert h1 == h2
    assert h1.startswith("0x")


def test_config_hash_different():
    minter = NFTMinter()
    h1 = minter.compute_config_hash(["0xAAA"], {"fee": 3000})
    h2 = minter.compute_config_hash(["0xBBB"], {"fee": 3000})
    assert h1 != h2
