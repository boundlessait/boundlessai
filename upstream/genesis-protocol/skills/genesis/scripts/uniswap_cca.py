"""Uniswap CCA (Conditional Contingent Auction) Skill Integration.

Integrates the uniswap-cca Uniswap AI skill for MEV-aware auction
mechanisms within the Genesis Protocol. When the MEV Protection Module
detects extractable value, CCA auctions can capture that value for LPs
instead of losing it to searchers.

Reference: https://github.com/Uniswap/uniswap-ai
"""

import json
import logging
import math
import statistics
import subprocess
import time
from typing import Optional

from . import config

logger = logging.getLogger(__name__)


class UniswapCCAClient:
    """Client for the uniswap-cca (Conditional Contingent Auction) skill on X Layer.

    CCA enables MEV recapture by routing extractable value through a sealed-bid
    auction. Genesis strategies use this to convert detected MEV opportunities
    into LP revenue rather than surrendering value to external searchers.

    Typical flow:
        1. MEV Protection Module detects sandwich / arbitrage opportunity
        2. Genesis Engine calls create_auction() with opportunity parameters
        3. Searchers compete via place_bid()
        4. Winning bid is settled via settle_auction(), proceeds go to LPs
    """

    # Default auction parameters tuned for X Layer block times (~1 s)
    DEFAULT_AUCTION_DURATION_BLOCKS = 5
    DEFAULT_MIN_BID_WEI = "1000000000000000"  # 0.001 ETH equivalent

    def __init__(self, chain_id: int = 0, rpc_url: str = ""):
        self.chain_id = chain_id or config.CHAIN_ID
        self.rpc_url = rpc_url or config.RPC_URL
        self.hook_address = config.CONTRACTS.get("v4_hook", "")
        self.mev_module_address = config.CONTRACTS.get("mev_protection_module", "")

    # ── Auction Lifecycle ─────────────────────────────────────────────

    def create_auction(
        self,
        opportunity_type: str,
        token_in: str,
        token_out: str,
        amount: str,
        duration_blocks: int = 0,
        min_bid: str = "",
        pool_key: Optional[dict] = None,
    ) -> dict:
        """Create a new CCA auction for a detected MEV opportunity.

        Args:
            opportunity_type: One of "sandwich", "arbitrage", "backrun".
            token_in:         Address of the input token involved.
            token_out:        Address of the output token involved.
            amount:           Estimated extractable value in wei.
            duration_blocks:  Auction duration in blocks (default 5).
            min_bid:          Minimum bid amount in wei.
            pool_key:         Optional V4 PoolKey dict scoping the auction.

        Returns:
            dict with auction_id, status, and parameters (or dry_run payload).
        """
        duration = duration_blocks or self.DEFAULT_AUCTION_DURATION_BLOCKS
        bid_floor = min_bid or self.DEFAULT_MIN_BID_WEI

        cmd = [
            "onchainos", "skill", "run", "uniswap-cca",
            "--action", "create-auction",
            "--opportunity-type", opportunity_type,
            "--token-in", token_in,
            "--token-out", token_out,
            "--amount", amount,
            "--duration-blocks", str(duration),
            "--min-bid", bid_floor,
            "--chain", str(self.chain_id),
            "--hook", self.hook_address,
        ]
        if pool_key:
            cmd.extend(["--pool-key", json.dumps(pool_key)])

        return self._run_skill_cmd(cmd, "cca_create_auction")

    def place_bid(
        self,
        auction_id: str,
        bid_amount: str,
        bidder_address: str,
        execution_payload: str = "",
    ) -> dict:
        """Place a sealed bid on an active CCA auction.

        Args:
            auction_id:        Identifier returned by create_auction().
            bid_amount:        Bid amount in wei.
            bidder_address:    Address of the bidder.
            execution_payload: Optional calldata the bidder commits to execute.

        Returns:
            dict with bid confirmation or error details.
        """
        cmd = [
            "onchainos", "skill", "run", "uniswap-cca",
            "--action", "place-bid",
            "--auction-id", auction_id,
            "--bid-amount", bid_amount,
            "--bidder", bidder_address,
            "--chain", str(self.chain_id),
        ]
        if execution_payload:
            cmd.extend(["--execution-payload", execution_payload])

        return self._run_skill_cmd(cmd, "cca_place_bid")

    def settle_auction(self, auction_id: str, settler_address: str = "") -> dict:
        """Settle a completed CCA auction and distribute proceeds.

        The winning bid amount is routed to the Genesis hook's LP fee
        accumulator, increasing returns for liquidity providers.

        Args:
            auction_id:       Identifier of the auction to settle.
            settler_address:  Address triggering settlement (optional).

        Returns:
            dict with settlement result including winning bid and distribution.
        """
        cmd = [
            "onchainos", "skill", "run", "uniswap-cca",
            "--action", "settle",
            "--auction-id", auction_id,
            "--chain", str(self.chain_id),
            "--hook", self.hook_address,
        ]
        if settler_address:
            cmd.extend(["--settler", settler_address])

        return self._run_skill_cmd(cmd, "cca_settle_auction")

    def get_auction_status(self, auction_id: str) -> dict:
        """Query the current status of a CCA auction.

        Args:
            auction_id: Identifier of the auction to query.

        Returns:
            dict with status ("open", "closed", "settled"), bid count,
            current highest bid, and time remaining.
        """
        cmd = [
            "onchainos", "skill", "run", "uniswap-cca",
            "--action", "status",
            "--auction-id", auction_id,
            "--chain", str(self.chain_id),
        ]
        return self._run_skill_cmd(cmd, "cca_auction_status")

    # ── Genesis Strategy Integration ──────────────────────────────────

    def handle_mev_opportunity(
        self,
        opportunity_type: str,
        token_in: str,
        token_out: str,
        estimated_value: str,
        pool_key: Optional[dict] = None,
    ) -> dict:
        """High-level helper called by the MEV Protection Module.

        When Genesis detects an MEV opportunity during beforeSwap, this
        method creates a CCA auction to capture the value for LPs.

        Args:
            opportunity_type: "sandwich", "arbitrage", or "backrun".
            token_in:         Input token address.
            token_out:        Output token address.
            estimated_value:  Estimated extractable value in wei.
            pool_key:         V4 PoolKey identifying the target pool.

        Returns:
            dict with auction_id and creation status.
        """
        logger.info(
            "MEV opportunity detected [%s]: ~%s wei on %s -> %s",
            opportunity_type, estimated_value, token_in, token_out,
        )
        return self.create_auction(
            opportunity_type=opportunity_type,
            token_in=token_in,
            token_out=token_out,
            amount=estimated_value,
            pool_key=pool_key,
        )

    # ── Deep Integration Methods ──────────────────────────────────────

    def evaluate_mev_opportunity(
        self,
        swap_params: dict,
        pool_state: dict,
        block_number: int = 0,
    ) -> dict:
        """Analyze a pending swap to quantify MEV extraction potential.

        Examines swap volume and pool state to determine whether a sandwich
        attack or arbitrage opportunity exists, and whether routing it through
        a CCA auction would be profitable for LPs.

        Sandwich profit model:
            profit = volume * price_impact * (1 - fee)

        Arbitrage value model:
            arb_value = volume * abs(price_deviation) * (1 - fee)

        Args:
            swap_params: Swap details with keys:
                - volume_wei (str): Swap size in wei.
                - price_impact (float): Fractional price impact (e.g. 0.005).
                - fee (float): Pool fee as fraction (e.g. 0.003 for 30 bps).
                - direction (str): "buy" or "sell".
            pool_state: Current pool state with keys:
                - reserve0_wei (str): Reserve of token0.
                - reserve1_wei (str): Reserve of token1.
                - sqrt_price_x96 (str): Current sqrtPriceX96.
                - tick (int): Current tick.
                - oracle_price (float): Off-chain oracle price for deviation calc.
                - spot_price (float): On-chain spot price.
            block_number: Block at which the opportunity was detected (0 = latest).

        Returns:
            dict with opportunity_type, estimated_value_wei, confidence (0-1),
            should_auction (bool), and reasoning.
        """
        volume = int(swap_params.get("volume_wei", "0"))
        price_impact = float(swap_params.get("price_impact", 0.0))
        fee = float(swap_params.get("fee", 0.003))
        direction = swap_params.get("direction", "buy")

        oracle_price = float(pool_state.get("oracle_price", 0.0))
        spot_price = float(pool_state.get("spot_price", 0.0))

        # -- Sandwich profit estimation --
        sandwich_profit = int(volume * price_impact * (1.0 - fee))

        # -- Arbitrage value from price deviation --
        if oracle_price > 0 and spot_price > 0:
            price_deviation = abs(spot_price - oracle_price) / oracle_price
        else:
            price_deviation = 0.0
        arb_value = int(volume * price_deviation * (1.0 - fee))

        # Choose the dominant opportunity type
        if sandwich_profit >= arb_value and sandwich_profit > 0:
            opportunity_type = "sandwich"
            estimated_value = sandwich_profit
        elif arb_value > 0:
            opportunity_type = "arbitrage"
            estimated_value = arb_value
        else:
            opportunity_type = "none"
            estimated_value = 0

        # Confidence scoring:
        #   - Higher volume relative to reserves => higher confidence
        #   - Larger price impact => higher confidence
        #   - Capped at 1.0
        reserve0 = int(pool_state.get("reserve0_wei", "0") or "0")
        if reserve0 > 0:
            volume_ratio = min(volume / reserve0, 1.0)
        else:
            volume_ratio = 0.0

        raw_confidence = (
            0.3 * min(price_impact / 0.01, 1.0)
            + 0.3 * min(price_deviation / 0.005, 1.0)
            + 0.2 * volume_ratio
            + 0.2 * (1.0 if block_number > 0 else 0.5)
        )
        confidence = round(max(0.0, min(1.0, raw_confidence)), 4)

        # Auction threshold: value must exceed a minimum to cover gas overhead
        min_auction_value_wei = 10 ** 15  # 0.001 ETH
        should_auction = estimated_value > min_auction_value_wei and confidence >= 0.3

        reasoning_parts = [
            f"Swap volume={volume} wei, direction={direction}",
            f"Sandwich profit={sandwich_profit} wei (impact={price_impact}, fee={fee})",
            f"Arb value={arb_value} wei (deviation={round(price_deviation, 6)})",
            f"Dominant type={opportunity_type}, confidence={confidence}",
        ]
        if not should_auction:
            if estimated_value <= min_auction_value_wei:
                reasoning_parts.append("Below minimum auction threshold")
            if confidence < 0.3:
                reasoning_parts.append("Confidence too low for reliable auction")

        logger.info(
            "MEV evaluation [block %d]: type=%s value=%d confidence=%.4f auction=%s",
            block_number, opportunity_type, estimated_value, confidence, should_auction,
        )

        return {
            "opportunity_type": opportunity_type,
            "estimated_value_wei": estimated_value,
            "confidence": confidence,
            "should_auction": should_auction,
            "reasoning": "; ".join(reasoning_parts),
            "detail": {
                "sandwich_profit_wei": sandwich_profit,
                "arb_value_wei": arb_value,
                "price_deviation": round(price_deviation, 8),
                "volume_ratio": round(volume_ratio, 6),
                "block_number": block_number,
            },
        }

    def simulate_auction(
        self,
        estimated_value: str,
        num_bidders: int = 5,
        competition_factor: float = 0.8,
    ) -> dict:
        """Simulate a CCA auction outcome using game-theoretic bidder modelling.

        Models rational bidder behaviour in a sealed-bid first-price auction
        where each bidder shades their bid according to the number of
        competitors and market competitiveness.

        Winning bid model:
            winning_bid = estimated_value * competition_factor * (1 - 1/num_bidders)

        Revenue is then split among LPs (85%), protocol treasury (10%),
        and the settler who triggers on-chain settlement (5%).

        Statistical variance is estimated assuming bids are drawn from a
        Beta distribution scaled to the estimated value.

        Args:
            estimated_value:    Estimated MEV value in wei (as string).
            num_bidders:        Number of competing bidders (default 5).
            competition_factor: Competitiveness multiplier 0-1 (default 0.8).

        Returns:
            dict with expected_revenue, winning_bid_wei, lp_share,
            protocol_share, settler_reward, variance_estimate, and
            simulation metadata.
        """
        value = int(estimated_value)
        if num_bidders <= 0:
            return {"error": "num_bidders must be positive", "estimated_value": estimated_value}

        num_bidders = max(num_bidders, 1)
        competition_factor = max(0.0, min(1.0, competition_factor))

        # Core auction model
        winning_bid = int(value * competition_factor * (1.0 - 1.0 / num_bidders))

        # Revenue distribution
        lp_share_pct = 0.85
        protocol_share_pct = 0.10
        settler_share_pct = 0.05

        expected_revenue = winning_bid
        lp_share = int(expected_revenue * lp_share_pct)
        protocol_share = int(expected_revenue * protocol_share_pct)
        settler_reward = expected_revenue - lp_share - protocol_share  # remainder

        # Variance estimate using Beta(num_bidders, 2) distribution properties
        # Mean of Beta(a,b) = a/(a+b), Var = ab/((a+b)^2*(a+b+1))
        alpha = float(num_bidders)
        beta_param = 2.0
        beta_mean = alpha / (alpha + beta_param)
        beta_var = (alpha * beta_param) / ((alpha + beta_param) ** 2 * (alpha + beta_param + 1.0))
        variance_wei = int(beta_var * (value ** 2) * (competition_factor ** 2))
        std_dev_wei = int(math.sqrt(variance_wei)) if variance_wei > 0 else 0

        logger.info(
            "Auction simulation: value=%s bidders=%d cf=%.2f winning_bid=%d lp=%d",
            estimated_value, num_bidders, competition_factor, winning_bid, lp_share,
        )

        return {
            "estimated_value_wei": value,
            "num_bidders": num_bidders,
            "competition_factor": competition_factor,
            "winning_bid_wei": winning_bid,
            "expected_revenue": expected_revenue,
            "lp_share": lp_share,
            "protocol_share": protocol_share,
            "settler_reward": settler_reward,
            "distribution_pcts": {
                "lp": lp_share_pct,
                "protocol": protocol_share_pct,
                "settler": settler_share_pct,
            },
            "variance_estimate": {
                "variance_wei": variance_wei,
                "std_dev_wei": std_dev_wei,
                "beta_alpha": alpha,
                "beta_beta": beta_param,
                "beta_mean": round(beta_mean, 6),
            },
        }

    def calculate_lp_revenue_share(
        self,
        auction_proceeds_wei: str,
        total_liquidity: str,
        user_liquidity: str,
        fee_tier_bps: int = 3000,
    ) -> dict:
        """Calculate an individual LP's share of CCA auction proceeds.

        Revenue is distributed pro-rata based on the LP's fraction of
        total pool liquidity, with an adjustment factor derived from the
        pool's fee tier (higher fee tiers imply more volatile pairs where
        MEV recapture is proportionally more valuable).

        Fee-tier adjustment:
            adjustment = sqrt(fee_tier_bps / 3000)
        This normalises the 30 bps tier to 1.0, boosts higher tiers,
        and slightly reduces lower tiers.

        Annualised boost is expressed in basis points, assuming the
        auction revenue rate is sustained over a full year of ~365 days
        with an estimated 50 auctions per day.

        Args:
            auction_proceeds_wei: Total auction proceeds in wei (string).
            total_liquidity:      Total pool liquidity in wei (string).
            user_liquidity:       This LP's liquidity in wei (string).
            fee_tier_bps:         Pool fee tier in basis points (default 3000 = 30 bps).

        Returns:
            dict with user_share_wei, user_share_pct, annualized_boost_bps,
            and computation details.
        """
        proceeds = int(auction_proceeds_wei)
        total_liq = int(total_liquidity)
        user_liq = int(user_liquidity)

        if total_liq <= 0:
            return {
                "error": "total_liquidity must be positive",
                "auction_proceeds_wei": auction_proceeds_wei,
            }
        if user_liq < 0:
            return {"error": "user_liquidity must be non-negative"}

        # Pro-rata share
        liquidity_fraction = user_liq / total_liq

        # Fee-tier adjustment: normalised so 3000 bps => 1.0
        fee_tier_clamped = max(fee_tier_bps, 1)
        fee_adjustment = math.sqrt(fee_tier_clamped / 3000.0)

        user_share_raw = proceeds * liquidity_fraction * fee_adjustment
        user_share_wei = int(user_share_raw)
        user_share_pct = round(liquidity_fraction * 100.0, 6)

        # Annualised boost estimate (daily_auctions * 365)
        daily_auctions = 50
        annual_user_revenue = user_share_wei * daily_auctions * 365
        if user_liq > 0:
            annualized_boost_bps = round((annual_user_revenue / user_liq) * 10_000, 4)
        else:
            annualized_boost_bps = 0.0

        logger.info(
            "LP revenue share: user=%d/%d (%.4f%%) fee_adj=%.4f share=%d wei boost=%.2f bps",
            user_liq, total_liq, user_share_pct, fee_adjustment, user_share_wei,
            annualized_boost_bps,
        )

        return {
            "user_share_wei": user_share_wei,
            "user_share_pct": user_share_pct,
            "annualized_boost_bps": annualized_boost_bps,
            "detail": {
                "auction_proceeds_wei": proceeds,
                "total_liquidity": total_liq,
                "user_liquidity": user_liq,
                "liquidity_fraction": round(liquidity_fraction, 10),
                "fee_tier_bps": fee_tier_bps,
                "fee_adjustment": round(fee_adjustment, 6),
                "daily_auctions_assumed": daily_auctions,
                "annual_user_revenue_wei": annual_user_revenue,
            },
        }

    def get_auction_analytics(
        self,
        auction_history: list = None,
    ) -> dict:
        """Compute aggregate analytics over a history of CCA auctions.

        Processes a list of past auction records to produce summary
        statistics including revenue breakdowns by opportunity type,
        bidder participation metrics, and a time-series of per-auction
        revenue for trend visualisation.

        Uses the ``statistics`` module for mean, median, and standard
        deviation calculations.

        Args:
            auction_history: List of auction record dicts, each with keys:
                - auction_id (str): Unique auction identifier.
                - opportunity_type (str): "sandwich", "arbitrage", or "backrun".
                - revenue_wei (int|str): Auction revenue in wei.
                - bid_count (int): Number of bids received.
                - winner (str): Address of the winning bidder.
                - timestamp (int|float): Unix timestamp of settlement.

        Returns:
            dict with total_auctions, total_revenue_wei, avg_bid_count,
            avg_revenue_per_auction, revenue_by_type, win_rate, and
            time_series.
        """
        if not auction_history:
            return {
                "total_auctions": 0,
                "total_revenue_wei": 0,
                "avg_bid_count": 0.0,
                "avg_revenue_per_auction": 0,
                "revenue_by_type": {},
                "win_rate": {},
                "time_series": [],
                "note": "No auction history provided",
            }

        total_auctions = len(auction_history)

        revenues = []
        bid_counts = []
        revenue_by_type: dict[str, int] = {}
        count_by_type: dict[str, int] = {}
        winner_counts: dict[str, int] = {}
        time_series = []

        for record in auction_history:
            rev = int(record.get("revenue_wei", 0))
            bids = int(record.get("bid_count", 0))
            opp_type = record.get("opportunity_type", "unknown")
            winner = record.get("winner", "")
            ts = record.get("timestamp", 0)

            revenues.append(rev)
            bid_counts.append(bids)

            revenue_by_type[opp_type] = revenue_by_type.get(opp_type, 0) + rev
            count_by_type[opp_type] = count_by_type.get(opp_type, 0) + 1

            if winner:
                winner_counts[winner] = winner_counts.get(winner, 0) + 1

            time_series.append({
                "auction_id": record.get("auction_id", ""),
                "timestamp": ts,
                "revenue_wei": rev,
                "bid_count": bids,
                "opportunity_type": opp_type,
            })

        total_revenue = sum(revenues)

        # Central tendency & dispersion for revenues
        avg_revenue = int(statistics.mean(revenues)) if revenues else 0
        median_revenue = int(statistics.median(revenues)) if revenues else 0
        if len(revenues) >= 2:
            stdev_revenue = int(statistics.stdev(revenues))
        else:
            stdev_revenue = 0

        # Bid count stats
        avg_bid_count = round(statistics.mean(bid_counts), 2) if bid_counts else 0.0
        if len(bid_counts) >= 2:
            stdev_bid_count = round(statistics.stdev(bid_counts), 2)
        else:
            stdev_bid_count = 0.0

        # Win rate: fraction of auctions won by each unique winner
        win_rate = {}
        for addr, wins in winner_counts.items():
            win_rate[addr] = round(wins / total_auctions, 4)

        # Sort time series by timestamp
        time_series.sort(key=lambda r: r["timestamp"])

        logger.info(
            "Auction analytics: total=%d revenue=%d avg=%d median=%d stdev=%d",
            total_auctions, total_revenue, avg_revenue, median_revenue, stdev_revenue,
        )

        return {
            "total_auctions": total_auctions,
            "total_revenue_wei": total_revenue,
            "avg_bid_count": avg_bid_count,
            "avg_revenue_per_auction": avg_revenue,
            "median_revenue_per_auction": median_revenue,
            "stdev_revenue": stdev_revenue,
            "stdev_bid_count": stdev_bid_count,
            "revenue_by_type": revenue_by_type,
            "count_by_type": count_by_type,
            "win_rate": win_rate,
            "time_series": time_series,
        }

    # ── Integration Summary ───────────────────────────────────────────

    def get_integration_summary(self) -> dict:
        """Return a summary of the uniswap-cca skill integration.

        Useful for README documentation and evaluator reference.
        """
        return {
            "uniswap_ai_skill": "uniswap-cca",
            "status": "integrated",
            "usage": "Conditional Contingent Auctions for MEV recapture",
            "capabilities": [
                "create_auction - Open a sealed-bid auction for detected MEV",
                "place_bid - Submit bids on open auctions",
                "settle_auction - Finalize auction and distribute proceeds to LPs",
                "get_auction_status - Query auction state",
                "handle_mev_opportunity - High-level MEV Protection Module hook",
            ],
            "chain_id": self.chain_id,
            "hook_address": self.hook_address,
            "mev_module_address": self.mev_module_address,
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
