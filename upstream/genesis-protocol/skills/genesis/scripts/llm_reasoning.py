"""LLM Reasoning Module - Natural language intelligence layer for the Genesis Protocol.

Integrates large language models (OpenAI GPT-4, Anthropic Claude, DeepSeek, any
OpenAI-compatible endpoint, OKX AI) to generate human-readable reasoning for every
decision in the 5-layer cognitive architecture.  Falls back to a sophisticated
template-based reasoning engine when no API keys are available, ensuring the system
always produces articulate explanations.

Architecture fit:
    Perception  -> analyze_market()
    Analysis    -> explain_decision(), risk_assessment()
    Planning    -> generate_strategy_rationale()
    Evolution   -> meta_reflect()
    Meta-Cog    -> meta_reflect() + internal calibration

Only stdlib + urllib are used for HTTP calls.  No third-party packages required.
"""

import hashlib
import json
import logging
import math
import os
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CACHE_TTL_SECONDS = 300  # 5 min default cache lifetime
_MAX_CACHE_ENTRIES = 256
_DEFAULT_RATE_LIMIT_RPM = 30  # requests per minute
_REQUEST_TIMEOUT_S = 25

# Confidence language bands (lower_bound, qualifier)
_CONFIDENCE_LANGUAGE = [
    (0.90, "with very high confidence"),
    (0.75, "with high confidence"),
    (0.60, "with moderate confidence"),
    (0.40, "with limited confidence"),
    (0.20, "with low confidence"),
    (0.00, "with very low confidence"),
]

# Market-regime descriptors used by the template engine
_REGIME_DESCRIPTORS = {
    "calm": {
        "adjective": "low-volatility",
        "behaviour": "range-bound price action with tight spreads",
        "risk_tone": "favourable for passive liquidity provision",
        "strategy_bias": "tighter fee ranges and wider LP positions",
    },
    "volatile": {
        "adjective": "high-volatility",
        "behaviour": "sharp directional moves and wide intra-block spreads",
        "risk_tone": "elevated risk requiring defensive positioning",
        "strategy_bias": "wider fee ranges, MEV protection, and narrower LP bounds",
    },
    "trending": {
        "adjective": "trending",
        "behaviour": "sustained directional momentum with moderate pullbacks",
        "risk_tone": "opportunity-rich but requiring trend-following discipline",
        "strategy_bias": "asymmetric LP ranges biased in the trend direction",
    },
}

