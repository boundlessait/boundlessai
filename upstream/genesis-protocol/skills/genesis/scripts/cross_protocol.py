"""Cross-Protocol DeFi Integration for Genesis Protocol on X Layer.

Integrates with multiple protocols beyond Uniswap V4 to provide:
  - DEX route comparison (Hook pool vs OKX DEX Aggregator)
  - Lending rate queries across X Layer protocols
  - Cross-venue arbitrage scanning
  - Multi-protocol yield optimization
  - X Layer bridge (OKB Bridge) status checks

Uses only stdlib (urllib, json). All external calls degrade gracefully
to simulated data when endpoints are unreachable, keeping the module
usable in offline/hackathon demo environments.

Reference APIs:
  - OKX DEX Aggregator: https://web3.okx.com/api/v6/dex/aggregator/quote
  - OKX DeFi API: https://web3.okx.com/api/v5/defi/
  - X Layer RPC: https://rpc.xlayer.tech
"""

import json
import logging
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Dict, List, Optional

from . import config

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

X_LAYER_CHAIN_ID = "196"
X_LAYER_RPC = "https://rpc.xlayer.tech"

POOL_MANAGER = "0x360e68faCCca8cA495c1B759Fd9EEe466dB9Fb32"

TOKENS: Dict[str, str] = {
    "WOKB": "0xe538905cf8410324e03A5A23C1c177a474D59b2b",
    "USDT": "0x1E4a5963aBFD975d8c9021ce480b42188849D41d",
    "WETH": "0x5A77f1443D16ee5761d310e38b62f77f726bC71c",
}

OKX_DEX_QUOTE_URL = "https://web3.okx.com/api/v6/dex/aggregator/quote"
OKX_DEFI_BASE_URL = "https://web3.okx.com/api/v5/defi"
OKX_BRIDGE_URL = "https://web3.okx.com/api/v5/defi/bridge/status"

# Simulated lending protocols on X Layer for demo purposes
LENDING_PROTOCOLS = [
    {"name": "LayerBank", "type": "lending", "chain": "xlayer"},
    {"name": "OKX Earn", "type": "yield", "chain": "xlayer"},
    {"name": "Compound (bridged)", "type": "lending", "chain": "xlayer"},
]

REQUEST_TIMEOUT = 10  # seconds


# ── Helpers ──────────────────────────────────────────────────────────────────

def _http_get(url: str, params: Optional[Dict] = None,
              timeout: int = REQUEST_TIMEOUT) -> Optional[Dict]:
    """GET request via urllib. Returns parsed JSON or None on failure."""
    try:
        if params:
            qs = urllib.parse.urlencode(params)
            url = f"{url}?{qs}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            OSError) as exc:
        logger.debug("HTTP GET %s failed: %s", url, exc)
        return None


def _rpc_call(method: str, params: list,
              rpc_url: str = X_LAYER_RPC) -> Optional[Any]:
    """JSON-RPC 2.0 call to X Layer node."""
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    }).encode()
    req = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            if "error" in body:
                logger.warning("RPC error: %s", body["error"])
                return None
            return body.get("result")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        logger.debug("RPC call %s failed: %s", method, exc)
        return None


