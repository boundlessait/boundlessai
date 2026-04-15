#!/usr/bin/env python3
"""
Genesis Protocol CLI - Entry point for all Genesis operations.

Usage:
    python -m scripts.main <command> [args...]

Commands:
    start                       Start the autonomous strategy engine
    stop                        Stop the engine gracefully
    status                      Show current engine state
    deploy                      Deploy all contracts to X Layer
    create-strategy [preset]    Create a strategy (calm_accumulator|volatile_defender|trend_rider)
    rebalance <strategy_id>     Force rebalance a strategy
    deactivate <strategy_id>    Deactivate a strategy
    mint-nft <strategy_id>      Check eligibility and mint Strategy NFT
    journal [strategy_id]       View decision journal
    market                      Show current market analysis
    config set <key> <value>    Update configuration
    config show                 Show current configuration
    x402 pricing                Show x402 payment tiers
"""

import sys
import json
import logging

from . import config
from .genesis_engine import GenesisEngine
from .market_oracle import MarketOracle
from .wallet_manager import WalletManager
from .strategy_manager import StrategyManager
from .decision_journal import DecisionJournal
from .hook_assembler import HookAssembler
from .nft_minter import NFTMinter
from .onchainos_api import OnchainOSAPI
from .payment_handler import PaymentHandler

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("genesis.cli")


def _startup_verify():
    """Run OnchainOS integration verification on startup and log results."""
    try:
        api = OnchainOSAPI()
        result = api.verify_integration()
        status = result.get("status", "unknown")
        dex = result.get("dex_api", "?")
        market = result.get("market_api", "?")
        logger.info(
            "OnchainOS integration check: status=%s | DEX=%s | Market=%s",
            status, dex, market,
        )
        if status == "degraded":
            logger.warning(
                "OnchainOS APIs are degraded. REST calls will fall back to CLI."
            )
        return result
    except Exception as exc:
        logger.error("OnchainOS startup verification failed: %s", exc)
        return {"status": "error", "error": str(exc)}


def cmd_start():
    """Start the autonomous strategy engine."""
    engine = GenesisEngine()
    print(f"Genesis Engine starting (mode={config.MODE}, paused={config.PAUSED})")
    engine.start()


def cmd_stop():
    """Stop the engine (sends signal)."""
    print("To stop the engine, press Ctrl+C in the running terminal.")
    print("The engine handles SIGINT gracefully.")


def cmd_status():
    """Show current engine state."""
    engine = GenesisEngine()
    status = engine.get_status()
    print(json.dumps(status, indent=2, default=str))


def cmd_deploy():
    """Deploy all contracts to X Layer."""
    assembler = HookAssembler()
    print(f"Deploying Genesis contracts to {config.CHAIN_NAME} (chain {config.CHAIN_ID})")
    print(f"  RPC: {config.RPC_URL}")
    print(f"  DRY_RUN: {config.DRY_RUN}")
    print()

    # Deploy assembler first
    wallet = WalletManager()
    master = wallet.get_wallet_address("master")
    print(f"  Master wallet: {master}")

    # Deploy modules
    modules = {}
    for name, mod_config in config.AVAILABLE_MODULES.items():
        print(f"  Deploying {mod_config['contract']}...")
        params = mod_config["default_params"]
        result = assembler.deploy_module(name, params)
        addr = result.get("address", "0x" + "0" * 40)
        modules[name] = addr
        print(f"    → {addr}")

    # Register modules
    for name, addr in modules.items():
        print(f"  Registering {name}...")
        assembler.register_module(addr)

    print()
    print("Deployment complete. Update config.CONTRACTS with deployed addresses.")
    print(json.dumps(modules, indent=2))


def cmd_create_strategy(preset_name=None):
    """Create a strategy from a preset."""
    if not preset_name:
        preset_name = "calm_accumulator"
    if preset_name not in config.STRATEGY_PRESETS:
        print(f"Unknown preset: {preset_name}")
        print(f"Available: {', '.join(config.STRATEGY_PRESETS.keys())}")
        return

    oracle = MarketOracle()
    prices = oracle.fetch_all_prices()
    pair = config.ONCHAINOS_MARKET_PAIRS[0]
    regime = oracle.get_market_regime(pair["base"], pair["quote"])

    manager = StrategyManager()
    result = manager.create_strategy(regime, {"prices": prices, "regime": regime})
    print(json.dumps(result, indent=2, default=str))


def cmd_rebalance(strategy_id):
    """Force rebalance a strategy."""
    oracle = MarketOracle()
    pair = config.ONCHAINOS_MARKET_PAIRS[0]
    regime = oracle.get_market_regime(pair["base"], pair["quote"])

    manager = StrategyManager()
    manager.rebalance_strategy(int(strategy_id), regime)
    print(f"Strategy {strategy_id} rebalanced.")


