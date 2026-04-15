#!/usr/bin/env python3
"""
x402 Guard — Live Demo Bot
Simulates 4 AI trading bots making real payments on X Layer testnet.
Each bot calls Guard API before every trade → approve / block / soft_alert

Run:
    python3 demo_bot.py

Stop:
    Ctrl+C
"""
import time, random, requests, json, sys, os
from datetime import datetime
from web3 import Web3

# ── Config ──────────────────────────────────────────────────────────────────
GUARD_URL = os.environ.get("GUARD_URL", "http://localhost:4402")
RPC_URL   = "https://testrpc.xlayer.tech"
CHAIN_ID  = 1952
ASSET     = "0xcB8BF24c6cE16Ad21D707c9505421a17f2bec79D"  # USDC_TEST on X Layer testnet

# Bot wallets (from testnet setup)
BOTS = [
    {
        "agent_id":   "agent-alpha",
        "name":       "Sniper Bot #1",
        "bot_type":   "sniper",
        "wallet":     "0x5672E35370b9ED17Cd9bC4f280078444429bE666",
        "key":        None,  # loaded from file
        "targets":    ["api.openai.com", "0xDEXRouter", "api.cohere.com"],
        "amounts":    [3.5, 7.0, 10.0, 13.0, 14.9],  # max per_tx 15 for sniper
        "interval":   7,    # seconds between trades
        "color":      "\033[93m",  # yellow
    },
    {
        "agent_id":   "agent-beta",
        "name":       "Arbitrage Bot",
        "bot_type":   "arbitrage",
        "wallet":     "0xAb96ea0B4c3F1Fb90A5cA96b248a3dC561c976E2",
        "key":        None,
        "targets":    ["api.uniswap.org", "api.sushiswap.com", "0xAMMPool"],
        "amounts":    [5.0, 12.0, 20.0, 24.9, 26.0],   # ~per_tx 25, 26 will block
        "interval":   12,
        "color":      "\033[96m",  # cyan
    },
    {
        "agent_id":   "agent-gamma",
        "name":       "Prediction Bot",
        "bot_type":   "prediction",
        "wallet":     "0xfA4cA6e03799BA7F207fcEFa50399C21c1376382",
        "key":        None,
        "targets":    ["api.openai.com", "api.anthropic.com", "api.cohere.com"],
        "amounts":    [2.5, 5.0, 8.0, 9.9],   # per_tx 10 for prediction
        "interval":   15,
        "color":      "\033[92m",  # green
    },
    {
        "agent_id":   "agent-delta",
        "name":       "Sentiment Bot",
        "bot_type":   "sentiment",
        "wallet":     "0x16067377bb02b3A86Eb3aC341d24Dd70C2C17a05",
        "key":        None,
        "targets":    ["api.twitter.com", "api.openai.com", "api.cohere.com"],
        "amounts":    [1.5, 3.5, 5.5, 7.9],   # per_tx 8 for sentiment
        "interval":   20,
        "color":      "\033[95m",  # magenta
    },
]

RESET    = "\033[0m"
BOLD     = "\033[1m"
RED      = "\033[91m"
GREEN    = "\033[92m"
YELLOW   = "\033[93m"
DIM      = "\033[2m"

# ── Load wallets ─────────────────────────────────────────────────────────────
try:
    with open("/tmp/agent_wallets.json") as f:
        wallets = json.load(f)
    for bot in BOTS:
        name = bot["agent_id"].replace("agent-", "")
        if name in wallets:
            bot["key"] = wallets[name]["key"]
except Exception as e:
    print(f"{YELLOW}[warn] Wallet keys not found ({e}) — running without onchain txs{RESET}")

w3 = Web3(Web3.HTTPProvider(RPC_URL))

# ── Guard check ───────────────────────────────────────────────────────────────
def guard_check(agent_id: str, amount: float, pay_to: str) -> dict:
    try:
        r = requests.post(f"{GUARD_URL}/guard/check", json={
            "agent_id":   agent_id,
            "amount":     amount,
            "asset":      ASSET,
            "pay_to":     pay_to,
            "network":    f"eip155:{CHAIN_ID}",
            "request_id": f"demo-{agent_id}-{int(time.time()*1000)}",
        }, timeout=8)
        return r.json()
    except Exception as e:
        return {"action": "block", "reason": f"Guard unavailable: {e}"}

# ── Send onchain tx (optional) ────────────────────────────────────────────────
GUARDIAN = "0xd28AC0e17fBb7fE96293A36CeaF72C81Bf1773E3"

def send_onchain(bot: dict, amount_usd: float) -> str | None:
    if not bot.get("key") or not w3.is_connected():
        return None
    try:
        addr    = w3.to_checksum_address(bot["wallet"])
        bal     = w3.eth.get_balance(addr)
        value   = w3.to_wei(0.00005, "ether")
        if bal < value + w3.to_wei(0.00002, "ether"):
            return None
        nonce   = w3.eth.get_transaction_count(addr, "pending")
        gp      = w3.eth.gas_price
        tx      = {"to": GUARDIAN, "value": value, "gas": 21000,
                   "gasPrice": gp, "nonce": nonce, "chainId": CHAIN_ID}
        signed  = w3.eth.account.sign_transaction(tx, bot["key"])
        raw     = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)
        txhash  = w3.eth.send_raw_transaction(raw).hex()
        return txhash
    except Exception:
        return None

