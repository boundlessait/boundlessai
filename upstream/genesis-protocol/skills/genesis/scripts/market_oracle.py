"""Market data aggregation using OnchainOS Market module.

Provides price fetching, volatility calculation, trend detection,
and market regime classification via the onchainos CLI.
"""
import subprocess
import json
import logging
import math
import time
import statistics
import urllib.request
import urllib.error

from . import config
from .onchainos_api import OnchainOSAPI

logger = logging.getLogger(__name__)
PRICE_CACHE_TTL = 60  # seconds

# Symbol -> CoinGecko ID mapping for common tokens
_SYMBOL_TO_COINGECKO_ID = {
    "ETH": "ethereum",
    "BTC": "bitcoin",
    "OKB": "okb",
    "USDT": "tether",
    "USDC": "usd-coin",
    "DAI": "dai",
    "WETH": "wethereum",
    "WBTC": "wrapped-bitcoin",
    "SOL": "solana",
    "AVAX": "avalanche-2",
    "MATIC": "matic-network",
    "BNB": "binancecoin",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "AAVE": "aave",
    "ARB": "arbitrum",
    "OP": "optimism",
}

# Maps internal regime names to config.STRATEGY_PRESETS keys
_REGIME_TO_PRESET = {
    "momentum": "trend_rider",
    "defensive": "volatile_defender",
    "volatile_range": "volatile_defender",
    "trend_following": "trend_rider",
    "mean_reversion": "calm_accumulator",
}


