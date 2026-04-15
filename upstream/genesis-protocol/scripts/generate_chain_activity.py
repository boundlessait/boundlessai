#!/usr/bin/env python3
"""
Genesis Protocol - Automated Chain Activity Generator

Generates 30+ realistic AI agent transactions on X Layer Testnet (Chain 1952)
using `cast send` (Foundry) to interact with deployed Genesis Protocol contracts.

Covers the full agent lifecycle:
  - logDecision: market analysis, fee adjustments, rebalance signals, etc.
  - updatePerformance: P&L tracking across strategies
  - createStrategy: deploying new module combinations
  - onBeforeSwap: simulating swap processing through the hook

Usage:
    python scripts/generate_chain_activity.py
"""

import subprocess
import sys
import time
import os

# ─── Configuration ───────────────────────────────────────────────────────────
RPC = "https://xlayertestrpc.okx.com"
PK = os.environ.get("PRIVATE_KEY", "")

ASSEMBLER = "0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78"
DYNAMIC_FEE = "0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed"
MEV_PROTECTION = "0xA4f6ABd6F77928b06F075637ccBACA8f89e17386"
AUTO_REBALANCE = "0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee"
STRATEGY_NFT = "0xd969448dfc24Fe3Aff25e86db338fAB41b104319"

LIQUIDITY_SHIELD = "0x34Bd6972F086c947e4503185e1A1094d9846b2aC"
ORACLE_MODULE = "0x30049511c4c483E9500A74701DED562A8F1ea86f"

DELAY_BETWEEN_TX = 1  # seconds between transactions

# ─── Helpers ─────────────────────────────────────────────────────────────────

