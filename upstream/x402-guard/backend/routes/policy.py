from fastapi import APIRouter, HTTPException
from typing import List
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Policy, PolicyCreate, PolicyUpdate
import storage

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("/", response_model=List[Policy], summary="List all policies")
async def list_policies():
    """Return all stored policies."""
    return [Policy(**p) for p in storage.load_policies()]


@router.get("/{policy_id}", response_model=Policy, summary="Get a policy by ID")
async def get_policy(policy_id: str):
    p = storage.get_policy(policy_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id!r} not found.")
    return Policy(**p)


@router.get("/agent/{agent_id}", response_model=List[Policy], summary="Get all policies for an agent")
async def get_policies_for_agent(agent_id: str):
    all_policies = storage.load_policies()
    agent_policies = [Policy(**p) for p in all_policies if p.get("agent_id") == agent_id]
    return agent_policies


@router.post("/", response_model=Policy, status_code=201, summary="Create a new policy")
async def create_policy(body: PolicyCreate):
    """
    Create a spending policy for an AI agent.

    Example body:
    {
      "agent_id": "agent-001",
      "name": "Strict Daily Policy",
      "daily_limit": 50.0,
      "hourly_limit": 10.0,
      "per_tx_limit": 5.0,
      "whitelist": ["0xRecipientThatIsAlwaysOk"],
      "blacklist": ["0xBadActor"],
      "soft_alert_threshold": 0.8
    }
    """
    policy = Policy(**body.model_dump())
    storage.create_policy(policy.model_dump())
    return policy


@router.patch("/{policy_id}", response_model=Policy, summary="Update an existing policy")
async def update_policy(policy_id: str, body: PolicyUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No update fields provided.")
    updated = storage.update_policy(policy_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id!r} not found.")
    return Policy(**updated)


@router.put("/{policy_id}", response_model=Policy, summary="Replace a policy")
async def replace_policy(policy_id: str, body: PolicyCreate):
    existing = storage.get_policy(policy_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id!r} not found.")
    updates = body.model_dump()
    updated = storage.update_policy(policy_id, updates)
    return Policy(**updated)


@router.delete("/{policy_id}", summary="Delete a policy")
async def delete_policy(policy_id: str):
    deleted = storage.delete_policy(policy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id!r} not found.")
    return {"deleted": True, "policy_id": policy_id}


@router.post("/{policy_id}/deactivate", response_model=Policy, summary="Deactivate a policy")
async def deactivate_policy(policy_id: str):
    updated = storage.update_policy(policy_id, {"active": False})
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id!r} not found.")
    return Policy(**updated)


@router.post("/{policy_id}/activate", response_model=Policy, summary="Activate a policy")
async def activate_policy(policy_id: str):
    updated = storage.update_policy(policy_id, {"active": True})
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id!r} not found.")
    return Policy(**updated)
