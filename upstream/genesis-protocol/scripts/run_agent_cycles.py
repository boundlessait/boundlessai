#!/usr/bin/env python3
"""Run Genesis Agent cognitive cycles and persist state.
Generates evidence of continuous agent operation.
"""
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

STATE_DIR = Path.home() / ".genesis"
STATE_FILE = STATE_DIR / "agent_state.json"
LOG_FILE = STATE_DIR / "agent.log"

STATE_DIR.mkdir(parents=True, exist_ok=True)

# Setup logging
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
root = logging.getLogger()
root.setLevel(logging.INFO)
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(fmt)
root.addHandler(ch)
fh = logging.FileHandler(str(LOG_FILE), mode="a")
fh.setFormatter(fmt)
root.addHandler(fh)

logger = logging.getLogger("genesis.service")

# Pre-train ML model with historical data from CoinGecko
def pretrain_ml_model(model):
    """Pre-train the statistical model with 30-day historical data."""
    try:
        import urllib.request
        url = "https://api.coingecko.com/api/v3/coins/ethereum/market_chart?vs_currency=usd&days=30"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "GenesisProtocol/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        prices = data.get("prices", [])
        if len(prices) > 10:
            logger.info("Pre-training ML model with %d historical price points from CoinGecko...", len(prices))
            for ts_ms, price in prices:
                model.update_price(price, ts_ms / 1000.0)

            # Also compute historical volatility observations
            for i in range(20, len(prices), 20):
                chunk = [p for _, p in prices[max(0,i-20):i]]
                if len(chunk) >= 2:
                    avg = sum(chunk) / len(chunk)
                    std = (sum((p - avg)**2 for p in chunk) / len(chunk)) ** 0.5
                    vol = (std / avg) * 100 if avg > 0 else 0
                    model.update_volatility(vol, prices[i][0] / 1000.0)

            forecast = model.linear_regression_predict()
            momentum = model.get_momentum_signal()
            vol_f = model.rolling_volatility_forecast()
            bayesian = model.bayesian_regime_update(
                vol_f.get("current_vol", 1.0), momentum.get("momentum_score", 0)
            )

            logger.info("Pre-training complete:")
            logger.info("  Prices loaded: %d", len(prices))
            logger.info("  EMA fast: $%.2f, EMA slow: $%.2f", model._ema_fast, model._ema_slow)
            logger.info("  Momentum: %s (score: %.6f)", momentum["signal"], momentum["momentum_score"])
            logger.info("  LR forecast: %s (R²=%.4f, change=%.4f%%)", forecast["direction"], forecast["r_squared"], forecast["predicted_change_pct"])
            logger.info("  Vol forecast: %.4f%% (%s)", vol_f["forecast_vol"], vol_f["vol_trend"])
            logger.info("  Bayesian regime: %s (conf=%.4f)", bayesian["regime"], bayesian["confidence"])
            return True
    except Exception as e:
        logger.warning("Pre-training failed (non-critical): %s", e)
    return False


def run_cycles():
    from skills.genesis.scripts.genesis_engine import GenesisEngine, StatisticalModel

    logger.info("=" * 60)
    logger.info("  Genesis Protocol - Agent Service")
    logger.info("  Starting cognitive cycles...")
    logger.info("=" * 60)

    engine = GenesisEngine()

    # Pre-train ML model with historical data
    pretrained = pretrain_ml_model(engine._ml_model)

    # Load previous state if exists
    if STATE_FILE.exists():
        try:
            prev = json.loads(STATE_FILE.read_text())
            if "preferences" in prev:
                engine._preferences.update(prev["preferences"])
            if "cycle_count" in prev:
                engine._cycle_count = prev["cycle_count"]
            if "prediction_accuracy" in prev:
                engine._prediction_accuracy = prev["prediction_accuracy"]
            logger.info("Restored previous state: %d cycles, accuracy=%.2f%%",
                       prev.get("cycle_count", 0), prev.get("prediction_accuracy", 0.5) * 100)
        except Exception:
            pass

    results = []
    for i in range(3):
        logger.info("")
        logger.info("─── Cognitive Cycle %d/3 ───", i + 1)
        try:
            result = engine.run_cycle()
            results.append(result)
            logger.info("Cycle %d complete: %d actions, accuracy=%.1f%%",
                       result["cycle"], result["actions_planned"],
                       (result.get("prediction_accuracy", 0.5) or 0.5) * 100)
        except Exception as e:
            logger.error("Cycle %d error: %s", i + 1, e)
            results.append({"cycle": i + 1, "error": str(e)})

        if i < 2:
            time.sleep(2)

    # Save state
    state = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "service_version": "1.0.0",
        "cycle_count": engine._cycle_count,
        "preferences": engine._preferences,
        "prediction_accuracy": engine._prediction_accuracy,
        "predictions_count": len(engine._predictions),
        "last_perception": engine._last_perception,
        "last_analysis": engine._last_analysis,
        "last_evolution": engine._last_evolution,
        "ml_state": {
            "ema_fast": engine._ml_model._ema_fast,
            "ema_slow": engine._ml_model._ema_slow,
            "momentum_score": engine._ml_model._momentum_score,
            "bayesian_prior": engine._ml_model._bayesian_prior,
            "price_history_len": len(engine._ml_model._price_history),
            "vol_history_len": len(engine._ml_model._vol_history),
            "action_outcomes_len": len(engine._ml_model._action_outcomes),
            "pretrained": pretrained,
        },
        "last_3_cycles": results,
        "engine_status": engine.get_status(),
    }
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))
    logger.info("")
    logger.info("State saved to %s", STATE_FILE)
    logger.info("Log saved to %s", LOG_FILE)

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("  Agent Service Summary")
    logger.info("  Total cycles: %d", engine._cycle_count)
    logger.info("  Prediction accuracy: %.1f%%", engine._prediction_accuracy * 100)
    logger.info("  Preferences: %s", engine._preferences)
    logger.info("  ML model: %d prices, %d vol obs, %d outcomes",
               len(engine._ml_model._price_history),
               len(engine._ml_model._vol_history),
               len(engine._ml_model._action_outcomes))
    logger.info("  Bayesian priors: %s", engine._ml_model._bayesian_prior)
    logger.info("=" * 60)


if __name__ == "__main__":
    run_cycles()
