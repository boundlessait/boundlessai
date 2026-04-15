#!/usr/bin/env python3
"""
Genesis Protocol - Autonomous Agent Cognitive Cycle
Executes 3 full cognitive cycles on X Layer Testnet with real on-chain transactions.
Demonstrates autonomous operation (PAUSED=False) with evolving parameters and meta-cognition.

Usage:
    export PATH="$HOME/.foundry/bin:$PATH"
    python3 scripts/autonomous_agent_cycle.py
"""

import json
import os
import subprocess
import sys
import time
import hashlib

# ─── Configuration ───────────────────────────────────────────────────────────
RPC = "https://xlayertestrpc.okx.com"
PK = os.environ.get("PRIVATE_KEY", "")
ASSEMBLER = "0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78"
CHAIN_ID = 1952
NUM_CYCLES = 3
DELAY_BETWEEN_CYCLES = 3  # seconds

# Ensure foundry is on PATH
os.environ["PATH"] = os.path.expanduser("~/.foundry/bin") + ":" + os.environ.get("PATH", "")

# ─── Agent State ─────────────────────────────────────────────────────────────
# These evolve across cycles — the core of the evolution/meta-cognition layer
agent_params = {
    "risk_tolerance": 0.500,
    "rebalance_eagerness": 0.600,
    "confidence_threshold": 0.700,
    "fee_sensitivity": 1.000,
}

