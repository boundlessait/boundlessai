---
name: genesis
version: 0.1.0
description: "AI-powered Uniswap V4 Hook strategy engine for X Layer. Autonomously generates, deploys, and manages composable Hook strategies with dynamic fees, MEV protection, and auto-rebalancing."
author: "Genesis Protocol"
tags:
  - defi
  - uniswap-v4
  - hooks
  - x-layer
  - strategy
  - nft
  - x402
dependencies:
  - onchainos-wallet
  - onchainos-trade
  - onchainos-market
  - onchainos-payment
  - uniswap-hooks
  - uniswap-trading
  - pay-with-any-token
---

# Genesis Protocol

## Overview

Genesis is an AI Skill that creates, deploys, and autonomously manages composable Uniswap V4 Hook strategies on X Layer. It combines on-chain Solidity modules with an off-chain Python cognitive engine to deliver institutional-grade DeFi strategy management through natural language commands.

**Core capabilities:**

- **Hook Template Engine** -- A modular assembly system with three plug-and-play Solidity modules (`DynamicFeeModule`, `MEVProtectionModule`, `AutoRebalanceModule`) that can be composed into custom Hook configurations via the `GenesisHookAssembler` contract.
- **5-Layer Cognitive Architecture** -- An AI decision pipeline (Perception, Analysis, Planning, Evolution, Meta-Cognition) that continuously monitors markets, selects optimal strategies, and self-improves over time.
- **Strategy NFTs** -- Proven strategies that meet performance thresholds are minted as on-chain NFTs with full parameter metadata, making them tradeable and composable.
- **x402 Payment Monetization** -- A revenue layer that lets external agents and users purchase signal queries, strategy subscriptions, parameter sets, and NFT licenses using the x402 payment protocol.

## Architecture

Genesis operates across two layers that coordinate through a shared decision journal.

### On-Chain Layer (Solidity)

| Contract | Purpose |
|---|---|
| `GenesisHookAssembler` | Factory contract that composes Hook modules into deployable Uniswap V4 Hooks. Registers module combinations and manages strategy lifecycle. |
| `DynamicFeeModule` | Adjusts swap fees in real-time based on volatility regime. Fee range: 0.05% to 1.00%, with configurable sensitivity and volatility thresholds. |
| `MEVProtectionModule` | Detects sandwich attacks by tracking per-block swap counts and directional volume. Applies penalty fees or blocks suspicious transactions. |
| `AutoRebalanceModule` | Monitors position boundaries and triggers rebalance when price drifts toward range edges. Supports IMMEDIATE, TWAP, and THRESHOLD_ACCUMULATE strategies. Enforces impermanent loss thresholds. |
| `StrategyNFT` | ERC-721 contract that mints NFTs for strategies meeting performance criteria. Stores full strategy parameters and performance history as on-chain metadata. |

### Off-Chain Layer (Python Agent Scripts)

| Script | Purpose |
|---|---|
| `genesis_engine.py` | Main orchestrator. Runs the 5-layer cognitive loop, coordinates all other scripts, and manages the strategy lifecycle. |
| `market_oracle.py` | Fetches and processes market data via `onchainos-market`. Calculates volatility, detects trends, and produces market regime classifications. |
| `hook_assembler.py` | Python interface to the `GenesisHookAssembler` contract. Handles deployment, module registration, and strategy creation transactions. |
| `strategy_manager.py` | Manages active strategies: monitors P&L, triggers rebalances, adjusts fee parameters, and handles deactivation logic. |
| `wallet_manager.py` | Manages the agentic wallet hierarchy (master, strategy, income, reserve, rebalance) via `onchainos-wallet`. |
| `decision_journal.py` | Records every AI decision both on-chain (via `DecisionJournal` contract) and locally. Supports 9 decision types from strategy creation to meta-cognition. |
| `nft_minter.py` | Evaluates strategy eligibility against NFT minting thresholds and mints `StrategyNFT` tokens for qualifying strategies. |
| `payment_handler.py` | Processes x402 payments with automatic token swap via `pay-with-any-token` Uniswap skill. Accepts any ERC-20 token and auto-swaps to USDT before settlement. |
| `config.py` | Central configuration file. All tunable parameters, safety defaults, chain settings, pricing tiers, and contract addresses. |

