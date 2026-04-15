from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import datetime, timezone
import uuid


class Policy(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Default Policy"
    agent_id: str
    # Bot identity
    wallet_address: Optional[str] = None   # bot's wallet address on X Layer
    bot_type: Optional[str] = None         # "sniper" | "arbitrage" | "prediction" | "sentiment" | "custom"
    description: Optional[str] = None
    # Spending limits
    daily_limit: float = 100.0
    hourly_limit: float = 20.0
    per_tx_limit: float = 10.0
    session_limit: Optional[float] = None
    whitelist: List[str] = Field(default_factory=list)
    blacklist: List[str] = Field(default_factory=list)
    auto_approve_under: float = 0.01
    soft_alert_threshold: float = 0.8
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active: bool = True


class PolicyCreate(BaseModel):
    name: str = "Default Policy"
    agent_id: str
    wallet_address: Optional[str] = None
    bot_type: Optional[str] = None
    description: Optional[str] = None
    daily_limit: float = 100.0
    hourly_limit: float = 20.0
    per_tx_limit: float = 10.0
    session_limit: Optional[float] = None
    whitelist: List[str] = Field(default_factory=list)
    blacklist: List[str] = Field(default_factory=list)
    auto_approve_under: float = 0.01
    soft_alert_threshold: float = 0.8

    @field_validator("daily_limit", "hourly_limit", "per_tx_limit")
    @classmethod
    def limits_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"limit must be greater than 0, got {v}")
        return v

    @field_validator("soft_alert_threshold")
    @classmethod
    def threshold_must_be_between_zero_and_one(cls, v: float) -> float:
        if not (0.0 < v < 1.0):
            raise ValueError(f"soft_alert_threshold must be between 0 and 1 exclusive, got {v}")
        return v


class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    wallet_address: Optional[str] = None
    bot_type: Optional[str] = None
    description: Optional[str] = None
    daily_limit: Optional[float] = None
    hourly_limit: Optional[float] = None
    per_tx_limit: Optional[float] = None
    session_limit: Optional[float] = None
    whitelist: Optional[List[str]] = None
    blacklist: Optional[List[str]] = None
    auto_approve_under: Optional[float] = None
    soft_alert_threshold: Optional[float] = None
    active: Optional[bool] = None


class Transaction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    amount: float
    asset: str = "0x4ae46a509f6b1d9056937ba4500cb143933d2dc8"
    pay_to: str
    network: str = "eip155:196"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["approved", "soft_alert", "blocked"] = "approved"
    reason: str = ""
    policy_id: Optional[str] = None


class GuardRequest(BaseModel):
    agent_id: str
    network: str = "eip155:196"
    amount: float
    asset: str = "0x4ae46a509f6b1d9056937ba4500cb143933d2dc8"
    pay_to: str
    policy_id: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"amount must be greater than 0, got {v}")
        return v

    @field_validator("agent_id", "pay_to")
    @classmethod
    def string_must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("field must not be blank")
        return v.strip()


class GuardResponse(BaseModel):
    allowed: bool
    action: Literal["approve", "soft_alert", "block"]
    reason: str
    remaining_daily: float
    remaining_hourly: float
    policy_id: Optional[str] = None
    transaction_id: Optional[str] = None


class SpendingStats(BaseModel):
    agent_id: str
    daily_spent: float
    hourly_spent: float
    daily_limit: float
    hourly_limit: float
    per_tx_limit: float
    remaining_daily: float
    remaining_hourly: float
    total_transactions: int
    blocked_transactions: int
    approved_transactions: int
    soft_alert_transactions: int
    policy_id: Optional[str] = None