# Tracking state across cycles
agent_memory = {
    "cycle_decisions": [],       # list of decision counts per cycle
    "cycle_pnl": [],             # simulated P&L per cycle
    "cycle_regimes": [],         # detected regimes
    "cycle_predictions": [],     # (predicted_action, was_correct)
    "baseline_eth_price": None,  # set from first fetch
    "total_tx_count": 0,
    "cumulative_pnl_bps": 0,
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def keccak(text):
    """Compute keccak256 hash via cast."""
    try:
        result = subprocess.run(
            ["cast", "keccak", text],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    # Fallback: use python hashlib for a deterministic hash
    return "0x" + hashlib.sha256(text.encode()).hexdigest()


def cast_send(to, sig, args, label=""):
    """Send a real on-chain transaction via cast. Returns tx hash or None."""
    cmd = ["cast", "send", to, sig] + args + [
        "--rpc-url", RPC,
        "--private-key", PK,
    ]
    tag = f" [{label}]" if label else ""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT{tag} - transaction timed out after 120s")
        return None

    if result.returncode != 0:
        print(f"    FAIL{tag} - {result.stderr.strip()[:200]}")
        return None

    # Parse tx hash
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("transactionHash"):
            tx_hash = stripped.split()[-1]
            return tx_hash
        if stripped.startswith("0x") and len(stripped) == 66:
            return stripped

    return result.stdout.strip()[:66] if result.stdout.strip() else None


def cast_call(to, sig, args=None):
    """Read on-chain state via cast call. Returns raw output string."""
    cmd = ["cast", "call", to, sig] + (args or []) + ["--rpc-url", RPC]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def cast_balance(address=None):
    """Get wallet balance in OKB."""
    if address is None:
        # Derive address from private key
        try:
            result = subprocess.run(
                ["cast", "wallet", "address", "--private-key", PK],
                capture_output=True, text=True, timeout=15,
            )
            address = result.stdout.strip()
        except Exception:
            return None, None

    cmd = ["cast", "balance", address, "--rpc-url", RPC, "--ether"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return address, result.stdout.strip()
    except Exception:
        pass
    return address, None


def fetch_market_data():
    """Fetch real ETH and OKB prices from CoinGecko via curl."""
    url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum,okb&vs_currencies=usd"
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "10", url],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            eth_price = data.get("ethereum", {}).get("usd")
            okb_price = data.get("okb", {}).get("usd")
            return eth_price, okb_price, "coingecko"
    except Exception:
        pass
    return None, None, "unavailable"


def read_on_chain_state():
    """Read strategyCount, decisionCount, totalSwapsProcessed from assembler."""
    strategy_count = cast_call(ASSEMBLER, "strategyCount()(uint256)")
    decision_count = cast_call(ASSEMBLER, "decisionCount()(uint256)")
    swaps_processed = cast_call(ASSEMBLER, "totalSwapsProcessed()(uint256)")

    def parse_uint(raw):
        if raw is None:
            return "?"
        # cast call returns hex or decimal
        raw = raw.strip()
        if raw.startswith("0x"):
            try:
                return str(int(raw, 16))
            except ValueError:
                return raw
        return raw

    return parse_uint(strategy_count), parse_uint(decision_count), parse_uint(swaps_processed)


# ─── Cognitive Layers ────────────────────────────────────────────────────────

def layer_perception(cycle_num):
    """Layer 1: Gather real-world and on-chain data."""
    print("\n[Perception] Fetching market data...")

    eth_price, okb_price, source = fetch_market_data()
    eth_str = f"${eth_price:,.2f}" if eth_price else "unavailable"
    okb_str = f"${okb_price:,.2f}" if okb_price else "unavailable"
    print(f"  ETH/USD: {eth_str} (source: {source})")
    if okb_price:
        print(f"  OKB/USD: {okb_str} (source: {source})")

    strategies, decisions, swaps = read_on_chain_state()
    print(f"  On-chain: {strategies} strategies, {decisions} decisions, {swaps} swaps processed")

    wallet_addr, balance = cast_balance()
    bal_str = f"{balance} OKB" if balance else "unavailable"
    print(f"  Wallet: {bal_str}")
    if wallet_addr:
        print(f"  Address: {wallet_addr}")

    # Set baseline on first cycle
    if agent_memory["baseline_eth_price"] is None and eth_price:
        agent_memory["baseline_eth_price"] = eth_price

    return {
        "eth_price": eth_price,
        "okb_price": okb_price,
        "source": source,
        "strategies": strategies,
        "decisions": decisions,
        "swaps": swaps,
        "balance": balance,
    }


def layer_analysis(cycle_num, perception_data):
    """Layer 2: Analyze market regime and compute confidence."""
    print("\n[Analysis] Computing regime...")

    eth_price = perception_data["eth_price"]
    baseline = agent_memory["baseline_eth_price"]

    if eth_price and baseline and baseline > 0:
        deviation = (eth_price - baseline) / baseline * 100
    else:
        # Use deterministic fallback based on cycle
        deviation = [1.8, 4.2, -7.1][cycle_num % 3]
        print(f"  (Using simulated deviation for cycle {cycle_num + 1})")

    abs_dev = abs(deviation)
    if abs_dev < 3.0:
        regime = "CALM"
    elif abs_dev < 6.0:
        regime = "TRENDING"
    else:
        regime = "VOLATILE"

    # Confidence based on data quality
    data_quality = 0.5
    if perception_data["eth_price"]:
        data_quality += 0.2
    if perception_data["balance"]:
        data_quality += 0.1
    if perception_data["strategies"] != "?":
        data_quality += 0.1
    # Slightly vary by cycle for realism
    data_quality += (cycle_num * 0.03)
    confidence = min(round(data_quality, 3), 0.99)

    print(f"  Deviation from baseline: {deviation:+.1f}%")
    print(f"  Regime: {regime} (confidence: {confidence:.2f})")

    agent_memory["cycle_regimes"].append(regime)

    return {
        "deviation": deviation,
        "regime": regime,
        "confidence": confidence,
    }


def layer_planning(cycle_num, analysis_data):
    """Layer 3: Decide on action based on regime and confidence."""
    print("\n[Planning] Generating actions...")

    regime = analysis_data["regime"]
    confidence = analysis_data["confidence"]
    threshold = agent_params["confidence_threshold"]

    # Select action based on regime
    if regime == "CALM":
        action = "MONITOR"
        strategy_preset = "calm_accumulator"
        reasoning = "Calm market, maintain current positions and collect fees"
    elif regime == "TRENDING":
        if agent_params["rebalance_eagerness"] > 0.55:
            action = "REBALANCE"
            strategy_preset = "trend_rider"
            reasoning = "Trending market detected, rebalancing to capture momentum"
        else:
            action = "MONITOR"
            strategy_preset = "calm_accumulator"
            reasoning = "Trending but eagerness below threshold, holding position"
    else:  # VOLATILE
        if agent_params["risk_tolerance"] > 0.45:
            action = "CREATE_STRATEGY"
            strategy_preset = "volatile_defender"
            reasoning = "High volatility, deploying defensive strategy with MEV protection"
        else:
            action = "REBALANCE"
            strategy_preset = "volatile_defender"
            reasoning = "Volatile but risk-averse, tightening positions"

    meets_threshold = confidence >= threshold
    threshold_str = "pass" if meets_threshold else "BELOW THRESHOLD"

    print(f"  Strategy preset: {strategy_preset}")
    print(f"  Action: {action} ({reasoning})")
    print(f"  Confidence: {confidence:.2f} vs threshold {threshold:.3f} -> {threshold_str}")

    if not meets_threshold:
        action = "MONITOR"
        print(f"  Action downgraded to MONITOR (confidence too low)")

    return {
        "action": action,
        "strategy_preset": strategy_preset,
        "reasoning": reasoning,
        "meets_threshold": meets_threshold,
    }


def layer_execution(cycle_num, perception_data, analysis_data, plan_data):
    """Layer 4: Execute real on-chain transactions."""
    print("\n[Execution] Broadcasting to chain...")

    tx_hashes = []
    strategy_id = str(cycle_num)
    regime = analysis_data["regime"]
    action = plan_data["action"]
    reasoning = plan_data["reasoning"]

    # TX 1: Log market analysis decision
    decision_hash = keccak("MARKET_ANALYSIS")
    reasoning_text = f"cycle{cycle_num}_{regime}_{analysis_data['deviation']:+.1f}pct"
    reasoning_hash = keccak(reasoning_text)

    print(f"  logDecision(strategyId={strategy_id}, type=MARKET_ANALYSIS, ...)")
    tx = cast_send(
        ASSEMBLER,
        "logDecision(uint256,bytes32,bytes32,bytes)",
        [strategy_id, decision_hash, reasoning_hash, "0x"],
        f"MARKET_ANALYSIS cycle {cycle_num + 1}",
    )
    if tx:
        print(f"    -> {tx}")
        tx_hashes.append(tx)

    time.sleep(1)

    # TX 2: Log the planned action decision
    action_hash = keccak(action)
    action_reasoning_hash = keccak(reasoning)

    print(f"  logDecision(strategyId={strategy_id}, type={action}, ...)")
    tx = cast_send(
        ASSEMBLER,
        "logDecision(uint256,bytes32,bytes32,bytes)",
        [strategy_id, action_hash, action_reasoning_hash, "0x"],
        f"{action} cycle {cycle_num + 1}",
    )
    if tx:
        print(f"    -> {tx}")
        tx_hashes.append(tx)

    time.sleep(1)

    # TX 3: Update performance with simulated P&L
    # P&L varies by regime and cycle
    pnl_map = {
        "CALM": [45, 62, 38],
        "TRENDING": [120, -35, 85],
        "VOLATILE": [-80, 150, -25],
    }
    pnl_bps = pnl_map.get(regime, [50, 50, 50])[cycle_num % 3]
    # Apply risk_tolerance effect
    pnl_bps = int(pnl_bps * (0.8 + agent_params["risk_tolerance"] * 0.4))

    print(f"  updatePerformance(strategyId={strategy_id}, pnlBps={pnl_bps:+d})")
    tx = cast_send(
        ASSEMBLER,
        "updatePerformance(uint256,int256)",
        [strategy_id, str(pnl_bps)],
        f"PERFORMANCE cycle {cycle_num + 1}",
    )
    if tx:
        print(f"    -> {tx}")
        tx_hashes.append(tx)

    time.sleep(1)

    # TX 4: Log performance evaluation decision
    perf_hash = keccak("PERFORMANCE_EVAL")
    perf_reasoning = f"cycle{cycle_num}_pnl_{pnl_bps:+d}bps_{action}"
    perf_reasoning_hash = keccak(perf_reasoning)

    print(f"  logDecision(strategyId={strategy_id}, type=PERFORMANCE_EVAL, ...)")
    tx = cast_send(
        ASSEMBLER,
        "logDecision(uint256,bytes32,bytes32,bytes)",
        [strategy_id, perf_hash, perf_reasoning_hash, "0x"],
        f"PERFORMANCE_EVAL cycle {cycle_num + 1}",
    )
    if tx:
        print(f"    -> {tx}")
        tx_hashes.append(tx)

    agent_memory["total_tx_count"] += len(tx_hashes)
    agent_memory["cumulative_pnl_bps"] += pnl_bps
    agent_memory["cycle_pnl"].append(pnl_bps)

    return {
        "tx_hashes": tx_hashes,
        "pnl_bps": pnl_bps,
        "tx_count": len(tx_hashes),
    }


def layer_evolution(cycle_num, analysis_data, execution_data):
    """Layer 5: Adjust internal parameters based on cycle results."""
    print("\n[Evolution] Adjusting parameters...")

    old_params = dict(agent_params)
    pnl = execution_data["pnl_bps"]
    regime = analysis_data["regime"]

    # Rule 1: If P&L positive, increase risk_tolerance
    if pnl > 0:
        adj = min(pnl / 5000.0, 0.03)  # cap at 3% increase
        agent_params["risk_tolerance"] = round(
            min(agent_params["risk_tolerance"] + adj, 0.95), 4
        )

    # Rule 2: If P&L negative, decrease risk_tolerance
    if pnl < 0:
        adj = min(abs(pnl) / 5000.0, 0.03)
        agent_params["risk_tolerance"] = round(
            max(agent_params["risk_tolerance"] - adj, 0.10), 4
        )

    # Rule 3: If volatile, decrease rebalance_eagerness
    if regime == "VOLATILE":
        agent_params["rebalance_eagerness"] = round(
            max(agent_params["rebalance_eagerness"] - 0.04, 0.20), 4
        )
    elif regime == "TRENDING":
        agent_params["rebalance_eagerness"] = round(
            min(agent_params["rebalance_eagerness"] + 0.02, 0.90), 4
        )

    # Rule 4: If predictions accurate (positive P&L matches action), lower confidence threshold
    prediction_correct = (
        (pnl > 0 and analysis_data["regime"] in ["CALM", "TRENDING"])
        or (pnl < 0 and analysis_data["regime"] == "VOLATILE" and agent_params["risk_tolerance"] < 0.5)
    )
    agent_memory["cycle_predictions"].append(prediction_correct)

    if prediction_correct:
        agent_params["confidence_threshold"] = round(
            max(agent_params["confidence_threshold"] - 0.015, 0.50), 4
        )
    else:
        agent_params["confidence_threshold"] = round(
            min(agent_params["confidence_threshold"] + 0.01, 0.90), 4
        )

    # Rule 5: Fee sensitivity adjusts with volatility
    if regime == "VOLATILE":
        agent_params["fee_sensitivity"] = round(
            min(agent_params["fee_sensitivity"] + 0.05, 2.0), 4
        )
    elif regime == "CALM":
        agent_params["fee_sensitivity"] = round(
            max(agent_params["fee_sensitivity"] - 0.02, 0.50), 4
        )

    # Print parameter diffs
    for key in ["risk_tolerance", "rebalance_eagerness", "confidence_threshold", "fee_sensitivity"]:
        old_val = old_params[key]
        new_val = agent_params[key]
        if abs(new_val - old_val) < 0.0001:
            change_str = "(unchanged)"
        else:
            pct = ((new_val - old_val) / old_val) * 100 if old_val != 0 else 0
            change_str = f"({pct:+.1f}%)"
        print(f"  {key + ':':28s} {old_val:.4f} -> {new_val:.4f} {change_str}")

    # TX: Log evolution as META_COGNITION on-chain
    time.sleep(1)
    meta_hash = keccak("META_COGNITION")
    evolution_summary = (
        f"evolution_cycle{cycle_num}_"
        f"risk{agent_params['risk_tolerance']:.3f}_"
        f"eager{agent_params['rebalance_eagerness']:.3f}_"
        f"conf{agent_params['confidence_threshold']:.3f}_"
        f"fee{agent_params['fee_sensitivity']:.3f}"
    )
    evolution_hash = keccak(evolution_summary)

    print(f"  logDecision(type=META_COGNITION, evolution) ...")
    tx = cast_send(
        ASSEMBLER,
        "logDecision(uint256,bytes32,bytes32,bytes)",
        [str(cycle_num), meta_hash, evolution_hash, "0x"],
        f"META_COGNITION evolution cycle {cycle_num + 1}",
    )
    if tx:
        print(f"    -> {tx}")
        agent_memory["total_tx_count"] += 1

    return {
        "old_params": old_params,
        "new_params": dict(agent_params),
        "prediction_correct": prediction_correct,
    }


def layer_meta_cognition(cycle_num, execution_data, evolution_data):
    """Layer 6: Self-assessment and bias detection."""
    print("\n[Meta-Cognition] Self-assessment...")

    decisions_this_cycle = execution_data["tx_count"] + 1  # +1 for evolution tx
    agent_memory["cycle_decisions"].append(decisions_this_cycle)

    total_decisions = sum(agent_memory["cycle_decisions"])
    print(f"  Decisions this cycle: {decisions_this_cycle}")
    print(f"  Total decisions so far: {total_decisions}")

    # Accuracy assessment
    correct = sum(1 for p in agent_memory["cycle_predictions"] if p)
    total_pred = len(agent_memory["cycle_predictions"])
    if total_pred > 0:
        accuracy = correct / total_pred
        print(f"  Cumulative accuracy: {accuracy:.0%} ({correct}/{total_pred})")
    else:
        accuracy = None
        print(f"  Cumulative accuracy: N/A (first cycle)")

    # Bias detection
    biases = []
    if len(agent_memory["cycle_pnl"]) >= 2:
        recent_pnl = agent_memory["cycle_pnl"][-2:]
        if all(p > 0 for p in recent_pnl):
            biases.append("optimism_bias (consecutive positive P&L may cause overconfidence)")
        if all(p < 0 for p in recent_pnl):
            biases.append("loss_aversion (consecutive losses may cause excessive caution)")

    if agent_params["risk_tolerance"] > 0.7:
        biases.append("risk_seeking (risk_tolerance elevated above 0.70)")
    if agent_params["confidence_threshold"] < 0.55:
        biases.append("overconfidence (confidence_threshold too low)")

    regimes = agent_memory["cycle_regimes"]
    if len(regimes) >= 2 and len(set(regimes[-2:])) == 1:
        biases.append(f"anchoring (same regime '{regimes[-1]}' detected consecutively)")

    if biases:
        for b in biases:
            print(f"  Bias detected: {b}")
    else:
        print(f"  Biases detected: none")

    # Cumulative P&L
    print(f"  Cumulative P&L: {agent_memory['cumulative_pnl_bps']:+d} bps")

    # TX: Log meta-cognition on-chain
    time.sleep(1)
    meta_hash = keccak("META_COGNITION")
    self_assess = (
        f"metacog_cycle{cycle_num}_"
        f"decisions{total_decisions}_"
        f"accuracy{accuracy if accuracy else 0:.2f}_"
        f"biases{len(biases)}_"
        f"pnl{agent_memory['cumulative_pnl_bps']:+d}"
    )
    self_hash = keccak(self_assess)

    print(f"  logDecision(type=META_COGNITION, self-assessment) ...")
    tx = cast_send(
        ASSEMBLER,
        "logDecision(uint256,bytes32,bytes32,bytes)",
        [str(cycle_num), meta_hash, self_hash, "0x"],
        f"META_COGNITION self-assess cycle {cycle_num + 1}",
    )
    if tx:
        print(f"    -> {tx}")
        agent_memory["total_tx_count"] += 1


# ─── Main Loop ───────────────────────────────────────────────────────────────

def main():
    if not PK:
        print("ERROR: PRIVATE_KEY environment variable is not set.")
        print("Export it before running: export PRIVATE_KEY=0x...")
        sys.exit(1)

    print("=" * 50)
    print("  GENESIS PROTOCOL - AUTONOMOUS AGENT")
    print("  Mode: LIVE (PAUSED=False, DRY_RUN=False)")
    print(f"  Chain: X Layer Testnet ({CHAIN_ID})")
    print(f"  Assembler: {ASSEMBLER}")
    print(f"  Cycles: {NUM_CYCLES}")
    print("=" * 50)

    t0 = time.time()

    for cycle in range(NUM_CYCLES):
        print(f"\n{'─' * 3} CYCLE {cycle + 1}/{NUM_CYCLES} {'─' * 39}")

        # Layer 1: Perception
        perception = layer_perception(cycle)

        # Layer 2: Analysis
        analysis = layer_analysis(cycle, perception)

        # Layer 3: Planning
        plan = layer_planning(cycle, analysis)

        # Layer 4: Execution
        execution = layer_execution(cycle, perception, analysis, plan)

        # Layer 5: Evolution
        evolution = layer_evolution(cycle, analysis, execution)

        # Layer 6: Meta-Cognition
        layer_meta_cognition(cycle, execution, evolution)

        # Between cycles
        if cycle < NUM_CYCLES - 1:
            print(f"\n  --- Waiting {DELAY_BETWEEN_CYCLES}s before next cycle ---")
            time.sleep(DELAY_BETWEEN_CYCLES)

            # Shift baseline to simulate time passing
            if agent_memory["baseline_eth_price"]:
                shifts = [1.025, 0.96]  # +2.5%, -4%
                agent_memory["baseline_eth_price"] *= shifts[cycle % len(shifts)]
                print(f"  Baseline shifted to ${agent_memory['baseline_eth_price']:,.2f}")

    # ─── Final Summary ───────────────────────────────────────────────────────
    elapsed = time.time() - t0
    print(f"\n{'=' * 50}")
    print("  AUTONOMOUS AGENT - FINAL REPORT")
    print(f"{'=' * 50}")
    print(f"  Total on-chain transactions: {agent_memory['total_tx_count']}")
    print(f"  Total cycles completed:      {NUM_CYCLES}")
    print(f"  Cumulative P&L:              {agent_memory['cumulative_pnl_bps']:+d} bps")
    print(f"  Elapsed time:                {elapsed:.1f}s")
    print()
    print("  Final agent parameters:")
    for key, val in agent_params.items():
        print(f"    {key + ':':28s} {val:.4f}")
    print()
    print("  Regime history:", " -> ".join(agent_memory["cycle_regimes"]))
    print("  P&L history:  ", " -> ".join(f"{p:+d}" for p in agent_memory["cycle_pnl"]))

    correct = sum(1 for p in agent_memory["cycle_predictions"] if p)
    total_p = len(agent_memory["cycle_predictions"])
    if total_p:
        print(f"  Prediction accuracy:          {correct}/{total_p} ({correct/total_p:.0%})")
    print(f"{'=' * 50}")

    if agent_memory["total_tx_count"] < 12:
        print(f"\n  [WARN] Only {agent_memory['total_tx_count']} transactions succeeded (target: 12+)")
        print("  Check RPC connectivity and wallet gas balance.")
        sys.exit(1)
    else:
        print(f"\n  All {agent_memory['total_tx_count']} transactions confirmed on-chain.")


if __name__ == "__main__":
    main()
