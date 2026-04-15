#!/usr/bin/env python3
"""Genesis Protocol - Backtesting Engine.

Simulates strategy performance on historical candle data from OKX.
Compares all four Genesis strategy presets (calm_accumulator, volatile_defender,
trend_rider, full_defense) on identical market data.

Simulation logic per candle:
    1. Compute rolling EWMA volatility and detect regime
    2. Apply the preset's fee structure based on detected regime
    3. Estimate swap volume from candle data (volume proxy)
    4. Calculate fee revenue from estimated volume
    5. Track impermanent loss (IL) from price movement
    6. Apply rebalancing when IL or range thresholds are hit
    7. Accumulate P&L = fee_revenue - IL - rebalance_costs

Metrics computed:
    - Total Return, Annualized Return
    - Sharpe Ratio, Sortino Ratio
    - Max Drawdown, Recovery Time
    - Win Rate (profitable periods / total)
    - Fee Revenue, IL Loss, Net P&L
    - Regime Distribution

Uses ONLY Python stdlib (urllib, json, math, time).

Usage:
    python3 skills/genesis/scripts/backtester.py
"""

import json
import math
import os
import sys
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.join(_SCRIPT_DIR, "..", "..", "..", "..")
sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Constants - Strategy Presets (mirroring config.py)
# ---------------------------------------------------------------------------
OKX_BASE = "https://www.okx.com"
USER_AGENT = "genesis-protocol-backtester/1.0"

PRESETS = {
    "calm_accumulator": {
        "description": "Low volatility - maximize volume via low fees",
        "modules": ["dynamic_fee", "auto_rebalance"],
        "fee_min_bps": 1.0,       # 0.01% min fee
        "fee_max_bps": 30.0,      # 0.30% max fee
        "fee_sensitivity": 0.8,
        "rebalance_threshold_pct": 2.0,   # rebalance when price moves 2%
        "rebalance_cost_bps": 5.0,        # 0.05% rebalance cost
        "il_multiplier": 1.0,             # standard IL exposure
        "vol_range": (0, 3.0),            # ideal vol range (% daily)
        "mev_protection": False,
    },
    "volatile_defender": {
        "description": "High volatility - protect LP with high fees + MEV guard",
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance"],
        "fee_min_bps": 10.0,
        "fee_max_bps": 150.0,
        "fee_sensitivity": 1.2,
        "rebalance_threshold_pct": 5.0,
        "rebalance_cost_bps": 8.0,
        "il_multiplier": 0.7,     # reduced IL due to wider range
        "vol_range": (5.0, 100.0),
        "mev_protection": True,
    },
    "trend_rider": {
        "description": "Trending market - wider range, TWAP rebalance",
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance"],
        "fee_min_bps": 5.0,
        "fee_max_bps": 100.0,
        "fee_sensitivity": 0.9,
        "rebalance_threshold_pct": 3.5,
        "rebalance_cost_bps": 6.0,
        "il_multiplier": 0.85,
        "vol_range": (2.0, 6.0),
        "mev_protection": True,
    },
    "full_defense": {
        "description": "Maximum protection - all 5 modules active",
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance",
                     "liquidity_shield", "oracle"],
        "fee_min_bps": 15.0,
        "fee_max_bps": 200.0,
        "fee_sensitivity": 1.5,
        "rebalance_threshold_pct": 7.0,
        "rebalance_cost_bps": 10.0,
        "il_multiplier": 0.5,     # heavily shielded
        "vol_range": (8.0, 100.0),
        "mev_protection": True,
    },
}


# ═══════════════════════════════════════════════════════════════════════════
#  BacktestEngine
# ═══════════════════════════════════════════════════════════════════════════

