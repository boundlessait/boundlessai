"""Hook Template Engine - Composes AI module selections into deployable V4 Hook strategies.

Takes market regime analysis and assembles Hook modules (dynamic fee, MEV
protection, auto-rebalance) into deployable strategies on X Layer (chainId 196).
All on-chain writes use the onchainos CLI via subprocess. Respects config.DRY_RUN.
"""

import subprocess, json, logging, hashlib
from . import config

logger = logging.getLogger(__name__)

# ABI type signatures per module constructor (matches Solidity)
_MODULE_ABI = {
    "dynamic_fee": [
        ("base_fee", "uint256"), ("min_fee", "uint256"), ("max_fee", "uint256"),
        ("sensitivity", "uint256"), ("low_threshold", "uint256"), ("high_threshold", "uint256"),
    ],
    "mev_protection": [
        ("swap_count_threshold", "uint256"), ("volume_threshold", "uint256"),
        ("penalty_fee", "uint256"), ("block_suspicious", "bool"),
    ],
    "auto_rebalance": [
        ("soft_trigger_pct", "uint256"), ("il_threshold_bps", "uint256"),
        ("cooldown_period", "uint256"), ("strategy", "uint8"),
    ],
}
_XLAYER_USD_PER_TX = 0.0005


class HookAssembler:
    """Assembles and deploys V4 Hook strategies from modular components."""

    def __init__(self, assembler_address: str = ""):
        """Initialize with assembler contract address (falls back to config)."""
        self.assembler = assembler_address or config.CONTRACTS.get("assembler", "")
        self._deployments: list[dict] = []
        logger.info("HookAssembler initialized (assembler=%s, dry_run=%s)",
                     self.assembler or "<unset>", config.DRY_RUN)

    # ── Public API ────────────────────────────────────────────────────────

    def select_modules(self, market_regime: dict) -> tuple[str, list[str]]:
        """Given a market regime dict, select best preset from STRATEGY_PRESETS."""
        vol = market_regime.get("volatility_bps", 0)
        trend = market_regime.get("trend", "sideways")
        best_name, best_modules, best_score = "", [], -1.0

        for name, preset in config.STRATEGY_PRESETS.items():
            cond = preset["market_conditions"]
            lo, hi = cond["vol_range"]
            if not (lo <= vol <= hi):
                continue
            pt = cond.get("trend", "any")
            if pt != "any" and pt != trend:
                continue
            score = 1.0 / (1.0 + abs(vol - (lo + hi) / 2))
            if score > best_score:
                best_score, best_name = score, name
                best_modules = list(preset["modules"])

        if not best_name:
            best_name = "calm_accumulator"
            best_modules = list(config.STRATEGY_PRESETS[best_name]["modules"])
            logger.warning("No preset matched %s; defaulting to %s", market_regime, best_name)

        logger.info("Selected preset '%s' -> %s", best_name, best_modules)
        return best_name, best_modules

    def compute_params(self, preset_name: str, market_data: dict) -> dict[str, dict]:
        """Compute module params: defaults + preset overrides + dynamic adjustments."""
        preset = config.STRATEGY_PRESETS[preset_name]
        overrides = preset.get("overrides", {})
        result: dict[str, dict] = {}
        for mod in preset["modules"]:
            params = dict(config.AVAILABLE_MODULES[mod]["default_params"])
            params.update(overrides.get(mod, {}))
            # Dynamic: scale fee sensitivity by realised/implied vol ratio
            if mod == "dynamic_fee" and "realised_vol_bps" in market_data:
                implied = max(market_data.get("implied_vol_bps", market_data["realised_vol_bps"]), 1)
                ratio = max(0.5, min(market_data["realised_vol_bps"] / implied, 2.0))
                params["sensitivity"] = int(params["sensitivity"] * ratio)
            result[mod] = params
        logger.info("Computed params for '%s': %s", preset_name, list(result))
        return result

    def deploy_module(self, module_name: str, params: dict) -> str:
        """Deploy a single module contract via onchainos CLI. Returns address."""
        contract = config.AVAILABLE_MODULES[module_name]["contract"]
        encoded = self._encode_module_params(module_name, params)
        out = self._run_cmd(["onchainos", "wallet", "deploy",
                             "--contract", contract, "--args", encoded, "--index", "1"])
        addr = out.get("address", out.get("contractAddress", ""))
        if addr:
            logger.info("Deployed %s at %s", contract, addr)
            self._deployments.append({"module": module_name, "address": addr})
        else:
            logger.error("Failed to deploy %s: %s", contract, out)
        return addr

    def register_module(self, module_address: str) -> dict:
        """Register module with assembler via registerModule(address)."""
        if not self.assembler:
            return {"error": "assembler_address_not_set"}
        out = self._run_cmd(["onchainos", "wallet", "call", "--to", self.assembler,
                             "--function", "registerModule(address)",
                             "--args", module_address, "--index", "0"])
        logger.info("Registered module %s -> %s", module_address, out.get("status", "unknown"))
        return out

    def create_strategy(self, module_addresses: list[str]) -> str:
        """Create strategy in assembler via createStrategy(address[]). Returns strategy_id."""
        if not self.assembler:
            return ""
        out = self._run_cmd(["onchainos", "wallet", "call", "--to", self.assembler,
                             "--function", "createStrategy(address[])",
                             "--args", ",".join(module_addresses), "--index", "1"])
        sid = out.get("strategy_id", out.get("strategyId", ""))
        if sid:
            logger.info("Created strategy %s with modules %s", sid, module_addresses)
        else:
            logger.error("Failed to create strategy: %s", out)
        return str(sid)

    def update_module_params(self, module_address: str, encoded_params: str) -> dict:
        """Update module params via assembler's updateModuleParams(address,bytes)."""
        if not self.assembler:
            return {"error": "assembler_address_not_set"}
        return self._run_cmd(["onchainos", "wallet", "call", "--to", self.assembler,
                              "--function", "updateModuleParams(address,bytes)",
                              "--args", f"{module_address},{encoded_params}", "--index", "0"])

    def deactivate_strategy(self, strategy_id: str) -> dict:
        """Deactivate a strategy via assembler's deactivateStrategy(uint256)."""
        if not self.assembler:
            return {"error": "assembler_address_not_set"}
        out = self._run_cmd(["onchainos", "wallet", "call", "--to", self.assembler,
                             "--function", "deactivateStrategy(uint256)",
                             "--args", str(strategy_id), "--index", "0"])
        logger.info("Deactivated strategy %s -> %s", strategy_id, out.get("status", "unknown"))
        return out

    def compose_and_deploy(self, market_regime: dict, market_data: dict) -> dict:
        """Full pipeline: select -> compute -> deploy -> register -> create strategy."""
        preset_name, modules = self.select_modules(market_regime)
        params_map = self.compute_params(preset_name, market_data)

        # Validate hook compatibility before deploying
        compat = self.validate_hook_compatibility(modules)
        if compat.get("error"):
            logger.error("Hook compatibility validation failed: %s", compat)
            return {"error": "hook_validation_failed", "detail": compat}
        if not compat.get("compatible", True):
            logger.error("Modules are not compatible with Uniswap V4: %s", compat)
            return {"error": "hook_incompatible", "detail": compat}
        logger.info("Hook compatibility validated for modules %s", modules)

        deployed: dict[str, str] = {}
        for mod in modules:
            addr = self.deploy_module(mod, params_map[mod])
            if not addr:
                logger.error("Aborting compose_and_deploy: %s failed", mod)
                return {"error": f"deploy_failed:{mod}", "deployed_so_far": deployed}
            deployed[mod] = addr

        addresses = list(deployed.values())
        for addr in addresses:
            reg = self.register_module(addr)
            if "error" in reg:
                logger.error("Registration failed for %s: %s", addr, reg)
                return {"error": f"register_failed:{addr}", "deployed": deployed}

        strategy_id = self.create_strategy(addresses)
        fingerprint = hashlib.sha256(
            json.dumps({"preset": preset_name, "modules": deployed}, sort_keys=True).encode()
        ).hexdigest()[:16]
        logger.info("Strategy deployed: id=%s preset=%s fp=%s", strategy_id, preset_name, fingerprint)
        return {"strategy_id": strategy_id, "preset": preset_name,
                "modules": deployed, "fingerprint": fingerprint}

    def get_deployment_cost_estimate(self) -> dict:
        """Estimate gas costs for a full 3-module deployment on X Layer."""
        n = 3
        deploy = n * _XLAYER_USD_PER_TX
        register = n * _XLAYER_USD_PER_TX
        create = _XLAYER_USD_PER_TX
        return {"deploy_modules_usd": round(deploy, 6),
                "register_modules_usd": round(register, 6),
                "create_strategy_usd": round(create, 6),
                "total_usd": round(deploy + register + create, 6),
                "num_transactions": n * 2 + 1, "note": "X Layer gas ~$0.0005/tx"}

    # ── Uniswap AI Skills Integration ────────────────────────────────────

    def validate_hook_compatibility(self, module_names: list[str]) -> dict:
        """Validate that the selected Hook modules are compatible with Uniswap V4.

        Calls the ``uniswap-hooks`` skill via the onchainos CLI.
        Returns the skill response dict, or an error dict on failure.
        """
        cmd = ["onchainos", "skill", "run", "uniswap-hooks", "validate",
               "--modules", json.dumps(module_names),
               "--chain", str(config.CHAIN_ID)]
        logger.info("Validating hook compatibility for modules %s", module_names)
        result = self._run_cmd(cmd)
        if "error" in result:
            logger.error("uniswap-hooks validate failed: %s", result)
        else:
            logger.info("uniswap-hooks validate result: %s", result)
        return result

    def get_v4_pool_params(self, base: str, quote: str, fee_tier: int) -> dict:
        """Get recommended Uniswap V4 pool parameters for a trading pair.

        Calls the ``uniswap-hooks`` skill via the onchainos CLI.
        Returns the skill response dict, or an error dict on failure.
        """
        cmd = ["onchainos", "skill", "run", "uniswap-hooks", "pool-params",
               "--pair", f"{base}/{quote}",
               "--fee-tier", str(fee_tier),
               "--chain", str(config.CHAIN_ID)]
        logger.info("Fetching V4 pool params for %s/%s (fee_tier=%d)", base, quote, fee_tier)
        result = self._run_cmd(cmd)
        if "error" in result:
            logger.error("uniswap-hooks pool-params failed: %s", result)
        else:
            logger.info("uniswap-hooks pool-params result: %s", result)
        return result

    # ── Internal Helpers ──────────────────────────────────────────────────

    def _encode_module_params(self, module_name: str, params: dict) -> str:
        """ABI-encode constructor params as comma-separated values for onchainos CLI."""
        parts: list[str] = []
        for field, sol_type in _MODULE_ABI.get(module_name, []):
            val = params.get(field, 0)
            if sol_type == "bool":
                parts.append("1" if val else "0")
            else:
                parts.append(str(int(val)))
        return ",".join(parts)

    def _run_cmd(self, cmd: list[str], dry_run: bool | None = None) -> dict:
        """Execute onchainos CLI command; return parsed JSON or error dict."""
        is_dry = config.DRY_RUN if dry_run is None else dry_run
        is_write = any(tok in cmd for tok in ("deploy", "call", "send"))

        if is_dry and is_write:
            logger.info("[DRY_RUN] Would execute: %s", " ".join(cmd))
            return {"dry_run": True, "cmd": " ".join(cmd)}

        logger.debug("Executing: %s", " ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=60, check=False)
            if result.returncode != 0:
                logger.error("Command failed (rc=%d): %s\nstderr: %s",
                             result.returncode, " ".join(cmd), result.stderr.strip())
                return {"error": "command_failed", "returncode": result.returncode,
                        "stderr": result.stderr.strip()}
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            logger.error("Command timed out: %s", " ".join(cmd))
            return {"error": "timeout", "cmd": " ".join(cmd)}
        except json.JSONDecodeError:
            logger.error("Non-JSON output from: %s", " ".join(cmd))
            return {"error": "invalid_json", "stdout": result.stdout.strip()}
        except FileNotFoundError:
            logger.error("onchainos CLI not found on PATH")
            return {"error": "cli_not_found"}
        except OSError as exc:
            logger.error("OS error running command: %s", exc)
            return {"error": "os_error", "detail": str(exc)}
