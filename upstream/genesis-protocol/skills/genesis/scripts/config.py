"""
Genesis Configuration - All tunable parameters for the Genesis Protocol.

IMPORTANT SAFETY DEFAULTS:
- PAUSED = True  (must be explicitly enabled)
- MODE = "paper" (paper trading by default)
- DRY_RUN = True (simulate all on-chain operations)

These defaults are required by the OKX plugin-store guidelines.
"""

# ─── Safety Controls ──────────────────────────────────────────────────────
PAUSED = True
MODE = "paper"          # "paper" | "live"
DRY_RUN = True          # If True, simulate all contract calls
LOG_LEVEL = "INFO"      # "DEBUG" | "INFO" | "WARN" | "ERROR"

# ─── Chain Configuration (Mainnet-first) ─────────────────────────────────
CHAIN_ID = 196                          # X Layer mainnet (primary)
CHAIN_NAME = "xlayer"
RPC_URL = "https://rpc.xlayer.tech"
EXPLORER_URL = "https://www.oklink.com/xlayer"
ZERO_GAS_TOKENS = ["USDG", "USDT"]     # Zero gas fee tokens on X Layer

# Testnet fallback (Chain 1952) for development / dry-run testing
TESTNET_CHAIN_ID = 1952
TESTNET_RPC_URL = "https://xlayertestrpc.okx.com"
TESTNET_EXPLORER_URL = "https://www.oklink.com/xlayer-test"

# ─── Agentic Wallet Configuration ─────────────────────────────────────────
WALLET_ROLES = {
    "master":    {"index": 0, "purpose": "Main control wallet"},
    "strategy":  {"index": 1, "purpose": "Deploys and manages Hook strategies"},
    "income":    {"index": 2, "purpose": "Receives LP fees and x402 revenue"},
    "reserve":   {"index": 3, "purpose": "Emergency reserve fund"},
    "rebalance": {"index": 4, "purpose": "Executes rebalance operations"},
}
MAX_SUB_WALLETS = 5     # Start conservative, can expand to 50

# ─── Hook Template Engine ─────────────────────────────────────────────────
AVAILABLE_MODULES = {
    "dynamic_fee": {
        "contract": "DynamicFeeModule",
        "description": "Volatility-responsive dynamic fee adjustment",
        "default_params": {
            "base_fee": 3000,           # 0.30% in hundredths of bip
            "min_fee": 500,             # 0.05%
            "max_fee": 10000,           # 1.00%
            "sensitivity": 10000,       # 1.0x multiplier (PRECISION=10000)
            "low_threshold": 200,       # 2% vol = low regime
            "high_threshold": 800,      # 8% vol = high regime
        },
    },
    "mev_protection": {
        "contract": "MEVProtectionModule",
        "description": "Sandwich attack detection and mitigation",
        "default_params": {
            "swap_count_threshold": 3,   # max same-dir swaps per block
            "volume_threshold": 10000,   # max volume per direction per block (in token units)
            "penalty_fee": 5000,         # 0.50% penalty for suspicious swaps
            "block_suspicious": False,   # penalize rather than block
        },
    },
    "auto_rebalance": {
        "contract": "AutoRebalanceModule",
        "description": "Intelligent position range management with IL protection",
        "default_params": {
            "soft_trigger_pct": 85,      # trigger when 85% toward boundary
            "il_threshold_bps": 200,     # 2% max IL before forced rebalance
            "cooldown_period": 300,      # 5 min between signals
            "strategy": 0,              # 0=IMMEDIATE, 1=TWAP, 2=THRESHOLD_ACCUMULATE
        },
    },
    "liquidity_shield": {
        "contract": "LiquidityShieldModule",
        "description": "JIT liquidity protection - shield fee proportional to price impact",
        "default_params": {
            "max_impact_bps": 50,        # 0.50% max allowed impact before shield activates
            "shield_fee_multiplier": 15000,  # 1.5x multiplier (PRECISION=10000)
            "block_impact_cap": 500,     # 5% cumulative per-block impact cap
        },
    },
    "oracle": {
        "contract": "OracleModule",
        "description": "On-chain TWAP oracle with volatility estimation for fee optimization",
        "default_params": {
            "observation_window": 1800,  # 30 min TWAP window
            "max_observations": 120,     # ring buffer size
        },
    },
}