class BacktestEngine:
    """Backtesting engine for Genesis Protocol strategy presets.

    Simulates LP strategy performance using historical candle data.
    Tracks fee revenue, impermanent loss, rebalancing costs, and net P&L.
    """

    def __init__(self, initial_capital=10000.0):
        """Initialize the backtest engine.

        Args:
            initial_capital: Starting capital in quote currency (e.g., USDT).
        """
        self.initial_capital = initial_capital
        self.results = {}

    # -------------------------------------------------------------------
    #  Data Fetching
    # -------------------------------------------------------------------

    def fetch_historical_data(self, pair="ETH-USDT", period="30d", bar="1H"):
        """Fetch historical candle data from the OKX public API.

        Args:
            pair:   Instrument ID (e.g., "ETH-USDT").
            period: Lookback period string, e.g. "30d", "7d".
            bar:    Candle bar size, e.g. "1H", "4H", "1D".

        Returns:
            list of dicts, each with keys: ts, open, high, low, close, vol.
            Sorted oldest-first.
        """
        days = int(period.replace("d", ""))
        # OKX /candles endpoint returns max 300 per request
        # For 30d of 1H data we need ~720 candles = 3 requests
        all_candles = []
        after = ""
        target_count = days * 24 if bar == "1H" else days * 6 if bar == "4H" else days

        for _ in range(10):  # safety limit
            params = {"instId": pair, "bar": bar, "limit": "300"}
            if after:
                params["after"] = after
            url = OKX_BASE + "/api/v5/market/history-candles"
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            full_url = url + "?" + qs
            req = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                if data.get("code") != "0" or not data.get("data"):
                    break
                batch = data["data"]
                for c in batch:
                    all_candles.append({
                        "ts": int(c[0]),
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "vol": float(c[5]),
                    })
                if len(batch) < 300:
                    break
                # OKX returns newest first; 'after' = oldest ts in batch
                after = str(batch[-1][0])
                if len(all_candles) >= target_count:
                    break
                time.sleep(0.2)  # rate limit courtesy
            except Exception as exc:
                print(f"  [WARN] Fetch error: {exc}")
                break

        # Sort oldest first
        all_candles.sort(key=lambda c: c["ts"])
        # Trim to target
        if len(all_candles) > target_count:
            all_candles = all_candles[-target_count:]

        return all_candles

    # -------------------------------------------------------------------
    #  Backtest Simulation
    # -------------------------------------------------------------------

    def run_backtest(self, preset_name, candles):
        """Simulate strategy execution on historical candles.

        For each candle:
            1. Compute rolling EWMA volatility
            2. Detect regime (calm/volatile/trending)
            3. Calculate dynamic fee based on vol and preset sensitivity
            4. Estimate swap volume and fee revenue (scaled to LP capital)
            5. Track impermanent loss using standard x*y=k IL formula
            6. Check rebalance threshold and apply costs
            7. Accumulate P&L

        Fee revenue model:
            We model a single Uniswap V4 pool with realistic TVL. Our LP
            position is $10k in a pool with ~$10M TVL, so our share of fees
            is capital/pool_TVL. Volume flowing through THIS pool is a small
            fraction (~0.3%) of total exchange volume reported by OKX.

        IL model:
            Standard constant-product IL from the last rebalance price:
            IL = 2*sqrt(price_ratio)/(1+price_ratio) - 1
            Applied to current capital * il_multiplier.

        Args:
            preset_name: Key into PRESETS dict.
            candles:     List of candle dicts (oldest first).

        Returns:
            dict with time-series results and period-by-period data.
        """
        preset = PRESETS[preset_name]
        capital = self.initial_capital

        # State variables
        ewma_var = 0.0
        lam = 0.94
        last_rebalance_price = candles[0]["close"] if candles else 0
        cumulative_pnl = 0.0
        peak_capital = capital

        # Pool parameters for realistic fee scaling
        # Assume a mid-tier Uniswap V4 pool with ~$10M TVL
        pool_tvl = 10_000_000.0
        # Fraction of total OKX volume that flows through this specific pool
        # (Most volume is on CEXes; a single DEX pool sees a tiny slice)
        pool_volume_share = 0.02  # ~2% of reported exchange volume

        # Track IL from last rebalance using cumulative price ratio
        il_applied_so_far = 0.0

        # Accumulators
        total_fee_revenue = 0.0
        total_il_loss = 0.0
        total_rebalance_cost = 0.0
        rebalance_count = 0
        periods = []
        regime_counts = {"calm": 0, "volatile": 0, "trending": 0}
        winning_periods = 0
        max_drawdown = 0.0
        max_dd_start = 0
        recovery_time = 0
        in_drawdown = False

        for i, candle in enumerate(candles):
            price = candle["close"]
            prev_price = candles[i - 1]["close"] if i > 0 else price

            # --- Volatility (EWMA) ---
            if i > 0 and prev_price > 0:
                ret = (price - prev_price) / prev_price
                ewma_var = lam * ewma_var + (1 - lam) * ret ** 2
            vol_pct = math.sqrt(ewma_var) * 100 if ewma_var > 0 else 0.0

            # --- Regime Detection ---
            if vol_pct > 5.0:
                regime = "volatile"
            elif vol_pct > 1.5:
                regime = "trending"
            else:
                regime = "calm"
            regime_counts[regime] += 1

            # --- Dynamic Fee Calculation ---
            # Fee scales with volatility, clamped to preset min/max
            raw_fee_bps = preset["fee_min_bps"] + vol_pct * preset["fee_sensitivity"] * 10
            fee_bps = max(preset["fee_min_bps"], min(preset["fee_max_bps"], raw_fee_bps))

            # --- Volume & Fee Revenue (realistic pool model) ---
            # candle["vol"] is in base asset units (ETH) from OKX.
            # Pool volume = exchange volume * pool_volume_share
            # Our fee share = (our capital / pool TVL) * pool_volume * fee_rate
            pool_volume_usd = candle["vol"] * price * pool_volume_share
            our_pool_share = capital / pool_tvl
            fee_revenue = pool_volume_usd * our_pool_share * (fee_bps / 10000.0)

            # --- Impermanent Loss (x*y=k model) ---
            # IL is computed from the price ratio since last rebalance.
            # IL(r) = 2*sqrt(r)/(1+r) - 1  where r = price / entry_price
            # We track the *incremental* IL each period.
            if last_rebalance_price > 0 and last_rebalance_price != price:
                r = price / last_rebalance_price
                sqrt_r = math.sqrt(r)
                # IL as a fraction (always <= 0 for any r != 1)
                il_fraction = 2.0 * sqrt_r / (1.0 + r) - 1.0
                # il_fraction is negative; total IL cost so far from this rebalance
                cumulative_il = abs(il_fraction) * capital * preset["il_multiplier"]
            else:
                cumulative_il = 0.0

            # Incremental IL this period = change in cumulative IL since last period
            il_loss = max(0.0, cumulative_il - il_applied_so_far)
            il_applied_so_far = cumulative_il

            # MEV protection reduces IL by ~20% when active
            if preset["mev_protection"] and regime == "volatile":
                il_loss *= 0.8

            # --- Rebalance Check ---
            rebalance_cost = 0.0
            if last_rebalance_price > 0:
                drift_pct = abs(price - last_rebalance_price) / last_rebalance_price * 100
                if drift_pct >= preset["rebalance_threshold_pct"]:
                    rebalance_cost = capital * (preset["rebalance_cost_bps"] / 10000.0)
                    last_rebalance_price = price
                    rebalance_count += 1
                    # Reset IL tracking after rebalance
                    il_applied_so_far = 0.0

            # --- Period P&L ---
            period_pnl = fee_revenue - il_loss - rebalance_cost
            capital += period_pnl
            cumulative_pnl += period_pnl

            total_fee_revenue += fee_revenue
            total_il_loss += il_loss
            total_rebalance_cost += rebalance_cost

            if period_pnl > 0:
                winning_periods += 1

            # --- Drawdown tracking ---
            if capital > peak_capital:
                peak_capital = capital
                in_drawdown = False
            else:
                dd = (peak_capital - capital) / peak_capital * 100
                if dd > max_drawdown:
                    max_drawdown = dd
                    max_dd_start = i
                if not in_drawdown:
                    in_drawdown = True

            periods.append({
                "ts": candle["ts"],
                "price": price,
                "vol_pct": round(vol_pct, 4),
                "regime": regime,
                "fee_bps": round(fee_bps, 2),
                "fee_revenue": round(fee_revenue, 4),
                "il_loss": round(il_loss, 4),
                "rebalance_cost": round(rebalance_cost, 4),
                "period_pnl": round(period_pnl, 4),
                "cumulative_pnl": round(cumulative_pnl, 4),
                "capital": round(capital, 4),
            })

        # Recovery time: candles from max-DD point until capital recovered
        recovery_time = 0
        if max_dd_start > 0:
            dd_capital = periods[max_dd_start]["capital"] if max_dd_start < len(periods) else capital
            for j in range(max_dd_start + 1, len(periods)):
                recovery_time += 1
                if periods[j]["capital"] >= peak_capital:
                    break

        result = {
            "preset": preset_name,
            "initial_capital": self.initial_capital,
            "final_capital": round(capital, 4),
            "total_periods": len(candles),
            "total_fee_revenue": round(total_fee_revenue, 4),
            "total_il_loss": round(total_il_loss, 4),
            "total_rebalance_cost": round(total_rebalance_cost, 4),
            "rebalance_count": rebalance_count,
            "net_pnl": round(cumulative_pnl, 4),
            "winning_periods": winning_periods,
            "regime_counts": regime_counts,
            "max_drawdown_pct": round(max_drawdown, 4),
            "recovery_time_periods": recovery_time,
            "periods": periods,
        }
        return result

    # -------------------------------------------------------------------
    #  Metrics Calculation
    # -------------------------------------------------------------------

    def calculate_metrics(self, results):
        """Compute comprehensive performance metrics from backtest results.

        Args:
            results: dict returned by run_backtest().

        Returns:
            dict with all computed metrics.
        """
        periods = results["periods"]
        n = len(periods)
        if n == 0:
            return {"error": "no data"}

        # Period returns
        returns = []
        for i, p in enumerate(periods):
            prev_cap = periods[i - 1]["capital"] if i > 0 else self.initial_capital
            if prev_cap > 0:
                returns.append(p["period_pnl"] / prev_cap)
            else:
                returns.append(0.0)

        # Total and annualized return
        total_return_pct = (results["final_capital"] - self.initial_capital) / self.initial_capital * 100
        # Assume 1H candles; 8760 hours per year
        periods_per_year = 8760.0
        if n > 1:
            annualized_return = ((results["final_capital"] / self.initial_capital)
                                 ** (periods_per_year / n) - 1) * 100
        else:
            annualized_return = 0.0

        # Mean and std of returns
        mean_ret = sum(returns) / n if n > 0 else 0
        var_ret = sum((r - mean_ret) ** 2 for r in returns) / n if n > 0 else 0
        std_ret = math.sqrt(var_ret) if var_ret > 0 else 0

        # Sharpe Ratio (annualized, risk-free rate = 0)
        sharpe = (mean_ret / std_ret * math.sqrt(periods_per_year)) if std_ret > 0 else 0

        # Sortino Ratio (downside deviation only)
        downside = [r for r in returns if r < 0]
        if downside:
            downside_var = sum(r ** 2 for r in downside) / len(downside)
            downside_std = math.sqrt(downside_var)
            sortino = (mean_ret / downside_std * math.sqrt(periods_per_year)) if downside_std > 0 else 0
        else:
            sortino = float("inf") if mean_ret > 0 else 0

        # Win rate
        win_rate = (results["winning_periods"] / n * 100) if n > 0 else 0

        # Regime distribution
        total_regime = sum(results["regime_counts"].values())
        regime_dist = {}
        if total_regime > 0:
            for regime, count in results["regime_counts"].items():
                regime_dist[regime] = round(count / total_regime * 100, 1)

        # Fee APY: annualize the fee revenue rate over the backtest period
        fee_return_pct = (results["total_fee_revenue"] / self.initial_capital) if self.initial_capital > 0 else 0
        if n > 1:
            fee_apy = ((1 + fee_return_pct) ** (periods_per_year / n) - 1) * 100
        else:
            fee_apy = 0.0

        metrics = {
            "preset": results["preset"],
            "total_return_pct": round(total_return_pct, 4),
            "annualized_return_pct": round(annualized_return, 4),
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4) if sortino != float("inf") else "inf",
            "max_drawdown_pct": results["max_drawdown_pct"],
            "recovery_time_periods": results["recovery_time_periods"],
            "win_rate_pct": round(win_rate, 2),
            "total_fee_revenue": results["total_fee_revenue"],
            "fee_apy_pct": round(fee_apy, 2),
            "total_il_loss": results["total_il_loss"],
            "total_rebalance_cost": results["total_rebalance_cost"],
            "rebalance_count": results["rebalance_count"],
            "net_pnl": results["net_pnl"],
            "final_capital": results["final_capital"],
            "total_periods": n,
            "regime_distribution": regime_dist,
        }
        return metrics

    # -------------------------------------------------------------------
    #  Preset Comparison
    # -------------------------------------------------------------------

    def compare_presets(self, candles):
        """Run backtests for all presets on the same candle data.

        Args:
            candles: List of candle dicts.

        Returns:
            dict mapping preset_name -> metrics dict.
        """
        comparison = {}
        for preset_name in PRESETS:
            bt_result = self.run_backtest(preset_name, candles)
            metrics = self.calculate_metrics(bt_result)
            comparison[preset_name] = metrics
            self.results[preset_name] = bt_result
        return comparison

    # -------------------------------------------------------------------
    #  Report Generation
    # -------------------------------------------------------------------

    def generate_report(self, comparison):
        """Format and print a comparison report of all preset backtests.

        Args:
            comparison: dict from compare_presets().
        """
        print()
        print("=" * 90)
        print("  GENESIS PROTOCOL - BACKTEST COMPARISON REPORT")
        print("=" * 90)
        print()

        # Summary table
        header = (f"  {'Preset':<22s} {'Return':>8s} {'Annual':>8s} {'Sharpe':>8s} "
                  f"{'Sortino':>8s} {'MaxDD':>8s} {'WinRate':>8s} {'Net P&L':>10s}")
        print(header)
        print("  " + "-" * 86)

        ranked = sorted(comparison.items(),
                        key=lambda x: x[1].get("total_return_pct", 0),
                        reverse=True)

        for name, m in ranked:
            sortino_str = f"{m['sortino_ratio']:>8.2f}" if m["sortino_ratio"] != "inf" else "     inf"
            print(f"  {name:<22s} {m['total_return_pct']:>7.2f}% {m['annualized_return_pct']:>7.1f}% "
                  f"{m['sharpe_ratio']:>8.2f} {sortino_str} "
                  f"{m['max_drawdown_pct']:>7.2f}% {m['win_rate_pct']:>7.1f}% "
                  f"${m['net_pnl']:>9.2f}")

        # Detailed breakdown
        print()
        print("  " + "-" * 86)
        print()
        print("  DETAILED BREAKDOWN")
        print("  " + "-" * 86)
        for name, m in ranked:
            print(f"\n  {name}")
            print(f"    {PRESETS[name]['description']}")
            print(f"    Modules:           {', '.join(PRESETS[name]['modules'])}")
            print(f"    Fee Revenue:       ${m['total_fee_revenue']:,.2f} (Fee APY: {m['fee_apy_pct']:.1f}%)")
            print(f"    IL Loss:           ${m['total_il_loss']:,.2f}")
            print(f"    Rebalance Cost:    ${m['total_rebalance_cost']:,.2f} ({m['rebalance_count']} rebalances)")
            print(f"    Net P&L:           ${m['net_pnl']:,.2f}")
            print(f"    Final Capital:     ${m['final_capital']:,.2f} (from ${self.initial_capital:,.2f})")
            rd = m.get("regime_distribution", {})
            if rd:
                dist_str = ", ".join(f"{k}={v}%" for k, v in rd.items())
                print(f"    Regime Dist:       {dist_str}")

        # Winner
        print()
        print("  " + "=" * 86)
        best_name = ranked[0][0] if ranked else "N/A"
        best_ret = ranked[0][1]["total_return_pct"] if ranked else 0
        print(f"  WINNER: {best_name} ({best_ret:+.2f}% total return)")
        print("  " + "=" * 86)
        print()


