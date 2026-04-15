"""Security Scanner -- token risk assessment via onchainos okx-security skill.

Scans tokens and pools for contract safety, liquidity depth, and rugpull
indicators before any strategy is deployed.  Uses subprocess to call the
onchainos CLI, following the same pattern as payment_handler.py and
strategy_manager.py.

Deep integration adds:
  - Real token contract analysis (proxy patterns, selfdestruct, ownership)
  - Honeypot detection via simulated buy+sell
  - Liquidity depth scoring relative to market cap
  - Historical rugpull pattern matching
  - OKX DEX token API integration for honeypot/tax data
"""
import hashlib
import json
import logging
import subprocess
import sys
import time
from collections import deque
from typing import Optional

from .config import DRY_RUN, CHAIN_ID, LOG_LEVEL

try:
    import requests as _requests
except ImportError:
    _requests = None

logger = logging.getLogger("genesis.security_scanner")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# ── Risk-score thresholds ────────────────────────────────────────────────
_MAX_ACCEPTABLE_RISK = 50          # 0-100 scale; above this is "unsafe"
_SIMULATED_RISK_SCORE = 15         # benign default for DRY_RUN / simulations

# ── OKX DEX API base URL ────────────────────────────────────────────────
OKX_DEX_BASE_URL = "https://www.okx.com"

# ── Known scam bytecode signatures (keccak256 prefix → description) ─────
_KNOWN_SCAM_SIGNATURES = {
    "selfdestruct": "ff",                       # SELFDESTRUCT opcode
    "delegatecall_proxy": "f4",                 # DELEGATECALL opcode (proxy pattern)
    "hidden_mint": "40c10f19",                  # mint(address,uint256)
    "hidden_transfer": "a9059cbb",              # transfer (if not expected)
    "ownership_renounce_fake": "715018a6",      # renounceOwnership()
    "approve_drain": "095ea7b3",                # approve(address,uint256)
    "blacklist_add": "44337ea1",                # addToBlacklist patterns
    "max_tx_manipulation": "3b124fe7",          # setMaxTxAmount patterns
    "fee_manipulation": "8da5cb5b",             # owner() used with fee changes
    "pause_trading": "02329a29",                # pause() / unpause()
}

# ── Weighted risk factors for pool assessment ────────────────────────────
_RISK_WEIGHTS = {
    "honeypot_score": 0.30,
    "contract_risk": 0.20,
    "liquidity_depth": 0.20,
    "ownership_risk": 0.15,
    "rugpull_pattern": 0.15,
}


