---
name: leigent-portfolio-agent
version: 1.0.0
description: "Autonomous DeFi portfolio builder for X Layer — natural language-driven AI agent that manages portfolio goals, monitors on-chain positions, executes intelligent swaps via OnchainOS DEX, and auto-rebalances. Use when user mentions portfolio management, DeFi investing, token allocation, rebalancing, yield strategies, or managing crypto holdings on X Layer."
license: MIT
author: Leigent
homepage: https://github.com/leigent/leigent-portfolio-agent
tags: [defi, portfolio, xlayer, onchainos, autonomous, trading, rebalancing, yield]
platform: openclaw
---

# Leigent Portfolio Agent Skill

An autonomous DeFi portfolio manager that understands natural language financial goals, monitors on-chain positions via OnchainOS, executes intelligent swaps on X Layer DEX, and auto-rebalances portfolio allocations.

## Pre-flight Checks

### 1. Verify OnchainOS CLI

```bash
~/.local/bin/onchainos --version
```

If not installed:
```bash
curl -fsSL https://raw.githubusercontent.com/okx/onchainos-skills/main/install.sh | sh
```

### 2. Verify API credentials

Check `~/.config/onchainos.env` contains:
```
OKX_API_KEY=your_api_key
OKX_SECRET_KEY=your_secret_key
OKX_PASSPHRASE=your_passphrase
```

### 3. Verify wallet

```bash
~/.local/bin/onchainos wallet addresses --chain 196
```

---

## Commands

### Portfolio Status — "What's my portfolio worth?"

```bash
~/.local/bin/onchainos wallet balance --chain 196
~/.local/bin/onchainos defi positions --address 0xWALLET --chains 196
```

**When to use:** User asks about portfolio value, holdings, or asset breakdown.

---

### Natural Language Intent Classification

The agent brain maps natural language to portfolio actions:

| User says... | Intent | Action |
|---|---|---|
| "What's my portfolio worth?" | status | Show balances + DeFi positions |
| "I want stable income" | goal_income | Suggest USDC/USDT/OKB yield strategy |
| "Grow my portfolio" | goal_growth | Suggest OKB/ETH aggressive strategy |
| "Keep it safe" | goal_safety | Suggest 100% stablecoin strategy |
| "Swap 10 USDC to OKB" | swap | Execute DEX swap via OnchainOS |
| "Rebalance to 60% OKB" | rebalance | Auto-correct allocation drift |
| "Is OKB better than USDC?" | question | Answer comparative question |

---

### Strategy Recommendations

#### Stable Income Strategy (Risk: Low, ~3-8% APY)
```
Allocation: 50% USDC + 30% USDT + 20% OKB
Execute: Swap excess → USDC/USDT, stake OKB for validator yield
```

#### Balanced Growth Strategy (Risk: Medium, ~8-20% APY)
```
Allocation: 30% USDC + 40% OKB + 20% ETH + 10% USDT
Execute: Gradual position building via DCA swaps
```

#### Aggressive Growth Strategy (Risk: High, ~20-100%+ APY)
```
Allocation: 60% OKB + 20% ETH + 20% USDC (war chest)
Execute: Max OKB position, monitor for rebalancing opportunities
```

---

### Swap Execution

#### Step 1: Get Quote

```bash
~/.local/bin/onchainos swap quote \
  --from 0x74b7f16337b8972027f6196a17a631ac6de26d22 \
  --to 0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee \
  --amount 1000000 \
  --chain 196
```

#### Step 2: Execute

```bash
~/.local/bin/onchainos swap execute \
  --from 0x74b7f16337b8972027f6196a17a631ac6de26d22 \
  --to 0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee \
  --amount 1000000 \
  --chain 196 \
  --wallet default \
  --slippage 0.5
```

---

### Auto-Rebalancing

Run the agent in autonomous mode:

```javascript
const { LeigentPortfolioAgent } = require('./src/index');
const agent = new LeigentPortfolioAgent('0xWALLET_ADDRESS');
agent.runAutonomous(300000); // Check every 5 minutes
```

The agent:
1. Fetches current portfolio allocation
2. Detects assets drifting >5% from target
3. Executes corrective swaps (sell overweight, buy underweight)
4. Reports all actions

---

### Security Scanning

Before swapping into a new token:

```bash
~/.local/bin/onchainos security token-scan \
  --address 0xTOKEN_CONTRACT \
  --chain 196
```

---

## X Layer Token Addresses

| Token | Contract Address | decimals |
|-------|----------------|----------|
| USDC | `0x74b7f16337b8972027f6196a17a631ac6de26d22` | 6 |
| USDT | `0x779ded0c9e1022225f8e0630b35a9b54be713736` | 6 |
| WOKB | `0xe538905cf8410324e03a5a23c1c177a474d59b2b` | 18 |
| OKB (native) | `0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee` | 18 |
| XLAYER_USDT | `0x1e4a5963abfd975d8c9021ce480b42188849d41d` | 6 |

---

## Error Handling

| Error | Solution |
|-------|----------|
| `session expired` | Run `~/.local/bin/onchainos wallet login` |
| `Invalid token address` | Use full contract address, not symbol |
| `insufficient balance` | Fund wallet with target token |
| `slippage exceeded` | Retry with higher `--slippage` (e.g., 1.0) |
| `rate limited` | Wait 30s and retry |

---

## Skill Routing

- User mentions **portfolio, holdings, assets** → Show portfolio status
- User mentions **income, yield, stable** → Suggest income strategy
- User mentions **grow, increase, aggressive** → Suggest growth strategy
- User mentions **swap, exchange, convert** → Execute swap flow
- User mentions **rebalance, adjust** → Trigger rebalancing
- User mentions **safe, preserve, protect** → Suggest safety strategy
- User asks a **question** → Route to knowledge base or search
