#!/usr/bin/env python3
"""
MarketScout Demo Agent
----------------------
Simulates AI agents making x402 micro-payments for market data,
routed through x402 Guard for policy enforcement.

Run with:
    python3 tests/demo_agent.py
    python3 tests/demo_agent.py --guard http://localhost:8000
"""

import argparse
import json
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ── ANSI color helpers ─────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

BLACK   = "\033[30m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[37m"

BG_BLACK   = "\033[40m"
BG_RED     = "\033[41m"
BG_GREEN   = "\033[42m"
BG_YELLOW  = "\033[43m"
BG_BLUE    = "\033[44m"

def col(text: str, *codes: str) -> str:
    return "".join(codes) + str(text) + RESET


# ── Fake x402 endpoint registry ───────────────────────────────────────────────

# (endpoint_url, price_usdc, pay_to_address, description)
ENDPOINTS: List[Tuple[str, float, str, str]] = [
    (
        "https://api.marketscout.xyz/prices",
        0.50,
        "0xAaaa1111aaaa1111aaaa1111aaaa1111aaaa1111",
        "Real-time token prices",
    ),
    (
        "https://api.marketscout.xyz/whales",
        1.00,
        "0xBbbb2222bbbb2222bbbb2222bbbb2222bbbb2222",
        "Whale wallet tracker",
    ),
    (
        "https://api.marketscout.xyz/signals",
        2.00,
        "0xCccc3333cccc3333cccc3333cccc3333cccc3333",
        "AI trading signals",
    ),
    (
        "https://api.marketscout.xyz/deep-analysis",
        5.00,
        "0xDddd4444dddd4444dddd4444dddd4444dddd4444",
        "Deep on-chain analysis",
    ),
    (
        "https://api.defi-alpha.xyz/yields",
        0.25,
        "0xEeee5555eeee5555eeee5555eeee5555eeee5555",
        "DeFi yield opportunities",
    ),
    (
        "https://api.rugcheck.xyz/scan",
        0.10,
        "0xFfff6666ffff6666ffff6666ffff6666ffff6666",
        "Token rug-pull scanner",
    ),
]

ENDPOINT_MAP = {ep[0]: ep for ep in ENDPOINTS}

# ── Policy presets ─────────────────────────────────────────────────────────────

POLICY_PRESETS = {
    "conservative": {
        "daily_limit":         10.0,
        "hourly_limit":         2.0,
        "per_tx_limit":         1.0,
        "auto_approve_under":   0.05,
        "soft_alert_threshold": 0.7,
        "whitelist": ["0xFfff6666ffff6666ffff6666ffff6666ffff6666"],  # rugcheck always allowed
        "blacklist": [],
        "color": BLUE,
        "label": "conservative",
    },
    "balanced": {
        "daily_limit":         50.0,
        "hourly_limit":        10.0,
        "per_tx_limit":         5.0,
        "auto_approve_under":   0.15,
        "soft_alert_threshold": 0.8,
        "whitelist": [],
        "blacklist": [],
        "color": GREEN,
        "label": "balanced",
    },
    "aggressive": {
        "daily_limit":        200.0,
        "hourly_limit":        40.0,
        "per_tx_limit":        10.0,
        "auto_approve_under":   0.50,
        "soft_alert_threshold": 0.9,
        "whitelist": [],
        "blacklist": [],
        "color": MAGENTA,
        "label": "aggressive",
    },
}

# Shared print lock so concurrent agents don't interleave lines
_print_lock = threading.Lock()

def tprint(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)


# ── Agent stats ────────────────────────────────────────────────────────────────

@dataclass
class AgentStats:
    approved:   int = 0
    soft_alert: int = 0
    blocked:    int = 0
    total_paid: float = 0.0
    errors:     int = 0
    latencies:  List[float] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.approved + self.soft_alert + self.blocked + self.errors

    @property
    def avg_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies) * 1000


