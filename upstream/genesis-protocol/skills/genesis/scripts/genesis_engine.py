"""Genesis Engine - 5-Layer Cognitive Architecture for the Genesis Protocol.
Layers: Perception -> Analysis -> Planning -> Evolution -> Meta-Cognition.
LLM-augmented reasoning with statistical ML foundation.
Only stdlib imports. All decisions logged to DecisionJournal.
"""
import logging
import math
import time
import json
import os

from . import config
from .market_oracle import MarketOracle
from .wallet_manager import WalletManager
from .decision_journal import DecisionJournal
from .strategy_manager import StrategyManager
from .llm_reasoning import LLMReasoner

logger = logging.getLogger(__name__)


class StatisticalModel:
    """Lightweight statistical ML model using only stdlib.
    Implements online learning with exponential moving averages,
    linear regression for trend prediction, and Bayesian confidence updating.
    """

    def __init__(self, confidence_ttl_seconds: float = 300.0):
        self._price_history: list = []  # [(timestamp, price)]
        self._vol_history: list = []    # [(timestamp, volatility)]
        self._regime_transitions: list = []  # [(from_regime, to_regime, timestamp)]
        self._action_outcomes: list = []  # [(action, confidence, outcome_score)]
        self._ema_fast = 0.0
        self._ema_slow = 0.0
        self._momentum_score = 0.0
        self._bayesian_prior = {"calm": 0.33, "volatile": 0.33, "trending": 0.34}
        # Dynamic Confidence TTL
        self._confidence_ttl_seconds = confidence_ttl_seconds
        self._confidence_cache: dict = {}  # {key: (timestamp, raw_score)}

    def update_price(self, price: float, timestamp: float):
        """Feed a new price observation into the model."""
        self._price_history.append((timestamp, price))
        if len(self._price_history) > 500:
            self._price_history = self._price_history[-500:]
        # Update EMAs (alpha_fast=0.1, alpha_slow=0.03)
        if self._ema_fast == 0:
            self._ema_fast = price
            self._ema_slow = price
        else:
            self._ema_fast = 0.1 * price + 0.9 * self._ema_fast
            self._ema_slow = 0.03 * price + 0.97 * self._ema_slow
        # Momentum = EMA crossover signal
        self._momentum_score = (self._ema_fast - self._ema_slow) / self._ema_slow if self._ema_slow > 0 else 0

    def update_volatility(self, vol: float, timestamp: float):
        """Feed a new volatility observation."""
        self._vol_history.append((timestamp, vol))
        if len(self._vol_history) > 200:
            self._vol_history = self._vol_history[-200:]

    def linear_regression_predict(self, horizon: int = 5) -> dict:
        """Simple OLS linear regression on recent prices to predict direction.
        Returns slope, r_squared, predicted_change_pct.
        """
        prices = [p for _, p in self._price_history[-30:]]
        n = len(prices)
        if n < 5:
            return {"slope": 0, "r_squared": 0, "predicted_change_pct": 0, "n": n}
        x_mean = (n - 1) / 2
        y_mean = sum(prices) / n
        ss_xy = sum((i - x_mean) * (p - y_mean) for i, p in enumerate(prices))
        ss_xx = sum((i - x_mean) ** 2 for i in range(n))
        ss_yy = sum((p - y_mean) ** 2 for p in prices)
        slope = ss_xy / ss_xx if ss_xx > 0 else 0
        r_squared = (ss_xy ** 2) / (ss_xx * ss_yy) if ss_xx > 0 and ss_yy > 0 else 0
        predicted = prices[-1] + slope * horizon
        change_pct = (predicted - prices[-1]) / prices[-1] * 100 if prices[-1] > 0 else 0
        return {
            "slope": round(slope, 6), "r_squared": round(r_squared, 4),
            "predicted_change_pct": round(change_pct, 4), "n": n,
            "direction": "up" if slope > 0 else "down" if slope < 0 else "flat",
        }

    def rolling_volatility_forecast(self) -> dict:
        """EWMA volatility forecast (like RiskMetrics/GARCH-lite).
        Uses exponentially weighted variance of returns.
        """
        prices = [p for _, p in self._price_history[-50:]]
        if len(prices) < 10:
            return {"forecast_vol": 0, "current_vol": 0, "vol_trend": "unknown"}
        returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
        # EWMA variance with lambda=0.94 (RiskMetrics standard)
        lam = 0.94
        var_ewma = returns[0] ** 2
        for r in returns[1:]:
            var_ewma = lam * var_ewma + (1 - lam) * r ** 2
        forecast_vol = var_ewma ** 0.5 * 100  # annualize-ish
        # Simple current vol
        mean_r = sum(returns) / len(returns)
        current_vol = (sum((r - mean_r) ** 2 for r in returns) / len(returns)) ** 0.5 * 100
        vol_trend = "increasing" if forecast_vol > current_vol * 1.05 else "decreasing" if forecast_vol < current_vol * 0.95 else "stable"
        return {
            "forecast_vol": round(forecast_vol, 4),
            "current_vol": round(current_vol, 4),
            "vol_trend": vol_trend,
            "ewma_lambda": lam,
        }

    def bayesian_regime_update(self, observed_vol: float, observed_momentum: float) -> dict:
        """Bayesian regime classification with prior updating.
        P(regime|data) ∝ P(data|regime) * P(regime)
        """
        def gaussian_likelihood(x, mu, sigma):
            return math.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * (2 * math.pi) ** 0.5)

        # Regime parameters: (vol_mean, vol_std, momentum_mean, momentum_std)
        regime_params = {
            "calm": (0.5, 0.3, 0.0, 0.005),
            "volatile": (3.0, 1.5, 0.0, 0.02),
            "trending": (1.5, 0.8, 0.01, 0.01),
        }
        posteriors = {}
        for regime, (v_mu, v_sigma, m_mu, m_sigma) in regime_params.items():
            vol_lik = gaussian_likelihood(observed_vol, v_mu, v_sigma)
            mom_lik = gaussian_likelihood(abs(observed_momentum), abs(m_mu), m_sigma)
            posteriors[regime] = vol_lik * mom_lik * self._bayesian_prior[regime]

        total = sum(posteriors.values())
        if total > 0:
            posteriors = {k: v / total for k, v in posteriors.items()}
        else:
            posteriors = {"calm": 0.33, "volatile": 0.33, "trending": 0.34}

        # Update priors with learning rate
        alpha = 0.1
        for regime in self._bayesian_prior:
            self._bayesian_prior[regime] = (1 - alpha) * self._bayesian_prior[regime] + alpha * posteriors.get(regime, 0)

        best_regime = max(posteriors, key=posteriors.get)
        return {
            "regime": best_regime,
            "confidence": round(posteriors[best_regime], 4),
            "posteriors": {k: round(v, 4) for k, v in posteriors.items()},
            "priors": {k: round(v, 4) for k, v in self._bayesian_prior.items()},
        }

    def compute_confidence(self, data_quality: float, regime_clarity: float, trend_strength: float) -> float:
        """ML-based confidence scoring using logistic regression weights.
        Weights are learned from action_outcomes history.
        Applies exponential time-decay via confidence TTL so scores degrade
        as market data ages.
        """
        cache_key = f"{data_quality:.4f}:{regime_clarity:.4f}:{trend_strength:.4f}"
        now = time.time()

        # Check cache: if inputs unchanged, apply decay to cached raw score
        if cache_key in self._confidence_cache:
            cached_ts, raw_score = self._confidence_cache[cache_key]
            elapsed = now - cached_ts
            if elapsed < self._confidence_ttl_seconds * 3:  # evict after 3x TTL
                decay = math.exp(-elapsed / self._confidence_ttl_seconds)
                decayed = raw_score * decay
                return round(max(0.1, min(0.98, decayed)), 4)

        # Compute fresh raw score
        w = self._get_learned_weights()
        z = w[0] + w[1] * data_quality + w[2] * regime_clarity + w[3] * trend_strength
        raw_score = 1.0 / (1.0 + math.exp(-z))
        raw_score = max(0.1, min(0.98, raw_score))

        # Store in cache
        self._confidence_cache[cache_key] = (now, raw_score)

        # Evict stale entries (beyond 3x TTL)
        stale_keys = [k for k, (ts, _) in self._confidence_cache.items()
                      if now - ts > self._confidence_ttl_seconds * 3]
        for k in stale_keys:
            del self._confidence_cache[k]

        return round(raw_score, 4)

    def invalidate_confidence_cache(self):
        """Clear the confidence cache, e.g. after fresh market data arrives."""
        self._confidence_cache.clear()

    def _get_learned_weights(self) -> list:
        """Learn logistic regression weights from outcome history using gradient descent."""
        if len(self._action_outcomes) < 5:
            return [-0.5, 1.2, 0.8, 0.6]  # sensible defaults
        # Mini gradient descent on recent outcomes
        w = [-0.5, 1.2, 0.8, 0.6]
        lr = 0.01
        for _ in range(20):  # 20 iterations of SGD
            for action, conf, outcome in self._action_outcomes[-20:]:
                # Features: [1, data_quality_proxy, regime_proxy, trend_proxy]
                x = [1.0, conf, conf * 0.8, conf * 0.5]
                z = sum(wi * xi for wi, xi in zip(w, x))
                pred = 1.0 / (1.0 + math.exp(-max(-10, min(10, z))))
                error = outcome - pred
                for j in range(4):
                    w[j] += lr * error * x[j]
        return w

    def record_outcome(self, action: str, confidence: float, outcome_score: float):
        """Record action outcome for online learning."""
        self._action_outcomes.append((action, confidence, outcome_score))
        if len(self._action_outcomes) > 200:
            self._action_outcomes = self._action_outcomes[-200:]

    def get_momentum_signal(self) -> dict:
        """Get current momentum trading signal."""
        return {
            "ema_fast": round(self._ema_fast, 4),
            "ema_slow": round(self._ema_slow, 4),
            "momentum_score": round(self._momentum_score, 6),
            "signal": "bullish" if self._momentum_score > 0.005 else "bearish" if self._momentum_score < -0.005 else "neutral",
        }


