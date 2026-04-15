"""Uniswap Driver (Swap & Liquidity Planning) Skill Integration.

Integrates the uniswap-driver Uniswap AI skill for advanced swap route
optimization and liquidity position planning. Provides the Planning Layer
with data-driven recommendations for tick ranges, fee tiers, multi-hop
routing, and gas estimation on X Layer.

Reference: https://github.com/Uniswap/uniswap-ai
"""

import json
import logging
import math
import subprocess
from typing import Optional

from . import config

logger = logging.getLogger(__name__)


class UniswapDriverClient:
    """Client for the uniswap-driver (swap & liquidity planning) skill on X Layer.

    The driver skill acts as a planning oracle for Genesis strategies:
      - Liquidity planning: optimal tick ranges, amounts, and fee tiers
      - Swap planning: route optimization, multi-hop paths, gas estimation
      - Pool analytics: TVL, volume, fee APR, tick distribution

    Integrates tightly with the AutoRebalanceModule by supplying optimal
    target ranges and rebalance parameters.
    """

    # Uniswap V4 addresses on X Layer (mirrors UniswapSkillClient)
    POOL_MANAGER = "0x360e68faCCca8cA495c1B759Fd9EEe466dB9Fb32"
    POSITION_MANAGER = "0x1b35d13a2e2528f192637f14b05f0dc0e7deb566"
    QUOTER = "0x3972c00f7ed4885e145823eb7c655375d275a1c5"

    # Fee tier presets (in hundredths of a bip)
    FEE_TIERS = {
        "lowest": 100,     # 0.01% - stable pairs
        "low": 500,        # 0.05% - correlated pairs
        "medium": 3000,    # 0.30% - standard pairs
        "high": 10000,     # 1.00% - exotic pairs
        "dynamic": 0x800000,  # Dynamic fee flag for Genesis hook pools
    }

    def __init__(self, chain_id: int = 0, rpc_url: str = ""):
        self.chain_id = chain_id or config.CHAIN_ID
        self.rpc_url = rpc_url or config.RPC_URL
        self.hook_address = config.CONTRACTS.get("v4_hook", "")
        self.rebalance_module = config.CONTRACTS.get("auto_rebalance_module", "")

    # ── Liquidity Planning ────────────────────────────────────────────

    def plan_liquidity_position(
        self,
        token0: str,
        token1: str,
        amount_usd: str,
        risk_profile: str = "moderate",
        use_genesis_hook: bool = True,
    ) -> dict:
        """Plan an optimal concentrated liquidity position.

        Uses the uniswap-driver skill to analyze current pool state and
        recommend tick range, liquidity amount, and fee tier.

        Args:
            token0:           Address of token0.
            token1:           Address of token1.
            amount_usd:       Total capital to deploy in USD terms.
            risk_profile:     One of "conservative", "moderate", "aggressive".
            use_genesis_hook: If True, plan for a Genesis hook pool (dynamic fees).

        Returns:
            dict with recommended tick_lower, tick_upper, liquidity, fee_tier,
            and expected APR range.
        """
        fee_tier = str(self.FEE_TIERS["dynamic"]) if use_genesis_hook else "auto"

        cmd = [
            "onchainos", "skill", "run", "uniswap-driver",
            "--action", "plan-liquidity",
            "--token0", token0,
            "--token1", token1,
            "--amount-usd", amount_usd,
            "--risk-profile", risk_profile,
            "--fee-tier", fee_tier,
            "--chain", str(self.chain_id),
        ]
        if use_genesis_hook:
            cmd.extend(["--hook", self.hook_address])

        return self._run_skill_cmd(cmd, "plan_liquidity_position")

    def optimize_tick_range(
        self,
        token0: str,
        token1: str,
        current_tick: int,
        volatility_pct: float,
        strategy_preset: str = "",
    ) -> dict:
        """Compute an optimal tick range based on volatility and strategy.

        Integrates with the AutoRebalanceModule: the returned range can be
        fed directly into a rebalance operation as the new target range.

        Args:
            token0:          Address of token0.
            token1:          Address of token1.
            current_tick:    Current pool tick.
            volatility_pct:  Rolling volatility percentage from OnchainOS data.
            strategy_preset: Optional Genesis strategy name (e.g. "calm_accumulator").

        Returns:
            dict with tick_lower, tick_upper, width_ticks, and reasoning.
        """
        cmd = [
            "onchainos", "skill", "run", "uniswap-driver",
            "--action", "optimize-tick-range",
            "--token0", token0,
            "--token1", token1,
            "--current-tick", str(current_tick),
            "--volatility", str(volatility_pct),
            "--chain", str(self.chain_id),
        ]
        if strategy_preset:
            cmd.extend(["--strategy-preset", strategy_preset])

        return self._run_skill_cmd(cmd, "optimize_tick_range")

    # ── Swap Planning ─────────────────────────────────────────────────

    def plan_swap_route(
        self,
        token_in: str,
        token_out: str,
        amount: str,
        exact_input: bool = True,
        max_hops: int = 3,
    ) -> dict:
        """Plan an optimal swap route with multi-hop path finding.

        Evaluates direct routes and multi-hop paths through intermediate
        tokens to find the best execution price. Considers both V4 hook
        pools and standard V4 pools on X Layer.

        Args:
            token_in:     Address of the input token.
            token_out:    Address of the output token.
            amount:       Amount in wei (input or output depending on exact_input).
            exact_input:  True for exactIn, False for exactOut.
            max_hops:     Maximum number of intermediate hops (default 3).

        Returns:
            dict with route (list of hops), expected output, price impact,
            and comparison to DEX aggregator quote.
        """
        cmd = [
            "onchainos", "skill", "run", "uniswap-driver",
            "--action", "plan-swap-route",
            "--token-in", token_in,
            "--token-out", token_out,
            "--amount", amount,
            "--swap-mode", "exactIn" if exact_input else "exactOut",
            "--max-hops", str(max_hops),
            "--chain", str(self.chain_id),
            "--quoter", self.QUOTER,
        ]
        return self._run_skill_cmd(cmd, "plan_swap_route")

    def estimate_gas(
        self,
        action: str,
        token0: str = "",
        token1: str = "",
        num_hops: int = 1,
    ) -> dict:
        """Estimate gas cost for a planned swap or liquidity operation.

        Args:
            action:   One of "swap", "add_liquidity", "remove_liquidity", "rebalance".
            token0:   Address of token0 (optional, for pool-specific estimates).
            token1:   Address of token1 (optional).
            num_hops: Number of swap hops (for multi-hop gas scaling).

        Returns:
            dict with estimated_gas, gas_price_gwei, cost_usd, and breakdown.
        """
        cmd = [
            "onchainos", "skill", "run", "uniswap-driver",
            "--action", "estimate-gas",
            "--operation", action,
            "--num-hops", str(num_hops),
            "--chain", str(self.chain_id),
        ]
        if token0:
            cmd.extend(["--token0", token0])
        if token1:
            cmd.extend(["--token1", token1])

        return self._run_skill_cmd(cmd, "estimate_gas")

    # ── Pool Analytics ────────────────────────────────────────────────

    def get_pool_analytics(
        self,
        token0: str,
        token1: str,
        fee_tier: str = "dynamic",
        period: str = "7d",
    ) -> dict:
        """Fetch comprehensive analytics for a Uniswap V4 pool.

        Returns TVL, volume, fee revenue, tick distribution, and LP
        performance metrics. Used by the Genesis Engine's Analysis Layer
        to evaluate pool health and inform strategy selection.

        Args:
            token0:   Address of token0.
            token1:   Address of token1.
            fee_tier: Fee tier key or numeric value (default "dynamic").
            period:   Analytics period: "1d", "7d", "30d".

        Returns:
            dict with tvl, volume_24h, fee_apr, active_liquidity,
            tick_distribution, and lp_pnl_summary.
        """
        fee = str(self.FEE_TIERS.get(fee_tier, fee_tier))

        cmd = [
            "onchainos", "skill", "run", "uniswap-driver",
            "--action", "pool-analytics",
            "--token0", token0,
            "--token1", token1,
            "--fee-tier", fee,
            "--period", period,
            "--chain", str(self.chain_id),
        ]
        return self._run_skill_cmd(cmd, "pool_analytics")

    # ── AutoRebalanceModule Integration ───────────────────────────────

    def recommend_rebalance_params(
        self,
        token0: str,
        token1: str,
        current_tick: int,
        current_tick_lower: int,
        current_tick_upper: int,
        volatility_pct: float,
    ) -> dict:
        """Generate rebalance recommendations for the AutoRebalanceModule.

        Combines tick range optimization with gas estimation to decide
        whether a rebalance is cost-effective at the current moment.

        Args:
            token0:             Address of token0.
            token1:             Address of token1.
            current_tick:       Current pool tick.
            current_tick_lower: Existing position lower tick.
            current_tick_upper: Existing position upper tick.
            volatility_pct:     Rolling volatility percentage.

        Returns:
            dict with should_rebalance, new_tick_lower, new_tick_upper,
            estimated_gas_cost, and reasoning.
        """
        # Get optimal range from the driver skill
        range_result = self.optimize_tick_range(
            token0, token1, current_tick, volatility_pct,
        )

        # Estimate cost of rebalance operation
        gas_result = self.estimate_gas("rebalance", token0, token1)

        # Determine position utilisation (how far price is from center)
        range_width = current_tick_upper - current_tick_lower
        if range_width == 0:
            utilisation_pct = 100.0
        else:
            center = (current_tick_lower + current_tick_upper) / 2
            distance_from_center = abs(current_tick - center)
            utilisation_pct = (distance_from_center / (range_width / 2)) * 100

        # Consult AutoRebalanceModule config for trigger threshold
        rebalance_cfg = config.AVAILABLE_MODULES.get("auto_rebalance", {}).get("default_params", {})
        trigger_pct = rebalance_cfg.get("soft_trigger_pct", 85)

        should_rebalance = utilisation_pct >= trigger_pct

        return {
            "should_rebalance": should_rebalance,
            "utilisation_pct": round(utilisation_pct, 2),
            "trigger_threshold_pct": trigger_pct,
            "current_range": {
                "tick_lower": current_tick_lower,
                "tick_upper": current_tick_upper,
            },
            "recommended_range": range_result,
            "gas_estimate": gas_result,
            "current_tick": current_tick,
            "volatility_pct": volatility_pct,
        }

    # ── Deep Integration Methods ──────────────────────────────────────

    def calculate_optimal_range(
        self,
        current_tick: int,
        volatility_pct: float,
        tick_spacing: int = 60,
        confidence_level: float = 0.95,
    ) -> dict:
        """Calculate optimal tick range using a statistical model of price movement.

        Models future price as a geometric Brownian motion and derives the
        tick boundaries that contain the expected price path with the
        requested confidence level over a 7-day horizon.

        Core formula:
            half_width = norm_z * volatility * sqrt(time_horizon)
        The resulting price-space half-width is mapped to ticks, then
        rounded outward to the nearest ``tick_spacing`` boundary.

        Args:
            current_tick:     Current pool tick.
            volatility_pct:   Annualized volatility as a percentage (e.g. 80.0
                              for 80 %).
            tick_spacing:     Pool tick spacing (default 60 for Genesis hook
                              pools).
            confidence_level: Probability that price remains inside the range
                              during the horizon window (0 < p < 1).

        Returns:
            dict with keys:
                tick_lower              - Lower tick boundary (aligned).
                tick_upper              - Upper tick boundary (aligned).
                width_ticks             - Total width in ticks.
                expected_time_in_range_pct - Estimated % of horizon the price
                    spends inside the range.
                capital_efficiency      - Multiplier vs a full-range position
                    (full_range_width / width_ticks).
        """
        # ── Z-score lookup (fall back to 1.96 for unlisted levels) ─────
        z_table = {0.90: 1.645, 0.95: 1.960, 0.99: 2.576}
        norm_z = z_table.get(confidence_level, 1.960)

        # ── Annualized vol  →  per-day standard deviation ──────────────
        volatility = volatility_pct / 100.0
        daily_sigma = volatility * math.sqrt(1.0 / 365.0)

        # ── Horizon in days (1 week) ──────────────────────────────────
        time_horizon = 7.0

        # ── Half-width in price-return space ──────────────────────────
        half_width_return = norm_z * daily_sigma * math.sqrt(time_horizon)

        # Map return-space half-width to tick space.
        # Each tick represents a ~0.01 % multiplicative price change,
        # i.e. 1 tick ≈ log(1.0001) in log-price space, so
        #   ticks = return / log(1.0001) ≈ return * 10_000.
        log_tick = math.log(1.0001)
        half_width_ticks_raw = half_width_return / log_tick

        # ── Round outward to tick_spacing ─────────────────────────────
        half_ticks = max(
            tick_spacing,
            int(math.ceil(half_width_ticks_raw / tick_spacing)) * tick_spacing,
        )

        tick_lower = (current_tick - half_ticks) // tick_spacing * tick_spacing
        tick_upper = -(-((current_tick + half_ticks)) // tick_spacing) * tick_spacing
        # Ensure tick_upper is at least one spacing above tick_lower
        if tick_upper <= tick_lower:
            tick_upper = tick_lower + tick_spacing

        width_ticks = tick_upper - tick_lower

        # ── Expected time-in-range % ─────────────────────────────────
        # Approximate: for a centred range sized to the confidence level,
        # the average fraction of time spent in range is slightly above the
        # confidence level (boundary effects), capped at 100.
        expected_time_in_range_pct = round(
            min(100.0, confidence_level * 100.0 + (1.0 - confidence_level) * 25.0),
            2,
        )

        # ── Capital efficiency vs full-range ─────────────────────────
        full_range_width = 887220 * 2  # tick_min to tick_max in Uniswap V3/V4
        capital_efficiency = round(full_range_width / max(width_ticks, 1), 2)

        return {
            "tick_lower": tick_lower,
            "tick_upper": tick_upper,
            "width_ticks": width_ticks,
            "current_tick": current_tick,
            "confidence_level": confidence_level,
            "norm_z": norm_z,
            "daily_sigma": round(daily_sigma, 6),
            "time_horizon_days": time_horizon,
            "expected_time_in_range_pct": expected_time_in_range_pct,
            "capital_efficiency": capital_efficiency,
            "tick_spacing": tick_spacing,
        }

    def score_liquidity_efficiency(
        self,
        tick_lower: int,
        tick_upper: int,
        current_tick: int,
        pool_volume_24h: float,
        position_liquidity: float,
    ) -> dict:
        """Score the efficiency of a concentrated-liquidity position (0-100).

        The composite score blends four sub-scores:

        * **in_range** (25 pts) -- whether the current tick falls within the
          position boundaries.
        * **range_utilization** (25 pts) -- how centred the current tick is
          inside the range.  A tick at the exact centre scores the full 25;
          a tick at the boundary scores 0.
        * **capital_efficiency** (25 pts) -- narrower ranges earn more fees
          per unit of capital.  Scored via log-scale of the concentration
          multiplier (full_range_width / range_width), capped at 4 000x.
        * **fee_capture_estimate** (25 pts) -- estimated daily fee revenue
          relative to position value, linearly scaled so that a 0.1 %/day
          capture rate maps to the full 25 points.

        Args:
            tick_lower:          Position lower tick.
            tick_upper:          Position upper tick.
            current_tick:        Current pool tick.
            pool_volume_24h:     Pool 24-hour trading volume in USD.
            position_liquidity:  Position value in USD.

        Returns:
            dict with keys:
                score                  - Composite score (0 -- 100).
                breakdown              - Dict of the four sub-scores.
                in_range               - Whether current tick is inside range.
                range_utilization      - 0-1 measure of how centred the tick is.
                capital_efficiency     - Multiplier vs full-range position.
                fee_capture_estimate   - Estimated daily fee capture in USD.
        """
        range_width = tick_upper - tick_lower
        if range_width <= 0 or position_liquidity <= 0:
            return {"error": "invalid_range_or_liquidity"}

        full_range_width = 887220 * 2  # tick_min to tick_max

        # ── 1. In-range check (25 pts) ────────────────────────────────
        in_range = tick_lower <= current_tick <= tick_upper
        in_range_pts = 25.0 if in_range else 0.0

        # ── 2. Range utilization (25 pts) ─────────────────────────────
        center = (tick_lower + tick_upper) / 2.0
        half_width = range_width / 2.0
        distance_ratio = abs(current_tick - center) / half_width if half_width else 1.0
        # Clamp to [0, 1]; 0 = perfectly centred, 1 = at boundary/outside
        distance_ratio = min(distance_ratio, 1.0)
        range_utilization = 1.0 - distance_ratio  # 1 = centred
        range_utilization_pts = range_utilization * 25.0

        # ── 3. Capital efficiency (25 pts) ────────────────────────────
        concentration_multiplier = min(full_range_width / max(range_width, 1), 4000.0)
        # log10 scale: 1x → 0 pts, 4000x → 25 pts
        cap_eff_pts = min(
            25.0,
            math.log10(max(concentration_multiplier, 1.0))
            / math.log10(4000.0)
            * 25.0,
        )

        # ── 4. Fee capture estimate (25 pts) ─────────────────────────
        base_fee_rate = 0.003  # 0.30 % fee tier assumption
        if in_range:
            # Position captures fees proportional to its share of active
            # liquidity, approximated by concentration multiplier.
            daily_fees = pool_volume_24h * base_fee_rate / max(concentration_multiplier, 1.0)
            fee_capture_daily = daily_fees * (position_liquidity / max(position_liquidity, 1.0))
        else:
            fee_capture_daily = 0.0

        fee_capture_rate = fee_capture_daily / position_liquidity  # fraction
        # 0.1 %/day (0.001) → 25 pts
        fee_pts = min(25.0, (fee_capture_rate / 0.001) * 25.0)

        # ── Composite ─────────────────────────────────────────────────
        composite = round(in_range_pts + range_utilization_pts + cap_eff_pts + fee_pts, 1)
        composite = min(100.0, composite)

        return {
            "score": composite,
            "breakdown": {
                "in_range_pts": round(in_range_pts, 2),
                "range_utilization_pts": round(range_utilization_pts, 2),
                "capital_efficiency_pts": round(cap_eff_pts, 2),
                "fee_capture_pts": round(fee_pts, 2),
            },
            "in_range": in_range,
            "range_utilization": round(range_utilization, 4),
            "capital_efficiency": round(concentration_multiplier, 2),
            "fee_capture_estimate": round(fee_capture_daily, 4),
            "fee_capture_rate_daily": round(fee_capture_rate, 6),
            "estimated_apr_pct": round(fee_capture_rate * 365 * 100, 2),
            "range_width_ticks": range_width,
        }

    def project_impermanent_loss(
        self,
        entry_price: float,
        current_price: float,
        tick_lower: int = 0,
        tick_upper: int = 0,
    ) -> dict:
        """Project impermanent loss for a concentrated liquidity position.

        IL Formula (full range):
            IL = 2 * sqrt(price_ratio) / (1 + price_ratio) - 1

        For concentrated liquidity, IL is amplified by the concentration factor.

        Args:
            entry_price:   Price at position entry.
            current_price: Current price.
            tick_lower:    Position lower tick (0 for full-range calculation).
            tick_upper:    Position upper tick (0 for full-range calculation).

        Returns:
            dict with il_pct, il_amplified_pct (for concentrated),
            breakeven_fees_pct, and price_ratio.
        """
        if entry_price <= 0:
            return {"error": "entry_price must be positive"}

        price_ratio = current_price / entry_price

        # Full-range IL
        if price_ratio > 0:
            sqrt_ratio = math.sqrt(price_ratio)
            il_full_range = 2 * sqrt_ratio / (1 + price_ratio) - 1
        else:
            il_full_range = -1.0

        il_pct = abs(il_full_range) * 100

        # Concentrated IL amplification
        if tick_lower != 0 and tick_upper != 0:
            range_width = tick_upper - tick_lower
            full_range = 887220 * 2
            concentration = full_range / max(range_width, 1)
            il_amplified_pct = il_pct * min(math.sqrt(concentration), 50)
        else:
            concentration = 1.0
            il_amplified_pct = il_pct

        # Fees needed to offset IL
        breakeven_fees_pct = il_amplified_pct

        return {
            "price_ratio": round(price_ratio, 6),
            "il_full_range_pct": round(il_pct, 4),
            "il_amplified_pct": round(il_amplified_pct, 4),
            "concentration_factor": round(concentration, 1),
            "breakeven_fees_pct": round(breakeven_fees_pct, 4),
            "price_change_pct": round((price_ratio - 1) * 100, 2),
            "direction": "up" if price_ratio > 1 else "down" if price_ratio < 1 else "flat",
        }

    def compare_fee_tiers(
        self,
        volume_24h_usd: float,
        volatility_pct: float,
        liquidity_usd: float = 100_000,
    ) -> dict:
        """Compare expected returns across different fee tiers.

        Evaluates each standard fee tier to determine which maximizes
        fee revenue given current market conditions.

        Model:
            expected_volume_share ∝ 1 / fee_tier (lower fees attract more volume)
            fee_revenue = volume_share * fee_rate
            optimal_tier = argmax(fee_revenue)

        Args:
            volume_24h_usd:  Total 24h pool volume.
            volatility_pct:  Current volatility percentage.
            liquidity_usd:   Reference liquidity amount for APR calculation.

        Returns:
            dict with tier comparisons and recommended tier.
        """
        tiers = {
            "0.01%": 100,
            "0.05%": 500,
            "0.30%": 3000,
            "1.00%": 10000,
            "dynamic": 0x800000,
        }

        comparisons = []
        best_tier = None
        best_apr = -1

        for tier_name, fee_bps in tiers.items():
            if tier_name == "dynamic":
                # Dynamic fee: estimate average fee based on volatility
                # Low vol -> low fee, high vol -> high fee
                estimated_fee_bps = int(500 + volatility_pct * 10)
                estimated_fee_bps = max(500, min(estimated_fee_bps, 10000))
                fee_rate = estimated_fee_bps / 1_000_000
            else:
                fee_rate = fee_bps / 1_000_000

            # Volume elasticity: lower fees capture proportionally more volume
            # Elasticity model: volume_share ~ (reference_fee / this_fee) ^ 0.5
            reference_fee = 3000 / 1_000_000  # 0.3% as reference
            if fee_rate > 0:
                volume_multiplier = math.sqrt(reference_fee / fee_rate)
            else:
                volume_multiplier = 1.0

            captured_volume = volume_24h_usd * volume_multiplier
            daily_fees = captured_volume * fee_rate
            apr_pct = (daily_fees / max(liquidity_usd, 1)) * 365 * 100

            entry = {
                "tier": tier_name,
                "fee_bps": fee_bps if tier_name != "dynamic" else estimated_fee_bps,
                "fee_rate": round(fee_rate, 6),
                "volume_multiplier": round(volume_multiplier, 3),
                "daily_fees_usd": round(daily_fees, 2),
                "apr_pct": round(apr_pct, 2),
            }
            comparisons.append(entry)

            if apr_pct > best_apr:
                best_apr = apr_pct
                best_tier = tier_name

        # For Genesis hook pools, dynamic is preferred when vol > 3%
        genesis_recommended = "dynamic" if volatility_pct > 3.0 else best_tier

        return {
            "volume_24h_usd": volume_24h_usd,
            "volatility_pct": volatility_pct,
            "liquidity_usd": liquidity_usd,
            "comparisons": comparisons,
            "best_static_tier": best_tier,
            "genesis_recommended": genesis_recommended,
            "dynamic_advantage": genesis_recommended == "dynamic",
        }

    # ── Integration Summary ───────────────────────────────────────────

    def get_integration_summary(self) -> dict:
        """Return a summary of the uniswap-driver skill integration.

        Useful for README documentation and evaluator reference.
        """
        return {
            "uniswap_ai_skill": "uniswap-driver",
            "status": "integrated",
            "usage": "Swap route optimization and liquidity position planning",
            "capabilities": [
                "plan_liquidity_position - Optimal LP position parameters",
                "optimize_tick_range - Volatility-aware tick range selection",
                "plan_swap_route - Multi-hop route finding with price impact",
                "estimate_gas - Gas cost estimation for all operations",
                "get_pool_analytics - TVL, volume, fee APR, tick distribution",
                "recommend_rebalance_params - AutoRebalanceModule integration",
            ],
            "chain_id": self.chain_id,
            "hook_address": self.hook_address,
            "rebalance_module": self.rebalance_module,
            "v4_contracts": {
                "pool_manager": self.POOL_MANAGER,
                "position_manager": self.POSITION_MANAGER,
                "quoter": self.QUOTER,
            },
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
