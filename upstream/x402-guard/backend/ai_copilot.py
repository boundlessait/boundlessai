"""
x402 Guard - AI Co-Pilot

Statistical analysis engine for spending pattern detection, policy suggestion,
risk scoring, and simulation. No external AI API calls — pure Python math.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict, Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from reputation import DomainReputation, reputation as global_reputation
import storage


# ── Data models (plain dicts, no Pydantic dep here) ───────────────────────────

def _make_policy_suggestion(
    suggested_policy: Dict[str, Any],
    reasoning: List[str],
    anomalies: List[Dict[str, Any]],
    confidence_score: float,
) -> Dict[str, Any]:
    return {
        "suggested_policy": suggested_policy,
        "reasoning": reasoning,
        "anomalies": anomalies,
        "confidence_score": round(confidence_score, 4),
    }


def _make_simulation_result(
    approved: int,
    soft_alerted: int,
    blocked: int,
    total_saved: float,
    false_positive_rate: float,
    recommendation: str,
) -> Dict[str, Any]:
    return {
        "approved": approved,
        "soft_alerted": soft_alerted,
        "blocked": blocked,
        "total_saved": round(total_saved, 6),
        "false_positive_rate": round(false_positive_rate, 4),
        "recommendation": recommendation,
    }


# ── Helper: parse timestamp ────────────────────────────────────────────────────

def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    s = str(raw).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(s.split("+")[0].rstrip("Z"), fmt)
        except ValueError:
            continue
    return None


def _percentile(data: List[float], pct: float) -> float:
    """Return the pct-th percentile of data (0-100)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * pct / 100.0
    lo = int(k)
    hi = lo + 1
    if hi >= len(sorted_data):
        return sorted_data[-1]
    frac = k - lo
    return sorted_data[lo] + frac * (sorted_data[hi] - sorted_data[lo])


# ── Core class ────────────────────────────────────────────────────────────────

