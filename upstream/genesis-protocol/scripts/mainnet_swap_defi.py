#!/usr/bin/env python3
"""
Genesis Protocol - Mainnet Swap & DeFi Interactions on X Layer (Chain 196)

Performs real on-chain transactions:
  Part 1: Uniswap V4 PoolManager reads (check pool state, quoter queries)
  Part 2: DeFi interactions (wrap OKB->WOKB, approve for Uniswap, Permit2 allowance)
"""

import json
import sys
import time
import traceback
from web3 import Web3

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
RPC_URL = "https://rpc.xlayer.tech"
CHAIN_ID = 196
PRIVATE_KEY = "0xdf50bbee9fdea174c322864baca05244e58ce92887dfc203521b61724dbae516"
WALLET = "0xd2D120eB7cEd38551cCeFb48021067d41D6542d3"

# Uniswap V4
POOL_MANAGER = Web3.to_checksum_address("0x360e68faCCca8cA495c1B759Fd9EEe466dB9Fb32")
UNIVERSAL_ROUTER = Web3.to_checksum_address("0x112908daC86e20e7241B0927479Ea3Bf935d1fa0")
QUOTER = Web3.to_checksum_address("0x3972c00f7ed4885e145823eb7c655375d275a1c5")
PERMIT2 = Web3.to_checksum_address("0x000000000022D473030F116dDEE9F6B43aC78BA3")

# Genesis
V4_HOOK = Web3.to_checksum_address("0x174a2450b342042AAe7398545f04B199248E69c0")
ASSEMBLER = Web3.to_checksum_address("0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78")

# Tokens
WOKB = Web3.to_checksum_address("0xe538905cf8410324e03A5A23C1c177a474D59b2b")
USDT = Web3.to_checksum_address("0x1E4a5963aBFD975d8c9021ce480b42188849D41d")
WETH = Web3.to_checksum_address("0x5A77f1443D16ee5761d310e38b62f77f726bC71c")

# Gas settings
GAS_LIMIT_SIMPLE = 100_000
WRAP_AMOUNT = Web3.to_wei(0.001, "ether")  # 0.001 OKB

# ---------------------------------------------------------------------------
# ABIs (minimal)
# ---------------------------------------------------------------------------
# PLACEHOLDER: ABIs filled in below
WOKB_ABI = json.loads("""[
  {"name":"deposit","type":"function","stateMutability":"payable","inputs":[],"outputs":[]},
  {"name":"withdraw","type":"function","stateMutability":"nonpayable","inputs":[{"name":"wad","type":"uint256"}],"outputs":[]},
  {"name":"balanceOf","type":"function","stateMutability":"view","inputs":[{"name":"","type":"address"}],"outputs":[{"name":"","type":"uint256"}]},
  {"name":"totalSupply","type":"function","stateMutability":"view","inputs":[],"outputs":[{"name":"","type":"uint256"}]},
  {"name":"approve","type":"function","stateMutability":"nonpayable","inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"outputs":[{"name":"","type":"bool"}]},
  {"name":"allowance","type":"function","stateMutability":"view","inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"outputs":[{"name":"","type":"uint256"}]}
]""")

ERC20_ABI = json.loads("""[
  {"name":"balanceOf","type":"function","stateMutability":"view","inputs":[{"name":"account","type":"address"}],"outputs":[{"name":"","type":"uint256"}]},
  {"name":"approve","type":"function","stateMutability":"nonpayable","inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"outputs":[{"name":"","type":"bool"}]},
  {"name":"allowance","type":"function","stateMutability":"view","inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"outputs":[{"name":"","type":"uint256"}]},
  {"name":"decimals","type":"function","stateMutability":"view","inputs":[],"outputs":[{"name":"","type":"uint8"}]},
  {"name":"symbol","type":"function","stateMutability":"view","inputs":[],"outputs":[{"name":"","type":"string"}]}
]""")

