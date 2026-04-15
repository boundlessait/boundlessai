"""NFT Minter - Mints Strategy NFTs when performance thresholds are met.
Uses onchainos CLI via subprocess for all on-chain interactions.
"""
import subprocess
import json
import logging
import time
import hashlib

from .config import (
    DRY_RUN, LOG_LEVEL,
    NFT_MINT_THRESHOLD_PNL_BPS, NFT_MINT_THRESHOLD_SWAPS,
    NFT_MINT_THRESHOLD_HOURS, CONTRACTS,
)

logger = logging.getLogger("genesis.nft_minter")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))


class NFTMinter:
    """Mints Strategy NFTs for strategies that meet performance thresholds."""

    def __init__(self, nft_contract="", assembler_address=""):
        self.nft_contract = nft_contract or CONTRACTS.get("strategy_nft", "")
        self.assembler = assembler_address or CONTRACTS.get("assembler", "")

    def check_mint_eligibility(self, strategy_data):
        """Check if strategy meets all thresholds. Returns (eligible, reasons)."""
        reasons = []
        pnl = strategy_data.get("pnl_bps", 0)
        swaps = strategy_data.get("total_swaps", 0)
        hours = strategy_data.get("run_hours", 0)
        if pnl < NFT_MINT_THRESHOLD_PNL_BPS:
            reasons.append(f"PnL {pnl} bps below threshold {NFT_MINT_THRESHOLD_PNL_BPS}")
        if swaps < NFT_MINT_THRESHOLD_SWAPS:
            reasons.append(f"Swaps {swaps} below threshold {NFT_MINT_THRESHOLD_SWAPS}")
        if hours < NFT_MINT_THRESHOLD_HOURS:
            reasons.append(f"Runtime {hours}h below threshold {NFT_MINT_THRESHOLD_HOURS}h")
        eligible = len(reasons) == 0
        if eligible:
            logger.info("Strategy eligible for NFT mint")
        else:
            logger.info("Strategy NOT eligible: %s", "; ".join(reasons))
        return eligible, reasons

    def mint_strategy_nft(self, to_address, strategy_snapshot):
        """Mint a Strategy NFT via onchainos CLI. Returns token_id or error dict."""
        args = self._format_mint_args(to_address, strategy_snapshot)
        cmd = [
            "onchainos", "wallet", "call",
            "--to", self.nft_contract,
            "--function", "mint(address,uint256,bytes32,uint256,uint256)",
            "--args", args,
        ]
        result = self._run_cmd(cmd)
        if result.get("error"):
            return result
        try:
            token_id = json.loads(result["stdout"]).get("token_id", result["stdout"])
            logger.info("Minted NFT token_id=%s to %s", token_id, to_address)
            return token_id
        except (json.JSONDecodeError, KeyError):
            return result.get("stdout", "")

    def get_strategy_snapshot(self, strategy_id):
        """Fetch a strategy snapshot from the assembler contract."""
        cmd = [
            "onchainos", "wallet", "call",
            "--to", self.assembler,
            "--function", "getStrategySnapshot(uint256)",
            "--args", str(strategy_id),
            "--read-only",
        ]
        result = self._run_cmd(cmd)
        if result.get("error"):
            return result
        try:
            return json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"raw": result["stdout"]}

    def compute_config_hash(self, modules, params):
        """Compute deterministic config hash (sha256, 0x-prefixed) matching on-chain logic."""
        canonical = json.dumps(
            {"modules": sorted(modules), "params": params},
            sort_keys=True, separators=(",", ":"),
        )
        return "0x" + hashlib.sha256(canonical.encode()).hexdigest()

    def get_total_supply(self):
        """Read totalSupply from the NFT contract."""
        cmd = [
            "onchainos", "wallet", "call",
            "--to", self.nft_contract,
            "--function", "totalSupply()",
            "--read-only",
        ]
        result = self._run_cmd(cmd)
        if result.get("error"):
            return -1
        try:
            return int(result["stdout"].strip())
        except ValueError:
            return -1

    def get_nft_metadata(self, token_id):
        """Read strategy metadata for a given NFT token."""
        cmd = [
            "onchainos", "wallet", "call",
            "--to", self.nft_contract,
            "--function", "strategyMetadata(uint256)",
            "--args", str(token_id),
            "--read-only",
        ]
        result = self._run_cmd(cmd)
        if result.get("error"):
            return result
        try:
            return json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"raw": result["stdout"]}

    def _run_cmd(self, cmd, dry_run=None):
        """Execute a subprocess command, respecting DRY_RUN config."""
        if dry_run is None:
            dry_run = DRY_RUN
        logger.debug("cmd: %s", " ".join(cmd))
        if dry_run:
            logger.info("[DRY_RUN] %s", " ".join(cmd))
            return {"stdout": '{"dry_run": true}'}
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                logger.error("Command failed (%d): %s", proc.returncode, proc.stderr)
                return {"error": proc.stderr or f"exit code {proc.returncode}"}
            return {"stdout": proc.stdout}
        except subprocess.TimeoutExpired:
            logger.error("Command timed out: %s", " ".join(cmd))
            return {"error": "timeout"}
        except FileNotFoundError:
            logger.error("onchainos CLI not found")
            return {"error": "onchainos CLI not found"}

    def _format_mint_args(self, to, snapshot):
        """Format arguments for the mint() call."""
        config_hash = self.compute_config_hash(
            snapshot.get("modules", []), snapshot.get("params", {}),
        )
        parts = [
            to,
            str(snapshot.get("strategy_id", 0)),
            config_hash,
            str(snapshot.get("pnl_bps", 0)),
            str(snapshot.get("total_swaps", 0)),
        ]
        return " ".join(parts)