### Interaction Flow

1. `market_oracle.py` feeds market data into the Perception layer.
2. `genesis_engine.py` runs Analysis and Planning to select or adjust strategies.
3. `hook_assembler.py` deploys composed Hook contracts via `GenesisHookAssembler`.
4. `strategy_manager.py` monitors active strategies and triggers on-chain module calls.
5. `decision_journal.py` logs every action for Evolution and Meta-Cognition review.
6. `nft_minter.py` checks mature strategies and mints NFTs when thresholds are met.

## Quick Start

Follow these steps in order to initialize and launch Genesis.

### Step 1: Initialize Wallets

```
run scripts/wallet_manager.py init
```

This creates the 5-wallet hierarchy (master, strategy, income, reserve, rebalance) using `onchainos-wallet`. Each wallet has a dedicated purpose to isolate funds and permissions.

### Step 2: Deploy Contracts

```
run scripts/hook_assembler.py deploy-all
```

Deploys all Solidity contracts to X Layer (chain ID 196):
- `GenesisHookAssembler` -- the main factory
- `DynamicFeeModule`, `MEVProtectionModule`, `AutoRebalanceModule` -- the three Hook modules
- `StrategyNFT` -- the NFT contract for proven strategies

Contract addresses are automatically written to `config.py` under `CONTRACTS`.

### Step 3: Start the Engine

```
run scripts/genesis_engine.py start
```

Launches the autonomous cognitive loop. The engine starts in **safe mode** by default:
- `PAUSED = True` -- engine initializes but does not execute trades
- `MODE = "paper"` -- all strategies run in paper trading mode
- `DRY_RUN = True` -- all on-chain calls are simulated

To enable live operation, explicitly update the configuration:

```
genesis config set PAUSED False
genesis config set MODE live
genesis config set DRY_RUN False
```

## Commands

All commands are prefixed with `genesis`. The agent can invoke these at any time after initialization.

| Command | Description |
|---|---|
| `genesis start` | Start the autonomous strategy engine. Begins the Perception-Analysis-Planning loop at the configured intervals (perception: 60s, analysis: 300s, evolution: 24h). |
| `genesis stop` | Stop the engine gracefully. Completes any in-flight transactions, saves state, and logs a shutdown decision to the journal. |
| `genesis status` | Display current engine state, number of active strategies, aggregate P&L, wallet balances, and module health. |
| `genesis deploy` | Deploy all Genesis contracts to X Layer. Equivalent to `run scripts/hook_assembler.py deploy-all`. |
| `genesis create-strategy [preset]` | Manually create a strategy using a named preset. Valid presets: `calm_accumulator`, `volatile_defender`, `trend_rider`. The engine normally selects presets autonomously, but this command allows manual override. |
| `genesis rebalance [strategy_id]` | Force an immediate rebalance on the specified strategy, bypassing the cooldown period. Useful when market conditions shift rapidly. |
| `genesis deactivate [strategy_id]` | Deactivate a strategy. Withdraws liquidity, closes positions, and logs a `STRATEGY_DEACTIVATE` decision. The strategy remains on-chain for historical reference. |
| `genesis mint-nft [strategy_id]` | Check whether the strategy meets NFT minting thresholds (minimum +1% P&L, 50 swaps processed, 48h runtime) and mint a `StrategyNFT` if eligible. |
| `genesis journal [strategy_id]` | View the decision journal for a strategy. Shows all logged decisions with timestamps, types, confidence scores, and outcomes. |
| `genesis market` | Run a full market analysis and display the current regime classification, volatility metrics, trend direction, and recommended preset. |
| `genesis config set [key] [value]` | Update a runtime configuration parameter. Changes take effect immediately. Critical parameters: `PAUSED`, `MODE`, `DRY_RUN`, `CONFIDENCE_THRESHOLD`, `MAX_POSITION_SIZE_PCT`. |
| `genesis x402 pricing` | Display x402 payment tiers: signal queries (0.001 USDT), strategy subscriptions (0.01 USDT), parameter purchases (1.00 USDT), NFT licensing (5.00 USDT). |
| `genesis x402 pay [product] [token] [payer]` | Process an x402 payment using any ERC-20 token. Automatically swaps to USDT via `pay-with-any-token` Uniswap skill if the payer's token is not USDT. Products: `signal_query`, `strategy_subscribe`, `strategy_params_buy`, `nft_license`. |

