"""
OnchainLogger — fire-and-forget logging of guard decisions to GuardLog.sol
on X Layer testnet (or mainnet).

Environment variables (all optional — if missing, logging is silently skipped):
    GUARD_CONTRACT_ADDRESS  deployed GuardLog contract address
    GUARDIAN_PRIVATE_KEY    private key of the guardian wallet
    XLAYER_RPC_URL          defaults to https://testrpc.xlayer.tech
    XLAYER_CHAIN_ID         defaults to 1952 (testnet), use 196 for mainnet
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ABI — only the functions we call
# ---------------------------------------------------------------------------

_GUARDLOG_ABI = [
    {
        "inputs": [
            {"internalType": "string", "name": "agentId", "type": "string"},
            {"internalType": "uint256","name": "amount",  "type": "uint256"},
            {"internalType": "uint8",  "name": "action",  "type": "uint8"},
            {"internalType": "string", "name": "domain",  "type": "string"},
        ],
        "name": "logDecision",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getStats",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"},
            {"internalType": "uint256", "name": "", "type": "uint256"},
            {"internalType": "uint256", "name": "", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

# action string -> uint8 mapping
ACTION_MAP = {
    "approve":    0,
    "soft_alert": 1,
    "block":      2,
}


class OnchainLogger:
    """
    Logs guard decisions to GuardLog.sol on X Layer.

    Gracefully degrades: if CONTRACT_ADDRESS or GUARDIAN_PRIVATE_KEY are not
    set, every log_decision call is a no-op.
    """

    def __init__(self):
        self._contract_address: Optional[str] = os.environ.get("GUARD_CONTRACT_ADDRESS", "").strip() or None
        self._private_key: Optional[str] = os.environ.get("GUARDIAN_PRIVATE_KEY", "").strip() or None
        self._rpc_url: str = os.environ.get("XLAYER_RPC_URL", "https://testrpc.xlayer.tech")
        self._chain_id: int = int(os.environ.get("XLAYER_CHAIN_ID", "1952"))  # 1952=testnet, 196=mainnet

        self._w3 = None
        self._contract = None
        self._account = None
        self._nonce_lock = threading.Lock()  # Prevent concurrent nonce conflicts

        if self._contract_address and self._private_key:
            self._init_web3()
        else:
            logger.info(
                "OnchainLogger: GUARD_CONTRACT_ADDRESS or GUARDIAN_PRIVATE_KEY not set "
                "— onchain logging disabled"
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _init_web3(self):
        try:
            from web3 import Web3  # type: ignore

            w3 = Web3(Web3.HTTPProvider(self._rpc_url))
            account = w3.eth.account.from_key(self._private_key)
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(self._contract_address),
                abi=_GUARDLOG_ABI,
            )
            self._w3 = w3
            self._account = account
            self._contract = contract
            logger.info(
                "OnchainLogger: connected to %s, contract %s, guardian %s",
                self._rpc_url,
                self._contract_address,
                account.address,
            )
        except ImportError:
            logger.warning("OnchainLogger: web3 not installed — onchain logging disabled")
        except Exception as exc:
            logger.warning("OnchainLogger: init failed (%s) — onchain logging disabled", exc)

    def _is_ready(self) -> bool:
        return self._w3 is not None and self._contract is not None and self._account is not None

    def _send_log_decision(self, agent_id: str, amount: float, action_int: int, domain: str):
        """Blocking call — meant to be run in executor or a background task."""
        from web3 import Web3  # type: ignore

        w3 = self._w3
        account = self._account
        contract = self._contract

        amount_int = int(amount * 1_000_000)

        with self._nonce_lock:
            # Get nonce inside lock to prevent concurrent conflicts
            nonce = w3.eth.get_transaction_count(account.address, 'pending')
            gas_price = w3.eth.gas_price

            txn = contract.functions.logDecision(
                agent_id, amount_int, action_int, domain,
            ).build_transaction({
                "chainId": self._chain_id,
                "from": account.address,
                "nonce": nonce,
                "gasPrice": gas_price,
                "gas": 120_000,
            })

            signed = account.sign_transaction(txn)
            # web3.py v5 uses rawTransaction, v6 uses raw_transaction
            raw = getattr(signed, 'raw_transaction', None) or getattr(signed, 'rawTransaction', None)
            tx_hash = w3.eth.send_raw_transaction(raw)
        logger.info(
            "OnchainLogger: logged decision (action=%d, agent=%s, amount=%s, domain=%s) tx=%s",
            action_int, agent_id, amount, domain, tx_hash.hex()
        )
        return tx_hash.hex()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def log_decision(
        self,
        agent_id: str,
        amount: float,
        action: str,
        domain: str,
    ):
        """
        Fire-and-forget: log a guard decision to the blockchain.

        action must be one of: "approve", "soft_alert", "block"
        """
        if not self._is_ready():
            return

        action_int = ACTION_MAP.get(action, -1)
        if action_int == -1:
            logger.warning("OnchainLogger.log_decision: unknown action '%s'", action)
            return

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                self._send_log_decision,
                str(agent_id),
                float(amount),
                action_int,
                str(domain),
            )
        except Exception as exc:
            # Never propagate — this is best-effort logging
            logger.warning("OnchainLogger.log_decision failed: %s", exc)

    def get_onchain_stats(self) -> Tuple[int, int, int]:
        """
        Return (approved, soft_alerts, blocked) from the contract.
        Returns (0, 0, 0) if not configured or on any error.
        """
        if not self._is_ready():
            return (0, 0, 0)
        try:
            approved, soft_alerts, blocked = self._contract.functions.getStats().call()
            return (approved, soft_alerts, blocked)
        except Exception as exc:
            logger.warning("OnchainLogger.get_onchain_stats failed: %s", exc)
            return (0, 0, 0)

    @property
    def contract_address(self) -> Optional[str]:
        return self._contract_address

    @property
    def network(self) -> str:
        return "xlayer-testnet" if self._chain_id == 1952 else (
            "xlayer-mainnet" if self._chain_id == 196 else f"chain-{self._chain_id}"
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

onchain_logger = OnchainLogger()
