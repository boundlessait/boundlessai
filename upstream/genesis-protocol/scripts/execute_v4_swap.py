#!/usr/bin/env python3
"""
Genesis Protocol - V4 Swap Execution Script
============================================
Deploys test tokens, initializes a Uniswap V4 pool with the GenesisV4Hook,
adds liquidity, executes a swap, and verifies hook state on X Layer Testnet.

Usage:
    python scripts/execute_v4_swap.py

Requirements:
    - foundry (forge, cast) installed and on PATH
    - Network access to X Layer Testnet RPC
"""

import subprocess
import sys
import os
import json
import time

# ─── Configuration ───────────────────────────────────────────────────────────

RPC_URL = "https://xlayertestrpc.okx.com"
CHAIN_ID = 195  # X Layer Testnet chain ID
PRIVATE_KEY = os.environ.get("PRIVATE_KEY", "")
WALLET = os.environ.get("WALLET_ADDRESS", "")

# Deployed contracts
POOL_MANAGER = "0x360e68faCCca8cA495c1B759Fd9EEe466dB9Fb32"
GENESIS_HOOK = "0x79a96bB2Ab2342cf6f1dD3c622F5CB01f9F7A8d4"
ASSEMBLER = "0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78"
DYNAMIC_FEE_MODULE = "0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed"
MEV_PROTECTION_MODULE = "0xA4f6ABd6F77928b06F075637ccBACA8f89e17386"
AUTO_REBALANCE_MODULE = "0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee"

# Paths
CONTRACTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts")
SCRIPT_CONTRACT = "script/V4Swap.sol:V4Swap"


