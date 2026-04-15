import json
import os
import threading
import time
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime, timezone

# Module-level lock — ONLY for writes (read-modify-write cycles).
# Reads use atomic file replacement so no lock needed.
_write_lock = threading.Lock()

# Simple in-memory read cache — invalidated on each write.
_tx_cache: List[Dict[str, Any]] = []
_tx_cache_ts: float = 0.0
_TX_CACHE_TTL = 3.0   # seconds

_pol_cache: List[Dict[str, Any]] = []
_pol_cache_ts: float = 0.0
_POL_CACHE_TTL = 5.0  # seconds


DATA_DIR = Path(os.environ.get("X402_DATA_DIR", Path(__file__).parent / "data"))
POLICIES_FILE    = DATA_DIR / "policies.json"
TRANSACTIONS_FILE = DATA_DIR / "transactions.json"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(filepath: Path) -> List[Dict[str, Any]]:
    _ensure_data_dir()
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _write_json(filepath: Path, data: List[Dict[str, Any]]) -> None:
    _ensure_data_dir()
    # Atomic write: write to tmp then rename — readers always see complete file.
    tmp = filepath.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    tmp.replace(filepath)


# ── Policies ──────────────────────────────────────────────────────────────────

def load_policies() -> List[Dict[str, Any]]:
    global _pol_cache, _pol_cache_ts
    now = time.monotonic()
    if now - _pol_cache_ts < _POL_CACHE_TTL and _pol_cache is not None:
        return list(_pol_cache)
    data = _read_json(POLICIES_FILE)
    _pol_cache = data
    _pol_cache_ts = now
    return list(data)


def save_policies(policies: List[Dict[str, Any]]) -> None:
    global _pol_cache, _pol_cache_ts
    with _write_lock:
        _write_json(POLICIES_FILE, policies)
        _pol_cache = list(policies)
        _pol_cache_ts = time.monotonic()


def get_policy(policy_id: str) -> Optional[Dict[str, Any]]:
    for p in load_policies():
        if p.get("id") == policy_id:
            return p
    return None


def get_policy_for_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    """Return the most recently created active policy for an agent."""
    policies = [
        p for p in load_policies()
        if p.get("agent_id") == agent_id and p.get("active", True)
    ]
    if not policies:
        return None
    policies.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return policies[0]


def update_policy(policy_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    global _pol_cache, _pol_cache_ts
    with _write_lock:
        policies = _read_json(POLICIES_FILE)
        for i, p in enumerate(policies):
            if p.get("id") == policy_id:
                policies[i].update(updates)
                policies[i]["updated_at"] = datetime.now(timezone.utc).isoformat()
                _write_json(POLICIES_FILE, policies)
                _pol_cache = list(policies)
                _pol_cache_ts = time.monotonic()
                return policies[i]
    return None


def delete_policy(policy_id: str) -> bool:
    global _pol_cache, _pol_cache_ts
    with _write_lock:
        policies = _read_json(POLICIES_FILE)
        new_policies = [p for p in policies if p.get("id") != policy_id]
        if len(new_policies) == len(policies):
            return False
        _write_json(POLICIES_FILE, new_policies)
        _pol_cache = list(new_policies)
        _pol_cache_ts = time.monotonic()
    return True


def create_policy(policy_dict: Dict[str, Any]) -> Dict[str, Any]:
    global _pol_cache, _pol_cache_ts
    with _write_lock:
        policies = _read_json(POLICIES_FILE)
        policies.append(policy_dict)
        _write_json(POLICIES_FILE, policies)
        _pol_cache = list(policies)
        _pol_cache_ts = time.monotonic()
    return policy_dict


# ── Transactions ──────────────────────────────────────────────────────────────

def _normalize_tx(t: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize legacy 'outcome' field to 'status' for consistency."""
    if "status" not in t and "outcome" in t:
        t = dict(t)
        t["status"] = t.pop("outcome")
    elif "status" not in t:
        t = dict(t)
        t["status"] = "approved"
    return t


def load_transactions() -> List[Dict[str, Any]]:
    global _tx_cache, _tx_cache_ts
    now = time.monotonic()
    if now - _tx_cache_ts < _TX_CACHE_TTL and _tx_cache is not None:
        return list(_tx_cache)
    data = [_normalize_tx(t) for t in _read_json(TRANSACTIONS_FILE)]
    _tx_cache = data
    _tx_cache_ts = now
    return list(data)


def save_transactions(transactions: List[Dict[str, Any]]) -> None:
    global _tx_cache, _tx_cache_ts
    with _write_lock:
        _write_json(TRANSACTIONS_FILE, transactions)
        _tx_cache = list(transactions)
        _tx_cache_ts = time.monotonic()


def store_transaction(tx_dict: Dict[str, Any]) -> Dict[str, Any]:
    global _tx_cache, _tx_cache_ts
    with _write_lock:
        transactions = _read_json(TRANSACTIONS_FILE)
        transactions.append(tx_dict)
        _write_json(TRANSACTIONS_FILE, transactions)
        _tx_cache = list(transactions)
        _tx_cache_ts = time.monotonic()
    return tx_dict


def get_transactions_for_agent(agent_id: str) -> List[Dict[str, Any]]:
    return [t for t in load_transactions() if t.get("agent_id") == agent_id]


def get_transaction(tx_id: str) -> Optional[Dict[str, Any]]:
    for t in load_transactions():
        if t.get("id") == tx_id:
            return t
    return None