def cmd_deactivate(strategy_id):
    """Deactivate a strategy."""
    manager = StrategyManager()
    manager.deactivate_strategy(int(strategy_id), "Manual deactivation via CLI")
    print(f"Strategy {strategy_id} deactivated.")


def cmd_mint_nft(strategy_id):
    """Check eligibility and mint Strategy NFT."""
    minter = NFTMinter()
    manager = StrategyManager()

    strategies = manager.get_active_strategies()
    strat = next((s for s in strategies if s.get("id") == int(strategy_id)), None)
    if not strat:
        print(f"Strategy {strategy_id} not found.")
        return

    eligible, reasons = minter.check_mint_eligibility({
        "pnl_bps": strat.get("pnl_bps", 0),
        "total_swaps": strat.get("total_swaps", 0),
        "run_hours": strat.get("run_hours", 0),
    })

    if eligible:
        print(f"Strategy {strategy_id} is eligible for NFT minting!")
        result = minter.mint_strategy_nft(
            strat.get("owner", ""),
            strat,
        )
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Strategy {strategy_id} is NOT eligible:")
        for r in reasons:
            print(f"  - {r}")


def cmd_journal(strategy_id=None):
    """View decision journal."""
    journal = DecisionJournal()
    if strategy_id:
        entries = journal.get_decisions_by_strategy(int(strategy_id))
    else:
        entries = journal.get_recent_decisions(20)

    for entry in entries:
        print(json.dumps(entry, indent=2, default=str))
        print("---")
    print(f"Total entries shown: {len(entries)}")


def cmd_market():
    """Show current market analysis."""
    oracle = MarketOracle()
    print("Market Analysis")
    print("=" * 60)

    for pair in config.ONCHAINOS_MARKET_PAIRS:
        base, quote = pair["base"], pair["quote"]
        print(f"\n{base}/{quote}:")

        price = oracle.fetch_price(base, quote)
        print(f"  Price:      {price}")

        vol = oracle.calculate_volatility(base, quote)
        print(f"  Volatility: {vol:.2f} bps (24h)")

        trend = oracle.detect_trend(base, quote)
        print(f"  Trend:      {trend}")

        regime = oracle.get_market_regime(base, quote)
        print(f"  Regime:     {regime.get('regime_name', 'unknown')}")
        print(f"  Confidence: {regime.get('confidence', 0):.2f}")


def cmd_config_show():
    """Show current configuration."""
    sections = {
        "Safety": {"PAUSED": config.PAUSED, "MODE": config.MODE, "DRY_RUN": config.DRY_RUN},
        "Chain": {"CHAIN_ID": config.CHAIN_ID, "CHAIN_NAME": config.CHAIN_NAME, "RPC_URL": config.RPC_URL},
        "AI Engine": {
            "PERCEPTION_INTERVAL": config.PERCEPTION_INTERVAL_SEC,
            "ANALYSIS_INTERVAL": config.ANALYSIS_INTERVAL_SEC,
            "CONFIDENCE_THRESHOLD": config.CONFIDENCE_THRESHOLD,
        },
        "NFT Thresholds": {
            "PNL_BPS": config.NFT_MINT_THRESHOLD_PNL_BPS,
            "SWAPS": config.NFT_MINT_THRESHOLD_SWAPS,
            "HOURS": config.NFT_MINT_THRESHOLD_HOURS,
        },
        "Contracts": config.CONTRACTS,
    }
    print(json.dumps(sections, indent=2))


def cmd_x402_pricing():
    """Show x402 payment tiers."""
    print("x402 Payment Tiers")
    print("=" * 60)
    for service, pricing in config.X402_PRICING.items():
        print(f"  {service:25s}  {pricing['amount']} {pricing['token']}  ({pricing['settle']})")


def cmd_x402_pay(product=None, token=None, payer=None):
    """Process an x402 payment with optional token swap via pay-with-any-token."""
    if not product:
        print("Usage: x402 pay <product> <token> <payer_address>")
        print(f"Products: {', '.join(config.X402_PRICING.keys())}")
        return

    handler = PaymentHandler()

    if not token or token.upper() == "USDT":
        # Direct USDT payment
        print(f"Processing x402 payment for '{product}' with USDT...")
        result = handler.process_payment(product, "USDT", payer or "")
    else:
        # Need swap via pay-with-any-token
        print(f"Processing x402 payment for '{product}'...")
        print(f"  Swapping {token} → USDT via pay-with-any-token (Uniswap V4)")
        estimate = handler.estimate_swap(token, product)
        if estimate.get("swap_needed"):
            print(f"  Estimated input: {estimate.get('amount', '?')} {token}")
        result = handler.process_payment(product, token, payer or "")

    if result.get("success"):
        print(f"  ✓ Payment settled: {result.get('amount_usdt')} USDT")
        if result.get("swap_details"):
            sd = result["swap_details"]
            print(f"  ✓ Swapped: {sd.get('from_amount', '?')} {sd.get('from_token')} → {sd.get('to_amount')} USDT")
        print(f"  TX: {result.get('tx_hash', 'N/A')}")
    else:
        print(f"  ✗ Payment failed: {result.get('error', 'unknown')}")