# ── Stats ─────────────────────────────────────────────────────────────────────
def get_stats(agent_id: str) -> dict:
    try:
        r = requests.get(f"{GUARD_URL}/guard/stats/{agent_id}", timeout=5)
        return r.json()
    except:
        return {}

# ── Print helpers ─────────────────────────────────────────────────────────────
def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")

def print_header():
    sys.stdout.flush()
    print(f"\n{BOLD}{'─'*70}{RESET}", flush=True)
    print(f"{BOLD}  x402 Guard — Live Demo Bot{RESET}  |  {DIM}Dashboard: http://localhost:3000{RESET}", flush=True)
    print(f"{BOLD}{'─'*70}{RESET}\n", flush=True)

def print_trade(bot: dict, amount: float, target: str, result: dict, txhash: str | None):
    color  = bot["color"]
    action = result.get("action", "?")
    reason = result.get("reason", "")[:60]

    if action == "approve":
        badge = f"{GREEN}[APPROVE]{RESET}"
    elif action == "soft_alert":
        badge = f"{YELLOW}[ALERT  ]{RESET}"
    else:
        badge = f"{RED}[BLOCK  ]{RESET}"

    chain = f"  ⛓  {txhash[:18]}..." if txhash else ""
    print(f"{DIM}{ts()}{RESET} {color}{bot['name']:20}{RESET} {badge}  ${amount:6.2f}  →  {target[:25]}")
    if action != "approve":
        print(f"        {DIM}{reason}{RESET}")
    if chain:
        print(f"        {DIM}{chain}{RESET}")

# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    print_header()
    print(f"  Starting {len(BOTS)} bots on X Layer Testnet (chain {CHAIN_ID})")
    print(f"  Guard API: {GUARD_URL}")
    print(f"  Dashboard: http://localhost:3000\n")
    print(f"  {DIM}Press Ctrl+C to stop{RESET}\n")
    print(f"{'─'*70}\n")

    # Check guard health (retry for cold start)
    guard_online = False
    for attempt in range(6):
        try:
            h = requests.get(f"{GUARD_URL}/health", timeout=20).json()
            print(f"  Guard: {GREEN}● ONLINE{RESET}  ({h.get('status','?')})\n")
            guard_online = True
            break
        except Exception as e:
            print(f"  Guard warming up ({attempt+1}/6)... {e}")
            time.sleep(10)
    if not guard_online:
        print(f"  Guard: {RED}● OFFLINE{RESET} — check {GUARD_URL}\n")
        return

    counters   = {b["agent_id"]: {"trades": 0, "approved": 0, "blocked": 0} for b in BOTS}
    last_trade = {b["agent_id"]: -999.0 for b in BOTS}  # start immediately

    total = 0
    try:
        while True:
            now = time.time()
            acted = False

            for bot in BOTS:
                aid = bot["agent_id"]
                if now - last_trade[aid] < bot["interval"]:
                    continue

                # Pick trade
                amount = random.choice(bot["amounts"])
                # Add some variance
                amount = round(amount * random.uniform(0.85, 1.15), 2)
                target = random.choice(bot["targets"])

                # Guard check
                result = guard_check(aid, amount, target)
                action = result.get("action", "block")

                # Real onchain tx if approved
                txhash = None
                if action in ("approve", "soft_alert"):
                    txhash = send_onchain(bot, amount)

                print_trade(bot, amount, target, result, txhash)
                counters[aid]["trades"]  += 1
                total                   += 1
                if action == "approve":    counters[aid]["approved"] += 1
                if action == "block":      counters[aid]["blocked"]  += 1
                if action == "soft_alert": counters[aid]["approved"] += 1

                last_trade[aid] = now
                acted = True

            # Print summary every 10 trades
            if total > 0 and total % 10 == 0 and acted:
                print(f"\n{DIM}{'─'*70}{RESET}")
                print(f"{DIM}  Summary after {total} trades:{RESET}")
                for bot in BOTS:
                    aid = bot["agent_id"]
                    c   = counters[aid]
                    stats = get_stats(aid)
                    spent = stats.get("daily_spent", 0)
                    limit = stats.get("daily_limit", 0)
                    pct   = f"{(spent/limit*100):.0f}%" if limit else "?"
                    print(f"  {bot['color']}{bot['name']:20}{RESET}  "
                          f"trades={c['trades']:3}  "
                          f"approved={c['approved']:3}  "
                          f"blocked={c['blocked']:3}  "
                          f"spent=${spent:.2f}/{limit:.0f} ({pct})")
                print(f"{DIM}{'─'*70}{RESET}\n")

            if not acted:
                time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n\n{BOLD}{'─'*70}{RESET}")
        print(f"{BOLD}  Demo stopped.{RESET}")
        print(f"\n  Final summary:")
        for bot in BOTS:
            aid = bot["agent_id"]
            c   = counters[aid]
            print(f"  {bot['color']}{bot['name']:20}{RESET}  "
                  f"{c['trades']} trades  "
                  f"{GREEN}{c['approved']} approved{RESET}  "
                  f"{RED}{c['blocked']} blocked{RESET}")
        print(f"\n  View dashboard: http://localhost:3000")
        print(f"{BOLD}{'─'*70}{RESET}\n")

if __name__ == "__main__":
    main()
