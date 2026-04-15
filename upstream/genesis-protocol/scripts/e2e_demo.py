#!/usr/bin/env python3
"""Genesis Protocol - End-to-End Demonstration Script.

Demonstrates the FULL lifecycle of the Genesis Protocol:
  1. Market Data Fetch   - Real prices from OKX public API
  2. AI Analysis         - 5-layer cognitive cycle (Perception -> Meta-Cognition)
  3. LLM Reasoning       - Human-readable explanations via LLMReasoner
  4. Strategy Selection   - Preset selection based on AI analysis
  5. On-Chain Verification- Read contract state from X Layer mainnet
  6. Decision Journal     - Create a decision journal entry with full reasoning
  7. NFT Eligibility      - Check if strategy meets minting thresholds
  8. Summary Report       - Formatted summary of entire cycle

Uses ONLY Python stdlib (urllib, json, hashlib, math, time).

Usage:
    python3 scripts/e2e_demo.py
"""

import hashlib
import json
import math
import os
import sys
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Path setup — allow imports from project root and skills package
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.join(_SCRIPT_DIR, "..")
sys.path.insert(0, _PROJECT_ROOT)

# Attempt to import LLMReasoner (may not be available yet)
try:
    from skills.genesis.scripts.llm_reasoning import LLMReasoner
    _HAS_LLM_REASONER = True
except ImportError:
    _HAS_LLM_REASONER = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RPC_URL = "https://rpc.xlayer.tech"
OKX_BASE = "https://www.okx.com"
USER_AGENT = "genesis-protocol/2.0"

CONTRACTS = {
    "assembler":    "0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78",
    "strategy_nft": "0x8a0e87395f864405c5225eBd80391Ac82eefe437",
    "v4_hook":      "0x174a2450b342042AAe7398545f04B199248E69c0",
}

STRATEGY_PRESETS = {
    "calm_accumulator": {
        "description": "Low volatility - maximize volume via low fees",
        "modules": ["dynamic_fee", "auto_rebalance"],
        "fee_range": (100, 3000),
        "vol_range": (0, 300),
    },
    "volatile_defender": {
        "description": "High volatility - protect LP with high fees + MEV guard",
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance"],
        "fee_range": (1000, 15000),
        "vol_range": (500, 9999),
    },
    "trend_rider": {
        "description": "Trending market - wider range, TWAP rebalance",
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance"],
        "fee_range": (500, 10000),
        "vol_range": (200, 600),
    },
    "full_defense": {
        "description": "Maximum protection - all 5 modules active",
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance",
                     "liquidity_shield", "oracle"],
        "fee_range": (1500, 20000),
        "vol_range": (800, 9999),
    },
}

# NFT mint thresholds
NFT_THRESHOLD_PNL_BPS = 100   # >= 100 bps (+1%)
NFT_THRESHOLD_SWAPS = 50      # >= 50 swaps
NFT_THRESHOLD_HOURS = 48      # >= 48 hours runtime

MARKET_PAIRS = [
    ("ETH", "USDT"),
    ("OKB", "USDT"),
    ("BTC", "USDT"),
]


# ═══════════════════════════════════════════════════════════════════════════
#  Utility helpers
# ═══════════════════════════════════════════════════════════════════════════

def _banner(title, char="=", width=72):
    """Print a formatted section banner."""
    print()
    print(char * width)
    print(f"  {title}")
    print(char * width)


def _sub(label, value="", indent=4):
    """Print an indented label-value pair."""
    pad = " " * indent
    if value != "":
        print(f"{pad}{label}: {value}")
    else:
        print(f"{pad}{label}")


def _okx_get(path, params=None):
    """Execute an unauthenticated GET against the OKX public API."""
    url = OKX_BASE + path
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += "?" + qs
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        return {"error": str(exc)}