def run_command(cmd, cwd=None, env=None, check=True):
    """Run a shell command and return stdout."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    print(f"\n>>> {cmd}")
    result = subprocess.run(
        cmd, shell=True, cwd=cwd, env=merged_env,
        capture_output=True, text=True
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        sys.exit(1)
    return result.stdout.strip()


def cast_call(to, sig, args="", rpc=RPC_URL):
    """Execute a cast call (read-only) and return the result."""
    cmd = f'cast call {to} "{sig}" {args} --rpc-url {rpc}'
    return run_command(cmd, check=False)


def cast_send(to, sig, args="", value="", private_key=PRIVATE_KEY, rpc=RPC_URL):
    """Execute a cast send (write tx) and return the result."""
    value_flag = f"--value {value}" if value else ""
    cmd = (
        f'cast send {to} "{sig}" {args} '
        f'--private-key {private_key} --rpc-url {rpc} {value_flag} '
        f'--gas-limit 5000000'
    )
    return run_command(cmd)


def check_prerequisites():
    """Verify forge and cast are available."""
    print("=== Checking prerequisites ===")
    for tool in ["forge", "cast"]:
        result = subprocess.run(
            [tool, "--version"], capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Error: {tool} not found. Please install Foundry.")
            sys.exit(1)
        print(f"  {tool}: {result.stdout.strip()}")


def check_wallet_balance():
    """Check the deployer wallet balance on X Layer Testnet."""
    print("\n=== Checking wallet balance ===")
    balance = run_command(
        f"cast balance {WALLET} --rpc-url {RPC_URL}", check=False
    )
    print(f"  Wallet: {WALLET}")
    print(f"  Balance: {balance} wei")
    if balance and int(balance) == 0:
        print("WARNING: Wallet has 0 balance. Transactions will fail.")
        print("Please fund the wallet with X Layer Testnet OKB.")
    return balance


def verify_deployed_contracts():
    """Verify that the Genesis contracts are deployed on-chain."""
    print("\n=== Verifying deployed contracts ===")
    contracts = {
        "PoolManager": POOL_MANAGER,
        "GenesisV4Hook": GENESIS_HOOK,
        "GenesisHookAssembler": ASSEMBLER,
        "DynamicFeeModule": DYNAMIC_FEE_MODULE,
    }
    all_ok = True
    for name, addr in contracts.items():
        code = run_command(
            f"cast code {addr} --rpc-url {RPC_URL}", check=False
        )
        has_code = code and code != "0x" and len(code) > 2
        status = "OK" if has_code else "NOT DEPLOYED"
        print(f"  {name} ({addr}): {status}")
        if not has_code:
            all_ok = False
    return all_ok


def run_forge_script():
    """Execute the full V4 swap flow via forge script."""
    print("\n=== Running V4 Swap via forge script ===")
    print("This will:")
    print("  1. Deploy two test ERC20 tokens")
    print("  2. Initialize a V4 pool with GenesisV4Hook")
    print("  3. Deploy helper contracts (LiquidityHelper, SwapRouter)")
    print("  4. Add liquidity to the pool")
    print("  5. Execute a swap through the hook")
    print("  6. Verify hook state\n")

    env = {
        "PRIVATE_KEY": PRIVATE_KEY,
    }

    cmd = (
        f"forge script {SCRIPT_CONTRACT} "
        f"--rpc-url {RPC_URL} "
        f"--broadcast "
        f"--slow "  # wait for each tx to be mined
        f"-vvvv"    # verbose output for debugging
    )

    output = run_command(cmd, cwd=CONTRACTS_DIR, env=env)
    return output


def verify_hook_state():
    """Verify the hook was called by checking assembler state."""
    print("\n=== Verifying Hook State (post-swap) ===")

    # Check totalSwapsProcessed
    swaps = cast_call(ASSEMBLER, "totalSwapsProcessed()(uint256)")
    print(f"  totalSwapsProcessed: {swaps}")

    # Check totalVolumeProcessed
    volume = cast_call(ASSEMBLER, "totalVolumeProcessed()(uint256)")
    print(f"  totalVolumeProcessed: {volume}")

    # Check assembler owner
    owner = cast_call(ASSEMBLER, "owner()(address)")
    print(f"  Assembler owner: {owner}")

    # Check hook's poolManager
    pm = cast_call(GENESIS_HOOK, "poolManager()(address)")
    print(f"  Hook poolManager: {pm}")

    # Check hook's assembler
    asm = cast_call(GENESIS_HOOK, "assembler()(address)")
    print(f"  Hook assembler: {asm}")

    # Check active strategy
    strat = cast_call(GENESIS_HOOK, "activeStrategyId()(uint256)")
    print(f"  Hook activeStrategyId: {strat}")

    return swaps, volume


def run_step_by_step():
    """
    Alternative: run each step individually using cast send.
    Useful if the forge script approach fails or for more granular control.
    """
    print("\n=== Step-by-step execution via cast ===")

    # Step 1: Deploy TestTokenA
    print("\n--- Step 1: Deploying TestTokenA ---")
    # We use forge create for deploying contracts
    token_a_output = run_command(
        f'forge create --rpc-url {RPC_URL} --private-key {PRIVATE_KEY} '
        f'script/V4Swap.sol:TestToken '
        f'--constructor-args "Genesis Test A" "GTA" 1000000000000000000000000',
        cwd=CONTRACTS_DIR
    )
    # Parse deployed address from output
    token_a_addr = None
    for line in token_a_output.split("\n"):
        if "Deployed to:" in line:
            token_a_addr = line.split("Deployed to:")[-1].strip()
            break
    if not token_a_addr:
        print("Failed to parse TestTokenA address")
        sys.exit(1)
    print(f"  TestTokenA: {token_a_addr}")

    # Step 2: Deploy TestTokenB
    print("\n--- Step 2: Deploying TestTokenB ---")
    token_b_output = run_command(
        f'forge create --rpc-url {RPC_URL} --private-key {PRIVATE_KEY} '
        f'script/V4Swap.sol:TestToken '
        f'--constructor-args "Genesis Test B" "GTB" 1000000000000000000000000',
        cwd=CONTRACTS_DIR
    )
    token_b_addr = None
    for line in token_b_output.split("\n"):
        if "Deployed to:" in line:
            token_b_addr = line.split("Deployed to:")[-1].strip()
            break
    if not token_b_addr:
        print("Failed to parse TestTokenB address")
        sys.exit(1)
    print(f"  TestTokenB: {token_b_addr}")

    # Sort tokens
    if int(token_a_addr, 16) < int(token_b_addr, 16):
        currency0, currency1 = token_a_addr, token_b_addr
    else:
        currency0, currency1 = token_b_addr, token_a_addr
    print(f"  Currency0: {currency0}")
    print(f"  Currency1: {currency1}")

    # Step 3: Initialize pool on PoolManager
    # PoolKey: (currency0, currency1, fee=0x800000, tickSpacing=60, hooks=GENESIS_HOOK)
    # sqrtPriceX96 = 79228162514264337593543950336
    print("\n--- Step 3: Initializing V4 Pool ---")
    # Encode PoolKey as tuple
    pool_key_tuple = f"({currency0},{currency1},0x800000,60,{GENESIS_HOOK})"
    sqrt_price = "79228162514264337593543950336"

    cast_send(
        POOL_MANAGER,
        "initialize((address,address,uint24,int24,address),uint160)",
        f"{pool_key_tuple} {sqrt_price}"
    )
    print("  Pool initialized!")

    # Step 4: Deploy SwapRouter
    print("\n--- Step 4: Deploying SwapRouter ---")
    router_output = run_command(
        f'forge create --rpc-url {RPC_URL} --private-key {PRIVATE_KEY} '
        f'script/V4Swap.sol:SwapRouter '
        f'--constructor-args {POOL_MANAGER}',
        cwd=CONTRACTS_DIR
    )
    router_addr = None
    for line in router_output.split("\n"):
        if "Deployed to:" in line:
            router_addr = line.split("Deployed to:")[-1].strip()
            break
    print(f"  SwapRouter: {router_addr}")

    # Step 5: Deploy LiquidityHelper
    print("\n--- Step 5: Deploying LiquidityHelper ---")
    liq_output = run_command(
        f'forge create --rpc-url {RPC_URL} --private-key {PRIVATE_KEY} '
        f'script/V4Swap.sol:LiquidityHelper '
        f'--constructor-args {POOL_MANAGER}',
        cwd=CONTRACTS_DIR
    )
    liq_addr = None
    for line in liq_output.split("\n"):
        if "Deployed to:" in line:
            liq_addr = line.split("Deployed to:")[-1].strip()
            break
    print(f"  LiquidityHelper: {liq_addr}")

    # Step 6: Approve tokens
    print("\n--- Step 6: Approving tokens ---")
    max_uint = "115792089237316195423570985008687907853269984665640564039457584007913129639935"
    for token in [currency0, currency1]:
        for spender in [liq_addr, router_addr]:
            cast_send(token, "approve(address,uint256)", f"{spender} {max_uint}")
    print("  All approvals set.")

    # Step 7: Add liquidity
    print("\n--- Step 7: Adding liquidity ---")
    liquidity_delta = "100000000000000000000000"  # 100_000e18
    cast_send(
        liq_addr,
        "addLiquidity((address,address,uint24,int24,address),int24,int24,int256,address)",
        f"{pool_key_tuple} -6000 6000 {liquidity_delta} {WALLET}"
    )
    print("  Liquidity added!")

    # Step 8: Execute swap
    print("\n--- Step 8: Executing swap ---")
    # SwapParams: (zeroForOne=true, amountSpecified=-1e18, sqrtPriceLimitX96=MIN_SQRT_PRICE+1)
    min_sqrt_price_plus_1 = "4295128740"  # TickMath.MIN_SQRT_PRICE + 1
    swap_amount = "-1000000000000000000"  # -1e18 (exactIn)
    swap_params = f"(true,{swap_amount},{min_sqrt_price_plus_1})"

    # Call swap on the router - it handles the unlock callback
    # Note: The router's swap function takes PoolKey and SwapParams
    cast_send(
        router_addr,
        "swap((address,address,uint24,int24,address),(bool,int256,uint160))",
        f"{pool_key_tuple} {swap_params}"
    )
    print("  Swap executed!")

    # Step 9: Verify
    print("\n--- Step 9: Verifying hook state ---")
    verify_hook_state()

    return True


def main():
    if not PRIVATE_KEY:
        print("ERROR: PRIVATE_KEY environment variable is not set.")
        print("Export it before running: export PRIVATE_KEY=0x...")
        sys.exit(1)
    if not WALLET:
        print("ERROR: WALLET_ADDRESS environment variable is not set.")
        print("Export it before running: export WALLET_ADDRESS=0x...")
        sys.exit(1)

    print("=" * 60)
    print("  Genesis Protocol - Uniswap V4 Swap Execution")
    print("  Chain: X Layer Testnet")
    print("=" * 60)

    check_prerequisites()
    check_wallet_balance()

    contracts_ok = verify_deployed_contracts()
    if not contracts_ok:
        print("\nWARNING: Some contracts are not deployed.")
        print("The script will attempt to proceed but may fail.\n")

    # Try forge script first (all-in-one approach)
    mode = os.environ.get("SWAP_MODE", "forge")

    if mode == "cast":
        print("\nUsing step-by-step cast mode...")
        run_step_by_step()
    else:
        print("\nUsing forge script mode...")
        try:
            run_forge_script()
        except SystemExit:
            print("\nForge script failed. Falling back to step-by-step mode...")
            run_step_by_step()

    # Final verification
    print("\n" + "=" * 60)
    print("  Final Hook State Verification")
    print("=" * 60)
    swaps, volume = verify_hook_state()

    print("\n" + "=" * 60)
    if swaps and int(swaps) > 0:
        print("  SUCCESS: Hook was triggered during the swap!")
    else:
        print("  NOTE: Check totalSwapsProcessed - hook may need an active strategy.")
        print("  Ensure GenesisV4Hook.setActiveStrategy() was called with a valid strategy ID.")
    print("=" * 60)


if __name__ == "__main__":
    main()
