"""Forensic Settlement Bridge - cryptographic intent-hash commitments for evidence-based settlement.

Implements the Intent-Hash commitment pattern inspired by community contributor
michaelagent0xd's concept.  At decision time (T=0) a cryptographic hash locks
the decision parameters.  Settlement can later verify that the actual trade
matched the original intent, producing a match score and per-field deviations.

Core flow:
  1. ``create_intent_commitment(params)`` -- generate SHA-256 intent hash that
     commits to strategy_id, action, price_target, confidence, timestamp, nonce.
  2. ``verify_settlement(commitment_id, actual_trade_data)`` -- compare the
     actual trade against the committed intent and return a match score.
  3. Helper methods for querying, revoking, and aggregating bridge statistics.

Uses only the Python standard library (hashlib, uuid, collections, etc.).
"""

import hashlib
import json
import logging
import time
import uuid
from collections import deque

logger = logging.getLogger("genesis.forensic_bridge")


class ForensicBridge:
    """Cryptographic intent-hash commitments for evidence-based settlement."""

    def __init__(self):
        """Initialize with empty registries for commitments, verifications, and revocations."""
        self._commitments = {}       # commitment_id -> commitment record
        self._verifications = deque(maxlen=1000)  # rolling verification history
        self._revocations = {}       # commitment_id -> revocation record

    # -- public API --------------------------------------------------------

    def create_intent_commitment(self, decision_params):
        """Create a cryptographic intent-hash commitment for a trading decision.

        Locks the decision parameters at T=0 so that settlement can later
        prove the trade matched the original intent.

        Args:
            decision_params: Dict with keys such as strategy_id, action,
                price_target, confidence, timestamp.  A random nonce is
                injected automatically.

        Returns:
            Dict with keys: intent_hash, commitment_id, committed_at,
            params_hash.
        """
        now = int(time.time())
        nonce = uuid.uuid4().hex
        commitment_id = str(uuid.uuid4())

        # Build the full params with injected nonce and timestamp
        full_params = dict(decision_params)
        full_params["nonce"] = nonce
        if "timestamp" not in full_params:
            full_params["timestamp"] = now

        intent_hash = self._compute_intent_hash(full_params)

        # params_hash covers only the caller-supplied fields (no nonce)
        params_hash = self._compute_intent_hash(decision_params)

        record = {
            "commitment_id": commitment_id,
            "intent_hash": intent_hash,
            "params_hash": params_hash,
            "committed_at": now,
            "nonce": nonce,
            "params": full_params,
            "status": "active",
        }
        self._commitments[commitment_id] = record

        logger.info(
            "Intent commitment created: id=%s hash=%s",
            commitment_id, intent_hash[:16] + "...",
        )

        return {
            "intent_hash": intent_hash,
            "commitment_id": commitment_id,
            "committed_at": now,
            "params_hash": params_hash,
        }

    def verify_settlement(self, commitment_id, actual_trade_data):
        """Verify how closely an actual trade matched the committed intent.

        Args:
            commitment_id: The UUID string returned by create_intent_commitment.
            actual_trade_data: Dict with keys mirroring the original params
                (e.g. action, price_target, confidence, timestamp).

        Returns:
            Dict with keys: verified (bool), match_score (float 0-1),
            deviations (dict of per-field comparisons).
        """
        record = self._commitments.get(commitment_id)
        if record is None:
            return {
                "verified": False,
                "match_score": 0.0,
                "deviations": {},
                "error": "Commitment not found",
            }

        if record.get("status") == "revoked":
            return {
                "verified": False,
                "match_score": 0.0,
                "deviations": {},
                "error": "Commitment has been revoked",
            }

        committed_params = record["params"]
        match_score, deviations = self._calculate_match_score(
            committed_params, actual_trade_data,
        )

        verified = match_score >= 0.7

        verification_entry = {
            "commitment_id": commitment_id,
            "verified": verified,
            "match_score": match_score,
            "deviations": deviations,
            "actual_data": actual_trade_data,
            "verified_at": int(time.time()),
        }
        self._verifications.append(verification_entry)

        logger.info(
            "Settlement verification: id=%s verified=%s score=%.4f",
            commitment_id, verified, match_score,
        )

        return {
            "verified": verified,
            "match_score": match_score,
            "deviations": deviations,
        }

    def get_commitment(self, commitment_id):
        """Return the commitment record for a given commitment_id.

        Args:
            commitment_id: The UUID string of the commitment.

        Returns:
            The commitment dict, or None if not found.
        """
        return self._commitments.get(commitment_id)

    def get_verification_history(self, commitment_id=None, limit=50):
        """Return verification records, optionally filtered by commitment_id.

        Args:
            commitment_id: If provided, only return verifications for this id.
            limit: Maximum number of records to return (default 50).

        Returns:
            List of verification record dicts, most recent first.
        """
        records = list(self._verifications)
        records.reverse()

        if commitment_id is not None:
            records = [
                r for r in records if r.get("commitment_id") == commitment_id
            ]

        return records[:limit]

    def get_bridge_stats(self):
        """Return aggregate statistics about the forensic bridge.

        Returns:
            Dict with keys: total_commitments, total_verifications,
            average_match_score, unverified_commitments_count.
        """
        total_commitments = len(self._commitments)
        total_verifications = len(self._verifications)

        scores = [v["match_score"] for v in self._verifications]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        verified_ids = {v["commitment_id"] for v in self._verifications}
        unverified_count = sum(
            1 for cid, rec in self._commitments.items()
            if cid not in verified_ids and rec.get("status") != "revoked"
        )

        return {
            "total_commitments": total_commitments,
            "total_verifications": total_verifications,
            "average_match_score": round(avg_score, 6),
            "unverified_commitments_count": unverified_count,
        }

    def get_unverified_commitments(self, max_age_hours=24):
        """Return commitments that have not been verified within the time window.

        Args:
            max_age_hours: Only include commitments created within this many
                hours (default 24).

        Returns:
            List of commitment dicts that lack a verification record.
        """
        now = int(time.time())
        cutoff = now - (max_age_hours * 3600)
        verified_ids = {v["commitment_id"] for v in self._verifications}

        unverified = []
        for cid, rec in self._commitments.items():
            if rec.get("status") == "revoked":
                continue
            if cid in verified_ids:
                continue
            if rec.get("committed_at", 0) < cutoff:
                continue
            unverified.append(rec)

        # Sort by committed_at descending (most recent first)
        unverified.sort(key=lambda r: r.get("committed_at", 0), reverse=True)
        return unverified

    def revoke_commitment(self, commitment_id, reason):
        """Mark a commitment as revoked (e.g. market conditions changed).

        Args:
            commitment_id: The UUID string of the commitment to revoke.
            reason: Human-readable explanation for the revocation.

        Returns:
            Dict with keys: revoked (bool), commitment_id, reason,
            revoked_at.
        """
        record = self._commitments.get(commitment_id)
        if record is None:
            return {
                "revoked": False,
                "error": "Commitment not found",
            }

        if record.get("status") == "revoked":
            return {
                "revoked": False,
                "error": "Commitment already revoked",
            }

        now = int(time.time())
        record["status"] = "revoked"

        self._revocations[commitment_id] = {
            "commitment_id": commitment_id,
            "reason": reason,
            "revoked_at": now,
        }

        logger.info("Commitment revoked: id=%s reason=%s", commitment_id, reason)

        return {
            "revoked": True,
            "commitment_id": commitment_id,
            "reason": reason,
            "revoked_at": now,
        }

    # -- private helpers ---------------------------------------------------

    def _compute_intent_hash(self, params):
        """Compute a SHA-256 hex digest over the canonical JSON of *params*.

        The params dict is serialised with sorted keys and compact separators
        to guarantee deterministic output.

        Args:
            params: Dict of decision parameters (including nonce).

        Returns:
            Hex string of the SHA-256 digest.
        """
        canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _calculate_match_score(self, committed_params, actual_data):
        """Score how closely *actual_data* matches *committed_params*.

        Scoring rules:
          - action:       1.0 if exact match, else 0.0
          - price_target: 1.0 minus the absolute percentage deviation, floored at 0.0
          - confidence:   1.0 minus the absolute difference, floored at 0.0
          - timing:       1.0 if within 60 s, decays linearly to 0.0 at 3600 s

        The final score is the weighted average (equal weights).

        Args:
            committed_params: The original decision params dict.
            actual_data: The actual trade data dict.

        Returns:
            Tuple of (match_score: float, deviations: dict).
        """
        scores = {}
        deviations = {}

        # Action match (exact string comparison)
        committed_action = str(committed_params.get("action", "")).lower()
        actual_action = str(actual_data.get("action", "")).lower()
        action_match = 1.0 if committed_action == actual_action else 0.0
        scores["action"] = action_match
        deviations["action"] = {
            "committed": committed_params.get("action"),
            "actual": actual_data.get("action"),
            "match": bool(action_match),
        }

        # Price target deviation (percentage)
        committed_price = float(committed_params.get("price_target", 0))
        actual_price = float(actual_data.get("price_target", 0))
        if committed_price > 0:
            price_pct_dev = abs(actual_price - committed_price) / committed_price
            price_score = max(0.0, 1.0 - price_pct_dev)
        else:
            price_pct_dev = 0.0
            price_score = 1.0 if actual_price == 0 else 0.0
        scores["price_target"] = price_score
        deviations["price_target"] = {
            "committed": committed_price,
            "actual": actual_price,
            "deviation_pct": round(price_pct_dev * 100, 4),
        }

        # Confidence deviation (absolute difference on 0-1 scale)
        committed_conf = float(committed_params.get("confidence", 0))
        actual_conf = float(actual_data.get("confidence", 0))
        conf_diff = abs(actual_conf - committed_conf)
        conf_score = max(0.0, 1.0 - conf_diff)
        scores["confidence"] = conf_score
        deviations["confidence"] = {
            "committed": committed_conf,
            "actual": actual_conf,
            "absolute_diff": round(conf_diff, 4),
        }

        # Timing deviation (linear decay: perfect within 60s, zero at 3600s)
        committed_ts = float(committed_params.get("timestamp", 0))
        actual_ts = float(actual_data.get("timestamp", 0))
        timing_delta = abs(actual_ts - committed_ts)
        if timing_delta <= 60:
            timing_score = 1.0
        elif timing_delta >= 3600:
            timing_score = 0.0
        else:
            timing_score = 1.0 - (timing_delta - 60) / (3600 - 60)
        scores["timing"] = timing_score
        deviations["timing"] = {
            "committed_ts": committed_ts,
            "actual_ts": actual_ts,
            "delta_seconds": round(timing_delta, 2),
        }

        # Weighted average (equal weights)
        match_score = sum(scores.values()) / len(scores) if scores else 0.0
        return round(match_score, 6), deviations