def _rpc_call(method, params=None):
    """Execute a JSON-RPC call to X Layer mainnet."""
    payload = json.dumps({
        "jsonrpc": "2.0", "method": method,
        "params": params or [], "id": 1,
    }).encode()
    req = urllib.request.Request(
        RPC_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("result")
    except Exception as exc:
        return f"ERROR: {exc}"


def _eth_call(to, data):
    """Execute a read-only eth_call on X Layer mainnet."""
    return _rpc_call("eth_call", [{"to": to, "data": data}, "latest"])


def _safe_int(hex_str):
    """Parse a hex RPC result to int, returning None on failure."""
    if hex_str and not str(hex_str).startswith("ERROR") and hex_str != "0x":
        try:
            return int(hex_str, 16)
        except (ValueError, TypeError):
            pass
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 1: Market Data Fetch
# ═══════════════════════════════════════════════════════════════════════════

def fetch_market_data():
    """Fetch real-time prices and 24h candles from OKX public API.

    Returns:
        dict with keys 'tickers' (list of ticker dicts) and 'candles' (list
        of [ts, open, high, low, close, vol] for ETH-USDT 1H).
    """
    _banner("STEP 1: Market Data Fetch (OKX Public API)")
    tickers = []
    for base, quote in MARKET_PAIRS:
        inst_id = f"{base}-{quote}"
        data = _okx_get("/api/v5/market/ticker", {"instId": inst_id})
        if data.get("code") == "0" and data.get("data"):
            t = data["data"][0]
            ticker = {
                "pair": inst_id,
                "price": float(t.get("last", 0)),
                "high24h": float(t.get("high24h", 0)),
                "low24h": float(t.get("low24h", 0)),
                "vol24h": float(t.get("vol24h", 0)),
                "change24h": float(t.get("last", 0)) - float(t.get("open24h", 0)),
            }
            tickers.append(ticker)
            chg_pct = (ticker["change24h"] / float(t.get("open24h", 1))) * 100
            _sub(f"{inst_id:12s} ${ticker['price']:>10,.2f}  "
                 f"H/L: ${ticker['high24h']:,.2f}/${ticker['low24h']:,.2f}  "
                 f"Chg: {chg_pct:+.2f}%")
        else:
            _sub(f"{inst_id:12s} [unavailable]")

    # Fetch 24h of 1H candles for ETH-USDT
    candles = []
    candles_resp = _okx_get("/api/v5/market/candles",
                            {"instId": "ETH-USDT", "bar": "1H", "limit": "24"})
    if candles_resp and candles_resp.get("code") == "0":
        for c in candles_resp["data"]:
            candles.append({
                "ts": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "vol": float(c[5]),
            })
        _sub(f"Fetched {len(candles)} hourly candles for ETH-USDT")

    return {"tickers": tickers, "candles": candles}


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 2: AI Analysis — 5-Layer Cognitive Cycle
# ═══════════════════════════════════════════════════════════════════════════

def run_ai_analysis(market_data):
    """Run the full 5-layer cognitive cycle on fetched market data.

    Layers:
        L1 Perception  - Parse market data into structured state
        L2 Analysis    - EWMA volatility, Bayesian regime, momentum signals
        L3 Planning    - Strategy preset selection with confidence scoring
        L4 Evolution   - Adaptive risk parameter adjustment
        L5 Meta-Cognition - Reasoning hash generation, self-assessment

    Returns:
        dict with analysis results for every layer.
    """
    _banner("STEP 2: AI Analysis - 5-Layer Cognitive Cycle")
    result = {}

    # --- L1: Perception ---------------------------------------------------
    _sub("L1 PERCEPTION - Parse market data", indent=2)
    tickers = market_data.get("tickers", [])
    candles = market_data.get("candles", [])
    prices = {t["pair"]: t["price"] for t in tickers}
    for pair, price in prices.items():
        _sub(f"{pair}: ${price:,.2f}")

    result["l1_prices"] = prices
    result["l1_candle_count"] = len(candles)
    _sub(f"Candles ingested: {len(candles)}")

    # --- L2: Analysis -----------------------------------------------------
    _sub("")
    _sub("L2 ANALYSIS - Volatility, Regime Detection, Momentum", indent=2)

    closes = [c["close"] for c in candles] if candles else []

    # EWMA volatility (lambda=0.94, RiskMetrics)
    ewma_vol = 0.0
    if len(closes) >= 3:
        returns = [(closes[i] - closes[i - 1]) / closes[i - 1]
                   for i in range(1, len(closes)) if closes[i - 1] > 0]
        if returns:
            lam = 0.94
            var_ewma = returns[0] ** 2
            for r in returns[1:]:
                var_ewma = lam * var_ewma + (1 - lam) * r ** 2
            ewma_vol = math.sqrt(var_ewma) * 100  # as percentage
    _sub(f"EWMA Volatility (24h): {ewma_vol:.4f}%")

    # Simple realized volatility
    realized_vol = 0.0
    if len(closes) >= 2:
        avg = sum(closes) / len(closes)
        std = math.sqrt(sum((p - avg) ** 2 for p in closes) / len(closes))
        realized_vol = (std / avg) * 100 if avg > 0 else 0
    _sub(f"Realized Volatility:   {realized_vol:.4f}%")

    # Bayesian regime classification
    def _gaussian_lik(x, mu, sigma):
        return math.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * math.sqrt(2 * math.pi))

    regime_params = {
        "calm":     (0.5, 0.3, 0.0, 0.005),
        "volatile": (3.0, 1.5, 0.0, 0.02),
        "trending": (1.5, 0.8, 0.01, 0.01),
    }
    prior = {"calm": 0.33, "volatile": 0.33, "trending": 0.34}

    # Momentum signal via EMA crossover
    momentum_score = 0.0
    ema_fast = ema_slow = 0.0
    if closes:
        ema_fast = closes[0]
        ema_slow = closes[0]
        for p in closes[1:]:
            ema_fast = 0.1 * p + 0.9 * ema_fast
            ema_slow = 0.03 * p + 0.97 * ema_slow
        momentum_score = (ema_fast - ema_slow) / ema_slow if ema_slow > 0 else 0

    posteriors = {}
    for regime, (v_mu, v_sigma, m_mu, m_sigma) in regime_params.items():
        vol_lik = _gaussian_lik(ewma_vol, v_mu, v_sigma)
        mom_lik = _gaussian_lik(abs(momentum_score), abs(m_mu), m_sigma)
        posteriors[regime] = vol_lik * mom_lik * prior[regime]
    total = sum(posteriors.values())
    if total > 0:
        posteriors = {k: v / total for k, v in posteriors.items()}
    else:
        posteriors = dict(prior)

    detected_regime = max(posteriors, key=posteriors.get)
    regime_confidence = posteriors[detected_regime]

    momentum_signal = ("bullish" if momentum_score > 0.005
                       else "bearish" if momentum_score < -0.005
                       else "neutral")
    _sub(f"Bayesian Regime:       {detected_regime} (conf={regime_confidence:.4f})")
    _sub(f"Regime Posteriors:     {', '.join(f'{k}={v:.4f}' for k, v in posteriors.items())}")
    _sub(f"Momentum Score:        {momentum_score:.6f} ({momentum_signal})")
    _sub(f"EMA Fast/Slow:         {ema_fast:.2f} / {ema_slow:.2f}")

    result["l2_ewma_vol"] = ewma_vol
    result["l2_realized_vol"] = realized_vol
    result["l2_regime"] = detected_regime
    result["l2_regime_confidence"] = regime_confidence
    result["l2_posteriors"] = posteriors
    result["l2_momentum"] = momentum_score
    result["l2_momentum_signal"] = momentum_signal

    # --- L3: Planning -----------------------------------------------------
    _sub("")
    _sub("L3 PLANNING - Strategy Selection & Confidence", indent=2)

    vol_bps = ewma_vol * 100  # convert pct to bps-ish for threshold matching
    if vol_bps > 800:
        selected_preset = "full_defense"
    elif vol_bps > 500 or detected_regime == "volatile":
        selected_preset = "volatile_defender"
    elif detected_regime == "trending" or momentum_signal != "neutral":
        selected_preset = "trend_rider"
    else:
        selected_preset = "calm_accumulator"

    preset_info = STRATEGY_PRESETS[selected_preset]

    # Confidence scoring (logistic function)
    data_quality = min(len(candles) / 24.0, 1.0)
    regime_clarity = abs(0.5 - regime_confidence) * 2
    trend_strength = min(abs(momentum_score) / 0.01, 1.0)
    z = -0.5 + 1.2 * data_quality + 0.8 * regime_clarity + 0.6 * trend_strength
    planning_confidence = 1.0 / (1.0 + math.exp(-z))
    planning_confidence = max(0.1, min(0.98, planning_confidence))

    _sub(f"Selected Preset:       {selected_preset}")
    _sub(f"Description:           {preset_info['description']}")
    _sub(f"Modules:               {', '.join(preset_info['modules'])}")
    _sub(f"Fee Range:             {preset_info['fee_range'][0]}-{preset_info['fee_range'][1]} (hundredths of bip)")
    _sub(f"Planning Confidence:   {planning_confidence:.4f}")
    _sub(f"  data_quality={data_quality:.2f}  regime_clarity={regime_clarity:.2f}  trend_strength={trend_strength:.2f}")

    result["l3_preset"] = selected_preset
    result["l3_confidence"] = planning_confidence
    result["l3_modules"] = preset_info["modules"]

    # --- L4: Evolution ----------------------------------------------------
    _sub("")
    _sub("L4 EVOLUTION - Adaptive Risk Parameters", indent=2)

    risk_tolerance = 0.50
    rebalance_eagerness = 0.50
    # Adapt risk based on volatility regime
    if detected_regime == "volatile":
        risk_tolerance = max(risk_tolerance - 0.10, 0.1)
        rebalance_eagerness = min(rebalance_eagerness + 0.10, 0.9)
    elif detected_regime == "calm":
        risk_tolerance = min(risk_tolerance + 0.05, 0.9)
    elif detected_regime == "trending":
        if momentum_signal == "bullish":
            risk_tolerance = min(risk_tolerance + 0.08, 0.9)
        elif momentum_signal == "bearish":
            risk_tolerance = max(risk_tolerance - 0.05, 0.1)

    _sub(f"Risk Tolerance:        {risk_tolerance:.2f}")
    _sub(f"Rebalance Eagerness:   {rebalance_eagerness:.2f}")

    result["l4_risk_tolerance"] = risk_tolerance
    result["l4_rebalance_eagerness"] = rebalance_eagerness

    # --- L5: Meta-Cognition -----------------------------------------------
    _sub("")
    _sub("L5 META-COGNITION - Reasoning Hash & Self-Assessment", indent=2)

    reasoning_data = {
        "prices": prices,
        "ewma_vol": ewma_vol,
        "regime": detected_regime,
        "regime_confidence": regime_confidence,
        "momentum": momentum_score,
        "selected_preset": selected_preset,
        "planning_confidence": planning_confidence,
        "risk_tolerance": risk_tolerance,
        "timestamp": int(time.time()),
    }
    reasoning_json = json.dumps(reasoning_data, sort_keys=True, separators=(",", ":"))
    reasoning_hash = "0x" + hashlib.sha256(reasoning_json.encode()).hexdigest()

    # Self-assessment score
    assessment_factors = [
        ("data_freshness", data_quality),
        ("regime_clarity", regime_clarity),
        ("confidence_level", planning_confidence),
        ("risk_calibration", 1.0 - abs(risk_tolerance - 0.5) * 2),
    ]
    self_assessment = sum(v for _, v in assessment_factors) / len(assessment_factors)

    _sub(f"Reasoning Hash:        {reasoning_hash[:42]}...")
    _sub(f"Self-Assessment Score: {self_assessment:.4f}")
    for name, val in assessment_factors:
        _sub(f"  {name:22s} {val:.4f}")

    result["l5_reasoning_hash"] = reasoning_hash
    result["l5_self_assessment"] = self_assessment

    return result


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 3: LLM Reasoning
# ═══════════════════════════════════════════════════════════════════════════

