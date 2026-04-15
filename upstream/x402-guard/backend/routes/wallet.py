"""
Wallet balance routes — read-only queries to X Layer RPC.
No private keys handled here. Address-based only.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import logging
import os
import time

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wallet", tags=["wallet"])

RPC_URL  = os.environ.get("XLAYER_RPC_URL", "https://testrpc.xlayer.tech")
CHAIN_ID = int(os.environ.get("XLAYER_CHAIN_ID", "1952"))

# In-memory cache for /balances (30s TTL — RPC calls are slow)
_balances_cache: list = []
_balances_cache_ts: float = 0.0
_BALANCES_TTL = 30.0

# USDC/USDG on X Layer testnet
USDC_ADDRESS = os.environ.get("USDC_CONTRACT_ADDRESS", "0xcB8BF24c6cE16Ad21D707c9505421a17f2bec79D")

ERC20_BALANCE_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def _get_w3():
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 8}))
        return w3 if w3.is_connected() else None
    except Exception:
        return None


@router.get("/balance/{address}")
async def get_balance(address: str):
    """
    Return OKB (native) + USDC balance for a wallet address on X Layer.
    Used by dashboard to show real bot wallet balances.
    """
    try:
        w3 = _get_w3()
        if not w3:
            raise HTTPException(status_code=503, detail="RPC unavailable")

        # Validate address
        try:
            checksum = w3.to_checksum_address(address)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid address: {address}")

        # Native OKB balance
        wei = w3.eth.get_balance(checksum)
        okb = float(w3.from_wei(wei, "ether"))

        # USDC balance
        usdc = 0.0
        try:
            token = w3.eth.contract(
                address=w3.to_checksum_address(USDC_ADDRESS),
                abi=ERC20_BALANCE_ABI,
            )
            raw     = token.functions.balanceOf(checksum).call()
            decimals = token.functions.decimals().call()
            usdc    = raw / (10 ** decimals)
        except Exception as e:
            logger.warning("USDC balance failed: %s", e)

        # Get OKB price from OKX OnchainOS
        okb_usd_price = 0.0
        try:
            from okx_client import get_okb_usd_price
            okb_price = await get_okb_usd_price()
            if okb_price:
                okb_usd_price = okb_price
        except Exception:
            pass

        okb_usd_value = round(okb * okb_usd_price, 2) if okb_usd_price else None
        total_usd     = round((okb * okb_usd_price if okb_usd_price else 0) + usdc, 2)

        return {
            "address":       checksum,
            "network":       "xlayer-testnet" if CHAIN_ID == 1952 else "xlayer-mainnet",
            "chain_id":      CHAIN_ID,
            "okb":           round(okb,  8),
            "okb_usd_price": round(okb_usd_price, 4) if okb_usd_price else None,
            "okb_usd_value": okb_usd_value,
            "usdc":          round(usdc, 6),
            "total_usd":     total_usd,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_balance error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balances")
async def get_all_bot_balances():
    """
    Return balances for all registered bot wallets (from policies).
    Results are cached for 30s to avoid slow RPC calls on every dashboard poll.
    """
    global _balances_cache, _balances_cache_ts

    # Return cached result if still fresh
    if _balances_cache and (time.monotonic() - _balances_cache_ts) < _BALANCES_TTL:
        return _balances_cache

    from storage import load_policies

    policies = load_policies()
    results  = []

    w3 = _get_w3()
    if not w3:
        # Return stale cache if available rather than error
        if _balances_cache:
            return _balances_cache
        return JSONResponse({"error": "RPC unavailable"}, status_code=503)

    for p in policies:
        addr = p.get("wallet_address")
        if not addr:
            results.append({
                "agent_id":  p["agent_id"],
                "name":      p.get("name", p["agent_id"]),
                "bot_type":  p.get("bot_type"),
                "address":   None,
                "okb":       None,
                "usdc":      None,
                "total_usd": None,
            })
            continue

        try:
            checksum = w3.to_checksum_address(addr)
            wei      = w3.eth.get_balance(checksum)
            okb      = float(w3.from_wei(wei, "ether"))

            usdc = 0.0
            try:
                token    = w3.eth.contract(address=w3.to_checksum_address(USDC_ADDRESS), abi=ERC20_BALANCE_ABI)
                raw      = token.functions.balanceOf(checksum).call()
                decimals = token.functions.decimals().call()
                usdc     = raw / (10 ** decimals)
            except Exception:
                pass

            results.append({
                "agent_id":  p["agent_id"],
                "name":      p.get("name", p["agent_id"]),
                "bot_type":  p.get("bot_type"),
                "address":   checksum,
                "okb":       round(okb,  8),
                "usdc":      round(usdc, 6),
                "total_usd": round(usdc, 2),
            })
        except Exception as e:
            logger.warning("balance error for %s: %s", addr, e)
            results.append({"agent_id": p["agent_id"], "address": addr, "error": str(e)})

    # Update cache
    _balances_cache    = results
    _balances_cache_ts = time.monotonic()

    return results