# ─── Strategy Presets (AI selects based on market analysis) ───────────────
STRATEGY_PRESETS = {
    "calm_accumulator": {
        "description": "Low volatility environment - maximize volume via low fees",
        "modules": ["dynamic_fee", "auto_rebalance"],
        "overrides": {
            "dynamic_fee": {"min_fee": 100, "max_fee": 3000, "sensitivity": 8000},
            "auto_rebalance": {"soft_trigger_pct": 90, "il_threshold_bps": 150},
        },
        "market_conditions": {"vol_range": [0, 300], "trend": "sideways"},
    },
    "volatile_defender": {
        "description": "High volatility - protect LP with high fees + MEV guard",
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance"],
        "overrides": {
            "dynamic_fee": {"min_fee": 1000, "max_fee": 15000, "sensitivity": 12000},
            "mev_protection": {"block_suspicious": True},
            "auto_rebalance": {"soft_trigger_pct": 70, "cooldown_period": 120},
        },
        "market_conditions": {"vol_range": [500, 9999], "trend": "any"},
    },
    "trend_rider": {
        "description": "Trending market - wider range, TWAP rebalance",
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance"],
        "overrides": {
            "dynamic_fee": {"sensitivity": 9000},
            "auto_rebalance": {"strategy": 1, "soft_trigger_pct": 75},
        },
        "market_conditions": {"vol_range": [200, 600], "trend": "trending"},
    },
    "full_defense": {
        "description": "Maximum protection - all 5 modules active, JIT shield + TWAP oracle",
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance", "liquidity_shield", "oracle"],
        "overrides": {
            "dynamic_fee": {"min_fee": 1500, "max_fee": 20000, "sensitivity": 15000},
            "mev_protection": {"block_suspicious": True, "swap_count_threshold": 2},
            "auto_rebalance": {"soft_trigger_pct": 65, "cooldown_period": 60},
            "liquidity_shield": {"max_impact_bps": 30, "shield_fee_multiplier": 20000},
        },
        "market_conditions": {"vol_range": [800, 9999], "trend": "any"},
    },
}

# ─── AI Decision Engine ───────────────────────────────────────────────────
PERCEPTION_INTERVAL_SEC = 60        # How often to poll market data
ANALYSIS_INTERVAL_SEC = 300         # How often to run full analysis
EVOLUTION_INTERVAL_SEC = 86400      # How often to run meta-cognition (24h)

VOLATILITY_WINDOW_HOURS = 24        # Lookback for vol calculation
TREND_WINDOW_HOURS = 72             # Lookback for trend detection
CONFIDENCE_THRESHOLD = 0.7          # Min confidence to act on a signal
MAX_POSITION_SIZE_PCT = 30          # Max % of wallet to deploy in one strategy

# ─── Decision Journal ─────────────────────────────────────────────────────
JOURNAL_ON_CHAIN = True             # Log decisions to DecisionJournal contract
JOURNAL_LOCAL_PATH = "decisions/"   # Also store locally for analysis
DECISION_TYPES = {
    "STRATEGY_CREATE": "0x01",
    "STRATEGY_DEACTIVATE": "0x02",
    "FEE_ADJUST": "0x03",
    "REBALANCE_EXECUTE": "0x04",
    "FUND_TRANSFER": "0x05",
    "MODULE_SWAP": "0x06",
    "PERFORMANCE_EVAL": "0x07",
    "META_COGNITION": "0x08",
    "NFT_MINT": "0x09",
    "CCA_AUCTION_CREATE": "0x0A",
    "CCA_AUCTION_SETTLE": "0x0B",
    "LIQUIDITY_SHIELD": "0x0C",
    "ORACLE_UPDATE": "0x0D",
    "DEFI_BENCHMARK": "0x0E",
}