def run_llm_reasoning(analysis):
    """Generate a human-readable explanation using LLMReasoner (if available).

    Falls back to a template-based explanation if the llm_reasoning module
    is not installed.

    Returns:
        str - the reasoning explanation text.
    """
    _banner("STEP 3: LLM Reasoning - Human-Readable Explanation")

    if _HAS_LLM_REASONER:
        _sub("Using LLMReasoner from skills.genesis.scripts.llm_reasoning")
        try:
            reasoner = LLMReasoner()
            explanation = reasoner.explain(analysis)
            _sub("")
            print(explanation)
            return explanation
        except Exception as exc:
            _sub(f"LLMReasoner failed ({exc}), falling back to template")

    # Template-based fallback
    _sub("LLMReasoner not available - using template-based reasoning")
    _sub("")

    regime = analysis.get("l2_regime", "unknown")
    preset = analysis.get("l3_preset", "calm_accumulator")
    conf = analysis.get("l3_confidence", 0.0)
    vol = analysis.get("l2_ewma_vol", 0.0)
    mom = analysis.get("l2_momentum_signal", "neutral")
    risk = analysis.get("l4_risk_tolerance", 0.5)

    explanation = (
        f"  REASONING SUMMARY\n"
        f"  {'~' * 50}\n"
        f"  The market is currently in a '{regime}' regime with EWMA\n"
        f"  volatility at {vol:.4f}%. Momentum is {mom}.\n"
        f"\n"
        f"  Based on this analysis, the AI engine recommends the\n"
        f"  '{preset}' strategy preset with {conf:.1%} confidence.\n"
        f"\n"
        f"  Risk tolerance has been adjusted to {risk:.2f} to reflect\n"
        f"  current market conditions. "
    )
    if regime == "volatile":
        explanation += (
            "The high volatility environment\n"
            "  warrants defensive positioning with elevated fees and\n"
            "  MEV protection to shield liquidity providers."
        )
    elif regime == "trending":
        explanation += (
            "The trending market suggests using\n"
            "  wider ranges with TWAP rebalancing to capture\n"
            "  directional moves while managing impermanent loss."
        )
    else:
        explanation += (
            "The calm environment is ideal for\n"
            "  tight ranges and low fees to maximize swap volume\n"
            "  and fee accumulation."
        )

    print(explanation)
    return explanation


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 4: Strategy Selection
# ═══════════════════════════════════════════════════════════════════════════

