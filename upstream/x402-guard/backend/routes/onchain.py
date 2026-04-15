"""
Onchain stats routes — expose GuardLog contract data + OKX OnchainOS live data.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from onchain_logger import onchain_logger
from okx_client import (
    get_okb_usd_price,
    get_dex_trades,
    get_token_prices,
    USDC_MAINNET,
    _is_configured,
)

router = APIRouter(prefix="/onchain", tags=["onchain"])


@router.get(
    "/stats",
    summary="Onchain GuardLog statistics",
    description=(
        "Returns approved / soft_alert / blocked counts read directly from "
        "the GuardLog smart contract on X Layer. Returns zeros if the contract "
        "is not configured."
    ),
)
async def onchain_stats():
    approved, soft_alerts, blocked = onchain_logger.get_onchain_stats()
    return {
        "approved":         approved,
        "soft_alerts":      soft_alerts,
        "blocked":          blocked,
        "contract_address": onchain_logger.contract_address,
        "network":          onchain_logger.network,
        "configured":       onchain_logger.contract_address is not None,
    }


@router.get(
    "/explorer-link",
    summary="X Layer explorer link for the GuardLog contract",
    description="Returns a URL to view the deployed GuardLog contract on the X Layer block explorer.",
)
async def explorer_link():
    addr = onchain_logger.contract_address

    if not addr:
        return JSONResponse(
            status_code=200,
            content={
                "configured": False,
                "message": "GUARD_CONTRACT_ADDRESS is not set",
                "explorer_url": None,
            },
        )

    chain_id = int(os.environ.get("XLAYER_CHAIN_ID", "1952"))
    if chain_id == 196:
        base = "https://www.oklink.com/xlayer"
    else:
        base = "https://www.oklink.com/xlayer-test"

    url = f"{base}/address/{addr}"
    return {
        "configured":    True,
        "contract":      addr,
        "network":       onchain_logger.network,
        "explorer_url":  url,
        "explorer_name": "OKLink X Layer Explorer",
    }


@router.get(
    "/okb-price",
    summary="Live OKB/USD price from OKX OnchainOS",
    description="Returns current OKB price in USD fetched from OKX API v5/v6.",
)
async def okb_price():
    price = await get_okb_usd_price()
    return {
        "symbol":      "OKB",
        "price_usd":   price,
        "source":      "OKX OnchainOS",
        "configured":  _is_configured(),
    }


@router.get(
    "/token-prices",
    summary="Live token prices from OKX OnchainOS",
    description="Returns USD prices for specified token addresses on X Layer mainnet.",
)
async def token_prices(
    addresses: str = Query(
        default=USDC_MAINNET,
        description="Comma-separated token contract addresses (X Layer mainnet)",
    )
):
    addr_list = [a.strip() for a in addresses.split(",") if a.strip()]
    data = await get_token_prices(addr_list)
    return {
        "chain":      "xlayer",
        "chain_index": "196",
        "tokens":     data,
        "configured": _is_configured(),
    }


@router.get(
    "/dex-activity",
    summary="Live DEX swap trades from OKX OnchainOS",
    description="Returns recent swap trades on X Layer DEX for a given token.",
)
async def dex_activity(
    token: str = Query(
        default=USDC_MAINNET,
        description="Token contract address to fetch trades for (X Layer mainnet)",
    ),
    limit: int = Query(default=20, ge=1, le=100),
):
    trades = await get_dex_trades(token_address=token, limit=limit)
    return {
        "chain":      "xlayer",
        "token":      token,
        "count":      len(trades),
        "trades":     trades,
        "configured": _is_configured(),
    }


@router.get(
    "/market-summary",
    summary="Combined market overview — OKB price + DEX activity + GuardLog stats",
)
async def market_summary():
    """Single endpoint for dashboard market widget — returns everything at once."""
    import asyncio

    okb_price_task  = asyncio.create_task(get_okb_usd_price())
    dex_trades_task = asyncio.create_task(get_dex_trades(limit=10))

    okb_price_val = await okb_price_task
    recent_trades = await dex_trades_task

    # GuardLog stats (onchain)
    approved, soft_alerts, blocked = onchain_logger.get_onchain_stats()

    return {
        "okb_price_usd":   okb_price_val,
        "dex_trades":      recent_trades,
        "guardlog": {
            "approved":    approved,
            "soft_alerts": soft_alerts,
            "blocked":     blocked,
            "contract":    onchain_logger.contract_address,
        },
        "source":          "OKX OnchainOS + X Layer GuardLog",
        "configured":      _is_configured(),
    }
