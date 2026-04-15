#!/usr/bin/env python3
"""Genesis Protocol - x402 Payment Server

Real HTTP 402 Payment Required protocol implementation.
Serves strategy signals, subscriptions, and parameter exports
with on-chain payment verification on X Layer.

Endpoints:
  GET  /health                    - Server health check
  GET  /api/v1/signal             - Market signal query ($0.001 USDT)
  GET  /api/v1/strategy/list      - List active strategies (free)
  GET  /api/v1/verify?tx=&tier=   - Verify tx hash on-chain (free)
  POST /api/v1/verify             - Verify tx hash on-chain (free)
  POST /api/v1/strategy/subscribe - Strategy subscription ($0.01 USDT)
  POST /api/v1/strategy/params    - Full parameter export ($1.00 USDT)
  POST /api/v1/nft/license        - NFT strategy license ($5.00 USDT)

Usage:
  python3 scripts/x402_server.py                 # Default port 8402
  python3 scripts/x402_server.py --port 8402
"""

import argparse
import hashlib
import json
import logging
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("x402")

# --- x402 Payment Configuration ---

CHAIN_ID = "196"  # X Layer mainnet
USDT_ADDRESS = "0x1E4a5963aBFD975d8c9021ce480b42188849D41d"
RECEIVER_ADDRESS = "0xd2D120eB7cEd38551cCeFb48021067d41D6542d3"

PAYMENT_TIERS = {
    "signal_query": {
        "price_usdt": "0.001",
        "description": "Single market signal with volatility and regime classification",
        "settle": "async",
    },
    "strategy_subscribe": {
        "price_usdt": "0.01",
        "description": "Real-time strategy change notifications",
        "settle": "async",
    },
    "strategy_params": {
        "price_usdt": "1.00",
        "description": "Full strategy parameter export with module configurations",
        "settle": "sync",
    },
    "nft_license": {
        "price_usdt": "5.00",
        "description": "Strategy NFT license - replicate full strategy",
        "settle": "sync",
    },
}
# --- Payment Verification ---

# In-memory payment records (production would use DB)
verified_payments = {}  # payment_hash -> {tier, timestamp, payer}
# Payment receipt cache: tx_hash (lowercase) -> verification result dict
payment_receipt_cache = {}
# Demo mode: accept X-Payment-Proof header with valid hash
DEMO_MODE = os.environ.get("X402_DEMO", "true").lower() == "true"

# X Layer RPC endpoint
XLAYER_RPC = "https://rpc.xlayer.tech"

# ERC20 Transfer event signature: Transfer(address,address,uint256)
TRANSFER_EVENT_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Minimum amounts per tier in USDT base units (6 decimals)
TIER_MIN_AMOUNTS = {
    "signal_query": 1000,          # 0.001 USDT = 1000 base units
    "strategy_subscribe": 10000,   # 0.01  USDT = 10000 base units
    "strategy_params": 1000000,    # 1.00  USDT = 1000000 base units
    "nft_license": 5000000,        # 5.00  USDT = 5000000 base units
}