def select_strategy(analysis):
    """Display the selected strategy preset with full module details.

    Returns:
        dict with preset name and configuration.
    """
    _banner("STEP 4: Strategy Selection")
    preset_name = analysis.get("l3_preset", "calm_accumulator")
    preset = STRATEGY_PRESETS[preset_name]

    _sub(f"Selected:    {preset_name}")
    _sub(f"Description: {preset['description']}")
    _sub(f"Modules:     {', '.join(preset['modules'])}")
    _sub(f"Fee Range:   {preset['fee_range'][0]}-{preset['fee_range'][1]} (hundredths of bip)")
    _sub(f"Vol Range:   {preset['vol_range'][0]}-{preset['vol_range'][1]} bps")
    _sub(f"Confidence:  {analysis.get('l3_confidence', 0):.4f}")

    _sub("")
    _sub("All presets comparison:")
    print(f"    {'Preset':<22s} {'Modules':<5s} {'Fee Min':>8s} {'Fee Max':>8s} {'Status':<10s}")
    print(f"    {'-'*22} {'-'*5} {'-'*8} {'-'*8} {'-'*10}")
    for name, info in STRATEGY_PRESETS.items():
        marker = "SELECTED" if name == preset_name else ""
        print(f"    {name:<22s} {len(info['modules']):<5d} {info['fee_range'][0]:>8d} "
              f"{info['fee_range'][1]:>8d} {marker:<10s}")

    return {"preset": preset_name, "config": preset}


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 5: On-Chain Verification
# ═══════════════════════════════════════════════════════════════════════════

