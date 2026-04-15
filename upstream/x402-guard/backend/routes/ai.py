"""
x402 Guard - AI Co-Pilot Routes

POST /ai/analyze/{agent_id}   -> PolicySuggestion
POST /ai/simulate             -> SimulationResult
GET  /ai/risk/{agent_id}/latest -> risk score of latest transaction
GET  /ai/report/{agent_id}    -> Markdown spending report
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

# Allow importing from parent package when run standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import storage
from ai_copilot import copilot
from reputation import reputation

router = APIRouter(prefix="/ai", tags=["ai-copilot"])


# ── Request / Response models ─────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    agent_id: str
    policy: Dict[str, Any] = Field(
        ...,
        description=(
            "Policy config dict with keys: daily_limit, hourly_limit, per_tx_limit, "
            "auto_approve_under, soft_alert_threshold, whitelist, blacklist"
        ),
        example={
            "daily_limit": 100.0,
            "hourly_limit": 20.0,
            "per_tx_limit": 10.0,
            "auto_approve_under": 0.01,
            "soft_alert_threshold": 0.80,
            "whitelist": [],
            "blacklist": [],
        },
    )
    days_back: int = Field(
        default=30,
        ge=1,
        le=365,
        description="How many days of history to replay (default 30)",
    )


class AnalyzeRequest(BaseModel):
    """Optional body for POST /ai/analyze/{agent_id} — if omitted, all history is used."""
    days_back: int = Field(
        default=90,
        ge=1,
        le=365,
        description="How many days of history to include (default 90)",
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    s = str(raw).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(s.split("+")[0].rstrip("Z"), fmt)
        except ValueError:
            continue
    return None


def _get_recent_txs(agent_id: str, days_back: int) -> List[Dict[str, Any]]:
    all_txs = storage.get_transactions_for_agent(agent_id)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_back)
    return [
        t for t in all_txs
        if (_parse_ts(t.get("timestamp")) or datetime.min) >= cutoff
    ]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/analyze/{agent_id}",
    summary="Analyse spending and get a suggested policy",
    response_description="PolicySuggestion with suggested limits, reasoning, and anomalies",
)
async def analyze_spending(
    agent_id: str,
    body: Optional[AnalyzeRequest] = None,
):
    """
    Analyses an agent's transaction history and returns a statistically derived
    policy suggestion together with detected anomalies.

    - Detects time-of-day clustering, domain frequency, amount distribution
    - Suggests optimal daily/hourly/per-tx limits based on 95th percentile
    - Flags: amount spikes, new unknown domains, off-hours payments
    - Returns confidence score based on sample size and variance
    """
    try:
        days_back = body.days_back if body else 90
        txs = _get_recent_txs(agent_id, days_back)
        result = copilot.analyze_spending(agent_id, txs)
        return {
            "agent_id": agent_id,
            "analysed_transactions": len(txs),
            "days_back": days_back,
            **result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/simulate",
    summary="Simulate a policy against historical transactions",
    response_description=(
        "SimulationResult: approved/soft_alerted/blocked counts, total_saved, "
        "false_positive_rate, recommendation"
    ),
)
async def simulate_policy(body: SimulateRequest):
    """
    Replays the last N days of an agent's transactions through the supplied policy
    configuration and returns simulation metrics.

    The false_positive_rate measures how many transactions that were *originally
    approved* would have been blocked by the new policy (conservative estimate of
    over-blocking).
    """
    try:
        txs = _get_recent_txs(body.agent_id, body.days_back)
        if not txs:
            return {
                "agent_id": body.agent_id,
                "days_back": body.days_back,
                "total_transactions_replayed": 0,
                "approved": 0,
                "soft_alerted": 0,
                "blocked": 0,
                "total_saved": 0.0,
                "false_positive_rate": 0.0,
                "recommendation": "No transaction history found for this agent.",
            }

        result = copilot.simulate_policy(body.policy, txs)
        return {
            "agent_id": body.agent_id,
            "days_back": body.days_back,
            "total_transactions_replayed": len(txs),
            **result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/risk/{agent_id}/latest",
    summary="Get risk score for the agent's latest transaction",
    response_description="Risk score 0.0 (safe) to 1.0 (high risk) for most recent transaction",
)
async def get_latest_risk_score(agent_id: str):
    """
    Computes a composite risk score for the agent's most recent transaction.

    Score factors (weighted):
    - Amount vs historical average (35%)
    - Domain/address reputation (30%)
    - Time of day (15%)
    - Transaction velocity last hour (20%)
    """
    try:
        all_txs = storage.get_transactions_for_agent(agent_id)
        if not all_txs:
            raise HTTPException(
                status_code=404,
                detail=f"No transactions found for agent '{agent_id}'",
            )

        # Sort by timestamp and get latest
        def _ts_key(t):
            return _parse_ts(t.get("timestamp")) or datetime.min

        latest = max(all_txs, key=_ts_key)
        risk = copilot.get_risk_score(latest)

        risk_level = "low" if risk < 0.35 else ("medium" if risk < 0.65 else "high")
        rep_score = reputation.score_domain(latest.get("pay_to", ""))

        return {
            "agent_id": agent_id,
            "transaction_id": latest.get("id"),
            "timestamp": latest.get("timestamp"),
            "amount": latest.get("amount"),
            "pay_to": latest.get("pay_to"),
            "original_status": latest.get("status"),
            "risk_score": risk,
            "risk_level": risk_level,
            "domain_reputation": rep_score,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/report/{agent_id}",
    summary="Generate a full Markdown spending report for an agent",
    response_class=PlainTextResponse,
    responses={
        200: {
            "content": {"text/markdown": {}},
            "description": "Markdown-formatted spending and risk report",
        }
    },
)
async def get_report(agent_id: str):
    """
    Generates a comprehensive Markdown report covering:
    - 30-day spending summary (totals, mean, p95, max)
    - Daily spending breakdown for the last 7 days
    - Top payment destinations with reputation scores
    - Detected anomalies with severity levels
    - AI policy recommendation with confidence score
    """
    try:
        all_txs = storage.get_transactions_for_agent(agent_id)
        if not all_txs:
            report = (
                f"# x402 Guard - AI Co-Pilot Report\n\n"
                f"**Agent:** `{agent_id}`\n\n"
                f"No transaction history found for this agent.\n"
            )
            return PlainTextResponse(content=report, media_type="text/markdown")

        report = copilot.generate_report(agent_id)
        return PlainTextResponse(content=report, media_type="text/markdown")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/domain-reputation",
    summary="Score a domain or address for trustworthiness",
)
async def score_domain(domain: str):
    """
    Returns a reputation score 0.0-1.0 for the given domain or wallet address.

    - >= 0.85 : trusted (known good protocol/exchange)
    - 0.40-0.84: unknown / neutral
    - < 0.40 : suspicious (bad patterns, typosquatting, high entropy)
    - 0.0 : known bad pattern
    """
    try:
        score = reputation.score_domain(domain)
        return {
            "domain": domain,
            "reputation_score": score,
            "trust_level": (
                "trusted" if score >= 0.85
                else "caution" if score >= 0.40
                else "suspicious"
            ),
            "is_known_good": reputation.is_known_good(domain),
            "is_suspicious": reputation.is_suspicious(domain),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
