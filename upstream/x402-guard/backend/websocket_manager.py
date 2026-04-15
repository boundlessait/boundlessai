"""
x402 Guard — WebSocket Connection Manager

Manages all active WebSocket connections and broadcasts real-time guard
decision events to the Next.js dashboard (and any other subscribers).

Usage in routes:

    from websocket_manager import manager

    await manager.connect(websocket)
    await manager.broadcast_event("guard_decision", result_dict)
"""

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Maintains a registry of live WebSocket connections and provides
    broadcast helpers for real-time event delivery.
    """

    def __init__(self) -> None:
        # Active WebSocket connections
        self._connections: list[WebSocket] = []

    # ── Connection lifecycle ──────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection and register it."""
        await websocket.accept()
        self._connections.append(websocket)
        logger.info(
            "WebSocket connected: %s  (total: %d)",
            websocket.client,
            len(self._connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the registry."""
        try:
            self._connections.remove(websocket)
        except ValueError:
            pass  # Already removed
        logger.info(
            "WebSocket disconnected: %s  (total: %d)",
            websocket.client,
            len(self._connections),
        )

    # ── Broadcast helpers ─────────────────────────────────────────────────────

    async def broadcast(self, message: str) -> None:
        """
        Send a raw text message to all connected clients.
        Disconnected clients are silently removed from the registry.
        """
        dead: list[WebSocket] = []

        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except Exception as exc:
                logger.debug("Removing dead connection (%s): %s", ws.client, exc)
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)

    async def broadcast_event(self, event_type: str, data: Any) -> None:
        """
        Broadcast a structured JSON event to all connected clients.

        The message envelope is:
            {"type": "<event_type>", "data": <data>}

        Args:
            event_type: A string tag identifying the event kind, e.g.
                        "guard_decision", "policy_updated", "agent_blocked".
            data:       Any JSON-serialisable value (dict, list, str, etc.).
        """
        payload = json.dumps({"type": event_type, "data": data}, default=str)
        await self.broadcast(payload)

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def connection_count(self) -> int:
        """Number of currently connected WebSocket clients."""
        return len(self._connections)


# ── Module-level singleton used by all routes ─────────────────────────────────
manager = ConnectionManager()
