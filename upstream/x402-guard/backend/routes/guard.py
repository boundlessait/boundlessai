from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import sys
import os

# Allow importing from parent package when run standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import GuardRequest, GuardResponse, SpendingStats
from policy_engine import engine
from notifier import notifier
from websocket_manager import manager
from onchain_logger import onchain_logger

router = APIRouter(prefix="/guard", tags=["guard"])


@router.post("/check", response_model=GuardResponse, summary="Evaluate a payment request against policy")
async def check_payment(request: GuardRequest) -> GuardResponse:
    """
    Core x402 middleware endpoint.

    An AI agent calls this before making any x402 payment.
    Returns whether the payment is allowed, a tiered action signal,
    and remaining budget figures so the agent can self-throttle.

    Actions:
      approve     — within all limits, proceed
      soft_alert  — approaching a limit (80-100%), allowed but agent should notify
      block       — over limit or policy violation, do NOT proceed
    """
    try:
        result = engine.check_and_approve(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ── Onchain logging (fire-and-forget) ──────────────────────────────────────
    # Log the guard decision to GuardLog.sol on X Layer asynchronously.
    # Never awaited — never blocks the guard response.
    import asyncio
    asyncio.create_task(
        onchain_logger.log_decision(
            agent_id=request.agent_id,
            amount=float(request.amount),
            action=result.action,
            domain=str(request.pay_to),
        )
    )

    # ── Real-time WebSocket broadcast ──────────────────────────────────────────
    # Broadcast the guard decision to all connected dashboard clients.
    # Fire-and-forget: never let a WS failure break the guard response.
    try:
        await manager.broadcast_event(
            "guard_decision",
            {
                "agent_id":        request.agent_id,
                "amount":          request.amount,
                "asset":           request.asset,
                "pay_to":          request.pay_to,
                "network":         request.network,
                "action":          result.action,
                "allowed":         result.allowed,
                "reason":          result.reason,
                "remaining_daily": result.remaining_daily,
                "remaining_hourly":result.remaining_hourly,
                "transaction_id":  result.transaction_id,
            },
        )
    except Exception as ws_exc:  # pragma: no cover
        import logging
        logging.getLogger(__name__).debug("WebSocket broadcast error: %s", ws_exc)

    # ── Post-check notifications ───────────────────────────────────────────────
    # Fire-and-forget: build a lightweight tx dict from the request + result so
    # the notifier has the context it needs without depending on storage lookups.
    try:
        tx_dict = {
            "id":       result.transaction_id or "",
            "agent_id": request.agent_id,
            "amount":   request.amount,
            "asset":    request.asset,
            "pay_to":   request.pay_to,
            "network":  request.network,
        }

        if result.action == "soft_alert":
            # Build a minimal stats dict from the GuardResponse fields
            stats_dict = _stats_from_response(request, result)
            notifier.send_soft_alert(
                agent_id=request.agent_id,
                tx=tx_dict,
                stats=stats_dict,
            )

        elif result.action == "block":
            notifier.send_block_alert(
                agent_id=request.agent_id,
                tx=tx_dict,
                reason=result.reason,
            )
    except Exception as notify_exc:  # pragma: no cover
        # Never let a notification failure break the guard response
        import logging
        logging.getLogger(__name__).warning("Notifier error: %s", notify_exc)

    return result


@router.get("/transactions/all", summary="List all transactions across all agents")
async def list_all_transactions(limit: int = Query(default=200, ge=1, le=1000)):
    """Return all transactions across every agent, newest first. Used by the dashboard."""
    import storage
    txs = storage.load_transactions()
    txs_sorted = sorted(txs, key=lambda t: str(t.get("timestamp", "")), reverse=True)
    return txs_sorted[:limit]


@router.get("/pnl", summary="Guard activity PnL chart — 24h hourly buckets")
async def get_pnl_chart():
    """Return 24 hourly buckets of approved vs blocked spend for the PnL chart.
    Computed server-side so the frontend just proxies one fast call."""
    import storage
    from datetime import datetime, timezone

    txs = storage.load_transactions()
    now = datetime.now(timezone.utc)
    buckets = []

    for h in range(23, -1, -1):
        start_ts = now.timestamp() - (h + 1) * 3600
        end_ts   = now.timestamp() - h * 3600
        label    = datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%H:%M")

        approved = 0.0
        blocked  = 0.0
        for tx in txs:
            try:
                tx_ts = datetime.fromisoformat(tx.get("timestamp", "")).timestamp()
            except Exception:
                continue
            if tx_ts < start_ts or tx_ts >= end_ts:
                continue
            amt = float(tx.get("amount") or 0)
            if tx.get("status") == "blocked":
                blocked += amt
            else:
                approved += amt

        buckets.append({
            "time":     label,
            "approved": round(approved, 2),
            "blocked":  round(blocked, 2),
        })

    # Cumulative
    cum_a = 0.0
    cum_b = 0.0
    for b in buckets:
        cum_a += b["approved"]
        cum_b += b["blocked"]
        b["cumApproved"] = round(cum_a, 2)
        b["cumBlocked"]  = round(cum_b, 2)

    return buckets


@router.get("/stats/{agent_id}", response_model=SpendingStats, summary="Get spending stats for an agent")
async def get_spending_stats(
    agent_id: str,
    policy_id: Optional[str] = Query(default=None, description="Specific policy ID to use for limits"),
) -> SpendingStats:
    """Return current spending statistics and remaining budget for an agent."""
    try:
        return engine.get_stats(agent_id, policy_id=policy_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/transactions/{agent_id}", summary="List transactions for an agent")
async def list_transactions(agent_id: str):
    """Return all recorded transactions for an agent."""
    import storage
    txs = storage.get_transactions_for_agent(agent_id)
    return {"agent_id": agent_id, "count": len(txs), "transactions": txs}


# ── Helper ────────────────────────────────────────────────────────────────────

def _stats_from_response(request: GuardRequest, result: GuardResponse) -> dict:
    """
    Derive a minimal stats-like dict from the request + GuardResponse so the
    notifier can compute the percentage-of-limit used without an extra DB call.

    We infer daily_spent = daily_limit - remaining_daily and reconstruct an
    approximate limit.  For the soft-alert case the values will be very close
    to reality; a full stats lookup is an option but adds latency.
    """
    # Try to fetch authoritative stats without failing the request
    try:
        stats = engine.get_stats(request.agent_id, policy_id=request.policy_id)
        return {
            "daily_spent":          stats.daily_spent,
            "daily_limit":          stats.daily_limit,
            "hourly_spent":         stats.hourly_spent,
            "hourly_limit":         stats.hourly_limit,
            "total_transactions":   stats.total_transactions,
            "blocked_transactions": stats.blocked_transactions,
        }
    except Exception:
        # Fallback: approximate from the GuardResponse
        remaining = result.remaining_daily
        # We don't know the limit exactly from GuardResponse alone, so use
        # remaining + amount as a conservative proxy for daily_limit.
        approx_limit = remaining + request.amount
        return {
            "daily_spent":          request.amount,
            "daily_limit":          approx_limit if approx_limit > 0 else request.amount,
            "hourly_spent":         request.amount,
            "hourly_limit":         result.remaining_hourly + request.amount,
            "total_transactions":   0,
            "blocked_transactions": 0,
        }