def _parse_natural_language(text: str) -> tuple:
    """Parse a natural language request into a (command, args) tuple.

    Enables AI-native interaction -- users and agents can describe what they
    want in plain language instead of memorising CLI syntax.

    Returns:
        (command_str, args_list)  or  (None, None) if no intent matched.
    """
    t = text.lower().strip()

    # ── Market / Price queries ─────────────────────────────────────────
    if any(kw in t for kw in ("市场", "market", "price", "价格", "行情",
                               "what's the market", "how's the market",
                               "show me prices", "check market")):
        return "market", []

    # ── Strategy creation ──────────────────────────────────────────────
    if any(kw in t for kw in ("创建策略", "create strategy", "new strategy",
                               "deploy strategy", "build strategy",
                               "部署策略", "生成策略")):
        for preset in config.STRATEGY_PRESETS:
            if preset.replace("_", " ") in t or preset in t:
                return "create-strategy", [preset]
        if any(kw in t for kw in ("volatile", "波动", "defend", "防御")):
            return "create-strategy", ["volatile_defender"]
        if any(kw in t for kw in ("trend", "趋势", "ride", "追涨")):
            return "create-strategy", ["trend_rider"]
        if any(kw in t for kw in ("full", "全部", "defense", "最大保护")):
            return "create-strategy", ["full_defense"]
        return "create-strategy", ["calm_accumulator"]

    # ── Strategy status / health ───────────────────────────────────────
    if any(kw in t for kw in ("状态", "status", "how are my strategies",
                               "check strategies", "策略状态",
                               "how's it going", "engine status")):
        return "status", []

    # ── Rebalance ──────────────────────────────────────────────────────
    if any(kw in t for kw in ("再平衡", "rebalance", "adjust position",
                               "调整头寸", "re-balance")):
        import re
        nums = re.findall(r'\d+', t)
        if nums:
            return "rebalance", [nums[0]]
        return "rebalance", ["0"]

    # ── Deactivate ─────────────────────────────────────────────────────
    if any(kw in t for kw in ("停止", "deactivate", "stop strategy",
                               "关闭策略", "shut down strategy")):
        import re
        nums = re.findall(r'\d+', t)
        if nums:
            return "deactivate", [nums[0]]
        return None, None

    # ── NFT minting ────────────────────────────────────────────────────
    if any(kw in t for kw in ("铸造", "mint", "nft", "generate nft",
                               "铸造nft", "mint nft", "create nft")):
        import re
        nums = re.findall(r'\d+', t)
        if nums:
            return "mint-nft", [nums[0]]
        return "mint-nft", ["0"]

    # ── Decision journal ───────────────────────────────────────────────
    if any(kw in t for kw in ("日志", "journal", "decisions", "决策记录",
                               "show decisions", "audit log", "审计")):
        import re
        nums = re.findall(r'\d+', t)
        return "journal", [nums[0]] if nums else []

    # ── Config ─────────────────────────────────────────────────────────
    if any(kw in t for kw in ("配置", "config", "settings", "设置",
                               "show config")):
        return "config", ["show"]

    # ── x402 payment ───────────────────────────────────────────────────
    if any(kw in t for kw in ("支付", "payment", "x402", "pay", "pricing",
                               "价格", "定价")):
        if any(kw in t for kw in ("pricing", "定价", "价格", "tiers")):
            return "x402", ["pricing"]
        return "x402", ["pricing"]

    # ── Start / stop engine ────────────────────────────────────────────
    if any(kw in t for kw in ("启动", "start engine", "run engine", "开始",
                               "launch", "begin")):
        return "start", []
    if any(kw in t for kw in ("停止引擎", "stop engine", "halt")):
        return "stop", []

    # ── Deploy ─────────────────────────────────────────────────────────
    if any(kw in t for kw in ("部署", "deploy", "deploy contracts")):
        return "deploy", []

    # ── Help / fallback ────────────────────────────────────────────────
    if any(kw in t for kw in ("帮助", "help", "what can you do",
                               "你能做什么", "commands")):
        return "help", []

    return None, None


