"""
x402 Guard — Notification Manager

Sends Telegram + Discord alerts when the policy engine raises soft-alerts,
blocks a transaction, or produces a daily spending summary.

Telegram messages use HTML parse mode and inline keyboard buttons so the
operator can take action (approve once / bump limit / pause agent) directly
from the chat without opening the dashboard.

Discord messages use the webhook embed format with colour-coded severity.
"""

import logging
import time
from typing import Any, Dict, Optional

import requests

import config

logger = logging.getLogger(__name__)

# ── Colour constants for Discord embeds ───────────────────────────────────────
_COLOUR_ORANGE = 0xFFA500   # soft alert
_COLOUR_RED    = 0xFF0000   # blocked
_COLOUR_GREEN  = 0x00C853   # approved / summary OK


class NotificationManager:
    """
    Thin notification layer on top of Telegram Bot API and Discord webhooks.

    All methods are fire-and-forget: errors are logged but never re-raised so
    that a misconfigured notifier never breaks the payment-guard hot-path.

    Spam protection: a per-agent in-memory timestamp prevents the same alert
    from firing more often than NOTIFICATION_COOLDOWN_SECONDS.
    """

    def __init__(self) -> None:
        self._last_sent: Dict[str, float] = {}   # agent_id -> epoch seconds

    # ── Public API ────────────────────────────────────────────────────────────

    def send_soft_alert(
        self,
        agent_id: str,
        tx: Dict[str, Any],
        stats: Dict[str, Any],
    ) -> None:
        """Send a warning notification when spending hits 80 %+ of the limit."""
        if not self._cooldown_ok(agent_id):
            return

        amount  = tx.get("amount", 0)
        domain  = tx.get("pay_to", "unknown")
        tx_id   = tx.get("id", "")
        daily_limit  = stats.get("daily_limit", 0) or 1   # avoid div-by-zero
        daily_spent  = stats.get("daily_spent", 0)
        pct = round((daily_spent / daily_limit) * 100, 1)

        # ── Telegram ──────────────────────────────────────────────────────────
        tg_text = (
            f"⚠️ <b>x402 Guard — {_esc(agent_id)}</b>\n"
            f"💰 <b>{amount} USDC</b> to <code>{_esc(domain)}</code>\n"
            f"📊 <b>{pct}%</b> of daily limit used "
            f"(<b>${daily_spent:.2f}</b> / <b>${daily_limit:.2f}</b>)\n"
            f"🔗 <a href='{config.BACKEND_URL}/guard/stats/{agent_id}'>View Dashboard</a>"
        )
        keyboard = _inline_keyboard([
            ("✅ Approve Once",  f"approve_once:{agent_id}:{tx_id}"),
            ("📈 +$10 Limit",   f"increase_limit:{agent_id}"),
            ("⏸ Pause Agent",   f"pause_agent:{agent_id}"),
        ])
        self._send_telegram(tg_text, keyboard)

        # ── Discord ───────────────────────────────────────────────────────────
        embed = _discord_embed(
            title=f"⚠️ x402 Guard Alert — {agent_id}",
            description=(
                f"Spending is at **{pct}%** of the daily limit.\n"
                f"[View Dashboard]({config.BACKEND_URL}/guard/stats/{agent_id})"
            ),
            colour=_COLOUR_ORANGE,
            fields=[
                ("Agent",       agent_id,            True),
                ("Amount",      f"${amount} USDC",   True),
                ("Domain",      domain,              True),
                ("Spent Today", f"${daily_spent:.2f} / ${daily_limit:.2f}", True),
                ("Action",      "Soft Alert — payment allowed", False),
            ],
        )
        self._send_discord(embed)

        self._mark_sent(agent_id)

    def send_block_alert(
        self,
        agent_id: str,
        tx: Dict[str, Any],
        reason: str,
    ) -> None:
        """Send a notification when a transaction is blocked."""
        if not self._cooldown_ok(agent_id):
            return

        amount = tx.get("amount", 0)
        domain = tx.get("pay_to", "unknown")
        tx_id  = tx.get("id", "")

        # ── Telegram ──────────────────────────────────────────────────────────
        tg_text = (
            f"🚫 <b>x402 Guard BLOCKED — {_esc(agent_id)}</b>\n"
            f"❌ <b>{amount} USDC</b> to <code>{_esc(domain)}</code>\n"
            f"📋 Reason: {_esc(reason)}\n"
            f"🔗 <a href='{config.BACKEND_URL}/guard/stats/{agent_id}'>View Dashboard</a>"
        )
        keyboard = _inline_keyboard([
            ("🔓 Override",       f"approve_once:{agent_id}:{tx_id}"),
            ("⚙️ Adjust Policy",  f"increase_limit:{agent_id}"),
            ("⏸ Pause Agent",    f"pause_agent:{agent_id}"),
        ])
        self._send_telegram(tg_text, keyboard)

        # ── Discord ───────────────────────────────────────────────────────────
        embed = _discord_embed(
            title=f"🚫 x402 Guard BLOCKED — {agent_id}",
            description=(
                f"Transaction **blocked**.\n"
                f"[View Dashboard]({config.BACKEND_URL}/guard/stats/{agent_id})"
            ),
            colour=_COLOUR_RED,
            fields=[
                ("Agent",   agent_id,           True),
                ("Amount",  f"${amount} USDC",  True),
                ("Domain",  domain,             True),
                ("Reason",  reason,             False),
                ("Action",  "Blocked — payment NOT sent", False),
            ],
        )
        self._send_discord(embed)

        self._mark_sent(agent_id)

    def send_daily_summary(
        self,
        agent_id: str,
        stats: Dict[str, Any],
    ) -> None:
        """Send a daily spending summary (suitable for a scheduler call)."""
        daily_limit  = stats.get("daily_limit", 0) or 1
        daily_spent  = stats.get("daily_spent", 0)
        pct = round((daily_spent / daily_limit) * 100, 1)
        total_tx = stats.get("total_transactions", 0)
        blocked  = stats.get("blocked_transactions", 0)

        # ── Telegram ──────────────────────────────────────────────────────────
        tg_text = (
            f"📅 <b>x402 Guard — Daily Summary</b>\n"
            f"🤖 Agent: <b>{_esc(agent_id)}</b>\n"
            f"💰 Spent: <b>${daily_spent:.2f}</b> / <b>${daily_limit:.2f}</b> ({pct}%)\n"
            f"📦 Transactions: <b>{total_tx}</b> total, <b>{blocked}</b> blocked\n"
            f"🔗 <a href='{config.BACKEND_URL}/guard/stats/{agent_id}'>View Dashboard</a>"
        )
        self._send_telegram(tg_text, reply_markup=None)

        # ── Discord ───────────────────────────────────────────────────────────
        colour = _COLOUR_GREEN if pct < 80 else (_COLOUR_ORANGE if pct < 100 else _COLOUR_RED)
        embed = _discord_embed(
            title=f"📅 Daily Summary — {agent_id}",
            description=(
                f"Spending at **{pct}%** of daily limit.\n"
                f"[View Dashboard]({config.BACKEND_URL}/guard/stats/{agent_id})"
            ),
            colour=colour,
            fields=[
                ("Agent",        agent_id,                              True),
                ("Spent Today",  f"${daily_spent:.2f} / ${daily_limit:.2f}", True),
                ("Transactions", str(total_tx),                         True),
                ("Blocked",      str(blocked),                          True),
            ],
        )
        self._send_discord(embed)

    # ── Internal: cooldown ────────────────────────────────────────────────────

    def _cooldown_ok(self, agent_id: str) -> bool:
        last = self._last_sent.get(agent_id, 0)
        return (time.time() - last) >= config.NOTIFICATION_COOLDOWN_SECONDS

    def _mark_sent(self, agent_id: str) -> None:
        self._last_sent[agent_id] = time.time()

    # ── Internal: Telegram ────────────────────────────────────────────────────

    def _send_telegram(
        self,
        text: str,
        reply_markup: Optional[Dict[str, Any]],
    ) -> None:
        token = config.TELEGRAM_BOT_TOKEN
        chat_id = config.TELEGRAM_CHAT_ID
        if not token or not chat_id:
            logger.debug("Telegram not configured — skipping notification.")
            return

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if not resp.ok:
                logger.warning("Telegram API error %s: %s", resp.status_code, resp.text)
        except requests.RequestException as exc:
            logger.warning("Telegram request failed: %s", exc)

    # ── Internal: Discord ─────────────────────────────────────────────────────

    def _send_discord(self, embed: Dict[str, Any]) -> None:
        webhook_url = config.DISCORD_WEBHOOK_URL
        if not webhook_url:
            logger.debug("Discord not configured — skipping notification.")
            return

        payload = {"embeds": [embed]}
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if not resp.ok:
                logger.warning("Discord webhook error %s: %s", resp.status_code, resp.text)
        except requests.RequestException as exc:
            logger.warning("Discord request failed: %s", exc)


# ── Module-level singleton ────────────────────────────────────────────────────

notifier = NotificationManager()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _inline_keyboard(buttons: list) -> Dict[str, Any]:
    """
    Build a Telegram InlineKeyboardMarkup with one row of buttons.

    buttons: list of (label, callback_data) tuples
    """
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": data} for label, data in buttons]
        ]
    }


def _discord_embed(
    title: str,
    description: str,
    colour: int,
    fields: list,
) -> Dict[str, Any]:
    """Build a Discord embed dict."""
    return {
        "title": title,
        "description": description,
        "color": colour,
        "fields": [
            {"name": name, "value": value, "inline": inline}
            for name, value, inline in fields
        ],
        "footer": {"text": "x402 Guard"},
        "timestamp": _utc_iso(),
    }


def _utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
