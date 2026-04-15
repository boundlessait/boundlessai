import importlib


def _setup_modules(tmp_path, monkeypatch):
    monkeypatch.setenv("X402_DATA_DIR", str(tmp_path))
    import storage
    import policy_engine
    storage = importlib.reload(storage)
    policy_engine = importlib.reload(policy_engine)
    return storage, policy_engine


def _create_policy(storage, Policy, **overrides):
    data = {
        "agent_id": "agent-alpha",
        "name": "Sniper Bot #1",
        "daily_limit": 100.0,
        "hourly_limit": 30.0,
        "per_tx_limit": 15.0,
        "auto_approve_under": 0.01,
    }
    data.update(overrides)
    policy = Policy(**data)
    storage.create_policy(policy.model_dump())
    return policy


def test_blacklist_blocks_and_whitelist_bypasses_limits(tmp_path, monkeypatch):
    storage, policy_engine = _setup_modules(tmp_path, monkeypatch)
    from models import GuardRequest, Policy

    _create_policy(
        storage,
        Policy,
        whitelist=["0xwhitelist"],
        blacklist=["0xblocked"],
        daily_limit=1.0,
        hourly_limit=1.0,
        per_tx_limit=0.5,
    )
    engine = policy_engine.PolicyEngine()

    blocked = engine.check_and_approve(GuardRequest(
        agent_id="agent-alpha",
        amount=0.2,
        pay_to="0xBlocked",
        asset=policy_engine.DEFAULT_ASSET,
        network=policy_engine.X_LAYER_CAIP2,
    ))
    approved = engine.check_and_approve(GuardRequest(
        agent_id="agent-alpha",
        amount=9.0,
        pay_to="0xWhitelist",
        asset=policy_engine.DEFAULT_ASSET,
        network=policy_engine.X_LAYER_CAIP2,
    ))

    assert blocked.action == "block"
    assert blocked.allowed is False
    assert "blacklisted" in blocked.reason.lower()
    assert approved.action == "approve"
    assert approved.allowed is True
    assert "whitelisted" in approved.reason.lower()


def test_daily_soft_alert_then_block(tmp_path, monkeypatch):
    storage, policy_engine = _setup_modules(tmp_path, monkeypatch)
    from models import GuardRequest, Policy

    _create_policy(storage, Policy, daily_limit=100.0, hourly_limit=1000.0, per_tx_limit=100.0)
    engine = policy_engine.PolicyEngine()

    first = engine.check_and_approve(GuardRequest(
        agent_id="agent-alpha",
        amount=85.0,
        pay_to="0xrecipient-a",
        asset=policy_engine.DEFAULT_ASSET,
        network=policy_engine.X_LAYER_CAIP2,
    ))
    second = engine.check_and_approve(GuardRequest(
        agent_id="agent-alpha",
        amount=10.0,
        pay_to="0xrecipient-b",
        asset=policy_engine.DEFAULT_ASSET,
        network=policy_engine.X_LAYER_CAIP2,
    ))
    third = engine.check_and_approve(GuardRequest(
        agent_id="agent-alpha",
        amount=10.0,
        pay_to="0xrecipient-c",
        asset=policy_engine.DEFAULT_ASSET,
        network=policy_engine.X_LAYER_CAIP2,
    ))

    assert first.action == "soft_alert"
    assert first.allowed is True
    assert second.action == "soft_alert"
    assert second.allowed is True
    assert third.action == "block"
    assert third.allowed is False
    assert "daily" in third.reason.lower()
