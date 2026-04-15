"""
OKX OnchainOS API v6 client for x402-guard.
Provides token price feeds and DEX trade history for X Layer.

NOTE: testnet (chainId 1952) is NOT supported by OKX wallet API.
      We use chainIndex=196 (mainnet) for price lookups — prices are
      the same token, just queried against mainnet contract addresses.
"""

from __future__ import annotations

import os
import hmac
import hashlib
import base64
import logging
import httpx
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

OKX_BASE     = "https://web3.okx.com"
CHAIN_INDEX  = "196"   # X Layer mainnet (price data only)

# Known X Layer token addresses (mainnet — for price queries)
OKB_MAINNET  = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"   # native OKB
USDC_MAINNET = "0x74b7F16337b8972027F6196A17a631aC6dE26d22"  # USDC mainnet


def _sign(timestamp: str, method: str, path: str, body: str = "") -> str:
    secret = os.getenv("OKX_SECRET_KEY", "")
    msg    = f"{timestamp}{method}{path}{body}"
    sig    = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
    return base64.b64encode(sig).decode()


def _headers(method: str, path: str, body: str = "") -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {
        "OK-ACCESS-KEY":        os.getenv("OKX_API_KEY", ""),
        "OK-ACCESS-SIGN":       _sign(ts, method, path, body),
        "OK-ACCESS-TIMESTAMP":  ts,
        "OK-ACCESS-PASSPHRASE": os.getenv("OKX_PASSPHRASE", ""),
        "OK-ACCESS-PROJECT":    os.getenv("OKX_PROJECT_ID", ""),
        "Content-Type":         "application/json",
    }


def _is_configured() -> bool:
    return bool(os.getenv("OKX_API_KEY") and os.getenv("OKX_SECRET_KEY"))


# ── Token Price ────────────────────────────────────────────────────────────────

async def get_token_prices(token_addresses: list[str]) -> list[dict]:
    """
    Fetch real-time USD prices for a list of token addresses on X Layer (mainnet).
    Returns list of {tokenAddress, price, symbol} dicts.
    Skips native token placeholder (0xeeee...) to avoid API errors.
    """
    if not _is_configured():
        logger.warning("OKX API not configured — no prices available")
        return []

    # Filter out native token placeholder — causes batch failures
    addrs = [a for a in token_addresses
             if a.lower() != "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"]
    if not addrs:
        return []

    path   = "/api/v5/wallet/token/real-time-price"
    body   = [{"chainIndex": CHAIN_INDEX, "tokenAddress": a} for a in addrs]
    import json
    body_str = json.dumps(body)

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                f"{OKX_BASE}{path}",
                headers=_headers("POST", path, body_str),
                content=body_str,
            )
            data = resp.json()
            if data.get("code") != "0":
                logger.warning("OKX price API error: %s", data.get("msg"))
                return []
            return data.get("data", [])
    except Exception as e:
        logger.error("OKX get_token_prices failed: %s", e)
        return []


async def get_okb_usd_price() -> Optional[float]:
    """
    Get native OKB price in USD using OKX DEX aggregator quote
    (OKB -> USDC on X Layer mainnet, via PotatoSwap/DEX router).
    Falls back to candle close price if quote fails.
    """
    if not _is_configured():
        return None

    # aggregator quote: 1 OKB -> USDC (gives tokenUnitPrice from dexRouterList)
    AMOUNT = "1000000000000000000"  # 1 OKB in wei
    OKB_NATIVE = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

    path = (
        f"/api/v6/dex/aggregator/quote"
        f"?chainIndex={CHAIN_INDEX}"
        f"&amount={AMOUNT}"
        f"&fromTokenAddress={OKB_NATIVE}"
        f"&toTokenAddress={USDC_MAINNET}"
    )
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{OKX_BASE}{path}",
                headers=_headers("GET", path),
            )
            data = resp.json()
            if data.get("code") == "0" and data.get("data"):
                quote = data["data"][0]
                # tokenUnitPrice is in the fromToken of dexRouterList
                router_list = quote.get("dexRouterList", [])
                if router_list:
                    from_token = router_list[0].get("fromToken", {})
                    price_str = from_token.get("tokenUnitPrice", "")
                    if price_str:
                        price = float(price_str)
                        if price > 0:
                            return round(price, 4)
                # fallback: use toTokenAmount / 1e6 (USDC decimals)
                to_amount = float(quote.get("toTokenAmount", "0"))
                if to_amount > 0:
                    return round(to_amount / 1e6, 4)
    except Exception as e:
        logger.warning("OKB price via aggregator failed: %s", e)

    # Fallback: use candle close price
    return await _get_okb_price_from_candle()


