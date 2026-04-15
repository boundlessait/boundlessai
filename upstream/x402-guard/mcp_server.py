#!/usr/bin/env python3
"""
x402 Guard MCP Server — compatible with OKX Agentic Wallet / OnchainOS.

Usage (local):
    python3 mcp_server.py

Usage (remote API mode):
    X402_GUARD_URL=http://localhost:4402 python3 mcp_server.py

Protocol: JSON-RPC 2.0 over stdio (MCP standard)
"""

import sys, os, json, logging, urllib.request, urllib.error

GUARD_URL = os.environ.get("X402_GUARD_URL", "").rstrip("/")
USE_REMOTE = bool(GUARD_URL)

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
logger = logging.getLogger("x402-guard-mcp")

# ── If local mode, import backend directly ──────────────────────────────────
if not USE_REMOTE:
    BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
    sys.path.insert(0, BACKEND_DIR)
    try:
        from policy_engine import PolicyEngine
        from models import GuardRequest, PolicyCreate
        import storage
        _engine = PolicyEngine()
        _local  = True
    except Exception as e:
        logger.warning(f"Local backend unavailable ({e}), falling back to remote")
        GUARD_URL = "http://localhost:4402"
        USE_REMOTE = True
        _local = False
else:
    _local = False

DEFAULT_ASSET   = "0x4ae46a509f6b1d9056937ba4500cb143933d2dc8"
DEFAULT_NETWORK = "eip155:1952"

# ── Remote helper ───────────────────────────────────────────────────────────

def _remote(path: str, method: str = "GET", body: dict | None = None) -> dict:
    url  = f"{GUARD_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode(), "status": e.code}
    except Exception as e:
        return {"error": str(e)}

# ── Tools ───────────────────────────────────────────────────────────────────

def tool_guard_check(params: dict) -> dict:
    """Check if an x402 payment is allowed. Call BEFORE every payment."""
    agent_id = params.get("agent_id", "").strip()
    if not agent_id:
        return {"error": "agent_id is required"}

    amount = float(params.get("amount", 0))
    pay_to = str(params.get("pay_to", "")).strip()
    network = params.get("network", DEFAULT_NETWORK)
    asset   = params.get("asset",   DEFAULT_ASSET)

    if USE_REMOTE:
        result = _remote("/guard/check", "POST", {
            "agent_id":   agent_id,
            "amount":     amount,
            "pay_to":     pay_to,
            "network":    network,
            "asset":      asset,
            "request_id": f"mcp-{id(params)}",
        })
        return result

    # Local mode
    from models import GuardRequest
    req = GuardRequest(
        agent_id=agent_id, amount=amount,
        pay_to=pay_to, network=network, asset=asset,
    )
    resp = _engine.check_and_approve(req)
    return {
        "allowed":          resp.allowed,
        "action":           resp.action,
        "reason":           resp.reason,
        "remaining_daily":  resp.remaining_daily,
        "remaining_hourly": resp.remaining_hourly,
    }


def tool_guard_stats(params: dict) -> dict:
    """Get spending stats for a bot."""
    agent_id = params.get("agent_id", "").strip()
    if not agent_id:
        return {"error": "agent_id is required"}

    if USE_REMOTE:
        return _remote(f"/guard/stats/{agent_id}")

    policies = storage.load_policies()
    policy = next((p for p in policies if p["agent_id"] == agent_id), None)
    if not policy:
        return {"error": f"No policy found for {agent_id}"}
    txs = storage.load_transactions()
    agent_txs = [t for t in txs if t["agent_id"] == agent_id]
    spent = sum(t["amount"] for t in agent_txs if t["status"] != "blocked")
    return {
        "agent_id":       agent_id,
        "daily_spent":    round(spent, 2),
        "daily_limit":    policy["daily_limit"],
        "total_transactions": len(agent_txs),
        "approved": sum(1 for t in agent_txs if t["status"] == "approved"),
        "blocked":  sum(1 for t in agent_txs if t["status"] == "blocked"),
    }


def tool_guard_register(params: dict) -> dict:
    """Register a bot/OKX Agentic Wallet sub-wallet with spending limits."""
    agent_id = params.get("agent_id", "").strip()
    name     = params.get("name", agent_id)
    if not agent_id:
        return {"error": "agent_id is required"}

    body = {
        "agent_id":       agent_id,
        "name":           name,
        "wallet_address": params.get("wallet_address", ""),
        "bot_type":       params.get("bot_type", "custom"),
        "daily_limit":    float(params.get("daily_limit", 100)),
        "hourly_limit":   float(params.get("hourly_limit", params.get("daily_limit", 100) / 4)),
        "per_tx_limit":   float(params.get("per_tx_limit", 10)),
        "auto_approve_under": 0.01,
        "soft_alert_threshold": 0.8,
        "active": True,
    }

    if USE_REMOTE:
        result = _remote("/policies/", "POST", body)
        if "id" in result:
            return {"success": True, "agent_id": result["agent_id"], "policy_id": result["id"],
                    "message": f"Bot '{name}' registered. daily_limit=${body['daily_limit']}, per_tx=${body['per_tx_limit']}"}
        return result

    from models import PolicyCreate
    pc = PolicyCreate(**{k: v for k, v in body.items() if k in PolicyCreate.model_fields})
    policy = storage.create_policy(pc.model_dump())
    return {"success": True, "agent_id": agent_id, "policy_id": policy["id"],
            "message": f"Bot '{name}' registered successfully."}