def keccak(text):
    """Compute keccak256 hash of a string using cast."""
    result = subprocess.run(
        ["cast", "keccak", text],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        print(f"  [WARN] keccak failed for '{text}': {result.stderr.strip()}")
        return "0x" + "00" * 32
    return result.stdout.strip()


def cast_send(to, sig, args, label=""):
    """Send a transaction via cast and return the tx hash."""
    cmd = ["cast", "send", to, sig] + args + [
        "--rpc-url", RPC,
        "--private-key", PK,
    ]
    tag = f" [{label}]" if label else ""
    print(f"  -> Sending{tag}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT]{tag} Transaction timed out after 120s")
        return None

    if result.returncode != 0:
        print(f"  [FAIL]{tag} {result.stderr.strip()[:200]}")
        return None

    # Parse tx hash from cast output
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("transactionHash"):
            tx_hash = stripped.split()[-1] if " " in stripped else stripped
            print(f"  [OK]{tag} tx: {tx_hash}")
            return tx_hash
        if stripped.startswith("0x") and len(stripped) == 66:
            print(f"  [OK]{tag} tx: {stripped}")
            return stripped

    # Fallback: print raw output
    print(f"  [OK]{tag} (output: {result.stdout.strip()[:120]})")
    return result.stdout.strip()


def section(title):
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ─── Transaction Generators ─────────────────────────────────────────────────

DECISION_TYPES = [
    ("MARKET_ANALYSIS", "ETH volatility at 5.8%, regime: volatile_defender, confidence: 0.87"),
    ("MARKET_ANALYSIS", "OKB stable at 2.1% vol, regime: calm_accumulator, confidence: 0.91"),
    ("MARKET_ANALYSIS", "BTC correlation spike to 0.94, cross-asset contagion risk elevated"),
    ("MARKET_ANALYSIS", "ETH-USDC 1h candle analysis: bearish engulfing, vol expanding 3.2%->4.8%"),
    ("MARKET_ANALYSIS", "Funding rate negative -0.012%, shorts dominant, potential squeeze setup"),
    ("FEE_ADJUST", "Raising min fee to 1000 bps due to elevated volatility regime"),
    ("FEE_ADJUST", "Lowering max fee to 3000 bps, calm market detected for 6 hours"),
    ("FEE_ADJUST", "Dynamic fee sensitivity adjusted to 1.2x for trending market"),
    ("FEE_ADJUST", "Fee optimization: sensitivity 8000->12000, responding to vol regime shift"),
    ("REBALANCE_SIGNAL", "Position at 87% of upper boundary, soft trigger activated"),
    ("REBALANCE_SIGNAL", "IL threshold exceeded at 2.3%, forced rebalance initiated"),
    ("REBALANCE_SIGNAL", "TWAP rebalance scheduled over 5 blocks, tick drift: +12"),
    ("REBALANCE_SIGNAL", "Auto-rebalance: tick moved 15 ticks, cooldown expired, executing immediate"),
    ("PERFORMANCE_EVAL", "Strategy #0 24h P&L: +1.52%, 47 swaps, fee revenue: 0.8 ETH"),
    ("PERFORMANCE_EVAL", "Strategy #1 24h P&L: -0.31%, 23 swaps, underperforming baseline"),
    ("PERFORMANCE_EVAL", "Portfolio sharpe ratio: 1.84, max drawdown: 0.6% over 7 days"),
    ("PERFORMANCE_EVAL", "DeFi benchmark: Genesis yield 12.3% vs Aave 4.1% vs Compound 3.8%"),
    ("META_COGNITION", "Self-assessment: prediction accuracy 78%, vol-response latency 42s"),
    ("META_COGNITION", "Bias check: no over-trading detected, wallet utilization at 94%"),
    ("META_COGNITION", "Adjusting risk_tolerance 0.50 -> 0.47, rebalance_eagerness 0.60 -> 0.64"),
    ("META_COGNITION", "Layer 5 review: 12 decisions in 24h, 9 correct, calibration score 0.82"),
    ("REGIME_SHIFT", "Transitioning from calm_accumulator to trend_rider, ETH breaking range"),
    ("REGIME_SHIFT", "Volatile regime confirmed for OKB pair, activating MEV protection"),
    ("REGIME_SHIFT", "Market calm restored after 4h volatility event, reverting to accumulator"),
    ("REGIME_SHIFT", "Full defense mode: vol 12.4%, MEV detected, activating all 5 modules"),
    ("CCA_AUCTION_CREATE", "MEV opportunity detected: 0.05 ETH extractable, creating CCA auction"),
    ("CCA_AUCTION_SETTLE", "CCA auction settled: 3 bidders, winning bid 0.04 ETH, LP share: 0.034 ETH"),
    ("LIQUIDITY_SHIELD", "JIT attack blocked: price impact 120bps exceeded 50bps threshold"),
    ("ORACLE_UPDATE", "TWAP oracle updated: 30min avg 1823.45, volatility estimate 4.7%"),
    ("DEFI_BENCHMARK", "Cross-protocol yield comparison: Genesis 11.2% vs market avg 5.1%"),
]


def run_log_decisions(tx_count):
    """Send logDecision transactions to the assembler."""
    section(f"LOG DECISIONS ({len(DECISION_TYPES)} transactions)")
    sent = 0
    for i, (dtype, reasoning) in enumerate(DECISION_TYPES):
        decision_hash = keccak(dtype)
        reasoning_hash = keccak(reasoning)
        strategy_id = str(i % 3)
        label = f"Decision {i+1}: {dtype}"
        result = cast_send(
            ASSEMBLER,
            "logDecision(uint256,bytes32,bytes32,bytes)",
            [strategy_id, decision_hash, reasoning_hash, "0x"],
            label,
        )
        sent += 1 if result else 0
        tx_count[0] += 1 if result else 0
        time.sleep(DELAY_BETWEEN_TX)
    print(f"\n  Decisions sent: {sent}/{len(DECISION_TYPES)}")
    return sent


PERFORMANCE_UPDATES = [
    (0, 152, 47, "Steady fee accumulation in calm market"),
    (0, 287, 89, "High volume day, strong fee capture"),
    (0, -31, 112, "Minor IL from price movement, fees offset partially"),
    (1, 98, 23, "New strategy warming up, initial results positive"),
    (1, -45, 35, "Rebalance cost exceeded fee income briefly"),
    (1, 210, 58, "Recovery after regime adjustment, strong rebound"),
    (2, 175, 41, "MEV protection saved estimated 0.3 ETH from sandwich"),
    (2, 320, 72, "Peak performance day, all modules contributing"),
    (0, 143, 130, "Consistent mid-range performance, no anomalies"),
    (1, -12, 90, "Near breakeven, awaiting regime shift confirmation"),
    (0, 195, 155, "Fee optimization pays off: +1.95% after sensitivity tweak"),
    (2, -68, 45, "Shield module triggered 3x, absorbed impact cost"),
    (1, 412, 102, "Best day: CCA auction captured 0.04 ETH MEV as LP revenue"),
    (0, 88, 178, "Steady state: low vol, consistent small gains"),
    (2, 245, 96, "Oracle TWAP feed improved rebalance timing by 15%"),
]


def run_update_performance(tx_count):
    """Send updatePerformance transactions."""
    section(f"UPDATE PERFORMANCE ({len(PERFORMANCE_UPDATES)} transactions)")
    sent = 0
    for i, (sid, pnl_bps, swaps, note) in enumerate(PERFORMANCE_UPDATES):
        label = f"Perf {i+1}: Strategy#{sid} PnL={pnl_bps:+d}bps"
        result = cast_send(
            ASSEMBLER,
            "updatePerformance(uint256,int256)",
            [str(sid), str(pnl_bps)],
            label,
        )
        sent += 1 if result else 0
        tx_count[0] += 1 if result else 0
        time.sleep(DELAY_BETWEEN_TX)
    print(f"\n  Performance updates sent: {sent}/{len(PERFORMANCE_UPDATES)}")
    return sent


STRATEGY_CONFIGS = [
    ("calm_accumulator", [DYNAMIC_FEE, AUTO_REBALANCE]),
    ("volatile_defender", [DYNAMIC_FEE, MEV_PROTECTION, AUTO_REBALANCE]),
    ("trend_rider", [DYNAMIC_FEE, MEV_PROTECTION, AUTO_REBALANCE]),
    ("sniper_mode", [DYNAMIC_FEE, MEV_PROTECTION]),
    ("full_defense", [DYNAMIC_FEE, MEV_PROTECTION, AUTO_REBALANCE, LIQUIDITY_SHIELD, ORACLE_MODULE]),
    ("shield_accumulator", [DYNAMIC_FEE, AUTO_REBALANCE, LIQUIDITY_SHIELD]),
    ("oracle_defender", [DYNAMIC_FEE, MEV_PROTECTION, ORACLE_MODULE]),
]


def run_create_strategies(tx_count):
    """Send createStrategy transactions."""
    section(f"CREATE STRATEGIES ({len(STRATEGY_CONFIGS)} transactions)")
    sent = 0
    for i, (name, modules) in enumerate(STRATEGY_CONFIGS):
        modules_str = "[" + ",".join(modules) + "]"
        label = f"Strategy {i+1}: {name} ({len(modules)} modules)"
        result = cast_send(
            ASSEMBLER,
            "createStrategy(address[])",
            [modules_str],
            label,
        )
        sent += 1 if result else 0
        tx_count[0] += 1 if result else 0
        time.sleep(DELAY_BETWEEN_TX)
    print(f"\n  Strategies created: {sent}/{len(STRATEGY_CONFIGS)}")
    return sent


SWAP_SCENARIOS = [
    (0, True,  "1000000000000000000", "Normal ETH/USDC buy, 1 ETH"),
    (0, False, "500000000000000000",  "ETH/USDC sell, 0.5 ETH"),
    (1, True,  "2500000000000000000", "Large OKB/USDT buy, 2.5 ETH"),
    (2, False, "750000000000000000",  "Medium sell during volatile regime, 0.75 ETH"),
    (0, True,  "100000000000000000",  "Small buy, testing dynamic fee at low vol"),
    (1, False, "3000000000000000000", "Whale sell, MEV protection active"),
    (2, True,  "200000000000000000",  "DCA buy in full_defense mode"),
    (0, True,  "1500000000000000000", "Post-rebalance buy to test new range"),
    (1, True,  "800000000000000000",  "Momentum buy, trend_rider active"),
    (2, False, "600000000000000000",  "Take profit sell, oracle TWAP confirms top"),
]

WALLET = "0xd2D120eB7cEd38551cCeFb48021067d41D6542d3"

def run_swap_simulations(tx_count):
    """Send onBeforeSwap calls to process swaps through hook modules."""
    section(f"SWAP SIMULATIONS ({len(SWAP_SCENARIOS)} transactions)")
    sent = 0
    for i, (strategy_id, zero_for_one, amount, note) in enumerate(SWAP_SCENARIOS):
        z = "true" if zero_for_one else "false"
        label = f"Swap {i+1}: strat#{strategy_id} {'buy' if zero_for_one else 'sell'} - {note}"
        result = cast_send(
            ASSEMBLER,
            "onBeforeSwap(uint256,address,uint256,bool)",
            [str(strategy_id), WALLET, amount, z],
            label,
        )
        sent += 1 if result else 0
        tx_count[0] += 1 if result else 0
        time.sleep(DELAY_BETWEEN_TX)
    print(f"\n  Swaps simulated: {sent}/{len(SWAP_SCENARIOS)}")
    return sent


def main():
    if not PK:
        print("[ERROR] PRIVATE_KEY environment variable is not set.")
        sys.exit(1)

    print("=" * 60)
    print("  Genesis Protocol - Chain Activity Generator")
    print("  X Layer Testnet (Chain 1952)")
    print(f"  RPC: {RPC}")
    print(f"  Assembler: {ASSEMBLER}")
    print("=" * 60)

    tx_count = [0]  # mutable counter

    t0 = time.time()

    run_log_decisions(tx_count)
    run_update_performance(tx_count)
    run_create_strategies(tx_count)
    run_swap_simulations(tx_count)

    elapsed = time.time() - t0

    print(f"\n{'=' * 60}")
    print(f"  COMPLETE")
    print(f"  Total transactions confirmed: {tx_count[0]}")
    total_attempted = len(DECISION_TYPES) + len(PERFORMANCE_UPDATES) + len(STRATEGY_CONFIGS) + len(SWAP_SCENARIOS)
    print(f"  Total attempted:              {total_attempted}")
    print(f"  Elapsed time:                 {elapsed:.1f}s")
    print(f"{'=' * 60}")

    if tx_count[0] == 0:
        print("\n  [WARN] No transactions succeeded. Check:")
        print("    - Is the RPC reachable?")
        print("    - Does the wallet have gas funds?")
        print("    - Are the contracts deployed at the expected addresses?")
        sys.exit(1)


if __name__ == "__main__":
    main()
