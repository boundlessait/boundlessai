#!/usr/bin/env python3
"""Setup Agentic Wallet for the Genesis Protocol hackathon project.

Creates the Agentic Wallet as the project's on-chain identity on X Layer,
registers 5 role-based sub-wallets, and verifies registration via OKX Web3 API.

Usage:
    python3 scripts/setup_agentic_wallet.py
"""

import sys
import os
import json
import logging

# Ensure the project root is on sys.path so skills.genesis.scripts is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from skills.genesis.scripts.wallet_manager import WalletManager
from skills.genesis.scripts import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("setup_agentic_wallet")

DIVIDER = "-" * 60


def main():
    print()
    print(DIVIDER)
    print("  Genesis Protocol - Agentic Wallet Setup")
    print(DIVIDER)
    print()
    print(f"  Wallet Address : {config.AGENTIC_WALLET}")
    print(f"  Chain          : X Layer (chainIndex {config.MAINNET_CHAIN_ID})")
    print(f"  DRY_RUN        : {config.DRY_RUN}")
    print(f"  Sub-wallets    : {len(config.WALLET_ROLES)}")
    print()

    # --- Step 1: Initialize WalletManager ---
    logger.info("Initializing WalletManager...")
    wm = WalletManager()
    print(f"[1/4] WalletManager initialized (credentials={'present' if wm._has_credentials else 'MISSING'})")
    print()

    # --- Step 2: Create Agentic Wallet ---
    logger.info("Creating Agentic Wallet via OKX API...")
    create_result = wm.create_agentic_wallet()
    print("[2/4] Create Agentic Wallet result:")
    print(f"      {json.dumps(create_result, indent=6, default=str)}")
    print()

    # --- Step 3: Setup 5 role-based sub-wallets ---
    logger.info("Setting up role-based sub-wallets...")
    sub_results = wm.setup_sub_wallets()
    print("[3/4] Sub-wallet setup results:")
    for role, result in sub_results.items():
        idx = config.WALLET_ROLES[role]["index"]
        purpose = config.WALLET_ROLES[role]["purpose"]
        if result.get("status") == "fallback":
            status = f"DEFERRED: {result.get('message', 'APIs unavailable')}"
        elif "error" not in result and result.get("code") in (None, "0", 0):
            status = "OK"
        else:
            status = f"ERROR: {result.get('error') or result.get('msg', 'unknown')}"
        print(f"      [{idx}] {role:<12} {status:<20} -- {purpose}")
    print()

    # --- Step 4: Verify registration ---
    logger.info("Verifying wallet registration...")
    verify_result = wm.verify_wallet_registration()
    print("[4/4] Verification result:")
    print(f"      Status: {verify_result.get('status', 'unknown')}")
    print(f"      Address: {verify_result.get('address', 'N/A')}")
    if verify_result.get("initialized_roles"):
        print(f"      Initialized roles: {verify_result['initialized_roles']}")
    print()

    # --- Summary ---
    print(DIVIDER)
    print("  Wallet Addresses")
    print(DIVIDER)
    print(f"  Agentic Wallet : {wm.agentic_wallet_address}")
    for role, meta in config.WALLET_ROLES.items():
        addr = wm.sub_wallet_addresses.get(role, "(pending API response)")
        print(f"  [{meta['index']}] {role:<12} : {addr}")
    print()
    print(DIVIDER)
    print("  Setup complete.")
    print(DIVIDER)
    print()


if __name__ == "__main__":
    main()
