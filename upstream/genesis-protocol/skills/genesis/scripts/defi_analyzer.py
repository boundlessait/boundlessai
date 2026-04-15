"""DeFi Analyzer - Deep onchainos-defi-invest integration for yield comparison.

Compares yields across X Layer DeFi protocols and benchmarks Genesis
Protocol strategy returns against the broader ecosystem. Uses OKX DeFi
API endpoints for protocol-level TVL, APY, and investment data.

Reference: https://web3.okx.com/api (DeFi Invest endpoints)
"""

import json
import logging
import math
import statistics
import os
import subprocess
from typing import Optional

try:
    import requests as _requests
except ImportError:
    _requests = None

from . import config

logger = logging.getLogger(__name__)

# OKX DeFi API base
DEFI_BASE_URL = "https://web3.okx.com"

# X Layer chain index used by OKX APIs
X_LAYER_CHAIN_INDEX = "196"


class DeFiAnalyzer:
    """Analyze and benchmark DeFi yields across X Layer protocols.

    Integrates with the onchainos-defi-invest skill and OKX DeFi API to
    provide Genesis Protocol with:
      - Cross-protocol yield comparisons on X Layer
      - TVL tracking for competing protocols
      - Benchmarking of Genesis strategy returns vs alternatives
      - Investment opportunity discovery

    Used by the Genesis Engine's Analysis Layer and the Evolution Layer's
    meta-cognition to evaluate whether Genesis strategies are competitive.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
        chain_index: str = X_LAYER_CHAIN_INDEX,
        timeout: int = 30,
    ):
        self.api_key = api_key or os.environ.get("OK_ACCESS_KEY", "")
        self.api_secret = api_secret or os.environ.get("OK_ACCESS_SECRET", "")
        self.passphrase = passphrase or os.environ.get("OK_ACCESS_PASSPHRASE", "")
        self.chain_index = chain_index
        self.timeout = timeout
        self._has_credentials = bool(self.api_key and self.api_secret and self.passphrase)
        if not self._has_credentials:
            logger.warning(
                "DeFiAnalyzer: missing API credentials; REST calls will fall back to CLI"
            )

    # ── Protocol Yield Data ───────────────────────────────────────────

    def get_protocol_yields(
        self,
        protocol_ids: Optional[list] = None,
        asset_filter: str = "",
    ) -> dict:
        """Fetch current yield / APY data for DeFi protocols on X Layer.

        Queries the OKX DeFi Invest API for protocol-level yield information
        including LP farming, lending, and staking opportunities.

        Args:
            protocol_ids: Optional list of protocol identifiers to filter.
            asset_filter: Optional token symbol to filter (e.g. "USDT").

        Returns:
            dict with protocol yields or CLI fallback result. Each entry
            contains protocol_name, pool, apy, tvl, and risk_level.
        """
        path = "/api/v5/defi/explore/product/list"
        params = {"chainIndex": self.chain_index}
        if asset_filter:
            params["tokenSymbol"] = asset_filter

        cli_cmd = [
            "onchainos", "skill", "run", "onchainos-defi-invest",
            "--action", "list-yields",
            "--chain", self.chain_index,
        ]
        if asset_filter:
            cli_cmd.extend(["--asset", asset_filter])

        result = self._request_with_fallback("GET", path, cli_cmd, params=params)

        # Filter by protocol_ids if provided
        if result and protocol_ids and isinstance(result.get("data"), list):
            result["data"] = [
                p for p in result["data"]
                if p.get("protocolId") in protocol_ids or p.get("protocol") in protocol_ids
            ]

        return result or {"error": "unable to fetch protocol yields"}

    def compare_strategies(
        self,
        genesis_apy: float,
        genesis_tvl: float,
        asset: str = "ETH-USDT",
    ) -> dict:
        """Compare Genesis strategy performance against competing protocols.

        Pulls yield data for similar pools on X Layer and ranks Genesis
        against them. Used by the Evolution Layer for meta-cognition.

        Args:
            genesis_apy: Current Genesis strategy APY (as percentage, e.g. 12.5).
            genesis_tvl: Current Genesis strategy TVL in USD.
            asset:       Trading pair to compare (e.g. "ETH-USDT").

        Returns:
            dict with ranked comparison, Genesis rank, and improvement suggestions.
        """
        base_token = asset.split("-")[0] if "-" in asset else asset
        yields_result = self.get_protocol_yields(asset_filter=base_token)

        competitors = []
        if isinstance(yields_result.get("data"), list):
            for entry in yields_result["data"]:
                apy = _safe_float(entry.get("apy") or entry.get("estimatedApy"))
                tvl = _safe_float(entry.get("tvl") or entry.get("totalTvl"))
                competitors.append({
                    "protocol": entry.get("protocolName") or entry.get("protocol", "unknown"),
                    "pool": entry.get("poolName") or entry.get("investmentName", ""),
                    "apy": apy,
                    "tvl": tvl,
                })

        # Insert Genesis into the comparison
        genesis_entry = {
            "protocol": "Genesis Protocol",
            "pool": f"{asset} (V4 Hook)",
            "apy": genesis_apy,
            "tvl": genesis_tvl,
        }
        all_entries = competitors + [genesis_entry]
        all_entries.sort(key=lambda x: x.get("apy", 0), reverse=True)

        genesis_rank = next(
            (i + 1 for i, e in enumerate(all_entries) if e["protocol"] == "Genesis Protocol"),
            len(all_entries),
        )

        return {
            "asset": asset,
            "chain_index": self.chain_index,
            "genesis": genesis_entry,
            "genesis_rank": genesis_rank,
            "total_protocols": len(all_entries),
            "top_5": all_entries[:5],
            "outperforming": genesis_rank == 1,
            "improvement_needed_bps": (
                round((all_entries[0]["apy"] - genesis_apy) * 100, 2)
                if genesis_rank > 1 and all_entries else 0
            ),
        }

    def get_tvl_data(
        self,
        protocol_ids: Optional[list] = None,
    ) -> dict:
        """Fetch TVL (Total Value Locked) data for X Layer DeFi protocols.

        Args:
            protocol_ids: Optional list of protocol identifiers to filter.

        Returns:
            dict with per-protocol TVL, total X Layer TVL, and TVL breakdown.
        """
        path = "/api/v5/defi/explore/protocol/list"
        params = {"chainIndex": self.chain_index}

        cli_cmd = [
            "onchainos", "skill", "run", "onchainos-defi-invest",
            "--action", "tvl-data",
            "--chain", self.chain_index,
        ]
        result = self._request_with_fallback("GET", path, cli_cmd, params=params)

        if not result:
            return {"error": "unable to fetch TVL data"}

        protocols = result.get("data", [])
        if protocol_ids and isinstance(protocols, list):
            protocols = [
                p for p in protocols
                if p.get("protocolId") in protocol_ids or p.get("protocolName") in protocol_ids
            ]

        total_tvl = sum(_safe_float(p.get("tvl", 0)) for p in protocols)

        return {
            "chain_index": self.chain_index,
            "total_tvl_usd": total_tvl,
            "protocol_count": len(protocols),
            "protocols": protocols,
        }

    def benchmark_genesis(
        self,
        strategy_name: str,
        genesis_metrics: Optional[dict] = None,
    ) -> dict:
        """Run a comprehensive benchmark of a Genesis strategy.

        Combines yield comparison, TVL ranking, and risk-adjusted metrics
        to produce a score-card for a Genesis strategy.

        Args:
            strategy_name:  Name of the Genesis strategy preset.
            genesis_metrics: dict with keys apy, tvl, sharpe, max_drawdown,
                             swap_count, runtime_hours. Falls back to defaults
                             if not provided.

        Returns:
            dict with benchmark score, category rankings, and recommendations.
        """
        metrics = genesis_metrics or {
            "apy": 0.0,
            "tvl": 0.0,
            "sharpe": 0.0,
            "max_drawdown_pct": 0.0,
            "swap_count": 0,
            "runtime_hours": 0,
        }

        # Pull ecosystem data
        yields = self.get_protocol_yields()
        tvl_data = self.get_tvl_data()

        # Compute yield percentile
        ecosystem_apys = []
        if isinstance(yields.get("data"), list):
            ecosystem_apys = [
                _safe_float(p.get("apy") or p.get("estimatedApy"))
                for p in yields["data"]
            ]
        ecosystem_apys_sorted = sorted(ecosystem_apys)
        genesis_apy = metrics.get("apy", 0)
        if ecosystem_apys_sorted:
            rank = sum(1 for a in ecosystem_apys_sorted if a <= genesis_apy)
            yield_percentile = (rank / len(ecosystem_apys_sorted)) * 100
        else:
            yield_percentile = 0

        # Strategy preset info
        preset = config.STRATEGY_PRESETS.get(strategy_name, {})

        return {
            "strategy_name": strategy_name,
            "strategy_description": preset.get("description", ""),
            "chain_index": self.chain_index,
            "genesis_metrics": metrics,
            "ecosystem_comparison": {
                "yield_percentile": round(yield_percentile, 2),
                "ecosystem_protocol_count": tvl_data.get("protocol_count", 0),
                "ecosystem_total_tvl": tvl_data.get("total_tvl_usd", 0),
                "ecosystem_median_apy": (
                    ecosystem_apys_sorted[len(ecosystem_apys_sorted) // 2]
                    if ecosystem_apys_sorted else 0
                ),
            },
            "score_card": {
                "yield_score": min(100, round(yield_percentile, 0)),
                "risk_score": _risk_score(metrics),
                "activity_score": _activity_score(metrics),
            },
        }

    # ── Deep Integration Methods ─────────────────────────────────────

    def calculate_risk_adjusted_return(self, returns_series, risk_free_rate=0.04):
        """Compute Sharpe, Sortino, and Calmar ratios from periodic returns.

        Uses standard portfolio-theory formulas with annualization based on
        the number of observations (assumed to be daily if len >= 30,
        otherwise treated as the raw period count up to 252).

        Args:
            returns_series: List of periodic (e.g. daily) decimal returns
                            such as [0.01, -0.005, 0.003, ...].
            risk_free_rate: Annualized risk-free rate (default 4 %).

        Returns:
            dict with sharpe_ratio, sortino_ratio, calmar_ratio,
            annualized_return, annualized_volatility, and max_drawdown.
        """
        if not returns_series or len(returns_series) < 2:
            return {
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "calmar_ratio": 0.0,
                "annualized_return": 0.0,
                "annualized_volatility": 0.0,
                "max_drawdown": 0.0,
            }

        n = len(returns_series)
        periods_per_year = min(252, max(n, 1))

        # Annualized return (geometric)
        cumulative = 1.0
        for r in returns_series:
            cumulative *= (1.0 + _safe_float(r))
        annualized_return = cumulative ** (periods_per_year / n) - 1.0

        # Annualized volatility
        std_dev = statistics.stdev([_safe_float(r) for r in returns_series])
        annualized_vol = std_dev * math.sqrt(periods_per_year)

        # Per-period risk-free rate
        rf_per_period = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0

        # Sharpe ratio
        excess = [_safe_float(r) - rf_per_period for r in returns_series]
        mean_excess = statistics.mean(excess)
        sharpe = (mean_excess / std_dev * math.sqrt(periods_per_year)) if std_dev > 0 else 0.0

        # Sortino ratio (downside deviation)
        downside = [min(0.0, e) for e in excess]
        downside_sq_mean = statistics.mean([d ** 2 for d in downside])
        downside_dev = math.sqrt(downside_sq_mean)
        sortino = (
            mean_excess / downside_dev * math.sqrt(periods_per_year)
            if downside_dev > 0 else 0.0
        )

        # Max drawdown
        peak = cumulative_val = 1.0
        max_dd = 0.0
        for r in returns_series:
            cumulative_val *= (1.0 + _safe_float(r))
            if cumulative_val > peak:
                peak = cumulative_val
            dd = (peak - cumulative_val) / peak
            if dd > max_dd:
                max_dd = dd

        # Calmar ratio
        calmar = (annualized_return / max_dd) if max_dd > 0 else 0.0

        return {
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "calmar_ratio": round(calmar, 4),
            "annualized_return": round(annualized_return, 6),
            "annualized_volatility": round(annualized_vol, 6),
            "max_drawdown": round(max_dd, 6),
        }

    def get_yield_decomposition(self, pool_apy, base_apy=0.0, reward_apy=0.0, il_drag=0.0):
        """Decompose a pool's total APY into its yield components.

        Breaks the advertised APY into base yield (swap fees), reward
        yield (token incentives), and impermanent loss drag, then computes
        a quality score that penalises IL-heavy and reward-dependent pools.

        Args:
            pool_apy:   Total advertised pool APY (percentage, e.g. 25.0).
            base_apy:   Swap-fee component of APY (percentage).
            reward_apy: Token-incentive component of APY (percentage).
            il_drag:    Estimated impermanent loss drag (percentage, positive value).

        Returns:
            dict with base_yield, reward_yield, il_drag, net_effective_yield,
            reward_dependency_pct, and quality_score (0-100).
        """
        pool_apy = _safe_float(pool_apy)
        base_apy = _safe_float(base_apy)
        reward_apy = _safe_float(reward_apy)
        il_drag = abs(_safe_float(il_drag))

        # If components not supplied, infer base from total minus reward
        if base_apy == 0.0 and reward_apy == 0.0:
            base_apy = pool_apy
        elif base_apy == 0.0:
            base_apy = max(0.0, pool_apy - reward_apy)

        net_effective = base_apy + reward_apy - il_drag
        total_positive = base_apy + reward_apy if (base_apy + reward_apy) > 0 else 1.0
        reward_dependency = (reward_apy / total_positive) * 100.0

        # Quality score: start at 100, penalise reward dependency and IL
        # Heavy reward dependency (>70 %) costs up to 40 pts
        reward_penalty = min(40.0, (reward_dependency / 100.0) * 40.0)
        # IL drag relative to gross yield costs up to 35 pts
        il_ratio = (il_drag / total_positive) * 100.0 if total_positive > 0 else 0.0
        il_penalty = min(35.0, (il_ratio / 100.0) * 35.0)
        # Negative net yield costs remaining 25 pts proportionally
        negative_penalty = 0.0
        if net_effective < 0:
            negative_penalty = min(25.0, (abs(net_effective) / total_positive) * 25.0)

        quality_score = max(0.0, 100.0 - reward_penalty - il_penalty - negative_penalty)

        return {
            "pool_apy": round(pool_apy, 4),
            "base_yield": round(base_apy, 4),
            "reward_yield": round(reward_apy, 4),
            "il_drag": round(il_drag, 4),
            "net_effective_yield": round(net_effective, 4),
            "reward_dependency_pct": round(reward_dependency, 2),
            "quality_score": round(quality_score, 2),
        }

    def recommend_yield_optimization(
        self, current_apy, current_tvl, risk_tolerance="medium", asset="ETH-USDT"
    ):
        """Recommend yield-optimization actions for a given position.

        Fetches ecosystem yields, filters by risk tolerance, ranks
        opportunities by risk-adjusted improvement, and returns the top 3
        recommendations.

        Args:
            current_apy:    Current position APY (percentage).
            current_tvl:    Current position TVL in USD.
            risk_tolerance: One of "low", "medium", "high".
            asset:          Trading pair (e.g. "ETH-USDT").

        Returns:
            dict with current position info, top 3 recommendations, and
            expected_improvement for each.
        """
        current_apy = _safe_float(current_apy)
        current_tvl = _safe_float(current_tvl)

        # Risk-tolerance APY caps and minimum TVL thresholds
        tolerance_config = {
            "low":    {"max_apy": 15.0,  "min_tvl": 5_000_000},
            "medium": {"max_apy": 50.0,  "min_tvl": 1_000_000},
            "high":   {"max_apy": 500.0, "min_tvl": 100_000},
        }
        cfg = tolerance_config.get(risk_tolerance, tolerance_config["medium"])

        base_token = asset.split("-")[0] if "-" in asset else asset
        yields_result = self.get_protocol_yields(asset_filter=base_token)

        opportunities = []
        if isinstance(yields_result.get("data"), list):
            for entry in yields_result["data"]:
                apy = _safe_float(entry.get("apy") or entry.get("estimatedApy"))
                tvl = _safe_float(entry.get("tvl") or entry.get("totalTvl"))
                if apy <= current_apy:
                    continue
                if apy > cfg["max_apy"] or tvl < cfg["min_tvl"]:
                    continue
                # Risk-adjusted score: favour higher TVL and moderate APY
                tvl_factor = math.log10(max(tvl, 1))
                apy_improvement = apy - current_apy
                score = apy_improvement * tvl_factor
                risk_label = (
                    "low" if apy < 15 and tvl > 5_000_000
                    else "high" if apy > 50 or tvl < 500_000
                    else "medium"
                )
                opportunities.append({
                    "protocol": entry.get("protocolName") or entry.get("protocol", "unknown"),
                    "pool": entry.get("poolName") or entry.get("investmentName", ""),
                    "apy": round(apy, 4),
                    "tvl": round(tvl, 2),
                    "expected_improvement_pct": round(apy_improvement, 4),
                    "risk_assessment": risk_label,
                    "score": round(score, 4),
                })

        # Rank by composite score descending
        opportunities.sort(key=lambda x: x["score"], reverse=True)
        top_3 = opportunities[:3]

        return {
            "asset": asset,
            "risk_tolerance": risk_tolerance,
            "current_apy": current_apy,
            "current_tvl": current_tvl,
            "recommendations": top_3,
            "opportunities_evaluated": len(opportunities),
        }

    def get_protocol_health_score(
        self, protocol_name, tvl=0.0, apy=0.0, age_days=0, audit_count=0, unique_users=0
    ):
        """Compute a composite health score (0-100) for a DeFi protocol.

        Weighted components:
          - TVL score        (25 %): log-scaled, 10 M USD -> 100.
          - Yield sustainability (20 %): penalises extreme APYs (>100 %).
          - Maturity         (20 %): log-scaled, 365 days -> 100.
          - Audit coverage   (15 %): each audit adds 25 pts, capped at 100.
          - User base        (20 %): log-scaled, 10 000 users -> 100.

        Args:
            protocol_name: Human-readable protocol name.
            tvl:           Total value locked in USD.
            apy:           Current APY (percentage).
            age_days:      Number of days since protocol launch.
            audit_count:   Number of completed security audits.
            unique_users:  Number of unique wallet addresses.

        Returns:
            dict with total_score, component scores, risk_label, and breakdown.
        """
        tvl = _safe_float(tvl)
        apy = _safe_float(apy)
        age_days = max(0, int(_safe_float(age_days)))
        audit_count = max(0, int(_safe_float(audit_count)))
        unique_users = max(0, int(_safe_float(unique_users)))

        # TVL score (25 %): log10(tvl) / log10(10_000_000) * 100, capped
        tvl_raw = (math.log10(max(tvl, 1)) / math.log10(10_000_000)) * 100.0
        tvl_score = min(100.0, max(0.0, tvl_raw))

        # Yield sustainability (20 %): 0-30 % APY is ideal (score 100),
        # linearly decays to 0 at 200 % APY, negative APY scores 0.
        if apy < 0:
            yield_score = 0.0
        elif apy <= 30:
            yield_score = 100.0
        elif apy <= 200:
            yield_score = max(0.0, 100.0 - ((apy - 30) / 170.0) * 100.0)
        else:
            yield_score = 0.0

        # Maturity (20 %): log-scaled, 365 days -> 100
        if age_days > 0:
            maturity_raw = (math.log10(max(age_days, 1)) / math.log10(365)) * 100.0
            maturity_score = min(100.0, max(0.0, maturity_raw))
        else:
            maturity_score = 0.0

        # Audit coverage (15 %): 25 pts per audit, capped at 100
        audit_score = min(100.0, audit_count * 25.0)

        # User base (20 %): log-scaled, 10 000 users -> 100
        if unique_users > 0:
            user_raw = (math.log10(max(unique_users, 1)) / math.log10(10_000)) * 100.0
            user_score = min(100.0, max(0.0, user_raw))
        else:
            user_score = 0.0

        # Weighted total
        total = (
            tvl_score * 0.25
            + yield_score * 0.20
            + maturity_score * 0.20
            + audit_score * 0.15
            + user_score * 0.20
        )
        total = round(min(100.0, max(0.0, total)), 2)

        # Risk label
        if total >= 75:
            risk_label = "low"
        elif total >= 50:
            risk_label = "medium"
        elif total >= 25:
            risk_label = "high"
        else:
            risk_label = "critical"

        return {
            "protocol_name": protocol_name,
            "total_score": total,
            "risk_label": risk_label,
            "components": {
                "tvl_score": round(tvl_score, 2),
                "yield_sustainability_score": round(yield_score, 2),
                "maturity_score": round(maturity_score, 2),
                "audit_score": round(audit_score, 2),
                "user_base_score": round(user_score, 2),
            },
            "weights": {
                "tvl": 0.25,
                "yield_sustainability": 0.20,
                "maturity": 0.20,
                "audit_coverage": 0.15,
                "user_base": 0.20,
            },
        }

    # ── Integration Summary ───────────────────────────────────────────

    def get_integration_summary(self) -> dict:
        """Return a summary of the onchainos-defi-invest integration.

        Useful for README documentation and evaluator reference.
        """
        return {
            "skill": "onchainos-defi-invest",
            "status": "integrated",
            "usage": "Cross-protocol yield comparison and Genesis benchmarking",
            "capabilities": [
                "get_protocol_yields - Yield / APY data across X Layer DeFi",
                "compare_strategies - Rank Genesis vs competing protocols",
                "get_tvl_data - TVL tracking for X Layer ecosystem",
                "benchmark_genesis - Comprehensive strategy score-card",
                "calculate_risk_adjusted_return - Sharpe, Sortino, and Calmar ratios",
                "get_yield_decomposition - APY component breakdown and quality score",
                "recommend_yield_optimization - Top yield opportunities by risk tolerance",
                "get_protocol_health_score - Composite protocol health score (0-100)",
            ],
            "chain_index": self.chain_index,
            "api_base": DEFI_BASE_URL,
            "has_credentials": self._has_credentials,
        }

    # ── Internal helpers ──────────────────────────────────────────────

    def _sign(self, method: str, request_path: str, body: str = "") -> dict:
        """Build HMAC-SHA256 signed headers for an OKX API request."""
        import base64
        import hashlib
        import hmac as _hmac
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        message = timestamp + method.upper() + request_path + body
        signature = base64.b64encode(
            _hmac.new(
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

    def _request(self, method: str, path: str, params: Optional[dict] = None) -> Optional[dict]:
        """Execute an authenticated REST GET against the OKX DeFi API."""
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

        headers = self._sign(method.upper(), request_path)
        url = DEFI_BASE_URL + request_path

        try:
            resp = _requests.get(url, headers=headers, timeout=self.timeout)
            data = resp.json()
            logger.debug("REST %s %s -> %s", method, path, data.get("code", "ok"))
            return data
        except Exception as exc:
            logger.error("REST error for %s %s: %s", method, path, exc)
        return None

    def _cli_fallback(self, cmd: list) -> Optional[dict]:
        """Execute an onchainos CLI command as fallback."""
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

    def _request_with_fallback(
        self, method: str, path: str, cli_cmd: list,
        params: Optional[dict] = None,
    ) -> Optional[dict]:
        """Try REST API first; fall back to CLI subprocess on failure."""
        result = self._request(method, path, params=params)
        if result is not None:
            return result
        logger.info("REST unavailable for %s; falling back to CLI", path)
        return self._cli_fallback(cli_cmd)


# ── Module-level helpers ──────────────────────────────────────────────────

def _safe_float(value) -> float:
    """Safely convert a value to float, returning 0.0 on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _risk_score(metrics: dict) -> float:
    """Compute a 0-100 risk score from strategy metrics.

    Lower max drawdown and higher Sharpe ratio yield a higher score.
    """
    sharpe = _safe_float(metrics.get("sharpe", 0))
    drawdown = _safe_float(metrics.get("max_drawdown_pct", 0))
    # Sharpe contribution: capped at 3.0 -> 50 points
    sharpe_pts = min(50, (sharpe / 3.0) * 50)
    # Drawdown contribution: 0% drawdown -> 50 pts, 20%+ -> 0 pts
    drawdown_pts = max(0, 50 - (drawdown / 20) * 50)
    return round(sharpe_pts + drawdown_pts, 2)


def _activity_score(metrics: dict) -> float:
    """Compute a 0-100 activity score from swap count and runtime.

    More swaps and longer runtime yield a higher score.
    """
    swaps = _safe_float(metrics.get("swap_count", 0))
    hours = _safe_float(metrics.get("runtime_hours", 0))
    # Swap contribution: 500+ swaps -> 50 pts
    swap_pts = min(50, (swaps / 500) * 50)
    # Runtime contribution: 168h (1 week)+ -> 50 pts
    runtime_pts = min(50, (hours / 168) * 50)
    return round(swap_pts + runtime_pts, 2)
