"""Tests for config module - validate safety defaults and structure."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from skills.genesis.scripts import config


def test_safety_defaults():
    """Safety defaults must be conservative."""
    assert config.PAUSED is True, "PAUSED must default to True"
    assert config.MODE == "paper", "MODE must default to paper"
    assert config.DRY_RUN is True, "DRY_RUN must default to True"


def test_chain_config():
    """X Layer chain configuration must be correct (mainnet-first)."""
    assert config.CHAIN_ID == 196, "Chain ID must be 196 (X Layer Mainnet)"
    assert "xlayer" in config.RPC_URL.lower()
    assert config.TESTNET_CHAIN_ID == 1952, "Testnet chain ID must be 1952"


def test_contracts_addresses():
    """All contract addresses must be present and valid."""
    required = ["assembler", "dynamic_fee_module", "mev_protection_module",
                "auto_rebalance_module", "strategy_nft"]
    for key in required:
        assert key in config.CONTRACTS, f"Missing contract: {key}"
        assert config.CONTRACTS[key].startswith("0x"), f"Invalid address for {key}"
        assert len(config.CONTRACTS[key]) == 42, f"Address wrong length for {key}"


def test_strategy_presets():
    """All presets must have required fields."""
    assert len(config.STRATEGY_PRESETS) >= 3
    for name, preset in config.STRATEGY_PRESETS.items():
        assert "modules" in preset, f"Preset {name} missing modules"
        assert "overrides" in preset, f"Preset {name} missing overrides"
        assert "market_conditions" in preset, f"Preset {name} missing market_conditions"
        assert len(preset["modules"]) > 0, f"Preset {name} has no modules"


def test_wallet_roles():
    """All wallet roles must be defined."""
    required = ["master", "strategy", "income", "reserve", "rebalance"]
    for role in required:
        assert role in config.WALLET_ROLES, f"Missing wallet role: {role}"
        assert "index" in config.WALLET_ROLES[role]
        assert "purpose" in config.WALLET_ROLES[role]


def test_decision_types():
    """Decision types must cover all operations."""
    expected = ["STRATEGY_CREATE", "STRATEGY_DEACTIVATE", "FEE_ADJUST",
                "REBALANCE_EXECUTE", "FUND_TRANSFER", "NFT_MINT"]
    for dt in expected:
        assert dt in config.DECISION_TYPES, f"Missing decision type: {dt}"


def test_x402_pricing():
    """x402 pricing tiers must be properly configured."""
    required = ["signal_query", "strategy_subscribe", "strategy_params_buy", "nft_license"]
    for product in required:
        assert product in config.X402_PRICING, f"Missing x402 product: {product}"
        tier = config.X402_PRICING[product]
        assert "amount" in tier
        assert "token" in tier
        assert "settle" in tier


def test_confidence_threshold():
    """Confidence threshold must be reasonable."""
    assert 0.5 <= config.CONFIDENCE_THRESHOLD <= 0.95


def test_max_position_size():
    """Max position size must be conservative."""
    assert config.MAX_POSITION_SIZE_PCT <= 50, "Position size too aggressive"