def tool_guard_kill(params: dict) -> dict:
    """Emergency kill switch — blocks all transactions for a bot immediately."""
    agent_id = params.get("agent_id", "").strip()
    if not agent_id:
        return {"error": "agent_id is required"}

    policies = (_remote("/policies/") if USE_REMOTE
                else storage.load_policies())

    if isinstance(policies, dict) and "error" in policies:
        return policies

    policy = next((p for p in policies if p["agent_id"] == agent_id), None)
    if not policy:
        return {"error": f"No policy found for agent: {agent_id}"}

    if USE_REMOTE:
        result = _remote(f"/policies/{policy['id']}", "PATCH", {"active": False})
    else:
        policy["active"] = False
        storage.update_policy(policy["id"], policy)
        result = policy

    return {"success": True, "agent_id": agent_id,
            "message": f"Bot '{agent_id}' KILLED — all transactions blocked."}


# ── MCP Tools manifest ──────────────────────────────────────────────────────

TOOLS = {
    "guard_check":    tool_guard_check,
    "guard_stats":    tool_guard_stats,
    "guard_register": tool_guard_register,
    "guard_kill":     tool_guard_kill,
}

TOOL_LIST = [
    {
        "name": "guard_check",
        "description": "Check if an x402 payment is allowed. Call BEFORE every payment. Returns approve/soft_alert/block.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Bot/agent ID"},
                "amount":   {"type": "number", "description": "Payment amount in USD"},
                "pay_to":   {"type": "string", "description": "Recipient address or domain"},
                "network":  {"type": "string", "description": "Network ID (default: X Layer testnet)"},
                "asset":    {"type": "string", "description": "Token contract address"},
            },
            "required": ["agent_id", "amount", "pay_to"],
        },
    },
    {
        "name": "guard_stats",
        "description": "Get spending stats and remaining budget for a bot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Bot/agent ID"},
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "guard_register",
        "description": "Register a new bot or OKX Agentic Wallet sub-wallet with spending limits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id":       {"type": "string", "description": "Unique bot ID"},
                "name":           {"type": "string", "description": "Bot display name"},
                "wallet_address": {"type": "string", "description": "OKX Agentic Wallet EVM address"},
                "bot_type":       {"type": "string", "description": "sniper/arbitrage/prediction/sentiment/custom"},
                "daily_limit":    {"type": "number", "description": "Max USD per day"},
                "per_tx_limit":   {"type": "number", "description": "Max USD per transaction"},
            },
            "required": ["agent_id", "name", "daily_limit", "per_tx_limit"],
        },
    },
    {
        "name": "guard_kill",
        "description": "Emergency kill switch — immediately block all payments for a bot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Bot ID to kill"},
            },
            "required": ["agent_id"],
        },
    },
]

# ── JSON-RPC dispatch ───────────────────────────────────────────────────────

def handle_request(req: dict) -> dict:
    rid    = req.get("id")
    method = req.get("method", "")
    params = req.get("params", {})

    # MCP standard methods
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "x402-guard", "version": "1.0.0"},
        }}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOL_LIST}}

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        handler   = TOOLS.get(tool_name)
        if not handler:
            return {"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32601, "message": f"Unknown tool: {tool_name}",
            }}
        try:
            result = handler(tool_args)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            }}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32603, "message": str(e),
            }}

    # Legacy direct method calls (backward compat)
    if method in TOOLS:
        try:
            result = TOOLS[method](params)
            return {"jsonrpc": "2.0", "id": rid, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32603, "message": str(e),
            }}

    return {"jsonrpc": "2.0", "id": rid, "error": {
        "code": -32601, "message": f"Method not found: {method}",
    }}


# ── Main loop ───────────────────────────────────────────────────────────────

def main():
    mode = "remote" if USE_REMOTE else "local"
    logger.warning(f"x402 Guard MCP Server starting ({mode} mode)")
    if USE_REMOTE:
        logger.warning(f"Guard API: {GUARD_URL}")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req  = json.loads(line)
            resp = handle_request(req)
        except json.JSONDecodeError as e:
            resp = {"jsonrpc": "2.0", "id": None, "error": {
                "code": -32700, "message": f"Parse error: {e}",
            }}
        print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    main()
