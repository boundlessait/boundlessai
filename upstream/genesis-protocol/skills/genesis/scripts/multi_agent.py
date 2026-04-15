"""Multi-Agent Orchestrator - Coordinates multiple specialized agents.

Each agent operates through a dedicated sub-wallet from the Agentic Wallet
hierarchy, ensuring fund isolation and clear role separation.

Agent Roles:
  - StrategyAgent (wallet index 1): Deploys and manages Hook strategies
  - RebalanceAgent (wallet index 4): Executes position rebalancing
  - IncomeAgent (wallet index 2): Manages revenue collection from x402 payments
  - SentinelAgent (wallet index 0): Monitors system health and approves operations

All agents share the same GenesisHookAssembler contract but use different
sub-wallets for their operations.
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from . import config

# Lazy imports for optional modules - handled gracefully per action
_strategy_manager = None
_decision_journal = None
_hook_assembler = None
_wallet_manager = None
_payment_handler = None
_market_oracle = None


def _get_strategy_manager():
    global _strategy_manager
    if _strategy_manager is None:
        try:
            from .strategy_manager import StrategyManager
            _strategy_manager = StrategyManager()
        except ImportError:
            _strategy_manager = None
    return _strategy_manager


def _get_decision_journal():
    global _decision_journal
    if _decision_journal is None:
        try:
            from .decision_journal import DecisionJournal
            _decision_journal = DecisionJournal()
        except ImportError:
            _decision_journal = None
    return _decision_journal


def _get_hook_assembler():
    global _hook_assembler
    if _hook_assembler is None:
        try:
            from .hook_assembler import HookAssembler
            _hook_assembler = HookAssembler()
        except ImportError:
            _hook_assembler = None
    return _hook_assembler


def _get_wallet_manager():
    global _wallet_manager
    if _wallet_manager is None:
        try:
            from .wallet_manager import WalletManager
            _wallet_manager = WalletManager()
        except ImportError:
            _wallet_manager = None
    return _wallet_manager


def _get_payment_handler():
    global _payment_handler
    if _payment_handler is None:
        try:
            from .payment_handler import PaymentHandler
            _payment_handler = PaymentHandler()
        except ImportError:
            _payment_handler = None
    return _payment_handler


def _get_market_oracle():
    global _market_oracle
    if _market_oracle is None:
        try:
            from .market_oracle import MarketOracle
            _market_oracle = MarketOracle()
        except ImportError:
            _market_oracle = None
    return _market_oracle


# Maps agent names to their supported actions
AGENT_CAPABILITIES = {
    "SentinelAgent": ["health_check", "approve_operation", "emergency_stop"],
    "StrategyAgent": ["create_strategy", "update_parameters", "deactivate_strategy"],
    "IncomeAgent": ["collect_revenue", "settle_payment", "report_income"],
    "RebalanceAgent": ["check_rebalance", "execute_rebalance", "twap_step"],
}

# ── Upgrade #7: Agent Health Levels ─────────────────────────────────────


class AgentHealth(Enum):
    """Health status levels for graceful agent degradation."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    DISABLED = "disabled"


# Thresholds for health transitions
DEGRADED_THRESHOLD = 3   # consecutive failures to become DEGRADED
FAILED_THRESHOLD = 5     # consecutive failures to become FAILED
RECOVERY_THRESHOLD = 3   # consecutive successes to recover from DEGRADED to HEALTHY

# Dependency graph: agent -> list of agents it depends on.
# If a dependency is FAILED, the dependent falls back to safe defaults.
AGENT_DEPENDENCIES: dict[str, list[str]] = {
    "StrategyAgent": ["SentinelAgent"],
    "RebalanceAgent": ["SentinelAgent", "StrategyAgent"],
    "IncomeAgent": ["SentinelAgent"],
    "SentinelAgent": [],
}

# ── Upgrade #8: Governance Rate-Limit Configuration ─────────────────────

# Max operations per hour, per agent type
AGENT_RATE_LIMITS: dict[str, int] = {
    "SentinelAgent": 100,
    "StrategyAgent": 50,
    "IncomeAgent": 30,
    "RebalanceAgent": 20,
}

# Per-agent max value for a single operation (in USD-equivalent units)
AGENT_MAX_SINGLE_VALUE: dict[str, float] = {
    "SentinelAgent": float("inf"),   # sentinel has no single-op value cap
    "StrategyAgent": 100_000.0,
    "IncomeAgent": 50_000.0,
    "RebalanceAgent": 75_000.0,
}

# Per-agent max cumulative value per hour (in USD-equivalent units)
AGENT_MAX_HOURLY_VALUE: dict[str, float] = {
    "SentinelAgent": float("inf"),
    "StrategyAgent": 500_000.0,
    "IncomeAgent": 200_000.0,
    "RebalanceAgent": 300_000.0,
}

# ── Upgrade #9: Economic Constraint Governance (Staking) ─────────────────

# Initial stake balance per agent type
AGENT_INITIAL_STAKE: dict[str, float] = {
    "SentinelAgent": 1000.0,
    "StrategyAgent": 2000.0,
    "IncomeAgent": 1500.0,
    "RebalanceAgent": 1500.0,
}

# Penalty factors by severity level
PENALTY_FACTORS: dict[str, float] = {
    "minor": 0.2,
    "moderate": 0.5,
    "major": 1.0,
}

# Stake cost multipliers by risk level
_RISK_STAKE_COST: dict[str, float] = {
    "low": 0.01,
    "medium": 0.05,
    "high": 0.10,
    "critical": 0.20,
}

# Minimum stake threshold factor (20% of initial)
_STAKE_DEGRADATION_FACTOR = 0.20

# ── Upgrade #10: Degradation Audit Chain ─────────────────────────────────

# Max attestations to keep in the degradation log
_DEGRADATION_LOG_MAXLEN = 200

# Number of recent operations to store in partial reasoning trace
_REASONING_TRACE_MAXLEN = 10

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """Tracks the operational state of a single agent."""
    name: str
    wallet_role: str
    wallet_index: int
    status: str = "idle"
    last_action_time: float = 0.0
    action_count: int = 0
    error_count: int = 0
    last_error: str = ""
    # Upgrade #7 – health tracking
    consecutive_failures: int = 0
    consecutive_successes: int = 0