# ── Guard HTTP helpers ─────────────────────────────────────────────────────────

def _post_json(url: str, payload: dict, timeout: int = 5) -> Tuple[int, dict]:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read())
        except Exception:
            body = {"detail": str(exc)}
        return exc.code, body


def _create_policy_via_api(guard_url: str, agent_id: str, preset: dict) -> Optional[str]:
    """Register a policy on the Guard server and return the policy ID."""
    payload = {
        "name":                 f"demo-{agent_id}",
        "agent_id":             agent_id,
        "daily_limit":          preset["daily_limit"],
        "hourly_limit":         preset["hourly_limit"],
        "per_tx_limit":         preset["per_tx_limit"],
        "auto_approve_under":   preset["auto_approve_under"],
        "soft_alert_threshold": preset["soft_alert_threshold"],
        "whitelist":            preset["whitelist"],
        "blacklist":            preset["blacklist"],
    }
    status, body = _post_json(f"{guard_url}/policy/", payload)
    if status in (200, 201) and "id" in body:
        return body["id"]
    return None


# ── MarketScoutAgent ───────────────────────────────────────────────────────────

class MarketScoutAgent:
    """
    Simulated AI trading agent that fetches market data via x402 micro-payments
    and routes every payment through x402 Guard for policy enforcement.
    """

    def __init__(
        self,
        agent_id: str,
        guard_url: str,
        policy_preset: str = "balanced",
        offline: bool = False,
    ):
        self.agent_id     = agent_id
        self.guard_url    = guard_url.rstrip("/")
        self.preset_name  = policy_preset
        self.preset       = POLICY_PRESETS[policy_preset]
        self.offline      = offline          # skip real HTTP if guard is not up
        self.stats        = AgentStats()
        self.policy_id: Optional[str] = None
        self._color       = self.preset["color"]

    # ── Setup ──────────────────────────────────────────────────────────────────

    def setup(self) -> bool:
        """Register policy on Guard server. Returns False if guard is unreachable."""
        if self.offline:
            self.policy_id = "offline-mock-policy"
            return True
        pid = _create_policy_via_api(self.guard_url, self.agent_id, self.preset)
        if pid:
            self.policy_id = pid
            self._log(
                f"Policy registered  id={col(pid[:8], DIM)}...  "
                f"daily=${self.preset['daily_limit']}  "
                f"hourly=${self.preset['hourly_limit']}  "
                f"per_tx=${self.preset['per_tx_limit']}",
                icon="🔐",
            )
            return True
        self._log(
            "Could not register policy (guard offline?) — running in offline mock mode",
            icon="⚠️ ",
            extra=YELLOW,
        )
        self.offline   = True
        self.policy_id = "offline-mock-policy"
        return False

    # ── Core fetch ─────────────────────────────────────────────────────────────

    def fetch_with_guard(self, endpoint: str) -> str:
        """
        Ask Guard whether this x402 payment is permitted, then simulate
        the actual payment if approved/soft-alerted.

        Returns: 'approved' | 'soft_alert' | 'blocked' | 'error'
        """
        _, price, pay_to, desc = ENDPOINT_MAP[endpoint]

        # ── Build guard request ──────────────────────────────────────────────
        guard_payload = {
            "agent_id":  self.agent_id,
            "network":   "eip155:196",
            "amount":    price,
            "asset":     "0x4ae46a509f6b1d9056937ba4500cb143933d2dc8",
            "pay_to":    pay_to,
            "policy_id": self.policy_id,
        }

        t0 = time.perf_counter()

        if self.offline:
            # Simulate guard logic locally so the demo is still interesting
            action, reason = self._offline_check(price)
            latency = time.perf_counter() - t0
            resp_body = {
                "allowed":    action != "block",
                "action":     action,
                "reason":     reason,
                "remaining_daily":   self.preset["daily_limit"],
                "remaining_hourly":  self.preset["hourly_limit"],
            }
        else:
            status, resp_body = _post_json(
                f"{self.guard_url}/guard/check", guard_payload
            )
            latency = time.perf_counter() - t0
            if status not in (200, 201):
                self.stats.errors += 1
                self._log(
                    f"Guard HTTP {status} for {endpoint}  ({resp_body.get('detail', '')})",
                    icon="💥",
                    extra=RED,
                )
                return "error"

        self.stats.latencies.append(latency)

        action   = resp_body.get("action", "block")
        allowed  = resp_body.get("allowed", False)
        reason   = resp_body.get("reason", "")
        rem_day  = resp_body.get("remaining_daily",  0.0)
        rem_hour = resp_body.get("remaining_hourly", 0.0)

        short_ep = endpoint.replace("https://", "")

        # ── React to guard decision ──────────────────────────────────────────
        if action == "approve":
            self.stats.approved   += 1
            self.stats.total_paid += price
            self._log(
                f"{col('APPROVED', GREEN, BOLD)}  "
                f"{col(f'${price:.2f}', BOLD)} -> {col(short_ep, CYAN)}  "
                f"{col(desc, DIM)}  "
                f"[day=${rem_day:.2f}  hr=${rem_hour:.2f}]",
                icon="✅",
            )

        elif action == "soft_alert":
            self.stats.soft_alert += 1
            self.stats.total_paid += price
            self._log(
                f"{col('SOFT ALERT', YELLOW, BOLD)}  "
                f"{col(f'${price:.2f}', BOLD)} -> {col(short_ep, CYAN)}  "
                f"{col(desc, DIM)}",
                icon="⚠️ ",
            )
            self._log(
                f"  {col(reason, YELLOW)}  proceeding anyway ...",
                icon="  ",
            )

        elif action == "block":
            self.stats.blocked += 1
            self._log(
                f"{col('BLOCKED', RED, BOLD)}  "
                f"{col(f'${price:.2f}', BOLD)} -> {col(short_ep, CYAN)}  "
                f"{col(desc, DIM)}",
                icon="🚫",
            )
            self._log(
                f"  {col(reason, RED)}",
                icon="  ",
            )

        else:
            self.stats.errors += 1
            self._log(f"Unknown action '{action}' from guard", icon="❓")

        return action

    # ── Session runner ─────────────────────────────────────────────────────────

    def run_session(self, num_requests: int = 10) -> AgentStats:
        self._log(
            f"Starting session — {num_requests} requests  "
            f"policy={col(self.preset_name, self._color, BOLD)}",
            icon="🚀",
        )
        for i in range(num_requests):
            endpoint = random.choice(ENDPOINTS)[0]
            self.fetch_with_guard(endpoint)
            # Small random delay to simulate real agent think-time
            time.sleep(random.uniform(0.05, 0.3))

        self._log(
            f"Session complete — "
            f"approved={col(self.stats.approved, GREEN)}  "
            f"soft={col(self.stats.soft_alert, YELLOW)}  "
            f"blocked={col(self.stats.blocked, RED)}  "
            f"paid={col(f'${self.stats.total_paid:.2f}', BOLD)}  "
            f"avg_latency={col(f'{self.stats.avg_latency_ms:.1f}ms', CYAN)}",
            icon="📊",
        )
        return self.stats

    # ── Offline simulation ─────────────────────────────────────────────────────

    def _offline_check(self, amount: float) -> Tuple[str, str]:
        """Very simple local policy simulation used when guard is unreachable."""
        if amount <= self.preset["auto_approve_under"]:
            return "approve", f"auto-approve: ${amount} <= threshold"
        if amount > self.preset["per_tx_limit"]:
            return "block", f"per-tx limit: ${amount} > ${self.preset['per_tx_limit']}"
        # Simulate random soft_alert occasionally
        roll = random.random()
        if roll < 0.15:
            return "soft_alert", "approaching hourly limit (simulated)"
        if roll < 0.05:
            return "block", "daily limit exceeded (simulated)"
        return "approve", "within all limits"

    # ── Logging ────────────────────────────────────────────────────────────────

    def _log(self, msg: str, icon: str = " ", extra: str = "") -> None:
        ts    = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        label = col(f"[{self.agent_id}]", self._color, BOLD)
        tprint(f"{col(ts, DIM)}  {label}  {icon}  {extra}{msg}{RESET}")


