# Leigent — Autonomous DeFi Portfolio Agent on X Layer

> Natural language-driven AI agent for intelligent DeFi portfolio management on X Layer. Built for the **OKX Build X Hackathon** — X Layer Arena.

## 🎯 What It Does

**Leigent** is an autonomous portfolio manager that speaks plain English:

```
You: "I want stable income"
Leigent: → Analyzes your current holdings
      → Recommends 50% USDC / 30% USDT / 20% OKB strategy (~3-8% APY)
      → Executes corrective swaps on X Layer DEX
      → Reports: "Swapped 0.5 ETH → 200 USDC. TxHash: 0xabc..."

You: "What's my portfolio worth?"
Leigent: → Fetches all wallet balances + DeFi positions
      → Shows: $1,234.56 total across USDC, OKB, USDT
      → Notes any staking rewards accruing

You: "Swap 10 USDC to OKB"
Leigent: → Gets best route via OnchainOS DEX aggregator (500+ sources)
      → Executes swap, reports tx hash + price impact
```

## 🏆 Hackathon Alignment

### X Layer Arena Scoring — How Leigent Scores

| Dimension | Weight | Leigent's Approach |
|-----------|--------|-------------------|
| **OnchainOS/Uniswap Integration** | 25% | ✅ swap quote/execute, wallet balance, defi positions, token search, **x402 payment**, **OKB staking** |
| **X Layer Ecosystem Fit** | 25% | ✅ OKB native gas, **x402 metered payments**, **OKB validator staking** (~5-10% APY), near-zero gas fees |
| **AI Interaction Experience** | 25% | ✅ **Multi-round conversation memory**, preference learning, natural language strategy matching, autonomous rebalancing |
| **Product Completeness** | 25% | ✅ Full end-to-end flows, real swap execution, tx reporting, autonomous monitoring loop |

### Special Prizes Leigent Targets
- 🏅 **Most Active On-Chain Agent** (400 USDT) — autonomous tx execution with tx counter
- 🏅 **Most Popular Repo** — active Moltbook + X engagement

## ✨ Features

### Natural Language Commands
| Command | What Happens |
|---------|-------------|
| `"What's my portfolio worth?"` | Fetches wallet balances + DeFi positions |
| `"I want stable income"` | Recommends USDC/USDT/OKB yield strategy |
| `"Swap 10 USDC to OKB"` | Executes best-route DEX swap |
| `"Rebalance to 60% OKB"` | Auto-corrects allocation drift |
| `"Stake my OKB"` | Shows OKB staking yield (~5-10% APY) |
| `"Pay for [API URL] via x402"` | Executes x402 HTTP 402 payment |
| `"I prefer low risk"` | Learns and adapts future recommendations |

### OnchainOS Integration
- **`swap quote` + `swap execute`** — DEX aggregation, 500+ liquidity sources, best-route routing
- **`wallet balance`** — token balance monitoring
- **`defi positions`** — cross-protocol DeFi position tracking
- **`token search`** — token address resolution
- **`security token-scan`** — pre-swap token safety verification
- **`staking`** — OKB validator staking (~5-10% APY)
- **`payment x402`** — metered API payments via HTTP 402

### X Layer Native Features
- **OKB** — Native gas token (~$0.0005/tx, 1s block time)
- **x402** — Metered payment protocol for API access
- **OKB Staking** — Validator rewards ~5-10% APY
- **DEX Aggregation** — CurveNG, QuickSwap V3, OkieStableSwap routing

### Autonomous Modes
- **Auto-rebalance**: Monitors every 5 min, corrects >5% drift
- **Transaction counter**: Tracks on-chain activity for "Most Active Agent" prize
- **Preference learning**: Remembers risk tolerance across sessions

## 🏗 Architecture

```
User input (plain English)
         │
         ▼
┌──────────────────────┐
│   Agent Brain         │ ← Intent classification + strategy engine
│  agent-brain.js       │   Multi-round memory, preference learning
│                       │   x402 + OKB staking awareness
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Portfolio Manager    │ ← Strategy execution + swap orchestration
│ portfolio-manager.js │   Rebalancing, staking, x402 payments
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  OnchainOS Client    │ ← CLI wrapper for all OnchainOS APIs
│ onchainos-client.js  │
└──────────┬───────────┘
           │
           ▼
    OnchainOS APIs → X Layer → On-chain execution
```

## 📁 Project Structure

```
leigent-portfolio-agent/
├── src/
│   ├── index.js              # Main agent + autonomous loop
│   ├── agent-brain.js        # NL understanding, strategies, memory
│   ├── portfolio-manager.js  # Positions, swaps, staking, x402
│   └── onchainos-client.js  # OnchainOS CLI wrapper
├── skills/
│   └── leigent-portfolio-skill/
│       └── SKILL.md          # OpenClaw skill file
├── scripts/
│   └── demo-swap.js          # Demo swap script
├── docs/
├── package.json
└── README.md
```

## 🔧 Quick Start

```bash
git clone https://github.com/leigents/leigent-portfolio-agent.git
cd leigent-portfolio-agent
npm install

# Configure (ensure ~/.config/onchainos.env has OKX_API_KEY etc.)
export WALLET_ADDRESS=0xYourXLayerAddress

# Run
node src/index.js
```

## 📊 X Layer Network

| Parameter | Value |
|-----------|-------|
| Chain ID | 196 |
| RPC | `https://rpc.xlayer.tech` |
| Explorer | `https://web3.okx.com/explorer/x-layer` |
| Gas token | OKB |
| Avg tx fee | ~$0.0005 |
| Block time | ~1s |

### X Layer Token Addresses

| Token | Contract | Decimals |
|-------|----------|----------|
| USDC | `0x74b7f16337b8972027f6196a17a631ac6de26d22` | 6 |
| USDT | `0x779ded0c9e1022225f8e0630b35a9b54be713736` | 6 |
| WOKB | `0xe538905cf8410324e03a5a23c1c177a474d59b2b` | 18 |
| OKB (native) | `0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee` | 18 |
| XLAYER_USDT | `0x1e4a5963abfd975d8c9021ce480b42188849d41d` | 6 |

## 🌐 Live Demo

**Agent:** Leigent (Moltbook: `@leigent`)
**Wallet:** `0xd1b3c96f1854791eb01f84c43b1bf4949264a75d` (X Layer)
**Repo:** https://github.com/leigents/leigent-portfolio-agent

## 📋 Submission

**Moltbook:** `m/buildx` — ProjectSubmission XLayerArena
**GitHub:** https://github.com/leigents/leigent-portfolio-agent
**Hackathon:** OKX Build X Hackathon 2026 | $14,000 USDT Prize Pool

## 📜 License

MIT
