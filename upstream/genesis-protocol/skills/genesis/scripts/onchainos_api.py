"""Onchain OS REST API Client - Market data + DEX aggregator integration.

Uses requests with HMAC-SHA256 authentication per OKX API docs.
Supports two base URLs:
  - Market/Public API: https://www.okx.com  (account-level API key)
  - DEX/Web3 API:     https://web3.okx.com  (project-level API key)

Falls back to onchainos CLI subprocess when the REST API is unavailable.

Credentials loaded from environment variables:
    OK_ACCESS_KEY, OK_ACCESS_SECRET, OK_ACCESS_PASSPHRASE
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import subprocess
from datetime import datetime, timezone

try:
    import requests as _requests
except ImportError:
    _requests = None

logger = logging.getLogger(__name__)

BASE_URL = "https://web3.okx.com"
MARKET_BASE_URL = "https://www.okx.com"


class OnchainOSAPI:
    """REST API client for Onchain OS with CLI fallback.

    Integrates both OKX Market API (price, candles, orderbook, funding)
    and OKX DEX Aggregator API (quote, swap, tokens) for the Genesis
    Protocol perception and trade execution layers.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
        base_url: str = BASE_URL,
        market_base_url: str = MARKET_BASE_URL,
        timeout: int = 30,
    ):
        self.api_key = api_key or os.environ.get("OK_ACCESS_KEY", "")
        self.api_secret = api_secret or os.environ.get("OK_ACCESS_SECRET", "")
        self.passphrase = passphrase or os.environ.get("OK_ACCESS_PASSPHRASE", "")
        self.base_url = base_url.rstrip("/")
        self.market_base_url = market_base_url.rstrip("/")
        self.timeout = timeout
        self._has_credentials = bool(self.api_key and self.api_secret and self.passphrase)
        if not self._has_credentials:
            logger.warning(
                "OnchainOSAPI: missing API credentials; REST calls will fall back to CLI"
            )

    # ── Authentication ────────────────────────────────────────────────────

    def _sign(self, method: str, request_path: str, body: str = "") -> dict:
        """Build HMAC-SHA256 signed headers for an OKX Web3 API request."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        message = timestamp + method.upper() + request_path + body
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

    # ── Low-level request helpers ─────────────────────────────────────────

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict | None:
        """Execute an authenticated REST request via requests lib. Returns parsed JSON or None."""
        if not self._has_credentials:
            logger.debug("No credentials; skipping REST request %s %s", method, path)
            return None
        if _requests is None:
            logger.error("requests library not installed")
            return None

        request_path = path
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            request_path = path + "?" + qs

        body_str = json.dumps(body) if body else ""
        headers = self._sign(method.upper(), request_path, body_str)
        url = self.base_url + request_path

        try:
            if method.upper() == "GET":
                resp = _requests.get(url, headers=headers, timeout=self.timeout)
            else:
                resp = _requests.post(url, headers=headers, data=body_str, timeout=self.timeout)
            data = resp.json()
            logger.debug("REST %s %s -> %s", method, path, data.get("code", "ok"))
            return data
        except Exception as exc:
            logger.error("REST error for %s %s: %s", method, path, exc)
        return None

    def _cli_fallback(self, cmd: list[str]) -> dict | None:
        """Execute an onchainos CLI command as fallback. Returns parsed JSON or None."""
        logger.debug("CLI fallback: %s", " ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
            if result.returncode != 0:
                logger.error("CLI fallback failed (rc=%d): %s", result.returncode, result.stderr.strip())
                return None
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            logger.error("CLI fallback timed out: %s", " ".join(cmd))
        except json.JSONDecodeError as exc:
            logger.error("CLI fallback invalid JSON: %s", exc)
        except OSError as exc:
            logger.error("CLI fallback OS error: %s", exc)
        return None

    def _request_with_fallback(self, method: str, path: str, cli_cmd: list[str],
                                params: dict | None = None, body: dict | None = None) -> dict | None:
        """Try REST API first; fall back to CLI subprocess, then stdlib GET."""
        result = self._request(method, path, params=params, body=body)
        if result is not None:
            return result
        logger.info("REST unavailable for %s; falling back to CLI", path)
        cli_result = self._cli_fallback(cli_cmd)
        if cli_result is not None:
            return cli_result
        # Last resort: stdlib GET (works for public endpoints without auth)
        if method.upper() == "GET":
            request_path = path
            if params:
                qs = "&".join(f"{k}={v}" for k, v in params.items())
                request_path = path + "?" + qs
            url = self.base_url + request_path
            logger.info("CLI unavailable for %s; falling back to stdlib GET", path)
            return self._stdlib_get_json(url)
        return None

    def _market_request(self, path: str, params: dict | None = None) -> dict | None:
        """Execute a GET against the Market API (www.okx.com).

        OKX Market API endpoints (/api/v5/market/*, /api/v5/public/*) are
        PUBLIC and do NOT require authentication. When credentials are
        available, signed headers are included for higher rate limits.
        Falls back to stdlib urllib when the ``requests`` library is absent.
        """
        request_path = path
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            request_path = path + "?" + qs

        url = self.market_base_url + request_path

        # Try with requests library (with auth if available, without if not)
        if _requests is not None:
            try:
                headers = self._sign("GET", request_path) if self._has_credentials else {
                    "Content-Type": "application/json",
                    "User-Agent": "genesis-protocol/1.0",
                }
                resp = _requests.get(url, headers=headers, timeout=self.timeout)
                data = resp.json()
                if data.get("code") == "0":
                    logger.debug("Market GET %s -> OK (%d items)", path,
                                 len(data.get("data", [])))
                else:
                    logger.debug("Market GET %s -> code=%s msg=%s",
                                 path, data.get("code"), data.get("msg"))
                return data
            except Exception as exc:
                logger.error("Market error for %s: %s", path, exc)

        # Stdlib fallback (no auth — public endpoints only)
        return self._stdlib_get_json(url)

    def _stdlib_get_json(self, url: str) -> dict | None:
        """Fetch JSON from a URL using only stdlib urllib.request (no auth)."""
        import urllib.request
        import urllib.error
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "genesis-protocol/1.0")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.error("stdlib GET %s failed: %s", url, exc)
            return None

    # ── Market Data Endpoints (Perception Layer) ───────────────────────────

    def get_ticker(self, inst_id: str = "ETH-USDT") -> dict | None:
        """GET real-time ticker for a trading pair.

        Used by the Perception Layer to feed live price data into the
        Genesis Engine for volatility calculation and regime detection.

        Returns: {code, data: [{last, open24h, high24h, low24h, vol24h, ...}]}
        """
        return self._market_request(
            "/api/v5/market/ticker", {"instId": inst_id}
        )

    def get_candles(self, inst_id: str = "ETH-USDT", bar: str = "1H",
                    limit: int = 20) -> dict | None:
        """GET historical candlestick data for volatility calculation.

        Used by the Analysis Layer to compute rolling volatility, detect
        trends, and classify market regime (calm/volatile/trending).

        Returns: {code, data: [[ts, open, high, low, close, vol, ...], ...]}
        """
        return self._market_request(
            "/api/v5/market/candles",
            {"instId": inst_id, "bar": bar, "limit": str(limit)},
        )

    def get_orderbook(self, inst_id: str = "ETH-USDT", depth: int = 5) -> dict | None:
        """GET orderbook depth for spread and liquidity analysis.

        Used by the MEV Protection Module to assess liquidity conditions
        and detect potential sandwich attack setups.

        Returns: {code, data: [{asks: [[price, qty, ...]], bids: [...]}]}
        """
        return self._market_request(
            "/api/v5/market/books",
            {"instId": inst_id, "sz": str(depth)},
        )

    def get_funding_rate(self, inst_id: str = "ETH-USDT-SWAP") -> dict | None:
        """GET current funding rate for a perpetual swap.

        Used by the Analysis Layer to gauge market sentiment and directional
        bias, which feeds into the DynamicFee Module's fee adjustment.

        Returns: {code, data: [{fundingRate, nextFundingRate, fundingTime, ...}]}
        """
        return self._market_request(
            "/api/v5/public/funding-rate", {"instId": inst_id}
        )

    def get_mark_price(self, inst_id: str = "ETH-USDT-SWAP") -> dict | None:
        """GET mark price for a derivatives instrument.

        Returns: {code, data: [{instId, markPx, ts}]}
        """
        return self._market_request(
            "/api/v5/public/mark-price",
            {"instType": "SWAP", "instId": inst_id},
        )

    def compute_volatility(self, inst_id: str = "ETH-USDT", bar: str = "1H",
                           limit: int = 20) -> dict | None:
        """Fetch candles and compute rolling volatility (std/mean of closes).

        This is the primary data feed for the DynamicFee Module's fee curve.
        Returns dict with volatility_pct, avg_price, std_dev, candle_count.
        """
        candles_resp = self.get_candles(inst_id, bar, limit)
        if not candles_resp or candles_resp.get("code") != "0":
            return None

        closes = [float(c[4]) for c in candles_resp["data"]]
        if len(closes) < 2:
            return None

        avg = sum(closes) / len(closes)
        std = (sum((p - avg) ** 2 for p in closes) / len(closes)) ** 0.5
        vol_pct = (std / avg) * 100

        return {
            "inst_id": inst_id,
            "bar": bar,
            "candle_count": len(closes),
            "avg_price": round(avg, 4),
            "std_dev": round(std, 4),
            "volatility_pct": round(vol_pct, 4),
            "latest_close": closes[0],
        }

    # ── DEX Aggregator Endpoints (V6 - Trade Execution Layer) ──────────────

    def get_supported_chains(self) -> dict | None:
        """GET supported chains for DEX aggregation.

        Returns all chains supported by the OKX DEX aggregator, including
        X Layer (chainIndex=196). Used to verify chain availability.
        """
        path = "/api/v6/dex/aggregator/supported/chain"
        cli_cmd = ["onchainos", "aggregator", "supported-chains"]
        return self._request_with_fallback("GET", path, cli_cmd)

    def get_dex_tokens(self, chain_index: str = "196") -> dict | None:
        """GET all tradeable tokens on a chain via DEX aggregator.

        Used by the Perception Layer to discover available tokens on X Layer
        and check token metadata (decimals, honeypot status, tax rate).
        """
        path = "/api/v6/dex/aggregator/all-tokens"
        params = {"chainIndex": chain_index}
        cli_cmd = ["onchainos", "aggregator", "all-tokens", "--chain", chain_index]
        return self._request_with_fallback("GET", path, cli_cmd, params=params)

    def get_price(self, base: str, quote: str, chain_id: str = "196") -> dict | None:
        """GET price data for a base/quote pair.

        Tries the Market API ticker endpoint first (e.g. ETH-USDT), then falls
        back to the DEX aggregator quote endpoint on X Layer.

        Returns: dict with ``price``, ``base``, ``quote`` keys, or None.
        """
        # Try Market API ticker first (most accurate for major pairs)
        inst_id = f"{base}-{quote}"
        ticker = self.get_ticker(inst_id)
        if ticker and ticker.get("code") == "0" and ticker.get("data"):
            last = ticker["data"][0].get("last")
            if last:
                return {"price": float(last), "base": base, "quote": quote,
                        "source": "market_ticker", "inst_id": inst_id}

        # Fallback: DEX aggregator quote (on-chain price)
        # Use well-known token addresses on X Layer
        token_map = {
            "ETH": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
            "WETH": "0x5A77f1443D16ee5761d310e38b62f77f726bC71c",
            "USDT": "0x1E4a5963aBFD975d8c9021ce480b42188849D41d",
            "USDC": "0x74b7F16337b8972027F6196A17a631aC6dE26d22",
            "OKB": "0xBb9cFe74E22EFC56C0F020F20D1684F02994a651",
        }
        token_in = token_map.get(base.upper())
        token_out = token_map.get(quote.upper())
        if token_in and token_out:
            # Quote 1 unit of base token
            decimals = 18
            amount = str(10 ** decimals)
            quote_resp = self.get_dex_quote(token_in, token_out, amount, chain_id)
            if quote_resp and quote_resp.get("data"):
                try:
                    route_data = quote_resp["data"][0] if isinstance(quote_resp["data"], list) else quote_resp["data"]
                    to_amount = float(route_data.get("toTokenAmount", 0))
                    to_decimals = int(route_data.get("toToken", {}).get("decimal", 18))
                    price = to_amount / (10 ** to_decimals)
                    return {"price": price, "base": base, "quote": quote,
                            "source": "dex_aggregator", "chain_id": chain_id}
                except (KeyError, ValueError, TypeError, IndexError):
                    pass

        return None

    def get_dex_quote(self, token_in: str, token_out: str, amount: str,
                      chain_id: str = "196", slippage: str = "50") -> dict | None:
        """GET a DEX swap quote via the V6 aggregator.

        Used by the Planning Layer to simulate swap outcomes, estimate
        slippage, and compare against hook pool fees before execution.

        Returns route details including dexName, fromToken, toToken amounts.
        """
        path = "/api/v6/dex/aggregator/quote"
        params = {
            "fromTokenAddress": token_in, "toTokenAddress": token_out,
            "amount": amount, "chainIndex": chain_id, "slippage": slippage,
        }
        cli_cmd = [
            "onchainos", "aggregator", "quote",
            "--from-token", token_in, "--to-token", token_out,
            "--amount", amount, "--chain", chain_id, "--slippage", slippage,
        ]
        return self._request_with_fallback("GET", path, cli_cmd, params=params)

    def post_swap(self, token_in: str, token_out: str, amount: str, user_address: str,
                  chain_id: str = "196", slippage: str = "50") -> dict | None:
        """POST a DEX swap execution via V6 aggregator.

        Used by the Rebalance Agent to execute position adjustments through
        the most efficient route across X Layer DEX liquidity sources.
        """
        path = "/api/v6/dex/aggregator/swap"
        body = {
            "fromTokenAddress": token_in, "toTokenAddress": token_out,
            "amount": amount, "userWalletAddress": user_address,
            "chainIndex": chain_id, "slippage": slippage,
        }
        cli_cmd = [
            "onchainos", "aggregator", "swap",
            "--from-token", token_in, "--to-token", token_out,
            "--amount", amount, "--user", user_address,
            "--chain", chain_id, "--slippage", slippage,
        ]
        return self._request_with_fallback("POST", path, cli_cmd, body=body)

    # ── Wallet Endpoints ──────────────────────────────────────────────────

    def get_balances(self, address: str, chain_id: str = "196") -> dict | None:
        """GET wallet token balances on a specific chain.

        Used by the Perception Layer to check wallet holdings and by the
        Sentinel Agent for portfolio health monitoring.
        """
        path = "/api/v5/wallet/asset/token-balances-by-address"
        params = {"address": address, "chainIndex": chain_id}
        cli_cmd = ["onchainos", "wallet", "balances", "--address", address, "--chain", chain_id]
        return self._request_with_fallback("GET", path, cli_cmd, params=params)

    def get_portfolio(self, address: str) -> dict | None:
        """GET wallet portfolio overview (cross-chain)."""
        path = "/api/v5/dex/wallet/portfolio"
        params = {"address": address}
        cli_cmd = ["onchainos", "wallet", "portfolio", "--address", address]
        return self._request_with_fallback("GET", path, cli_cmd, params=params)

    # ── Integration Verification ──────────────────────────────────────────

    def verify_integration(self) -> dict:
        """Verify OnchainOS API connectivity across DEX and Market endpoints.

        Calls get_supported_chains() to verify DEX API connectivity and
        get_ticker("ETH-USDT") to verify Market API connectivity.

        Uses only stdlib (urllib.request) as a fallback if the ``requests``
        library is not available, ensuring the check works in minimal
        environments.

        Returns:
            A status dict with keys: ``status``, ``dex_api``, ``market_api``,
            ``has_credentials``, ``has_requests_lib``, ``timestamp``.
        """
        from datetime import datetime, timezone as _tz

        result = {
            "status": "unknown",
            "dex_api": "untested",
            "market_api": "untested",
            "has_credentials": self._has_credentials,
            "has_requests_lib": _requests is not None,
            "timestamp": datetime.now(_tz.utc).isoformat(),
        }

        # --- DEX API check (get_supported_chains) -------------------------
        dex_resp = self.get_supported_chains()
        if dex_resp is not None:
            code = dex_resp.get("code") if isinstance(dex_resp, dict) else None
            if code == "0" or (isinstance(dex_resp, dict) and "data" in dex_resp):
                result["dex_api"] = "connected"
            else:
                result["dex_api"] = f"response_code={code}"
        else:
            # stdlib fallback: try a plain GET without auth
            result["dex_api"] = self._stdlib_get(
                self.base_url + "/api/v6/dex/aggregator/supported/chain"
            )

        # --- Market API check (get_ticker) ---------------------------------
        ticker_resp = self.get_ticker("ETH-USDT")
        if ticker_resp is not None:
            code = ticker_resp.get("code") if isinstance(ticker_resp, dict) else None
            if code == "0" and ticker_resp.get("data"):
                last = ticker_resp["data"][0].get("last", "?")
                result["market_api"] = f"connected (ETH-USDT={last})"
            else:
                result["market_api"] = f"response_code={code}"
        else:
            # stdlib fallback
            result["market_api"] = self._stdlib_get(
                self.market_base_url + "/api/v5/market/ticker?instId=ETH-USDT"
            )

        # --- Overall status ------------------------------------------------
        dex_ok = result["dex_api"].startswith("connected") or result["dex_api"].startswith("response_code")
        mkt_ok = result["market_api"].startswith("connected") or result["market_api"].startswith("response_code")
        if dex_ok and mkt_ok:
            result["status"] = "operational"
        elif dex_ok or mkt_ok:
            result["status"] = "partial"
        else:
            result["status"] = "degraded"

        logger.info("verify_integration result: %s", result)
        return result

    @staticmethod
    def _stdlib_get(url: str) -> str:
        """Attempt a plain HTTP GET using only urllib.request (no auth).

        Returns a short status string for use in verify_integration().
        """
        import urllib.request
        import urllib.error
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "genesis-protocol/1.0")
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                code = body.get("code") if isinstance(body, dict) else None
                if code == "0":
                    return "connected (stdlib)"
                return f"response_code={code} (stdlib)"
        except urllib.error.HTTPError as exc:
            return f"http_error_{exc.code} (stdlib)"
        except urllib.error.URLError as exc:
            return f"url_error: {exc.reason} (stdlib)"
        except Exception as exc:
            return f"error: {exc} (stdlib)"
