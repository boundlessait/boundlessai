#!/usr/bin/env python3
"""Live integration test for OKX API - Market + DEX V6 endpoints.

Demonstrates real API calls used by Genesis Protocol's perception and trade layers.
Requires environment variables:
  - OK_ACCESS_KEY, OK_ACCESS_SECRET, OK_ACCESS_PASSPHRASE  (Market API, account-level)
  - OK_DEX_KEY, OK_DEX_SECRET, OK_DEX_PASSPHRASE           (DEX API, project-level)

Tests:
  Market API (www.okx.com):
    1. ETH-USDT ticker (real-time price)
    2. OKB-USDT ticker (X Layer native token)
    3. BTC-USDT ticker (benchmark)
    4. ETH-USDT 1H candles (volatility calculation)
    5. ETH-USDT orderbook depth (liquidity/spread analysis)
    6. ETH-USDT-SWAP funding rate (sentiment signal)
    7. Volatility computation (DynamicFee Module input)
    8. Multi-pair snapshot (full perception cycle)
  DEX Aggregator API V6 (web3.okx.com):
    9. Supported chains (X Layer discovery)
   10. All tokens on X Layer (token registry)
   11. DEX quote OKB->USDT (trade simulation)
"""
import base64
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

# ─── Credentials ─────────────────────────────────────────────────────────────

# Market API (account-level key)
MARKET_KEY = os.environ.get("OK_ACCESS_KEY", "")
MARKET_SECRET = os.environ.get("OK_ACCESS_SECRET", "")
MARKET_PASSPHRASE = os.environ.get("OK_ACCESS_PASSPHRASE", "")
MARKET_BASE = "https://www.okx.com"

# DEX API (project-level key)
DEX_KEY = os.environ.get("OK_DEX_KEY", "")
DEX_SECRET = os.environ.get("OK_DEX_SECRET", "")
DEX_PASSPHRASE = os.environ.get("OK_DEX_PASSPHRASE", "")
DEX_BASE = "https://web3.okx.com"