class MarketOracle:
    """Aggregates market data from multiple oracle sources for strategy decisions.

    Fetches prices from OnchainOS, CoinGecko, and OKX, using a median-based
    consensus mechanism to improve reliability and resilience.
    """

    def __init__(self):
        """Initialize with configured trading pairs, price cache, and history."""
        self.pairs = config.ONCHAINOS_MARKET_PAIRS
        self.chain_id = getattr(config, "CHAIN_ID", "1")
        self._price_cache = {}  # (base, quote) -> (timestamp, price)
        self._last_source_prices = {}  # (base, quote) -> raw source data from last fetch
        self._price_history = {}  # (base, quote) -> [(timestamp, price), ...]
        self._api = OnchainOSAPI()
        self._source_reliability = {
            "onchainos": {"success": 0, "failure": 0},
            "coingecko": {"success": 0, "failure": 0},
            "okx": {"success": 0, "failure": 0},
        }
        logger.info("MarketOracle initialized with %d pairs (REST API available: %s)",
                     len(self.pairs), self._api._has_credentials)

    # -- Price fetching ------------------------------------------------- #

    def fetch_price(self, base: str, quote: str) -> float | None:
        """Get the current price for a base/quote pair using multi-source consensus.

        Fetches from OnchainOS, CoinGecko, and OKX in parallel-fashion, then
        returns the median of all successful responses.  Falls back gracefully
        when one or more sources are unavailable.  Returns the cached value if
        it is younger than PRICE_CACHE_TTL seconds.
        """
        key = (base, quote)
        now = time.time()
        cached = self._price_cache.get(key)
        if cached and (now - cached[0]) < PRICE_CACHE_TTL:
            logger.debug("Cache hit for %s/%s", base, quote)
            return cached[1]

        # Collect prices from all available sources
        source_prices: dict[str, float | None] = {}

        # Source 1: OnchainOS (REST API + CLI fallback)
        source_prices["onchainos"] = self._fetch_from_onchainos(base, quote)

        # Source 2: CoinGecko via server proxy
        source_prices["coingecko"] = self._fetch_from_coingecko(base, quote)

        # Source 3: OKX via server proxy
        source_prices["okx"] = self._fetch_from_okx(base, quote)

        # Track reliability and collect valid prices
        valid_prices: list[float] = []
        succeeded: list[str] = []
        failed: list[str] = []
        for source, px in source_prices.items():
            if px is not None and px > 0:
                self._source_reliability[source]["success"] += 1
                valid_prices.append(px)
                succeeded.append(source)
            else:
                self._source_reliability[source]["failure"] += 1
                failed.append(source)

        if not valid_prices:
            logger.error("All price sources failed for %s/%s", base, quote)
            return None

        # Use median for consensus
        price = statistics.median(valid_prices)

        if failed:
            logger.warning(
                "Price sources failed for %s/%s: %s", base, quote, ", ".join(failed)
            )
        logger.info(
            "Consensus price %s/%s = %s (median of %d sources: %s; values: %s)",
            base, quote, price, len(valid_prices),
            ", ".join(succeeded),
            ", ".join(f"{s}={source_prices[s]}" for s in succeeded),
        )

        self._price_cache[key] = (now, price)
        self._last_source_prices[key] = {
            "valid_prices": valid_prices,
            "source_prices": source_prices,
            "succeeded": succeeded,
            "failed": failed,
            "median": price,
        }
        self.update_price_history(base, quote, price)
        return price

    def get_price_with_confidence(self, base: str, quote: str) -> dict | None:
        """Get the current price with full confidence metadata for a base/quote pair.

        Returns a dict with keys:
            - price (float): median consensus price
            - confidence (float): 0.0-1.0 score; 1.0 when all sources agree within 0.5%
            - spread (float): percentage spread (max-min)/median
            - sources_agreed (int): number of sources within 1% of the median
            - total_sources (int): total number of sources that returned valid prices
            - source_details (list): per-source dicts with name, price, and deviation

        Calls ``fetch_price`` internally to ensure caching and history are updated,
        then computes agreement metrics from the last fetch's raw source data.

        Returns ``None`` if no price could be fetched from any source.
        """
        price = self.fetch_price(base, quote)
        if price is None:
            return None

        key = (base, quote)
        raw = self._last_source_prices.get(key)
        if raw is None:
            # Fallback: only cached price available, no per-source detail
            return {
                "price": price,
                "confidence": 0.5,
                "spread": 0.0,
                "sources_agreed": 1,
                "total_sources": 1,
                "source_details": [],
            }

        return self._compute_confidence_result(price, raw)

    def _compute_confidence_result(self, median_price: float, raw: dict) -> dict:
        """Build the confidence-enriched result dict from raw source data.

        Args:
            median_price: the consensus (median) price already computed.
            raw: internal dict produced during ``fetch_price`` containing
                 ``valid_prices``, ``source_prices``, ``succeeded``, and ``failed``.

        Returns:
            A dict conforming to the ``get_price_with_confidence`` contract.
        """
        valid_prices: list[float] = raw["valid_prices"]
        source_prices: dict = raw["source_prices"]
        succeeded: list[str] = raw["succeeded"]
        total_sources = len(valid_prices)

        # Spread as percentage: (max - min) / median * 100
        if total_sources >= 2:
            spread = (max(valid_prices) - min(valid_prices)) / median_price * 100
        else:
            spread = 0.0

        # Sources agreed: within 1% of the median
        sources_agreed = 0
        source_details: list[dict] = []
        for src_name in succeeded:
            px = source_prices.get(src_name)
            if px is not None and px > 0:
                deviation_pct = abs(px - median_price) / median_price * 100
                source_details.append({
                    "name": src_name,
                    "price": px,
                    "deviation_pct": round(deviation_pct, 4),
                })
                if deviation_pct <= 1.0:
                    sources_agreed += 1

        # Confidence calculation:
        # Start at 1.0 when all sources agree within 0.5% spread,
        # decrease as spread widens. Penalise for fewer agreeing sources.
        if spread <= 0.5:
            spread_factor = 1.0
        elif spread <= 5.0:
            # Linear decay from 1.0 at 0.5% to 0.1 at 5.0%
            spread_factor = max(0.1, 1.0 - (spread - 0.5) / (5.0 - 0.5) * 0.9)
        else:
            spread_factor = 0.1

        agreement_factor = sources_agreed / total_sources if total_sources > 0 else 0.0
        confidence = round(
            max(0.0, min(1.0, spread_factor * 0.6 + agreement_factor * 0.4)), 4
        )

        result = {
            "price": median_price,
            "confidence": confidence,
            "spread": round(spread, 4),
            "sources_agreed": sources_agreed,
            "total_sources": total_sources,
            "source_details": source_details,
        }
        logger.debug("Price with confidence %s: %s", median_price, result)
        return result

    def _fetch_from_onchainos(self, base: str, quote: str) -> float | None:
        """Fetch price from OnchainOS REST API with CLI fallback."""
        try:
            data = self._api.get_price(base, quote, str(self.chain_id))
            if data is None:
                cmd = [
                    "onchainos", "market", "price",
                    "--base", base,
                    "--quote", quote,
                    "--chain", self.chain_id,
                ]
                data = self._run_cmd(cmd)
            if data is not None:
                return float(data.get("price", 0))
        except (ValueError, TypeError, KeyError) as exc:
            logger.error("OnchainOS price parse error for %s/%s: %s", base, quote, exc)
        return None

    def _fetch_from_coingecko(self, base: str, quote: str) -> float | None:
        """Fetch price from CoinGecko via the server's /cg-api/ proxy.

        Maps token symbols to CoinGecko IDs and queries the simple/price
        endpoint. Returns ``None`` on any failure.
        """
        base_id = _SYMBOL_TO_COINGECKO_ID.get(base.upper())
        if base_id is None:
            # Try using the lowercase symbol as a fallback ID
            base_id = base.lower()
            logger.debug("No CoinGecko ID mapping for %s, trying '%s'", base, base_id)

        quote_lower = quote.lower()
        # CoinGecko uses 'usd' for stablecoins when used as vs_currency
        if quote_lower in ("usdt", "usdc"):
            quote_lower = "usd"

        url = (
            f"http://localhost:3000/cg-api/api/v3/simple/price"
            f"?ids={base_id}&vs_currencies={quote_lower}"
        )
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode())
            price = body.get(base_id, {}).get(quote_lower)
            if price is not None:
                return float(price)
            logger.warning("CoinGecko returned no price for %s/%s: %s", base, quote, body)
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            logger.error("CoinGecko request failed for %s/%s: %s", base, quote, exc)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            logger.error("CoinGecko parse error for %s/%s: %s", base, quote, exc)
        return None

    def _fetch_from_okx(self, base: str, quote: str) -> float | None:
        """Fetch price from OKX via the server's /okx-api/ proxy.

        Constructs the instrument ID as ``{BASE}-{QUOTE}`` and queries the
        v5 market ticker endpoint. Returns ``None`` on any failure.
        """
        inst_id = f"{base.upper()}-{quote.upper()}"
        url = (
            f"http://localhost:3000/okx-api/api/v5/market/ticker"
            f"?instId={inst_id}"
        )
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode())
            data_list = body.get("data")
            if data_list and len(data_list) > 0:
                last = data_list[0].get("last")
                if last is not None:
                    return float(last)
            logger.warning("OKX returned no price for %s/%s: %s", base, quote, body)
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            logger.error("OKX request failed for %s/%s: %s", base, quote, exc)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            logger.error("OKX parse error for %s/%s: %s", base, quote, exc)
        return None

    def fetch_all_prices(self) -> dict:
        """Fetch prices for every configured pair.

        Returns a dict mapping ``(base, quote)`` to the latest price.
        """
        results = {}
        for pair in self.pairs:
            base, quote = pair["base"], pair["quote"]
            price = self.fetch_price(base, quote)
            if price is not None:
                results[(base, quote)] = price
        logger.info("Fetched prices for %d/%d pairs", len(results), len(self.pairs))
        return results

    def get_source_health(self) -> dict:
        """Return reliability statistics for each oracle price source.

        Returns a dict keyed by source name, each containing ``success``,
        ``failure``, ``total``, and ``reliability_pct`` fields.
        """
        health = {}
        for source, counts in self._source_reliability.items():
            total = counts["success"] + counts["failure"]
            reliability = (counts["success"] / total * 100) if total > 0 else 0.0
            health[source] = {
                "success": counts["success"],
                "failure": counts["failure"],
                "total": total,
                "reliability_pct": round(reliability, 2),
            }
        logger.info("Source health: %s", health)
        return health

    # -- Analytics ------------------------------------------------------- #

    def calculate_volatility(
        self, base: str, quote: str, window_hours: float | None = None
    ) -> float | None:
        """Calculate realised volatility from stored price history.

        Uses standard deviation of log-returns over *window_hours*
        (defaults to ``config.VOLATILITY_WINDOW_HOURS``).
        """
        window = window_hours or config.VOLATILITY_WINDOW_HOURS
        prices = self._windowed_prices(base, quote, window)
        if len(prices) < 2:
            logger.warning("Not enough price points for %s/%s volatility", base, quote)
            return None

        log_returns = self._calculate_log_returns(prices)
        vol = statistics.stdev(log_returns) * math.sqrt(len(log_returns))
        logger.info("Volatility %s/%s (%.1fh): %.6f", base, quote, window, vol)
        return vol

    def detect_trend(
        self, base: str, quote: str, window_hours: float | None = None
    ) -> str:
        """Detect trend direction using a simple moving-average comparison.

        Compares the short-window SMA (first half) against the long-window SMA
        (full window).  Returns ``"trending_up"``, ``"trending_down"``, or
        ``"sideways"``.
        """
        window = window_hours or config.TREND_WINDOW_HOURS
        prices = self._windowed_prices(base, quote, window)
        if len(prices) < 4:
            logger.warning("Not enough data to detect trend for %s/%s", base, quote)
            return "sideways"

        mid = len(prices) // 2
        sma_recent = statistics.mean(prices[mid:])
        sma_full = statistics.mean(prices)

        pct_diff = (sma_recent - sma_full) / sma_full if sma_full else 0
        threshold = getattr(config, "TREND_THRESHOLD", 0.005)

        if pct_diff > threshold:
            trend = "trending_up"
        elif pct_diff < -threshold:
            trend = "trending_down"
        else:
            trend = "sideways"

        logger.info("Trend %s/%s: %s (delta=%.4f)", base, quote, trend, pct_diff)
        return trend

    def get_market_regime(self, base: str, quote: str) -> dict:
        """Combine volatility and trend into a market-regime classification.

        Returns a dict with keys: ``volatility``, ``trend``, ``regime_name``,
        and ``confidence``.  The ``regime_name`` maps to one of the keys in
        ``config.STRATEGY_PRESETS``.
        """
        vol = self.calculate_volatility(base, quote)
        trend = self.detect_trend(base, quote)

        high_vol_threshold = getattr(config, "HIGH_VOL_THRESHOLD", 0.04)
        is_high_vol = vol is not None and vol > high_vol_threshold

        if is_high_vol and trend == "trending_up":
            regime = "momentum"
            confidence = 0.8
        elif is_high_vol and trend == "trending_down":
            regime = "defensive"
            confidence = 0.75
        elif is_high_vol:
            regime = "volatile_range"
            confidence = 0.6
        elif trend in ("trending_up", "trending_down"):
            regime = "trend_following"
            confidence = 0.7
        else:
            regime = "mean_reversion"
            confidence = 0.65

        preset_name = _REGIME_TO_PRESET.get(regime, "calm_accumulator")
        presets = getattr(config, "STRATEGY_PRESETS", {})
        if preset_name not in presets:
            logger.warning("Preset '%s' (from regime '%s') not found in STRATEGY_PRESETS", preset_name, regime)

        result = {
            "volatility": vol,
            "trend": trend,
            "regime_name": regime,
            "preset_name": preset_name,
            "confidence": confidence,
        }
        logger.info("Market regime %s/%s: %s", base, quote, result)
        return result

    # -- Price history --------------------------------------------------- #

    def update_price_history(self, base: str, quote: str, price: float) -> None:
        """Append a timestamped price entry to the history for a pair."""
        key = (base, quote)
        self._price_history.setdefault(key, []).append((time.time(), price))

    # -- DEX quoting ---------------------------------------------------- #

    def get_dex_quote(
        self, token_in: str, token_out: str, amount: float
    ) -> dict | None:
        """Get a DEX swap quote via the onchainos CLI.

        Uses ``config.DEX_SLIPPAGE_BPS`` for slippage tolerance.
        """
        # Try REST API first, fall back to CLI subprocess
        data = self._api.get_dex_quote(
            token_in, token_out, str(amount),
            chain_id=str(self.chain_id),
            slippage=str(config.DEX_SLIPPAGE_BPS),
        )
        if data is None:
            cmd = [
                "onchainos", "trade", "quote",
                "--token-in", token_in,
                "--token-out", token_out,
                "--amount", str(amount),
                "--chain", self.chain_id,
                "--slippage", str(config.DEX_SLIPPAGE_BPS),
            ]
            data = self._run_cmd(cmd)
        if data is not None:
            logger.info(
                "DEX quote %s->%s (%s): %s", token_in, token_out, amount, data
            )
        return data

    # -- Uniswap AI Skills Integration --------------------------------- #

    def get_uniswap_pool_data(
        self, token_in: str, token_out: str
    ) -> dict | None:
        """Get Uniswap pool liquidity and pricing data via the uniswap-trading skill.

        Returns the skill response dict, or ``None`` on failure.
        """
        cmd = ["onchainos", "skill", "run", "uniswap-trading", "pool-info",
               "--token-in", token_in,
               "--token-out", token_out,
               "--chain", str(config.CHAIN_ID)]
        logger.info("Fetching Uniswap pool data for %s -> %s", token_in, token_out)
        data = self._run_cmd(cmd)
        if data is not None:
            logger.info("Uniswap pool data %s/%s: %s", token_in, token_out, data)
        else:
            logger.error("Failed to fetch Uniswap pool data for %s/%s", token_in, token_out)
        return data

    def get_optimal_swap_route(
        self, token_in: str, token_out: str, amount: float
    ) -> dict | None:
        """Get the optimal Uniswap swap route via the uniswap-trading skill.

        Returns the skill response dict with route information, or ``None`` on failure.
        """
        cmd = ["onchainos", "skill", "run", "uniswap-trading", "route",
               "--token-in", token_in,
               "--token-out", token_out,
               "--amount", str(amount),
               "--chain", str(config.CHAIN_ID)]
        logger.info("Fetching optimal swap route %s -> %s (amount=%s)", token_in, token_out, amount)
        data = self._run_cmd(cmd)
        if data is not None:
            logger.info("Optimal route %s->%s: %s", token_in, token_out, data)
        else:
            logger.error("Failed to fetch optimal swap route for %s->%s", token_in, token_out)
        return data

    # -- Internal helpers ------------------------------------------------ #

    def _run_cmd(self, cmd: list[str]) -> dict | None:
        """Execute a subprocess command and return parsed JSON output.

        Returns ``None`` on any failure (non-zero exit, invalid JSON, etc.).
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                logger.error(
                    "Command %s failed (rc=%d): %s",
                    cmd, result.returncode, result.stderr.strip(),
                )
                return None
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            logger.error("Command timed out: %s", cmd)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON from command %s: %s", cmd, exc)
        except OSError as exc:
            logger.error("OS error running %s: %s", cmd, exc)
        return None

    def _calculate_log_returns(self, prices: list[float]) -> list[float]:
        """Compute log-returns from an ordered list of prices."""
        return [
            math.log(prices[i] / prices[i - 1])
            for i in range(1, len(prices))
            if prices[i - 1] > 0
        ]

    def _windowed_prices(
        self, base: str, quote: str, window_hours: float
    ) -> list[float]:
        """Return prices within the last *window_hours* hours."""
        key = (base, quote)
        history = self._price_history.get(key, [])
        cutoff = time.time() - (window_hours * 3600)
        return [p for ts, p in history if ts >= cutoff]
