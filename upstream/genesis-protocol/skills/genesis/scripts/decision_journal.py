"""Decision journal for logging AI decisions locally and on-chain.

Records every strategy decision to a local JSONL file and, when enabled,
to the GenesisHookAssembler's logDecision function via the onchainos CLI.
"""

import subprocess
import json
import logging
import os
import time
import hashlib
import uuid

from . import config

logger = logging.getLogger(__name__)

EVALUATION_TIMEFRAMES = ["T+1h", "T+1d", "T+7d", "T+30d"]


class DecisionJournal:
    """Logs AI decisions to a local JSONL file and on-chain via onchainos."""

    def __init__(self, assembler_address=""):
        """Initialize with assembler contract address and local journal path."""
        self.assembler = assembler_address or config.CONTRACTS.get("assembler", "")
        self.journal_path = config.JOURNAL_LOCAL_PATH
        self._ensure_journal_dir()
        self.trade_links_path = os.path.join(self.journal_path, "trade_links.jsonl")
        self.degradation_path = os.path.join(self.journal_path, "degradation_attestations.jsonl")
        logger.info("DecisionJournal initialized (assembler=%s)", self.assembler)

    # -- public API --------------------------------------------------------

    def log_decision(self, strategy_id, decision_type, reasoning, params=None):
        """Log a decision both locally and on-chain.

        Args:
            strategy_id: Numeric strategy identifier.
            decision_type: Key from config.DECISION_TYPES (e.g. "FEE_ADJUST").
            reasoning: Human-readable reasoning string.
            params: Optional dict of extra parameters.

        Returns:
            The journal entry dict.
        """
        decision_type_hex = config.DECISION_TYPES.get(decision_type, "0x00")
        reasoning_hash = self.compute_reasoning_hash(reasoning)
        params_bytes = self._encode_params(params)

        entry = {
            "id": self._next_id(),
            "decision_id": str(uuid.uuid4()),
            "timestamp": int(time.time()),
            "strategy_id": strategy_id,
            "decision_type": decision_type,
            "reasoning": reasoning,
            "reasoning_hash": reasoning_hash,
            "params": params or {},
            "trade_outcomes": [],
            "timeframe_evaluations": {},
            "on_chain_status": "pending",
        }

        # On-chain logging
        if config.JOURNAL_ON_CHAIN and self.assembler:
            if config.DRY_RUN:
                entry["on_chain_status"] = "dry_run"
                logger.info("DRY_RUN: would log decision #%d on-chain", entry["id"])
            else:
                try:
                    self._log_onchain(
                        strategy_id, decision_type_hex, reasoning_hash, params_bytes
                    )
                    entry["on_chain_status"] = "confirmed"
                except Exception as exc:
                    logger.error("On-chain log failed: %s", exc)
                    entry["on_chain_status"] = "failed"
        else:
            entry["on_chain_status"] = "skipped"

        self._log_local(entry)
        logger.info("Decision #%d logged (%s)", entry["id"], entry["on_chain_status"])
        return entry

    def get_decision_count(self):
        """Return the number of decisions in the local journal."""
        return len(self._read_journal())

    def get_recent_decisions(self, n=10):
        """Return the last *n* decisions from the local journal."""
        return self._read_journal()[-n:]

    def get_decisions_by_type(self, decision_type):
        """Filter journal entries by decision_type string."""
        return [e for e in self._read_journal() if e.get("decision_type") == decision_type]

    def get_decisions_by_strategy(self, strategy_id):
        """Filter journal entries by strategy_id."""
        return [e for e in self._read_journal() if e.get("strategy_id") == strategy_id]

    def compute_reasoning_hash(self, reasoning_text):
        """Compute a sha256 hex digest as a simplified keccak256 stand-in."""
        return "0x" + hashlib.sha256(reasoning_text.encode("utf-8")).hexdigest()

    def export_journal(self):
        """Return the full journal as a list of dicts."""
        return self._read_journal()

    def link_trade(self, decision_id, trade_data):
        """Associate a trade execution result with a decision.

        Args:
            decision_id: The UUID of the decision to link.
            trade_data: Dict containing trade details. Expected keys:
                trade_id, trade_type, token_pair, amount, price,
                pnl (optional).

        Returns:
            The trade link entry dict, or None if the decision was not found.
        """
        # Verify the decision exists
        decision = self._find_decision(decision_id)
        if decision is None:
            logger.warning("link_trade: decision_id %s not found", decision_id)
            return None

        link_entry = {
            "decision_id": decision_id,
            "trade_id": trade_data.get("trade_id", str(uuid.uuid4())),
            "trade_type": trade_data.get("trade_type", ""),
            "token_pair": trade_data.get("token_pair", ""),
            "amount": trade_data.get("amount", 0),
            "price": trade_data.get("price", 0),
            "pnl": trade_data.get("pnl"),
            "timestamp": trade_data.get("timestamp", int(time.time())),
        }

        # Persist the link to trade_links.jsonl
        self._append_trade_link(link_entry)

        # Update the decision's trade_outcomes in the journal
        self._append_trade_outcome(decision_id, link_entry)

        logger.info(
            "Linked trade %s to decision %s", link_entry["trade_id"], decision_id
        )
        return link_entry

    def get_decision_with_trades(self, decision_id):
        """Get a decision and all its linked trades.

        Args:
            decision_id: The UUID of the decision.

        Returns:
            The decision dict with a populated trade_outcomes list,
            or None if not found.
        """
        decision = self._find_decision(decision_id)
        if decision is None:
            return None

        # Ensure trade_outcomes is populated from trade_links file
        trade_links = self._read_trade_links()
        linked = [t for t in trade_links if t.get("decision_id") == decision_id]
        decision["trade_outcomes"] = linked
        return decision

    def get_trade_success_rate(self, strategy_id=None):
        """Calculate success metrics optionally filtered by strategy.

        Args:
            strategy_id: If provided, only consider decisions for this strategy.

        Returns:
            Dict with keys: total_decisions, linked_decisions, total_trades,
            wins, losses, win_rate, avg_pnl.
        """
        journal = self._read_journal()
        trade_links = self._read_trade_links()

        if strategy_id is not None:
            relevant_ids = {
                e["decision_id"]
                for e in journal
                if e.get("strategy_id") == strategy_id and "decision_id" in e
            }
            filtered_journal = [
                e for e in journal
                if e.get("strategy_id") == strategy_id
            ]
            filtered_links = [
                t for t in trade_links if t.get("decision_id") in relevant_ids
            ]
        else:
            relevant_ids = {
                e["decision_id"] for e in journal if "decision_id" in e
            }
            filtered_journal = journal
            filtered_links = trade_links

        linked_decision_ids = {t.get("decision_id") for t in filtered_links}

        pnl_values = [
            t["pnl"] for t in filtered_links
            if t.get("pnl") is not None
        ]
        wins = sum(1 for p in pnl_values if p > 0)
        losses = sum(1 for p in pnl_values if p <= 0)
        avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0

        return {
            "total_decisions": len(filtered_journal),
            "linked_decisions": len(linked_decision_ids),
            "total_trades": len(filtered_links),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(pnl_values) if pnl_values else 0.0,
            "avg_pnl": avg_pnl,
        }

    def get_unlinked_decisions(self, limit=50):
        """Get decisions that have no trade outcomes linked.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of decision dicts with no linked trades.
        """
        trade_links = self._read_trade_links()
        linked_ids = {t.get("decision_id") for t in trade_links}
        journal = self._read_journal()
        unlinked = [
            e for e in journal
            if e.get("decision_id") and e["decision_id"] not in linked_ids
        ]
        return unlinked[:limit]

    # -- Upgrade A: Multi-timeframe Decision Evaluation ---------------------

    def record_timeframe_evaluation(self, decision_id, timeframe, outcome_data):
        """Record an evaluation for a decision at a specific timeframe window.

        Stores the outcome_data under the given timeframe key inside the
        decision's ``timeframe_evaluations`` dict and rewrites the journal.

        Args:
            decision_id: The UUID of the decision to evaluate.
            timeframe: One of the EVALUATION_TIMEFRAMES labels
                       (e.g. "T+1h", "T+1d", "T+7d", "T+30d").
            outcome_data: Dict containing evaluation details.  Expected keys
                          include ``pnl``, ``outcome`` ("win"/"loss"/"neutral"),
                          and any additional context.

        Returns:
            The updated decision dict, or None if the decision was not found.
        """
        if timeframe not in EVALUATION_TIMEFRAMES:
            logger.warning(
                "record_timeframe_evaluation: unknown timeframe %s (expected one of %s)",
                timeframe, EVALUATION_TIMEFRAMES,
            )

        filepath = os.path.join(self.journal_path, "journal.jsonl")
        entries = self._read_journal()
        target = None
        for entry in entries:
            if entry.get("decision_id") == decision_id:
                target = entry
                break

        if target is None:
            logger.warning("record_timeframe_evaluation: decision_id %s not found", decision_id)
            return None

        if "timeframe_evaluations" not in target:
            target["timeframe_evaluations"] = {}

        outcome_data_copy = dict(outcome_data) if outcome_data else {}
        outcome_data_copy.setdefault("recorded_at", int(time.time()))
        target["timeframe_evaluations"][timeframe] = outcome_data_copy

        try:
            with open(filepath, "w") as fh:
                for entry in entries:
                    fh.write(json.dumps(entry) + "\n")
        except OSError as exc:
            logger.error("Failed to update journal with timeframe evaluation: %s", exc)

        logger.info(
            "Recorded %s evaluation for decision %s", timeframe, decision_id
        )
        return target

    def get_decision_maturity(self, decision_id):
        """Return the maturity status of a decision's multi-timeframe evaluations.

        The maturity score is the fraction of ``EVALUATION_TIMEFRAMES`` that
        have been evaluated (0.0 .. 1.0).

        Args:
            decision_id: The UUID of the decision.

        Returns:
            Dict with keys: decision_id, evaluated_timeframes (list),
            pending_timeframes (list), evaluated_count, total_timeframes,
            maturity_score.  Returns None if the decision is not found.
        """
        decision = self._find_decision(decision_id)
        if decision is None:
            return None

        evals = decision.get("timeframe_evaluations", {})
        evaluated = [tf for tf in EVALUATION_TIMEFRAMES if tf in evals]
        pending = [tf for tf in EVALUATION_TIMEFRAMES if tf not in evals]
        total = len(EVALUATION_TIMEFRAMES)

        return {
            "decision_id": decision_id,
            "evaluated_timeframes": evaluated,
            "pending_timeframes": pending,
            "evaluated_count": len(evaluated),
            "total_timeframes": total,
            "maturity_score": len(evaluated) / total if total else 0.0,
        }

    def get_multi_timeframe_performance(self, strategy_id=None):
        """Aggregate win rates across all evaluation timeframes.

        Allows the strategy-evolution module to see how a decision's perceived
        quality changes over time (e.g. bad at T+1h but good at T+7d).

        Args:
            strategy_id: If provided, only consider decisions for this strategy.

        Returns:
            Dict keyed by timeframe label, each value is a dict with:
            total, wins, losses, neutral, win_rate, avg_pnl.
            Also includes an ``overall`` key aggregating all timeframes.
        """
        journal = self._read_journal()
        if strategy_id is not None:
            journal = [e for e in journal if e.get("strategy_id") == strategy_id]

        results = {}
        for tf in EVALUATION_TIMEFRAMES:
            results[tf] = {"total": 0, "wins": 0, "losses": 0, "neutral": 0, "pnl_values": []}

        for entry in journal:
            evals = entry.get("timeframe_evaluations", {})
            for tf in EVALUATION_TIMEFRAMES:
                if tf not in evals:
                    continue
                ev = evals[tf]
                results[tf]["total"] += 1
                outcome = ev.get("outcome", "").lower()
                if outcome == "win":
                    results[tf]["wins"] += 1
                elif outcome == "loss":
                    results[tf]["losses"] += 1
                else:
                    results[tf]["neutral"] += 1
                if ev.get("pnl") is not None:
                    results[tf]["pnl_values"].append(ev["pnl"])

        # Build final output with win_rate / avg_pnl and remove temp pnl_values
        overall = {"total": 0, "wins": 0, "losses": 0, "neutral": 0, "pnl_values": []}
        for tf in EVALUATION_TIMEFRAMES:
            bucket = results[tf]
            pnl_vals = bucket.pop("pnl_values")
            bucket["win_rate"] = bucket["wins"] / bucket["total"] if bucket["total"] else 0.0
            bucket["avg_pnl"] = sum(pnl_vals) / len(pnl_vals) if pnl_vals else 0.0
            overall["total"] += bucket["total"]
            overall["wins"] += bucket["wins"]
            overall["losses"] += bucket["losses"]
            overall["neutral"] += bucket["neutral"]
            overall["pnl_values"].extend(pnl_vals)

        overall_pnl = overall.pop("pnl_values")
        overall["win_rate"] = overall["wins"] / overall["total"] if overall["total"] else 0.0
        overall["avg_pnl"] = sum(overall_pnl) / len(overall_pnl) if overall_pnl else 0.0
        results["overall"] = overall

        return results

    # -- Upgrade B: Degradation Audit Chain --------------------------------

    def record_degradation_attestation(self, agent_name, attestation_data):
        """Record a degradation attestation for an agent.

        Persists the attestation to ``degradation_attestations.jsonl``.

        Args:
            agent_name: Identifier for the agent recording the attestation.
            attestation_data: Dict that should include:
                available_submodules (list), unavailable_submodules (list),
                degradation_reason (str), partial_reasoning_chain (list/str),
                confidence_level (float 0-1), timestamp (int, optional).

        Returns:
            The stored attestation record dict.
        """
        record = {
            "id": str(uuid.uuid4()),
            "agent_name": agent_name,
            "available_submodules": attestation_data.get("available_submodules", []),
            "unavailable_submodules": attestation_data.get("unavailable_submodules", []),
            "degradation_reason": attestation_data.get("degradation_reason", ""),
            "partial_reasoning_chain": attestation_data.get("partial_reasoning_chain", []),
            "confidence_level": attestation_data.get("confidence_level", 1.0),
            "timestamp": attestation_data.get("timestamp", int(time.time())),
            "decision_id": attestation_data.get("decision_id"),
        }

        try:
            with open(self.degradation_path, "a") as fh:
                fh.write(json.dumps(record) + "\n")
        except OSError as exc:
            logger.error("Failed to write degradation attestation: %s", exc)

        logger.info(
            "Degradation attestation recorded for agent %s (reason=%s)",
            agent_name, record["degradation_reason"],
        )
        return record

    def get_degradation_history(self, agent_name=None, limit=50):
        """Query degradation attestation records.

        Args:
            agent_name: If provided, filter attestations to this agent.
            limit: Maximum number of records to return (most recent first).

        Returns:
            List of attestation dicts, ordered most-recent-first.
        """
        records = self._read_degradation_attestations()
        if agent_name is not None:
            records = [r for r in records if r.get("agent_name") == agent_name]
        # Most recent first
        records.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
        return records[:limit]

    def get_degradation_impact(self, agent_name):
        """Correlate degraded decisions with trade outcomes for an agent.

        Identifies decisions that were made while the agent was in a degraded
        state and computes performance metrics for those decisions versus
        non-degraded decisions, enabling measurement of degradation impact.

        Args:
            agent_name: The agent whose degradation impact to measure.

        Returns:
            Dict with keys: agent_name, degraded_decision_ids,
            degraded_stats (wins, losses, win_rate, avg_pnl, total_trades),
            normal_stats (same shape), delta_win_rate, delta_avg_pnl.
        """
        attestations = self._read_degradation_attestations()
        agent_attestations = [a for a in attestations if a.get("agent_name") == agent_name]

        # Collect decision_ids linked to degradation attestations
        degraded_decision_ids = set()
        for att in agent_attestations:
            did = att.get("decision_id")
            if did:
                degraded_decision_ids.add(did)

        journal = self._read_journal()
        trade_links = self._read_trade_links()

        # Build decision_id -> trade_links mapping
        trade_map = {}
        for t in trade_links:
            did = t.get("decision_id")
            if did:
                trade_map.setdefault(did, []).append(t)

        def _compute_stats(decision_ids):
            trades = []
            for did in decision_ids:
                trades.extend(trade_map.get(did, []))
            pnl_values = [t["pnl"] for t in trades if t.get("pnl") is not None]
            wins = sum(1 for p in pnl_values if p > 0)
            losses = sum(1 for p in pnl_values if p <= 0)
            return {
                "total_trades": len(trades),
                "wins": wins,
                "losses": losses,
                "win_rate": wins / len(pnl_values) if pnl_values else 0.0,
                "avg_pnl": sum(pnl_values) / len(pnl_values) if pnl_values else 0.0,
            }

        all_decision_ids = {e.get("decision_id") for e in journal if e.get("decision_id")}
        normal_decision_ids = all_decision_ids - degraded_decision_ids

        degraded_stats = _compute_stats(degraded_decision_ids)
        normal_stats = _compute_stats(normal_decision_ids)

        return {
            "agent_name": agent_name,
            "degraded_decision_ids": sorted(degraded_decision_ids),
            "degraded_stats": degraded_stats,
            "normal_stats": normal_stats,
            "delta_win_rate": degraded_stats["win_rate"] - normal_stats["win_rate"],
            "delta_avg_pnl": degraded_stats["avg_pnl"] - normal_stats["avg_pnl"],
        }

    # -- private helpers ---------------------------------------------------

    def _log_local(self, entry):
        """Append a JSON entry as one line to the local JSONL journal."""
        filepath = os.path.join(self.journal_path, "journal.jsonl")
        try:
            with open(filepath, "a") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError as exc:
            logger.error("Failed to write local journal: %s", exc)

    def _log_onchain(self, strategy_id, decision_type_hex, reasoning_hash, params_bytes):
        """Call the assembler's logDecision via onchainos CLI."""
        cmd = [
            "onchainos", "wallet", "call",
            "--to", self.assembler,
            "--function",
            'logDecision(uint256,bytes32,bytes32,bytes)',
            "--args",
            str(strategy_id),
            decision_type_hex,
            reasoning_hash,
            params_bytes,
            "--index", "1",
        ]
        logger.debug("On-chain call: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"onchainos call failed (rc={result.returncode}): {result.stderr.strip()}")
        logger.debug("On-chain tx output: %s", result.stdout.strip())

    def _read_journal(self):
        """Read all entries from the local JSONL journal file."""
        filepath = os.path.join(self.journal_path, "journal.jsonl")
        entries = []
        if not os.path.isfile(filepath):
            return entries
        try:
            with open(filepath, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to read journal: %s", exc)
        return entries

    def _next_id(self):
        """Return the next sequential decision id."""
        return self.get_decision_count() + 1

    def _encode_params(self, params):
        """Encode params dict to a hex-string for on-chain submission."""
        if not params:
            return "0x"
        raw = json.dumps(params, separators=(",", ":"), sort_keys=True)
        return "0x" + raw.encode("utf-8").hex()

    def _ensure_journal_dir(self):
        """Create the local journal directory if it doesn't exist."""
        os.makedirs(self.journal_path, exist_ok=True)

    def _find_decision(self, decision_id):
        """Find a single decision entry by decision_id."""
        for entry in self._read_journal():
            if entry.get("decision_id") == decision_id:
                return entry
        return None

    def _append_trade_link(self, link_entry):
        """Append a trade link entry to the trade_links.jsonl file."""
        try:
            with open(self.trade_links_path, "a") as fh:
                fh.write(json.dumps(link_entry) + "\n")
        except OSError as exc:
            logger.error("Failed to write trade link: %s", exc)

    def _read_trade_links(self):
        """Read all entries from the trade_links.jsonl file."""
        entries = []
        if not os.path.isfile(self.trade_links_path):
            return entries
        try:
            with open(self.trade_links_path, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to read trade links: %s", exc)
        return entries

    def _append_trade_outcome(self, decision_id, link_entry):
        """Update the journal file in-place to add a trade outcome to a decision.

        Rewrites the journal JSONL to append the link_entry into the
        matching decision's trade_outcomes list.
        """
        filepath = os.path.join(self.journal_path, "journal.jsonl")
        entries = self._read_journal()
        updated = False
        for entry in entries:
            if entry.get("decision_id") == decision_id:
                if "trade_outcomes" not in entry:
                    entry["trade_outcomes"] = []
                entry["trade_outcomes"].append(link_entry)
                updated = True
                break
        if updated:
            try:
                with open(filepath, "w") as fh:
                    for entry in entries:
                        fh.write(json.dumps(entry) + "\n")
            except OSError as exc:
                logger.error("Failed to update journal with trade outcome: %s", exc)

    def _read_degradation_attestations(self):
        """Read all entries from the degradation_attestations.jsonl file."""
        entries = []
        if not os.path.isfile(self.degradation_path):
            return entries
        try:
            with open(self.degradation_path, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to read degradation attestations: %s", exc)
        return entries
