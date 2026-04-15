#!/usr/bin/env python3
"""
Genesis Protocol - Full Cognitive Cycle Demo

Simulates a complete AI agent lifecycle with realistic market data:
  Perception → Analysis → Planning → Execution → Decision Journal → NFT Mint

This demo uses mock market data to showcase the full pipeline without
requiring onchainos CLI or live RPC connections.
"""

import time
import json
import random
import hashlib
import sys
import subprocess

# ─── ANSI Colors ────────────────────────────────────────────────────────────
C = {
    "cyan": "\033[96m", "purple": "\033[95m", "green": "\033[92m",
    "yellow": "\033[93m", "red": "\033[91m", "bold": "\033[1m",
    "dim": "\033[2m", "reset": "\033[0m", "blue": "\033[94m",
}

def styled(text, *styles):
    return "".join(C[s] for s in styles) + text + C["reset"]

def banner(text, color="cyan"):
    w = 64
    print(f"\n{C[color]}{'═' * w}")
    print(f"  {text}")
    print(f"{'═' * w}{C['reset']}")

def log(layer, msg, color="cyan"):
    ts = time.strftime("%H:%M:%S")
    prefix = styled(f"[{ts}]", "dim") + " " + styled(f"[{layer}]", color, "bold")
    print(f"{prefix} {msg}")

def progress_bar(label, duration=1.0, steps=20):
    sys.stdout.write(f"  {styled(label, 'dim')} [")
    for i in range(steps):
        time.sleep(duration / steps)
        sys.stdout.write(styled("█", "cyan"))
        sys.stdout.flush()
    sys.stdout.write(f"] {styled('Done', 'green')}\n")

# ─── Deterministic Market Data ───────────────────────────────────────────────

def generate_price_walk(seed, start_price, steps=48, drift=0.0002, vol=0.012):
    """
    Generate a realistic price series using geometric Brownian motion with
    mean reversion.  Uses a seeded RNG so results are reproducible across runs
    while still looking like genuine market behavior.

    Args:
        seed:        int seed for reproducibility
        start_price: initial price level
        steps:       number of hourly data points to generate
        drift:       annualized drift per step (slight upward bias)
        vol:         per-step volatility (std dev of log returns)

    Returns:
        list of prices (floats) and realised volatility (float, %).
    """
    rng = random.Random(seed)
    prices = [start_price]
    mean_price = start_price
    reversion_strength = 0.03  # pull toward mean

    for _ in range(steps - 1):
        shock = rng.gauss(0, vol)
        reversion = reversion_strength * (mean_price - prices[-1]) / prices[-1]
        log_return = drift + reversion + shock
        prices.append(prices[-1] * (1 + log_return))

    # Realised volatility as annualised % of hourly log returns
    log_returns = [
        (prices[i] - prices[i - 1]) / prices[i - 1]
        for i in range(1, len(prices))
    ]
    realised_vol = (sum(r ** 2 for r in log_returns) / len(log_returns)) ** 0.5
    annualised_vol_pct = round(realised_vol * (8760 ** 0.5) * 100, 2)  # hourly -> annual

    return prices, annualised_vol_pct


# Pre-generate deterministic series (seed ensures same output every run)
_eth_prices, _eth_vol = generate_price_walk(seed=42, start_price=2450.0, vol=0.014)
_okb_prices, _okb_vol = generate_price_walk(seed=99, start_price=48.5, vol=0.009)

PAIRS = [
    {"base": "ETH", "quote": "USDC", "price": _eth_prices[-1], "vol_24h": _eth_vol,
     "price_series": _eth_prices},
    {"base": "OKB", "quote": "USDT", "price": _okb_prices[-1], "vol_24h": _okb_vol,
     "price_series": _okb_prices},
]

PRESETS = {
    "calm_accumulator": {"vol_range": [0, 300], "trend": "sideways", "modules": ["DynamicFee", "AutoRebalance"]},
    "volatile_defender": {"vol_range": [500, 9999], "trend": "any", "modules": ["DynamicFee", "MEVProtection", "AutoRebalance"]},
    "trend_rider": {"vol_range": [200, 600], "trend": "trending", "modules": ["DynamicFee", "MEVProtection", "AutoRebalance"]},
}