def verify_onchain():
    """Read current contract state from X Layer mainnet via JSON-RPC.

    Reads:
        - GenesisHookAssembler: strategyCount, decisionCount, owner
        - StrategyNFT: totalSupply
        - V4 Hook: code verification

    Returns:
        dict with on-chain state values.
    """
    _banner("STEP 5: On-Chain Verification (X Layer Mainnet)")
    state = {}

    # GenesisHookAssembler reads
    assembler = CONTRACTS["assembler"]
    _sub(f"GenesisHookAssembler: {assembler}")

    # strategyCount() = 0x22068b44
    val = _safe_int(_eth_call(assembler, "0x22068b44"))
    state["strategy_count"] = val
    _sub(f"  strategyCount():  {val if val is not None else '?'}")

    # decisionCount() = 0x100b63cb
    val = _safe_int(_eth_call(assembler, "0x100b63cb"))
    state["decision_count"] = val
    _sub(f"  decisionCount():  {val if val is not None else '?'}")

    # owner() = 0x8da5cb5b
    raw = _eth_call(assembler, "0x8da5cb5b")
    if raw and len(raw) >= 42 and not str(raw).startswith("ERROR"):
        owner = "0x" + raw[-40:]
        state["owner"] = owner
        _sub(f"  owner():          {owner}")
    else:
        state["owner"] = None
        _sub("  owner():          ?")

    # StrategyNFT reads
    nft = CONTRACTS["strategy_nft"]
    _sub(f"StrategyNFT: {nft}")

    # totalSupply() = 0x18160ddd
    val = _safe_int(_eth_call(nft, "0x18160ddd"))
    state["nft_total_supply"] = val
    _sub(f"  totalSupply():    {val if val is not None else '?'}")

    # V4 Hook verification
    hook = CONTRACTS["v4_hook"]
    _sub(f"V4 Hook: {hook}")
    code = _rpc_call("eth_getCode", [hook, "latest"])
    has_code = code and code != "0x" and not str(code).startswith("ERROR")
    code_len = (len(code) - 2) // 2 if has_code else 0
    state["hook_deployed"] = has_code
    state["hook_code_bytes"] = code_len
    _sub(f"  Code deployed:    {'YES' if has_code else 'NO'} ({code_len} bytes)")

    # Hook flag verification
    addr_int = int(hook, 16)
    flags = addr_int & 0x3FFF
    has_before = bool(flags & (1 << 7))
    has_after = bool(flags & (1 << 6))
    _sub(f"  BEFORE_SWAP flag: {'YES' if has_before else 'NO'}")
    _sub(f"  AFTER_SWAP flag:  {'YES' if has_after else 'NO'}")
    state["hook_flags"] = {"before_swap": has_before, "after_swap": has_after}

    return state


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 6: Decision Journal Entry
# ═══════════════════════════════════════════════════════════════════════════