async def _get_okb_price_from_candle() -> Optional[float]:
    """Fallback: get OKB price from last 1-minute candle."""
    OKB_XLAYER = "0x3f4b6664338F23d2397c953f2AB4Ce8031663f80"
    path = f"/api/v6/dex/market/candles?chainIndex={CHAIN_INDEX}&tokenContractAddress={OKB_XLAYER}&bar=1m&limit=1"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{OKX_BASE}{path}",
                headers=_headers("GET", path),
            )
            data = resp.json()
            if data.get("code") == "0" and data.get("data"):
                raw = data["data"][0]
                # candle array: [ts, o, h, l, c, vol, quoteVol, confirmed]
                if isinstance(raw, list) and len(raw) >= 5:
                    return float(raw[4])  # close price
    except Exception as e:
        logger.warning("OKB candle fallback failed: %s", e)
    return None


# ── DEX Trades ────────────────────────────────────────────────────────────────

async def get_dex_trades(
    token_address: str = USDC_MAINNET,
    limit: int = 20,
) -> list[dict]:
    """
    Fetch recent DEX swap trades on X Layer for a given token.
    Returns list of normalized trade dicts.
    """
    if not _is_configured():
        return []

    path = (
        f"/api/v6/dex/market/trades"
        f"?chainIndex={CHAIN_INDEX}"
        f"&tokenContractAddress={token_address}"
        f"&limit={limit}"
    )
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{OKX_BASE}{path}",
                headers=_headers("GET", path),
            )
            data = resp.json()
            if data.get("code") != "0":
                logger.warning("OKX trades API error: %s", data.get("msg"))
                return []
            raw_trades = data.get("data", [])
            # Normalize fields
            normalized = []
            for t in raw_trades:
                normalized.append({
                    "tx_hash":    t.get("txHash", ""),
                    "timestamp":  t.get("timestamp", ""),
                    "price":      t.get("price", "0"),
                    "amount":     t.get("amount", "0"),
                    "side":       t.get("side", ""),
                    "token":      token_address,
                    "chain":      "xlayer",
                })
            return normalized
    except Exception as e:
        logger.error("OKX get_dex_trades failed: %s", e)
        return []


# ── Wallet Token Balances (mainnet only) ──────────────────────────────────────

async def get_wallet_token_balances(address: str) -> list[dict]:
    """
    Fetch all token balances for a wallet address via OKX OnchainOS.
    NOTE: Only works for X Layer MAINNET (chainIndex=196).
          Testnet (1952) is not supported by this API.
    """
    if not _is_configured():
        return []

    path = f"/api/v5/wallet/asset/all-token-balances-by-address?address={address}&chains={CHAIN_INDEX}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{OKX_BASE}{path}",
                headers=_headers("GET", path),
            )
            data = resp.json()
            if data.get("code") != "0":
                logger.warning("OKX balances error: %s", data.get("msg"))
                return []
            raw = data.get("data", [])
            if raw:
                return raw[0].get("tokenAssets", [])
            return []
    except Exception as e:
        logger.error("OKX get_wallet_token_balances failed: %s", e)
        return []