# ── Main ───────────────────────────────────────────────────────────────────────

def print_banner():
    tprint(col("""
╔══════════════════════════════════════════════════════════════════╗
║          MarketScout x402 Guard  —  Demo Agent                  ║
║  Simulates AI agents making micro-payments for market data       ║
╚══════════════════════════════════════════════════════════════════╝
""", CYAN, BOLD))


def print_summary(agents: List[MarketScoutAgent]):
    tprint()
    tprint(col("═" * 68, DIM))
    tprint(col("  FINAL SUMMARY", BOLD))
    tprint(col("═" * 68, DIM))
    hdr = (
        f"  {'Agent':<22}  {'Policy':<13}  "
        f"{'OK':>4}  {'Warn':>4}  {'Blk':>4}  "
        f"{'Paid':>8}  {'AvgMs':>7}"
    )
    tprint(col(hdr, BOLD))
    tprint(col("  " + "-" * 66, DIM))

    total_paid = 0.0
    for ag in agents:
        s = ag.stats
        row = (
            f"  {col(ag.agent_id, ag._color):<31}  "
            f"{col(ag.preset_name, ag._color):<22}  "
            f"{col(s.approved, GREEN):>13}  "
            f"{col(s.soft_alert, YELLOW):>13}  "
            f"{col(s.blocked, RED):>13}  "
            f"{col(f'${s.total_paid:.2f}', BOLD):>17}  "
            f"{col(f'{s.avg_latency_ms:.1f}', CYAN):>16}"
        )
        tprint(row)
        total_paid += s.total_paid

    tprint(col("  " + "-" * 66, DIM))
    tprint(f"  {col('Total paid across all agents:', BOLD)}  {col(f'${total_paid:.2f} USDC', GREEN, BOLD)}")
    tprint(col("═" * 68, DIM))
    tprint()