class CrossProtocolEngine:
    """Cross-protocol DeFi integration engine for the Genesis Protocol."""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.rpc_url = X_LAYER_RPC
        self.hook_address = config.MAINNET_CONTRACTS.get(
            "v4_hook", "0x174a2450b342042AAe7398545f04B199248E69c0"
        )
        self._cache: Dict[str, Any] = {}
        logger.info("CrossProtocolEngine initialised (dry_run=%s)", dry_run)

    # ── Public API ───────────────────────────────────────────────────────

    def compare_dex_routes(self, token_in: str, token_out: str,
                           amount: float) -> Dict[str, Any]:
        """Compare swap quotes: Hook pool vs OKX DEX Aggregator.

        Returns both quotes and a recommendation for which venue is better.
        Falls back to simulated data if APIs are unreachable.
        """
        in_addr = TOKENS.get(token_in, token_in)
        out_addr = TOKENS.get(token_out, token_out)
        decimals = 18 if token_in in ("WOKB", "WETH") else 6
        amount_wei = int(amount * (10 ** decimals))

        hook_quote = self._get_hook_pool_quote(token_in, token_out, amount)
        dex_quote = self._get_dex_aggregator_quote(in_addr, out_addr, amount_wei)

        # If live data unavailable, produce simulated comparison
        if hook_quote is None:
            hook_quote = {
                "source": "genesis_hook_pool",
                "amount_out": round(amount * 0.9985, 6),
                "fee_bps": 30,
                "simulated": True,
            }
        if dex_quote is None:
            dex_quote = {
                "source": "okx_dex_aggregator",
                "amount_out": round(amount * 0.9970, 6),
                "fee_bps": 50,
                "simulated": True,
            }

        hook_out = hook_quote["amount_out"]
        dex_out = dex_quote["amount_out"]
        better = "hook_pool" if hook_out >= dex_out else "dex_aggregator"
        edge_bps = abs(hook_out - dex_out) / max(hook_out, dex_out) * 10_000

        return {
            "pair": f"{token_in}/{token_out}",
            "amount_in": amount,
            "hook_pool": hook_quote,
            "dex_aggregator": dex_quote,
            "recommendation": better,
            "edge_bps": round(edge_bps, 2),
            "timestamp": int(time.time()),
        }

    def check_lending_rates(self) -> Dict[str, Any]:
        """Query lending protocol rates on X Layer.

        Attempts to pull data from OKX DeFi API. Falls back to realistic
        simulated rates for demo environments.
        """
        live_data = _http_get(
            f"{OKX_DEFI_BASE_URL}/explore/protocol/list",
            params={"chainId": X_LAYER_CHAIN_ID},
        )

        if live_data and live_data.get("data"):
            protocols = []
            for p in live_data["data"][:10]:
                protocols.append({
                    "name": p.get("protocolName", "Unknown"),
                    "tvl_usd": p.get("tvl", 0),
                    "apy_pct": p.get("apy", 0),
                })
            return {"source": "live", "protocols": protocols,
                    "timestamp": int(time.time())}

        # Simulated fallback
        rates = self._simulate_lending_rates()
        return {"source": "simulated", "protocols": rates,
                "timestamp": int(time.time())}

    def arbitrage_scanner(self, pair: str) -> Dict[str, Any]:
        """Detect price discrepancies between Hook pool and DEX aggregator.

        Args:
            pair: Slash-separated pair, e.g. "WETH/USDT".

        Returns a dict with detected opportunities and whether they exceed
        the profitability threshold (gas + fees).
        """
        tokens = pair.split("/")
        if len(tokens) != 2:
            return {"error": f"Invalid pair format: {pair}. Use TOKEN_A/TOKEN_B."}

        token_in, token_out = tokens[0].strip(), tokens[1].strip()
        test_amounts = [0.1, 1.0, 10.0]
        opportunities: List[Dict] = []

        for amt in test_amounts:
            result = self.compare_dex_routes(token_in, token_out, amt)
            edge = result["edge_bps"]
            # Estimate gas cost at ~0.001 OKB (~$0.05) per swap
            est_gas_bps = 5.0 / max(amt, 0.01) * 100  # rough bps cost
            net_edge = edge - est_gas_bps
            profitable = net_edge > 0

            opportunities.append({
                "amount": amt,
                "gross_edge_bps": round(edge, 2),
                "est_gas_bps": round(est_gas_bps, 2),
                "net_edge_bps": round(net_edge, 2),
                "profitable": profitable,
                "direction": result["recommendation"],
            })

        best = max(opportunities, key=lambda o: o["net_edge_bps"])
        return {
            "pair": pair,
            "opportunities": opportunities,
            "best_opportunity": best,
            "scan_block": self._get_block_number(),
            "timestamp": int(time.time()),
        }

    def yield_optimizer(self, strategy_id: str) -> Dict[str, Any]:
        """Suggest yield optimization across protocols.

        Compares the Genesis Hook pool fee yield for *strategy_id* against
        lending/LP yields available elsewhere on X Layer and recommends
        allocation adjustments.
        """
        lending = self.check_lending_rates()
        lending_rates = lending.get("protocols", [])

        # Estimate current Hook pool APY from strategy preset
        preset = config.STRATEGY_PRESETS.get(strategy_id)
        if preset is None:
            # Fall back to a generic estimate
            hook_apy = 12.5
            strategy_label = strategy_id
        else:
            # Rough APY estimate: base_fee / 10000 * volume_multiplier * 365
            fee_overrides = preset.get("overrides", {}).get("dynamic_fee", {})
            base_fee = fee_overrides.get("base_fee",
                                         config.AVAILABLE_MODULES["dynamic_fee"]
                                         ["default_params"]["base_fee"])
            hook_apy = round((base_fee / 10_000) * 100 * 3.5, 2)  # simplified
            strategy_label = preset.get("description", strategy_id)

        alternatives: List[Dict] = []
        for p in lending_rates:
            apy = p.get("apy_pct", 0)
            alternatives.append({
                "protocol": p["name"],
                "asset": p.get("asset", "USDT"),
                "apy_pct": apy,
                "vs_hook_delta_pct": round(apy - hook_apy, 2),
            })

        # Sort by APY descending
        alternatives.sort(key=lambda x: x["apy_pct"], reverse=True)

        suggestion = "hold_hook"
        if alternatives and alternatives[0]["apy_pct"] > hook_apy * 1.2:
            suggestion = f"consider_split: 70% hook / 30% {alternatives[0]['protocol']}"

        return {
            "strategy_id": strategy_id,
            "strategy_label": strategy_label,
            "hook_pool_est_apy_pct": hook_apy,
            "alternatives": alternatives[:5],
            "suggestion": suggestion,
            "timestamp": int(time.time()),
        }

    def bridge_status(self) -> Dict[str, Any]:
        """Check X Layer OKB Bridge status.

        Queries chain liveness via eth_blockNumber and reports bridge
        operational status. Uses the OKX bridge API when reachable.
        """
        block = self._get_block_number()
        chain_live = block is not None

        bridge_data = _http_get(OKX_BRIDGE_URL, params={
            "chainId": X_LAYER_CHAIN_ID,
        })

        if bridge_data and bridge_data.get("data"):
            bridge_info = bridge_data["data"]
            return {
                "bridge": "OKB Bridge",
                "chain_live": chain_live,
                "latest_block": block,
                "bridge_status": bridge_info.get("status", "unknown"),
                "source": "live",
                "timestamp": int(time.time()),
            }

        # Simulated fallback
        return {
            "bridge": "OKB Bridge",
            "chain_live": chain_live,
            "latest_block": block,
            "bridge_status": "operational" if chain_live else "degraded",
            "supported_assets": ["OKB", "USDT", "WETH", "USDC"],
            "avg_finality_sec": 3,
            "source": "simulated",
            "timestamp": int(time.time()),
        }

    def get_ecosystem_overview(self) -> Dict[str, Any]:
        """Summary of all integrated protocols and their status."""
        block = self._get_block_number()
        chain_ok = block is not None

        protocols = [
            {
                "name": "Uniswap V4 (Genesis Hook)",
                "type": "DEX / Hook Pool",
                "address": self.hook_address,
                "pool_manager": POOL_MANAGER,
                "status": "active" if chain_ok else "unreachable",
            },
            {
                "name": "OKX DEX Aggregator",
                "type": "DEX Aggregator",
                "endpoint": OKX_DEX_QUOTE_URL,
                "status": "available",
            },
            {
                "name": "OKX DeFi API",
                "type": "Yield / Analytics",
                "endpoint": OKX_DEFI_BASE_URL,
                "status": "available",
            },
            {
                "name": "OKB Bridge",
                "type": "Bridge",
                "status": "operational" if chain_ok else "unknown",
            },
        ]

        for lp in LENDING_PROTOCOLS:
            protocols.append({
                "name": lp["name"],
                "type": lp["type"],
                "status": "simulated",
            })

        return {
            "chain": "X Layer (196)",
            "rpc": self.rpc_url,
            "latest_block": block,
            "chain_healthy": chain_ok,
            "integrated_protocols": protocols,
            "total_integrations": len(protocols),
            "genesis_hook_modules": list(config.AVAILABLE_MODULES.keys()),
            "timestamp": int(time.time()),
        }

    # ── Internal helpers ─────────────────────────────────────────────────

    def _get_hook_pool_quote(self, token_in: str, token_out: str,
                             amount: float) -> Optional[Dict]:
        """Query Uniswap V4 Quoter for a Hook pool price.

        Encodes a quoteExactInputSingle call to the V4 Quoter contract.
        Returns None if the call fails (offline, pool not initialised, etc.).
        """
        quoter = config.UNISWAP_V4.get("quoter", "")
        if not quoter:
            return None

        in_addr = TOKENS.get(token_in, token_in)
        out_addr = TOKENS.get(token_out, token_out)
        decimals = 18 if token_in in ("WOKB", "WETH") else 6
        amount_wei = int(amount * (10 ** decimals))

        # quoteExactInputSingle selector = 0xc6a5026a (simplified ABI encoding)
        # For a real deployment this would use full ABI encoding; here we
        # attempt a raw eth_call and fall back gracefully.
        data = "0xc6a5026a"  # selector only - will revert but proves RPC path
        result = _rpc_call("eth_call", [
            {"to": quoter, "data": data}, "latest",
        ], self.rpc_url)

        if result and result != "0x":
            try:
                out_wei = int(result[:66], 16)
                out_decimals = 18 if token_out in ("WOKB", "WETH") else 6
                amount_out = out_wei / (10 ** out_decimals)
                return {
                    "source": "genesis_hook_pool",
                    "amount_out": round(amount_out, 6),
                    "fee_bps": 30,
                    "simulated": False,
                }
            except (ValueError, IndexError):
                pass
        return None

    def _get_dex_aggregator_quote(self, token_in: str, token_out: str,
                                  amount_wei: int) -> Optional[Dict]:
        """Query OKX DEX Aggregator for a quote."""
        data = _http_get(OKX_DEX_QUOTE_URL, params={
            "chainIndex": X_LAYER_CHAIN_ID,
            "fromTokenAddress": token_in,
            "toTokenAddress": token_out,
            "amount": str(amount_wei),
            "slippage": "0.5",
        })
        if data and data.get("data"):
            quote = data["data"]
            out_amount = float(quote.get("toTokenAmount", 0))
            out_decimals = int(quote.get("toToken", {}).get("decimals", 18))
            return {
                "source": "okx_dex_aggregator",
                "amount_out": round(out_amount / (10 ** out_decimals), 6),
                "fee_bps": 50,
                "router": quote.get("dexRouterList", []),
                "simulated": False,
            }
        return None

    def _get_block_number(self) -> Optional[int]:
        """Fetch latest block number from X Layer RPC."""
        result = _rpc_call("eth_blockNumber", [], self.rpc_url)
        if result:
            try:
                return int(result, 16)
            except (ValueError, TypeError):
                pass
        return None

    def _simulate_lending_rates(self) -> List[Dict]:
        """Generate realistic simulated lending rates for demo."""
        import hashlib
        # Deterministic but date-varying seed for consistent demo output
        seed = int(hashlib.md5(str(int(time.time()) // 3600).encode()).hexdigest()[:8], 16)
        base = (seed % 500) / 100  # 0.00 - 4.99

        return [
            {"name": "LayerBank", "asset": "USDT", "type": "supply",
             "apy_pct": round(base + 3.2, 2)},
            {"name": "LayerBank", "asset": "WETH", "type": "supply",
             "apy_pct": round(base + 1.8, 2)},
            {"name": "LayerBank", "asset": "USDT", "type": "borrow",
             "apy_pct": round(base + 5.5, 2)},
            {"name": "OKX Earn", "asset": "OKB", "type": "staking",
             "apy_pct": round(base + 6.1, 2)},
            {"name": "OKX Earn", "asset": "USDT", "type": "savings",
             "apy_pct": round(base + 4.0, 2)},
            {"name": "Compound (bridged)", "asset": "USDT", "type": "supply",
             "apy_pct": round(base + 2.7, 2)},
            {"name": "Compound (bridged)", "asset": "WETH", "type": "supply",
             "apy_pct": round(base + 1.2, 2)},
        ]


# ── Main entrypoint ──────────────────────────────────────────────────────────

def run_full_scan() -> None:
    """Execute a full cross-protocol scan and print results."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    sep = "=" * 60

    print(f"\n{sep}")
    print("  GENESIS PROTOCOL - Cross-Protocol DeFi Scan")
    print(f"  Chain: X Layer (196) | RPC: {X_LAYER_RPC}")
    print(sep)

    engine = CrossProtocolEngine(dry_run=True)

    # 1. Ecosystem overview
    print(f"\n{'─' * 40}")
    print("  1. Ecosystem Overview")
    print(f"{'─' * 40}")
    overview = engine.get_ecosystem_overview()
    print(f"  Chain healthy : {overview['chain_healthy']}")
    print(f"  Latest block  : {overview['latest_block']}")
    print(f"  Integrations  : {overview['total_integrations']}")
    for p in overview["integrated_protocols"]:
        print(f"    - {p['name']:35s} [{p['type']:18s}] {p['status']}")

    # 2. DEX route comparison
    print(f"\n{'─' * 40}")
    print("  2. DEX Route Comparison")
    print(f"{'─' * 40}")
    for pair in [("WETH", "USDT"), ("WOKB", "USDT")]:
        route = engine.compare_dex_routes(pair[0], pair[1], 1.0)
        hook = route["hook_pool"]
        dex = route["dex_aggregator"]
        sim_tag = " (sim)" if hook.get("simulated") else ""
        print(f"  {route['pair']:12s} | Hook: {hook['amount_out']:.6f}{sim_tag}"
              f" | DEX: {dex['amount_out']:.6f}{sim_tag}"
              f" | Best: {route['recommendation']} (+{route['edge_bps']:.1f} bps)")

    # 3. Arbitrage scan
    print(f"\n{'─' * 40}")
    print("  3. Arbitrage Scanner")
    print(f"{'─' * 40}")
    arb = engine.arbitrage_scanner("WETH/USDT")
    for opp in arb["opportunities"]:
        flag = " <<< PROFITABLE" if opp["profitable"] else ""
        print(f"  amt={opp['amount']:>6.1f} | gross={opp['gross_edge_bps']:>6.2f} bps"
              f" | gas={opp['est_gas_bps']:>8.2f} bps"
              f" | net={opp['net_edge_bps']:>8.2f} bps{flag}")

    # 4. Lending rates
    print(f"\n{'─' * 40}")
    print("  4. Lending / Yield Rates")
    print(f"{'─' * 40}")
    lending = engine.check_lending_rates()
    print(f"  Source: {lending['source']}")
    for p in lending["protocols"]:
        print(f"    {p['name']:25s} | {p.get('asset','?'):5s}"
              f" | {p.get('type',''):8s} | APY {p['apy_pct']:.2f}%")

    # 5. Yield optimiser
    print(f"\n{'─' * 40}")
    print("  5. Yield Optimizer")
    print(f"{'─' * 40}")
    for sid in ["calm_accumulator", "volatile_defender"]:
        opt = engine.yield_optimizer(sid)
        print(f"  Strategy: {opt['strategy_label']}")
        print(f"    Hook APY est : {opt['hook_pool_est_apy_pct']:.2f}%")
        print(f"    Suggestion   : {opt['suggestion']}")
        if opt["alternatives"]:
            best_alt = opt["alternatives"][0]
            print(f"    Best alt     : {best_alt['protocol']}"
                  f" @ {best_alt['apy_pct']:.2f}% "
                  f"(delta {best_alt['vs_hook_delta_pct']:+.2f}%)")

    # 6. Bridge status
    print(f"\n{'─' * 40}")
    print("  6. OKB Bridge Status")
    print(f"{'─' * 40}")
    bridge = engine.bridge_status()
    print(f"  Status : {bridge['bridge_status']}")
    print(f"  Chain  : {'live' if bridge['chain_live'] else 'unreachable'}")
    if bridge.get("supported_assets"):
        print(f"  Assets : {', '.join(bridge['supported_assets'])}")

    print(f"\n{sep}")
    print("  Scan complete.")
    print(f"{sep}\n")


if __name__ == "__main__":
    run_full_scan()