# Preset descriptions for strategy rationale
_PRESET_PROFILES = {
    "conservative": {
        "philosophy": "capital preservation with steady yield",
        "fee_approach": "moderate base fees with gentle volatility scaling",
        "risk_stance": "defensive; prioritises drawdown avoidance over return maximisation",
    },
    "balanced": {
        "philosophy": "risk-adjusted return optimisation",
        "fee_approach": "adaptive fees that track realised volatility closely",
        "risk_stance": "neutral; accepts moderate drawdowns for higher expected yield",
    },
    "aggressive": {
        "philosophy": "return maximisation with active risk-taking",
        "fee_approach": "tight fees in calm markets, aggressive scaling in volatile ones",
        "risk_stance": "offensive; tolerates significant drawdowns for outsized gains",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# LRU Cache with TTL
# ═══════════════════════════════════════════════════════════════════════════

class _TTLCache:
    """Thread-naive LRU cache with per-entry TTL.  Good enough for a single
    event-loop agent and keeps stdlib-only constraint."""

    def __init__(self, maxsize: int = _MAX_CACHE_ENTRIES, ttl: float = _CACHE_TTL_SECONDS):
        self._store: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.time() - ts > self._ttl:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def put(self, key: str, value: Any) -> None:
        self._store[key] = (value, time.time())
        self._store.move_to_end(key)
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Rate Limiter (token-bucket)
# ═══════════════════════════════════════════════════════════════════════════

class _RateLimiter:
    """Simple token-bucket rate limiter.  Blocks via ``time.sleep`` if the
    bucket is empty — acceptable for a hackathon agent loop."""

    def __init__(self, rpm: int = _DEFAULT_RATE_LIMIT_RPM):
        self._interval = 60.0 / max(rpm, 1)
        self._last_call = 0.0

    def acquire(self) -> None:
        now = time.time()
        wait = self._interval - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()


# ═══════════════════════════════════════════════════════════════════════════
# Provider adapters
# ═══════════════════════════════════════════════════════════════════════════

def _http_json_post(url: str, headers: dict, payload: dict,
                    timeout: int = _REQUEST_TIMEOUT_S) -> dict:
    """Fire a JSON POST via urllib and return the parsed response body."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        logger.error("HTTP %s from %s: %s", exc.code, url, body[:300])
        raise
    except urllib.error.URLError as exc:
        logger.error("URLError reaching %s: %s", url, exc.reason)
        raise


def _call_openai_compatible(base_url: str, api_key: str, model: str,
                            messages: list, temperature: float = 0.4,
                            max_tokens: int = 1024) -> str:
    """Call any OpenAI-compatible Chat Completions API and return the assistant message.

    Works with OpenAI, DeepSeek, Together, Groq, Ollama, and any other provider
    that implements the ``/chat/completions`` endpoint contract.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    resp = _http_json_post(
        url=url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    )
    return resp["choices"][0]["message"]["content"]


def _call_openai(api_key: str, messages: list, model: str = "gpt-4",
                 temperature: float = 0.4, max_tokens: int = 1024) -> str:
    """Call the OpenAI Chat Completions API and return the assistant message."""
    return _call_openai_compatible(
        base_url="https://api.openai.com/v1",
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _call_anthropic(api_key: str, messages: list, model: str = "claude-3-5-sonnet-20241022",
                    temperature: float = 0.4, max_tokens: int = 1024) -> str:
    """Call the Anthropic Messages API and return the assistant text."""
    # Anthropic expects a system message separated from the user turns.
    system_text = ""
    user_messages = []
    for m in messages:
        if m["role"] == "system":
            system_text += m["content"] + "\n"
        else:
            user_messages.append(m)

    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": user_messages,
    }
    if system_text.strip():
        payload["system"] = system_text.strip()

    resp = _http_json_post(
        url="https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        payload=payload,
    )
    return resp["content"][0]["text"]


def _call_okx_ai(api_key: str, messages: list,
                 temperature: float = 0.4, max_tokens: int = 1024) -> str:
    """Call the OKX AI endpoint (X Layer ecosystem).

    The OKX AI gateway exposes an OpenAI-compatible chat completions route,
    so we reuse the same payload shape.
    """
    base = os.environ.get("OKX_AI_BASE_URL", "https://ai.okx.com/v1")
    resp = _http_json_post(
        url=f"{base}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload={
            "model": os.environ.get("OKX_AI_MODEL", "okx-chat"),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    )
    return resp["choices"][0]["message"]["content"]


def _call_deepseek(api_key: str, messages: list, model: str = "deepseek-chat",
                   temperature: float = 0.4, max_tokens: int = 1024) -> str:
    """Call the DeepSeek Chat API (OpenAI-compatible) and return the assistant message."""
    return _call_openai_compatible(
        base_url="https://api.deepseek.com/v1",
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _call_generic_openai_compatible(api_key: str, messages: list,
                                     temperature: float = 0.4,
                                     max_tokens: int = 1024) -> str:
    """Call a user-configured OpenAI-compatible endpoint.

    Reads ``LLM_BASE_URL`` and ``LLM_MODEL`` from the environment so users can
    plug in any provider (Together, Groq, Ollama, vLLM, etc.).
    """
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("LLM_MODEL", "gpt-4")
    return _call_openai_compatible(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Template-based Reasoning Engine (fallback)
# ═══════════════════════════════════════════════════════════════════════════

class _TemplateReasoner:
    """Generates sophisticated, multi-factor reasoning without any external
    API.  Uses regime-aware templates, confidence-calibrated language, and
    quantitative evidence synthesis.

    This is intentionally *not* a simple f-string formatter.  Each method
    assembles a chain of reasoning steps, weighs evidence, and produces
    prose that mirrors how a quant analyst would narrate a decision.
    """

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _confidence_phrase(conf: float) -> str:
        for threshold, phrase in _CONFIDENCE_LANGUAGE:
            if conf >= threshold:
                return phrase
        return "with indeterminate confidence"

    @staticmethod
    def _direction_word(val: float, pos: str = "upward", neg: str = "downward",
                        neutral: str = "sideways") -> str:
        if val > 0.005:
            return pos
        if val < -0.005:
            return neg
        return neutral

    @staticmethod
    def _magnitude_word(val: float) -> str:
        abs_val = abs(val)
        if abs_val > 5.0:
            return "extreme"
        if abs_val > 2.0:
            return "significant"
        if abs_val > 0.5:
            return "moderate"
        return "marginal"

    @staticmethod
    def _format_bps(bps: float) -> str:
        return f"{bps:.0f} bps ({bps / 100:.2f}%)"

    @staticmethod
    def _risk_score_label(score: float) -> str:
        if score >= 0.8:
            return "critical"
        if score >= 0.6:
            return "elevated"
        if score >= 0.4:
            return "moderate"
        if score >= 0.2:
            return "low"
        return "minimal"

    # -- public reasoning methods ------------------------------------------

    def analyze_market(self, market_data: dict) -> dict:
        """Produce a multi-paragraph market analysis from raw data."""
        vol = market_data.get("volatility_bps", 0) / 100  # to pct
        trend = market_data.get("trend", "sideways")
        momentum = market_data.get("momentum_score", 0.0)
        regime = market_data.get("regime", "calm")
        price = market_data.get("price", 0)
        volume_24h = market_data.get("volume_24h", 0)
        regime_desc = _REGIME_DESCRIPTORS.get(regime, _REGIME_DESCRIPTORS["calm"])

        factors = []
        factors.append(
            f"Realised volatility stands at {vol:.2f}%, which is "
            f"{self._magnitude_word(vol)} for this pair.  "
            f"The EWMA forecast suggests volatility is "
            f"{self._direction_word(market_data.get('vol_trend_score', 0), 'increasing', 'decreasing', 'stable')}."
        )
        factors.append(
            f"Price momentum is {self._direction_word(momentum, 'bullish', 'bearish', 'neutral')} "
            f"(score: {momentum:+.4f}), consistent with "
            f"{regime_desc['behaviour']}."
        )
        if volume_24h:
            factors.append(
                f"24-hour volume of {volume_24h:,.0f} "
                f"{'supports' if volume_24h > 100_000 else 'offers limited support for'} "
                f"the current {regime_desc['adjective']} reading."
            )

        # Synthesise
        headline = (
            f"The market is currently in a **{regime}** regime characterised by "
            f"{regime_desc['behaviour']}.  "
            f"This environment is {regime_desc['risk_tone']}."
        )
        body = "  ".join(factors)
        recommendation = (
            f"Given these conditions, the engine favours {regime_desc['strategy_bias']}.  "
            f"Current trend classification: **{trend}**."
        )

        return {
            "headline": headline,
            "body": body,
            "recommendation": recommendation,
            "factors_considered": len(factors),
            "regime": regime,
            "provider": "template",
        }

    def explain_decision(self, decision_type: str, context: dict) -> str:
        """Compose a structured explanation for a specific decision."""
        conf = context.get("confidence", 0.5)
        regime = context.get("regime", "calm")
        regime_desc = _REGIME_DESCRIPTORS.get(regime, _REGIME_DESCRIPTORS["calm"])

        # Build reasoning chain depending on decision type
        if decision_type == "FEE_ADJUST":
            old_fee = context.get("old_fee_bps", 3000)
            new_fee = context.get("new_fee_bps", 3000)
            delta = new_fee - old_fee
            direction = "increased" if delta > 0 else "decreased" if delta < 0 else "held steady"
            return (
                f"Fee {direction} from {self._format_bps(old_fee)} to "
                f"{self._format_bps(new_fee)} {self._confidence_phrase(conf)}.  "
                f"Rationale: the current {regime_desc['adjective']} regime exhibits "
                f"{regime_desc['behaviour']}, making the prior fee level "
                f"{'insufficient to compensate LPs for impermanent loss risk' if delta > 0 else 'unnecessarily restrictive for swap volume'}."
                f"  The adjustment of {self._format_bps(abs(delta))} aligns with "
                f"the engine's {regime_desc['strategy_bias']} policy."
            )

        if decision_type == "REBALANCE":
            shift = context.get("volatility_shift_bps", 0)
            return (
                f"A rebalance was triggered {self._confidence_phrase(conf)} after detecting "
                f"a {self._magnitude_word(shift / 100)} volatility shift of "
                f"{self._format_bps(abs(shift))}.  "
                f"Under the {regime_desc['adjective']} regime the engine determined that "
                f"LP range boundaries required adjustment to maintain capital efficiency.  "
                f"The new position reflects {regime_desc['strategy_bias']}."
            )

        if decision_type == "STRATEGY_CREATE":
            preset = context.get("preset", "balanced")
            profile = _PRESET_PROFILES.get(preset, _PRESET_PROFILES["balanced"])
            return (
                f"A new **{preset}** strategy was deployed {self._confidence_phrase(conf)} "
                f"for the current {regime_desc['adjective']} regime.  "
                f"This preset emphasises {profile['philosophy']} through "
                f"{profile['fee_approach']}.  "
                f"Risk stance: {profile['risk_stance']}.  "
                f"The regime's characteristic {regime_desc['behaviour']} "
                f"supports this selection."
            )

        if decision_type == "DEACTIVATE":
            pnl = context.get("pnl_bps", 0)
            swaps = context.get("total_swaps", 0)
            reason_parts = []
            if pnl < -500:
                reason_parts.append(
                    f"cumulative PnL of {self._format_bps(pnl)} breached the "
                    f"-500 bps stop-loss threshold"
                )
            if swaps < 5:
                reason_parts.append(
                    f"only {swaps} swaps executed, indicating insufficient market engagement"
                )
            reason_str = " and ".join(reason_parts) if reason_parts else "performance metrics fell below thresholds"
            return (
                f"The strategy was deactivated {self._confidence_phrase(conf)} because "
                f"{reason_str}.  Under the {regime_desc['adjective']} regime, "
                f"continuing operation would expose capital to uncompensated risk."
            )

        # Generic fallback for unknown decision types
        return (
            f"Decision **{decision_type}** was made {self._confidence_phrase(conf)} "
            f"under the {regime_desc['adjective']} ({regime}) market regime.  "
            f"Primary context factors: {json.dumps(context, default=str)[:300]}."
        )

    def generate_strategy_rationale(self, preset: str, regime: str,
                                     confidence: float, market_data: dict) -> str:
        """Explain why a particular strategy preset was selected."""
        profile = _PRESET_PROFILES.get(preset, _PRESET_PROFILES["balanced"])
        regime_desc = _REGIME_DESCRIPTORS.get(regime, _REGIME_DESCRIPTORS["calm"])
        vol = market_data.get("volatility_bps", 0) / 100
        momentum = market_data.get("momentum_score", 0.0)

        evidence_lines = []
        evidence_lines.append(
            f"Volatility at {vol:.2f}% places the market in the "
            f"{regime_desc['adjective']} band, where {regime_desc['behaviour']}."
        )
        evidence_lines.append(
            f"Momentum score of {momentum:+.4f} indicates "
            f"{self._direction_word(momentum, 'bullish bias', 'bearish bias', 'no directional bias')}, "
            f"which is {regime_desc['risk_tone']}."
        )
        evidence_lines.append(
            f"Bayesian posterior confidence in the {regime} classification: "
            f"{confidence:.1%}."
        )

        evidence_block = "\n".join(f"  {i+1}. {line}" for i, line in enumerate(evidence_lines))

        return (
            f"## Strategy Selection: **{preset.title()}**\n\n"
            f"The engine selected the **{preset}** preset "
            f"{self._confidence_phrase(confidence)} based on the following evidence:\n\n"
            f"{evidence_block}\n\n"
            f"**Philosophy:** {profile['philosophy']}.\n"
            f"**Fee approach:** {profile['fee_approach']}.\n"
            f"**Risk stance:** {profile['risk_stance']}.\n\n"
            f"This configuration is designed to exploit the {regime_desc['adjective']} "
            f"regime's tendency toward {regime_desc['behaviour']}, while maintaining "
            f"guardrails consistent with {profile['risk_stance'].split(';')[0].strip()} positioning."
        )

    def meta_reflect(self, history: list, performance: dict) -> dict:
        """Generate a self-reflection report on past decisions."""
        total = len(history)
        if total == 0:
            return {
                "summary": "No decision history available for reflection.",
                "lessons": [],
                "bias_flags": [],
                "calibration": "insufficient data",
                "provider": "template",
            }

        # Tally outcomes
        wins = sum(1 for h in history if h.get("outcome_score", 0) > 0)
        losses = total - wins
        win_rate = wins / total
        avg_conf = sum(h.get("confidence", 0.5) for h in history) / total
        avg_outcome = sum(h.get("outcome_score", 0) for h in history) / total

        # Detect biases
        bias_flags = []
        if avg_conf > 0.8 and win_rate < 0.5:
            bias_flags.append(
                "Overconfidence detected: average confidence "
                f"({avg_conf:.1%}) substantially exceeds realised win rate ({win_rate:.1%}).  "
                "Recommend reducing confidence scaling factor."
            )
        if avg_conf < 0.4 and win_rate > 0.6:
            bias_flags.append(
                "Under-confidence detected: decisions are performing well "
                f"(win rate {win_rate:.1%}) despite low stated confidence ({avg_conf:.1%}).  "
                "Recommend increasing trust in the model signals."
            )
        recent = history[-10:] if len(history) >= 10 else history
        recent_actions = [h.get("action", "") for h in recent]
        if len(set(recent_actions)) == 1 and len(recent_actions) > 3:
            bias_flags.append(
                f"Action monotony: the last {len(recent_actions)} decisions were all "
                f"'{recent_actions[0]}', suggesting possible anchoring bias."
            )

        # Calibration assessment
        if abs(avg_conf - win_rate) < 0.10:
            calibration = "well-calibrated"
        elif avg_conf > win_rate:
            calibration = "over-confident"
        else:
            calibration = "under-confident"

        # Lessons
        lessons = []
        pnl = performance.get("total_pnl_bps", 0)
        sharpe = performance.get("sharpe_ratio", 0)
        if pnl > 0:
            lessons.append(
                f"Cumulative PnL of {self._format_bps(pnl)} validates the current strategy mix."
            )
        else:
            lessons.append(
                f"Negative PnL of {self._format_bps(pnl)} suggests parameter recalibration "
                f"or regime-detection lag."
            )
        if sharpe > 1.0:
            lessons.append(f"Sharpe ratio of {sharpe:.2f} indicates strong risk-adjusted returns.")
        elif sharpe > 0:
            lessons.append(f"Sharpe ratio of {sharpe:.2f} is acceptable but has room for improvement.")
        else:
            lessons.append(
                f"Sharpe ratio of {sharpe:.2f} is below breakeven; consider tightening "
                "risk parameters or switching to a more conservative preset."
            )

        summary = (
            f"Over {total} decisions (win rate {win_rate:.1%}, avg confidence {avg_conf:.1%}), "
            f"the engine is {calibration}.  "
            f"{'No systematic biases detected.' if not bias_flags else f'{len(bias_flags)} bias flag(s) raised.'}"
        )

        return {
            "summary": summary,
            "win_rate": round(win_rate, 4),
            "avg_confidence": round(avg_conf, 4),
            "calibration": calibration,
            "lessons": lessons,
            "bias_flags": bias_flags,
            "provider": "template",
        }

    def risk_assessment(self, portfolio: dict, market_data: dict) -> dict:
        """Produce a multi-factor risk assessment."""
        vol_bps = market_data.get("volatility_bps", 0)
        regime = market_data.get("regime", "calm")
        regime_desc = _REGIME_DESCRIPTORS.get(regime, _REGIME_DESCRIPTORS["calm"])
        total_value = portfolio.get("total_value_usd", 0)
        positions = portfolio.get("positions", [])
        num_positions = len(positions)

        # Composite risk score (0-1)
        vol_risk = min(vol_bps / 1500, 1.0)  # 15% vol saturates
        concentration_risk = 1.0 / max(num_positions, 1)  # single position = 1.0
        regime_risk = {"calm": 0.2, "trending": 0.5, "volatile": 0.8}.get(regime, 0.5)
        composite = 0.4 * vol_risk + 0.3 * concentration_risk + 0.3 * regime_risk
        composite = round(min(composite, 1.0), 4)

        # Estimated VaR (simple parametric, 95%)
        daily_vol_pct = vol_bps / 100 / math.sqrt(365) if vol_bps else 0
        var_95_usd = total_value * daily_vol_pct * 1.645
        max_drawdown_estimate = total_value * daily_vol_pct * 3.0  # ~3-sigma rough estimate

        factors_narrative = []
        factors_narrative.append(
            f"Volatility risk ({vol_risk:.0%} weight 40%): realised vol of "
            f"{vol_bps / 100:.2f}% maps to {self._risk_score_label(vol_risk)} exposure."
        )
        factors_narrative.append(
            f"Concentration risk ({concentration_risk:.0%} weight 30%): "
            f"{num_positions} active position(s) — "
            f"{'well-diversified' if num_positions >= 3 else 'concentrated; consider diversifying'}."
        )
        factors_narrative.append(
            f"Regime risk ({regime_risk:.0%} weight 30%): the {regime_desc['adjective']} "
            f"regime is {regime_desc['risk_tone']}."
        )

        narrative = (
            f"**Composite risk score: {composite:.0%} ({self._risk_score_label(composite)})**\n\n"
            + "\n".join(f"- {f}" for f in factors_narrative)
            + f"\n\nEstimated daily VaR (95%): ${var_95_usd:,.2f}.  "
            f"Rough max-drawdown estimate: ${max_drawdown_estimate:,.2f}."
        )

        return {
            "composite_risk_score": composite,
            "risk_label": self._risk_score_label(composite),
            "var_95_usd": round(var_95_usd, 2),
            "max_drawdown_estimate_usd": round(max_drawdown_estimate, 2),
            "narrative": narrative,
            "factors": {
                "volatility": round(vol_risk, 4),
                "concentration": round(concentration_risk, 4),
                "regime": round(regime_risk, 4),
            },
            "provider": "template",
        }

    def generate_nft_description(self, strategy_meta: dict) -> str:
        """Create a rich NFT description for a Strategy NFT."""
        preset = strategy_meta.get("preset_name", "balanced")
        profile = _PRESET_PROFILES.get(preset, _PRESET_PROFILES["balanced"])
        pnl = strategy_meta.get("pnl_bps", 0)
        swaps = strategy_meta.get("total_swaps", 0)
        hours = strategy_meta.get("run_hours", 0)
        modules = strategy_meta.get("modules", [])
        regime = strategy_meta.get("market_regime_at_creation", "calm")
        regime_desc = _REGIME_DESCRIPTORS.get(regime, _REGIME_DESCRIPTORS["calm"])
        days = hours / 24

        module_prose = ", ".join(m.replace("_", " ").title() for m in modules) if modules else "standard fee module"
        pnl_narrative = (
            f"delivered a cumulative return of {self._format_bps(pnl)}"
            if pnl >= 0
            else f"experienced a drawdown of {self._format_bps(abs(pnl))}"
        )

        return (
            f"# Genesis Strategy NFT — {preset.title()} Architect\n\n"
            f"This NFT immortalises a **{preset}** Uniswap V4 Hook strategy "
            f"forged by the Genesis Protocol AI engine on X Layer.\n\n"
            f"**Performance:** Over {days:.1f} days and {swaps:,} swaps, the strategy "
            f"{pnl_narrative}.\n\n"
            f"**Modules:** {module_prose}.\n\n"
            f"**Market context at creation:** {regime_desc['adjective']} regime "
            f"characterised by {regime_desc['behaviour']}.\n\n"
            f"**Philosophy:** {profile['philosophy']}.\n\n"
            f"*Generated by Genesis Protocol's 5-layer cognitive architecture.*"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Main LLMReasoner class
# ═══════════════════════════════════════════════════════════════════════════

class LLMReasoner:
    """Natural-language reasoning layer for the Genesis Protocol cognitive engine.

    Supports multiple LLM providers (OpenAI, Anthropic, DeepSeek, OKX AI, and
    any OpenAI-compatible endpoint) and falls back to a sophisticated
    template-based reasoning engine when no API keys are configured.  Every
    public method returns structured data that includes both machine-readable
    fields and human-readable narratives.

    Usage::

        reasoner = LLMReasoner()                       # auto-detects provider
        analysis = reasoner.analyze_market(market_data)
        print(analysis["headline"])

    Environment variables (all optional):
        OPENAI_API_KEY      – enables OpenAI GPT-4
        ANTHROPIC_API_KEY   – enables Anthropic Claude
        DEEPSEEK_API_KEY    – enables DeepSeek (deepseek-chat)
        LLM_API_KEY         – enables generic OpenAI-compatible endpoint
        LLM_BASE_URL        – base URL for openai_compatible provider
                              (default: https://api.openai.com/v1)
        LLM_MODEL           – model name for openai_compatible provider
                              (default: gpt-4)
        OKX_AI_API_KEY      – enables OKX AI endpoint
        OKX_AI_BASE_URL     – override OKX AI base URL
        OKX_AI_MODEL        – override OKX AI model name
        LLM_PROVIDER        – force a specific provider ("openai", "anthropic",
                              "deepseek", "openai_compatible", "okx", "template")
        LLM_CACHE_TTL       – cache lifetime in seconds (default 300)
        LLM_RATE_LIMIT_RPM  – max requests per minute (default 30)
    """

    # Provider priority order (first available key wins)
    _PROVIDER_ORDER = ["openai", "anthropic", "deepseek", "openai_compatible", "okx"]

    def __init__(self, provider: Optional[str] = None):
        """Initialise the reasoner.

        Args:
            provider: Force a specific provider.  If ``None``, the best
                      available provider is auto-detected from env vars.
        """
        self._keys: Dict[str, str] = {
            "openai": os.environ.get("OPENAI_API_KEY", ""),
            "anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
            "deepseek": os.environ.get("DEEPSEEK_API_KEY", ""),
            "openai_compatible": os.environ.get("LLM_API_KEY", ""),
            "okx": os.environ.get("OKX_AI_API_KEY", ""),
        }
        forced = provider or os.environ.get("LLM_PROVIDER", "")
        if forced and forced != "template":
            if self._keys.get(forced):
                self._provider = forced
            else:
                logger.warning(
                    "Forced provider '%s' has no API key; falling back to template mode.",
                    forced,
                )
                self._provider = "template"
        elif forced == "template":
            self._provider = "template"
        else:
            self._provider = self._auto_detect_provider()

        ttl = int(os.environ.get("LLM_CACHE_TTL", str(_CACHE_TTL_SECONDS)))
        rpm = int(os.environ.get("LLM_RATE_LIMIT_RPM", str(_DEFAULT_RATE_LIMIT_RPM)))
        self._cache = _TTLCache(ttl=ttl)
        self._limiter = _RateLimiter(rpm=rpm)
        self._template = _TemplateReasoner()

        logger.info("LLMReasoner initialised (provider=%s)", self._provider)

    # -- internal helpers --------------------------------------------------

    def _auto_detect_provider(self) -> str:
        for p in self._PROVIDER_ORDER:
            if self._keys.get(p):
                return p
        return "template"

    @property
    def provider(self) -> str:
        """The active provider name."""
        return self._provider

    def _cache_key(self, *parts: str) -> str:
        raw = "|".join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def _call_llm(self, messages: list, temperature: float = 0.4,
                  max_tokens: int = 1024) -> str:
        """Dispatch to the active LLM provider with rate limiting and caching.

        Returns the model's text response, or raises on failure.
        """
        ck = self._cache_key(self._provider, json.dumps(messages))
        cached = self._cache.get(ck)
        if cached is not None:
            return cached

        self._limiter.acquire()

        if self._provider == "openai":
            text = _call_openai(self._keys["openai"], messages, temperature=temperature,
                                max_tokens=max_tokens)
        elif self._provider == "anthropic":
            text = _call_anthropic(self._keys["anthropic"], messages, temperature=temperature,
                                   max_tokens=max_tokens)
        elif self._provider == "deepseek":
            text = _call_deepseek(self._keys["deepseek"], messages, temperature=temperature,
                                  max_tokens=max_tokens)
        elif self._provider == "openai_compatible":
            text = _call_generic_openai_compatible(self._keys["openai_compatible"], messages,
                                                    temperature=temperature,
                                                    max_tokens=max_tokens)
        elif self._provider == "okx":
            text = _call_okx_ai(self._keys["okx"], messages, temperature=temperature,
                                max_tokens=max_tokens)
        else:
            raise ValueError(f"Cannot call LLM with provider '{self._provider}'")

        self._cache.put(ck, text)
        return text

    def _llm_or_fallback(self, messages: list, fallback_fn, *fb_args,
                         temperature: float = 0.4, max_tokens: int = 1024,
                         **fb_kwargs) -> Tuple[Any, str]:
        """Try calling the LLM; on any failure, invoke *fallback_fn* instead.

        Returns ``(result, provider_used)`` where *result* is either the LLM
        text or the fallback function's return value.
        """
        if self._provider == "template":
            return fallback_fn(*fb_args, **fb_kwargs), "template"
        try:
            text = self._call_llm(messages, temperature=temperature,
                                  max_tokens=max_tokens)
            return text, self._provider
        except Exception as exc:
            logger.warning("LLM call failed (%s); using template fallback: %s",
                           self._provider, exc)
            return fallback_fn(*fb_args, **fb_kwargs), "template"

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Genesis Protocol's AI reasoning engine — an autonomous DeFi agent "
            "operating Uniswap V4 Hook strategies on X Layer (Chain 196). You analyze "
            "market microstructure, volatility regimes, and MEV patterns to optimize "
            "liquidity provision. Provide concise, quantitative analysis.  "
            "You operate within a 5-layer cognitive architecture (Perception, Analysis, "
            "Planning, Evolution, Meta-Cognition).  Reference specific numbers from the "
            "data.  Write in professional analyst prose — no bullet-point lists unless "
            "explicitly requested.  Never fabricate data."
        )

    # =====================================================================
    # Public API
    # =====================================================================

    def analyze_market(self, market_data: dict) -> dict:
        """Generate a comprehensive market analysis with human-readable reasoning.

        Args:
            market_data: Dictionary containing at minimum ``regime``,
                ``volatility_bps``, ``trend``, ``momentum_score``.  Optional
                keys: ``price``, ``volume_24h``, ``vol_trend_score``.

        Returns:
            Dictionary with keys ``headline``, ``body``, ``recommendation``,
            ``regime``, ``factors_considered``, ``provider``.
        """
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": (
                "Analyse the following market snapshot and produce a JSON object "
                "with keys: headline, body, recommendation, factors_considered (int), "
                "regime.  Be specific and quantitative.\n\n"
                f"Market data: {json.dumps(market_data, default=str)}"
            )},
        ]
        result, prov = self._llm_or_fallback(
            messages, self._template.analyze_market, market_data,
        )
        if prov != "template":
            try:
                parsed = json.loads(result)
                parsed["provider"] = prov
                return parsed
            except (json.JSONDecodeError, TypeError):
                return {
                    "headline": result[:200],
                    "body": result,
                    "recommendation": "",
                    "factors_considered": 0,
                    "regime": market_data.get("regime", "unknown"),
                    "provider": prov,
                }
        return result  # already a dict from template

    def explain_decision(self, decision_type: str, context: dict) -> str:
        """Explain why a specific decision was made.

        Args:
            decision_type: One of the Genesis decision types (``FEE_ADJUST``,
                ``REBALANCE``, ``STRATEGY_CREATE``, ``DEACTIVATE``, etc.).
            context: Relevant context dict (confidence, regime, fee values, …).

        Returns:
            Human-readable explanation string.
        """
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": (
                f"Explain this {decision_type} decision made by the Genesis Protocol "
                f"engine.  Provide a 2–4 sentence analyst-grade explanation.\n\n"
                f"Context: {json.dumps(context, default=str)}"
            )},
        ]
        result, prov = self._llm_or_fallback(
            messages, self._template.explain_decision, decision_type, context,
        )
        if prov != "template" and isinstance(result, str):
            return result
        return result

    def generate_strategy_rationale(self, preset: str, regime: str,
                                     confidence: float, market_data: dict) -> str:
        """Explain why a particular strategy preset was selected.

        Args:
            preset: Strategy preset name (``conservative``, ``balanced``,
                ``aggressive``).
            regime: Current market regime (``calm``, ``volatile``, ``trending``).
            confidence: Bayesian posterior confidence in the regime classification
                (0.0–1.0).
            market_data: Supporting market data dict.

        Returns:
            Markdown-formatted rationale string.
        """
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": (
                f"The Genesis engine selected the '{preset}' strategy preset for a "
                f"'{regime}' market regime (confidence {confidence:.1%}).  "
                f"Write a compelling markdown rationale (heading + 2-3 paragraphs) "
                f"explaining why.\n\n"
                f"Market data: {json.dumps(market_data, default=str)}"
            )},
        ]
        result, prov = self._llm_or_fallback(
            messages, self._template.generate_strategy_rationale,
            preset, regime, confidence, market_data,
        )
        return result

    def meta_reflect(self, history: list, performance: dict) -> dict:
        """Self-reflection on past decisions (Meta-Cognition layer).

        Args:
            history: List of past decision dicts, each containing at least
                ``action``, ``confidence``, ``outcome_score``.
            performance: Aggregate performance dict with ``total_pnl_bps``,
                ``sharpe_ratio``, etc.

        Returns:
            Dictionary with ``summary``, ``lessons``, ``bias_flags``,
            ``calibration``, ``provider``, and optionally ``win_rate``,
            ``avg_confidence``.
        """
        # Truncate history for prompt context window
        recent = history[-50:] if len(history) > 50 else history

        messages = [
            {"role": "system", "content": (
                self._system_prompt() + "  You are performing meta-cognition: "
                "reflect on the engine's own decision history, identify biases, "
                "assess calibration, and suggest concrete improvements."
            )},
            {"role": "user", "content": (
                "Reflect on the following decision history and performance metrics.  "
                "Return a JSON object with keys: summary (str), lessons (list[str]), "
                "bias_flags (list[str]), calibration (str), win_rate (float), "
                "avg_confidence (float).\n\n"
                f"Recent decisions ({len(recent)} of {len(history)} total): "
                f"{json.dumps(recent, default=str)}\n\n"
                f"Performance: {json.dumps(performance, default=str)}"
            )},
        ]
        result, prov = self._llm_or_fallback(
            messages, self._template.meta_reflect, history, performance,
        )
        if prov != "template":
            try:
                parsed = json.loads(result) if isinstance(result, str) else result
                parsed["provider"] = prov
                return parsed
            except (json.JSONDecodeError, TypeError):
                return {
                    "summary": result if isinstance(result, str) else str(result),
                    "lessons": [],
                    "bias_flags": [],
                    "calibration": "unknown",
                    "provider": prov,
                }
        return result

    def risk_assessment(self, portfolio: dict, market_data: dict) -> dict:
        """Generate a risk analysis with LLM-powered reasoning.

        Args:
            portfolio: Dict with ``total_value_usd`` and ``positions`` (list).
            market_data: Current market snapshot dict.

        Returns:
            Dictionary with ``composite_risk_score``, ``risk_label``,
            ``var_95_usd``, ``narrative``, ``factors``, ``provider``.
        """
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": (
                "Perform a risk assessment for this DeFi portfolio.  Return a JSON "
                "object with keys: composite_risk_score (0-1), risk_label, "
                "var_95_usd, max_drawdown_estimate_usd, narrative (markdown str), "
                "factors (dict with volatility, concentration, regime sub-scores).\n\n"
                f"Portfolio: {json.dumps(portfolio, default=str)}\n\n"
                f"Market data: {json.dumps(market_data, default=str)}"
            )},
        ]
        result, prov = self._llm_or_fallback(
            messages, self._template.risk_assessment, portfolio, market_data,
        )
        if prov != "template":
            try:
                parsed = json.loads(result) if isinstance(result, str) else result
                parsed["provider"] = prov
                return parsed
            except (json.JSONDecodeError, TypeError):
                return {
                    "composite_risk_score": 0.5,
                    "risk_label": "unknown",
                    "var_95_usd": 0,
                    "max_drawdown_estimate_usd": 0,
                    "narrative": result if isinstance(result, str) else str(result),
                    "factors": {},
                    "provider": prov,
                }
        return result

    def generate_nft_description(self, strategy_meta: dict) -> str:
        """Generate a rich description for a Strategy NFT.

        Args:
            strategy_meta: Strategy record dict including ``preset_name``,
                ``pnl_bps``, ``total_swaps``, ``run_hours``, ``modules``,
                ``market_regime_at_creation``.

        Returns:
            Markdown-formatted NFT description string.
        """
        messages = [
            {"role": "system", "content": (
                self._system_prompt() + "  You are writing a prestigious NFT "
                "description for a high-performing Uniswap V4 Hook strategy.  "
                "Make it compelling, quantitative, and collector-worthy."
            )},
            {"role": "user", "content": (
                "Write a markdown NFT description (title + 3-4 paragraphs) for "
                "this Genesis Protocol Strategy NFT.\n\n"
                f"Strategy metadata: {json.dumps(strategy_meta, default=str)}"
            )},
        ]
        result, prov = self._llm_or_fallback(
            messages, self._template.generate_nft_description, strategy_meta,
        )
        return result

    # -- utility -----------------------------------------------------------

    def clear_cache(self) -> None:
        """Flush the response cache."""
        self._cache.clear()
        logger.debug("LLMReasoner cache cleared.")

    def health_check(self) -> dict:
        """Return provider status information.

        Returns:
            Dict with ``provider``, ``has_api_key``, ``cache_size``.
        """
        return {
            "provider": self._provider,
            "has_api_key": bool(self._keys.get(self._provider)),
            "available_providers": [
                p for p in self._PROVIDER_ORDER if self._keys.get(p)
            ] + ["template"],
            "cache_entries": len(self._cache._store),
        }

    def __repr__(self) -> str:
        return f"<LLMReasoner provider={self._provider!r}>"
