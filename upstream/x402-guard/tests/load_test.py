#!/usr/bin/env python3
"""
x402 Guard Load Test
---------------------
Fires 100 concurrent /guard/check requests and reports:
  - avg latency, p50, p95, p99
  - throughput (req/s)
  - success / error breakdown

Run with:
    python3 tests/load_test.py
    python3 tests/load_test.py --guard http://localhost:8000 --concurrency 100 --total 500
    python3 tests/load_test.py --offline          (mock mode, tests threading overhead only)
"""

import argparse
import json
import math
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional


# ── ANSI helpers ───────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
WHITE  = "\033[37m"

def col(text, *codes) -> str:
    return "".join(codes) + str(text) + RESET


# ── Sample data ────────────────────────────────────────────────────────────────

AGENTS = [f"load-agent-{i:03d}" for i in range(10)]

ENDPOINTS_AMOUNTS = [
    ("0xAaaa1111aaaa1111aaaa1111aaaa1111aaaa1111", 0.50),
    ("0xBbbb2222bbbb2222bbbb2222bbbb2222bbbb2222", 1.00),
    ("0xCccc3333cccc3333cccc3333cccc3333cccc3333", 2.00),
    ("0xDddd4444dddd4444dddd4444dddd4444dddd4444", 5.00),
    ("0xEeee5555eeee5555eeee5555eeee5555eeee5555", 0.25),
    ("0xFfff6666ffff6666ffff6666ffff6666ffff6666", 0.10),
]


def _random_payload() -> dict:
    pay_to, amount = random.choice(ENDPOINTS_AMOUNTS)
    return {
        "agent_id": random.choice(AGENTS),
        "network":  "eip155:196",
        "amount":   amount,
        "asset":    "0x4ae46a509f6b1d9056937ba4500cb143933d2dc8",
        "pay_to":   pay_to,
    }


# ── Result container ───────────────────────────────────────────────────────────

@dataclass
class RequestResult:
    latency_s:  float
    status_code: int
    action:      Optional[str] = None
    error:       Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status_code in (200, 201) and self.error is None


# ── Single request worker ──────────────────────────────────────────────────────

def _do_request(guard_url: str, results: List[RequestResult], idx: int, offline: bool):
    payload = _random_payload()

    if offline:
        # Simulate a tiny bit of work so timing is realistic
        time.sleep(random.uniform(0.001, 0.005))
        results[idx] = RequestResult(
            latency_s   = random.uniform(0.001, 0.008),
            status_code = 200,
            action      = random.choice(["approve", "approve", "approve", "soft_alert", "block"]),
        )
        return

    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{guard_url}/guard/check",
        data    = data,
        headers = {"Content-Type": "application/json"},
        method  = "POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            latency = time.perf_counter() - t0
            body    = json.loads(resp.read())
            results[idx] = RequestResult(
                latency_s    = latency,
                status_code  = resp.status,
                action       = body.get("action"),
            )
    except urllib.error.HTTPError as exc:
        latency = time.perf_counter() - t0
        try:
            body = json.loads(exc.read())
        except Exception:
            body = {}
        results[idx] = RequestResult(
            latency_s    = latency,
            status_code  = exc.code,
            error        = body.get("detail", str(exc)),
        )
    except Exception as exc:
        latency = time.perf_counter() - t0
        results[idx] = RequestResult(
            latency_s    = latency,
            status_code  = 0,
            error        = str(exc),
        )


# ── Statistics helpers ─────────────────────────────────────────────────────────

def _percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = max(0, math.ceil(pct / 100.0 * len(sorted_values)) - 1)
    return sorted_values[idx]


def _stats(latencies: List[float]):
    s = sorted(latencies)
    n = len(s)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    avg  = sum(s) / n
    p50  = _percentile(s, 50)
    p95  = _percentile(s, 95)
    p99  = _percentile(s, 99)
    mx   = s[-1]
    return avg, p50, p95, p99, mx


# ── Pretty table ───────────────────────────────────────────────────────────────

def _print_table(rows: List[tuple], headers: List[str], col_widths: List[int]):
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    hdr_fmt = "|" + "|".join(f" {h:<{col_widths[i]}} " for i, h in enumerate(headers)) + "|"

    print(col(sep, DIM))
    print(col(hdr_fmt, BOLD))
    print(col(sep, DIM))
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            cells.append(f" {str(cell):<{col_widths[i]}} ")
        print("|" + "|".join(cells) + "|")
    print(col(sep, DIM))


# ── Load test runner ───────────────────────────────────────────────────────────