def _rpc_call(method: str, params: list) -> dict:
    """Make a JSON-RPC call to the X Layer RPC endpoint."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1,
    }).encode()
    req = urllib.request.Request(
        XLAYER_RPC,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "GenesisProtocol-x402/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def verify_onchain_payment(tx_hash: str, tier: str) -> tuple:
    """Verify an on-chain payment transaction.

    Args:
        tx_hash: The transaction hash (0x-prefixed hex string).
        tier: The payment tier to verify against.

    Returns:
        (valid: bool, details: dict) where details contains verification info
        or error information.
    """
    tx_hash = tx_hash.strip().lower()

    # Normalize: ensure 0x prefix
    if not tx_hash.startswith("0x"):
        tx_hash = "0x" + tx_hash

    # Basic format validation
    if len(tx_hash) != 66 or not all(c in "0123456789abcdef" for c in tx_hash[2:]):
        return False, {"error": "Invalid transaction hash format"}

    # Check cache first
    cache_key = tx_hash
    if cache_key in payment_receipt_cache:
        cached = payment_receipt_cache[cache_key]
        # If the cached result was valid, check tier compatibility
        if cached.get("valid"):
            cached_amount = cached.get("transfer_value", 0)
            required = TIER_MIN_AMOUNTS.get(tier, 0)
            if cached_amount >= required:
                return True, cached
            else:
                return False, {
                    "error": "Cached tx amount insufficient for requested tier",
                    "transfer_value": cached_amount,
                    "required": required,
                    "tier": tier,
                }
        return False, cached

    try:
        # Step 1: Get transaction receipt
        rpc_resp = _rpc_call("eth_getTransactionReceipt", [tx_hash])

        if "error" in rpc_resp:
            details = {"error": f"RPC error: {rpc_resp['error']}"}
            payment_receipt_cache[cache_key] = details
            return False, details

        receipt = rpc_resp.get("result")
        if receipt is None:
            details = {"error": "Transaction not found or not yet confirmed"}
            # Don't cache missing txs - they may confirm later
            return False, details

        # Step 2: Verify transaction status (0x1 = success)
        status = receipt.get("status", "0x0")
        if status != "0x1":
            details = {"error": "Transaction failed (status != 0x1)", "status": status, "valid": False}
            payment_receipt_cache[cache_key] = details
            return False, details

        # Step 3: Verify the transaction interacts with the USDT contract
        tx_to = (receipt.get("to") or "").lower()
        if tx_to != USDT_ADDRESS.lower():
            details = {
                "error": "Transaction is not a USDT transfer on X Layer",
                "tx_to": tx_to,
                "expected_contract": USDT_ADDRESS.lower(),
                "valid": False,
            }
            payment_receipt_cache[cache_key] = details
            return False, details

        # Step 4: Parse ERC20 Transfer event logs
        logs = receipt.get("logs", [])
        transfer_found = False
        transfer_from = None
        transfer_to = None
        transfer_value = 0

        for log_entry in logs:
            log_address = (log_entry.get("address") or "").lower()
            topics = log_entry.get("topics", [])

            # Must be from the USDT contract and be a Transfer event
            if log_address != USDT_ADDRESS.lower():
                continue
            if len(topics) < 3:
                continue
            if topics[0].lower() != TRANSFER_EVENT_TOPIC:
                continue

            # Transfer event: topics[1] = from (padded), topics[2] = to (padded)
            # data = value (uint256)
            transfer_from = "0x" + topics[1][-40:]
            transfer_to = "0x" + topics[2][-40:]
            raw_data = log_entry.get("data", "0x0")
            transfer_value = int(raw_data, 16)
            transfer_found = True
            break  # Use first matching Transfer event

        if not transfer_found:
            details = {
                "error": "No ERC20 Transfer event found in transaction logs",
                "valid": False,
            }
            payment_receipt_cache[cache_key] = details
            return False, details

        # Step 5: Verify transfer recipient is our payment address
        if transfer_to.lower() != RECEIVER_ADDRESS.lower():
            details = {
                "error": "Transfer recipient does not match payment address",
                "transfer_to": transfer_to,
                "expected_receiver": RECEIVER_ADDRESS.lower(),
                "valid": False,
            }
            payment_receipt_cache[cache_key] = details
            return False, details

        # Step 6: Verify transfer amount meets minimum for tier
        required_amount = TIER_MIN_AMOUNTS.get(tier, 0)
        if transfer_value < required_amount:
            details = {
                "error": "Transfer amount below minimum for tier",
                "transfer_value": transfer_value,
                "required": required_amount,
                "tier": tier,
                "valid": False,
            }
            payment_receipt_cache[cache_key] = details
            return False, details

        # All checks passed
        details = {
            "valid": True,
            "tx_hash": tx_hash,
            "block_number": receipt.get("blockNumber"),
            "transfer_from": transfer_from,
            "transfer_to": transfer_to,
            "transfer_value": transfer_value,
            "transfer_usdt": transfer_value / 1e6,
            "tier": tier,
            "contract": USDT_ADDRESS,
        }
        payment_receipt_cache[cache_key] = details
        return True, details

    except urllib.error.URLError as e:
        return False, {"error": f"RPC connection failed: {str(e)}"}
    except Exception as e:
        logger.error("On-chain verification error: %s", e)
        return False, {"error": f"Verification error: {str(e)}"}


def generate_payment_request(tier: str) -> dict:
    """Generate a 402 payment request for the given tier."""
    config = PAYMENT_TIERS[tier]
    nonce = hashlib.sha256(f"{tier}:{time.time()}".encode()).hexdigest()[:16]
    return {
        "x402_version": "1.0",
        "chain": f"xlayer-{CHAIN_ID}",
        "token": USDT_ADDRESS,
        "amount": config["price_usdt"],
        "receiver": RECEIVER_ADDRESS,
        "description": config["description"],
        "settle_mode": config["settle"],
        "nonce": nonce,
        "expires_at": int(time.time()) + 300,  # 5 min expiry
    }


def verify_payment(headers: dict, tier: str) -> tuple:
    """Verify payment proof from request headers.
    Returns (is_valid, payer_address_or_error).
    """
    proof = headers.get("X-Payment-Proof", "")
    payer = headers.get("X-Payer-Address", "")

    if not proof:
        return False, "Missing X-Payment-Proof header"

    if DEMO_MODE:
        # In demo mode, accept any proof that's a valid hex hash
        if len(proof) >= 16 and all(c in "0123456789abcdef" for c in proof.lower()):
            payment_hash = hashlib.sha256(f"{proof}:{tier}".encode()).hexdigest()
            verified_payments[payment_hash] = {
                "tier": tier,
                "timestamp": int(time.time()),
                "payer": payer or "0xdemo",
                "proof": proof,
            }
            return True, payer or "0xdemo"
    else:
        # Production: verify on-chain transaction
        valid, details = verify_onchain_payment(proof, tier)
        if valid:
            payment_hash = hashlib.sha256(f"{proof}:{tier}".encode()).hexdigest()
            resolved_payer = details.get("transfer_from", payer or "unknown")
            verified_payments[payment_hash] = {
                "tier": tier,
                "timestamp": int(time.time()),
                "payer": resolved_payer,
                "proof": proof,
                "onchain": details,
            }
            return True, resolved_payer
        else:
            return False, details.get("error", "Payment verification failed")

    return False, "Payment verification failed (set X402_DEMO=true for demo)"
# --- Market Data Cache (TTL-based to avoid CoinGecko 30 req/min limit) ---

MARKET_CACHE_TTL = 60  # seconds
_market_cache = {}  # key -> {"data": ..., "timestamp": float}


def _cache_get(key: str):
    """Return cached data if fresh (within TTL), else None."""
    entry = _market_cache.get(key)
    if entry and (time.time() - entry["timestamp"]) < MARKET_CACHE_TTL:
        logger.info("Cache HIT for %s (age %.1fs)", key, time.time() - entry["timestamp"])
        return entry["data"]
    return None


def _cache_set(key: str, data):
    """Store data in cache with current timestamp."""
    _market_cache[key] = {"data": data, "timestamp": time.time()}


# --- Market Data (for signal endpoint) ---

def get_market_signal(pair: str = "ETH-USDT") -> dict:
    """Generate a real market signal using available data."""
    try:
        cg_map = {"ETH-USDT": "ethereum", "BTC-USDT": "bitcoin", "OKB-USDT": "okb"}
        cg_id = cg_map.get(pair, "ethereum")
        cache_key = f"market_chart:{cg_id}"

        # Check cache first to avoid hitting CoinGecko rate limits
        data = _cache_get(cache_key)
        if data is None:
            url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days=1"
            req = urllib.request.Request(url, headers={"User-Agent": "GenesisProtocol/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            _cache_set(cache_key, data)
            logger.info("Cache MISS for %s - fetched fresh data from CoinGecko", cache_key)

        prices = [p[1] for p in data.get("prices", [])]
        if len(prices) < 10:
            raise ValueError("Insufficient data")

        current = prices[-1]
        avg = sum(prices) / len(prices)
        std = (sum((p - avg) ** 2 for p in prices) / len(prices)) ** 0.5
        vol = (std / avg) * 100

        # EMA momentum
        ema_fast = prices[-1]
        ema_slow = prices[-1]
        for p in prices:
            ema_fast = 0.1 * p + 0.9 * ema_fast
            ema_slow = 0.03 * p + 0.97 * ema_slow
        momentum = (ema_fast - ema_slow) / ema_slow if ema_slow > 0 else 0

        # Regime classification
        regime = "volatile" if vol > 3.0 else "trending" if vol > 1.0 else "calm"

        # Bayesian confidence
        regime_params = {"calm": (0.5, 0.3), "volatile": (3.0, 1.5), "trending": (1.5, 0.8)}
        mu, sigma = regime_params[regime]
        confidence = math.exp(-0.5 * ((vol - mu) / sigma) ** 2)

        return {
            "pair": pair,
            "price": round(current, 2),
            "volatility_pct": round(vol, 4),
            "regime": regime,
            "confidence": round(confidence, 4),
            "momentum": round(momentum, 6),
            "momentum_signal": "bullish" if momentum > 0.005 else "bearish" if momentum < -0.005 else "neutral",
            "ema_fast": round(ema_fast, 2),
            "ema_slow": round(ema_slow, 2),
            "recommendation": {
                "calm": "MAINTAIN_CALM_ACCUMULATOR",
                "volatile": "SWITCH_TO_VOLATILE_DEFENDER",
                "trending": "ADJUST_FEE_SENSITIVITY",
            }[regime],
            "fee_range": {
                "calm": "0.01% - 0.30%",
                "volatile": "0.10% - 1.50%",
                "trending": "0.05% - 0.80%",
            }[regime],
            "source": "coingecko_live",
            "timestamp": int(time.time()),
        }
    except Exception as e:
        logger.warning("Market data fetch failed: %s", e)
        return {
            "pair": pair,
            "price": 0,
            "error": "Market data temporarily unavailable",
            "timestamp": int(time.time()),
        }
# --- Strategy Data ---

MAINNET_CONTRACTS = {
    "assembler": "0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78",
    "v4_hook": "0x174a2450b342042AAe7398545f04B199248E69c0",
    "dynamic_fee": "0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed",
    "mev_protection": "0xA4f6ABd6F77928b06F075637ccBACA8f89e17386",
    "auto_rebalance": "0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee",
    "liquidity_shield": "0xd969448dfc24Fe3Aff25e86db338fAB41b104319",
    "oracle": "0xCFc867E2379Cbe097D934CB8e19e3F028B82Bd3D",
    "strategy_nft": "0x8a0e87395f864405c5225eBd80391Ac82eefe437",
}

STRATEGY_PRESETS = {
    "calm_accumulator": {
        "modules": ["dynamic_fee", "auto_rebalance"],
        "params": {"min_fee_bps": 1, "max_fee_bps": 30, "rebalance_trigger": 0.90},
    },
    "volatile_defender": {
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance"],
        "params": {"min_fee_bps": 10, "max_fee_bps": 150, "mev_block": True, "rebalance_trigger": 0.70},
    },
    "trend_rider": {
        "modules": ["dynamic_fee", "mev_protection"],
        "params": {"min_fee_bps": 5, "max_fee_bps": 80, "sensitivity": 0.8},
    },
    "full_defense": {
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance", "liquidity_shield", "oracle"],
        "params": {"min_fee_bps": 15, "max_fee_bps": 200, "mev_block": True, "shield_threshold_bps": 50},
    },
}
# --- HTTP Request Handler ---

class X402Handler(BaseHTTPRequestHandler):
    """HTTP handler implementing x402 payment protocol."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/health":
            self._json_response(200, {
                "status": "healthy",
                "service": "genesis-x402",
                "version": "1.0.0",
                "chain": f"xlayer-{CHAIN_ID}",
                "demo_mode": DEMO_MODE,
                "payment_tiers": list(PAYMENT_TIERS.keys()),
                "uptime": int(time.time() - SERVER_START),
            })

        elif path == "/api/v1/signal":
            # x402 gated endpoint
            headers = {k: v for k, v in self.headers.items()}
            paid, payer = verify_payment(headers, "signal_query")

            if not paid:
                # Return 402 Payment Required
                payment_req = generate_payment_request("signal_query")
                self._json_response(402, {
                    "error": "Payment Required",
                    "message": "This endpoint requires x402 payment",
                    "payment": payment_req,
                    "instructions": {
                        "1": f"Send {payment_req['amount']} USDT to {RECEIVER_ADDRESS} on X Layer (Chain {CHAIN_ID})",
                        "2": "Include tx hash in X-Payment-Proof header",
                        "3": "Include your address in X-Payer-Address header",
                        "demo": "In demo mode, any 16+ char hex string is accepted as proof",
                    },
                })
                return

            # Payment verified - return signal
            pair = params.get("pair", ["ETH-USDT"])[0]
            signal = get_market_signal(pair)
            signal["payment"] = {"tier": "signal_query", "payer": payer, "verified": True}
            self._json_response(200, signal)

        elif path == "/api/v1/strategy/list":
            # Free endpoint
            self._json_response(200, {
                "strategies": STRATEGY_PRESETS,
                "contracts": MAINNET_CONTRACTS,
                "chain": f"xlayer-{CHAIN_ID}",
                "timestamp": int(time.time()),
            })

        elif path == "/api/v1/tiers":
            self._json_response(200, {
                "tiers": PAYMENT_TIERS,
                "chain": f"xlayer-{CHAIN_ID}",
                "token": USDT_ADDRESS,
                "receiver": RECEIVER_ADDRESS,
            })

        elif path == "/api/v1/verify":
            # Free endpoint: verify a tx hash without payment gate
            tx_hash = params.get("tx", [""])[0]
            tier = params.get("tier", ["signal_query"])[0]
            if not tx_hash:
                self._json_response(400, {
                    "error": "Missing 'tx' query parameter",
                    "usage": "GET /api/v1/verify?tx=0x...&tier=signal_query",
                })
                return
            if tier not in PAYMENT_TIERS:
                self._json_response(400, {
                    "error": f"Unknown tier: {tier}",
                    "valid_tiers": list(PAYMENT_TIERS.keys()),
                })
                return
            if DEMO_MODE:
                self._json_response(200, {
                    "demo_mode": True,
                    "message": "On-chain verification disabled in demo mode. Set X402_DEMO=false to enable.",
                    "tx_hash": tx_hash,
                    "tier": tier,
                })
                return
            valid, details = verify_onchain_payment(tx_hash, tier)
            self._json_response(200, {
                "verified": valid,
                "tx_hash": tx_hash,
                "tier": tier,
                "details": details,
            })

        else:
            self._json_response(404, {
                "error": "Not Found",
                "endpoints": [
                    "GET  /health",
                    "GET  /api/v1/signal?pair=ETH-USDT  (x402: $0.001)",
                    "GET  /api/v1/strategy/list          (free)",
                    "GET  /api/v1/tiers                   (free)",
                    "GET  /api/v1/verify?tx=0x...&tier=   (free)",
                    "POST /api/v1/verify                  (free)",
                    "POST /api/v1/strategy/subscribe      (x402: $0.01)",
                    "POST /api/v1/strategy/params         (x402: $1.00)",
                    "POST /api/v1/nft/license             (x402: $5.00)",
                ],
            })

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        headers = {k: v for k, v in self.headers.items()}

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else "{}"
        try:
            body_data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            body_data = {}

        if path == "/api/v1/verify":
            # Free endpoint: verify a tx hash (POST variant)
            tx_hash = body_data.get("tx", body_data.get("tx_hash", ""))
            tier = body_data.get("tier", "signal_query")
            if not tx_hash:
                self._json_response(400, {
                    "error": "Missing 'tx' or 'tx_hash' in request body",
                    "usage": "POST /api/v1/verify with JSON body {\"tx\": \"0x...\", \"tier\": \"signal_query\"}",
                })
                return
            if tier not in PAYMENT_TIERS:
                self._json_response(400, {
                    "error": f"Unknown tier: {tier}",
                    "valid_tiers": list(PAYMENT_TIERS.keys()),
                })
                return
            if DEMO_MODE:
                self._json_response(200, {
                    "demo_mode": True,
                    "message": "On-chain verification disabled in demo mode. Set X402_DEMO=false to enable.",
                    "tx_hash": tx_hash,
                    "tier": tier,
                })
                return
            valid, details = verify_onchain_payment(tx_hash, tier)
            self._json_response(200, {
                "verified": valid,
                "tx_hash": tx_hash,
                "tier": tier,
                "details": details,
            })
            return

        if path == "/api/v1/strategy/subscribe":
            tier = "strategy_subscribe"
        elif path == "/api/v1/strategy/params":
            tier = "strategy_params"
        elif path == "/api/v1/nft/license":
            tier = "nft_license"
        else:
            self._json_response(404, {"error": "Not Found"})
            return

        paid, payer = verify_payment(headers, tier)

        if not paid:
            payment_req = generate_payment_request(tier)
            self._json_response(402, {
                "error": "Payment Required",
                "message": f"This endpoint requires x402 payment ({PAYMENT_TIERS[tier]['price_usdt']} USDT)",
                "payment": payment_req,
            })
            return

        # Payment verified
        if tier == "strategy_subscribe":
            self._json_response(200, {
                "subscription": {
                    "id": hashlib.sha256(f"{payer}:{time.time()}".encode()).hexdigest()[:16],
                    "payer": payer,
                    "active": True,
                    "strategies": list(STRATEGY_PRESETS.keys()),
                    "webhook_url": body_data.get("webhook_url", ""),
                    "events": ["strategy_created", "strategy_deactivated", "fee_adjusted", "rebalance_triggered"],
                },
                "payment": {"tier": tier, "verified": True},
            })

        elif tier == "strategy_params":
            preset = body_data.get("preset", "volatile_defender")
            strategy = STRATEGY_PRESETS.get(preset, STRATEGY_PRESETS["volatile_defender"])
            self._json_response(200, {
                "preset": preset,
                "modules": strategy["modules"],
                "module_addresses": {m: MAINNET_CONTRACTS.get(m, "unknown") for m in strategy["modules"]},
                "parameters": strategy["params"],
                "contracts": MAINNET_CONTRACTS,
                "deployment_instructions": {
                    "chain": f"X Layer Mainnet (Chain {CHAIN_ID})",
                    "assembler": MAINNET_CONTRACTS["assembler"],
                    "steps": [
                        "1. Connect to X Layer RPC: https://rpc.xlayer.tech",
                        "2. Call assembler.createStrategy([module_addresses])",
                        "3. Configure module params via assembler.updateModuleParams()",
                        "4. Set active strategy on GenesisV4Hook",
                    ],
                },
                "payment": {"tier": tier, "verified": True},
            })

        elif tier == "nft_license":
            token_id = body_data.get("token_id", 1)
            self._json_response(200, {
                "license": {
                    "token_id": token_id,
                    "nft_contract": MAINNET_CONTRACTS["strategy_nft"],
                    "licensee": payer,
                    "license_type": "full_replication",
                    "granted_at": int(time.time()),
                    "chain": f"xlayer-{CHAIN_ID}",
                },
                "strategy_data": STRATEGY_PRESETS.get("full_defense"),
                "payment": {"tier": tier, "verified": True},
            })

    def _json_response(self, code: int, body: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "X-Payment-Proof, X-Payer-Address, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        if code == 402:
            self.send_header("X-Payment-Required", "true")
            self.send_header("X-Payment-Chain", f"xlayer-{CHAIN_ID}")
        self.end_headers()
        self.wfile.write(json.dumps(body, indent=2).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "X-Payment-Proof, X-Payer-Address, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def log_message(self, format, *args):
        logger.info("%s %s", self.client_address[0], format % args)
# --- Main ---

SERVER_START = time.time()


def main():
    parser = argparse.ArgumentParser(description="Genesis x402 Payment Server")
    parser.add_argument("--port", type=int, default=8402, help="Server port (default: 8402)")
    args = parser.parse_args()

    global SERVER_START
    SERVER_START = time.time()

    server = HTTPServer(("0.0.0.0", args.port), X402Handler)
    logger.info("=" * 50)
    logger.info("  Genesis x402 Payment Server")
    logger.info("  Port: %d", args.port)
    logger.info("  Chain: X Layer (Chain %s)", CHAIN_ID)
    logger.info("  Demo mode: %s", DEMO_MODE)
    logger.info("  Receiver: %s", RECEIVER_ADDRESS)
    logger.info("=" * 50)
    logger.info("Endpoints:")
    logger.info("  GET  /health")
    logger.info("  GET  /api/v1/signal?pair=ETH-USDT  ($0.001)")
    logger.info("  GET  /api/v1/strategy/list          (free)")
    logger.info("  GET  /api/v1/verify?tx=0x...         (free)")
    logger.info("  POST /api/v1/verify                  (free)")
    logger.info("  POST /api/v1/strategy/subscribe      ($0.01)")
    logger.info("  POST /api/v1/strategy/params         ($1.00)")
    logger.info("  POST /api/v1/nft/license             ($5.00)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped")
        server.server_close()


if __name__ == "__main__":
    main()