def _sign(secret, timestamp, method, path):
    msg = timestamp + method + path
    mac = hmac.new(secret.encode(), msg.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


def api_get(path, params=None):
    """Authenticated GET request to OKX Market API (www.okx.com)."""
    request_path = path
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        request_path = path + "?" + qs
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    headers = {
        "OK-ACCESS-KEY": MARKET_KEY,
        "OK-ACCESS-SIGN": _sign(MARKET_SECRET, ts, "GET", request_path),
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": MARKET_PASSPHRASE,
        "Content-Type": "application/json",
    }
    try:
        r = requests.get(MARKET_BASE + request_path, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        print(f"  Error: {e}")
        return {"error": str(e)}


def dex_get(path, params=None):
    """Authenticated GET request to OKX DEX V6 API (web3.okx.com)."""
    request_path = path
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        request_path = path + "?" + qs
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    headers = {
        "OK-ACCESS-KEY": DEX_KEY,
        "OK-ACCESS-SIGN": _sign(DEX_SECRET, ts, "GET", request_path),
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": DEX_PASSPHRASE,
        "Content-Type": "application/json",
    }
    try:
        r = requests.get(DEX_BASE + request_path, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        print(f"  Error: {e}")
        return {"error": str(e)}


# ─── Test Cases ──────────────────────────────────────────────────────────────

def test_eth_ticker():
    """[Perception Layer] Real-time ETH-USDT price for regime detection."""
    print("\n[1] GET /api/v5/market/ticker - ETH-USDT")
    data = api_get("/api/v5/market/ticker", {"instId": "ETH-USDT"})
    if data.get("code") == "0" and data.get("data"):
        d = data["data"][0]
        print(f"  Last: ${d['last']}  High24h: ${d['high24h']}  Low24h: ${d['low24h']}")
        print(f"  Vol24h: {d['vol24h']}  VolCcy24h: {d['volCcy24h']}")
        return True
    print(f"  Failed: {data}")
    return False


def test_okb_ticker():
    """[Perception Layer] OKB-USDT price (X Layer native gas token)."""
    print("\n[2] GET /api/v5/market/ticker - OKB-USDT")
    data = api_get("/api/v5/market/ticker", {"instId": "OKB-USDT"})
    if data.get("code") == "0" and data.get("data"):
        d = data["data"][0]
        print(f"  Last: ${d['last']}  Vol24h: {d['vol24h']}")
        return True
    print(f"  Failed: {data}")
    return False


def test_btc_ticker():
    """[Perception Layer] BTC-USDT benchmark price."""
    print("\n[3] GET /api/v5/market/ticker - BTC-USDT")
    data = api_get("/api/v5/market/ticker", {"instId": "BTC-USDT"})
    if data.get("code") == "0" and data.get("data"):
        d = data["data"][0]
        print(f"  Last: ${d['last']}  Vol24h: {d['vol24h']}")
        return True
    print(f"  Failed: {data}")
    return False


def test_candles():
    """[Analysis Layer] 1H candles for volatility → DynamicFee input."""
    print("\n[4] GET /api/v5/market/candles - ETH-USDT 1H x20")
    data = api_get("/api/v5/market/candles", {"instId": "ETH-USDT", "bar": "1H", "limit": "20"})
    if data.get("code") == "0" and data.get("data"):
        candles = data["data"]
        closes = [float(c[4]) for c in candles]
        avg = sum(closes) / len(closes)
        std = (sum((p - avg) ** 2 for p in closes) / len(closes)) ** 0.5
        vol = (std / avg) * 100
        print(f"  Candles: {len(candles)}  Avg: ${avg:.2f}  StdDev: ${std:.2f}")
        print(f"  Volatility: {vol:.3f}% -> {'HIGH' if vol > 2 else 'MEDIUM' if vol > 0.5 else 'LOW'} regime")
        return True
    print(f"  Failed: {data}")
    return False


def test_orderbook():
    """[MEV Protection] Orderbook depth for spread and liquidity analysis."""
    print("\n[5] GET /api/v5/market/books - ETH-USDT depth=5")
    data = api_get("/api/v5/market/books", {"instId": "ETH-USDT", "sz": "5"})
    if data.get("code") == "0" and data.get("data"):
        book = data["data"][0]
        bids, asks = book.get("bids", []), book.get("asks", [])
        if bids and asks:
            spread = float(asks[0][0]) - float(bids[0][0])
            bid_depth = sum(float(b[1]) for b in bids)
            ask_depth = sum(float(a[1]) for a in asks)
            print(f"  Best bid: ${bids[0][0]}  Best ask: ${asks[0][0]}  Spread: ${spread:.4f}")
            print(f"  Bid depth: {bid_depth:.2f} ETH  Ask depth: {ask_depth:.2f} ETH")
            return True
    print(f"  Failed: {data}")
    return False


def test_funding_rate():
    """[Analysis Layer] Funding rate as sentiment signal for fee adjustment."""
    print("\n[6] GET /api/v5/public/funding-rate - ETH-USDT-SWAP")
    data = api_get("/api/v5/public/funding-rate", {"instId": "ETH-USDT-SWAP"})
    if data.get("code") == "0" and data.get("data"):
        d = data["data"][0]
        rate = float(d.get("fundingRate", 0))
        print(f"  Funding rate: {rate * 100:.4f}%")
        print(f"  Sentiment: {'BULLISH (longs paying)' if rate > 0 else 'BEARISH (shorts paying)'}")
        return True
    print(f"  Failed: {data}")
    return False


def test_volatility_computation():
    """[DynamicFee Module] Full volatility computation pipeline."""
    print("\n[7] Volatility computation (4H candles -> stddev -> regime -> fee)")
    data = api_get("/api/v5/market/candles", {"instId": "ETH-USDT", "bar": "4H", "limit": "30"})
    if data.get("code") == "0" and data.get("data"):
        closes = [float(c[4]) for c in data["data"]]
        avg = sum(closes) / len(closes)
        std = (sum((p - avg) ** 2 for p in closes) / len(closes)) ** 0.5
        vol = (std / avg) * 100

        if vol > 3.0:
            fee_range, regime = "0.10% - 1.50%", "volatile_defender"
        elif vol > 1.0:
            fee_range, regime = "0.05% - 0.80%", "trend_rider"
        else:
            fee_range, regime = "0.01% - 0.30%", "calm_accumulator"

        print(f"  4H candles: {len(closes)}  Volatility: {vol:.3f}%")
        print(f"  Regime: {regime}  Fee range: {fee_range}")
        return True
    print(f"  Failed: {data}")
    return False


def test_multi_pair_snapshot():
    """[Full Perception Cycle] Parallel price fetch for all monitored pairs."""
    print("\n[8] Multi-pair snapshot (ETH, BTC, OKB)")
    pairs = ["ETH-USDT", "BTC-USDT", "OKB-USDT"]
    all_ok = True
    for pair in pairs:
        data = api_get("/api/v5/market/ticker", {"instId": pair})
        if data.get("code") == "0" and data.get("data"):
            d = data["data"][0]
            print(f"  {pair}: ${d['last']}  vol24h={d['vol24h']}")
        else:
            print(f"  {pair}: FAILED")
            all_ok = False
    return all_ok


# ─── DEX V6 Tests ────────────────────────────────────────────────────────────

def test_dex_supported_chains():
    """[DEX Aggregator] Discover supported chains including X Layer."""
    print("\n[9] GET /api/v6/dex/aggregator/supported/chain")
    data = dex_get("/api/v6/dex/aggregator/supported/chain")
    if data.get("code") == "0" and data.get("data"):
        chains = data["data"]
        xlayer = [c for c in chains if str(c.get("chainIndex")) == "196"]
        print(f"  Supported chains: {len(chains)}")
        if xlayer:
            x = xlayer[0]
            print(f"  X Layer found: chainIndex={x['chainIndex']} name={x['chainName']}")
            print(f"  DEX approve addr: {x.get('dexTokenApproveAddress', '?')}")
        return bool(xlayer)
    print(f"  Failed: {data}")
    return False


def test_dex_all_tokens():
    """[DEX Aggregator] Token registry on X Layer."""
    print("\n[10] GET /api/v6/dex/aggregator/all-tokens?chainIndex=196")
    data = dex_get("/api/v6/dex/aggregator/all-tokens", {"chainIndex": "196"})
    if data.get("code") == "0" and data.get("data"):
        tokens = data["data"]
        print(f"  Tokens on X Layer: {len(tokens)}")
        for t in tokens[:5]:
            sym = t.get("tokenSymbol", "?")
            addr = t.get("tokenContractAddress", "?")[:20]
            dec = t.get("decimal", "?")
            honey = t.get("isHoneyPot", "?")
            print(f"    {sym} ({dec} dec) honeypot={honey} {addr}...")
        return True
    print(f"  Failed: {data}")
    return False


def test_dex_quote():
    """[Trade Layer] DEX swap quote OKB -> USDT on X Layer."""
    print("\n[11] GET /api/v6/dex/aggregator/quote (OKB -> USDT)")
    data = dex_get("/api/v6/dex/aggregator/quote", {
        "chainIndex": "196",
        "fromTokenAddress": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
        "toTokenAddress": "0x1E4a5963aBFD975d8c9021ce480b42188849D41d",
        "amount": "1000000000000000000",  # 1 OKB
    })
    if data.get("code") == "0" and data.get("data"):
        routes = data["data"]
        if isinstance(routes, list) and routes:
            r = routes[0]
            dex_list = r.get("dexRouterList", [])
            if dex_list:
                dex = dex_list[0]
                proto = dex.get("dexProtocol", {})
                from_tok = dex.get("fromToken", {})
                to_tok = dex.get("toToken", {})
                print(f"  Route: {proto.get('dexName', '?')} ({proto.get('percent', '?')}%)")
                print(f"  From: {from_tok.get('tokenSymbol', '?')} @ ${from_tok.get('tokenUnitPrice', '?')}")
                print(f"  To: {to_tok.get('tokenSymbol', '?')} @ ${to_tok.get('tokenUnitPrice', '?')}")
                print(f"  Est output: {r.get('toTokenAmount', '?')}")
                return True
        elif isinstance(routes, dict):
            print(f"  Route data: {json.dumps(routes)[:300]}")
            return True
    print(f"  Failed: {data}")
    return False


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    has_market = all([MARKET_KEY, MARKET_SECRET, MARKET_PASSPHRASE])
    has_dex = all([DEX_KEY, DEX_SECRET, DEX_PASSPHRASE])

    if not has_market and not has_dex:
        print("ERROR: Set at least one credential set:")
        print("  Market: OK_ACCESS_KEY, OK_ACCESS_SECRET, OK_ACCESS_PASSPHRASE")
        print("  DEX:    OK_DEX_KEY, OK_DEX_SECRET, OK_DEX_PASSPHRASE")
        sys.exit(1)

    print("=" * 60)
    print("  OKX API - Live Integration Test")
    print("  Genesis Protocol Perception + Analysis + Trade Layer")
    print(f"  Market API: {MARKET_BASE} ({'OK' if has_market else 'SKIP'})")
    print(f"  DEX API:    {DEX_BASE} ({'OK' if has_dex else 'SKIP'})")
    print(f"  Timestamp:  {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    tests = []

    if has_market:
        tests.extend([
            ("ETH-USDT Ticker", test_eth_ticker),
            ("OKB-USDT Ticker", test_okb_ticker),
            ("BTC-USDT Ticker", test_btc_ticker),
            ("1H Candles + Volatility", test_candles),
            ("Orderbook Depth", test_orderbook),
            ("Funding Rate", test_funding_rate),
            ("Volatility -> Regime -> Fee", test_volatility_computation),
            ("Multi-pair Snapshot", test_multi_pair_snapshot),
        ])

    if has_dex:
        tests.extend([
            ("DEX Supported Chains", test_dex_supported_chains),
            ("DEX X Layer Tokens", test_dex_all_tokens),
            ("DEX Quote OKB->USDT", test_dex_quote),
        ])

    results = []
    for name, fn in tests:
        try:
            ok = fn()
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            ok = False
        results.append((name, ok))

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    print(f"\n  {passed}/{len(results)} tests passed")
    print("=" * 60)

    if passed < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
