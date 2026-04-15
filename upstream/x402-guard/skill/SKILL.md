# x402 Guard — Onchain OS Skill

AI Agent Spending Policy Co-Pilot for x402 payments on X Layer (eip155:196).

x402 Guard intercepts every HTTP 402 Payment Required response before your agent signs
anything on-chain. It enforces daily / hourly / per-transaction limits, maintains
blacklists and whitelists, and emits real-time alerts when budgets run low.

---

## Quick Start: MCP Server Setup

x402 Guard runs as an MCP (Model Context Protocol) server so any Onchain OS agent
can call the guard tools directly from its reasoning loop.

### 1. Install

```bash
cd ~/x402-guard
pip install -r backend/requirements.txt   # pydantic, fastapi (for models/storage)
```

### 2. Configure .mcp.json

Add x402 Guard to your Onchain OS agent's `.mcp.json`:

```json
{
  "mcpServers": {
    "x402-guard": {
      "command": "python3",
      "args": ["/path/to/x402-guard/mcp_server.py"],
      "description": "x402 Guard - AI Agent Spending Policy Co-Pilot",
      "env": {
        "X402_DATA_DIR": "/path/to/x402-guard/backend/data"
      }
    }
  }
}
```

A pre-configured `.mcp.json` is included at the project root:
```
~/x402-guard/.mcp.json
```

### 3. Start the MCP server (standalone test)

```bash
# Test that the server starts and responds correctly
echo '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}' | python3 mcp_server.py

# List available tools
echo '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":2}' | python3 mcp_server.py
```

---

## How to use with Onchain OS

### Set a spending policy for your agent

```bash
# Via the guard API (when FastAPI backend is running)
curl -X POST http://localhost:4402/policies \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-trading-agent",
    "name": "Conservative Policy",
    "daily_limit": 50.0,
    "hourly_limit": 10.0,
    "per_tx_limit": 5.0,
    "auto_approve_under": 0.01
  }'

# Or via MCP tool call:
echo '{
  "jsonrpc":"2.0",
  "method":"tools/call",
  "params":{
    "name":"guard_set_policy",
    "arguments":{
      "agent_id":"my-trading-agent",
      "daily_limit":50.0,
      "hourly_limit":10.0,
      "per_tx_limit":5.0
    }
  },
  "id":1
}' | python3 mcp_server.py
```

### Check a payment before signing

```bash
echo '{
  "jsonrpc":"2.0",
  "method":"tools/call",
  "params":{
    "name":"guard_check",
    "arguments":{
      "agent_id":"my-trading-agent",
      "network":"eip155:196",
      "amount":2.50,
      "asset":"0x4ae46a509f6b1d9056937ba4500cb143933d2dc8",
      "pay_to":"0xRecipientAddress"
    }
  },
  "id":1
}' | python3 mcp_server.py
```

### Make an x402 payment (the full onchainos flow)

After the guard approves, use `onchainos payment x402-pay` to sign and send:

```bash
# Full x402 payment command
onchainos payment x402-pay \
  --network eip155:196 \
  --amount 1000000 \
  --pay-to 0xRecipientAddress \
  --asset 0x4ae46a509f6b1d9056937ba4500cb143933d2dc8 \
  --json

# Output (example):
# {
#   "signature": "0xabc123...",
#   "authorization": "eyJ...",
#   "transaction_hash": "0xdef456...",
#   "from": "0xYourWalletAddress"
# }
```

### Get spending stats

```bash
# Via CLI
onchainos agent stats --agent-id my-trading-agent

# Via guard API
curl http://localhost:4402/guard/stats/my-trading-agent

# Via MCP
echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"guard_get_stats","arguments":{"agent_id":"my-trading-agent"}},"id":1}' \
  | python3 mcp_server.py
```

---

## Complete x402 Flow

```
Agent code
    │
    ├─ fetchWithGuard("https://api.example.com/data", "agent-001")
    │
    ▼
HTTP GET /data
    │
    ◄── HTTP 402 Payment Required ──────────────────────────────────────
    │   Body: base64({ network, amount, payTo, asset, scheme, resource })
    │
    ▼
parseX402Response()        ← decode base64, extract payment requirements
    │
    ▼
callGuard(agentId, paymentDetails)
    │   POST /guard/check
    │   ◄── { allowed: true, action: "approve", remaining_daily: 47.5 }
    │
    ├── action == "block"  → throw Error("Daily limit exceeded"), STOP
    ├── action == "soft_alert" → warn, continue
    └── action == "approve"  → continue
    │
    ▼
signWithOnchainos(paymentDetails)
    │   runs: onchainos payment x402-pay \
    │           --network eip155:196 \
    │           --amount 1000000 \
    │           --pay-to 0x... \
    │           --asset 0x... \
    │           --json
    │   ◄── { signature: "0x...", authorization: "eyJ..." }
    │
    ▼
assemblePaymentHeader(decoded, signature, authorization)
    │   → X-PAYMENT-SIGNATURE: base64({ ...requirements, signature, authorization })
    │
    ▼
HTTP GET /data
    Headers: X-PAYMENT-SIGNATURE: ...
    │
    ◄── HTTP 200 OK + response data
    │
    ▼
return response to agent
```