class SecurityScanner:
    """Assess token and pool risk via the onchainos okx-security skill."""

    # ── Public API ───────────────────────────────────────────────────────

    def scan_token(self, address: str) -> dict:
        """Return a risk-score dict for a single token address.

        Keys: risk_score (int 0-100), flags (list[str]), safe (bool).
        """
        cmd = [
            "onchainos", "skill", "run", "okx-security",
            "--action", "token-risk",
            "--address", address,
            "--chain", str(CHAIN_ID),
        ]
        result = self._run_cmd(cmd)

        if result.get("error"):
            logger.warning("Security scan failed for %s: %s", address, result["error"])
            return {"risk_score": 100, "flags": ["scan_error"], "safe": False,
                    "error": result["error"]}

        try:
            data = json.loads(result["stdout"])
        except (json.JSONDecodeError, KeyError):
            logger.warning("Unparseable security response for %s", address)
            return {"risk_score": 100, "flags": ["parse_error"], "safe": False}

        risk_score = int(data.get("risk_score", 100))
        flags = list(data.get("flags", []))
        safe = risk_score <= _MAX_ACCEPTABLE_RISK
        return {"risk_score": risk_score, "flags": flags, "safe": safe}

    def scan_pool(self, token0: str, token1: str) -> dict:
        """Scan both tokens of a pool and return a combined risk dict.

        Keys: token0 (dict), token1 (dict), combined_risk (int), safe (bool).
        """
        t0_risk = self.scan_token(token0)
        t1_risk = self.scan_token(token1)
        combined = max(t0_risk["risk_score"], t1_risk["risk_score"])
        safe = t0_risk["safe"] and t1_risk["safe"]
        return {
            "token0": t0_risk,
            "token1": t1_risk,
            "combined_risk": combined,
            "safe": safe,
        }

    def is_safe_for_strategy(self, token0: str, token1: str) -> tuple:
        """Determine whether a token pair is safe enough for strategy deployment.

        Returns:
            (bool, str) -- (is_safe, human-readable reason)
        """
        pool_risk = self.scan_pool(token0, token1)

        if pool_risk["safe"]:
            reason = (
                f"Pool passed security scan "
                f"(combined_risk={pool_risk['combined_risk']})"
            )
            logger.info("Security OK for %s / %s: %s", token0, token1, reason)
            return True, reason

        # Build a descriptive rejection reason
        parts = []
        for label, tok in [("token0", pool_risk["token0"]),
                           ("token1", pool_risk["token1"])]:
            if not tok["safe"]:
                parts.append(
                    f"{label} risk={tok['risk_score']} flags={tok['flags']}"
                )
        reason = "Security check failed: " + "; ".join(parts)
        logger.warning("Security REJECT for %s / %s: %s", token0, token1, reason)
        return False, reason

    # ── Deep Integration: Token Contract Analysis ──────────────────────

    def deep_scan_token(self, address: str, chain_id: Optional[int] = None) -> dict:
        """Perform a deep token scan combining on-chain analysis with OKX DEX API data.

        Calls the OKX DEX aggregator ``/api/v6/dex/aggregator/all-tokens`` endpoint
        to retrieve real honeypot detection flags, buy/sell tax percentages, and
        token metadata. Falls back to CLI-based scanning when the REST call is
        unavailable.

        Args:
            address:  Token contract address (checksummed or lowercase).
            chain_id: Chain ID override (defaults to config CHAIN_ID).

        Returns:
            dict with keys:
                honeypot (bool), buy_tax_pct (float), sell_tax_pct (float),
                is_proxy (bool), has_selfdestruct (bool), ownership_concentration (float),
                scam_signatures (list[str]), risk_score (int 0-100), safe (bool),
                source (str).
        """
        cid = chain_id or CHAIN_ID

        # --- Attempt OKX DEX API for honeypot/tax data ---
        api_data = self._fetch_okx_token_data(address, cid)

        # --- Bytecode analysis for proxy / selfdestruct / scam patterns ---
        bytecode_flags = self._analyze_bytecode(address)

        # --- Ownership concentration heuristic ---
        ownership_concentration = self._estimate_ownership_concentration(address)

        # --- Combine API data with bytecode analysis ---
        honeypot = False
        buy_tax = 0.0
        sell_tax = 0.0
        source = "cli_fallback"

        if api_data and not api_data.get("error"):
            source = "okx_dex_api"
            # OKX token data may include honeypot and tax fields
            honeypot = bool(api_data.get("honeypot", False))
            buy_tax = _safe_float(api_data.get("buyTax", api_data.get("buy_tax", 0)))
            sell_tax = _safe_float(api_data.get("sellTax", api_data.get("sell_tax", 0)))
        else:
            # Fallback: run a simulated buy+sell honeypot check
            hp_result = self._simulate_honeypot_check(address, cid)
            honeypot = hp_result.get("is_honeypot", False)
            buy_tax = hp_result.get("buy_tax_pct", 0.0)
            sell_tax = hp_result.get("sell_tax_pct", 0.0)

        # --- Compute composite risk score ---
        honeypot_score = 100 if honeypot else min(100, (buy_tax + sell_tax) * 5)
        contract_risk = bytecode_flags.get("risk_score", 0)
        ownership_risk = min(100, ownership_concentration * 100)
        rugpull_score = len(bytecode_flags.get("scam_signatures", [])) * 20
        rugpull_score = min(100, rugpull_score)
        # Liquidity depth is unknown without pool context; default to neutral
        liquidity_score = 50

        weighted_risk = (
            _RISK_WEIGHTS["honeypot_score"] * honeypot_score
            + _RISK_WEIGHTS["contract_risk"] * contract_risk
            + _RISK_WEIGHTS["liquidity_depth"] * liquidity_score
            + _RISK_WEIGHTS["ownership_risk"] * ownership_risk
            + _RISK_WEIGHTS["rugpull_pattern"] * rugpull_score
        )
        risk_score = int(min(100, max(0, weighted_risk)))
        safe = risk_score <= _MAX_ACCEPTABLE_RISK

        return {
            "address": address,
            "honeypot": honeypot,
            "buy_tax_pct": round(buy_tax, 2),
            "sell_tax_pct": round(sell_tax, 2),
            "is_proxy": bytecode_flags.get("is_proxy", False),
            "has_selfdestruct": bytecode_flags.get("has_selfdestruct", False),
            "ownership_concentration": round(ownership_concentration, 4),
            "scam_signatures": bytecode_flags.get("scam_signatures", []),
            "risk_score": risk_score,
            "risk_breakdown": {
                "honeypot_score": round(honeypot_score, 2),
                "contract_risk": round(contract_risk, 2),
                "liquidity_score": liquidity_score,
                "ownership_risk": round(ownership_risk, 2),
                "rugpull_score": round(rugpull_score, 2),
            },
            "safe": safe,
            "source": source,
        }

    def assess_pool_risk(
        self, token0: str, token1: str,
        liquidity_usd: float = 0.0,
        market_cap_usd: float = 0.0,
    ) -> dict:
        """Assess overall pool risk using weighted scoring across multiple dimensions.

        Performs deep scans on both tokens, evaluates liquidity depth relative to
        market cap, and produces a weighted composite risk score.

        Args:
            token0:          Address of the first token in the pool.
            token1:          Address of the second token in the pool.
            liquidity_usd:   Total pool liquidity in USD (0 = unknown).
            market_cap_usd:  Combined market cap of the pair in USD (0 = unknown).

        Returns:
            dict with keys:
                token0_scan (dict), token1_scan (dict),
                liquidity_depth_score (float 0-100),
                combined_risk (int 0-100), safe (bool),
                risk_factors (list[str]), recommendation (str).
        """
        t0_scan = self.deep_scan_token(token0)
        t1_scan = self.deep_scan_token(token1)

        # --- Liquidity depth scoring ---
        liquidity_depth_score = self._score_liquidity_depth(
            liquidity_usd, market_cap_usd,
        )

        # --- Aggregate risk factors ---
        risk_factors = []
        if t0_scan.get("honeypot"):
            risk_factors.append("token0_honeypot")
        if t1_scan.get("honeypot"):
            risk_factors.append("token1_honeypot")
        if t0_scan.get("is_proxy"):
            risk_factors.append("token0_proxy_contract")
        if t1_scan.get("is_proxy"):
            risk_factors.append("token1_proxy_contract")
        if t0_scan.get("has_selfdestruct"):
            risk_factors.append("token0_selfdestruct")
        if t1_scan.get("has_selfdestruct"):
            risk_factors.append("token1_selfdestruct")
        if t0_scan.get("ownership_concentration", 0) > 0.5:
            risk_factors.append("token0_concentrated_ownership")
        if t1_scan.get("ownership_concentration", 0) > 0.5:
            risk_factors.append("token1_concentrated_ownership")
        if liquidity_depth_score < 30:
            risk_factors.append("low_liquidity_depth")
        if t0_scan.get("buy_tax_pct", 0) > 5 or t0_scan.get("sell_tax_pct", 0) > 5:
            risk_factors.append("token0_high_tax")
        if t1_scan.get("buy_tax_pct", 0) > 5 or t1_scan.get("sell_tax_pct", 0) > 5:
            risk_factors.append("token1_high_tax")

        # --- Weighted combined risk ---
        token_risk = max(t0_scan["risk_score"], t1_scan["risk_score"])
        # Liquidity depth is inverse: low depth = high risk
        liquidity_risk = max(0, 100 - liquidity_depth_score)
        combined_risk = int(
            0.60 * token_risk
            + 0.25 * liquidity_risk
            + 0.15 * min(100, len(risk_factors) * 15)
        )
        combined_risk = min(100, max(0, combined_risk))
        safe = combined_risk <= _MAX_ACCEPTABLE_RISK

        # --- Recommendation ---
        if combined_risk <= 20:
            recommendation = "LOW RISK: Pool appears safe for strategy deployment."
        elif combined_risk <= 50:
            recommendation = "MODERATE RISK: Proceed with caution; monitor closely."
        elif combined_risk <= 75:
            recommendation = "HIGH RISK: Not recommended without manual review."
        else:
            recommendation = "CRITICAL RISK: Do NOT deploy. Multiple red flags detected."

        return {
            "token0_scan": t0_scan,
            "token1_scan": t1_scan,
            "liquidity_depth_score": round(liquidity_depth_score, 2),
            "combined_risk": combined_risk,
            "safe": safe,
            "risk_factors": risk_factors,
            "recommendation": recommendation,
        }

    # ── Deep Integration: Internal Analysis Helpers ──────────────────

    def _fetch_okx_token_data(self, address: str, chain_id: int) -> Optional[dict]:
        """Fetch token data from OKX DEX aggregator all-tokens endpoint.

        Queries ``/api/v6/dex/aggregator/all-tokens`` filtered by chain to
        retrieve honeypot flags, buy/sell tax, and token metadata.

        Args:
            address:  Token contract address.
            chain_id: Numeric chain ID.

        Returns:
            dict with token metadata or None on failure.
        """
        if DRY_RUN:
            logger.info("[DRY_RUN] OKX DEX API lookup for %s on chain %d", address, chain_id)
            return {
                "honeypot": False,
                "buyTax": 0,
                "sellTax": 0,
                "tokenSymbol": "SIM",
                "dry_run": True,
            }

        # Try onchainos REST API wrapper first
        try:
            from . import onchainos_api
            api = onchainos_api.OnchainOSAPI()
            result = api.get_dex_tokens(chain_id=str(chain_id))
            if result and isinstance(result.get("data"), list):
                addr_lower = address.lower()
                for token_entry in result["data"]:
                    if token_entry.get("tokenContractAddress", "").lower() == addr_lower:
                        return token_entry
                logger.debug("Token %s not found in OKX all-tokens response", address)
                return None
        except (ImportError, AttributeError, Exception) as exc:
            logger.debug("OnchainOSAPI unavailable, trying requests: %s", exc)

        # Direct HTTP fallback
        if _requests is None:
            logger.debug("requests library not available for OKX API call")
            return None

        try:
            url = f"{OKX_DEX_BASE_URL}/api/v6/dex/aggregator/all-tokens"
            resp = _requests.get(
                url,
                params={"chainId": str(chain_id)},
                timeout=15,
            )
            data = resp.json()
            if isinstance(data.get("data"), list):
                addr_lower = address.lower()
                for token_entry in data["data"]:
                    if token_entry.get("tokenContractAddress", "").lower() == addr_lower:
                        return token_entry
        except Exception as exc:
            logger.warning("OKX DEX API request failed: %s", exc)

        return None

    def _analyze_bytecode(self, address: str) -> dict:
        """Analyze token contract bytecode for dangerous patterns.

        Checks for proxy patterns (DELEGATECALL), SELFDESTRUCT opcodes,
        and known scam function signatures in the deployed bytecode.

        Args:
            address: Token contract address.

        Returns:
            dict with is_proxy, has_selfdestruct, scam_signatures, risk_score.
        """
        if DRY_RUN:
            return {
                "is_proxy": False,
                "has_selfdestruct": False,
                "scam_signatures": [],
                "risk_score": 0,
                "dry_run": True,
            }

        # Fetch bytecode via onchainos CLI
        cmd = [
            "onchainos", "rpc", "call",
            "--method", "eth_getCode",
            "--params", json.dumps([address, "latest"]),
            "--chain", str(CHAIN_ID),
        ]
        result = self._run_cmd(cmd)
        bytecode = ""
        if not result.get("error"):
            try:
                parsed = json.loads(result.get("stdout", "{}"))
                bytecode = parsed.get("result", result.get("stdout", "")).strip()
            except (json.JSONDecodeError, AttributeError):
                bytecode = result.get("stdout", "").strip()

        if not bytecode or bytecode == "0x":
            return {
                "is_proxy": False,
                "has_selfdestruct": False,
                "scam_signatures": ["no_bytecode_eoa_or_destroyed"],
                "risk_score": 80,
            }

        bytecode_lower = bytecode.lower()
        is_proxy = _KNOWN_SCAM_SIGNATURES["delegatecall_proxy"] in bytecode_lower
        has_selfdestruct = _KNOWN_SCAM_SIGNATURES["selfdestruct"] in bytecode_lower

        scam_sigs = []
        for name, sig in _KNOWN_SCAM_SIGNATURES.items():
            if name in ("selfdestruct", "delegatecall_proxy"):
                continue  # Already checked above
            if sig in bytecode_lower:
                scam_sigs.append(name)

        risk_score = 0
        if is_proxy:
            risk_score += 25
        if has_selfdestruct:
            risk_score += 35
        risk_score += len(scam_sigs) * 8
        risk_score = min(100, risk_score)

        return {
            "is_proxy": is_proxy,
            "has_selfdestruct": has_selfdestruct,
            "scam_signatures": scam_sigs,
            "risk_score": risk_score,
        }

    def _estimate_ownership_concentration(self, address: str) -> float:
        """Estimate token ownership concentration (0.0 = distributed, 1.0 = single holder).

        Uses a heuristic based on top holder data when available, or returns
        a conservative estimate when data is unavailable.

        Args:
            address: Token contract address.

        Returns:
            float between 0.0 and 1.0 representing concentration ratio.
        """
        if DRY_RUN:
            return 0.05  # Benign default

        cmd = [
            "onchainos", "skill", "run", "okx-security",
            "--action", "top-holders",
            "--address", address,
            "--chain", str(CHAIN_ID),
        ]
        result = self._run_cmd(cmd)

        if result.get("error"):
            return 0.3  # Conservative unknown estimate

        try:
            data = json.loads(result.get("stdout", "{}"))
            holders = data.get("holders", [])
            if not holders:
                return 0.3

            # Concentration = fraction held by top holder
            top_pct = _safe_float(holders[0].get("percentage", 0))
            # Normalize: 100% -> 1.0, 0% -> 0.0
            return min(1.0, top_pct / 100.0)
        except (json.JSONDecodeError, IndexError, KeyError):
            return 0.3

    def _simulate_honeypot_check(self, address: str, chain_id: int) -> dict:
        """Simulate a buy+sell cycle to detect honeypot behavior.

        Attempts to simulate swapping a small amount into the token and then
        back out. If the sell simulation fails or returns significantly less
        than expected, the token is flagged as a potential honeypot.

        Args:
            address:  Token contract address.
            chain_id: Chain ID for the simulation.

        Returns:
            dict with is_honeypot, buy_tax_pct, sell_tax_pct, details.
        """
        if DRY_RUN:
            return {
                "is_honeypot": False,
                "buy_tax_pct": 0.0,
                "sell_tax_pct": 0.0,
                "details": "dry_run simulation",
            }

        sim_amount = "1000000"  # Simulate with 1 USDT (6 decimals)
        # X Layer USDT contract address
        usdt_address = "0x1E4a5963aBFD975d8c9021ce480b42188849D41d"

        # Simulate buy: USDT -> token
        buy_cmd = [
            "onchainos", "skill", "run", "swap-integration",
            "--action", "simulate",
            "--token-in", usdt_address,
            "--token-out", address,
            "--amount", sim_amount,
            "--swap-mode", "exactIn",
            "--chain", str(chain_id),
        ]
        buy_result = self._run_cmd(buy_cmd)

        if buy_result.get("error"):
            return {
                "is_honeypot": True,
                "buy_tax_pct": 100.0,
                "sell_tax_pct": 100.0,
                "details": f"Buy simulation failed: {buy_result['error']}",
            }

        try:
            buy_data = json.loads(buy_result.get("stdout", "{}"))
            tokens_received = _safe_float(buy_data.get("outputAmount", 0))
        except (json.JSONDecodeError, KeyError):
            tokens_received = 0

        if tokens_received <= 0:
            return {
                "is_honeypot": True,
                "buy_tax_pct": 100.0,
                "sell_tax_pct": 100.0,
                "details": "Buy simulation returned zero tokens",
            }

        # Simulate sell: token -> USDT
        sell_cmd = [
            "onchainos", "skill", "run", "swap-integration",
            "--action", "simulate",
            "--token-in", address,
            "--token-out", usdt_address,
            "--amount", str(int(tokens_received)),
            "--swap-mode", "exactIn",
            "--chain", str(chain_id),
        ]
        sell_result = self._run_cmd(sell_cmd)

        if sell_result.get("error"):
            return {
                "is_honeypot": True,
                "buy_tax_pct": 0.0,
                "sell_tax_pct": 100.0,
                "details": f"Sell simulation failed (classic honeypot): {sell_result['error']}",
            }

        try:
            sell_data = json.loads(sell_result.get("stdout", "{}"))
            usdt_received = _safe_float(sell_data.get("outputAmount", 0))
        except (json.JSONDecodeError, KeyError):
            usdt_received = 0

        input_amount = _safe_float(sim_amount)
        buy_tax_pct = max(0, (1 - (tokens_received / max(1, input_amount))) * 100) if input_amount > 0 else 0
        sell_tax_pct = max(0, (1 - (usdt_received / max(1, input_amount))) * 100) if input_amount > 0 else 0
        round_trip_loss = max(0, (1 - (usdt_received / max(1, input_amount))) * 100)

        is_honeypot = sell_tax_pct > 50 or usdt_received <= 0

        return {
            "is_honeypot": is_honeypot,
            "buy_tax_pct": round(buy_tax_pct, 2),
            "sell_tax_pct": round(sell_tax_pct, 2),
            "round_trip_loss_pct": round(round_trip_loss, 2),
            "details": "honeypot detected" if is_honeypot else "passed",
        }

    def _score_liquidity_depth(
        self, liquidity_usd: float, market_cap_usd: float,
    ) -> float:
        """Score liquidity depth relative to market cap on a 0-100 scale.

        Higher scores indicate healthier liquidity-to-market-cap ratios,
        reducing the risk of slippage and price manipulation.

        Args:
            liquidity_usd:   Total pool liquidity in USD.
            market_cap_usd:  Token market capitalization in USD.

        Returns:
            float score 0-100 where 100 = excellent depth.
        """
        if liquidity_usd <= 0:
            return 0.0
        if market_cap_usd <= 0:
            # If market cap unknown, score based on absolute liquidity
            if liquidity_usd >= 1_000_000:
                return 80.0
            elif liquidity_usd >= 100_000:
                return 60.0
            elif liquidity_usd >= 10_000:
                return 40.0
            else:
                return 20.0

        ratio = liquidity_usd / market_cap_usd

        # Scoring curve: ratio >= 0.10 (10%) = 100, ratio 0 = 0
        # Use a logarithmic-ish mapping for practical ranges
        if ratio >= 0.10:
            return 100.0
        elif ratio >= 0.05:
            return 80.0 + (ratio - 0.05) / 0.05 * 20.0
        elif ratio >= 0.02:
            return 60.0 + (ratio - 0.02) / 0.03 * 20.0
        elif ratio >= 0.005:
            return 30.0 + (ratio - 0.005) / 0.015 * 30.0
        elif ratio >= 0.001:
            return 10.0 + (ratio - 0.001) / 0.004 * 20.0
        else:
            return ratio / 0.001 * 10.0

    # ── Private helpers ──────────────────────────────────────────────────

    def _run_cmd(self, cmd):
        """Execute a subprocess command, respecting DRY_RUN."""
        logger.debug("cmd: %s", " ".join(cmd))
        if DRY_RUN:
            logger.info("[DRY_RUN] %s", " ".join(cmd))
            return {"stdout": json.dumps({
                "risk_score": _SIMULATED_RISK_SCORE,
                "flags": [],
                "dry_run": True,
            })}
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                return {"error": proc.stderr or f"exit code {proc.returncode}"}
            return {"stdout": proc.stdout}
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return {"error": str(exc)}