class AICopilot:
    """
    Statistical AI Co-Pilot for x402 Guard.

    Methods
    -------
    analyze_spending(agent_id, transactions)  -> PolicySuggestion dict
    simulate_policy(policy, transactions)     -> SimulationResult dict
    get_risk_score(transaction)               -> float 0-1
    generate_report(agent_id)                 -> str (Markdown)
    """

    def __init__(self, rep: Optional[DomainReputation] = None):
        self._rep = rep or global_reputation

    # ── analyze_spending ──────────────────────────────────────────────────────

    def analyze_spending(
        self,
        agent_id: str,
        transactions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Analyse a list of transactions and suggest an optimal policy.

        Pattern detection
        -----------------
        - Time-of-day clustering (business hours vs off-hours)
        - Domain / pay_to frequency
        - Amount distribution (mean, std-dev, 95th percentile)

        Anomaly detection
        -----------------
        - Sudden amount spikes (> mean + 3*std)
        - New unknown domains (not seen before last 7 days)
        - Off-hours payments (outside 06:00-22:00 UTC)
        """
        if not transactions:
            return _make_policy_suggestion(
                suggested_policy=self._default_policy(agent_id),
                reasoning=["No transaction history available. Using conservative defaults."],
                anomalies=[],
                confidence_score=0.1,
            )

        txs = [t for t in transactions if t.get("status") != "blocked"]
        amounts = [float(t.get("amount", 0)) for t in txs if t.get("amount")]

        reasoning: List[str] = []
        anomalies: List[Dict[str, Any]] = []

        # ── Amount statistics ──────────────────────────────────────────────
        if amounts:
            mean_amt = statistics.mean(amounts)
            std_amt = statistics.stdev(amounts) if len(amounts) > 1 else mean_amt * 0.5
            p95_amt = _percentile(amounts, 95)
            p99_amt = _percentile(amounts, 99)
        else:
            mean_amt = std_amt = p95_amt = p99_amt = 0.0

        # ── Time-of-day analysis ───────────────────────────────────────────
        hours: List[int] = []
        off_hours_txs: List[Dict[str, Any]] = []
        for t in txs:
            ts = _parse_ts(t.get("timestamp"))
            if ts:
                hours.append(ts.hour)
                if ts.hour < 6 or ts.hour > 22:
                    off_hours_txs.append(t)

        hour_counts = Counter(hours)
        peak_hours = [h for h, _ in hour_counts.most_common(5)]
        off_hours_ratio = len(off_hours_txs) / max(len(txs), 1)

        # ── Domain / recipient frequency ───────────────────────────────────
        domains = [t.get("pay_to", "unknown") for t in txs]
        domain_counts = Counter(domains)
        top_domains = domain_counts.most_common(5)

        # Score each top domain
        domain_trust: Dict[str, float] = {}
        for dom, _ in top_domains:
            domain_trust[dom] = self._rep.score_domain(dom)

        # ── Per-day spending for daily-limit suggestion ────────────────────
        daily_totals: Dict[str, float] = defaultdict(float)
        hourly_windows: List[float] = []

        for t in txs:
            ts = _parse_ts(t.get("timestamp"))
            amt = float(t.get("amount", 0))
            if ts:
                day_key = ts.strftime("%Y-%m-%d")
                daily_totals[day_key] += amt

        daily_amounts = list(daily_totals.values())
        if daily_amounts:
            p95_daily = _percentile(daily_amounts, 95)
            mean_daily = statistics.mean(daily_amounts)
        else:
            p95_daily = p95_amt * 10
            mean_daily = mean_amt * 5

        # Hourly rolling windows
        sorted_txs = sorted(txs, key=lambda t: _parse_ts(t.get("timestamp")) or datetime.min)
        for i, t in enumerate(sorted_txs):
            ts = _parse_ts(t.get("timestamp"))
            if not ts:
                continue
            window_end = ts
            window_start = ts - timedelta(hours=1)
            window_total = sum(
                float(t2.get("amount", 0))
                for t2 in sorted_txs[:i + 1]
                if _parse_ts(t2.get("timestamp")) and window_start <= _parse_ts(t2.get("timestamp")) <= window_end
            )
            hourly_windows.append(window_total)

        p95_hourly = _percentile(hourly_windows, 95) if hourly_windows else p95_daily / 24

        # ── Anomaly: amount spikes ─────────────────────────────────────────
        spike_threshold = mean_amt + 3 * std_amt if std_amt > 0 else mean_amt * 4
        for t in txs:
            amt = float(t.get("amount", 0))
            if amt > spike_threshold and spike_threshold > 0:
                anomalies.append({
                    "type": "amount_spike",
                    "severity": "high",
                    "transaction_id": t.get("id", "unknown"),
                    "amount": amt,
                    "threshold": round(spike_threshold, 6),
                    "description": f"Amount {amt:.4f} is > 3 std-devs above mean ({mean_amt:.4f})",
                })

        # ── Anomaly: suspicious domains ────────────────────────────────────
        seven_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
        all_known_domains: set = set()
        for t in sorted_txs:
            ts = _parse_ts(t.get("timestamp"))
            if ts and ts < seven_days_ago:
                all_known_domains.add(t.get("pay_to", ""))

        for t in sorted_txs:
            ts = _parse_ts(t.get("timestamp"))
            if ts and ts >= seven_days_ago:
                domain = t.get("pay_to", "")
                rep_score = self._rep.score_domain(domain)
                if rep_score < 0.40:
                    anomalies.append({
                        "type": "suspicious_domain",
                        "severity": "critical",
                        "transaction_id": t.get("id", "unknown"),
                        "domain": domain,
                        "reputation_score": rep_score,
                        "description": f"Domain '{domain}' has a low reputation score ({rep_score:.2f})",
                    })
                elif domain not in all_known_domains and rep_score < 0.70:
                    anomalies.append({
                        "type": "new_unknown_domain",
                        "severity": "medium",
                        "transaction_id": t.get("id", "unknown"),
                        "domain": domain,
                        "reputation_score": rep_score,
                        "description": f"New domain '{domain}' not seen before last 7 days (rep={rep_score:.2f})",
                    })

        # ── Anomaly: off-hours activity ────────────────────────────────────
        if off_hours_ratio > 0.20:
            anomalies.append({
                "type": "off_hours_activity",
                "severity": "medium",
                "ratio": round(off_hours_ratio, 3),
                "count": len(off_hours_txs),
                "description": f"{off_hours_ratio*100:.1f}% of transactions occur outside 06:00-22:00 UTC",
            })

        # ── Build suggested policy ─────────────────────────────────────────
        # Add a 20% safety buffer on top of p95
        suggested_daily = max(round(p95_daily * 1.20, 2), 1.0)
        suggested_hourly = max(round(p95_hourly * 1.20, 2), 0.5)
        suggested_per_tx = max(round(p95_amt * 1.10, 2), 0.1)

        # Auto-approve under micro-payment threshold (10% of mean or 0.01 min)
        auto_approve = max(round(mean_amt * 0.10, 4), 0.01)

        suggested_policy = {
            "agent_id": agent_id,
            "name": f"AI-Suggested Policy for {agent_id}",
            "daily_limit": suggested_daily,
            "hourly_limit": suggested_hourly,
            "per_tx_limit": suggested_per_tx,
            "auto_approve_under": auto_approve,
            "soft_alert_threshold": 0.80,
            "whitelist": [d for d, s in domain_trust.items() if s >= 0.85],
            "blacklist": [d for d, s in domain_trust.items() if s < 0.10],
        }

        # ── Build reasoning ────────────────────────────────────────────────
        reasoning.append(
            f"Analysed {len(txs)} non-blocked transactions. "
            f"Amount stats: mean={mean_amt:.4f}, p95={p95_amt:.4f}, max={max(amounts, default=0):.4f}."
        )
        reasoning.append(
            f"Daily spending: mean={mean_daily:.4f}, p95={p95_daily:.4f}. "
            f"Suggested daily limit set at p95 + 20% = {suggested_daily}."
        )
        reasoning.append(
            f"Hourly limit set to {suggested_hourly} (p95 of rolling hourly windows + 20%)."
        )
        reasoning.append(
            f"Per-transaction limit set to {suggested_per_tx} (p95 amount + 10%)."
        )

        if peak_hours:
            reasoning.append(
                f"Peak activity hours (UTC): {sorted(peak_hours)}. "
                + ("Most activity within business hours." if off_hours_ratio < 0.10
                   else f"WARNING: {off_hours_ratio*100:.0f}% off-hours activity detected.")
            )

        if top_domains:
            dom_summary = ", ".join(f"{d}({c})" for d, c in top_domains[:3])
            reasoning.append(f"Top payment destinations: {dom_summary}.")

        trusted_whitelist = suggested_policy["whitelist"]
        if trusted_whitelist:
            reasoning.append(
                f"Auto-whitelisted {len(trusted_whitelist)} highly-trusted domain(s): "
                f"{', '.join(trusted_whitelist[:3])}."
            )

        if anomalies:
            reasoning.append(
                f"Detected {len(anomalies)} anomal{'y' if len(anomalies)==1 else 'ies'} "
                f"— review before applying policy."
            )

        # ── Confidence score ───────────────────────────────────────────────
        # Based on: sample size, variance, anomaly count
        sample_confidence = min(1.0, math.log1p(len(txs)) / math.log1p(100))
        variance_penalty = 0.0
        if amounts and mean_amt > 0:
            cv = std_amt / mean_amt  # coefficient of variation
            variance_penalty = min(0.3, cv * 0.15)
        anomaly_penalty = min(0.3, len(anomalies) * 0.05)
        confidence = max(0.1, sample_confidence - variance_penalty - anomaly_penalty)

        return _make_policy_suggestion(
            suggested_policy=suggested_policy,
            reasoning=reasoning,
            anomalies=anomalies,
            confidence_score=confidence,
        )

    # ── simulate_policy ───────────────────────────────────────────────────────

    def simulate_policy(
        self,
        policy: Dict[str, Any],
        historical_transactions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Replay historical transactions through the given policy config and report
        how many would have been approved, soft-alerted, or blocked.

        False-positive rate = (blocked txs that were originally approved) / total_approved_originally
        """
        daily_limit = float(policy.get("daily_limit", 100.0))
        hourly_limit = float(policy.get("hourly_limit", 20.0))
        per_tx_limit = float(policy.get("per_tx_limit", 10.0))
        auto_approve_under = float(policy.get("auto_approve_under", 0.01))
        soft_threshold = float(policy.get("soft_alert_threshold", 0.80))
        whitelist = {w.lower().strip() for w in policy.get("whitelist", [])}
        blacklist = {b.lower().strip() for b in policy.get("blacklist", [])}

        sorted_txs = sorted(
            historical_transactions,
            key=lambda t: _parse_ts(t.get("timestamp")) or datetime.min,
        )

        approved_count = 0
        soft_alerted_count = 0
        blocked_count = 0
        total_saved = 0.0
        false_positives = 0  # originally approved, now blocked

        # Rolling spend trackers (keyed by timestamp)
        daily_spent = 0.0
        hourly_spent = 0.0
        day_window_start: Optional[datetime] = None
        hour_window_start: Optional[datetime] = None

        for tx in sorted_txs:
            ts = _parse_ts(tx.get("timestamp")) or datetime.now(timezone.utc).replace(tzinfo=None)
            amount = float(tx.get("amount", 0))
            pay_to = tx.get("pay_to", "").lower().strip()
            original_status = tx.get("status", "approved")

            # Advance rolling windows
            if day_window_start is None:
                day_window_start = ts
            if hour_window_start is None:
                hour_window_start = ts

            if (ts - day_window_start).total_seconds() >= 86400:
                daily_spent = 0.0
                day_window_start = ts
            if (ts - hour_window_start).total_seconds() >= 3600:
                hourly_spent = 0.0
                hour_window_start = ts

            # Simulate decision
            action = self._simulate_decision(
                amount, pay_to, daily_spent, hourly_spent,
                daily_limit, hourly_limit, per_tx_limit,
                auto_approve_under, soft_threshold, whitelist, blacklist,
            )

            if action == "approve":
                approved_count += 1
                daily_spent += amount
                hourly_spent += amount
            elif action == "soft_alert":
                soft_alerted_count += 1
                daily_spent += amount
                hourly_spent += amount
            else:  # block
                blocked_count += 1
                total_saved += amount
                if original_status in ("approved", "soft_alert"):
                    false_positives += 1

        total_originally_approved = sum(
            1 for t in sorted_txs if t.get("status") in ("approved", "soft_alert")
        )
        false_positive_rate = (
            false_positives / max(total_originally_approved, 1)
        )

        # Generate recommendation
        total = len(sorted_txs)
        block_pct = blocked_count / max(total, 1) * 100
        if false_positive_rate > 0.20:
            recommendation = (
                f"Policy is too aggressive: {false_positive_rate*100:.1f}% false-positive rate. "
                "Consider raising the per-transaction or daily limits."
            )
        elif block_pct > 30:
            recommendation = (
                f"Policy blocks {block_pct:.1f}% of transactions (${total_saved:.2f} saved). "
                "Review if blocked transactions were legitimate business activity."
            )
        elif blocked_count == 0:
            recommendation = (
                "Policy would not have blocked any historical transactions. "
                "Consider tightening limits if anomalies were detected."
            )
        else:
            recommendation = (
                f"Policy looks well-balanced: blocks {block_pct:.1f}% of transactions "
                f"(${total_saved:.2f} saved) with a {false_positive_rate*100:.1f}% false-positive rate."
            )

        return _make_simulation_result(
            approved=approved_count,
            soft_alerted=soft_alerted_count,
            blocked=blocked_count,
            total_saved=total_saved,
            false_positive_rate=false_positive_rate,
            recommendation=recommendation,
        )

    # ── get_risk_score ────────────────────────────────────────────────────────

    def get_risk_score(self, transaction: Dict[str, Any]) -> float:
        """
        Return a risk score 0.0 (safe) to 1.0 (highly risky) for a single tx.

        Factors
        -------
        - amount vs historical average for this agent
        - domain reputation
        - time of day
        - recent frequency (velocity)
        """
        agent_id = transaction.get("agent_id", "")
        amount = float(transaction.get("amount", 0))
        pay_to = transaction.get("pay_to", "")
        ts = _parse_ts(transaction.get("timestamp")) or datetime.now(timezone.utc).replace(tzinfo=None)

        historical = storage.get_transactions_for_agent(agent_id) if agent_id else []
        prev_txs = [t for t in historical if t.get("status") != "blocked"]
        prev_amounts = [float(t.get("amount", 0)) for t in prev_txs if t.get("amount")]

        scores: List[Tuple[float, float]] = []  # (score, weight)

        # 1. Amount vs historical average (weight 0.35)
        if prev_amounts:
            mean_a = statistics.mean(prev_amounts)
            std_a = statistics.stdev(prev_amounts) if len(prev_amounts) > 1 else mean_a * 0.5
            if std_a > 0:
                z = (amount - mean_a) / std_a
                amount_risk = min(1.0, max(0.0, (z + 1) / 5.0))
            else:
                amount_risk = 0.5 if amount > mean_a * 2 else 0.1
        else:
            amount_risk = 0.5  # no history, moderate risk
        scores.append((amount_risk, 0.35))

        # 2. Domain reputation (weight 0.30)
        rep = self._rep.score_domain(pay_to)
        domain_risk = 1.0 - rep  # invert: low rep = high risk
        scores.append((domain_risk, 0.30))

        # 3. Time of day risk (weight 0.15)
        hour = ts.hour
        if 9 <= hour <= 17:
            time_risk = 0.05   # business hours, low risk
        elif 6 <= hour <= 22:
            time_risk = 0.20   # extended hours, slight risk
        else:
            time_risk = 0.65   # off-hours, higher risk
        scores.append((time_risk, 0.15))

        # 4. Velocity risk - how many txs in last hour (weight 0.20)
        one_hour_ago = ts - timedelta(hours=1)
        recent_count = sum(
            1 for t in prev_txs
            if (_parse_ts(t.get("timestamp")) or datetime.min) >= one_hour_ago
        )
        if recent_count <= 2:
            velocity_risk = 0.0
        elif recent_count <= 5:
            velocity_risk = 0.3
        elif recent_count <= 10:
            velocity_risk = 0.6
        else:
            velocity_risk = 0.9
        scores.append((velocity_risk, 0.20))

        # Weighted average
        total_weight = sum(w for _, w in scores)
        risk = sum(s * w for s, w in scores) / total_weight

        return round(min(1.0, max(0.0, risk)), 4)

    # ── generate_report ───────────────────────────────────────────────────────

    def generate_report(self, agent_id: str) -> str:
        """Generate a Markdown spending analysis report for an agent."""
        txs = storage.get_transactions_for_agent(agent_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        thirty_days_ago = now - timedelta(days=30)

        recent_txs = [
            t for t in txs
            if (_parse_ts(t.get("timestamp")) or datetime.min) >= thirty_days_ago
        ]
        approved_txs = [t for t in recent_txs if t.get("status") != "blocked"]
        blocked_txs = [t for t in recent_txs if t.get("status") == "blocked"]

        amounts = [float(t.get("amount", 0)) for t in approved_txs]
        total_spent = sum(amounts)
        mean_amt = statistics.mean(amounts) if amounts else 0.0
        max_amt = max(amounts, default=0.0)
        p95_amt = _percentile(amounts, 95)

        # Domain breakdown
        domain_counts: Counter = Counter(t.get("pay_to", "unknown") for t in approved_txs)
        top_domains = domain_counts.most_common(5)

        # Daily breakdown (last 7 days)
        daily_totals: Dict[str, float] = defaultdict(float)
        for t in approved_txs:
            ts = _parse_ts(t.get("timestamp"))
            if ts and ts >= now - timedelta(days=7):
                daily_totals[ts.strftime("%Y-%m-%d")] += float(t.get("amount", 0))

        # Risk scores for recent txs
        risk_scores = []
        for t in recent_txs[-20:]:  # last 20 only for perf
            try:
                rs = self.get_risk_score(t)
                risk_scores.append(rs)
            except Exception:
                pass

        avg_risk = statistics.mean(risk_scores) if risk_scores else 0.0
        high_risk_count = sum(1 for r in risk_scores if r > 0.65)

        # Anomaly analysis
        analysis = self.analyze_spending(agent_id, recent_txs)
        anomalies = analysis.get("anomalies", [])

        # ── Build Markdown ─────────────────────────────────────────────────
        lines = [
            f"# x402 Guard - AI Co-Pilot Report",
            f"",
            f"**Agent:** `{agent_id}`  ",
            f"**Generated:** {now.strftime('%Y-%m-%d %H:%M:%S')} UTC  ",
            f"**Period:** Last 30 days",
            f"",
            f"---",
            f"",
            f"## Summary",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Transactions | {len(recent_txs)} |",
            f"| Approved / Soft-Alert | {len(approved_txs)} |",
            f"| Blocked | {len(blocked_txs)} |",
            f"| Total Spent (USD) | ${total_spent:.4f} |",
            f"| Mean Transaction | ${mean_amt:.4f} |",
            f"| Max Transaction | ${max_amt:.4f} |",
            f"| 95th Percentile | ${p95_amt:.4f} |",
            f"| Avg Risk Score | {avg_risk:.3f} |",
            f"| High-Risk Txs (last 20) | {high_risk_count} |",
            f"",
        ]

        # Daily spending table
        if daily_totals:
            lines += [
                f"## Daily Spending (Last 7 Days)",
                f"",
                f"| Date | Amount (USD) |",
                f"|------|-------------|",
            ]
            for day in sorted(daily_totals.keys()):
                lines.append(f"| {day} | ${daily_totals[day]:.4f} |")
            lines.append("")

        # Top destinations
        if top_domains:
            lines += [
                f"## Top Payment Destinations",
                f"",
                f"| Destination | Tx Count | Reputation Score |",
                f"|-------------|----------|-----------------|",
            ]
            for dom, cnt in top_domains:
                rep_score = self._rep.score_domain(dom)
                rep_label = "trusted" if rep_score >= 0.85 else ("caution" if rep_score >= 0.40 else "suspicious")
                lines.append(f"| `{dom}` | {cnt} | {rep_score:.2f} ({rep_label}) |")
            lines.append("")

        # Anomalies
        if anomalies:
            lines += [
                f"## Anomalies Detected",
                f"",
            ]
            sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            for a in sorted(anomalies, key=lambda x: sev_order.get(x.get("severity", "low"), 9)):
                sev = a.get("severity", "unknown").upper()
                icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(sev, "⚪")
                lines.append(f"### {icon} {sev}: {a.get('type', 'unknown').replace('_', ' ').title()}")
                lines.append(f"")
                lines.append(f"{a.get('description', '')}")
                if a.get("transaction_id"):
                    lines.append(f"- **Transaction:** `{a['transaction_id']}`")
                if a.get("domain"):
                    lines.append(f"- **Domain:** `{a['domain']}`")
                if a.get("amount"):
                    lines.append(f"- **Amount:** ${a['amount']:.4f}")
                lines.append("")
        else:
            lines += [
                f"## Anomalies Detected",
                f"",
                f"No anomalies detected in the last 30 days.",
                f"",
            ]

        # Policy suggestion
        suggestion = analysis.get("suggested_policy", {})
        confidence = analysis.get("confidence_score", 0.0)
        reasoning = analysis.get("reasoning", [])

        lines += [
            f"## AI Policy Recommendation",
            f"",
            f"**Confidence:** {confidence*100:.0f}%",
            f"",
            f"### Suggested Limits",
            f"",
            f"| Parameter | Suggested Value |",
            f"|-----------|----------------|",
            f"| Daily Limit | ${suggestion.get('daily_limit', 'N/A')} |",
            f"| Hourly Limit | ${suggestion.get('hourly_limit', 'N/A')} |",
            f"| Per-Tx Limit | ${suggestion.get('per_tx_limit', 'N/A')} |",
            f"| Auto-Approve Under | ${suggestion.get('auto_approve_under', 'N/A')} |",
            f"",
            f"### Reasoning",
            f"",
        ]
        for r in reasoning:
            lines.append(f"- {r}")
        lines.append("")

        lines += [
            f"---",
            f"",
            f"*Report generated by x402 Guard AI Co-Pilot v1.0 — statistical analysis only.*",
        ]

        return "\n".join(lines)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _default_policy(self, agent_id: str) -> Dict[str, Any]:
        return {
            "agent_id": agent_id,
            "name": "Conservative Default Policy",
            "daily_limit": 50.0,
            "hourly_limit": 10.0,
            "per_tx_limit": 5.0,
            "auto_approve_under": 0.01,
            "soft_alert_threshold": 0.80,
            "whitelist": [],
            "blacklist": [],
        }

    def _simulate_decision(
        self,
        amount: float,
        pay_to: str,
        daily_spent: float,
        hourly_spent: float,
        daily_limit: float,
        hourly_limit: float,
        per_tx_limit: float,
        auto_approve_under: float,
        soft_threshold: float,
        whitelist: set,
        blacklist: set,
    ) -> str:
        """Replicate PolicyEngine decision logic for simulation."""
        if pay_to in blacklist:
            return "block"
        if pay_to in whitelist:
            return "approve"
        if amount <= auto_approve_under:
            return "approve"
        if amount > per_tx_limit:
            return "block"

        # Hourly check
        projected_hourly = hourly_spent + amount
        if projected_hourly > hourly_limit:
            return "block"
        if projected_hourly >= soft_threshold * hourly_limit:
            return "soft_alert"

        # Daily check
        projected_daily = daily_spent + amount
        if projected_daily > daily_limit:
            return "block"
        if projected_daily >= soft_threshold * daily_limit:
            return "soft_alert"

        return "approve"


# ── Singleton ─────────────────────────────────────────────────────────────────
copilot = AICopilot()