CONTRACTS = {
    "assembler": "0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78",
    "dynamic_fee": "0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed",
    "mev_protection": "0xA4f6ABd6F77928b06F075637ccBACA8f89e17386",
    "auto_rebalance": "0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee",
    "strategy_nft": "0xd969448dfc24Fe3Aff25e86db338fAB41b104319",
}

# ─── Live Chain Data ─────────────────────────────────────────────────────────
XLAYER_RPC = "https://testrpc.xlayer.tech"

def read_chain_data():
    """Read real on-chain state from X Layer Testnet via cast call."""
    chain_data = {
        "strategy_count": None,
        "decision_count": None,
        "nft_supply": None,
        "total_swaps": None,
    }

    calls = {
        "strategy_count": {
            "to": CONTRACTS["assembler"],
            "sig": "strategyCount()(uint256)",
        },
        "decision_count": {
            "to": CONTRACTS["assembler"],
            "sig": "decisionCount()(uint256)",
        },
        "nft_supply": {
            "to": CONTRACTS["strategy_nft"],
            "sig": "totalSupply()(uint256)",
        },
        "total_swaps": {
            "to": CONTRACTS["assembler"],
            "sig": "totalSwapsProcessed()(uint256)",
        },
    }

    for key, call in calls.items():
        try:
            proc = subprocess.run(
                ["cast", "call", call["to"], call["sig"],
                 "--rpc-url", XLAYER_RPC],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                val = proc.stdout.strip()
                # cast may return hex or decimal
                if val.startswith("0x"):
                    chain_data[key] = int(val, 16)
                else:
                    chain_data[key] = int(val)
        except Exception:
            pass  # Fallback to None, demo will use defaults

    return chain_data

# ─── Decision Journal ───────────────────────────────────────────────────────
journal = []

def log_decision(strategy_id, dtype, reasoning, confidence):
    entry = {
        "id": len(journal),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "strategy_id": strategy_id,
        "type": dtype,
        "reasoning": reasoning,
        "reasoning_hash": "0x" + hashlib.sha256(reasoning.encode()).hexdigest()[:16],
        "confidence": confidence,
        "on_chain": "confirmed",
    }
    journal.append(entry)
    return entry

# ─── Layer 1: Perception ────────────────────────────────────────────────────
def perceive():
    banner("LAYER 1: PERCEPTION", "cyan")
    log("Perception", "Fetching market data via OnchainOS Market...")
    progress_bar("onchainos market price", 0.8)

    world = {"prices": {}, "volatility": {}, "wallets": {}, "price_series": {}}

    for pair in PAIRS:
        price = pair["price"]
        vol = pair["vol_24h"]
        world["prices"][f"{pair['base']}/{pair['quote']}"] = round(price, 2)
        world["volatility"][f"{pair['base']}/{pair['quote']}"] = round(vol, 2)
        world["price_series"][f"{pair['base']}/{pair['quote']}"] = pair.get("price_series", [price])
        log("Perception", f"  {pair['base']}/{pair['quote']}: ${price:,.2f}  vol={vol:.2f}%")

    log("Perception", "Querying wallet balances...")
    progress_bar("onchainos wallet balance", 0.5)
    wallets = {"master": "0.15 OKB", "strategy": "1,200 USDT", "income": "45.2 USDT", "reserve": "500 USDT", "rebalance": "200 USDT"}
    for role, bal in wallets.items():
        world["wallets"][role] = bal
        log("Perception", f"  [{role:10s}] {bal}")

    log("Perception", "Checking active strategies on-chain...")
    progress_bar("cast call strategyCount", 0.3)

    # Read live chain state
    chain = read_chain_data()
    sc = chain["strategy_count"] if chain["strategy_count"] is not None else 1
    sw = chain["total_swaps"] if chain["total_swaps"] is not None else 128
    src = styled("live", "green") if chain["strategy_count"] is not None else styled("cached", "yellow")
    log("Perception", f"  Active strategies: {styled(str(sc), 'green')} ({src})")
    log("Perception", f"  Total swaps processed: {styled(str(sw), 'cyan')}")
    log("Perception", f"  Total volume: {styled('42.3 ETH', 'cyan')}")

    return world

# ─── Layer 2: Analysis ──────────────────────────────────────────────────────
def analyze(world):
    banner("LAYER 2: ANALYSIS", "blue")
    log("Analysis", "Computing market regime...", "blue")
    progress_bar("Volatility calculation (24h window)", 0.6)

    # Use seeded RNG for reproducible analysis results
    analysis_rng = random.Random(7)
    analysis = {"regimes": {}, "anomalies": [], "opportunities": []}

    for pair_name, vol in world["volatility"].items():
        if vol < 3.0:
            regime = "calm_accumulator"
            trend = "sideways"
            conf = round(0.75 + analysis_rng.uniform(0, 0.15), 2)
        elif vol > 5.0:
            regime = "volatile_defender"
            trend = "volatile"
            conf = round(0.80 + analysis_rng.uniform(0, 0.15), 2)
        else:
            regime = "trend_rider"
            trend = "trending"
            conf = round(0.70 + analysis_rng.uniform(0, 0.15), 2)

        analysis["regimes"][pair_name] = {"regime": regime, "trend": trend, "confidence": conf, "volatility": vol}
        color = "green" if regime == "calm_accumulator" else ("red" if regime == "volatile_defender" else "yellow")
        log("Analysis", f"  {pair_name}: {styled(regime, color)} (vol={vol:.1f}%, trend={trend}, conf={conf})", "blue")

    # Anomaly detection
    for pair_name, vol in world["volatility"].items():
        if vol > 4.5:
            analysis["anomalies"].append({"pair": pair_name, "type": "vol_spike", "severity": "medium"})
            log("Analysis", styled(f"  ⚠ Anomaly: {pair_name} volatility spike ({vol:.1f}%)", "yellow"), "blue")

    if not analysis["anomalies"]:
        log("Analysis", styled("  ✓ No anomalies detected", "green"), "blue")

    return analysis

# ─── Layer 3: Planning ──────────────────────────────────────────────────────
def plan(analysis):
    banner("LAYER 3: PLANNING", "purple")
    log("Planning", "Generating action plan...", "purple")

    actions = []
    for pair_name, regime_data in analysis["regimes"].items():
        regime = regime_data["regime"]
        conf = regime_data["confidence"]

        if conf < 0.7:
            log("Planning", styled(f"  ✗ {pair_name}: confidence {conf} < 0.7, skipping", "dim"), "purple")
            continue

        preset = PRESETS[regime]
        fee_range = "0.05%-0.30%" if regime == "calm_accumulator" else ("0.10%-1.50%" if regime == "volatile_defender" else "0.05%-0.50%")

        action = {
            "type": "adjust_strategy",
            "pair": pair_name,
            "preset": regime,
            "modules": preset["modules"],
            "fee_range": fee_range,
            "confidence": conf,
        }
        actions.append(action)

        log("Planning", f"  {pair_name}:", "purple")
        log("Planning", f"    Preset:     {styled(regime, 'cyan')}", "purple")
        log("Planning", f"    Modules:    {', '.join(preset['modules'])}", "purple")
        log("Planning", f"    Fee range:  {fee_range}", "purple")
        log("Planning", f"    Confidence: {styled(str(conf), 'green')}", "purple")

    # Position sizing
    log("Planning", f"\n  Position sizing: max {styled('30%', 'yellow')} of wallet per strategy", "purple")
    log("Planning", f"  Estimated deployment cost: {styled('~$0.003', 'green')} (6 txns × $0.0005)", "purple")

    return actions

# ─── Layer 4: Execution ─────────────────────────────────────────────────────
def execute(actions):
    banner("EXECUTION ENGINE", "green")
    log("Executor", "Dispatching actions to X Layer (Chain 1952)...", "green")
    print()

    for i, action in enumerate(actions):
        log("Executor", f"Action {i+1}: {styled(action['type'], 'cyan')} for {action['pair']}", "green")

        # Simulate module parameter updates
        for mod in action["modules"]:
            progress_bar(f"  updateParams → {mod}", 0.4)

        # Log decision
        reasoning = f"Market regime: {action['preset']}. Confidence: {action['confidence']}. Modules: {', '.join(action['modules'])}. Fee range: {action['fee_range']}."
        entry = log_decision(0, "FEE_ADJUST", reasoning, action["confidence"])
        log("Executor", f"  Decision #{entry['id']} logged → {styled(entry['reasoning_hash'], 'dim')}", "green")
        log("Executor", styled(f"  ✓ On-chain: confirmed (assembler: {CONTRACTS['assembler'][:10]}...)", "green"), "green")
        print()

    return True

# ─── Layer 4: Evolution ─────────────────────────────────────────────────────
def evolve():
    banner("LAYER 4: EVOLUTION", "yellow")
    log("Evolution", "Reviewing historical performance (24h lookback)...", "yellow")
    progress_bar("Loading decision journal", 0.5)

    evolve_rng = random.Random(13)
    metrics = {
        "prediction_accuracy": round(0.72 + evolve_rng.uniform(0, 0.1), 2),
        "avg_pnl_bps": 150,
        "total_strategies_evaluated": 3,
        "rebalance_count": 4,
    }

    log("Evolution", f"  Prediction accuracy:  {styled(str(metrics['prediction_accuracy']), 'green')}", "yellow")
    log("Evolution", f"  Average P&L:          {styled('+' + str(metrics['avg_pnl_bps']) + ' bps', 'green')}", "yellow")
    log("Evolution", f"  Strategies evaluated:  {metrics['total_strategies_evaluated']}", "yellow")
    log("Evolution", f"  Rebalances executed:   {metrics['rebalance_count']}", "yellow")

    # Adjust parameters
    log("Evolution", "\n  Adjusting internal parameters:", "yellow")
    log("Evolution", f"    risk_tolerance:      0.5 → {styled('0.48', 'cyan')} (-4%)", "yellow")
    log("Evolution", f"    rebalance_eagerness: 0.6 → {styled('0.63', 'cyan')} (+5%)", "yellow")
    log("Evolution", f"    confidence_threshold: 0.70 → {styled('0.72', 'cyan')} (+3%)", "yellow")

    log_decision(0, "META_COGNITION", f"Evolution cycle complete. Accuracy: {metrics['prediction_accuracy']}. Adjusted risk_tolerance, rebalance_eagerness.", 0.95)
    return metrics

# ─── Layer 5: Meta-Cognition ────────────────────────────────────────────────
def reflect():
    banner("LAYER 5: META-COGNITION", "purple")
    log("MetaCog", "Self-assessment of decision-making quality...", "purple")
    progress_bar("Analyzing decision journal", 0.6)

    log("MetaCog", "  Decision quality analysis:", "purple")
    log("MetaCog", f"    Total decisions:     {styled(str(len(journal)), 'cyan')}", "purple")
    log("MetaCog", f"    On-chain confirmed:  {styled(str(len(journal)), 'green')}", "purple")
    log("MetaCog", f"    Avg confidence:      {styled('0.84', 'green')}", "purple")
    log("MetaCog", f"    Decision latency:    {styled('1.2s', 'green')} (signal → execution)", "purple")

    log("MetaCog", "\n  Bias detection:", "purple")
    log("MetaCog", styled("    ✓ No systematic over-trading detected", "green"), "purple")
    log("MetaCog", styled("    ⚠ Slight delay in vol-spike response (avg 45s)", "yellow"), "purple")
    log("MetaCog", styled("    ✓ Wallet allocation efficient (no idle funds >5%)", "green"), "purple")

    log("MetaCog", f"\n  Recommendation: {styled('Reduce perception interval to 45s for faster vol response', 'cyan')}", "purple")

    log_decision(0, "META_COGNITION", "Self-assessment complete. Identified vol-response delay. Recommending perception interval reduction.", 0.92)

# ─── NFT Eligibility Check ──────────────────────────────────────────────────
def check_nft():
    banner("STRATEGY NFT CHECK", "yellow")
    log("NFT", "Checking mint eligibility for Strategy #0...", "yellow")

    checks = [
        ("P&L ≥ +1.00% (100 bps)", 150, 100, True),
        ("Swaps ≥ 50", 128, 50, True),
        ("Runtime ≥ 48h", 72, 48, True),
    ]

    all_pass = True
    for label, actual, threshold, passed in checks:
        status = styled("✓ PASS", "green") if passed else styled("✗ FAIL", "red")
        log("NFT", f"  {status}  {label}  (actual: {actual})", "yellow")
        if not passed:
            all_pass = False

    if all_pass:
        log("NFT", styled("\n  ★ All thresholds met! Minting Strategy NFT...", "green", "bold"), "yellow")
        progress_bar("StrategyNFT.mint()", 0.8)
        log("NFT", f"  Token ID:   {styled('0', 'cyan')}", "yellow")
        log("NFT", f"  Contract:   {styled(CONTRACTS['strategy_nft'], 'dim')}", "yellow")
        log("NFT", f"  Metadata:   on-chain (modules, params, P&L, market state)", "yellow")
        log("NFT", styled(f"  ✓ NFT minted successfully!", "green", "bold"), "yellow")

        log_decision(0, "NFT_MINT", "Strategy #0 met all thresholds. Minted NFT #0 with full on-chain metadata.", 0.99)

# ─── Main ───────────────────────────────────────────────────────────────────
def main():
    print(styled("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║   ██████╗ ███████╗███╗   ██╗███████╗███████╗██╗███████╗  ║
    ║  ██╔════╝ ██╔════╝████╗  ██║██╔════╝██╔════╝██║██╔════╝  ║
    ║  ██║  ███╗█████╗  ██╔██╗ ██║█████╗  ███████╗██║███████╗  ║
    ║  ██║   ██║██╔══╝  ██║╚██╗██║██╔══╝  ╚════██║██║╚════██║  ║
    ║  ╚██████╔╝███████╗██║ ╚████║███████╗███████║██║███████║  ║
    ║   ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚══════╝╚══════╝╚═╝╚══════╝  ║
    ║                                                           ║
    ║   AI-Powered Uniswap V4 Hook Strategy Engine              ║
    ║   X Layer (Chain 1952) · OKX Build X Hackathon 2026       ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """, "cyan"))

    # Fetch live chain data
    print(styled("  Connecting to X Layer Testnet (Chain 1952)...", "dim"))
    chain = read_chain_data()
    has_live = any(v is not None for v in chain.values())

    if has_live:
        print(styled("  ✓ Live chain data loaded from testrpc.xlayer.tech", "green"))
    else:
        print(styled("  ⚠ Chain RPC unavailable — using cached data", "yellow"))

    # Use live data with fallbacks
    strategy_count = chain["strategy_count"] if chain["strategy_count"] is not None else 1
    decision_count = chain["decision_count"] if chain["decision_count"] is not None else 5
    nft_supply = chain["nft_supply"] if chain["nft_supply"] is not None else 1
    total_swaps = chain["total_swaps"] if chain["total_swaps"] is not None else 2

    print(styled("\n  Configuration:", "bold"))
    print(f"    Chain:      X Layer Testnet (1952)")
    print(f"    Mode:       {styled('DEMO (simulated + live chain state)', 'yellow')}")
    print(f"    Assembler:  {styled(CONTRACTS['assembler'], 'dim')}")
    print(f"    Modules:    3 registered (DynamicFee, MEVProtection, AutoRebalance)")
    data_source = styled("LIVE", "green") if has_live else styled("CACHED", "yellow")
    print(f"    Data:       {data_source}")
    print(f"    Strategies: {styled(str(strategy_count), 'cyan')} on-chain")
    print(f"    Decisions:  {styled(str(decision_count), 'cyan')} journal entries")
    print(f"    NFTs:       {styled(str(nft_supply), 'cyan')} minted")
    print(f"    Swaps:      {styled(str(total_swaps), 'cyan')} processed")
    time.sleep(0.5)

    # Run full cognitive cycle
    world = perceive()
    time.sleep(0.3)

    analysis = analyze(world)
    time.sleep(0.3)

    actions = plan(analysis)
    time.sleep(0.3)

    execute(actions)
    time.sleep(0.3)

    evolve()
    time.sleep(0.3)

    reflect()
    time.sleep(0.3)

    check_nft()

    # Summary
    banner("CYCLE COMPLETE", "green")
    log("Engine", f"Decisions logged:    {styled(str(len(journal)), 'cyan')}", "green")
    log("Engine", f"On-chain confirmed:  {styled(str(len(journal)), 'green')}", "green")
    log("Engine", f"Actions executed:     {styled(str(len(actions)), 'cyan')}", "green")
    log("Engine", f"NFTs minted:         {styled('1', 'green')}", "green")

    print(f"\n{styled('  Decision Journal:', 'bold')}")
    for entry in journal:
        print(f"    #{entry['id']}  {styled(entry['type'], 'cyan'):30s}  conf={entry['confidence']}  {styled(entry['reasoning_hash'], 'dim')}")

    print(f"\n{styled('  Next cycle in 60 seconds...', 'dim')}")
    print(f"{styled('  Press Ctrl+C to stop the engine.', 'dim')}\n")

if __name__ == "__main__":
    main()
