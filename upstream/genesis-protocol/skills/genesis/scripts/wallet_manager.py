"""Wallet Manager - Agentic Wallet sub-wallets on X Layer (chainId 196).

Supports two modes of operation:
  1. OKX Web3 REST API with HMAC-SHA256 authentication (primary)
  2. onchainos CLI via subprocess (fallback)

Respects DRY_RUN for all write operations.
"""

import base64
import hashlib
import hmac
import subprocess
import json
import logging
import os
from datetime import datetime, timezone

try:
    import requests as _requests
except ImportError:
    _requests = None

from . import config

logger = logging.getLogger(__name__)

# OKX Web3 API base URL for wallet operations
WEB3_BASE_URL = "https://web3.okx.com"

# API credentials must be provided via environment variables:
#   OK_ACCESS_KEY, OK_ACCESS_SECRET, OK_ACCESS_PASSPHRASE
# No default credentials are stored in source code for security.


class WalletManager:
    """Manages onchainos sub-wallets mapped to operational roles.

    Provides both OKX Web3 API-based wallet creation and CLI fallback.
    The API methods (create_agentic_wallet, setup_sub_wallets,
    verify_wallet_registration) use HMAC-SHA256 signed requests following
    the same authentication pattern as OnchainOSAPI.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
        base_url: str = WEB3_BASE_URL,
    ):
        """Initialize wallet manager from config.WALLET_ROLES.

        Args:
            api_key:    OKX API key. Falls back to OK_ACCESS_KEY env var, then default.
            api_secret: OKX secret key. Falls back to OK_ACCESS_SECRET env var, then default.
            passphrase: OKX passphrase. Falls back to OK_ACCESS_PASSPHRASE env var, then default.
            base_url:   OKX Web3 API base URL.
        """
        self.roles = config.WALLET_ROLES
        self.initialized: set[str] = set()

        # API credentials: constructor > env vars (no hardcoded defaults)
        self.api_key = api_key or os.environ.get("OK_ACCESS_KEY", "")
        self.api_secret = api_secret or os.environ.get("OK_ACCESS_SECRET", "")
        self.passphrase = passphrase or os.environ.get("OK_ACCESS_PASSPHRASE", "")
        self.base_url = base_url.rstrip("/")
        self._has_credentials = bool(
            self.api_key and self.api_secret and self.passphrase
        )

        # Wallet state populated by create/setup methods
        self.agentic_wallet_address: str = config.AGENTIC_WALLET
        self.sub_wallet_addresses: dict[str, str] = {}

        logger.info("WalletManager created with roles: %s", list(self.roles.keys()))

    # ── HMAC-SHA256 Authentication ────────────────────────────────────────

    def _sign(self, method: str, request_path: str, body: str = "") -> dict:
        """Build HMAC-SHA256 signed headers for an OKX Web3 API request.

        Follows the same signing convention as onchainos_api.OnchainOSAPI._sign.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        message = timestamp + method.upper() + request_path + body
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

    def _api_request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        body: dict | None = None,
    ) -> dict | None:
        """Execute an authenticated REST request against OKX Web3 API.

        Returns parsed JSON response dict, or None on failure.
        """
        if not self._has_credentials:
            logger.debug("No API credentials; skipping REST request %s %s", method, path)
            return None
        if _requests is None:
            logger.error("requests library not installed; cannot call OKX API")
            return None

        request_path = path
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            request_path = path + "?" + qs

        body_str = json.dumps(body) if body else ""
        headers = self._sign(method.upper(), request_path, body_str)
        url = self.base_url + request_path

        try:
            if method.upper() == "GET":
                resp = _requests.get(url, headers=headers, timeout=30)
            else:
                resp = _requests.post(url, headers=headers, data=body_str, timeout=30)
            data = resp.json()
            logger.debug("API %s %s -> %s", method, path, data.get("code", "ok"))
            return data
        except Exception as exc:
            logger.error("API error for %s %s: %s", method, path, exc)
        return None

    @staticmethod
    def _is_api_error(result: dict | None) -> bool:
        """Return True if *result* represents an API-level failure.

        Detects both connection failures (None) and HTTP/API error responses
        (non-zero ``code``, presence of ``error_code``, or HTTP status errors).
        """
        if result is None:
            return True
        code = result.get("code")
        if code is not None and str(code) != "0":
            return True
        if "error_code" in result or "error" in result:
            return True
        if result.get("status") == "fallback":
            return True
        return False

    # ── Agentic Wallet Setup (OKX Web3 API) ───────────────────────────────

    def create_agentic_wallet(self) -> dict:
        """Register this project's Agentic Wallet with the OnchainOS API.

        Calls POST /api/v5/wallet/account/create-wallet to register the
        wallet derived from the project private key as an Agentic Wallet
        on X Layer (chainIndex 196).

        Returns:
            API response dict with wallet registration details, or an
            error dict if the call failed.
        """
        logger.info(
            "Creating Agentic Wallet for address %s on chain %s",
            self.agentic_wallet_address, config.MAINNET_CHAIN_ID,
        )

        if config.DRY_RUN:
            logger.info("[DRY_RUN] Would create Agentic Wallet via API")
            return {
                "dry_run": True,
                "action": "create_agentic_wallet",
                "address": self.agentic_wallet_address,
                "chain_index": str(config.MAINNET_CHAIN_ID),
            }

        body = {
            "addresses": [
                {
                    "chainIndex": str(config.MAINNET_CHAIN_ID),
                    "address": self.agentic_wallet_address,
                }
            ],
        }
        result = self._api_request(
            "POST", "/api/v5/wallet/account/create-wallet", body=body,
        )
        if self._is_api_error(result):
            api_detail = result if result is not None else {}
            logger.info(
                "API returned error (code=%s); falling back to onchainos CLI",
                api_detail.get("code", "N/A"),
            )
            cli_result = self._run_cmd([
                "onchainos", "wallet", "create",
                "--address", self.agentic_wallet_address,
                "--chain", str(config.MAINNET_CHAIN_ID),
            ])
            # If CLI also fails, return a graceful fallback result
            if "error" in cli_result:
                logger.warning(
                    "Both API and CLI failed for create_agentic_wallet; "
                    "returning fallback result"
                )
                return {
                    "status": "fallback",
                    "action": "create_agentic_wallet",
                    "address": self.agentic_wallet_address,
                    "chain_index": str(config.MAINNET_CHAIN_ID),
                    "api_error": api_detail.get("msg") or api_detail.get("error", "unavailable"),
                    "cli_error": cli_result.get("error", "unknown"),
                    "message": "Wallet registration deferred - APIs unavailable",
                }
            return cli_result
        return result

    def setup_sub_wallets(self) -> dict[str, dict]:
        """Create the 5 role-based sub-wallets for the Agentic Wallet.

        Iterates over WALLET_ROLES (master, strategy, income, reserve,
        rebalance) and registers each via the OKX Web3 API
        POST /api/v5/wallet/account/create-sub-wallet.

        Returns:
            Dict mapping role name to API response for each sub-wallet.
        """
        logger.info("Setting up %d role-based sub-wallets", len(self.roles))
        results: dict[str, dict] = {}

        for role, meta in self.roles.items():
            idx = meta["index"]
            purpose = meta["purpose"]
            logger.info(
                "Creating sub-wallet: role=%s index=%d purpose='%s'",
                role, idx, purpose,
            )

            if config.DRY_RUN:
                logger.info("[DRY_RUN] Would create sub-wallet role=%s index=%d", role, idx)
                results[role] = {
                    "dry_run": True,
                    "action": "create_sub_wallet",
                    "role": role,
                    "index": idx,
                    "purpose": purpose,
                }
                self.initialized.add(role)
                continue

            body = {
                "walletAddress": self.agentic_wallet_address,
                "chainIndex": str(config.MAINNET_CHAIN_ID),
                "subWalletIndex": str(idx),
                "label": role,
                "purpose": purpose,
            }
            result = self._api_request(
                "POST", "/api/v5/wallet/account/create-sub-wallet", body=body,
            )
            if self._is_api_error(result):
                api_detail = result if result is not None else {}
                logger.info(
                    "API error for sub-wallet %s (code=%s); trying CLI fallback",
                    role, api_detail.get("code", "N/A"),
                )
                cli_result = self._run_cmd([
                    "onchainos", "wallet", "create-sub",
                    "--index", str(idx),
                    "--label", role,
                ])
                if "error" in cli_result:
                    # Both API and CLI unavailable - record graceful fallback
                    logger.warning(
                        "Both API and CLI failed for sub-wallet %s; "
                        "recording fallback",
                        role,
                    )
                    result = {
                        "status": "fallback",
                        "action": "create_sub_wallet",
                        "role": role,
                        "index": idx,
                        "api_error": api_detail.get("msg") or api_detail.get("error", "unavailable"),
                        "cli_error": cli_result.get("error", "unknown"),
                        "message": f"Sub-wallet '{role}' registration deferred",
                    }
                else:
                    result = cli_result

            if result and not self._is_api_error(result):
                self.initialized.add(role)
                # Store address if returned
                addr = (
                    result.get("data", {}).get("address")
                    if isinstance(result.get("data"), dict)
                    else None
                )
                if addr:
                    self.sub_wallet_addresses[role] = addr

            results[role] = result or {"error": "no_response", "role": role}

        return results

    def verify_wallet_registration(self) -> dict:
        """Verify that the Agentic Wallet is properly registered on-chain.

        Calls GET /api/v5/wallet/account/wallet-info to confirm the
        wallet exists and retrieve its current state, including any
        registered sub-wallets.

        Returns:
            API response dict with wallet registration status, or an
            error dict if verification failed.
        """
        logger.info(
            "Verifying wallet registration for %s", self.agentic_wallet_address,
        )

        params = {
            "address": self.agentic_wallet_address,
            "chainIndex": str(config.MAINNET_CHAIN_ID),
        }
        result = self._api_request(
            "GET", "/api/v5/wallet/account/wallet-info", params=params,
        )
        if result is None:
            logger.info("API unavailable for verification; falling back to CLI")
            cli_result = self._run_cmd([
                "onchainos", "wallet", "info",
                "--address", self.agentic_wallet_address,
            ])
            if "error" in cli_result:
                logger.warning(
                    "Both API and CLI unavailable for verification; "
                    "returning deferred status"
                )
                return {
                    "status": "deferred",
                    "address": self.agentic_wallet_address,
                    "chain_index": str(config.MAINNET_CHAIN_ID),
                    "initialized_roles": list(self.initialized),
                    "message": "Verification deferred - APIs unavailable",
                }
            return cli_result

        # Check for successful response
        if result.get("code") == "0":
            logger.info("Wallet registration verified successfully")
            return {
                "status": "verified",
                "address": self.agentic_wallet_address,
                "chain_index": str(config.MAINNET_CHAIN_ID),
                "data": result.get("data"),
                "initialized_roles": list(self.initialized),
            }

        logger.warning(
            "Wallet verification returned code=%s msg=%s",
            result.get("code"), result.get("msg"),
        )
        return {
            "status": "unverified",
            "address": self.agentic_wallet_address,
            "initialized_roles": list(self.initialized),
            "api_response": result,
        }

    # ── Public API (CLI-based operations) ─────────────────────────────────

    def initialize_wallets(self) -> dict[str, dict]:
        """Create a sub-wallet for every defined role.

        Returns a dict mapping role names to their creation results.
        """
        results: dict[str, dict] = {}
        for role, meta in self.roles.items():
            idx = meta["index"]
            logger.info("Creating sub-wallet role=%s index=%d", role, idx)
            out = self._run_cmd([
                "onchainos", "wallet", "create-sub",
                "--index", str(idx),
                "--label", role,
            ])
            if "error" not in out:
                self.initialized.add(role)
            results[role] = out
        return results

    def get_wallet_address(self, role: str) -> dict:
        """Return the on-chain address for *role*.

        Args:
            role: A key from WALLET_ROLES (e.g. 'master', 'strategy').
        """
        idx = self._role_index(role)
        if idx is None:
            return {"error": f"Unknown role: {role}"}
        return self._run_cmd([
            "onchainos", "wallet", "address",
            "--index", str(idx),
        ])

    def get_balance(self, role: str, token: str = "native") -> dict:
        """Query the balance for *role*.

        Args:
            role:  Wallet role name.
            token: Token symbol or 'native' for OKB gas token.
        """
        idx = self._role_index(role)
        if idx is None:
            return {"error": f"Unknown role: {role}"}
        return self._run_cmd([
            "onchainos", "wallet", "balance",
            "--index", str(idx),
            "--token", token,
        ])

    def transfer(
        self,
        from_role: str,
        to_role: str,
        amount: str,
        token: str = "OKB",
    ) -> dict:
        """Transfer *amount* of *token* between two sub-wallets.

        Args:
            from_role: Source wallet role.
            to_role:   Destination wallet role.
            amount:    Human-readable amount (e.g. '1.5').
            token:     Token symbol (default OKB).
        """
        from_idx = self._role_index(from_role)
        to_idx = self._role_index(to_role)
        if from_idx is None or to_idx is None:
            return {"error": f"Invalid role(s): {from_role}, {to_role}"}

        logger.info(
            "Transfer %s %s: %s (idx %d) -> %s (idx %d)",
            amount, token, from_role, from_idx, to_role, to_idx,
        )
        return self._run_cmd([
            "onchainos", "wallet", "transfer",
            "--from-index", str(from_idx),
            "--to-index", str(to_idx),
            "--amount", str(amount),
            "--token", token,
        ])

    def fund_strategy_wallet(self, amount: str, token: str = "USDT") -> dict:
        """Move funds from master wallet to strategy wallet.

        Args:
            amount: Human-readable amount to transfer.
            token:  Token symbol (default USDT).
        """
        logger.info("Funding strategy wallet: %s %s", amount, token)
        return self.transfer("master", "strategy", amount, token=token)

    def collect_income(self) -> dict:
        """Sweep the full balance of the income wallet back to master.

        Queries the income wallet balance first, then transfers if non-zero.
        """
        logger.info("Collecting income -> master")
        bal = self.get_balance("income", token="USDT")
        amount = bal.get("balance", bal.get("amount", "0"))
        if float(amount) <= 0:
            logger.info("Income wallet empty, nothing to collect")
            return {"status": "empty", "amount": "0"}
        return self.transfer("income", "master", str(amount), token="USDT")

    def get_all_balances(self) -> dict[str, dict]:
        """Return a balance snapshot for every wallet role.

        Returns:
            Dict keyed by role name, each value is the balance response.
        """
        balances: dict[str, dict] = {}
        for role in self.roles:
            balances[role] = self.get_balance(role)
        return balances

    # ── Internal Helpers ─────────────────────────────────────────────────

    def _role_index(self, role: str) -> int | None:
        """Resolve a role name to its sub-wallet index."""
        meta = self.roles.get(role)
        return meta["index"] if meta else None

    def _run_cmd(self, cmd: list[str], dry_run: bool | None = None) -> dict:
        """Execute an onchainos CLI command and return parsed JSON.

        Args:
            cmd:     Command tokens (e.g. ['onchainos', 'wallet', 'balance', ...]).
            dry_run: Override config.DRY_RUN for this call. None = use config.

        Returns:
            Parsed JSON dict from stdout, or an error dict on failure.
        """
        is_dry = config.DRY_RUN if dry_run is None else dry_run
        is_write = any(
            tok in cmd for tok in ("create-sub", "transfer", "deploy", "send")
        )

        if is_dry and is_write:
            logger.info("[DRY_RUN] Would execute: %s", " ".join(cmd))
            return {"dry_run": True, "cmd": " ".join(cmd)}

        logger.debug("Executing: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode != 0:
                logger.error(
                    "Command failed (rc=%d): %s\nstderr: %s",
                    result.returncode, " ".join(cmd), result.stderr.strip(),
                )
                return {
                    "error": "command_failed",
                    "returncode": result.returncode,
                    "stderr": result.stderr.strip(),
                }
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
