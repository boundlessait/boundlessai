#!/usr/bin/env python3
"""
Deploy GuardLog.sol to X Layer testnet using web3.py + py-solc-x.

Requirements:
    pip install web3 py-solc-x

Usage:
    export DEPLOYER_PRIVATE_KEY=0x...
    python contracts/deploy_contract.py
"""

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Lazy imports with helpful error messages
# ---------------------------------------------------------------------------

def _require(pkg, install_name=None):
    import importlib
    try:
        return importlib.import_module(pkg)
    except ImportError:
        name = install_name or pkg
        print(f"Missing dependency: {name}. Install with: pip install {name}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
SOL_FILE = SCRIPT_DIR / "GuardLog.sol"
OUTPUT_FILE = SCRIPT_DIR / "deployed.json"

RPC_URL = os.environ.get("XLAYER_RPC_URL", "https://testrpc.xlayer.tech")
CHAIN_ID = int(os.environ.get("XLAYER_CHAIN_ID", "1952"))  # X Layer testnet = 1952, mainnet = 196
PRIVATE_KEY = os.environ.get("DEPLOYER_PRIVATE_KEY", "")

GUARD_LOG_ABI = [
    {
        "inputs": [],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "internalType": "bytes32", "name": "agentId",   "type": "bytes32"},
            {"indexed": False, "internalType": "uint256", "name": "amount",    "type": "uint256"},
            {"indexed": True,  "internalType": "uint8",   "name": "action",    "type": "uint8"},
            {"indexed": True,  "internalType": "bytes32", "name": "domain",    "type": "bytes32"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"}
        ],
        "name": "GuardDecision",
        "type": "event"
    },
    {
        "inputs": [
            {"internalType": "string", "name": "agentId", "type": "string"},
            {"internalType": "uint256","name": "amount",  "type": "uint256"},
            {"internalType": "uint8",  "name": "action",  "type": "uint8"},
            {"internalType": "string", "name": "domain",  "type": "string"}
        ],
        "name": "logDecision",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "getStats",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"},
            {"internalType": "uint256", "name": "", "type": "uint256"},
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalApproved",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalBlocked",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalSoftAlerts",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "guardian",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "newGuardian", "type": "address"}],
        "name": "transferGuardian",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]


# ---------------------------------------------------------------------------
# Compile
# ---------------------------------------------------------------------------

def compile_contract():
    """Compile GuardLog.sol and return (abi, bytecode)."""
    solcx = _require("solcx", "py-solc-x")

    source = SOL_FILE.read_text()

    # Install the required compiler version if not already present
    try:
        solcx.install_solc("0.8.20")
    except Exception as e:
        print(f"Warning: could not auto-install solc 0.8.20: {e}", file=sys.stderr)

    compiled = solcx.compile_source(
        source,
        output_values=["abi", "bin"],
        solc_version="0.8.20",
        optimize=True,
        optimize_runs=200,
    )

    # The key is like "<stdin>:GuardLog"
    contract_id = next(k for k in compiled if "GuardLog" in k)
    iface = compiled[contract_id]
    return iface["abi"], iface["bin"]


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

def deploy():
    if not PRIVATE_KEY:
        print("ERROR: DEPLOYER_PRIVATE_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    web3_mod = _require("web3")
    Web3 = web3_mod.Web3

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print(f"ERROR: Cannot connect to RPC at {RPC_URL}", file=sys.stderr)
        sys.exit(1)

    account = w3.eth.account.from_key(PRIVATE_KEY)
    deployer_address = account.address
    balance = w3.eth.get_balance(deployer_address)

    print(f"Connected to {RPC_URL} (chainId={CHAIN_ID})")
    print(f"Deployer: {deployer_address}")
    print(f"Balance : {w3.from_wei(balance, 'ether')} OKB")

    if balance == 0:
        print("WARNING: deployer balance is 0. The transaction may fail.")

    print("\nCompiling GuardLog.sol...")
    abi, bytecode = compile_contract()
    print("Compilation OK")

    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    nonce = w3.eth.get_transaction_count(deployer_address)
    gas_price = w3.eth.gas_price

    # Build constructor tx
    construct_txn = Contract.constructor().build_transaction({
        "chainId": CHAIN_ID,
        "from": deployer_address,
        "nonce": nonce,
        "gasPrice": gas_price,
    })

    # Estimate gas
    try:
        construct_txn["gas"] = w3.eth.estimate_gas(construct_txn)
    except Exception as e:
        print(f"Gas estimation failed ({e}), using fallback 500000", file=sys.stderr)
        construct_txn["gas"] = 500_000

    print(f"\nSending deployment tx (gas={construct_txn['gas']}, gasPrice={gas_price})...")
    signed = account.sign_transaction(construct_txn)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hex = tx_hash.hex()
    print(f"Tx hash: {tx_hex}")
    print("Waiting for receipt...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    contract_address = receipt["contractAddress"]

    print(f"\nDeployed at: {contract_address}")
    print(f"Block      : {receipt['blockNumber']}")
    print(f"Gas used   : {receipt['gasUsed']}")
    print(f"Status     : {'SUCCESS' if receipt['status'] == 1 else 'FAILED'}")
    explorer_base = "https://www.oklink.com/xlayer-test" if CHAIN_ID == 1952 else "https://www.oklink.com/xlayer"
    print(f"Explorer   : {explorer_base}/address/{contract_address}")

    # Save to deployed.json
    output = {
        "contract": "GuardLog",
        "address": contract_address,
        "txHash": tx_hex,
        "network": "xlayer-testnet",
        "chainId": CHAIN_ID,
        "rpcUrl": RPC_URL,
        "explorerUrl": f"{explorer_base}/address/{contract_address}",
        "blockNumber": receipt["blockNumber"],
        "abi": abi,
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2))
    print(f"\nSaved to {OUTPUT_FILE}")

    return contract_address, tx_hex


if __name__ == "__main__":
    deploy()