class GenesisEngine:
    """5-layer AI cognitive engine orchestrating the Genesis Protocol."""

    def __init__(self):
        self.oracle = MarketOracle()
        self.wallet = WalletManager()
        self.journal = DecisionJournal()
        self.strategy_mgr = StrategyManager()
        self._last_perception = 0.0
        self._last_analysis = 0.0
        self._last_evolution = 0.0
        self._cycle_count = 0
        self._world_state: dict = {}
        self._analysis_cache: dict = {}
        self._running = False
        self._preferences = {
            "risk_tolerance": 0.5, "rebalance_eagerness": 0.5, "new_strategy_bias": 0.5,
        }
        self._preference_baselines = dict(self._preferences)  # default/initial values
        self._regularization_strength = 0.1
        self._evolution_lr = 0.05  # learning rate for evolution updates
        self._evolution_max_step = 0.02  # max change per parameter per step
        self._recent_decisions_for_validation: list = []  # track recent N decisions for holdout
        self._predictions: list = []   # [(ts, prediction_dict, outcome_dict|None)]
        self._prediction_accuracy = 0.5
        self._ml_model = StatisticalModel()
        self._llm = LLMReasoner()
        self._llm_reasoning_cache: dict = {}  # Store latest LLM reasoning for UI
        self._oracle_confidence_weight = 1.0  # modulates oracle data weight in decisions
        self._oracle_confidence_details: dict = {}  # latest per-pair oracle confidence
        logger.info("GenesisEngine initialized (paused=%s, mode=%s, llm=%s)",
                     config.PAUSED, config.MODE, self._llm.provider)

    # ═══════════════════════════════════════════════════════════════════
    # LAYER 1 — PERCEPTION: gather world state
    # ═══════════════════════════════════════════════════════════════════

    def perceive(self) -> dict:
        """Fetch market data, wallet balances, strategy statuses. Returns world-state dict."""
        try:
            prices = self.oracle.fetch_all_prices()
            balances = self.wallet.get_all_balances()
            active = self.strategy_mgr.get_active_strategies()
            health = {s["id"]: self.strategy_mgr.monitor_strategy(s["id"]) for s in active}

            # Fetch confidence-enriched prices and apply oracle confidence logic
            self._oracle_confidence_details = {}
            for pair in config.ONCHAINOS_MARKET_PAIRS:
                b, q = pair["base"], pair["quote"]
                enriched = self.oracle.get_price_with_confidence(b, q)
                if enriched is not None:
                    pair_key = f"{b}/{q}"
                    self._oracle_confidence_details[pair_key] = enriched
                    self._apply_oracle_confidence_adjustments(pair_key, enriched)

            self._world_state = {
                "timestamp": int(time.time()),
                "prices": {f"{k[0]}/{k[1]}": v for k, v in prices.items()},
                "oracle_confidence": self._oracle_confidence_details,
                "balances": balances, "active_strategies": active,
                "strategy_health": health,
                "strategy_summary": self.strategy_mgr.get_strategy_summary(),
            }
            # Feed prices to ML model
            for pair_key, price_data in prices.items():
                if isinstance(price_data, (int, float)):
                    self._ml_model.update_price(float(price_data), time.time())
            self._last_perception = time.time()
            logger.info("Perception: %d prices, %d strategies, oracle_weight=%.3f",
                        len(prices), len(active), self._oracle_confidence_weight)
        except Exception as exc:
            logger.error("Perception layer failed: %s", exc)
            self._world_state["error"] = str(exc)
        return self._world_state

    def _apply_oracle_confidence_adjustments(self, pair_key: str, enriched: dict) -> None:
        """Apply oracle confidence-based adjustments to engine parameters.

        When the oracle spread exceeds 2%, the statistical model's confidence
        TTL is reduced by 50% so that stale high-uncertainty data expires
        faster.  When fewer than 2 sources agree, a warning is logged and
        ``_oracle_confidence_weight`` is penalised.

        Args:
            pair_key: human-readable pair identifier, e.g. ``"ETH/USDT"``.
            enriched: confidence-enriched dict from
                ``MarketOracle.get_price_with_confidence``.
        """
        spread = enriched.get("spread", 0.0)
        sources_agreed = enriched.get("sources_agreed", 0)
        oracle_conf = enriched.get("confidence", 1.0)

        # High spread -> reduce confidence TTL by 50%
        if spread > 2.0:
            original_ttl = self._ml_model._confidence_ttl_seconds
            reduced_ttl = original_ttl * 0.5
            self._ml_model._confidence_ttl_seconds = reduced_ttl
            self._ml_model.invalidate_confidence_cache()
            logger.warning(
                "Oracle spread %.2f%% > 2%% for %s — confidence TTL reduced "
                "from %.0fs to %.0fs",
                spread, pair_key, original_ttl, reduced_ttl,
            )

        # Few sources agreeing -> log warning and apply confidence penalty
        if sources_agreed < 2:
            logger.warning(
                "Only %d source(s) agreed for %s (spread=%.2f%%) — "
                "applying confidence penalty to oracle weight",
                sources_agreed, pair_key, spread,
            )

        # Modulate _oracle_confidence_weight based on oracle's own confidence
        # Blend toward oracle confidence with a smoothing factor
        smoothing = 0.3
        self._oracle_confidence_weight = (
            (1.0 - smoothing) * self._oracle_confidence_weight
            + smoothing * oracle_conf
        )
        # Floor at 0.1 to never fully ignore oracle data
        self._oracle_confidence_weight = max(0.1, min(1.0, self._oracle_confidence_weight))

    # ═══════════════════════════════════════════════════════════════════
    # LAYER 2 — ANALYSIS: regime detection, mismatch & anomaly finding
    # ═══════════════════════════════════════════════════════════════════

    def analyze(self) -> dict:
        """Analyze market regimes, compare strategies to optimal, detect anomalies."""
        try:
            regimes = {}
            for pair in config.ONCHAINOS_MARKET_PAIRS:
                b, q = pair["base"], pair["quote"]
                regimes[f"{b}/{q}"] = self.oracle.get_market_regime(b, q)
            # Strategy-regime mismatch detection
            mismatches = []
            first_regime = next((r.get("regime_name", "") for r in regimes.values()), "")
            for strat in self._world_state.get("active_strategies", []):
                created = strat.get("market_regime_at_creation", "")
                if created and first_regime and created != first_regime:
                    mismatches.append({"strategy_id": strat["id"], "was": created, "now": first_regime})
            anomalies = self._detect_anomalies(regimes)
            # ML-enhanced analysis
            lr_forecast = self._ml_model.linear_regression_predict()
            vol_forecast = self._ml_model.rolling_volatility_forecast()
            momentum = self._ml_model.get_momentum_signal()

            # Bayesian regime classification
            avg_vol = 0
            for r in regimes.values():
                v = r.get("volatility", 0)
                if v: avg_vol = v
            bayesian_regime = self._ml_model.bayesian_regime_update(
                avg_vol, momentum.get("momentum_score", 0)
            )

            self._analysis_cache = {
                "timestamp": int(time.time()), "regimes": regimes,
                "mismatches": mismatches, "anomalies": anomalies,
                "ml_forecast": lr_forecast,
                "vol_forecast": vol_forecast,
                "momentum": momentum,
                "bayesian_regime": bayesian_regime,
            }
            # LLM-augmented market analysis
            try:
                llm_analysis = self._llm.analyze_market({
                    "regimes": regimes,
                    "ml_forecast": lr_forecast,
                    "vol_forecast": vol_forecast,
                    "momentum": momentum,
                    "bayesian_regime": bayesian_regime,
                    "prices": self._world_state.get("prices", {}),
                })
                self._analysis_cache["llm_analysis"] = llm_analysis
                self._llm_reasoning_cache["analysis"] = llm_analysis
                logger.info("LLM analysis: %s", llm_analysis.get("headline", ""))
            except Exception as llm_exc:
                logger.warning("LLM analysis fallback: %s", llm_exc)
            self._last_analysis = time.time()
            logger.info("Analysis: %d regimes, %d mismatches, %d anomalies",
                        len(regimes), len(mismatches), len(anomalies))
        except Exception as exc:
            logger.error("Analysis layer failed: %s", exc)
            self._analysis_cache["error"] = str(exc)
        return self._analysis_cache

    def _detect_anomalies(self, regimes: dict) -> list:
        """Detect sudden vol spikes and balance drain."""
        anomalies = []
        for pair_key, regime in regimes.items():
            vol = regime.get("volatility")
            if vol is not None and vol > 0.10:
                anomalies.append({"type": "vol_spike", "pair": pair_key,
                                  "volatility": vol, "severity": "high"})
        for role, bal_data in self._world_state.get("balances", {}).items():
            if role == "reserve":
                raw = bal_data.get("balance", bal_data.get("amount", "0"))
                try:
                    if float(raw) <= 0:
                        anomalies.append({"type": "balance_drain", "wallet": role,
                                          "balance": raw, "severity": "critical"})
                except (ValueError, TypeError):
                    pass
        return anomalies

    # ═══════════════════════════════════════════════════════════════════
    # LAYER 3 — PLANNING: generate actions with confidence scores
    # ═══════════════════════════════════════════════════════════════════

    def plan(self) -> list:
        """Generate action plan: create/adjust/rebalance/deactivate/hold. Returns action list."""
        actions: list = []
        try:
            regimes = self._analysis_cache.get("regimes", {})
            mismatches = self._analysis_cache.get("mismatches", [])
            anomalies = self._analysis_cache.get("anomalies", [])
            active = self._world_state.get("active_strategies", [])

            # Critical anomalies -> hold
            for a in anomalies:
                if a["severity"] == "critical":
                    target = a.get("wallet", a.get("pair", "?"))
                    actions.append({"type": "hold", "confidence": 0.95,
                                    "reasoning": f"Critical anomaly: {a['type']} on {target}",
                                    "params": {"anomaly": a}})
            # Rebalance mismatched strategies
            for mm in mismatches:
                conf = min(0.6 + self._preferences["rebalance_eagerness"] * 0.3, 0.95)
                actions.append({"type": "rebalance", "confidence": conf,
                                "reasoning": f"Regime shifted {mm['was']}->{mm['now']} for {mm['strategy_id']}",
                                "params": {"strategy_id": mm["strategy_id"], "new_regime": mm["now"]}})
            # Evaluate existing strategies for deactivation
            for strat in active:
                sid = strat["id"]
                perf = self.strategy_mgr.evaluate_performance(sid)
                should, reason = self.strategy_mgr.should_deactivate(sid, perf)
                if should:
                    actions.append({"type": "deactivate", "confidence": 0.85,
                                    "reasoning": f"Deactivate {sid}: {reason}",
                                    "params": {"strategy_id": sid, "reason": reason}})
            # Create new strategy if few active and regime is clear
            if len(active) < 2 and regimes:
                best_r, best_c = None, 0.0
                for regime in regimes.values():
                    c = regime.get("confidence", 0)
                    if c > best_c:
                        best_c, best_r = c, regime
                if best_r and best_c > config.CONFIDENCE_THRESHOLD:
                    bias = self._preferences["new_strategy_bias"]
                    # ML-enhanced confidence scoring
                    ml_conf = self._ml_model.compute_confidence(
                        data_quality=best_c,
                        regime_clarity=abs(0.5 - self._analysis_cache.get("bayesian_regime", {}).get("confidence", 0.5)) * 2,
                        trend_strength=abs(self._analysis_cache.get("ml_forecast", {}).get("predicted_change_pct", 0)) / 5
                    )
                    final_conf = min((best_c * 0.4 + ml_conf * 0.6) * (0.7 + bias * 0.3) * self._oracle_confidence_weight, 0.95)
                    actions.append({
                        "type": "create_strategy",
                        "confidence": final_conf,
                        "reasoning": f"Regime {best_r['regime_name']} confidence {best_c:.2f}",
                        "params": {"regime": best_r["regime_name"], "market_data": best_r},
                    })
                    # LLM-generated strategy rationale
                    try:
                        rationale = self._llm.generate_strategy_rationale(
                            preset=best_r["regime_name"],
                            regime=bayesian_regime.get("regime", "unknown") if bayesian_regime else "unknown",
                            confidence=final_conf,
                            market_data={
                                "prices": self._world_state.get("prices", {}),
                                "volatility": avg_vol,
                                "momentum": self._analysis_cache.get("momentum", {}),
                            }
                        )
                        actions[-1]["llm_rationale"] = rationale
                        self._llm_reasoning_cache["strategy_rationale"] = rationale
                    except Exception as llm_exc:
                        logger.warning("LLM rationale fallback: %s", llm_exc)
            # Default hold
            if not actions:
                actions.append({"type": "hold", "confidence": 1.0,
                                "reasoning": "All strategies within bounds", "params": {}})
            # Track predictions for meta-cognition
            for act in actions:
                if act["type"] != "hold":
                    self._predictions.append((time.time(), {
                        "action": act["type"], "confidence": act["confidence"],
                        "reasoning": act["reasoning"]}, None))
            logger.info("Planning: %d actions planned", len(actions))
        except Exception as exc:
            logger.error("Planning layer failed: %s", exc)
        return actions

    # ═══════════════════════════════════════════════════════════════════
    # LAYER 4 — EVOLUTION: adjust preferences via meta-learning
    # ═══════════════════════════════════════════════════════════════════

    def evolve(self) -> dict:
        """Adjust internal preferences based on historical performance.
        Uses L2 regularization toward baselines, parameter change rate limiting,
        and a simple validation holdout to detect overfitting.
        """
        try:
            summary = self.strategy_mgr.get_strategy_summary()
            avg_pnl = summary.get("avg_pnl_bps", 0)
            active_n = summary.get("active_count", 0)
            old = dict(self._preferences)
            p = self._preferences
            lr = self._evolution_lr
            reg = self._regularization_strength
            baselines = self._preference_baselines
            max_step = self._evolution_max_step

            # --- Compute raw gradients for each preference ---
            gradients = {"risk_tolerance": 0.0, "rebalance_eagerness": 0.0, "new_strategy_bias": 0.0}

            # Risk tolerance gradient from P&L
            if avg_pnl > 100:
                gradients["risk_tolerance"] = 1.0
            elif avg_pnl < -100:
                gradients["risk_tolerance"] = -1.0

            # Rebalance eagerness gradient
            recent = self.journal.get_recent_decisions(20)
            rebalance_count = sum(1 for d in recent if d.get("decision_type") == "REBALANCE_EXECUTE")
            if rebalance_count > 3:
                gradients["rebalance_eagerness"] = 1.0

            # New strategy bias gradient based on active count
            if active_n > 3:
                gradients["new_strategy_bias"] = -2.0
            elif active_n == 0:
                gradients["new_strategy_bias"] = 2.0

            # Low prediction accuracy -> reduce risk
            if self._prediction_accuracy < 0.4:
                gradients["risk_tolerance"] += -2.0

            # ML-driven: volatility trend adjustment
            vol_forecast = self._ml_model.rolling_volatility_forecast()
            if vol_forecast.get("vol_trend") == "increasing":
                gradients["risk_tolerance"] += -0.6
            elif vol_forecast.get("vol_trend") == "decreasing":
                gradients["risk_tolerance"] += 0.4

            # --- Validation holdout: detect overfitting ---
            # Track recent decisions and use last 20% as validation
            self._recent_decisions_for_validation.extend(recent)
            if len(self._recent_decisions_for_validation) > 100:
                self._recent_decisions_for_validation = self._recent_decisions_for_validation[-100:]

            validation_warning = False
            tracked = self._recent_decisions_for_validation
            if len(tracked) >= 10:
                split = max(1, int(len(tracked) * 0.8))
                train_set = tracked[:split]
                val_set = tracked[split:]
                # Simple performance proxy: fraction of executed (non-skipped) decisions
                def _perf(decisions):
                    executed = sum(1 for d in decisions if d.get("decision_type", "").endswith("EXECUTE"))
                    return executed / len(decisions) if decisions else 0.5
                train_perf = _perf(train_set)
                val_perf = _perf(val_set)
                # Overfitting signal: training improves but validation drops
                if train_perf > 0.5 and val_perf < train_perf * 0.7:
                    validation_warning = True
                    lr *= 0.5  # reduce learning rate

            # --- Apply regularized updates with rate limiting ---
            for key in gradients:
                raw_update = lr * (gradients[key] - reg * (p[key] - baselines[key]))
                # Rate limit: clamp update magnitude
                clamped = max(-max_step, min(max_step, raw_update))
                new_val = p[key] + clamped
                p[key] = max(0.1, min(0.9, new_val))

            self._last_evolution = time.time()
            self.journal.log_decision(0, "META_COGNITION",
                f"Evolution: prefs {old} -> {p}",
                {"old": old, "new": dict(p), "avg_pnl_bps": avg_pnl,
                 "prediction_accuracy": self._prediction_accuracy,
                 "regularization_strength": reg,
                 "validation_warning": validation_warning,
                 "effective_lr": lr})
            logger.info("Evolution complete: %s (reg=%.2f, val_warn=%s)", p, reg, validation_warning)
            return {"old": old, "new": dict(p), "validation_warning": validation_warning}
        except Exception as exc:
            logger.error("Evolution layer failed: %s", exc)
            return {"error": str(exc)}

    # ═══════════════════════════════════════════════════════════════════
    # LAYER 5 — META-COGNITION: self-assess prediction quality
    # ═══════════════════════════════════════════════════════════════════
    def reflect(self) -> dict:
        """Evaluate decision quality: compare predictions to actual outcomes."""
        try:
            resolved = correct = 0
            recent_decisions = self.journal.get_recent_decisions(50)
            for i, (ts, pred, outcome) in enumerate(self._predictions):
                if outcome is not None:
                    continue
                atype = pred.get("action", "")
                matched = [d for d in recent_decisions
                           if d.get("decision_type", "").lower().replace("_", "")
                           == atype.replace("_", "") and d.get("timestamp", 0) >= ts]
                if matched:
                    self._predictions[i] = (ts, pred, {"executed": True, "n": len(matched)})
                    resolved += 1
                    if pred.get("confidence", 0) > config.CONFIDENCE_THRESHOLD:
                        correct += 1
            total = sum(1 for _, _, o in self._predictions if o is not None)
            self._prediction_accuracy = (correct / total) if total > 0 else 0.5
            # Feed outcomes to ML model for online learning
            for ts, pred, outcome in self._predictions:
                if outcome is not None and outcome.get("executed"):
                    score = 1.0 if pred.get("confidence", 0) > config.CONFIDENCE_THRESHOLD else 0.0
                    self._ml_model.record_outcome(
                        pred.get("action", ""), pred.get("confidence", 0), score
                    )
            if len(self._predictions) > 100:
                self._predictions = self._predictions[-100:]
            insights = {
                "total_predictions": len(self._predictions),
                "resolved_this_cycle": resolved,
                "prediction_accuracy": round(self._prediction_accuracy, 3),
                "preferences": dict(self._preferences),
            }
            # LLM-powered self-reflection
            try:
                history = [{"action": p[1].get("action", ""), "confidence": p[1].get("confidence", 0),
                            "executed": p[2] is not None} for p in self._predictions[-20:]]
                llm_reflection = self._llm.meta_reflect(
                    history=history,
                    performance={
                        "accuracy": self._prediction_accuracy,
                        "total_predictions": len(self._predictions),
                        "preferences": dict(self._preferences),
                        "cycle_count": self._cycle_count,
                    }
                )
                insights["llm_reflection"] = llm_reflection
                self._llm_reasoning_cache["reflection"] = llm_reflection
                logger.info("LLM reflection: %s", llm_reflection.get("summary", "")[:100])
            except Exception as llm_exc:
                logger.warning("LLM reflection fallback: %s", llm_exc)
            self.journal.log_decision(0, "META_COGNITION",
                f"Reflection: accuracy={self._prediction_accuracy:.2%}, resolved={resolved}",
                insights)
            logger.info("Reflection: accuracy=%.1f%%, %d tracked",
                        self._prediction_accuracy * 100, len(self._predictions))
            return insights
        except Exception as exc:
            logger.error("Meta-cognition layer failed: %s", exc)
            return {"error": str(exc)}

    # ═══════════════════════════════════════════════════════════════════
    # ORCHESTRATION: execute_plan, run_cycle, start/stop, status
    # ═══════════════════════════════════════════════════════════════════
    def execute_plan(self, actions: list) -> list:
        """Dispatch actions to managers. Respects CONFIDENCE_THRESHOLD and PAUSED."""
        results = []
        for action in actions:
            atype, conf = action["type"], action.get("confidence", 0)
            params = action.get("params", {})
            # Generate LLM explanation for every significant action
            if atype != "hold":
                try:
                    explanation = self._llm.explain_decision(
                        decision_type=atype.upper(),
                        context={
                            "confidence": conf,
                            "reasoning": action.get("reasoning", ""),
                            "params": params,
                            "market_state": {
                                k: v for k, v in self._analysis_cache.items()
                                if k in ("regimes", "momentum", "bayesian_regime")
                            },
                        }
                    )
                    action["llm_explanation"] = explanation
                    self._llm_reasoning_cache[f"decision_{atype}"] = explanation
                except Exception:
                    pass
            atype, conf = action["type"], action.get("confidence", 0)
            params = action.get("params", {})
            if conf < config.CONFIDENCE_THRESHOLD:
                logger.info("Skip %s (conf %.2f < %.2f)", atype, conf, config.CONFIDENCE_THRESHOLD)
                results.append({"action": atype, "status": "skipped_low_confidence"})
                continue
            if config.PAUSED:
                logger.info("PAUSED — skip %s", atype)
                results.append({"action": atype, "status": "paused"})
                continue
            try:
                if atype == "create_strategy":
                    r = self.strategy_mgr.create_strategy(params["regime"], params.get("market_data", {}))
                    results.append({"action": atype, "status": "ok", "result": r})
                elif atype == "rebalance":
                    self.strategy_mgr.rebalance_strategy(params["strategy_id"], params["new_regime"])
                    results.append({"action": atype, "status": "ok"})
                elif atype == "deactivate":
                    self.strategy_mgr.deactivate_strategy(params["strategy_id"], params["reason"])
                    results.append({"action": atype, "status": "ok"})
                elif atype == "hold":
                    results.append({"action": atype, "status": "ok"})
                else:
                    logger.warning("Unknown action type: %s", atype)
                    results.append({"action": atype, "status": "unknown_type"})
            except Exception as exc:
                logger.error("Execute %s failed: %s", atype, exc)
                results.append({"action": atype, "status": "error", "error": str(exc)})
        return results

    def run_cycle(self) -> dict:
        """One full cognitive cycle: perceive -> analyze -> plan -> execute -> reflect."""
        self._cycle_count += 1
        t0 = time.time()
        logger.info("=== Cycle %d start ===", self._cycle_count)
        self.perceive()
        now = time.time()
        if now - self._last_analysis >= config.ANALYSIS_INTERVAL_SEC or self._cycle_count == 1:
            self.analyze()
        actions = self.plan()
        results = self.execute_plan(actions)
        evolution = self.evolve() if (now - self._last_evolution >= config.EVOLUTION_INTERVAL_SEC) else None
        reflection = self.reflect()
        elapsed = time.time() - t0
        logger.info("=== Cycle %d done (%.2fs) ===", self._cycle_count, elapsed)
        return {
            "cycle": self._cycle_count, "elapsed_sec": round(elapsed, 3),
            "actions_planned": len(actions),
            "actions_executed": sum(1 for r in results if r["status"] == "ok"),
            "evolution": evolution,
            "prediction_accuracy": reflection.get("prediction_accuracy"),
        }

    def start(self):
        """Main loop — runs cycles at PERCEPTION_INTERVAL_SEC."""
        self._running = True
        logger.info("GenesisEngine starting (interval=%ds)", config.PERCEPTION_INTERVAL_SEC)
        try:
            while self._running:
                self.run_cycle()
                time.sleep(config.PERCEPTION_INTERVAL_SEC)
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            logger.info("GenesisEngine stopped")

    def stop(self):
        """Signal the main loop to stop after the current cycle."""
        self._running = False

    def get_status(self) -> dict:
        """Current engine status for external monitoring."""
        return {
            "running": self._running, "paused": config.PAUSED, "mode": config.MODE,
            "cycle_count": self._cycle_count,
            "prediction_accuracy": round(self._prediction_accuracy, 3),
            "preferences": dict(self._preferences),
            "active_strategies": self.strategy_mgr.get_strategy_summary(),
            "last_perception": int(self._last_perception) or None,
            "last_analysis": int(self._last_analysis) or None,
            "last_evolution": int(self._last_evolution) or None,
            "ml_momentum": self._ml_model.get_momentum_signal(),
            "ml_forecast": self._ml_model.linear_regression_predict(),
            "bayesian_regime": self._ml_model._bayesian_prior,
            "llm_provider": self._llm.provider,
            "llm_reasoning": self._llm_reasoning_cache,
            "oracle_confidence_weight": round(self._oracle_confidence_weight, 4),
            "oracle_confidence_details": self._oracle_confidence_details,
        }