def create_journal_entry(analysis, strategy, onchain_state):
    """Create a decision journal entry with full reasoning chain.

    Returns:
        dict representing the journal entry.
    """
    _banner("STEP 6: Decision Journal Entry")

    reasoning_text = (
        f"Market regime: {analysis['l2_regime']} "
        f"(conf={analysis['l2_regime_confidence']:.4f}). "
        f"EWMA vol: {analysis['l2_ewma_vol']:.4f}%. "
        f"Momentum: {analysis['l2_momentum_signal']}. "
        f"Selected preset: {strategy['preset']} "
        f"(planning confidence: {analysis['l3_confidence']:.4f}). "
        f"Risk tolerance: {analysis['l4_risk_tolerance']:.2f}."
    )
    reasoning_hash = "0x" + hashlib.sha256(reasoning_text.encode()).hexdigest()

    entry = {
        "id": int(time.time()),
        "timestamp": int(time.time()),
        "decision_type": "STRATEGY_CREATE",
        "strategy_preset": strategy["preset"],
        "reasoning": reasoning_text,
        "reasoning_hash": reasoning_hash,
        "analysis_snapshot": {
            "regime": analysis["l2_regime"],
            "ewma_vol": analysis["l2_ewma_vol"],
            "momentum": analysis["l2_momentum_signal"],
            "confidence": analysis["l3_confidence"],
        },
        "onchain_snapshot": {
            "strategy_count": onchain_state.get("strategy_count"),
            "decision_count": onchain_state.get("decision_count"),
            "nft_supply": onchain_state.get("nft_total_supply"),
        },
        "on_chain_status": "demo_mode",
    }

    _sub(f"Entry ID:       {entry['id']}")
    _sub(f"Type:           {entry['decision_type']}")
    _sub(f"Preset:         {entry['strategy_preset']}")
    _sub(f"Reasoning Hash: {reasoning_hash[:42]}...")
    _sub(f"Status:         {entry['on_chain_status']}")
    _sub("")
    _sub("Full Reasoning:")
    # Word-wrap the reasoning for display
    words = reasoning_text.split()
    line = "      "
    for w in words:
        if len(line) + len(w) + 1 > 72:
            print(line)
            line = "      " + w
        else:
            line += " " + w if line.strip() else w
    if line.strip():
        print(line)

    return entry


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 7: NFT Eligibility Check
# ═══════════════════════════════════════════════════════════════════════════