class MultiAgentOrchestrator:
    """Orchestrates multiple specialized agents operating on X Layer.

    Architecture:
    ┌─────────────────────────────────────────────────────┐
    │               Multi-Agent Orchestrator               │
    │                                                     │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
    │  │ Sentinel │  │ Strategy │  │ Rebalance│         │
    │  │ Agent    │  │ Agent    │  │ Agent    │         │
    │  │ (idx 0)  │  │ (idx 1)  │  │ (idx 4)  │         │
    │  └────┬─────┘  └────┬─────┘  └────┬─────┘         │
    │       │              │              │               │
    │       ▼              ▼              ▼               │
    │  ┌──────────────────────────────────────────┐      │
    │  │        Agentic Wallet (TEE-backed)        │      │
    │  │   5 sub-wallets with role isolation        │      │
    │  └──────────────────────────────────────────┘      │
    │                      │                              │
    │                      ▼                              │
    │  ┌──────────────────────────────────────────┐      │
    │  │     GenesisHookAssembler (X Layer)         │      │
    │  └──────────────────────────────────────────┘      │
    └─────────────────────────────────────────────────────┘
    """

    def __init__(self):
        self.agents: dict[str, AgentState] = {}
        # Upgrade #7 – per-agent health tracking
        self._agent_health: dict[str, AgentHealth] = {}
        # Upgrade #8 – rate limiter: {agent_name: [(timestamp, operation_type, value), ...]}
        self._rate_limiter: dict[str, list[tuple[float, str, float]]] = defaultdict(list)
        # Upgrade #9 – staking balances, reward/penalty accumulators
        self._agent_stakes: dict[str, float] = {}
        self._staking_total_rewards: dict[str, float] = defaultdict(float)
        self._staking_total_penalties: dict[str, float] = defaultdict(float)
        # Upgrade #10 – degradation audit chain & per-agent operation trace
        self._degradation_log: deque = deque(maxlen=_DEGRADATION_LOG_MAXLEN)
        self._agent_operation_trace: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=_REASONING_TRACE_MAXLEN)
        )
        self._init_agents()
        logger.info("MultiAgentOrchestrator initialized with %d agents", len(self.agents))

    def _init_agents(self):
        """Initialize all specialized agents."""
        agent_configs = [
            ("SentinelAgent", "master", 0,
             "Monitors system health, approves high-value operations, emergency shutdown"),
            ("StrategyAgent", "strategy", 1,
             "Deploys and manages Uniswap V4 Hook strategies via GenesisHookAssembler"),
            ("IncomeAgent", "income", 2,
             "Collects x402 payment revenue and manages pay-with-any-token settlements"),
            ("RebalanceAgent", "rebalance", 4,
             "Executes position rebalancing with isolated funds"),
        ]

        for name, role, index, description in agent_configs:
            self.agents[name] = AgentState(
                name=name,
                wallet_role=role,
                wallet_index=index,
            )
            self._agent_health[name] = AgentHealth.HEALTHY
            self._agent_stakes[name] = AGENT_INITIAL_STAKE.get(name, 1000.0)
            logger.debug("Registered agent: %s (wallet=%s, idx=%d, stake=%.1f) - %s",
                         name, role, index, self._agent_stakes[name], description)

    def get_agent(self, name: str) -> Optional[AgentState]:
        """Get agent state by name."""
        return self.agents.get(name)

    def dispatch(self, agent_name: str, action: str, params: dict) -> dict:
        """Dispatch an action to a specific agent.

        Each agent operates through its dedicated sub-wallet, ensuring:
        - Fund isolation (strategy funds separate from rebalance funds)
        - Clear audit trail (each agent's actions are traceable)
        - Risk containment (a bug in RebalanceAgent can't drain StrategyAgent's funds)

        Upgrade #7 adds graceful degradation based on agent health.
        Upgrade #8 adds per-agent rate limiting and value checks.
        """
        agent = self.agents.get(agent_name)
        if not agent:
            return {"error": f"Unknown agent: {agent_name}"}

        if config.PAUSED and agent_name != "SentinelAgent":
            logger.info("System PAUSED - only SentinelAgent can operate")
            return {"status": "paused", "agent": agent_name}

        # ── Upgrade #7: check agent health ──────────────────────────────
        health = self._agent_health.get(agent_name, AgentHealth.HEALTHY)
        if health == AgentHealth.DISABLED:
            logger.info("Agent %s is DISABLED – skipping dispatch", agent_name)
            return {"status": "disabled", "agent": agent_name}
        if health == AgentHealth.FAILED:
            # Check if any dependents need safe-default fallback
            logger.warning("Agent %s is FAILED – attempting recovery probe", agent_name)
            # Allow the call through so we can detect recovery (auto-recovery logic below)

        # In DEGRADED mode, annotate params so handlers can reduce scope
        degraded_mode = health == AgentHealth.DEGRADED
        if degraded_mode:
            params = {**params, "_degraded": True}
            logger.info("Agent %s is DEGRADED – running with reduced scope", agent_name)

        # ── Upgrade #8: rate-limit check ────────────────────────────────
        operation_type = params.get("operation_type", action)
        operation_value = float(params.get("operation_value", 0))
        if not self.check_rate_limit(agent_name, operation_type):
            logger.warning("Agent %s rate-limited for %s", agent_name, operation_type)
            return {"status": "rate_limited", "agent": agent_name, "action": action}

        # Value-per-operation cap
        max_single = AGENT_MAX_SINGLE_VALUE.get(agent_name, float("inf"))
        if operation_value > max_single:
            logger.warning("Agent %s single-op value %.2f exceeds cap %.2f",
                           agent_name, operation_value, max_single)
            return {
                "status": "rejected",
                "agent": agent_name,
                "reason": f"Single operation value {operation_value} exceeds limit {max_single}",
            }

        # Cumulative hourly value cap
        max_hourly = AGENT_MAX_HOURLY_VALUE.get(agent_name, float("inf"))
        now = time.time()
        hourly_total = sum(
            v for ts, _, v in self._rate_limiter.get(agent_name, [])
            if now - ts < 3600
        ) + operation_value
        if hourly_total > max_hourly:
            logger.warning("Agent %s cumulative hourly value %.2f would exceed cap %.2f",
                           agent_name, hourly_total, max_hourly)
            return {
                "status": "rejected",
                "agent": agent_name,
                "reason": (f"Cumulative hourly value {hourly_total:.2f} "
                           f"exceeds limit {max_hourly}"),
            }

        # ── Dispatch ────────────────────────────────────────────────────
        logger.info("Dispatching %s to %s (wallet_idx=%d, health=%s)",
                     action, agent_name, agent.wallet_index, health.value)

        agent.status = "executing"
        agent.last_action_time = time.time()

        try:
            result = self._execute_agent_action(agent, action, params)
            agent.action_count += 1
            agent.status = "idle"

            # Record operation for rate limiter
            self._rate_limiter[agent_name].append(
                (time.time(), operation_type, operation_value)
            )

            # Upgrade #10 – record operation in trace
            self._agent_operation_trace[agent_name].append({
                "action": action,
                "timestamp": int(time.time()),
                "status": "success",
            })

            # ── Upgrade #7: auto-recovery on success ────────────────────
            agent.consecutive_failures = 0
            agent.consecutive_successes += 1
            if health == AgentHealth.FAILED and agent.consecutive_successes >= 1:
                self._agent_health[agent_name] = AgentHealth.DEGRADED
                agent.consecutive_successes = 0
                logger.info("Agent %s recovered from FAILED -> DEGRADED", agent_name)
            elif health == AgentHealth.DEGRADED and agent.consecutive_successes >= RECOVERY_THRESHOLD:
                self._agent_health[agent_name] = AgentHealth.HEALTHY
                logger.info("Agent %s recovered from DEGRADED -> HEALTHY", agent_name)

            return result
        except Exception as exc:
            agent.error_count += 1
            agent.last_error = str(exc)
            agent.status = "error"
            logger.error("Agent %s failed: %s", agent_name, exc)

            # Upgrade #10 – record failed operation in trace
            self._agent_operation_trace[agent_name].append({
                "action": action,
                "timestamp": int(time.time()),
                "status": "error",
                "error": str(exc),
            })

            # ── Upgrade #7: track consecutive failures & degrade ────────
            agent.consecutive_successes = 0
            agent.consecutive_failures += 1
            old_health = self._agent_health.get(agent_name, AgentHealth.HEALTHY)
            if agent.consecutive_failures >= FAILED_THRESHOLD:
                self._agent_health[agent_name] = AgentHealth.FAILED
                logger.error("Agent %s marked FAILED after %d consecutive failures",
                             agent_name, agent.consecutive_failures)
                # Upgrade #10 – attestation on automatic FAILED transition
                if old_health != AgentHealth.FAILED:
                    self._generate_degradation_attestation(
                        agent_name, old_health, AgentHealth.FAILED,
                        f"{agent.consecutive_failures} consecutive failures"
                    )
            elif agent.consecutive_failures >= DEGRADED_THRESHOLD:
                self._agent_health[agent_name] = AgentHealth.DEGRADED
                logger.warning("Agent %s marked DEGRADED after %d consecutive failures",
                               agent_name, agent.consecutive_failures)
                # Upgrade #10 – attestation on automatic DEGRADED transition
                if old_health != AgentHealth.DEGRADED:
                    self._generate_degradation_attestation(
                        agent_name, old_health, AgentHealth.DEGRADED,
                        f"{agent.consecutive_failures} consecutive failures"
                    )

            return {"error": str(exc), "agent": agent_name,
                    "health": self._agent_health.get(agent_name, AgentHealth.HEALTHY).value}

    def _execute_agent_action(self, agent: AgentState, action: str, params: dict) -> dict:
        """Execute a specific action for an agent.

        Routes to the appropriate handler based on agent name and action.
        Each handler returns a structured result dict with status, details,
        and timestamps.  DRY_RUN is respected inside each handler.
        """
        # Validate that the action is supported for this agent
        supported = AGENT_CAPABILITIES.get(agent.name, [])
        if action not in supported:
            return {
                "error": f"Unsupported action '{action}' for {agent.name}",
                "supported_actions": supported,
            }

        # Build a base result that every handler augments
        base = {
            "agent": agent.name,
            "action": action,
            "wallet_index": agent.wallet_index,
            "dry_run": config.DRY_RUN,
            "timestamp": int(time.time()),
        }

        # Route to the correct agent handler
        handler_map = {
            "SentinelAgent": self._handle_sentinel,
            "StrategyAgent": self._handle_strategy,
            "IncomeAgent": self._handle_income,
            "RebalanceAgent": self._handle_rebalance,
        }
        handler = handler_map.get(agent.name)
        if handler is None:
            return {**base, "error": f"No handler registered for {agent.name}"}

        result = handler(agent, action, params)
        result.update(base)
        return result

    # ── SentinelAgent handlers ───────────────────────────────────────────

    def _handle_sentinel(self, agent: AgentState, action: str, params: dict) -> dict:
        if action == "health_check":
            return self._sentinel_health_check(agent, params)
        elif action == "approve_operation":
            return self._sentinel_approve_operation(agent, params)
        elif action == "emergency_stop":
            return self._sentinel_emergency_stop(agent, params)
        return {"error": f"Unknown sentinel action: {action}"}

    def _sentinel_health_check(self, agent: AgentState, params: dict) -> dict:
        """Run system-wide health check across all agents."""
        logger.info("[SentinelAgent] Running system-wide health check")

        total_errors = sum(a.error_count for a in self.agents.values())
        all_idle = all(a.status == "idle" or a.name == agent.name
                       for a in self.agents.values())
        error_rate = total_errors / max(
            sum(a.action_count for a in self.agents.values()), 1
        )
        agent_statuses = {}
        for name, a in self.agents.items():
            agent_statuses[name] = {
                "status": a.status,
                "action_count": a.action_count,
                "error_count": a.error_count,
                "last_error": a.last_error,
            }

        healthy = total_errors == 0 and all_idle and not config.PAUSED
        return {
            "status": "healthy" if healthy else "degraded",
            "all_idle": all_idle,
            "total_errors": total_errors,
            "error_rate": round(error_rate, 4),
            "paused": config.PAUSED,
            "mode": config.MODE,
            "agent_statuses": agent_statuses,
        }

    def _sentinel_approve_operation(self, agent: AgentState, params: dict) -> dict:
        """Validate and approve high-value operations.

        Upgrade #8: also enforces per-agent rate limits and cumulative value caps.
        """
        logger.info("[SentinelAgent] Evaluating operation approval: %s", params)

        position_size_pct = params.get("position_size_pct", 0)
        max_allowed = config.MAX_POSITION_SIZE_PCT
        operation_type = params.get("operation_type", "unknown")
        strategy_id = params.get("strategy_id", "")
        requesting_agent = params.get("requesting_agent", "")
        operation_value = float(params.get("operation_value", 0))

        # Existing position-size check
        if position_size_pct > max_allowed:
            reason = (f"Position size {position_size_pct}% exceeds "
                      f"MAX_POSITION_SIZE_PCT ({max_allowed}%)")
            logger.warning("[SentinelAgent] Operation REJECTED: %s", reason)
            journal = _get_decision_journal()
            if journal:
                journal.log_decision(
                    strategy_id, "FUND_TRANSFER",
                    f"Sentinel rejected: {reason}",
                    {"position_size_pct": position_size_pct, "max_allowed": max_allowed},
                )
            return {
                "status": "rejected",
                "approved": False,
                "reason": reason,
                "position_size_pct": position_size_pct,
                "max_allowed": max_allowed,
            }

        # ── Upgrade #8: rate-limit check for the requesting agent ───────
        if requesting_agent:
            if not self.check_rate_limit(requesting_agent, operation_type):
                reason = (f"Agent {requesting_agent} has exceeded its rate limit "
                          f"for {operation_type}")
                logger.warning("[SentinelAgent] Operation REJECTED (rate limit): %s", reason)
                return {
                    "status": "rejected",
                    "approved": False,
                    "reason": reason,
                }

            # Cumulative hourly value check for requesting agent
            max_hourly = AGENT_MAX_HOURLY_VALUE.get(requesting_agent, float("inf"))
            now = time.time()
            hourly_total = sum(
                v for ts, _, v in self._rate_limiter.get(requesting_agent, [])
                if now - ts < 3600
            ) + operation_value
            if hourly_total > max_hourly:
                reason = (f"Agent {requesting_agent} cumulative hourly value "
                          f"{hourly_total:.2f} exceeds limit {max_hourly}")
                logger.warning("[SentinelAgent] Operation REJECTED (value cap): %s", reason)
                return {
                    "status": "rejected",
                    "approved": False,
                    "reason": reason,
                }

            # Single-operation value check
            max_single = AGENT_MAX_SINGLE_VALUE.get(requesting_agent, float("inf"))
            if operation_value > max_single:
                reason = (f"Agent {requesting_agent} single operation value "
                          f"{operation_value} exceeds limit {max_single}")
                logger.warning("[SentinelAgent] Operation REJECTED (single value): %s", reason)
                return {
                    "status": "rejected",
                    "approved": False,
                    "reason": reason,
                }

        logger.info("[SentinelAgent] Operation APPROVED (size=%s%%, type=%s)",
                     position_size_pct, operation_type)
        return {
            "status": "approved",
            "approved": True,
            "operation_type": operation_type,
            "position_size_pct": position_size_pct,
            "max_allowed": max_allowed,
        }

    def _sentinel_emergency_stop(self, agent: AgentState, params: dict) -> dict:
        """Set all agents to stopped status and log to decision journal."""
        reason = params.get("reason", "Emergency stop triggered")
        logger.critical("[SentinelAgent] EMERGENCY STOP: %s", reason)

        stopped_agents = []
        for name, a in self.agents.items():
            a.status = "stopped"
            stopped_agents.append(name)
            logger.info("[SentinelAgent] Stopped agent: %s", name)

        # Log to decision journal
        journal = _get_decision_journal()
        if journal:
            journal.log_decision(
                0, "STRATEGY_DEACTIVATE",
                f"Emergency stop: {reason}",
                {"stopped_agents": stopped_agents, "reason": reason},
            )

        return {
            "status": "emergency_stopped",
            "stopped_agents": stopped_agents,
            "reason": reason,
        }

    # ── StrategyAgent handlers ───────────────────────────────────────────

    def _handle_strategy(self, agent: AgentState, action: str, params: dict) -> dict:
        if action == "create_strategy":
            return self._strategy_create(agent, params)
        elif action == "update_parameters":
            return self._strategy_update_parameters(agent, params)
        elif action == "deactivate_strategy":
            return self._strategy_deactivate(agent, params)
        return {"error": f"Unknown strategy action: {action}"}

    def _strategy_create(self, agent: AgentState, params: dict) -> dict:
        """Select preset based on market regime, compose modules via hook_assembler."""
        logger.info("[StrategyAgent] Creating strategy with params: %s", params)

        market_regime = params.get("market_regime", "low_vol")
        market_data = params.get("market_data", {})

        if config.DRY_RUN:
            logger.info("[StrategyAgent] DRY_RUN: simulating strategy creation")
            assembler = _get_hook_assembler()
            preset_name, modules = ("calm_accumulator", ["dynamic_fee", "auto_rebalance"])
            if assembler:
                preset_name, modules = assembler.select_modules(
                    {"volatility_bps": market_data.get("volatility_bps", 0),
                     "trend": market_data.get("trend", "sideways")}
                )
            return {
                "status": "simulated",
                "preset_name": preset_name,
                "modules": modules,
                "market_regime": market_regime,
            }

        sm = _get_strategy_manager()
        if sm is None:
            return {"status": "error", "error": "StrategyManager unavailable"}

        record = sm.create_strategy(market_regime, market_data)
        if record.get("error"):
            return {"status": "error", "error": record["error"]}

        return {
            "status": "created",
            "strategy_id": record.get("id", ""),
            "preset_name": record.get("preset_name", ""),
            "modules": record.get("modules", []),
            "market_regime": market_regime,
        }

    def _strategy_update_parameters(self, agent: AgentState, params: dict) -> dict:
        """Adjust module parameters based on analysis layer output."""
        logger.info("[StrategyAgent] Updating parameters: %s", params)

        strategy_id = params.get("strategy_id", "")
        new_params = params.get("module_params", {})

        if not strategy_id:
            return {"status": "error", "error": "strategy_id is required"}

        if config.DRY_RUN:
            logger.info("[StrategyAgent] DRY_RUN: simulating parameter update")
            return {
                "status": "simulated",
                "strategy_id": strategy_id,
                "updated_params": new_params,
            }

        assembler = _get_hook_assembler()
        if assembler is None:
            return {"status": "error", "error": "HookAssembler unavailable"}

        results = {}
        for module_address, encoded_params in new_params.items():
            result = assembler.update_module_params(module_address, encoded_params)
            results[module_address] = result

        journal = _get_decision_journal()
        if journal:
            journal.log_decision(
                strategy_id, "FEE_ADJUST",
                f"Updated parameters for strategy {strategy_id}",
                {"module_updates": list(new_params.keys())},
            )

        return {
            "status": "updated",
            "strategy_id": strategy_id,
            "module_results": results,
        }

    def _strategy_deactivate(self, agent: AgentState, params: dict) -> dict:
        """Mark strategy inactive and log decision."""
        logger.info("[StrategyAgent] Deactivating strategy: %s", params)

        strategy_id = params.get("strategy_id", "")
        reason = params.get("reason", "Manual deactivation")

        if not strategy_id:
            return {"status": "error", "error": "strategy_id is required"}

        if config.DRY_RUN:
            logger.info("[StrategyAgent] DRY_RUN: simulating deactivation")
            return {
                "status": "simulated",
                "strategy_id": strategy_id,
                "reason": reason,
            }

        sm = _get_strategy_manager()
        if sm is None:
            return {"status": "error", "error": "StrategyManager unavailable"}

        sm.deactivate_strategy(strategy_id, reason)
        return {
            "status": "deactivated",
            "strategy_id": strategy_id,
            "reason": reason,
        }

    # ── IncomeAgent handlers ─────────────────────────────────────────────

    def _handle_income(self, agent: AgentState, action: str, params: dict) -> dict:
        if action == "collect_revenue":
            return self._income_collect_revenue(agent, params)
        elif action == "settle_payment":
            return self._income_settle_payment(agent, params)
        elif action == "report_income":
            return self._income_report(agent, params)
        return {"error": f"Unknown income action: {action}"}

    def _income_collect_revenue(self, agent: AgentState, params: dict) -> dict:
        """Query income wallet balance and log revenue stats."""
        logger.info("[IncomeAgent] Collecting revenue")

        wm = _get_wallet_manager()
        if wm is None:
            return {"status": "error", "error": "WalletManager unavailable"}

        if config.DRY_RUN:
            logger.info("[IncomeAgent] DRY_RUN: simulating revenue collection")
            return {
                "status": "simulated",
                "balance": "0",
                "collected": False,
            }

        balance_info = wm.get_balance("income", token="USDT")
        balance = balance_info.get("balance", balance_info.get("amount", "0"))

        result = wm.collect_income()
        collected = result.get("status") != "empty"

        logger.info("[IncomeAgent] Revenue collection: balance=%s collected=%s",
                     balance, collected)
        return {
            "status": "collected" if collected else "empty",
            "balance": balance,
            "collected": collected,
            "transfer_result": result,
        }

    def _income_settle_payment(self, agent: AgentState, params: dict) -> dict:
        """Process x402 payment settlement."""
        logger.info("[IncomeAgent] Settling payment: %s", params)

        product = params.get("product", "")
        payer_token = params.get("payer_token", "USDT")
        payer_address = params.get("payer_address", "")

        if not product or not payer_address:
            return {"status": "error", "error": "product and payer_address are required"}

        ph = _get_payment_handler()
        if ph is None:
            return {"status": "error", "error": "PaymentHandler unavailable"}

        if config.DRY_RUN:
            logger.info("[IncomeAgent] DRY_RUN: simulating payment settlement")
            return {
                "status": "simulated",
                "product": product,
                "payer_token": payer_token,
                "payer_address": payer_address,
            }

        result = ph.process_payment(product, payer_token, payer_address)
        return {
            "status": "settled" if result.get("success") else "failed",
            "product": product,
            "payment_result": result,
        }

    def _income_report(self, agent: AgentState, params: dict) -> dict:
        """Generate income summary."""
        logger.info("[IncomeAgent] Generating income report")

        wm = _get_wallet_manager()
        balance_info = {}
        if wm:
            balance_info = wm.get_balance("income", token="USDT")

        journal = _get_decision_journal()
        recent_decisions = []
        if journal:
            recent_decisions = journal.get_decisions_by_type("FUND_TRANSFER")

        ph = _get_payment_handler()
        pricing = {}
        if ph:
            pricing = ph.get_pricing()

        return {
            "status": "reported",
            "income_wallet_balance": balance_info.get(
                "balance", balance_info.get("amount", "0")
            ),
            "x402_pricing": pricing,
            "recent_transfers": len(recent_decisions),
            "x402_enabled": config.X402_ENABLED,
        }

    # ── RebalanceAgent handlers ──────────────────────────────────────────

    def _handle_rebalance(self, agent: AgentState, action: str, params: dict) -> dict:
        if action == "check_rebalance":
            return self._rebalance_check(agent, params)
        elif action == "execute_rebalance":
            return self._rebalance_execute(agent, params)
        elif action == "twap_step":
            return self._rebalance_twap_step(agent, params)
        return {"error": f"Unknown rebalance action: {action}"}

    def _rebalance_check(self, agent: AgentState, params: dict) -> dict:
        """Evaluate if rebalance is needed based on position boundaries."""
        logger.info("[RebalanceAgent] Checking rebalance conditions: %s", params)

        strategy_id = params.get("strategy_id", "")
        market_data = params.get("market_data", {})

        if not strategy_id:
            return {"status": "error", "error": "strategy_id is required"}

        sm = _get_strategy_manager()
        if sm is None:
            return {"status": "error", "error": "StrategyManager unavailable"}

        needs_rebalance, reason = sm.should_rebalance(strategy_id, market_data)
        logger.info("[RebalanceAgent] Rebalance check: needed=%s reason=%s",
                     needs_rebalance, reason)
        return {
            "status": "checked",
            "strategy_id": strategy_id,
            "needs_rebalance": needs_rebalance,
            "reason": reason,
        }

    def _rebalance_execute(self, agent: AgentState, params: dict) -> dict:
        """Execute rebalance via DEX aggregator with slippage check."""
        logger.info("[RebalanceAgent] Executing rebalance: %s", params)

        strategy_id = params.get("strategy_id", "")
        new_market_regime = params.get("new_market_regime", "low_vol")
        max_slippage_bps = params.get("max_slippage_bps", config.DEX_SLIPPAGE_BPS)

        if not strategy_id:
            return {"status": "error", "error": "strategy_id is required"}

        if config.DRY_RUN:
            logger.info("[RebalanceAgent] DRY_RUN: simulating rebalance execution")
            return {
                "status": "simulated",
                "strategy_id": strategy_id,
                "new_market_regime": new_market_regime,
                "max_slippage_bps": max_slippage_bps,
            }

        # Check slippage via market oracle before executing
        oracle = _get_market_oracle()
        if oracle and config.DEX_COMPARE_WITH_HOOK:
            pair = config.ONCHAINOS_MARKET_PAIRS[0] if config.ONCHAINOS_MARKET_PAIRS else {}
            if pair:
                quote = oracle.get_dex_quote(
                    pair.get("base", "ETH"),
                    pair.get("quote", "USDC"),
                    1.0,
                )
                if quote and quote.get("slippage_bps", 0) > max_slippage_bps:
                    logger.warning("[RebalanceAgent] Slippage too high: %s > %s",
                                   quote.get("slippage_bps"), max_slippage_bps)
                    return {
                        "status": "aborted",
                        "strategy_id": strategy_id,
                        "reason": "slippage exceeds limit",
                        "slippage_bps": quote.get("slippage_bps", 0),
                        "max_slippage_bps": max_slippage_bps,
                    }

        sm = _get_strategy_manager()
        if sm is None:
            return {"status": "error", "error": "StrategyManager unavailable"}

        sm.rebalance_strategy(strategy_id, new_market_regime)
        return {
            "status": "rebalanced",
            "strategy_id": strategy_id,
            "new_market_regime": new_market_regime,
        }

    def _rebalance_twap_step(self, agent: AgentState, params: dict) -> dict:
        """Execute one step of a TWAP rebalance strategy."""
        logger.info("[RebalanceAgent] Executing TWAP step: %s", params)

        strategy_id = params.get("strategy_id", "")
        step_number = params.get("step_number", 1)
        total_steps = params.get("total_steps", 5)
        token_in = params.get("token_in", "ETH")
        token_out = params.get("token_out", "USDC")
        total_amount = params.get("total_amount", 0)

        if not strategy_id or total_amount <= 0:
            return {"status": "error", "error": "strategy_id and positive total_amount required"}

        step_amount = total_amount / total_steps

        if config.DRY_RUN:
            logger.info("[RebalanceAgent] DRY_RUN: simulating TWAP step %d/%d",
                         step_number, total_steps)
            return {
                "status": "simulated",
                "strategy_id": strategy_id,
                "step_number": step_number,
                "total_steps": total_steps,
                "step_amount": step_amount,
                "token_in": token_in,
                "token_out": token_out,
            }

        oracle = _get_market_oracle()
        if oracle is None:
            return {"status": "error", "error": "MarketOracle unavailable"}

        quote = oracle.get_dex_quote(token_in, token_out, step_amount)
        if quote is None:
            return {
                "status": "error",
                "error": "Failed to get DEX quote for TWAP step",
                "step_number": step_number,
            }

        journal = _get_decision_journal()
        if journal:
            journal.log_decision(
                strategy_id, "REBALANCE_EXECUTE",
                f"TWAP step {step_number}/{total_steps}: {step_amount} {token_in}->{token_out}",
                {"step": step_number, "total_steps": total_steps,
                 "step_amount": step_amount, "quote": quote},
            )

        logger.info("[RebalanceAgent] TWAP step %d/%d executed: %s %s -> %s",
                     step_number, total_steps, step_amount, token_in, token_out)
        return {
            "status": "executed",
            "strategy_id": strategy_id,
            "step_number": step_number,
            "total_steps": total_steps,
            "step_amount": step_amount,
            "complete": step_number >= total_steps,
            "quote": quote,
        }

    # ── Coordination & capabilities ──────────────────────────────────────

    def coordinate_cycle(self) -> dict:
        """Run a full coordination cycle across all agents.

        Order: sentinel health check -> strategy eval -> rebalance check -> income collection.
        Returns a summary dict with results from each phase.

        Upgrade #7: agents that are FAILED or DISABLED are skipped gracefully
        instead of aborting the entire cycle.  Dependency health is also checked.
        """
        logger.info("Starting coordination cycle")
        cycle_start = time.time()
        results = {}
        skipped_agents: list[str] = []

        # ── Helper: should we skip an agent? ────────────────────────────
        def _should_skip(agent_name: str) -> Optional[str]:
            """Return a reason string if the agent should be skipped, else None."""
            h = self._agent_health.get(agent_name, AgentHealth.HEALTHY)
            if h in (AgentHealth.FAILED, AgentHealth.DISABLED):
                return f"{agent_name} is {h.value}"
            # Check dependency health
            for dep in AGENT_DEPENDENCIES.get(agent_name, []):
                dep_h = self._agent_health.get(dep, AgentHealth.HEALTHY)
                if dep_h == AgentHealth.FAILED:
                    return f"dependency {dep} is FAILED"
            return None

        # Phase 1: Sentinel health check
        skip_reason = _should_skip("SentinelAgent")
        if skip_reason:
            logger.warning("SentinelAgent skipped: %s – using safe defaults", skip_reason)
            skipped_agents.append("SentinelAgent")
            health = {"status": "skipped", "reason": skip_reason}
        else:
            health = self.dispatch("SentinelAgent", "health_check", {})
        results["health_check"] = health

        if health.get("status") == "emergency_stopped":
            logger.warning("Coordination cycle aborted: system in emergency stop")
            results["aborted"] = True
            results["cycle_duration_sec"] = round(time.time() - cycle_start, 3)
            return results

        # Phase 2: Strategy evaluation - check active strategies
        skip_reason = _should_skip("StrategyAgent")
        if skip_reason:
            logger.warning("StrategyAgent skipped: %s", skip_reason)
            skipped_agents.append("StrategyAgent")
            results["strategy_eval"] = [{"status": "skipped", "reason": skip_reason}]
        else:
            sm = _get_strategy_manager()
            strategy_results = []
            if sm:
                active = sm.get_active_strategies()
                for record in active:
                    sid = record.get("id", "")
                    perf = sm.evaluate_performance(sid)
                    strategy_results.append({"strategy_id": sid, "performance": perf})

                    # Check if strategy should be deactivated
                    should_deactivate, reason = sm.should_deactivate(sid, perf)
                    if should_deactivate:
                        self.dispatch("StrategyAgent", "deactivate_strategy",
                                      {"strategy_id": sid, "reason": reason})
                        strategy_results[-1]["deactivated"] = True
                        strategy_results[-1]["deactivate_reason"] = reason
            results["strategy_eval"] = strategy_results

        # Phase 3: Rebalance check for active strategies
        skip_reason = _should_skip("RebalanceAgent")
        if skip_reason:
            logger.warning("RebalanceAgent skipped: %s", skip_reason)
            skipped_agents.append("RebalanceAgent")
            results["rebalance"] = [{"status": "skipped", "reason": skip_reason}]
        else:
            sm = _get_strategy_manager()
            rebalance_results = []
            if sm:
                oracle = _get_market_oracle()
                market_data = {}
                if oracle:
                    pair = config.ONCHAINOS_MARKET_PAIRS[0] if config.ONCHAINOS_MARKET_PAIRS else {}
                    if pair:
                        base, quote = pair.get("base", "ETH"), pair.get("quote", "USDC")
                        vol = oracle.calculate_volatility(base, quote)
                        trend = oracle.detect_trend(base, quote)
                        market_data = {
                            "volatility_bps": int(vol * 10000) if vol else 0,
                            "trend": trend,
                        }

                for record in sm.get_active_strategies():
                    sid = record.get("id", "")
                    check = self.dispatch("RebalanceAgent", "check_rebalance",
                                          {"strategy_id": sid, "market_data": market_data})
                    rebalance_results.append(check)
                    if check.get("needs_rebalance"):
                        regime = market_data.get("trend", "low_vol")
                        exec_result = self.dispatch(
                            "RebalanceAgent", "execute_rebalance",
                            {"strategy_id": sid, "new_market_regime": regime},
                        )
                        rebalance_results.append(exec_result)
            results["rebalance"] = rebalance_results

        # Phase 4: Income collection
        skip_reason = _should_skip("IncomeAgent")
        if skip_reason:
            logger.warning("IncomeAgent skipped: %s", skip_reason)
            skipped_agents.append("IncomeAgent")
            results["income_collection"] = {"status": "skipped", "reason": skip_reason}
        else:
            income_result = self.dispatch("IncomeAgent", "collect_revenue", {})
            results["income_collection"] = income_result

        results["skipped_agents"] = skipped_agents
        # Upgrade #10 – include attestation info for skipped agents
        skipped_attestations = []
        for skipped_name in skipped_agents:
            agent_attestations = [
                a for a in self._degradation_log if a["agent_name"] == skipped_name
            ]
            if agent_attestations:
                skipped_attestations.append({
                    "agent_name": skipped_name,
                    "latest_attestation": agent_attestations[-1],
                })
        results["skipped_attestations"] = skipped_attestations
        results["cycle_duration_sec"] = round(time.time() - cycle_start, 3)
        logger.info("Coordination cycle complete in %.3fs (skipped: %s)",
                     results["cycle_duration_sec"], skipped_agents or "none")
        return results

    def get_agent_capabilities(self, name: str) -> list[str]:
        """Return list of supported actions for a given agent.

        Args:
            name: Agent name (e.g. 'SentinelAgent').

        Returns:
            List of action strings, or empty list if agent not found.
        """
        return list(AGENT_CAPABILITIES.get(name, []))

    # ── Upgrade #7: Health status helpers ────────────────────────────────

    def get_agent_health_status(self) -> dict[str, dict]:
        """Return a snapshot of every agent's health, dependency state, and
        consecutive failure/success counters."""
        report: dict[str, dict] = {}
        for name, agent in self.agents.items():
            health = self._agent_health.get(name, AgentHealth.HEALTHY)
            deps_ok = all(
                self._agent_health.get(d, AgentHealth.HEALTHY)
                not in (AgentHealth.FAILED, AgentHealth.DISABLED)
                for d in AGENT_DEPENDENCIES.get(name, [])
            )
            report[name] = {
                "health": health.value,
                "consecutive_failures": agent.consecutive_failures,
                "consecutive_successes": agent.consecutive_successes,
                "dependencies_healthy": deps_ok,
                "dependencies": AGENT_DEPENDENCIES.get(name, []),
            }
        return report

    def set_agent_health(self, agent_name: str, health: AgentHealth) -> None:
        """Manually override an agent's health (e.g., to DISABLED).

        Upgrade #10: auto-generates a degradation attestation when the new
        health is DEGRADED or FAILED.
        """
        if agent_name in self._agent_health:
            old = self._agent_health[agent_name]
            self._agent_health[agent_name] = health
            logger.info("Agent %s health manually set: %s -> %s",
                        agent_name, old.value, health.value)
            # Upgrade #10 – attestation on degradation
            if health in (AgentHealth.DEGRADED, AgentHealth.FAILED):
                self._generate_degradation_attestation(
                    agent_name, old, health, "manual health override"
                )

    # ── Upgrade #8: Rate-limiting helpers ────────────────────────────────

    def check_rate_limit(self, agent_name: str, operation_type: str) -> bool:
        """Return True if the agent is within its hourly operation limit.

        Stale entries (older than 1 hour) are pruned on each call.
        """
        now = time.time()
        # Prune stale entries
        self._rate_limiter[agent_name] = [
            entry for entry in self._rate_limiter[agent_name]
            if now - entry[0] < 3600
        ]
        max_ops = AGENT_RATE_LIMITS.get(agent_name, 100)
        current_count = len(self._rate_limiter[agent_name])
        return current_count < max_ops

    def get_governance_report(self) -> dict:
        """Return current rate-limit usage vs limits for every agent.

        Includes operations count, cumulative value, and remaining budget
        within the rolling 1-hour window.
        """
        now = time.time()
        report: dict[str, dict] = {}
        for name in self.agents:
            entries = [e for e in self._rate_limiter.get(name, []) if now - e[0] < 3600]
            ops_used = len(entries)
            ops_limit = AGENT_RATE_LIMITS.get(name, 100)
            cumulative_value = sum(v for _, _, v in entries)
            max_hourly_val = AGENT_MAX_HOURLY_VALUE.get(name, float("inf"))
            max_single_val = AGENT_MAX_SINGLE_VALUE.get(name, float("inf"))
            report[name] = {
                "operations_used": ops_used,
                "operations_limit": ops_limit,
                "operations_remaining": max(ops_limit - ops_used, 0),
                "cumulative_value": round(cumulative_value, 2),
                "max_hourly_value": max_hourly_val,
                "hourly_value_remaining": round(max(max_hourly_val - cumulative_value, 0), 2),
                "max_single_value": max_single_val,
            }
        return report

    def get_all_status(self) -> dict:
        """Get status snapshot of all agents."""
        return {
            name: {
                "wallet_role": agent.wallet_role,
                "wallet_index": agent.wallet_index,
                "status": agent.status,
                "action_count": agent.action_count,
                "error_count": agent.error_count,
                "last_action": int(agent.last_action_time) if agent.last_action_time else None,
            }
            for name, agent in self.agents.items()
        }

    def health_check(self) -> dict:
        """Run a system-wide health check across all agents."""
        total_errors = sum(a.error_count for a in self.agents.values())
        all_idle = all(a.status == "idle" for a in self.agents.values())

        return {
            "healthy": total_errors == 0 and all_idle,
            "total_agents": len(self.agents),
            "total_actions": sum(a.action_count for a in self.agents.values()),
            "total_errors": total_errors,
            "all_idle": all_idle,
            "paused": config.PAUSED,
            "mode": config.MODE,
            "agents": self.get_all_status(),
        }

    # ── Upgrade #9: Economic Constraint Governance (Staking) ────────────

    def _stake_cost(self, agent_name: str, risk_level: str) -> float:
        """Calculate the stake cost for an operation based on risk level.

        The cost is a fraction of the agent's initial stake determined by
        the risk-level multiplier.

        Args:
            agent_name: Name of the agent (e.g. 'StrategyAgent').
            risk_level: One of 'low', 'medium', 'high', 'critical'.

        Returns:
            The computed stake cost (float).
        """
        initial = AGENT_INITIAL_STAKE.get(agent_name, 1000.0)
        multiplier = _RISK_STAKE_COST.get(risk_level, 0.05)
        return initial * multiplier

    def check_stake_sufficiency(self, agent_name: str, risk_level: str) -> dict:
        """Verify that an agent has sufficient stake for a high-risk operation.

        Args:
            agent_name: Name of the agent.
            risk_level: One of 'low', 'medium', 'high', 'critical'.

        Returns:
            Dict with 'sufficient' bool, 'current_stake', 'required_cost',
            and 'shortfall' (0 if sufficient).
        """
        current = self._agent_stakes.get(agent_name, 0.0)
        cost = self._stake_cost(agent_name, risk_level)
        sufficient = current >= cost
        return {
            "sufficient": sufficient,
            "current_stake": round(current, 4),
            "required_cost": round(cost, 4),
            "shortfall": round(max(cost - current, 0), 4),
        }

    def record_stake_outcome(
        self, agent_name: str, decision_id: str, success: bool,
        magnitude: float, severity: str = "moderate"
    ) -> dict:
        """Record the outcome of a staked operation.

        On success the agent receives its stake cost back plus a reward
        equal to 10% of the cost.  On failure the cost is multiplied by
        the penalty factor for the given severity and deducted.

        If the agent's remaining stake drops below 20% of its initial
        value the agent is automatically degraded.

        Args:
            agent_name: Name of the agent.
            decision_id: Unique identifier for the decision/operation.
            success: Whether the operation succeeded.
            magnitude: Nominal value/size of the operation (informational).
            severity: One of 'minor', 'moderate', 'major' (used on failure).

        Returns:
            Dict with outcome details including new stake balance.
        """
        cost = self._stake_cost(agent_name, "medium")  # base cost
        current = self._agent_stakes.get(agent_name, 0.0)

        if success:
            reward = cost * 0.1
            self._agent_stakes[agent_name] = current + reward
            self._staking_total_rewards[agent_name] += reward
            logger.info("Agent %s staking reward +%.4f for decision %s",
                        agent_name, reward, decision_id)
            outcome = {
                "agent_name": agent_name,
                "decision_id": decision_id,
                "success": True,
                "reward": round(reward, 4),
                "penalty": 0.0,
                "new_stake": round(self._agent_stakes[agent_name], 4),
            }
        else:
            penalty_factor = PENALTY_FACTORS.get(severity, 0.5)
            penalty = cost * penalty_factor
            self._agent_stakes[agent_name] = max(current - penalty, 0.0)
            self._staking_total_penalties[agent_name] += penalty
            logger.warning("Agent %s staking penalty -%.4f (severity=%s) for decision %s",
                           agent_name, penalty, severity, decision_id)
            outcome = {
                "agent_name": agent_name,
                "decision_id": decision_id,
                "success": False,
                "reward": 0.0,
                "penalty": round(penalty, 4),
                "severity": severity,
                "new_stake": round(self._agent_stakes[agent_name], 4),
            }

        # Auto-degrade if stake drops below 20% of initial
        initial = AGENT_INITIAL_STAKE.get(agent_name, 1000.0)
        threshold = initial * _STAKE_DEGRADATION_FACTOR
        if self._agent_stakes[agent_name] < threshold:
            old_health = self._agent_health.get(agent_name, AgentHealth.HEALTHY)
            if old_health not in (AgentHealth.DEGRADED, AgentHealth.FAILED,
                                  AgentHealth.DISABLED):
                self._agent_health[agent_name] = AgentHealth.DEGRADED
                logger.warning("Agent %s auto-degraded: stake %.4f below threshold %.4f",
                               agent_name, self._agent_stakes[agent_name], threshold)
                self._generate_degradation_attestation(
                    agent_name, old_health, AgentHealth.DEGRADED,
                    f"stake {self._agent_stakes[agent_name]:.4f} below threshold {threshold:.4f}"
                )
            outcome["auto_degraded"] = True

        return outcome

    def get_staking_report(self) -> dict:
        """Return per-agent stake levels, total rewards, and total penalties.

        Returns:
            Dict keyed by agent name with stake details, plus global totals.
        """
        report: dict[str, dict] = {}
        for name in self.agents:
            initial = AGENT_INITIAL_STAKE.get(name, 1000.0)
            current = self._agent_stakes.get(name, 0.0)
            report[name] = {
                "initial_stake": initial,
                "current_stake": round(current, 4),
                "stake_pct": round((current / initial) * 100, 2) if initial > 0 else 0.0,
                "total_rewards": round(self._staking_total_rewards.get(name, 0.0), 4),
                "total_penalties": round(self._staking_total_penalties.get(name, 0.0), 4),
                "degraded_threshold": round(initial * _STAKE_DEGRADATION_FACTOR, 4),
            }
        total_rewards = sum(self._staking_total_rewards.values())
        total_penalties = sum(self._staking_total_penalties.values())
        return {
            "agents": report,
            "global_total_rewards": round(total_rewards, 4),
            "global_total_penalties": round(total_penalties, 4),
        }

    def replenish_stake(self, agent_name: str, amount: float) -> dict:
        """Top-up an agent's stake balance.

        Can be called manually or on a schedule to restore operational
        capacity after penalty deductions.

        Args:
            agent_name: Name of the agent.
            amount: Positive amount to add to the agent's stake.

        Returns:
            Dict with previous and new stake balances.
        """
        if agent_name not in self._agent_stakes:
            return {"error": f"Unknown agent: {agent_name}"}
        if amount <= 0:
            return {"error": "Amount must be positive"}
        previous = self._agent_stakes[agent_name]
        self._agent_stakes[agent_name] = previous + amount
        logger.info("Agent %s stake replenished: %.4f -> %.4f (+%.4f)",
                    agent_name, previous, self._agent_stakes[agent_name], amount)
        return {
            "agent_name": agent_name,
            "previous_stake": round(previous, 4),
            "replenished": round(amount, 4),
            "new_stake": round(self._agent_stakes[agent_name], 4),
        }

    # ── Upgrade #10: Degradation Audit Chain ─────────────────────────────

    def _generate_degradation_attestation(
        self, agent_name: str, previous_health: AgentHealth,
        new_health: AgentHealth, trigger_reason: str
    ) -> dict:
        """Create and store an attestation dict when an agent degrades.

        The attestation captures capability status, a partial reasoning
        trace (recent operations), and is appended to ``_degradation_log``.

        Args:
            agent_name: Name of the agent transitioning.
            previous_health: Health state before the transition.
            new_health: Health state after the transition.
            trigger_reason: Human-readable reason for the transition.

        Returns:
            The attestation dict that was stored.
        """
        all_caps = list(AGENT_CAPABILITIES.get(agent_name, []))
        if new_health == AgentHealth.FAILED:
            available = []
            unavailable = all_caps
        elif new_health == AgentHealth.DEGRADED:
            # In DEGRADED mode, health_check-type actions remain available
            available = [c for c in all_caps if "check" in c or "report" in c or "health" in c]
            unavailable = [c for c in all_caps if c not in available]
            # Ensure at least some are available if the heuristic yields nothing
            if not available and all_caps:
                available = all_caps[:1]
                unavailable = all_caps[1:]
        else:
            available = all_caps
            unavailable = []

        trace = list(self._agent_operation_trace.get(agent_name, []))

        attestation = {
            "agent_name": agent_name,
            "previous_health": previous_health.value,
            "new_health": new_health.value,
            "trigger_reason": trigger_reason,
            "available_capabilities": available,
            "unavailable_capabilities": unavailable,
            "partial_reasoning_trace": trace,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._degradation_log.append(attestation)
        logger.info("Degradation attestation recorded for %s: %s -> %s (%s)",
                    agent_name, previous_health.value, new_health.value, trigger_reason)
        return attestation

    def get_degradation_attestations(self, agent_name: str | None = None) -> list[dict]:
        """Return degradation attestations, optionally filtered by agent name.

        Args:
            agent_name: If provided, only attestations for this agent are
                returned.  If ``None``, all attestations are returned.

        Returns:
            List of attestation dicts ordered from oldest to newest.
        """
        if agent_name is None:
            return list(self._degradation_log)
        return [a for a in self._degradation_log if a["agent_name"] == agent_name]