---

## MCP Tools Reference

### guard_check

Check whether a payment is allowed before signing.

**Input:**
```json
{
  "agent_id": "string",      // required
  "network": "eip155:196",   // CAIP-2 chain ID
  "amount": 2.50,            // payment amount
  "asset": "0x...",          // token contract address
  "pay_to": "0x...",         // recipient address
  "domain": "api.example.com" // optional, for logging
}
```

**Output:**
```json
{
  "allowed": true,
  "action": "approve",          // "approve" | "soft_alert" | "block"
  "reason": "Transaction approved within all policy limits.",
  "remaining_daily": 47.50,
  "remaining_hourly": 7.50,
  "policy_id": "uuid",
  "transaction_id": "uuid"
}
```

### guard_set_policy

Create or update a spending policy for an agent.

**Input:**
```json
{
  "agent_id": "string",
  "daily_limit": 100.0,
  "hourly_limit": 20.0,
  "per_tx_limit": 10.0,
  "name": "My Policy",
  "auto_approve_under": 0.01
}
```

### guard_get_stats

Get current spending statistics.

**Input:** `{"agent_id": "string"}`

**Output:**
```json
{
  "agent_id": "string",
  "daily_spent": 2.50,
  "hourly_spent": 2.50,
  "daily_limit": 100.0,
  "remaining_daily": 97.50,
  "total_transactions": 5,
  "blocked_transactions": 0,
  "approved_transactions": 5
}
```

### guard_get_alerts

Get recent blocked or soft-alert transactions.

**Input:** `{"agent_id": "string", "limit": 20}`

**Output:**
```json
{
  "agent_id": "string",
  "count": 2,
  "alerts": [
    {
      "id": "uuid",
      "amount": 150.0,
      "status": "blocked",
      "reason": "Daily spending limit exceeded",
      "timestamp": "2025-01-01T12:00:00Z"
    }
  ]
}
```

---

## Integration Example

See `skill/integration-example.js` for the full working JavaScript implementation
of `fetchWithGuard()` — a drop-in replacement for `fetch()` that handles the entire
x402 flow including guard checks and onchainos signing.

```bash
# Run the demo (requires guard API at localhost:4402)
cd skill
node integration-example.js
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Onchain OS Agent                         │
│                                                             │
│   fetchWithGuard(url, agentId)                              │
│         │                                                   │
│         └─ calls guard_check via MCP or HTTP API           │
└─────────────────────────────────────────────────────────────┘
                          │
         ┌────────────────▼────────────────┐
         │         x402 Guard              │
         │                                 │
         │  ┌─────────────────────────┐   │
         │  │     PolicyEngine        │   │
         │  │  - daily_limit check    │   │
         │  │  - hourly_limit check   │   │
         │  │  - per_tx_limit check   │   │
         │  │  - blacklist/whitelist  │   │
         │  │  - soft_alert tiers     │   │
         │  └─────────────────────────┘   │
         │                                 │
         │  ┌─────────────────────────┐   │
         │  │     MCP Server          │   │
         │  │  (mcp_server.py)        │   │
         │  │  stdio JSON-RPC         │   │
         │  └─────────────────────────┘   │
         │                                 │
         │  ┌─────────────────────────┐   │
         │  │     FastAPI Backend     │   │
         │  │  POST /guard/check      │   │
         │  │  GET  /guard/stats/:id  │   │
         │  │  WS   /ws               │   │
         │  └─────────────────────────┘   │
         └─────────────────────────────────┘
                          │
         ┌────────────────▼────────────────┐
         │      onchainos payment          │
         │      x402-pay --json            │
         │   (signs only after approval)   │
         └─────────────────────────────────┘
                          │
         ┌────────────────▼────────────────┐
         │         X Layer (eip155:196)    │
         │         on-chain payment        │
         └─────────────────────────────────┘
```

---

## Running the Full Stack

```bash
# Start guard backend
cd ~/x402-guard
uvicorn backend.main:app --reload --port 4402

# Start frontend dashboard (optional)
cd frontend && npm run dev

# Or use Docker Compose
docker-compose up
```

The guard dashboard will be at http://localhost:3000 — watch policy decisions
in real time via WebSocket.