## Strategy Presets

The AI engine selects presets based on real-time market analysis. Each preset defines which modules to activate, parameter overrides, and the market conditions under which it performs best.

### `calm_accumulator`

**Purpose:** Maximize trading volume in low-volatility, sideways markets.

- **Modules:** `DynamicFeeModule` + `AutoRebalanceModule`
- **Fee range:** 0.01% - 0.30% (low fees attract volume)
- **Fee sensitivity:** 0.8x (damped response to minor vol fluctuations)
- **Rebalance trigger:** 90% toward boundary (tight range, less frequent rebalance)
- **IL threshold:** 1.50% (tighter IL tolerance in calm conditions)
- **Market conditions:** Volatility 0-3%, sideways trend
- **No MEV protection** -- low volatility environments have minimal sandwich risk.

### `volatile_defender`

**Purpose:** Protect LP capital during high-volatility events.

- **Modules:** `DynamicFeeModule` + `MEVProtectionModule` + `AutoRebalanceModule`
- **Fee range:** 0.10% - 1.50% (high fees compensate for IL risk)
- **Fee sensitivity:** 1.2x (aggressive response to vol spikes)
- **MEV protection:** Active with blocking enabled (suspicious swaps are rejected, not just penalized)
- **Rebalance trigger:** 70% toward boundary (early rebalance to stay in range)
- **Cooldown:** 120s (faster rebalance cadence)
- **Market conditions:** Volatility 5%+, any trend direction

### `trend_rider`

**Purpose:** Capture directional moves with wider ranges and gradual rebalancing.

- **Modules:** `DynamicFeeModule` + `MEVProtectionModule` + `AutoRebalanceModule`
- **Fee sensitivity:** 0.9x (slightly damped to avoid over-adjusting in trends)
- **Rebalance strategy:** TWAP (time-weighted rebalance to reduce market impact)
- **Rebalance trigger:** 75% toward boundary
- **Market conditions:** Volatility 2-6%, trending market

## Module System

Genesis uses a composable module architecture. The `GenesisHookAssembler` contract accepts any combination of the three modules and produces a deployable Uniswap V4 Hook.

### DynamicFeeModule

Adjusts swap fees in real-time based on the current volatility regime.

- **Base fee:** 0.30% (3000 hundredths of bip)
- **Range:** 0.05% (min) to 1.00% (max)
- **Sensitivity:** 1.0x multiplier (PRECISION = 10000)
- **Volatility thresholds:** Low regime below 2%, high regime above 8%
- **Mechanism:** The module reads a volatility feed and scales the fee linearly between `min_fee` and `max_fee`. In low-vol regimes, fees drop to attract volume. In high-vol regimes, fees increase to compensate LPs for impermanent loss risk.

### MEVProtectionModule

Detects and mitigates sandwich attacks at the Hook level.

- **Swap count threshold:** Maximum 3 same-direction swaps per block
- **Volume threshold:** Maximum 10,000 token units per direction per block
- **Penalty fee:** 0.50% surcharge applied to suspicious swaps
- **Blocking mode:** When `block_suspicious = True`, suspicious swaps are reverted instead of penalized
- **Mechanism:** Tracks per-block swap counts and directional volume. When thresholds are exceeded, the module flags the transaction as suspicious and applies the configured penalty or revert.

### AutoRebalanceModule

Manages liquidity positions by monitoring price drift and triggering rebalance operations.

- **Soft trigger:** 85% -- signals rebalance when price reaches 85% of the distance to a range boundary
- **IL threshold:** 2.00% (200 bps) -- forces rebalance when impermanent loss exceeds this level regardless of position
- **Cooldown:** 300 seconds (5 minutes) between rebalance signals
- **Rebalance strategies:**
  - `IMMEDIATE` (0) -- Execute rebalance in a single transaction
  - `TWAP` (1) -- Split rebalance across multiple blocks to reduce market impact
  - `THRESHOLD_ACCUMULATE` (2) -- Accumulate rebalance signals and execute in batch when a threshold is reached

