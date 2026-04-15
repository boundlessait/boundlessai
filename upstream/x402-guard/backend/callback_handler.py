"""
x402 Guard — Telegram Webhook / Callback Handler

Registers a FastAPI router at  POST /guard/telegram/webhook

Telegram sends an Update object here whenever:
  - The bot receives a message
  - A user presses an inline keyboard button (callback_query)

Supported callback_data values
--------------------------------
  approve_once:{agent_id}:{tx_id}   — whitelist a single tx id
  increase_limit:{agent_id}         — bump the agent's daily_limit by $10
  pause_agent:{agent_id}            — set the agent's policy active=False

After handling the action, an answerCallbackQuery call silences the Telegram
"loading" spinner, and a follow-up sendMessage confirms the action.
"""

import logging
import os
import sys
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, Request, Response

# Allow importing from parent package when run standalone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guard", tags=["telegram"])

# ── One-time whitelist (in-memory) ────────────────────────────────────────────
# Maps tx_id -> agent_id.  A tx present here is allowed through once and then
# removed so it cannot be reused.
_one_time_whitelist: Dict[str, str] = {}


def is_tx_whitelisted(tx_id: str, agent_id: str) -> bool:
    """Return True (and consume the entry) if this tx was approved once."""
    if _one_time_whitelist.get(tx_id) == agent_id:
        _one_time_whitelist.pop(tx_id, None)
        return True
    return False


# ── Telegram webhook endpoint ─────────────────────────────────────────────────

@router.post("/telegram/webhook", summary="Receive Telegram bot updates")
async def telegram_webhook(request: Request) -> Response:
    """
    Telegram sends a JSON Update object to this endpoint for every bot event.
    We only handle callback_query (inline keyboard button presses) here.
    """
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return Response(content="bad request", status_code=400)

    callback = body.get("callback_query")
    if callback:
        await _handle_callback(callback)

    # Always return 200 so Telegram doesn't retry
    return Response(content="ok", status_code=200)


# ── Callback dispatcher ───────────────────────────────────────────────────────

async def _handle_callback(callback: Dict[str, Any]) -> None:
    callback_id   = callback.get("id", "")
    chat_id       = callback.get("message", {}).get("chat", {}).get("id")
    callback_data = callback.get("data", "")

    # Acknowledge the button press immediately (stops the spinner in Telegram)
    _answer_callback(callback_id)

    parts = callback_data.split(":")
    action = parts[0] if parts else ""

    if action == "approve_once" and len(parts) >= 3:
        agent_id = parts[1]
        tx_id    = parts[2]
        _do_approve_once(agent_id, tx_id, chat_id)

    elif action == "increase_limit" and len(parts) >= 2:
        agent_id = parts[1]
        _do_increase_limit(agent_id, chat_id)

    elif action == "pause_agent" and len(parts) >= 2:
        agent_id = parts[1]
        _do_pause_agent(agent_id, chat_id)

    else:
        logger.warning("Unknown callback_data: %s", callback_data)
        _send_confirmation(chat_id, "⚠️ Unknown action. Nothing changed.")


# ── Action handlers ───────────────────────────────────────────────────────────

def _do_approve_once(agent_id: str, tx_id: str, chat_id: Optional[int]) -> None:
    """Add a transaction id to the one-time whitelist."""
    _one_time_whitelist[tx_id] = agent_id
    logger.info("approve_once: agent=%s tx=%s", agent_id, tx_id)
    _send_confirmation(
        chat_id,
        f"✅ <b>Approved once</b>\n"
        f"Agent <code>{_esc(agent_id)}</code> — transaction <code>{_esc(tx_id)}</code> "
        f"has been added to the one-time whitelist.\n"
        f"The next check for this tx will be allowed through.",
    )


def _do_increase_limit(agent_id: str, chat_id: Optional[int]) -> None:
    """Increase the agent's daily_limit by $10."""
    policy_dict = storage.get_policy_for_agent(agent_id)
    if policy_dict is None:
        _send_confirmation(
            chat_id,
            f"❌ No active policy found for agent <code>{_esc(agent_id)}</code>.",
        )
        return

    policy_id   = policy_dict["id"]
    old_limit   = float(policy_dict.get("daily_limit", 0))
    new_limit   = old_limit + 10.0

    updated = storage.update_policy(policy_id, {"daily_limit": new_limit})
    if updated is None:
        _send_confirmation(chat_id, "❌ Failed to update policy.")
        return

    logger.info("increase_limit: agent=%s policy=%s %.2f -> %.2f", agent_id, policy_id, old_limit, new_limit)
    _send_confirmation(
        chat_id,
        f"📈 <b>Daily limit increased</b>\n"
        f"Agent <code>{_esc(agent_id)}</code>\n"
        f"${old_limit:.2f} → <b>${new_limit:.2f}</b>",
    )


def _do_pause_agent(agent_id: str, chat_id: Optional[int]) -> None:
    """Set the agent's policy to inactive (paused)."""
    policy_dict = storage.get_policy_for_agent(agent_id)
    if policy_dict is None:
        _send_confirmation(
            chat_id,
            f"❌ No active policy found for agent <code>{_esc(agent_id)}</code>.",
        )
        return

    policy_id = policy_dict["id"]
    updated   = storage.update_policy(policy_id, {"active": False})
    if updated is None:
        _send_confirmation(chat_id, "❌ Failed to pause agent.")
        return

    logger.info("pause_agent: agent=%s policy=%s", agent_id, policy_id)
    _send_confirmation(
        chat_id,
        f"⏸ <b>Agent paused</b>\n"
        f"Agent <code>{_esc(agent_id)}</code> policy has been set to <b>inactive</b>.\n"
        f"All payment requests will be blocked until the policy is reactivated.",
    )


# ── Telegram API helpers ──────────────────────────────────────────────────────

def _answer_callback(callback_query_id: str) -> None:
    """Tell Telegram the callback was handled (removes the loading spinner)."""
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id}, timeout=5)
    except requests.RequestException as exc:
        logger.warning("answerCallbackQuery failed: %s", exc)


def _send_confirmation(chat_id: Optional[int], text: str) -> None:
    """Send a plain HTML confirmation message back to the Telegram chat."""
    token = config.TELEGRAM_BOT_TOKEN
    if not token or not chat_id:
        logger.debug("Cannot send confirmation — token or chat_id missing.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            logger.warning("sendMessage error %s: %s", resp.status_code, resp.text)
    except requests.RequestException as exc:
        logger.warning("sendMessage failed: %s", exc)


def _esc(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