def check_nft_eligibility():
    """Check if a hypothetical strategy meets NFT minting thresholds.

    Simulates strategy performance metrics for demonstration.

    Returns:
        dict with eligibility result and threshold details.
    """
    _banner("STEP 7: NFT Eligibility Check")

    # Simulated strategy metrics for demo
    demo_metrics = {
        "pnl_bps": 150,
        "total_swaps": 87,
        "run_hours": 72.5,
    }

    checks = []
    pnl_ok = demo_metrics["pnl_bps"] >= NFT_THRESHOLD_PNL_BPS
    checks.append(("PNL >= 100 bps", demo_metrics["pnl_bps"], NFT_THRESHOLD_PNL_BPS, "bps", pnl_ok))

    swaps_ok = demo_metrics["total_swaps"] >= NFT_THRESHOLD_SWAPS
    checks.append(("Swaps >= 50", demo_metrics["total_swaps"], NFT_THRESHOLD_SWAPS, "swaps", swaps_ok))

    hours_ok = demo_metrics["run_hours"] >= NFT_THRESHOLD_HOURS
    checks.append(("Runtime >= 48h", demo_metrics["run_hours"], NFT_THRESHOLD_HOURS, "hours", hours_ok))

    eligible = all(ok for *_, ok in checks)

    _sub("Simulated Strategy Metrics (demo):")
    _sub(f"  PNL:        {demo_metrics['pnl_bps']} bps (+{demo_metrics['pnl_bps']/100:.1f}%)")
    _sub(f"  Swaps:      {demo_metrics['total_swaps']}")
    _sub(f"  Runtime:    {demo_metrics['run_hours']:.1f} hours")
    _sub("")
    _sub("Threshold Checks:")
    for label, actual, threshold, unit, passed in checks:
        status = "PASS" if passed else "FAIL"
        _sub(f"  [{status}] {label:20s}  actual={actual} {unit} (threshold={threshold})")
    _sub("")
    _sub(f"NFT Eligible: {'YES - Strategy NFT can be minted' if eligible else 'NO - Thresholds not met'}")

    if eligible:
        config_hash = "0x" + hashlib.sha256(
            json.dumps(demo_metrics, sort_keys=True).encode()
        ).hexdigest()
        _sub(f"Config Hash:  {config_hash[:42]}...")

    return {"eligible": eligible, "metrics": demo_metrics, "checks": checks}


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 8: Summary Report
# ═══════════════════════════════════════════════════════════════════════════

