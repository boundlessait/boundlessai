from pathlib import Path
import importlib
import json


def test_load_transactions_normalizes_legacy_outcome(tmp_path, monkeypatch):
    monkeypatch.setenv("X402_DATA_DIR", str(tmp_path))

    import storage
    storage = importlib.reload(storage)

    tx_file = Path(tmp_path) / "transactions.json"
    tx_file.write_text(json.dumps([
        {"id": "1", "agent_id": "agent-alpha", "amount": 5, "outcome": "blocked"},
        {"id": "2", "agent_id": "agent-alpha", "amount": 3},
    ]))

    txs = storage.load_transactions()

    assert txs[0]["status"] == "blocked"
    assert "outcome" not in txs[0]
    assert txs[1]["status"] == "approved"