# ── Module-level helpers ──────────────────────────────────────────────────

def _safe_float(value) -> float:
    """Safely convert a value to float, returning 0.0 on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ── Runtime Anomaly Monitoring ────────────────────────────────────────────

# Default configuration for the runtime monitor
_DEFAULT_HISTORY_SIZE = 200       # Max operations stored per component
_DEFAULT_WINDOW_SIZE = 50         # Sliding window for error-rate calculation
_LATENCY_ANOMALY_FACTOR = 3.0    # Latency > 3x rolling avg = anomaly
_ERROR_RATE_THRESHOLD = 0.20     # Error rate > 20% = anomaly
_CRITICAL_ERROR_RATE = 0.50      # Error rate > 50% = critical


class RuntimeMonitor:
    """Track the agent's own runtime behaviour and flag anomalies.

    Monitors operation latencies, error rates, and memory usage across
    named components (e.g. ``market_oracle``, ``payment``, ``strategy``).
    All history buffers use :class:`collections.deque` with a fixed
    ``maxlen`` so memory is bounded.

    Severity levels:
        * ``"info"``     -- metric of interest, no action needed
        * ``"warning"``  -- threshold breached, warrants attention
        * ``"critical"`` -- severe degradation, intervention likely needed
    """

    SEVERITY_INFO = "info"
    SEVERITY_WARNING = "warning"
    SEVERITY_CRITICAL = "critical"

    def __init__(self, history_size: int = _DEFAULT_HISTORY_SIZE,
                 window_size: int = _DEFAULT_WINDOW_SIZE):
        self._history_size = history_size
        self._window_size = window_size

        # component -> deque of (operation, duration_ms, success, timestamp)
        self._operations: dict[str, deque] = {}
        # component -> operation -> deque of duration_ms (successes only)
        self._latencies: dict[str, dict[str, deque]] = {}

        self._logger = logging.getLogger("genesis.runtime_monitor")

    # ── Public API ────────────────────────────────────────────────────

    def record_operation(self, component: str, operation: str,
                         duration_ms: float, success: bool) -> None:
        """Log a single operation for *component*.

        Args:
            component:   Logical subsystem name (e.g. ``"market_oracle"``).
            operation:   Operation identifier (e.g. ``"fetch_price"``).
            duration_ms: Wall-clock duration in milliseconds.
            success:     Whether the operation completed without error.
        """
        if component not in self._operations:
            self._operations[component] = deque(maxlen=self._history_size)
            self._latencies[component] = {}

        self._operations[component].append(
            (operation, duration_ms, success, time.time())
        )

        if success:
            if operation not in self._latencies[component]:
                self._latencies[component][operation] = deque(
                    maxlen=self._history_size,
                )
            self._latencies[component][operation].append(duration_ms)

    def check_anomalies(self) -> list[dict]:
        """Scan all tracked components and return a list of detected anomalies.

        Each anomaly dict contains:
            ``component``, ``type``, ``detail``, ``severity``, ``value``,
            ``threshold``, ``timestamp``.
        """
        anomalies: list[dict] = []
        now = time.time()

        for component, ops in self._operations.items():
            # --- Error-rate check (sliding window) ---
            recent = list(ops)[-self._window_size:]
            if recent:
                failures = sum(1 for _, _, ok, _ in recent if not ok)
                error_rate = failures / len(recent)
                if error_rate > _CRITICAL_ERROR_RATE:
                    anomalies.append(self._anomaly(
                        component, "error_rate",
                        f"{failures}/{len(recent)} operations failed",
                        self.SEVERITY_CRITICAL, error_rate,
                        _CRITICAL_ERROR_RATE, now,
                    ))
                elif error_rate > _ERROR_RATE_THRESHOLD:
                    anomalies.append(self._anomaly(
                        component, "error_rate",
                        f"{failures}/{len(recent)} operations failed",
                        self.SEVERITY_WARNING, error_rate,
                        _ERROR_RATE_THRESHOLD, now,
                    ))

            # --- Latency check per operation ---
            for op, durations in self._latencies.get(component, {}).items():
                if len(durations) < 2:
                    continue
                avg = sum(durations) / len(durations)
                latest = durations[-1]
                threshold = avg * _LATENCY_ANOMALY_FACTOR
                if latest > threshold:
                    severity = (self.SEVERITY_CRITICAL
                                if latest > avg * _LATENCY_ANOMALY_FACTOR * 2
                                else self.SEVERITY_WARNING)
                    anomalies.append(self._anomaly(
                        component, "latency_spike",
                        f"{op}: {latest:.1f}ms vs avg {avg:.1f}ms",
                        severity, latest, threshold, now,
                    ))

        # --- Memory check ---
        mem_anomaly = self._check_memory(now)
        if mem_anomaly:
            anomalies.append(mem_anomaly)

        return anomalies

    def get_health_report(self) -> dict:
        """Return an overall health snapshot of all tracked components.

        Returns:
            dict with ``components`` (per-component stats), ``anomalies``
            (current anomaly list), ``memory_mb``, and ``timestamp``.
        """
        report: dict = {
            "timestamp": time.time(),
            "memory_mb": self._current_memory_mb(),
            "components": {},
            "anomalies": self.check_anomalies(),
        }

        for component, ops in self._operations.items():
            recent = list(ops)[-self._window_size:]
            total = len(recent)
            failures = sum(1 for _, _, ok, _ in recent if not ok)
            all_durations = [d for _, d, ok, _ in recent if ok]
            avg_latency = (sum(all_durations) / len(all_durations)
                           if all_durations else 0.0)
            report["components"][component] = {
                "total_ops": len(ops),
                "recent_ops": total,
                "recent_failures": failures,
                "error_rate": round(failures / total, 4) if total else 0.0,
                "avg_latency_ms": round(avg_latency, 2),
                "operations_tracked": list(
                    self._latencies.get(component, {}).keys()
                ),
            }

        return report

    def reset_counters(self) -> None:
        """Clear all tracking data."""
        self._operations.clear()
        self._latencies.clear()
        self._logger.info("RuntimeMonitor counters reset")

    # ── Internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _anomaly(component: str, anomaly_type: str, detail: str,
                 severity: str, value: float, threshold: float,
                 timestamp: float) -> dict:
        return {
            "component": component,
            "type": anomaly_type,
            "detail": detail,
            "severity": severity,
            "value": round(value, 4),
            "threshold": round(threshold, 4),
            "timestamp": timestamp,
        }

    @staticmethod
    def _current_memory_mb() -> float:
        """Return current process RSS in megabytes (best-effort)."""
        try:
            import resource as _resource
            # maxrss is in KB on Linux, bytes on macOS
            rss_kb = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
            if sys.platform == "darwin":
                return round(rss_kb / (1024 * 1024), 2)
            return round(rss_kb / 1024, 2)
        except (ImportError, AttributeError):
            return 0.0

    def _check_memory(self, now: float) -> Optional[dict]:
        """Flag a memory anomaly if RSS exceeds conservative thresholds."""
        mb = self._current_memory_mb()
        if mb > 1024:
            return self._anomaly(
                "system", "memory_usage",
                f"RSS {mb:.1f} MB exceeds 1024 MB",
                self.SEVERITY_CRITICAL, mb, 1024.0, now,
            )
        if mb > 512:
            return self._anomaly(
                "system", "memory_usage",
                f"RSS {mb:.1f} MB exceeds 512 MB",
                self.SEVERITY_WARNING, mb, 512.0, now,
            )
        return None