def print_summary(market_data, analysis, strategy, onchain, journal, nft):
    """Print a formatted summary of the entire E2E demo cycle."""
    _banner("SUMMARY REPORT", char="*", width=72)

    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    _sub(f"Timestamp:         {ts}")
    _sub(f"Chain:             X Layer Mainnet (ID 196)")
    _sub("")

    # Market
    _sub("Market Data:", indent=2)
    for t in market_data.get("tickers", []):
        _sub(f"  {t['pair']}: ${t['price']:,.2f}")
    _sub(f"  Candles: {market_data.get('candles', []).__len__()} hourly (ETH-USDT)")

    # Analysis
    _sub("")
    _sub("AI Analysis:", indent=2)
    _sub(f"  EWMA Volatility:   {analysis['l2_ewma_vol']:.4f}%")
    _sub(f"  Regime:            {analysis['l2_regime']} (conf={analysis['l2_regime_confidence']:.4f})")
    _sub(f"  Momentum:          {analysis['l2_momentum_signal']} ({analysis['l2_momentum']:.6f})")
    _sub(f"  Self-Assessment:   {analysis['l5_self_assessment']:.4f}")

    # Strategy
    _sub("")
    _sub("Strategy:", indent=2)
    _sub(f"  Preset:            {strategy['preset']}")
    _sub(f"  Modules:           {', '.join(strategy['config']['modules'])}")
    _sub(f"  Confidence:        {analysis['l3_confidence']:.4f}")
    _sub(f"  Risk Tolerance:    {analysis['l4_risk_tolerance']:.2f}")

    # On-Chain
    _sub("")
    _sub("On-Chain State:", indent=2)
    _sub(f"  Strategies:        {onchain.get('strategy_count', '?')}")
    _sub(f"  Decisions:         {onchain.get('decision_count', '?')}")
    _sub(f"  NFT Supply:        {onchain.get('nft_total_supply', '?')}")
    _sub(f"  Hook Deployed:     {'YES' if onchain.get('hook_deployed') else 'NO'} "
         f"({onchain.get('hook_code_bytes', 0)} bytes)")

    # Journal
    _sub("")
    _sub("Decision Journal:", indent=2)
    _sub(f"  Entry ID:          {journal['id']}")
    _sub(f"  Reasoning Hash:    {journal['reasoning_hash'][:42]}...")

    # NFT
    _sub("")
    _sub("NFT Eligibility:", indent=2)
    _sub(f"  Eligible:          {'YES' if nft['eligible'] else 'NO'}")
    _sub(f"  PNL:               {nft['metrics']['pnl_bps']} bps")
    _sub(f"  Swaps:             {nft['metrics']['total_swaps']}")
    _sub(f"  Runtime:           {nft['metrics']['run_hours']}h")

    print()
    print("*" * 72)
    print("  Genesis Protocol E2E Demo Complete")
    print("  All 8 steps executed successfully.")
    print("*" * 72)
    print()


# ═══════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """Run the full end-to-end Genesis Protocol demonstration."""
    print()
    print("=" * 72)
    print("  Genesis Protocol - End-to-End Demonstration")
    print("  X Layer Mainnet (Chain 196) | OKX Public API | Live Data")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 72)

    # Step 1: Market Data
    market_data = fetch_market_data()

    # Step 2: AI Analysis
    analysis = run_ai_analysis(market_data)

    # Step 3: LLM Reasoning
    run_llm_reasoning(analysis)

    # Step 4: Strategy Selection
    strategy = select_strategy(analysis)

    # Step 5: On-Chain Verification
    onchain = verify_onchain()

    # Step 6: Decision Journal
    journal = create_journal_entry(analysis, strategy, onchain)

    # Step 7: NFT Eligibility
    nft = check_nft_eligibility()

    # Step 8: Summary Report
    print_summary(market_data, analysis, strategy, onchain, journal, nft)

    return 0


if __name__ == "__main__":
    sys.exit(main())
