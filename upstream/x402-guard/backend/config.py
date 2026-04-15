"""
x402 Guard — centralised settings loaded from environment variables.

Copy .env.example to .env and fill in the values, then load it with:
    source .env   (bash)
or use python-dotenv / Docker env-file support.
"""

import os


# ── Telegram ──────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Discord ───────────────────────────────────────────────────────────────────

DISCORD_WEBHOOK_URL: str = os.environ.get("DISCORD_WEBHOOK_URL", "")

# ── Backend / dashboard ───────────────────────────────────────────────────────

BACKEND_URL: str = os.environ.get("BACKEND_URL", "http://localhost:4402")

# ── Notification spam-guard ───────────────────────────────────────────────────
# Minimum seconds that must pass between two notifications for the *same* agent.

NOTIFICATION_COOLDOWN_SECONDS: int = int(
    os.environ.get("NOTIFICATION_COOLDOWN_SECONDS", "60")
)