# ─── Strategy NFT ─────────────────────────────────────────────────────────
NFT_MINT_THRESHOLD_PNL_BPS = 100    # Min +1% P&L to mint
NFT_MINT_THRESHOLD_SWAPS = 50       # Min 50 swaps processed
NFT_MINT_THRESHOLD_HOURS = 48       # Min 48h runtime

# ─── x402 Payment Configuration ──────────────────────────────────────────
X402_ENABLED = True
X402_PRICING = {
    "signal_query": {"amount": "0.001", "token": "USDT", "settle": "async"},
    "strategy_subscribe": {"amount": "0.01", "token": "USDT", "settle": "async"},
    "strategy_params_buy": {"amount": "1.00", "token": "USDT", "settle": "sync"},
    "nft_license": {"amount": "5.00", "token": "USDT", "settle": "sync"},
}

# ─── OnchainOS Integration ────────────────────────────────────────────────
ONCHAINOS_MARKET_PAIRS = [
    {"base": "ETH", "quote": "USDC", "chain": CHAIN_ID},
    {"base": "OKB", "quote": "USDT", "chain": CHAIN_ID},
]
DEX_SLIPPAGE_BPS = 50              # 0.5% default slippage
DEX_COMPARE_WITH_HOOK = True       # Always compare Hook pool vs DEX aggregator

# ─── Contract Addresses (X Layer Testnet - Chain 1952) ─────────────────────
CONTRACTS = {
    "assembler": "0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78",
    "v4_hook": "0x79a96bB2Ab2342cf6f1dD3c622F5CB01f9F7A8d4",        # CREATE2-mined, flags: BEFORE_SWAP|AFTER_SWAP
    "hook_deployer": "0xe38ac0DD1fe57Cb02DB80884eA14D47Fa181dF64",
    "dynamic_fee_module": "0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed",
    "mev_protection_module": "0xA4f6ABd6F77928b06F075637ccBACA8f89e17386",
    "auto_rebalance_module": "0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee",
    "strategy_nft": "0xd969448dfc24Fe3Aff25e86db338fAB41b104319",
    "liquidity_shield_module": "0x34Bd6972F086c947e4503185e1A1094d9846b2aC",
    "oracle_module": "0x30049511c4c483E9500A74701DED562A8F1ea86f",
}

# ─── Mainnet Contract Addresses (X Layer Mainnet - Chain 196) ──────────────
# Populated after mainnet deployment via DeployMainnet.sol
MAINNET_CONTRACTS = {
    "assembler": "0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78",
    "v4_hook": "0x174a2450b342042AAe7398545f04B199248E69c0",
    "hook_deployer": "0xE07039Eab157B99e356c52DbC825aA3a0b4F55B9",
    "dynamic_fee_module": "0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed",
    "mev_protection_module": "0xA4f6ABd6F77928b06F075637ccBACA8f89e17386",
    "auto_rebalance_module": "0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee",
    "liquidity_shield_module": "0xd969448dfc24Fe3Aff25e86db338fAB41b104319",
    "oracle_module": "0xCFc867E2379Cbe097D934CB8e19e3F028B82Bd3D",
    "strategy_nft": "0x8a0e87395f864405c5225eBd80391Ac82eefe437",
}

# ─── Mainnet Chain Configuration ─────────────────────────────────────────
MAINNET_CHAIN_ID = 196
MAINNET_RPC_URL = "https://rpc.xlayer.tech"
MAINNET_EXPLORER_URL = "https://www.oklink.com/xlayer"

# ─── Uniswap V4 Core (X Layer) ──────────────────────────────────────────
UNISWAP_V4 = {
    "pool_manager": "0x360e68faCCca8cA495c1B759Fd9EEe466dB9Fb32",
    "position_manager": "0x1b35d13a2e2528f192637f14b05f0dc0e7deb566",
    "quoter": "0x3972c00f7ed4885e145823eb7c655375d275a1c5",
    "universal_router": "0x112908daC86e20e7241B0927479Ea3Bf935d1fa0",
    "permit2": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
}

# ─── Agentic Wallet Address ──────────────────────────────────────────────
AGENTIC_WALLET = "0xd2D120eB7cEd38551cCeFb48021067d41D6542d3"
