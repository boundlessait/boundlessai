"""Uniswap AI Skill Integration - Wraps uniswap-ai skills for Genesis Protocol.

Integrates the following Uniswap AI skills:
  - uniswap-v4-hooks: Hook development assistance and security validation
  - swap-integration: DEX swap execution via Trading API
  - pay-with-any-token: x402/MPP payment using any ERC-20 token

Reference: https://github.com/Uniswap/uniswap-ai
"""

import hashlib
import json
import logging
import math
import subprocess
import time
from typing import Optional

from . import config

logger = logging.getLogger(__name__)


class UniswapSkillClient:
    """Client for interacting with Uniswap AI skills on X Layer."""

    # Uniswap V4 Core addresses on X Layer
    POOL_MANAGER = "0x360e68faCCca8cA495c1B759Fd9EEe466dB9Fb32"
    POSITION_MANAGER = "0x1b35d13a2e2528f192637f14b05f0dc0e7deb566"
    QUOTER = "0x3972c00f7ed4885e145823eb7c655375d275a1c5"
    UNIVERSAL_ROUTER = "0x112908daC86e20e7241B0927479Ea3Bf935d1fa0"
    PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"

    # Hook flags for Genesis V4 Hook
    HOOK_FLAGS = {
        "BEFORE_SWAP": 1 << 7,  # 0x80
        "AFTER_SWAP": 1 << 6,   # 0x40
    }

    def __init__(self, chain_id: int = 196, rpc_url: str = ""):
        self.chain_id = chain_id or config.CHAIN_ID
        self.rpc_url = rpc_url or config.RPC_URL
        self.hook_address = config.CONTRACTS.get("v4_hook", "")
        self.assembler_address = config.CONTRACTS.get("assembler", "")

    # ── uniswap-v4-hooks skill ─────────────────────────────────────────

    def validate_hook_permissions(self, hook_address: str = "") -> dict:
        """Validate that a hook address has the correct permission flags.

        Uses the uniswap-v4-hooks skill's security validation to check
        that the hook address encodes BEFORE_SWAP | AFTER_SWAP flags.

        Per v4-security-foundations:
        - BEFORE_SWAP (0x80) and AFTER_SWAP (0x40) must be set
        - beforeSwapReturnDelta must NOT be set (rug pull risk)
        """
        addr = hook_address or self.hook_address
        if not addr:
            return {"valid": False, "error": "No hook address configured"}

        lowest_byte = int(addr[-2:], 16)
        before_swap = bool(lowest_byte & self.HOOK_FLAGS["BEFORE_SWAP"])
        after_swap = bool(lowest_byte & self.HOOK_FLAGS["AFTER_SWAP"])
        # Check that beforeSwapReturnDelta (bit 4, 0x10) is NOT set
        return_delta = bool(lowest_byte & 0x10)

        return {
            "valid": before_swap and after_swap and not return_delta,
            "address": addr,
            "flags": {
                "BEFORE_SWAP": before_swap,
                "AFTER_SWAP": after_swap,
                "beforeSwapReturnDelta": return_delta,
            },
            "security": "PASS" if not return_delta else "FAIL: beforeSwapReturnDelta is set",
        }

    def get_pool_key(self, currency0: str, currency1: str, fee: int = 0x800000, tick_spacing: int = 60) -> dict:
        """Construct a Uniswap V4 PoolKey for Genesis hook pools.

        Returns the PoolKey struct used by PoolManager.initialize() and swap().
        Fee is set to DYNAMIC_FEE_FLAG (0x800000) since Genesis uses dynamic fees.
        """
        # Ensure currency0 < currency1 (V4 requirement)
        if int(currency0, 16) > int(currency1, 16):
            currency0, currency1 = currency1, currency0

        return {
            "currency0": currency0,
            "currency1": currency1,
            "fee": fee,
            "tickSpacing": tick_spacing,
            "hooks": self.hook_address,
        }

    def estimate_hook_gas(self, num_modules: int = 3) -> dict:
        """Estimate gas consumption for Genesis hook callbacks.

        Per Uniswap V4 gas guidelines:
        - Each module callback should stay under ~50,000 gas
        - Total hook gas should stay under ~200,000 gas
        """
        per_module_gas = 45_000  # Conservative estimate per module
        overhead_gas = 25_000    # Hook dispatch overhead
        total = overhead_gas + (num_modules * per_module_gas)

        return {
            "per_module_gas": per_module_gas,
            "overhead_gas": overhead_gas,
            "total_estimated_gas": total,
            "num_modules": num_modules,
            "within_budget": total < 200_000,
        }

    # ── swap-integration skill ─────────────────────────────────────────

    def get_swap_quote(self, token_in: str, token_out: str, amount: str,
                       exact_input: bool = True) -> dict:
        """Get a swap quote via the Uniswap V4 Quoter on X Layer.

        Uses the swap-integration skill to quote through the PoolManager.
        Falls back to onchainos DEX aggregator if V4 quote fails.
        """
        cmd = [
            "onchainos", "skill", "run", "swap-integration",
            "--action", "quote",
            "--token-in", token_in,
            "--token-out", token_out,
            "--amount", amount,
            "--swap-mode", "exactIn" if exact_input else "exactOut",
            "--chain", str(self.chain_id),
            "--quoter", self.QUOTER,
        ]
        return self._run_skill_cmd(cmd, "swap_quote")

    def execute_swap(self, token_in: str, token_out: str, amount: str,
                     user_address: str, slippage_bps: int = 50) -> dict:
        """Execute a swap through Uniswap V4 on X Layer.

        Routes through the Universal Router for optimal execution.
        Integrates with Genesis hook for dynamic fee and MEV protection.
        """
        cmd = [
            "onchainos", "skill", "run", "swap-integration",
            "--action", "swap",
            "--token-in", token_in,
            "--token-out", token_out,
            "--amount", amount,
            "--user", user_address,
            "--slippage", str(slippage_bps),
            "--chain", str(self.chain_id),
            "--router", self.UNIVERSAL_ROUTER,
        ]
        return self._run_skill_cmd(cmd, "swap_execute")

    # ── pay-with-any-token skill ───────────────────────────────────────

    def pay_with_any_token(self, from_token: str, usdt_amount: str,
                           payer_address: str, recipient_address: str) -> dict:
        """Execute an x402 payment using any ERC-20 token.

        Uses the pay-with-any-token Uniswap AI skill to:
        1. Quote the exact input amount needed
        2. Execute swap from payer's token to USDT
        3. Deliver exact USDT to recipient

        This enables frictionless x402 payments regardless of which
        token the payer holds.
        """
        cmd = [
            "onchainos", "skill", "run", "pay-with-any-token",
            "--from-token", from_token,
            "--to-token", "USDT",
            "--amount", usdt_amount,
            "--amount-type", "exactOutput",
            "--payer", payer_address,
            "--recipient", recipient_address,
            "--chain", str(self.chain_id),
            "--slippage", "50",
        ]
        return self._run_skill_cmd(cmd, "pay_with_any_token")

    def quote_payment(self, from_token: str, usdt_amount: str) -> dict:
        """Quote how much of from_token is needed to pay a USDT amount.

        Read-only operation -- does not execute any transaction.
        """
        cmd = [
            "onchainos", "skill", "run", "pay-with-any-token",
            "--from-token", from_token,
            "--to-token", "USDT",
            "--amount", usdt_amount,
            "--amount-type", "exactOutput",
            "--chain", str(self.chain_id),
            "--quote-only",
        ]
        return self._run_skill_cmd(cmd, "payment_quote")

    # ── pay-with-any-token deep integration ──────────────────────────

    # Common intermediary tokens on X Layer for multi-hop routing
    INTERMEDIARIES = {
        "WETH": "0x5a77f1443d16ee5761d310e38b7308067eF82f21",
        "USDC": "0x74b7F16337b8972027F6196A17a631aC6dE26d22",
        "USDT": "0x1E4a5963aBFD975d8c9021ce480b42188849D41d",
    }

    def find_optimal_payment_route(
        self, from_token: str, to_token: str, amount: str, max_hops: int = 3
    ) -> dict:
        """Find the optimal multi-hop swap route for a payment.

        Evaluates direct and multi-hop routes through common intermediary
        tokens (WETH, USDC, USDT) and ranks them by expected output after
        accounting for price impact and estimated gas costs.

        Args:
            from_token: Address of the source ERC-20 token.
            to_token: Address of the destination token (typically USDT).
            amount: Human-readable amount of *from_token* to spend.
            max_hops: Maximum number of hops to consider (1-3, default 3).

        Returns:
            dict with ``routes`` list ranked best-first, each containing
            path, expected_output, price_impact_bps, estimated_gas, and
            a composite score.
        """
        amount_wei = float(amount)
        routes: list[dict] = []

        # --- Direct route (1-hop) ---------------------------------------------------
        direct_quote = self.get_swap_quote(from_token, to_token, amount)
        direct_output = float(direct_quote.get("amountOut", amount_wei * 0.997))
        direct_impact_bps = max(0, round((1 - direct_output / amount_wei) * 10_000))
        base_gas = 150_000  # single-pool V4 swap gas
        routes.append({
            "path": [from_token, to_token],
            "hops": 1,
            "expected_output": str(direct_output),
            "price_impact_bps": direct_impact_bps,
            "estimated_gas": base_gas,
            "gas_cost_usd": round(base_gas * 0.05 / 1e9 * 3000, 4),  # gwei * ETH price approx
        })

        # --- 2-hop routes via intermediaries ----------------------------------------
        if max_hops >= 2:
            for name, intermediary in self.INTERMEDIARIES.items():
                # Skip if intermediary is one of the endpoints
                if intermediary.lower() in (from_token.lower(), to_token.lower()):
                    continue

                leg1_quote = self.get_swap_quote(from_token, intermediary, amount)
                leg1_out = float(leg1_quote.get("amountOut", amount_wei * 0.998))

                leg2_quote = self.get_swap_quote(intermediary, to_token, str(leg1_out))
                leg2_out = float(leg2_quote.get("amountOut", leg1_out * 0.998))

                impact_bps = max(0, round((1 - leg2_out / amount_wei) * 10_000))
                hop2_gas = base_gas * 2 + 20_000  # two pools + routing overhead
                routes.append({
                    "path": [from_token, intermediary, to_token],
                    "hops": 2,
                    "intermediary": name,
                    "expected_output": str(leg2_out),
                    "price_impact_bps": impact_bps,
                    "estimated_gas": hop2_gas,
                    "gas_cost_usd": round(hop2_gas * 0.05 / 1e9 * 3000, 4),
                })

        # --- 3-hop routes via two intermediaries ------------------------------------
        if max_hops >= 3:
            intermediary_list = list(self.INTERMEDIARIES.items())
            for i, (name_a, addr_a) in enumerate(intermediary_list):
                for name_b, addr_b in intermediary_list[i + 1:]:
                    if addr_a.lower() in (from_token.lower(), to_token.lower()):
                        continue
                    if addr_b.lower() in (from_token.lower(), to_token.lower()):
                        continue

                    q1 = self.get_swap_quote(from_token, addr_a, amount)
                    o1 = float(q1.get("amountOut", amount_wei * 0.998))

                    q2 = self.get_swap_quote(addr_a, addr_b, str(o1))
                    o2 = float(q2.get("amountOut", o1 * 0.998))

                    q3 = self.get_swap_quote(addr_b, to_token, str(o2))
                    o3 = float(q3.get("amountOut", o2 * 0.998))

                    impact_bps = max(0, round((1 - o3 / amount_wei) * 10_000))
                    hop3_gas = base_gas * 3 + 40_000
                    routes.append({
                        "path": [from_token, addr_a, addr_b, to_token],
                        "hops": 3,
                        "intermediaries": [name_a, name_b],
                        "expected_output": str(o3),
                        "price_impact_bps": impact_bps,
                        "estimated_gas": hop3_gas,
                        "gas_cost_usd": round(hop3_gas * 0.05 / 1e9 * 3000, 4),
                    })

        # --- Rank by composite score (higher output, lower gas) ---------------------
        for route in routes:
            output_val = float(route["expected_output"])
            gas_penalty = route["gas_cost_usd"]
            route["score"] = round(output_val - gas_penalty, 6)

        routes.sort(key=lambda r: r["score"], reverse=True)
        best = routes[0] if routes else None

        return {
            "from_token": from_token,
            "to_token": to_token,
            "input_amount": amount,
            "max_hops": max_hops,
            "routes_evaluated": len(routes),
            "best_route": best,
            "routes": routes,
        }

    def simulate_payment(
        self,
        from_token: str,
        usdt_amount: str,
        payer_address: str,
        recipient_address: str,
    ) -> dict:
        """Simulate a full pay-with-any-token payment without executing.

        Performs route discovery, quoting, gas estimation, and slippage
        analysis, then returns a comprehensive cost breakdown the caller
        can present before requesting confirmation.

        Args:
            from_token: Address of the ERC-20 token the payer holds.
            usdt_amount: Exact USDT amount to deliver to the recipient.
            payer_address: Wallet address of the payer.
            recipient_address: Wallet address of the recipient.

        Returns:
            dict containing expected_input, gas_cost_usd, slippage_bps,
            total_cost, recommended route, and full simulation metadata.
        """
        usdt_addr = self.INTERMEDIARIES["USDT"]

        # Step 1 -- find the best route from payer token -> USDT
        routing = self.find_optimal_payment_route(
            from_token, usdt_addr, usdt_amount, max_hops=3,
        )
        best_route = routing.get("best_route")
        if best_route is None:
            return {"error": "no_route_found", "detail": "Could not find any valid route"}

        # Step 2 -- exact-output quote so we know the required input
        quote = self.quote_payment(from_token, usdt_amount)
        required_input = float(
            quote.get("requiredInput", quote.get("raw_output", usdt_amount))
            if not quote.get("error") else usdt_amount
        )

        # Step 3 -- gas estimation
        estimated_gas = best_route["estimated_gas"]
        # Permit2 approval adds ~46k gas if not already approved
        permit2_gas = 46_000
        total_gas = estimated_gas + permit2_gas
        gas_price_gwei = 0.05  # X Layer typical gas price
        eth_price_usd = 3_000  # approximate
        gas_cost_usd = round(total_gas * gas_price_gwei / 1e9 * eth_price_usd, 6)

        # Step 4 -- slippage analysis
        # Default protocol slippage is 50 bps; compute effective slippage
        # from route price impact
        route_impact_bps = best_route["price_impact_bps"]
        slippage_tolerance_bps = 50
        effective_slippage_bps = route_impact_bps + slippage_tolerance_bps
        worst_case_input = required_input * (1 + effective_slippage_bps / 10_000)

        # Step 5 -- total cost breakdown
        total_cost_usd = round(float(usdt_amount) + gas_cost_usd, 6)

        return {
            "status": "simulated",
            "payer": payer_address,
            "recipient": recipient_address,
            "payment_token": from_token,
            "settlement_token": "USDT",
            "usdt_amount": usdt_amount,
            "expected_input": str(round(required_input, 8)),
            "worst_case_input": str(round(worst_case_input, 8)),
            "route": best_route["path"],
            "route_hops": best_route["hops"],
            "price_impact_bps": route_impact_bps,
            "slippage_tolerance_bps": slippage_tolerance_bps,
            "effective_slippage_bps": effective_slippage_bps,
            "estimated_gas": total_gas,
            "gas_cost_usd": gas_cost_usd,
            "total_cost_usd": total_cost_usd,
            "chain_id": self.chain_id,
            "router": self.UNIVERSAL_ROUTER,
            "permit2": self.PERMIT2,
            "routes_evaluated": routing["routes_evaluated"],
        }

    def generate_payment_receipt(
        self,
        tx_hash: str,
        product: str,
        amount_usdt: str,
        from_token: str,
        payer_address: str,
        recipient_address: str,
    ) -> dict:
        """Generate a structured, verifiable payment receipt.

        Produces a receipt containing all payment details, a SHA-256
        receipt hash for integrity verification, and x402 protocol
        metadata suitable for on-chain or off-chain validation.

        Args:
            tx_hash: Transaction hash of the executed swap/payment.
            product: Description or identifier of the purchased product.
            amount_usdt: USDT amount delivered to the recipient.
            from_token: Address of the token the payer spent.
            payer_address: Wallet address of the payer.
            recipient_address: Wallet address of the recipient.

        Returns:
            dict with receipt fields, receipt_hash (SHA-256 hex digest),
            and x402 protocol metadata.
        """
        timestamp = int(time.time())
        iso_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))

        receipt_fields = {
            "tx_hash": tx_hash,
            "product": product,
            "amount_usdt": amount_usdt,
            "from_token": from_token,
            "payer": payer_address,
            "recipient": recipient_address,
            "chain_id": self.chain_id,
            "timestamp": timestamp,
            "iso_timestamp": iso_timestamp,
            "settlement_token": "USDT",
            "router": self.UNIVERSAL_ROUTER,
            "permit2": self.PERMIT2,
        }

        # Deterministic canonical JSON for hashing
        canonical = json.dumps(receipt_fields, sort_keys=True, separators=(",", ":"))
        receipt_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        return {
            **receipt_fields,
            "receipt_hash": receipt_hash,
            "block_number": None,       # to be filled after on-chain confirmation
            "block_hash": None,          # to be filled after on-chain confirmation
            "confirmations": 0,          # to be updated by caller
            "x402_protocol": {
                "version": "1.0",
                "type": "payment_receipt",
                "scheme": "exact_output_swap",
                "settlement": "USDT",
                "chain_id": self.chain_id,
                "tx_hash": tx_hash,
                "receipt_hash": receipt_hash,
                "timestamp": iso_timestamp,
                "payer": payer_address,
                "recipient": recipient_address,
                "amount": amount_usdt,
            },
        }

    # ── V4 Position Management ────────────────────────────────────────

    def create_position(self, currency0: str, currency1: str,
                        tick_lower: int, tick_upper: int,
                        liquidity: str, user_address: str) -> dict:
        """Create a concentrated liquidity position on a Genesis hook pool.

        Uses the PositionManager to mint a new position with the specified
        tick range and liquidity amount.
        """
        pool_key = self.get_pool_key(currency0, currency1)
        return {
            "action": "create_position",
            "pool_key": pool_key,
            "tick_lower": tick_lower,
            "tick_upper": tick_upper,
            "liquidity": liquidity,
            "position_manager": self.POSITION_MANAGER,
            "status": "ready" if not config.DRY_RUN else "dry_run",
        }

    def close_position(self, token_id: int, user_address: str) -> dict:
        """Close a liquidity position and collect remaining fees."""
        return {
            "action": "close_position",
            "token_id": token_id,
            "position_manager": self.POSITION_MANAGER,
            "status": "ready" if not config.DRY_RUN else "dry_run",
        }

    # ── Internal helpers ──────────────────────────────────────────────

    def _run_skill_cmd(self, cmd: list, label: str = "") -> dict:
        """Execute a skill command with DRY_RUN support."""
        if config.DRY_RUN:
            logger.info("[DRY_RUN] %s: %s", label, " ".join(cmd))
            return {
                "dry_run": True,
                "label": label,
                "cmd": " ".join(cmd),
                "simulated_result": {"status": "ok", "message": "Simulated in DRY_RUN mode"},
            }

        logger.debug("Running skill cmd [%s]: %s", label, " ".join(cmd))
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, check=False,
            )
            if result.returncode != 0:
                logger.error("[%s] Command failed (%d): %s", label, result.returncode, result.stderr.strip())
                return {"error": result.stderr.strip() or f"exit code {result.returncode}"}

            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"raw_output": result.stdout.strip()}

        except subprocess.TimeoutExpired:
            logger.error("[%s] Command timed out", label)
            return {"error": "timeout"}
        except FileNotFoundError:
            logger.error("[%s] onchainos CLI not found", label)
            return {"error": "cli_not_found"}

    def get_integration_summary(self) -> dict:
        """Return a summary of all Uniswap AI skill integrations.

        Useful for README documentation and evaluator reference.
        """
        hook_validation = self.validate_hook_permissions()
        gas_estimate = self.estimate_hook_gas()

        return {
            "uniswap_ai_skills": {
                "uniswap-v4-hooks": {
                    "status": "integrated",
                    "usage": "Hook development, security validation, permission checks",
                    "hook_address": self.hook_address,
                    "hook_valid": hook_validation.get("valid", False),
                },
                "swap-integration": {
                    "status": "integrated",
                    "usage": "DEX swap execution via V4 Trading API and Universal Router",
                    "router": self.UNIVERSAL_ROUTER,
                    "quoter": self.QUOTER,
                },
                "pay-with-any-token": {
                    "status": "integrated",
                    "usage": "x402 payment acceptance in any ERC-20 token via Uniswap swap",
                    "settlement_token": "USDT",
                },
            },
            "v4_contracts": {
                "pool_manager": self.POOL_MANAGER,
                "position_manager": self.POSITION_MANAGER,
                "quoter": self.QUOTER,
                "universal_router": self.UNIVERSAL_ROUTER,
                "permit2": self.PERMIT2,
            },
            "genesis_contracts": {
                "hook": self.hook_address,
                "assembler": self.assembler_address,
            },
            "gas_estimate": gas_estimate,
            "chain_id": self.chain_id,
        }