# ═══════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """Execute backtest on ETH-USDT 30-day 1H data, compare all presets."""
    print()
    print("=" * 90)
    print("  Genesis Protocol - Backtesting Engine")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 90)
    print()

    engine = BacktestEngine(initial_capital=10000.0)

    # Fetch historical data
    print("  Fetching ETH-USDT 30-day 1H candles from OKX...")
    candles = engine.fetch_historical_data(pair="ETH-USDT", period="30d", bar="1H")
    print(f"  Fetched {len(candles)} candles")

    if not candles:
        print("  ERROR: No candle data available. Cannot run backtest.")
        return 1

    # Show data summary
    first_price = candles[0]["close"]
    last_price = candles[-1]["close"]
    price_chg = (last_price - first_price) / first_price * 100
    prices = [c["close"] for c in candles]
    high = max(prices)
    low = min(prices)
    print(f"  Period:  {candles[0]['ts']} -> {candles[-1]['ts']}")
    print(f"  Price:   ${first_price:,.2f} -> ${last_price:,.2f} ({price_chg:+.2f}%)")
    print(f"  Range:   ${low:,.2f} - ${high:,.2f}")
    print()

    # Compare all presets
    print("  Running backtests for all 4 presets...")
    print()
    comparison = engine.compare_presets(candles)

    # Generate and print report
    engine.generate_report(comparison)

    return 0


if __name__ == "__main__":
    sys.exit(main())
