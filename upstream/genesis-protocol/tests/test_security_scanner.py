"""Tests for SecurityScanner -- token risk assessment logic."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from skills.genesis.scripts.security_scanner import SecurityScanner


def _scanner():
    """Create a scanner instance (DRY_RUN=True by default)."""
    return SecurityScanner()


def test_scan_token_returns_dict():
    """scan_token must return a dict with required keys."""
    result = _scanner().scan_token("0x" + "a" * 40)
    assert isinstance(result, dict)
    assert "risk_score" in result
    assert "flags" in result
    assert "safe" in result


def test_scan_token_dry_run_is_safe():
    """In DRY_RUN mode, simulated score should be below threshold (safe)."""
    result = _scanner().scan_token("0x" + "b" * 40)
    assert result["safe"] is True
    assert result["risk_score"] <= 50


def test_scan_pool_combines_risks():
    """scan_pool must return combined risk from both tokens."""
    result = _scanner().scan_pool("0x" + "a" * 40, "0x" + "b" * 40)
    assert "token0" in result
    assert "token1" in result
    assert "combined_risk" in result
    assert "safe" in result
    assert result["combined_risk"] == max(
        result["token0"]["risk_score"],
        result["token1"]["risk_score"],
    )


def test_is_safe_for_strategy_returns_tuple():
    """is_safe_for_strategy must return (bool, str)."""
    safe, reason = _scanner().is_safe_for_strategy("0x" + "a" * 40, "0x" + "b" * 40)
    assert isinstance(safe, bool)
    assert isinstance(reason, str)


def test_is_safe_dry_run_passes():
    """In DRY_RUN mode, simulated tokens should pass safety check."""
    safe, reason = _scanner().is_safe_for_strategy("0x" + "a" * 40, "0x" + "b" * 40)
    assert safe is True
    assert "passed" in reason.lower() or "ok" in reason.lower()


def test_scan_pool_safe_requires_both_tokens_safe():
    """Pool is only safe if both tokens are safe."""
    result = _scanner().scan_pool("0x" + "a" * 40, "0x" + "b" * 40)
    expected = result["token0"]["safe"] and result["token1"]["safe"]
    assert result["safe"] == expected