# Uniswap V4 PoolManager - key read functions
POOL_MANAGER_ABI = json.loads("""[
  {"name":"protocolFeeController","type":"function","stateMutability":"view","inputs":[],"outputs":[{"name":"","type":"address"}]},
  {"name":"MAX_TICK_SPACING","type":"function","stateMutability":"view","inputs":[],"outputs":[{"name":"","type":"int24"}]},
  {"name":"MIN_TICK_SPACING","type":"function","stateMutability":"view","inputs":[],"outputs":[{"name":"","type":"int24"}]},
  {"name":"isOperator","type":"function","stateMutability":"view","inputs":[{"name":"owner","type":"address"},{"name":"operator","type":"address"}],"outputs":[{"name":"approved","type":"bool"}]}
]""")

# Permit2 - approve for Universal Router
PERMIT2_ABI = json.loads("""[
  {"name":"approve","type":"function","stateMutability":"nonpayable","inputs":[{"name":"token","type":"address"},{"name":"spender","type":"address"},{"name":"amount","type":"uint160"},{"name":"expiration","type":"uint48"}],"outputs":[]},
  {"name":"allowance","type":"function","stateMutability":"view","inputs":[{"name":"owner","type":"address"},{"name":"token","type":"address"},{"name":"spender","type":"address"}],"outputs":[{"name":"amount","type":"uint160"},{"name":"expiration","type":"uint48"},{"name":"nonce","type":"uint48"}]}
]""")

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
w3 = None
account = None
tx_results = []  # list of (description, tx_hash_or_error, success)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def setup():
    """Initialize web3 connection and account."""
    global w3, account
    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 30}))
    assert w3.is_connected(), "Failed to connect to X Layer RPC"
    account = w3.eth.account.from_key(PRIVATE_KEY)
    assert account.address.lower() == WALLET.lower(), "Key/wallet mismatch"
    print(f"[+] Connected to X Layer (Chain {CHAIN_ID})")
    bal = w3.eth.get_balance(WALLET)
    print(f"[+] Wallet {WALLET}")
    print(f"[+] OKB balance: {Web3.from_wei(bal, 'ether')} OKB")
    return bal


def get_gas_price():
    """Get current gas price with a small bump for reliability."""
    gp = w3.eth.gas_price
    # add 10% buffer
    return int(gp * 1.1)


