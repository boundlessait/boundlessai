"""
x402 Guard - AI Agent Spending Policy & Security Co-Pilot
FastAPI Backend Entry Point

X Layer network:
  chainId : 1952
  CAIP-2  : eip155:1952
  USDC_TEST asset: 0xcB8BF24c6cE16Ad21D707c9505421a17f2bec79D
"""

import sys
import os

# Ensure backend/ is on the path so relative imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routes.guard import router as guard_router
from routes.policy import router as policy_router
from routes.ai import router as ai_router
from routes.onchain import router as onchain_router
from routes.wallet import router as wallet_router
# seed_router removed — no fake data generation in production
from callback_handler import router as callback_router
from websocket_manager import manager

# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="x402 Guard",
    description=(
        "AI Agent Spending Policy & Security Co-Pilot.\n\n"
        "Sits in front of x402 payment flows and enforces per-agent spending policies "
        "with tiered alert levels (approve / soft_alert / block).\n\n"
        "**X Layer network:** chainId 1952 (testnet), CAIP-2 eip155:1952\n"
        "**Default asset:** USDC_TEST `0xcB8BF24c6cE16Ad21D707c9505421a17f2bec79D`"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────

ALLOWED_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:8080",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(guard_router)
app.include_router(policy_router)
app.include_router(ai_router)
app.include_router(onchain_router)
app.include_router(wallet_router)
app.include_router(callback_router)
# seed router removed





# ── Health / meta endpoints ───────────────────────────────────────────────────

@app.get("/", tags=["meta"], summary="Root — service info")
async def root():
    return {
        "service": "x402 Guard",
        "version": "1.0.0",
        "status": "running",
        "network": {
            "name": "X Layer Testnet",
            "chain_id": int(os.environ.get("XLAYER_CHAIN_ID", "1952")),
            "caip2": f"eip155:{os.environ.get('XLAYER_CHAIN_ID', '1952')}",
            "default_asset": os.environ.get("USDC_CONTRACT_ADDRESS", "0xcB8BF24c6cE16Ad21D707c9505421a17f2bec79D"),
            "usdc_symbol": "USDC_TEST",
            "guard_contract": os.environ.get("GUARD_CONTRACT_ADDRESS", ""),
        },
        "endpoints": {
            "guard_check": "POST /guard/check",
            "guard_stats": "GET  /guard/stats/{agent_id}",
            "guard_transactions": "GET  /guard/transactions/{agent_id}",
            "policies_list": "GET  /policies/",
            "policies_create": "POST /policies/",
            "policies_get": "GET  /policies/{policy_id}",
            "policies_update": "PATCH /policies/{policy_id}",
            "policies_delete": "DELETE /policies/{policy_id}",
            "policies_by_agent":   "GET  /policies/agent/{agent_id}",
            "telegram_webhook":    "POST /guard/telegram/webhook",
            "ai_analyze":          "POST /ai/analyze/{agent_id}",
            "ai_simulate":         "POST /ai/simulate",
            "ai_risk_latest":      "GET  /ai/risk/{agent_id}/latest",
            "ai_report":           "GET  /ai/report/{agent_id}",
            "ai_domain_rep":       "GET  /ai/domain-reputation?domain=...",
            "onchain_stats":       "GET  /onchain/stats",
            "onchain_explorer":    "GET  /onchain/explorer-link",
        },
    }


@app.get("/health", tags=["meta"], summary="Health check")
async def health():
    return {"status": "ok", "websocket_clients": manager.connection_count}


# ── WebSocket — real-time guard event feed ─────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for the real-time dashboard feed.

    Connect with:
        ws://localhost:4402/ws

    Messages are JSON objects:
        {"type": "guard_decision", "data": { ...GuardResponse fields... }}
        {"type": "policy_updated", "data": { ...policy fields... }}
    """
    await manager.connect(websocket)
    try:
        # Keep the connection alive; the server pushes events, client can send pings
        while True:
            # Receive and discard client messages (ping frames, etc.)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )


# ── Dev entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=bool(os.environ.get("DEV", True)),
        log_level="info",
        workers=1,  # single worker (async handles concurrency)
    )
