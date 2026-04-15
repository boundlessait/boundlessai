#!/usr/bin/env python3
"""
Genesis Protocol - Full V4 Hook Deployment on X Layer Mainnet
1. Deploy HookDeployer factory
2. Mine CREATE2 salt for correct hook flag bits (BEFORE_SWAP | AFTER_SWAP)
3. Deploy GenesisV4Hook via factory
4. Run V4Swap script to create pool, add liquidity, execute swaps
"""

import subprocess
import sys
import json
import os
from Crypto.Hash import keccak

# ─── Configuration ────────────────────────────────────────────────────
RPC = "https://rpc.xlayer.tech"
PRIVATE_KEY = os.environ.get("PRIVATE_KEY", "")
POOL_MANAGER = "0x360e68faCCca8cA495c1B759Fd9EEe466dB9Fb32"
ASSEMBLER = "0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78"

CONTRACTS_DIR = "/workspace/genesis-protocol/contracts"
FOUNDRY_BIN = os.path.expanduser("~/.foundry/bin")
ENV = {**os.environ, "PATH": f"{FOUNDRY_BIN}:{os.environ.get('PATH', '')}"}

REQUIRED_MASK = 0xC0  # bits 7 (BEFORE_SWAP) and 6 (AFTER_SWAP)


def run_cmd(cmd, cwd=CONTRACTS_DIR, check=True):
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd, env=ENV, timeout=300
    )
    if check and result.returncode != 0:
        print(f"COMMAND FAILED: {cmd}")
        print(f"STDERR: {result.stderr[:500]}")
        print(f"STDOUT: {result.stdout[:500]}")
        sys.exit(1)
    return result.stdout.strip()


def keccak256(data: bytes) -> bytes:
    k = keccak.new(digest_bits=256)
    k.update(data)
    return k.digest()


def compute_create2_address(deployer: str, salt_int: int, init_code_hash: bytes) -> str:
    deployer_bytes = bytes.fromhex(deployer[2:].lower())
    salt_bytes = salt_int.to_bytes(32, "big")
    data = b"\xff" + deployer_bytes + salt_bytes + init_code_hash
    addr_hash = keccak256(data)
    return "0x" + addr_hash[-20:].hex()


def parse_json_output(output):
    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    return json.loads(output)


def main():
    if not PRIVATE_KEY:
        print("[ERROR] PRIVATE_KEY not set.")
        sys.exit(1)

    print("=" * 60)
    print("  Genesis V4 Hook - X Layer Mainnet Deployment")
    print("  Chain 196 | PoolManager:", POOL_MANAGER)
    print("=" * 60)

    # Build first
    print("\n[0/4] Building contracts...")
    run_cmd("forge build")

    # ─── Step 1: Deploy HookDeployer ──────────────────────────────
    print("\n[1/4] Deploying HookDeployer factory to mainnet...")
    output = run_cmd(
        f'forge create src/HookDeployer.sol:HookDeployer '
        f'--rpc-url {RPC} '
        f'--private-key {PRIVATE_KEY} '
        f'--broadcast --json'
    )
    deploy_result = parse_json_output(output)
    deployer_address = deploy_result["deployedTo"]
    print(f"  HookDeployer: {deployer_address}")

    # ─── Step 2: Compute init code hash ───────────────────────────
    print("\n[2/4] Computing init code hash...")
    artifact_path = os.path.join(CONTRACTS_DIR, "out", "GenesisV4Hook.sol", "GenesisV4Hook.json")
    with open(artifact_path) as f:
        artifact = json.load(f)

    creation_bytecode = artifact["bytecode"]["object"]
    if not creation_bytecode.startswith("0x"):
        creation_bytecode = "0x" + creation_bytecode

    pm_padded = POOL_MANAGER[2:].lower().zfill(64)
    asm_padded = ASSEMBLER[2:].lower().zfill(64)
    constructor_args = pm_padded + asm_padded

    init_code_hex = creation_bytecode[2:] + constructor_args
    init_code_bytes = bytes.fromhex(init_code_hex)
    init_code_hash = keccak256(init_code_bytes)
    print(f"  Init code: {len(init_code_bytes)} bytes")
    print(f"  Hash: 0x{init_code_hash.hex()}")

    # ─── Step 3: Mine salt ────────────────────────────────────────
    print("\n[3/4] Mining CREATE2 salt (BEFORE_SWAP | AFTER_SWAP flags)...")
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

    last_byte = int(found_address[-2:], 16)
    print(f"  Salt: {found_salt}")
    print(f"  Hook address: {found_address}")
    print(f"  Last byte: 0x{last_byte:02X} (BEFORE_SWAP={bool(last_byte & 0x80)}, AFTER_SWAP={bool(last_byte & 0x40)})")

    # ─── Step 4: Deploy Hook via factory ──────────────────────────
    salt_hex = "0x" + found_salt.to_bytes(32, "big").hex()
    print(f"\n[4/4] Deploying GenesisV4Hook via HookDeployer...")
    output = run_cmd(
        f'cast send {deployer_address} '
        f'"deploy(address,address,bytes32)" '
        f'{POOL_MANAGER} {ASSEMBLER} {salt_hex} '
        f'--rpc-url {RPC} '
        f'--private-key {PRIVATE_KEY} '
        f'--json'
    )
    tx_result = parse_json_output(output)
    print(f"  TX: {tx_result.get('transactionHash', 'unknown')}")
    print(f"  Status: {tx_result.get('status', 'unknown')}")

    # Verify the hook was deployed
    print("\n  Verifying hook deployment...")
    code_output = run_cmd(
        f'cast code {found_address} --rpc-url {RPC}',
        check=False
    )
    has_code = code_output.strip() != "0x" and len(code_output.strip()) > 4
    print(f"  Hook has code: {has_code}")

    # ─── Summary ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  DEPLOYMENT SUMMARY")
    print(f"{'='*60}")
    print(f"  Network:          X Layer Mainnet (Chain 196)")
    print(f"  HookDeployer:     {deployer_address}")
    print(f"  GenesisV4Hook:    {found_address}")
    print(f"  PoolManager:      {POOL_MANAGER}")
    print(f"  Assembler:        {ASSEMBLER}")
    print(f"  Salt:             {found_salt}")
    lb = int(found_address[-2:], 16)
    print(f"  BEFORE_SWAP:      {'SET' if lb & 0x80 else 'NOT SET'}")
    print(f"  AFTER_SWAP:       {'SET' if lb & 0x40 else 'NOT SET'}")
    print(f"{'='*60}")

    # Write the hook address to a file for the V4Swap script to use
    with open("/tmp/mainnet_hook_address.txt", "w") as f:
        f.write(found_address)
    with open("/tmp/mainnet_deployer_address.txt", "w") as f:
        f.write(deployer_address)

    return found_address, deployer_address


if __name__ == "__main__":
    main()