## AI Cognitive Layers

The Genesis engine operates a 5-layer cognitive architecture that runs continuously at different intervals.

### Layer 1: Perception (every 60 seconds)

Collects raw market data via `onchainos-market` and on-chain state. Outputs:
- Current price, 24h volume, and order book depth for configured pairs (ETH/USDC, OKB/USDT on X Layer)
- On-chain pool metrics: TVL, fee revenue, swap count, tick distribution
- Active strategy positions: current tick, range boundaries, accrued fees

### Layer 2: Analysis (every 300 seconds)

Processes perception data into actionable signals:
- **Volatility calculation:** Rolling standard deviation over a 24-hour window, classified into low/medium/high regimes
- **Trend detection:** 72-hour lookback using price momentum and volume-weighted direction
- **Market regime classification:** Maps current conditions to the nearest strategy preset
- **Confidence scoring:** Each signal carries a confidence score (0.0 to 1.0). Only signals above the `CONFIDENCE_THRESHOLD` (default: 0.7) trigger action.

### Layer 3: Planning (on signal)

Translates analysis signals into executable actions:
- Select or switch strategy presets based on regime classification
- Calculate optimal module parameters (fee ranges, rebalance triggers, MEV thresholds)
- Size positions using the `MAX_POSITION_SIZE_PCT` constraint (default: 30% of wallet)
- Route execution through the appropriate wallet (strategy wallet for deployments, rebalance wallet for adjustments)

### Layer 4: Evolution (every 24 hours)

Reviews historical performance and adjusts engine behavior:
- Compares predicted outcomes against actual P&L for each strategy
- Identifies parameter drift: which overrides consistently outperform defaults
- Adjusts confidence thresholds and sensitivity multipliers based on hit rate
- Flags underperforming strategies for deactivation review

### Layer 5: Meta-Cognition (every 24 hours, after Evolution)

Self-reflective layer that evaluates the decision-making process itself:
- Analyzes the decision journal for systematic biases (e.g., over-trading in low-vol, slow response to vol spikes)
- Measures decision latency: time from signal detection to execution
- Evaluates wallet allocation efficiency across the 5-wallet hierarchy
- Produces a meta-cognition report logged as decision type `META_COGNITION` (0x08)

## Strategy NFT

Proven strategies can be minted as ERC-721 NFTs on the `StrategyNFT` contract. This creates a tradeable, on-chain representation of a successful Hook configuration.

### Minting Thresholds

A strategy must meet **all three** criteria:

| Criterion | Threshold | Rationale |
|---|---|---|
| P&L performance | +1.00% (100 bps) | Strategy must be net profitable |
| Swaps processed | 50 minimum | Strategy must have meaningful usage |
| Runtime | 48 hours minimum | Strategy must demonstrate sustained performance |

### NFT Metadata

Each minted NFT stores the following on-chain:
- **Strategy ID** and creation timestamp
- **Module composition** (which modules were active)
- **Parameter snapshot** (all module parameters at time of mint)
- **Performance metrics** (P&L, total swaps, fee revenue, IL incurred)
- **Market regime** at time of deployment

### Usage

```
genesis mint-nft [strategy_id]
```

The command checks eligibility, and if all thresholds are met, mints the NFT to the income wallet. NFTs can be traded on any X Layer NFT marketplace or licensed via the x402 payment layer.

## x402 Payment Integration

Genesis monetizes its intelligence through the x402 payment protocol, allowing external agents and users to purchase access to strategy data.

### Payment Tiers

| Product | Price | Token | Settlement | Description |
|---|---|---|---|---|
| Signal Query | 0.001 USDT | USDT | Async | One-time query for current market signal and recommended action |
| Strategy Subscribe | 0.01 USDT | USDT | Async | Subscribe to real-time strategy updates and parameter changes |
| Strategy Params Buy | 1.00 USDT | USDT | Sync | Purchase the full parameter set of a specific strategy for replication |
| NFT License | 5.00 USDT | USDT | Sync | License a Strategy NFT's parameters for deployment on another pool |