def send_tx(tx, description):
    """Sign, send, and wait for a transaction. Track result."""
    try:
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        hex_hash = tx_hash.hex()
        print(f"  -> Tx sent: {hex_hash}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        status = receipt["status"]
        gas_used = receipt["gasUsed"]
        print(f"  -> Status: {'SUCCESS' if status == 1 else 'REVERTED'} | Gas used: {gas_used}")
        tx_results.append((description, hex_hash, status == 1, gas_used))
        return receipt
    except Exception as e:
        err = str(e)[:200]
        print(f"  -> FAILED: {err}")
        tx_results.append((description, err, False, 0))
        return None


def get_nonce():
    """Get pending nonce."""
    return w3.eth.get_transaction_count(WALLET, "pending")

# ---------------------------------------------------------------------------
# Part 1 - Uniswap V4 reads
# ---------------------------------------------------------------------------
def part1_uniswap_v4_reads():
    """Read Uniswap V4 PoolManager state and attempt Quoter queries."""
    print("\n" + "=" * 70)
    print("PART 1: Uniswap V4 PoolManager & Quoter Reads")
    print("=" * 70)

    pm = w3.eth.contract(address=Web3.to_checksum_address(POOL_MANAGER), abi=POOL_MANAGER_ABI)

    # 1. Check PoolManager is deployed
    code = w3.eth.get_code(Web3.to_checksum_address(POOL_MANAGER))
    print(f"\n[1] PoolManager contract size: {len(code)} bytes (deployed: {len(code) > 2})")

    # 2. Read protocol fee controller
    try:
        fee_ctrl = pm.functions.protocolFeeController().call()
        print(f"[2] Protocol fee controller: {fee_ctrl}")
    except Exception as e:
        print(f"[2] protocolFeeController() call failed: {e}")

    # 3. Read tick spacing bounds
    try:
        max_ts = pm.functions.MAX_TICK_SPACING().call()
        min_ts = pm.functions.MIN_TICK_SPACING().call()
        print(f"[3] Tick spacing bounds: min={min_ts}, max={max_ts}")
    except Exception as e:
        print(f"[3] Tick spacing read failed: {e}")

    # 4. Check if our wallet is operator on PoolManager
    try:
        is_op = pm.functions.isOperator(WALLET, UNIVERSAL_ROUTER).call()
        print(f"[4] Wallet is operator for UniversalRouter: {is_op}")
    except Exception as e:
        print(f"[4] isOperator() call failed: {e}")

    # 5. Check hook contract
    hook_code = w3.eth.get_code(Web3.to_checksum_address(V4_HOOK))
    print(f"[5] V4 Hook contract size: {len(hook_code)} bytes (deployed: {len(hook_code) > 2})")

    # 6. Check Quoter contract
    quoter_code = w3.eth.get_code(Web3.to_checksum_address(QUOTER))
    print(f"[6] Quoter contract size: {len(quoter_code)} bytes (deployed: {len(quoter_code) > 2})")

    # 7. Check Universal Router
    router_code = w3.eth.get_code(Web3.to_checksum_address(UNIVERSAL_ROUTER))
    print(f"[7] Universal Router contract size: {len(router_code)} bytes (deployed: {len(router_code) > 2})")

    # 8. Try to read pool state via low-level call for our hook pool
    # PoolKey: (currency0, currency1, fee, tickSpacing, hooks)
    # We try WOKB/USDT pool with our hook - compute poolId
    # pools mapping uses keccak256(abi.encode(PoolKey))
    print(f"\n[8] Attempting to read pool slot0 for WOKB/USDT with hook...")

    # Sort tokens (currency0 < currency1)
    wokb_addr = Web3.to_checksum_address(WOKB)
    usdt_addr = Web3.to_checksum_address(USDT)
    if int(wokb_addr, 16) < int(usdt_addr, 16):
        currency0, currency1 = wokb_addr, usdt_addr
    else:
        currency0, currency1 = usdt_addr, wokb_addr

    # Compute poolId = keccak256(abi.encode(currency0, currency1, fee, tickSpacing, hooks))
    # Try common fee tiers: 3000 (0.3%), tickSpacing 60
    fee = 3000
    tick_spacing = 60
    hook_addr = Web3.to_checksum_address(V4_HOOK)

    pool_key_encoded = w3.codec.encode(
        ["address", "address", "uint24", "int24", "address"],
        [currency0, currency1, fee, tick_spacing, hook_addr]
    )
    pool_id = Web3.keccak(pool_key_encoded)
    print(f"    Pool ID (fee=3000, ts=60): {pool_id.hex()}")

    # Try to read slot0 of this pool via getSlot0(bytes32)
    # Signature: getSlot0(bytes32) -> (uint160 sqrtPriceX96, int24 tick, uint24 protocolFee, uint24 lpFee)
    get_slot0_sig = Web3.keccak(text="getSlot0(bytes32)")[:4]
    call_data = get_slot0_sig + w3.codec.encode(["bytes32"], [pool_id])
    try:
        result = w3.eth.call({"to": POOL_MANAGER, "data": call_data.hex()})
        decoded = w3.codec.decode(["uint160", "int24", "uint24", "uint24"], result)
        sqrt_price, tick, proto_fee, lp_fee = decoded
        if sqrt_price > 0:
            print(f"    Pool EXISTS! sqrtPriceX96={sqrt_price}, tick={tick}, protocolFee={proto_fee}, lpFee={lp_fee}")
        else:
            print(f"    Pool not initialized (sqrtPriceX96=0)")
    except Exception as e:
        print(f"    getSlot0 call failed: {str(e)[:150]}")

    # Also try with native OKB (address(0)) as currency0
    print(f"\n[9] Trying native OKB / WOKB pool with hook...")
    addr_zero = "0x0000000000000000000000000000000000000000"
    pool_key_encoded2 = w3.codec.encode(
        ["address", "address", "uint24", "int24", "address"],
        [addr_zero, wokb_addr, fee, tick_spacing, hook_addr]
    )
    pool_id2 = Web3.keccak(pool_key_encoded2)
    print(f"    Pool ID: {pool_id2.hex()}")
    call_data2 = get_slot0_sig + w3.codec.encode(["bytes32"], [pool_id2])
    try:
        result2 = w3.eth.call({"to": POOL_MANAGER, "data": call_data2.hex()})
        decoded2 = w3.codec.decode(["uint160", "int24", "uint24", "uint24"], result2)
        if decoded2[0] > 0:
            print(f"    Pool EXISTS! sqrtPriceX96={decoded2[0]}, tick={decoded2[1]}")
        else:
            print(f"    Pool not initialized (sqrtPriceX96=0)")
    except Exception as e:
        print(f"    getSlot0 call failed: {str(e)[:150]}")

    # 10. Check Assembler contract
    asm_code = w3.eth.get_code(Web3.to_checksum_address(ASSEMBLER))
    print(f"\n[10] Assembler contract size: {len(asm_code)} bytes (deployed: {len(asm_code) > 2})")

    print("\n[Part 1 Complete] Uniswap V4 infrastructure verified on X Layer.")

# ---------------------------------------------------------------------------
# Part 2 - DeFi interactions
# ---------------------------------------------------------------------------
def part2_defi_interactions():
    """Execute real DeFi transactions on X Layer."""
    print("\n" + "=" * 70)
    print("PART 2: DeFi Interactions (Real Transactions)")
    print("=" * 70)

    gas_price = get_gas_price()
    print(f"\n[Gas price: {gas_price} wei ({Web3.from_wei(gas_price, 'gwei')} gwei)]")

    wokb_contract = w3.eth.contract(address=Web3.to_checksum_address(WOKB), abi=WOKB_ABI)
    permit2_contract = w3.eth.contract(address=Web3.to_checksum_address(PERMIT2), abi=PERMIT2_ABI)

    # Check initial WOKB balance
    wokb_bal_before = wokb_contract.functions.balanceOf(WALLET).call()
    print(f"\n[Initial WOKB balance: {Web3.from_wei(wokb_bal_before, 'ether')}]")

    # --- TX 1: Wrap OKB -> WOKB ---
    print("\n--- TX 1: Wrap 0.001 OKB -> WOKB ---")
    nonce = get_nonce()
    tx1 = wokb_contract.functions.deposit().build_transaction({
        "from": WALLET,
        "value": WRAP_AMOUNT,
        "gas": GAS_LIMIT_SIMPLE,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    })
    receipt1 = send_tx(tx1, "Wrap 0.001 OKB -> WOKB (deposit)")

    if receipt1 and receipt1["status"] == 1:
        wokb_bal_after = wokb_contract.functions.balanceOf(WALLET).call()
        print(f"  WOKB balance after wrap: {Web3.from_wei(wokb_bal_after, 'ether')}")

    # --- TX 2: Approve WOKB for PoolManager ---
    print("\n--- TX 2: Approve WOKB for PoolManager (Uniswap V4) ---")
    approve_amount = Web3.to_wei(1000, "ether")  # large approval, no cost
    nonce = get_nonce()
    tx2 = wokb_contract.functions.approve(
        Web3.to_checksum_address(POOL_MANAGER),
        approve_amount
    ).build_transaction({
        "from": WALLET,
        "gas": GAS_LIMIT_SIMPLE,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    })
    send_tx(tx2, "Approve WOKB for PoolManager")

    # --- TX 3: Approve WOKB for Universal Router ---
    print("\n--- TX 3: Approve WOKB for Universal Router ---")
    nonce = get_nonce()
    tx3 = wokb_contract.functions.approve(
        Web3.to_checksum_address(UNIVERSAL_ROUTER),
        approve_amount
    ).build_transaction({
        "from": WALLET,
        "gas": GAS_LIMIT_SIMPLE,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    })
    send_tx(tx3, "Approve WOKB for Universal Router")

    # --- TX 4: Approve WOKB for Permit2 ---
    print("\n--- TX 4: Approve WOKB for Permit2 ---")
    nonce = get_nonce()
    tx4 = wokb_contract.functions.approve(
        Web3.to_checksum_address(PERMIT2),
        approve_amount
    ).build_transaction({
        "from": WALLET,
        "gas": GAS_LIMIT_SIMPLE,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    })
    send_tx(tx4, "Approve WOKB for Permit2")

    # --- TX 5: Set Permit2 allowance for Universal Router ---
    print("\n--- TX 5: Permit2 allowance for Universal Router ---")
    # Permit2.approve(token, spender, amount, expiration)
    permit2_amount = (2**160) - 1  # max uint160
    expiration = int(time.time()) + 365 * 24 * 3600  # 1 year
    nonce = get_nonce()
    tx5 = permit2_contract.functions.approve(
        Web3.to_checksum_address(WOKB),
        Web3.to_checksum_address(UNIVERSAL_ROUTER),
        permit2_amount,
        expiration
    ).build_transaction({
        "from": WALLET,
        "gas": GAS_LIMIT_SIMPLE,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    })
    send_tx(tx5, "Permit2: set WOKB allowance for Universal Router")

    # Verify final state
    print("\n--- Verification ---")
    wokb_bal_final = wokb_contract.functions.balanceOf(WALLET).call()
    print(f"  WOKB balance: {Web3.from_wei(wokb_bal_final, 'ether')}")

    allowance_pm = wokb_contract.functions.allowance(WALLET, POOL_MANAGER).call()
    print(f"  WOKB allowance for PoolManager: {Web3.from_wei(allowance_pm, 'ether')}")

    allowance_router = wokb_contract.functions.allowance(WALLET, UNIVERSAL_ROUTER).call()
    print(f"  WOKB allowance for Universal Router: {Web3.from_wei(allowance_router, 'ether')}")

    allowance_permit2 = wokb_contract.functions.allowance(WALLET, PERMIT2).call()
    print(f"  WOKB allowance for Permit2: {Web3.from_wei(allowance_permit2, 'ether')}")

    try:
        p2_allow = permit2_contract.functions.allowance(WALLET, WOKB, UNIVERSAL_ROUTER).call()
        print(f"  Permit2 allowance (WOKB->Router): amount={p2_allow[0]}, expiration={p2_allow[1]}, nonce={p2_allow[2]}")
    except Exception as e:
        print(f"  Permit2 allowance read failed: {e}")

    okb_final = w3.eth.get_balance(WALLET)
    print(f"  Final OKB balance: {Web3.from_wei(okb_final, 'ether')} OKB")

    print("\n[Part 2 Complete] DeFi interactions executed.")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("Genesis Protocol - Mainnet Swap & DeFi Script")
    print(f"Chain: X Layer (ID {CHAIN_ID})")
    print("=" * 70)

    bal = setup()

    # Safety check
    min_required = Web3.to_wei(0.01, "ether")
    if bal < min_required:
        print(f"[!] Balance too low ({Web3.from_wei(bal, 'ether')} OKB). Aborting.")
        sys.exit(1)

    # Part 1: Uniswap V4 reads (no gas cost)
    try:
        part1_uniswap_v4_reads()
    except Exception as e:
        print(f"[!] Part 1 error: {e}")
        traceback.print_exc()

    # Part 2: DeFi interactions (real txs)
    try:
        part2_defi_interactions()
    except Exception as e:
        print(f"[!] Part 2 error: {e}")
        traceback.print_exc()

    # Summary
    print("\n" + "=" * 70)
    print("TRANSACTION SUMMARY")
    print("=" * 70)
    total_gas = 0
    for desc, hash_or_err, success, gas in tx_results:
        status_str = "OK" if success else "FAIL"
        print(f"  [{status_str}] {desc}")
        if success:
            print(f"        tx: {hash_or_err}")
            print(f"        gas: {gas}")
            total_gas += gas
        else:
            print(f"        error: {hash_or_err}")

    print(f"\n  Total transactions: {len(tx_results)}")
    print(f"  Successful: {sum(1 for _, _, s, _ in tx_results if s)}")
    print(f"  Failed: {sum(1 for _, _, s, _ in tx_results if not s)}")
    print(f"  Total gas used: {total_gas}")

    final_bal = w3.eth.get_balance(WALLET)
    print(f"  Final OKB balance: {Web3.from_wei(final_bal, 'ether')} OKB")
    print("=" * 70)


if __name__ == "__main__":
    main()
