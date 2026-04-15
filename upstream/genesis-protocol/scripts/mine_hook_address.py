#!/usr/bin/env python3
"""
Mine a CREATE2 salt for GenesisV4Hook deployment on X Layer Testnet.
The hook address must have bits 7 and 6 set in the last byte (& 0xC0 == 0xC0)
to indicate BEFORE_SWAP and AFTER_SWAP hook flags.

Steps:
1. Deploy HookDeployer factory (or use existing)
2. Get init code hash for GenesisV4Hook(poolManager, assembler)
3. Mine salt where CREATE2 address has correct flag bits
4. Deploy hook via factory with mined salt
"""

import subprocess
import sys
import json
import os
from Crypto.Hash import keccak

# ─── Configuration ────────────────────────────────────────────────────
RPC = "https://xlayertestrpc.okx.com"
PRIVATE_KEY = os.environ.get("PRIVATE_KEY", "")
POOL_MANAGER = "0x360e68faCCca8cA495c1B759Fd9EEe466dB9Fb32"
ASSEMBLER = "0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78"

CONTRACTS_DIR = "/workspace/genesis-protocol/contracts"
FOUNDRY_BIN = os.path.expanduser("~/.foundry/bin")
ENV = {**os.environ, "PATH": f"{FOUNDRY_BIN}:{os.environ.get('PATH', '')}"}

REQUIRED_MASK = 0xC0  # bits 7 and 6

# Set to None to deploy fresh, or set to existing address to skip deploy
EXISTING_DEPLOYER = None


