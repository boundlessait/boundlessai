# Genesis Protocol - AI Agent Scripts
"""
Genesis Protocol agent scripts for autonomous Uniswap V4 Hook strategy management.

Modules:
    config          - All tunable parameters
    wallet_manager  - Agentic Wallet multi-sub-wallet management
    market_oracle   - Market data aggregation via OnchainOS
    decision_journal- On-chain + local decision logging
    hook_assembler  - Hook Template Engine (compose & deploy)
    strategy_manager- Strategy lifecycle orchestration
    nft_minter      - Strategy NFT minting
    genesis_engine  - 5-layer AI cognitive architecture
    uniswap_cca     - Uniswap CCA (Conditional Contingent Auction) MEV recapture
    uniswap_driver  - Uniswap Driver (swap & liquidity planning)
    defi_analyzer   - DeFi yield comparison and Genesis benchmarking
"""

from .uniswap_cca import UniswapCCAClient
from .uniswap_driver import UniswapDriverClient
from .defi_analyzer import DeFiAnalyzer
