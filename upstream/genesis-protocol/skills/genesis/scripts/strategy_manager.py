"""Strategy Lifecycle Manager — tracks active strategies, monitors performance,
triggers rebalances and NFT mints.

Manages the full lifecycle: create -> monitor -> evaluate -> rebalance -> deactivate.
All strategy records are persisted to a local JSON registry.
"""
import json
import logging
import subprocess
import time
import os

from . import config
from .decision_journal import DecisionJournal
from .nft_minter import NFTMinter
from .hook_assembler import HookAssembler
from .security_scanner import SecurityScanner

logger = logging.getLogger(__name__)

REGISTRY_PATH = os.path.join("strategies", "registry.json")
_REBALANCE_VOL_SHIFT_BPS = 300       # 3% vol shift triggers rebalance review
_DEACTIVATE_LOSS_BPS = -500          # -5% cumulative loss => deactivate
_DEACTIVATE_IDLE_SWAPS = 5           # fewer swaps than this in eval window
_BENCHMARK_HOLD_ANNUAL_BPS = 500     # naive hold benchmark: +5% annualised


class StrategyManager:
    """Orchestrates strategy creation, monitoring, rebalancing and retirement."""

    def __init__(self, assembler_address="", nft_address=""):
        self.assembler_address = assembler_address or config.CONTRACTS.get("assembler", "")
        self.nft_address = nft_address or config.CONTRACTS.get("strategy_nft", "")
        self.assembler = HookAssembler(self.assembler_address)
        self.journal = DecisionJournal(self.assembler_address)
        self.nft_minter = NFTMinter(self.nft_address, self.assembler_address)
        self.security = SecurityScanner()
        self.strategies = {}
        self._load_local_registry()
        logger.info("StrategyManager ready (%d strategies loaded)", len(self.strategies))

    def create_strategy(self, market_regime, market_data):
        """Orchestrate full strategy creation via HookAssembler. Returns strategy record."""
        preset_name = self._select_preset(market_regime)
        regime_dict = {
            "regime_name": market_regime if isinstance(market_regime, str) else market_regime.get("regime_name", ""),
            "volatility_bps": market_data.get("volatility_bps", 0) if isinstance(market_data, dict) else 0,
            "trend": market_data.get("trend", "sideways") if isinstance(market_data, dict) else "sideways",
        }
        # ── Security check before deployment ────────────────────────────
        token0_addr = market_data.get("token0", "") if isinstance(market_data, dict) else ""
        token1_addr = market_data.get("token1", "") if isinstance(market_data, dict) else ""
        if token0_addr and token1_addr:
            safe, reason = self.security.is_safe_for_strategy(token0_addr, token1_addr)
            logger.info("Security check: safe=%s reason=%s", safe, reason)
            if not safe and not config.PAUSED:
                return {"error": f"Security check failed: {reason}"}
        else:
            logger.info("Security check skipped: token addresses not provided in market_data")

        deploy_result = self.assembler.compose_and_deploy(regime_dict, market_data if isinstance(market_data, dict) else {})
        if deploy_result.get("error"):
            logger.error("compose_and_deploy failed: %s", deploy_result)
            return {"error": deploy_result["error"]}
        strategy_id = deploy_result.get("strategy_id", "")
        modules = list(deploy_result.get("modules", {}).keys())
        record = {
            "id": strategy_id, "preset_name": preset_name, "modules": modules,
            "created_at": int(time.time()), "last_evaluated": 0,
            "pnl_bps": 0, "total_swaps": 0, "total_volume": 0,
            "status": "active", "market_regime_at_creation": market_regime,
        }
        self.strategies[strategy_id] = record
        self._save_local_registry()
        self.journal.log_decision(
            strategy_id, "STRATEGY_CREATE",
            f"Created {preset_name} for regime={market_regime}",
            {"preset": preset_name, "modules": modules},
        )
        logger.info("Strategy %s created (preset=%s)", strategy_id, preset_name)
        return record

    def monitor_strategy(self, strategy_id):
        """Check strategy health: active, modules responding, P&L within bounds."""
        record = self.strategies.get(strategy_id)
        if not record:
            return {"healthy": False, "reason": "unknown strategy"}
        active = record["status"] == "active"
        age_hours = (int(time.time()) - record["created_at"]) / 3600
        pnl_ok = record["pnl_bps"] > _DEACTIVATE_LOSS_BPS
        modules_ok = len(record.get("modules", [])) > 0
        healthy = active and pnl_ok and modules_ok
        return {
            "strategy_id": strategy_id, "healthy": healthy, "active": active,
            "pnl_ok": pnl_ok, "modules_ok": modules_ok, "age_hours": round(age_hours, 2),
        }

    def evaluate_performance(self, strategy_id):
        """Calculate P&L, volume metrics, compare to benchmarks. Returns performance dict."""
        record = self.strategies.get(strategy_id)
        if not record:
            return {"error": "unknown strategy"}
        on_chain = self.assembler.get_strategy_stats(strategy_id)
        pnl_bps = on_chain.get("pnl_bps", record["pnl_bps"])
        total_swaps = on_chain.get("total_swaps", record["total_swaps"])
        total_volume = on_chain.get("total_volume", record["total_volume"])
        age_hours = max((int(time.time()) - record["created_at"]) / 3600, 1)
        annualised_bps = int(pnl_bps * (8760 / age_hours))
        vs_benchmark = annualised_bps - _BENCHMARK_HOLD_ANNUAL_BPS
        record.update(pnl_bps=pnl_bps, total_swaps=total_swaps,
                      total_volume=total_volume, last_evaluated=int(time.time()))
        self._save_local_registry()
        self.assembler.update_performance(strategy_id, pnl_bps, total_volume)
        self.journal.log_decision(
            strategy_id, "PERFORMANCE_EVAL",
            f"P&L={pnl_bps}bps swaps={total_swaps} vs_bench={vs_benchmark}bps",
            {"pnl_bps": pnl_bps, "annualised_bps": annualised_bps},
        )
        return {
            "strategy_id": strategy_id, "pnl_bps": pnl_bps,
            "annualised_bps": annualised_bps, "total_swaps": total_swaps,
            "total_volume": total_volume, "vs_benchmark_bps": vs_benchmark,
        }

    def should_rebalance(self, strategy_id, market_data):
        """Determine if strategy needs rebalancing based on market shift. Returns (bool, reason)."""
        record = self.strategies.get(strategy_id)
        if not record or record["status"] != "active":
            return False, "not active"
        current_vol = market_data.get("volatility_bps", 0)
        preset = config.STRATEGY_PRESETS.get(record["preset_name"], {})
        vol_range = preset.get("market_conditions", {}).get("vol_range", [0, 9999])
        if current_vol < vol_range[0] - _REBALANCE_VOL_SHIFT_BPS:
            return True, f"vol {current_vol} dropped below preset range"
        if current_vol > vol_range[1] + _REBALANCE_VOL_SHIFT_BPS:
            return True, f"vol {current_vol} exceeded preset range"
        regime = record.get("market_regime_at_creation", "")
        current_regime = market_data.get("regime", regime)
        if current_regime != regime:
            return True, f"regime shifted from {regime} to {current_regime}"
        return False, "within bounds"

    def rebalance_strategy(self, strategy_id, new_market_regime):
        """Update module parameters for new market conditions. Log decision.

        Compares Hook pool vs Uniswap DEX routes via uniswap-trading skill
        to ensure optimal execution venue before rebalancing.
        """
        record = self.strategies.get(strategy_id)
        if not record:
            logger.warning("Cannot rebalance unknown strategy %s", strategy_id)
            return
        new_preset = self._select_preset(new_market_regime)
        preset = config.STRATEGY_PRESETS[new_preset]

        # Compare Hook pool vs DEX aggregator via uniswap-trading
        route_comparison = self._compare_swap_routes(record)

        self.assembler.update_modules(strategy_id, preset["modules"], preset.get("overrides", {}))
        record["preset_name"] = new_preset
        record["modules"] = preset["modules"]
        record["market_regime_at_creation"] = new_market_regime
        self._save_local_registry()
        self.journal.log_decision(
            strategy_id, "REBALANCE_EXECUTE",
            f"Rebalanced to {new_preset} for regime={new_market_regime}. Route: {route_comparison.get('best_venue', 'hook')}",
            {"new_preset": new_preset, "modules": preset["modules"],
             "route_comparison": route_comparison},
        )
        logger.info("Strategy %s rebalanced -> %s (venue: %s)",
                     strategy_id, new_preset, route_comparison.get("best_venue", "hook"))

    def should_deactivate(self, strategy_id, performance):
        """Determine if strategy should be shut down. Returns (bool, reason)."""
        pnl = performance.get("pnl_bps", 0)
        swaps = performance.get("total_swaps", 0)
        if pnl <= _DEACTIVATE_LOSS_BPS:
            return True, f"persistent loss ({pnl} bps)"
        if performance.get("vs_benchmark_bps", 0) < -1000:
            return True, "significantly underperforming benchmark"
        if swaps < _DEACTIVATE_IDLE_SWAPS and performance.get("annualised_bps", 0) < 0:
            return True, f"idle ({swaps} swaps) with negative P&L"
        return False, "performance acceptable"

    def deactivate_strategy(self, strategy_id, reason):
        """Deactivate strategy, log decision, check NFT eligibility."""
        record = self.strategies.get(strategy_id)
        if not record:
            logger.warning("Cannot deactivate unknown strategy %s", strategy_id)
            return
        record["status"] = "inactive"
        self._save_local_registry()
        self.assembler.deactivate_strategy(strategy_id)
        self.journal.log_decision(
            strategy_id, "STRATEGY_DEACTIVATE",
            f"Deactivated: {reason}",
            {"reason": reason, "final_pnl_bps": record["pnl_bps"]},
        )
        logger.info("Strategy %s deactivated: %s", strategy_id, reason)
        self.check_nft_eligibility(strategy_id)

    def check_nft_eligibility(self, strategy_id):
        """Check all NFT mint thresholds. If eligible, trigger mint via NFTMinter."""
        record = self.strategies.get(strategy_id)
        if not record:
            return
        age_hours = (int(time.time()) - record["created_at"]) / 3600
        strategy_data = {
            "pnl_bps": record["pnl_bps"],
            "total_swaps": record["total_swaps"],
            "run_hours": age_hours,
        }
        eligible, reasons = self.nft_minter.check_mint_eligibility(strategy_data)
        if not eligible:
            logger.info("Strategy %s not NFT-eligible: %s", strategy_id, reasons)
            return
        snapshot = self.nft_minter.get_strategy_snapshot(strategy_id)
        if isinstance(snapshot, dict) and snapshot.get("error"):
            logger.error("Failed to get snapshot for NFT mint: %s", snapshot)
            return
        to_address = config.WALLET_ROLES["income"]["index"]
        result = self.nft_minter.mint_strategy_nft(str(to_address), snapshot)
        self.journal.log_decision(
            strategy_id, "NFT_MINT",
            f"Minted strategy NFT (pnl={record['pnl_bps']}bps, swaps={record['total_swaps']})",
            {"token_id": str(result)},
        )
        logger.info("NFT minted for strategy %s: %s", strategy_id, result)

    def get_active_strategies(self):
        """Return list of active strategy records."""
        return [r for r in self.strategies.values() if r["status"] == "active"]

    def get_strategy_summary(self):
        """Return summary stats: count, total volume, avg P&L, best/worst."""
        active = self.get_active_strategies()
        if not active:
            return {"active_count": 0, "total_volume": 0, "avg_pnl_bps": 0,
                    "best_pnl_bps": 0, "worst_pnl_bps": 0}
        pnls = [r["pnl_bps"] for r in active]
        return {
            "active_count": len(active),
            "total_volume": sum(r["total_volume"] for r in active),
            "avg_pnl_bps": int(sum(pnls) / len(pnls)),
            "best_pnl_bps": max(pnls), "worst_pnl_bps": min(pnls),
        }

    # ── Private helpers ──────────────────────────────────────────────────

    def _compare_swap_routes(self, record):
        """Compare Hook pool vs Uniswap DEX routes via uniswap-trading skill.

        Queries uniswap-trading for the best available swap route, then compares
        effective price against the Hook pool's current fee structure.
        Returns venue recommendation for rebalance execution.
        """
        pair = config.ONCHAINOS_MARKET_PAIRS[0] if config.ONCHAINOS_MARKET_PAIRS else {}
        base = pair.get("base", "ETH")
        quote = pair.get("quote", "USDC")

        # Query uniswap-trading for optimal route
        cmd = [
            "onchainos", "skill", "run", "uniswap-trading",
            "--action", "quote",
            "--from-token", base,
            "--to-token", quote,
            "--amount", "1.0",
            "--chain", str(config.CHAIN_ID),
        ]

        dex_quote = self._run_cmd(cmd)

        # Query onchainos-trade (DEX aggregator) for comparison
        cmd_agg = [
            "onchainos", "trade", "quote",
            "--from", base,
            "--to", quote,
            "--amount", "1.0",
            "--chain", str(config.CHAIN_ID),
        ]

        agg_quote = self._run_cmd(cmd_agg)

        # Determine best venue
        try:
            dex_price = json.loads(dex_quote.get("stdout", "{}")).get("price", 0)
        except (json.JSONDecodeError, ValueError):
            dex_price = 0

        try:
            agg_price = json.loads(agg_quote.get("stdout", "{}")).get("price", 0)
        except (json.JSONDecodeError, ValueError):
            agg_price = 0

        # Include Hook pool fee in comparison
        preset_name = record.get("preset_name", "calm_accumulator")
        preset = config.STRATEGY_PRESETS.get(preset_name, {})
        fee_overrides = preset.get("overrides", {}).get("dynamic_fee", {})
        hook_fee_bps = fee_overrides.get("min_fee", 500)  # Use min fee as best-case

        best_venue = "hook"
        if dex_price and agg_price:
            # If DEX aggregator beats Uniswap route by more than hook fee, use aggregator
            if agg_price > dex_price * (1 + hook_fee_bps / 1_000_000):
                best_venue = "dex_aggregator"
            else:
                best_venue = "uniswap_v4"

        logger.info("Route comparison: uniswap=%s, aggregator=%s, best=%s",
                     dex_price, agg_price, best_venue)

        return {
            "uniswap_price": dex_price,
            "aggregator_price": agg_price,
            "hook_fee_bps": hook_fee_bps,
            "best_venue": best_venue,
            "pair": f"{base}/{quote}",
        }

    def _run_cmd(self, cmd):
        """Execute a subprocess command, respecting DRY_RUN."""
        logger.debug("cmd: %s", " ".join(cmd))
        if config.DRY_RUN:
            logger.info("[DRY_RUN] %s", " ".join(cmd))
            return {"stdout": json.dumps({"dry_run": True, "price": 0})}
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                return {"error": proc.stderr or f"exit code {proc.returncode}"}
            return {"stdout": proc.stdout}
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return {"error": str(exc)}

    def _select_preset(self, market_regime):
        """Map a market regime (string or dict) to the best strategy preset name."""
        # Handle dict input from MarketOracle.get_market_regime()
        if isinstance(market_regime, dict):
            # Prefer the preset_name key if present (set by _REGIME_TO_PRESET mapping)
            if market_regime.get("preset_name"):
                return market_regime["preset_name"]
            regime_str = market_regime.get("regime_name", "")
        else:
            regime_str = market_regime

        regime_map = {
            "low_vol": "calm_accumulator", "sideways": "calm_accumulator",
            "high_vol": "volatile_defender", "volatile": "volatile_defender",
            "trending": "trend_rider", "bull": "trend_rider",
            "bear": "volatile_defender",
            # Regime names returned by MarketOracle.get_market_regime()
            "momentum": "trend_rider",
            "defensive": "volatile_defender",
            "volatile_range": "volatile_defender",
            "trend_following": "trend_rider",
            "mean_reversion": "calm_accumulator",
        }
        return regime_map.get(regime_str, "calm_accumulator")

    def _load_local_registry(self):
        """Load strategy records from local JSON file."""
        if not os.path.isfile(REGISTRY_PATH):
            self.strategies = {}
            return
        try:
            with open(REGISTRY_PATH, "r") as fh:
                data = json.load(fh)
            self.strategies = {r["id"]: r for r in data}
            logger.debug("Loaded %d strategies from registry", len(self.strategies))
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            logger.error("Failed to load registry: %s", exc)
            self.strategies = {}

    def _save_local_registry(self):
        """Persist strategy records to local JSON file."""
        os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
        try:
            with open(REGISTRY_PATH, "w") as fh:
                json.dump(list(self.strategies.values()), fh, indent=2)
        except OSError as exc:
            logger.error("Failed to save registry: %s", exc)