### Revenue Flow

All x402 payments are received by the **income wallet** (wallet index 2). The `onchainos-payment` dependency handles payment verification and settlement. Revenue is tracked in the decision journal under decision type `FUND_TRANSFER` (0x05).

### Pay with Any Token

Genesis integrates the `pay-with-any-token` Uniswap skill to accept payments in any ERC-20 token. When a payer uses a non-USDT token:

1. The `PaymentHandler` calls `pay-with-any-token` with `exactOutput` to determine the required input amount
2. The skill routes through Uniswap V4 to swap the payer's token to USDT
3. The exact USDT amount is delivered to the income wallet
4. The x402 payment is settled normally

This removes friction for agents and users who hold OKB, ETH, USDC, or any other X Layer token — they can pay for Genesis services without manually acquiring USDT first.

```
genesis x402 pay signal_query OKB 0xPayerAddress
genesis x402 pay strategy_subscribe ETH 0xPayerAddress
```

### Configuration

x402 is enabled by default (`X402_ENABLED = True`). To view current pricing:

```
genesis x402 pricing
```

To disable x402 payments:

```
genesis config set X402_ENABLED False
```

## Safety

Genesis ships with conservative safety defaults that prevent accidental fund loss. **All three safety flags must be explicitly disabled before the engine will execute real transactions.**

### Default Configuration

```python
PAUSED = True       # Engine initializes but does not act
MODE = "paper"      # All strategies run in paper trading simulation
DRY_RUN = True      # All on-chain calls are simulated, no transactions broadcast
```

### Enabling Live Mode

Each flag must be set independently. This is intentional -- it requires three deliberate actions:

```
genesis config set PAUSED False
genesis config set MODE live
genesis config set DRY_RUN False
```

### Additional Safety Constraints

- **Position sizing:** No single strategy can exceed 30% of wallet funds (`MAX_POSITION_SIZE_PCT = 30`)
- **Confidence gating:** The engine only acts on signals with confidence above 0.7 (`CONFIDENCE_THRESHOLD = 0.7`)
- **Wallet isolation:** Five separate wallets isolate funds by purpose. The reserve wallet (index 3) is never used for strategy operations.
- **Decision logging:** Every action is recorded on-chain and locally. The journal provides a full audit trail for all engine decisions.
- **Cooldown enforcement:** Rebalance operations enforce a minimum 300-second cooldown to prevent rapid-fire transactions.
- **Slippage protection:** DEX operations enforce a 0.5% maximum slippage (`DEX_SLIPPAGE_BPS = 50`).

## X Layer Optimization

Genesis is purpose-built for OKX X Layer (chain ID 196), taking advantage of its unique properties for high-frequency DeFi operations.

### Zero Gas Fees

X Layer offers zero gas fees for transactions using USDG and USDT. Genesis leverages this by:
- Routing all strategy operations through zero-gas token paths
- Enabling frequent rebalance and fee adjustment calls without cost concerns
- Making the decision journal economically viable for on-chain logging of every action

### Low-Cost Execution

For non-zero-gas operations, X Layer transaction costs average approximately $0.0005 per transaction. This enables:
- High-frequency parameter adjustments that would be prohibitively expensive on Ethereum mainnet
- Aggressive rebalance strategies (120s cooldown in `volatile_defender`) without cost drag on P&L
- On-chain NFT minting and metadata storage at negligible cost

### Fast Finality

X Layer's 1-second block time provides:
- Near-instant strategy deployment and module composition
- Real-time MEV protection with per-block swap tracking
- Responsive rebalance execution that keeps pace with rapid market moves
- Low-latency x402 payment settlement

### DEX Integration

Genesis compares Hook pool performance against DEX aggregator pricing (`DEX_COMPARE_WITH_HOOK = True`), ensuring strategies always route through the most efficient venue. The `onchainos-trade` dependency provides access to X Layer DEX liquidity for rebalance operations.