def run_load_test(
    guard_url:   str,
    total:       int = 100,
    concurrency: int = 100,
    offline:     bool = False,
) -> List[RequestResult]:
    """
    Send `total` requests in batches of `concurrency` concurrent threads.
    Returns list of RequestResult objects.
    """
    all_results: List[RequestResult] = []

    batches = math.ceil(total / concurrency)
    print(
        f"\n  {col('Guard URL:', BOLD)}  {guard_url}"
        f"  {'(OFFLINE MOCK)' if offline else ''}"
    )
    print(
        f"  {col('Total requests:', BOLD)}   {total}  |  "
        f"{col('Concurrency:', BOLD)}  {concurrency}  |  "
        f"{col('Batches:', BOLD)}  {batches}\n"
    )

    wall_start = time.perf_counter()

    for batch_idx in range(batches):
        batch_size  = min(concurrency, total - batch_idx * concurrency)
        results     = [None] * batch_size
        threads     = []

        t_batch = time.perf_counter()
        for i in range(batch_size):
            t = threading.Thread(
                target=_do_request,
                args=(guard_url, results, i, offline),
                daemon=True,
            )
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed_batch = time.perf_counter() - t_batch
        done  = (batch_idx + 1) * concurrency
        ok    = sum(1 for r in results if r and r.ok)
        print(
            f"  Batch {batch_idx + 1:>2}/{batches}  "
            f"{col(ok, GREEN)}/{batch_size} ok  "
            f"{elapsed_batch * 1000:.0f} ms",
            end="\r",
            flush=True,
        )
        all_results.extend([r for r in results if r is not None])

    wall_elapsed = time.perf_counter() - wall_start
    print()  # clear \r line
    return all_results, wall_elapsed


# ── Report ─────────────────────────────────────────────────────────────────────

def print_report(results: List[RequestResult], wall_elapsed: float):
    total   = len(results)
    ok      = [r for r in results if r.ok]
    errors  = [r for r in results if not r.ok]
    n_ok    = len(ok)
    n_err   = len(errors)

    latencies = [r.latency_s for r in ok]
    avg, p50, p95, p99, mx = _stats(latencies)

    throughput = total / wall_elapsed if wall_elapsed > 0 else 0

    # Action breakdown
    actions: dict = {}
    for r in ok:
        a = r.action or "unknown"
        actions[a] = actions.get(a, 0) + 1

    print(col("\n" + "═" * 58, DIM))
    print(col("  LOAD TEST RESULTS", BOLD))
    print(col("═" * 58, DIM))

    # ── Latency table ──────────────────────────────────────────
    print(f"\n  {col('Latency (successful requests only)', BOLD)}\n")
    latency_rows = [
        ("Average",  f"{avg  * 1000:>8.2f} ms"),
        ("P50",      f"{p50  * 1000:>8.2f} ms"),
        ("P95",      f"{p95  * 1000:>8.2f} ms"),
        ("P99",      f"{p99  * 1000:>8.2f} ms"),
        ("Max",      f"{mx   * 1000:>8.2f} ms"),
    ]
    _print_table(latency_rows, ["Metric", "Value"], [12, 14])

    # ── Throughput / overview table ────────────────────────────
    print(f"\n  {col('Throughput & Overview', BOLD)}\n")
    overview_rows = [
        ("Total requests",   str(total)),
        ("Successful",       col(n_ok,  GREEN)),
        ("Errors",           col(n_err, RED) if n_err else col("0", GREEN)),
        ("Wall time",        f"{wall_elapsed:.3f} s"),
        ("Throughput",       f"{throughput:.1f} req/s"),
    ]
    _print_table(overview_rows, ["Metric", "Value"], [18, 18])

    # ── Action breakdown ───────────────────────────────────────
    if actions:
        print(f"\n  {col('Guard Decision Breakdown', BOLD)}\n")
        action_colors = {"approve": GREEN, "soft_alert": YELLOW, "block": RED}
        action_rows = []
        for act, cnt in sorted(actions.items(), key=lambda x: -x[1]):
            c = action_colors.get(act, WHITE)
            pct = cnt / n_ok * 100 if n_ok else 0
            bar = "█" * int(pct / 5)
            action_rows.append((
                col(act, c, BOLD),
                col(f"{cnt:>5}", c),
                col(f"{pct:>5.1f}%  {bar}", c),
            ))
        _print_table(action_rows, ["Action", "Count", "Share"], [12, 8, 30])

    # ── Errors sample ──────────────────────────────────────────
    if errors:
        print(f"\n  {col('Error Sample (up to 5)', BOLD, RED)}\n")
        for r in errors[:5]:
            print(f"   HTTP {r.status_code}  {r.error}")

    # ── Pass / Fail verdict ────────────────────────────────────
    print()
    error_rate = n_err / total if total else 1.0
    if error_rate == 0 and p95 < 0.5:
        verdict = col("PASS  All requests succeeded and p95 < 500 ms", GREEN, BOLD)
    elif error_rate < 0.05:
        verdict = col(f"WARN  {n_err} errors ({error_rate*100:.1f}% error rate)", YELLOW, BOLD)
    else:
        verdict = col(f"FAIL  {n_err} errors ({error_rate*100:.1f}% error rate)", RED, BOLD)

    print(f"  Verdict:  {verdict}")
    print(col("═" * 58 + "\n", DIM))

    return error_rate == 0


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="x402 Guard load test")
    parser.add_argument(
        "--guard",
        default="http://localhost:8000",
        help="Guard base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--total",
        type=int,
        default=100,
        help="Total number of requests (default: 100)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=25,
        help="Max concurrent threads per batch (default: 25)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Offline/mock mode — no real HTTP calls",
    )
    args = parser.parse_args()

    print(col("""
╔══════════════════════════════════════════════════════╗
║         x402 Guard  —  Load Test                     ║
╚══════════════════════════════════════════════════════╝
""", CYAN, BOLD))

    results, wall = run_load_test(
        guard_url   = args.guard,
        total       = args.total,
        concurrency = args.concurrency,
        offline     = args.offline,
    )

    passed = print_report(results, wall)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