def main():
    parser = argparse.ArgumentParser(description="MarketScout x402 Guard demo")
    parser.add_argument(
        "--guard",
        default="http://localhost:8000",
        help="x402 Guard base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=10,
        help="Number of requests per agent (default: 10)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force offline mode (no real HTTP calls to guard)",
    )
    args = parser.parse_args()

    print_banner()

    # ── Create agents ──────────────────────────────────────────────────────────
    agents = [
        MarketScoutAgent("scout-alpha",   args.guard, "conservative", args.offline),
        MarketScoutAgent("scout-beta",    args.guard, "balanced",     args.offline),
        MarketScoutAgent("scout-gamma",   args.guard, "aggressive",   args.offline),
    ]

    # ── Setup (register policies) ──────────────────────────────────────────────
    tprint(col("── Setting up agent policies ──", DIM))
    for ag in agents:
        ag.setup()
        time.sleep(0.1)
    tprint()

    # ── Run concurrent sessions ────────────────────────────────────────────────
    tprint(col("── Starting concurrent sessions ──", DIM))
    threads = []
    for ag in agents:
        t = threading.Thread(
            target=ag.run_session,
            kwargs={"num_requests": args.requests},
            name=ag.agent_id,
            daemon=True,
        )
        threads.append(t)

    for t in threads:
        t.start()
        time.sleep(0.05)   # stagger starts slightly so output doesn't all fire at once

    for t in threads:
        t.join()

    # ── Summary ────────────────────────────────────────────────────────────────
    print_summary(agents)


if __name__ == "__main__":
    main()