def run_cmd(cmd, cwd=CONTRACTS_DIR, check=True):
    """Run a shell command and return stdout."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd, env=ENV
    )
    if check and result.returncode != 0:
        print(f"COMMAND FAILED: {cmd}")
        print(f"STDERR: {result.stderr}")
        print(f"STDOUT: {result.stdout}")
        sys.exit(1)
    return result.stdout.strip()


def keccak256(data: bytes) -> bytes:
    """Compute keccak256 hash."""
    k = keccak.new(digest_bits=256)
    k.update(data)
    return k.digest()


def compute_create2_address(deployer: str, salt_int: int, init_code_hash: bytes) -> str:
    """Compute CREATE2 address from deployer, salt, and init code hash."""
    deployer_bytes = bytes.fromhex(deployer[2:].lower())
    salt_bytes = salt_int.to_bytes(32, "big")
    data = b"\xff" + deployer_bytes + salt_bytes + init_code_hash
    addr_hash = keccak256(data)
    return "0x" + addr_hash[-20:].hex()


def parse_json_output(output):
    """Parse JSON from forge/cast output, skipping warning lines."""
    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    # Try parsing entire output as JSON
    return json.loads(output)


def main():
    if not PRIVATE_KEY:
        print("[ERROR] PRIVATE_KEY environment variable is not set.")
        sys.exit(1)

    print("=" * 60)
    print("GenesisV4Hook CREATE2 Address Mining & Deployment")
    print("=" * 60)

    # ─── Step 1: Deploy HookDeployer factory ──────────────────────────
    if EXISTING_DEPLOYER:
        deployer_address = EXISTING_DEPLOYER
        deployer_tx = "(pre-existing)"
        print(f"\n[1/4] Using existing HookDeployer at {deployer_address}")
    else:
        print("\n[1/4] Deploying HookDeployer factory...")
        output = run_cmd(
            f'forge create src/HookDeployer.sol:HookDeployer '
            f'--rpc-url {RPC} '
            f'--private-key {PRIVATE_KEY} '
            f'--broadcast --json'
        )
        deploy_result = parse_json_output(output)
        deployer_address = deploy_result["deployedTo"]
        deployer_tx = deploy_result["transactionHash"]
        print(f"  HookDeployer deployed at: {deployer_address}")
        print(f"  Transaction: {deployer_tx}")

    # ─── Step 2: Get init code hash ──────────────────────────────────
    print("\n[2/4] Computing init code hash...")

    artifact_path = os.path.join(
        CONTRACTS_DIR, "out", "GenesisV4Hook.sol", "GenesisV4Hook.json"
    )
    with open(artifact_path) as f:
        artifact = json.load(f)

    creation_bytecode = artifact["bytecode"]["object"]
    if not creation_bytecode.startswith("0x"):
        creation_bytecode = "0x" + creation_bytecode

    # ABI-encode constructor args: (IPoolManager, GenesisHookAssembler)
    pm_padded = POOL_MANAGER[2:].lower().zfill(64)
    asm_padded = ASSEMBLER[2:].lower().zfill(64)
    constructor_args = pm_padded + asm_padded

    # Full init code = creation bytecode + constructor args
    init_code_hex = creation_bytecode[2:] + constructor_args
    init_code_bytes = bytes.fromhex(init_code_hex)
    init_code_hash = keccak256(init_code_bytes)

    print(f"  Init code length: {len(init_code_bytes)} bytes")
    print(f"  Init code hash: 0x{init_code_hash.hex()}")

    # ─── Step 3: Mine salt ───────────────────────────────────────────
    print("\n[3/4] Mining salt for address with BEFORE_SWAP | AFTER_SWAP flags...")
    print(f"  Required: last byte & 0x{REQUIRED_MASK:02X} == 0x{REQUIRED_MASK:02X}")
    print(f"  Deployer: {deployer_address}")

    found_salt = None
    found_address = None

    for salt in range(10_000_000):
        addr = compute_create2_address(deployer_address, salt, init_code_hash)
        last_byte = int(addr[-2:], 16)
        if last_byte & REQUIRED_MASK == REQUIRED_MASK:
            found_salt = salt
            found_address = addr
            break

        if salt % 100_000 == 0 and salt > 0:
            print(f"  ... checked {salt:,} salts")

    if found_salt is None:
        print("ERROR: No valid salt found in 10M attempts!")
        sys.exit(1)

    print(f"  Found salt: {found_salt}")
    print(f"  Hook address: {found_address}")
    last_byte = int(found_address[-2:], 16)
    print(f"  Last byte: 0x{last_byte:02X} (BEFORE_SWAP={'YES' if last_byte & 0x80 else 'NO'}, AFTER_SWAP={'YES' if last_byte & 0x40 else 'NO'})")

    # Verify with on-chain computeAddress
    salt_hex = "0x" + found_salt.to_bytes(32, "big").hex()
    print(f"\n  Verifying with on-chain computeAddress...")
    onchain_addr = run_cmd(
        f'cast call {deployer_address} '
        f'"computeAddress(address,address,bytes32)(address)" '
        f'{POOL_MANAGER} {ASSEMBLER} {salt_hex} '
        f'--rpc-url {RPC}'
    )
    onchain_addr = onchain_addr.strip()
    print(f"  On-chain computed address: {onchain_addr}")

    if onchain_addr.lower() != found_address.lower():
        print("WARNING: Address mismatch! On-chain vs local computation differ.")
        print(f"  Local:    {found_address}")
        print(f"  On-chain: {onchain_addr}")
        found_address = onchain_addr
        last_byte_check = int(found_address[-2:], 16)
        if last_byte_check & REQUIRED_MASK != REQUIRED_MASK:
            print("ERROR: On-chain address does not have correct flags!")
            sys.exit(1)
        print("  On-chain address still has correct flags, proceeding.")

    # ─── Step 4: Deploy hook via factory ─────────────────────────────
    print(f"\n[4/4] Deploying GenesisV4Hook via HookDeployer with salt {found_salt}...")
    output = run_cmd(
        f'cast send {deployer_address} '
        f'"deploy(address,address,bytes32)" '
        f'{POOL_MANAGER} {ASSEMBLER} {salt_hex} '
        f'--rpc-url {RPC} '
        f'--private-key {PRIVATE_KEY} '
        f'--json'
    )

    tx_result = parse_json_output(output)
    deploy_tx_hash = tx_result.get("transactionHash", "unknown")
    status = tx_result.get("status", "unknown")

    print(f"  Transaction: {deploy_tx_hash}")
    print(f"  Status: {status}")

    # ─── Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("DEPLOYMENT SUMMARY")
    print("=" * 60)
    print(f"  Network:            X Layer Testnet")
    print(f"  HookDeployer:       {deployer_address}")
    print(f"  HookDeployer TX:    {deployer_tx}")
    print(f"  Salt:               {found_salt} ({salt_hex})")
    print(f"  GenesisV4Hook:      {found_address}")
    print(f"  Hook Deploy TX:     {deploy_tx_hash}")
    print(f"  Status:             {status}")
    print(f"  PoolManager:        {POOL_MANAGER}")
    print(f"  Assembler:          {ASSEMBLER}")
    last_b = int(found_address[-2:], 16)
    print(f"  Address last byte:  0x{last_b:02X}")
    print(f"  BEFORE_SWAP flag:   {'SET' if last_b & 0x80 else 'NOT SET'}")
    print(f"  AFTER_SWAP flag:    {'SET' if last_b & 0x40 else 'NOT SET'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