def cmd_help():
    """Display available commands with natural language examples."""
    print("Genesis Protocol - AI-Powered Uniswap V4 Hook Strategy Engine")
    print("=" * 65)
    print()
    print("You can use commands or natural language:")
    print()
    print("  Commands:")
    print("    market                  Show market analysis")
    print("    status                  Engine and strategy status")
    print("    create-strategy [name]  Create a strategy")
    print("    rebalance <id>          Rebalance a strategy")
    print("    deactivate <id>         Deactivate a strategy")
    print("    mint-nft <id>           Mint strategy NFT")
    print("    journal [id]            View decision journal")
    print("    deploy                  Deploy contracts")
    print("    config show             Show configuration")
    print("    x402 pricing            Show payment tiers")
    print("    start                   Start cognitive engine")
    print()
    print("  Natural language examples:")
    print('    "今天市场看起来很波动"       → market analysis')
    print('    "Create a volatile strategy" → create volatile_defender')
    print('    "策略状态如何？"             → status')
    print('    "Mint NFT for strategy 3"   → mint-nft 3')
    print('    "Show me the decision log"  → journal')
    print()
    print(f"  Chain: X Layer mainnet (ID {config.CHAIN_ID})")
    print(f"  Wallet: {config.AGENTIC_WALLET}")


def main():
    # Run integration verification on startup
    _startup_verify()

    if len(sys.argv) < 2:
        cmd_help()
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    # ── Try natural language parsing first ──────────────────────────────
    # If the first arg doesn't match a known command, try NL parsing
    commands = {
        "start": lambda: cmd_start(),
        "stop": lambda: cmd_stop(),
        "status": lambda: cmd_status(),
        "deploy": lambda: cmd_deploy(),
        "create-strategy": lambda: cmd_create_strategy(args[0] if args else None),
        "rebalance": lambda: cmd_rebalance(args[0]) if args else print("Usage: rebalance <strategy_id>"),
        "deactivate": lambda: cmd_deactivate(args[0]) if args else print("Usage: deactivate <strategy_id>"),
        "mint-nft": lambda: cmd_mint_nft(args[0]) if args else print("Usage: mint-nft <strategy_id>"),
        "journal": lambda: cmd_journal(args[0] if args else None),
        "market": lambda: cmd_market(),
        "config": lambda: cmd_config_show() if not args or args[0] == "show" else print("Usage: config show"),
        "x402": lambda: cmd_x402_pricing() if args and args[0] == "pricing" else (cmd_x402_pay(args[1] if len(args) > 1 else None, args[2] if len(args) > 2 else None, args[3] if len(args) > 3 else None) if args and args[0] == "pay" else print("Usage: x402 pricing | x402 pay <product> <token> <payer>")),
        "help": lambda: cmd_help(),
    }

    if cmd in commands:
        commands[cmd]()
    elif cmd == "ask" or cmd not in commands:
        # Natural language mode: join all args as a query
        nl_input = " ".join([cmd] + args)
        parsed_cmd, parsed_args = _parse_natural_language(nl_input)
        if parsed_cmd and parsed_cmd in commands:
            # Re-bind args for the parsed command
            args = parsed_args
            logger.info("NL parsed: '%s' -> cmd=%s args=%s", nl_input, parsed_cmd, args)
            print(f"  [AI] Understood: {parsed_cmd} {' '.join(args)}")
            print()
            # Re-create command lambdas with parsed args
            nl_commands = {
                "start": lambda: cmd_start(),
                "stop": lambda: cmd_stop(),
                "status": lambda: cmd_status(),
                "deploy": lambda: cmd_deploy(),
                "create-strategy": lambda: cmd_create_strategy(parsed_args[0] if parsed_args else None),
                "rebalance": lambda: cmd_rebalance(parsed_args[0]) if parsed_args else print("Need strategy ID"),
                "deactivate": lambda: cmd_deactivate(parsed_args[0]) if parsed_args else print("Need strategy ID"),
                "mint-nft": lambda: cmd_mint_nft(parsed_args[0]) if parsed_args else print("Need strategy ID"),
                "journal": lambda: cmd_journal(parsed_args[0] if parsed_args else None),
                "market": lambda: cmd_market(),
                "config": lambda: cmd_config_show(),
                "x402": lambda: cmd_x402_pricing(),
                "help": lambda: cmd_help(),
            }
            nl_commands[parsed_cmd]()
        else:
            print(f"I didn't understand: '{nl_input}'")
            print("Try 'help' for available commands, or describe what you want in natural language.")
            print()
            print("Examples:")
            print('  genesis market')
            print('  genesis "show me the market"')
            print('  genesis create-strategy volatile_defender')


if __name__ == "__main__":
    main()
