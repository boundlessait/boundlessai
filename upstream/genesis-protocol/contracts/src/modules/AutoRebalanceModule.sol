// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IGenesisModule} from "../IGenesisModule.sol";

/// @title AutoRebalanceModule - Intelligent position range management
/// @notice Monitors price movement relative to the LP position range and emits
///         signals when rebalancing is needed. The off-chain Genesis Agent
///         listens for these events and executes the rebalance via
///         Agentic Wallet + OnchainOS DEX.
///
///  Rebalance triggers:
///   1. Price exits the configured range (hard trigger)
///   2. Price approaches range boundary beyond threshold (soft trigger)
///   3. Cumulative impermanent loss exceeds IL threshold
///
///  The module does NOT execute rebalances on-chain (too expensive/complex).
///  Instead it emits `RebalanceNeeded` events that the Agent monitors.
///  This is the hybrid architecture: on-chain detection + off-chain execution.
contract AutoRebalanceModule is IGenesisModule {

    // ─── State ───────────────────────────────────────────────────────────
    address public assembler;

    // Position range (set by Agent during deployment)
    int24 public lowerTick;
    int24 public upperTick;

    // Trigger parameters
    uint256 public softTriggerPct;   // e.g. 85 = trigger when 85% toward boundary
    uint256 public ilThresholdBps;   // max IL in basis points before forced rebalance
    uint256 public cooldownPeriod;   // min seconds between rebalance signals

    // Tracking state
    int24 public lastObservedTick;
    uint256 public lastRebalanceSignal;
    uint256 public entryPrice;       // price at position entry (for IL calc)
    uint256 public currentPrice;     // latest price (updated by afterSwap)

    // Strategy preference for rebalance execution
    enum RebalanceStrategy { IMMEDIATE, TWAP, THRESHOLD_ACCUMULATE }
    RebalanceStrategy public strategy;

    // Stats
    uint256 public totalSignals;
    uint256 public totalRebalances;  // incremented by Agent after execution

    // ─── Events ──────────────────────────────────────────────────────────
    event RebalanceNeeded(
        uint8 triggerType,       // 0=soft, 1=hard(out-of-range), 2=IL
        int24 currentTick,
        int24 lowerTick,
        int24 upperTick,
        uint256 currentPrice,
        uint256 estimatedIL,
        RebalanceStrategy suggestedStrategy
    );

    event RebalanceExecuted(
        int24 newLowerTick,
        int24 newUpperTick,
        uint256 timestamp
    );

    event PositionRangeUpdated(int24 newLower, int24 newUpper);

    // ─── Errors ──────────────────────────────────────────────────────────
    error OnlyAssembler();
    error CooldownActive();

    modifier onlyAssembler() {
        if (msg.sender != assembler) revert OnlyAssembler();
        _;
    }

    constructor(
        address _assembler,
        int24 _lowerTick,
        int24 _upperTick,
        uint256 _softTriggerPct,
        uint256 _ilThresholdBps,
        uint256 _cooldownPeriod,
        RebalanceStrategy _strategy
    ) {
        assembler = _assembler;
        lowerTick = _lowerTick;
        upperTick = _upperTick;
        softTriggerPct = _softTriggerPct;
        ilThresholdBps = _ilThresholdBps;
        cooldownPeriod = _cooldownPeriod;
        strategy = _strategy;
    }

    // ─── Core Logic ──────────────────────────────────────────────────────

    function beforeSwapModule(
        address,
        uint256,
        bool
    ) external pure override returns (uint24 fee, bool blocked) {
        // AutoRebalance has no before-swap fee logic
        return (0, false);
    }

    function afterSwapModule(
        uint256,
        uint256,
        bool
    ) external override {
        // In a real V4 hook, we'd get the current tick from the pool.
        // For the template, we use the last observed tick + price updates
        // pushed by the Agent.
        _checkRebalanceConditions();
    }

    /// @notice Agent pushes latest market state
    function updateMarketState(
        int24 _currentTick,
        uint256 _currentPrice
    ) external onlyAssembler {
        lastObservedTick = _currentTick;
        currentPrice = _currentPrice;
        _checkRebalanceConditions();
    }

    /// @notice Agent confirms rebalance was executed off-chain
    function confirmRebalance(
        int24 _newLower,
        int24 _newUpper
    ) external onlyAssembler {
        lowerTick = _newLower;
        upperTick = _newUpper;
        entryPrice = currentPrice;
        totalRebalances++;
        emit RebalanceExecuted(_newLower, _newUpper, block.timestamp);
        emit PositionRangeUpdated(_newLower, _newUpper);
    }

    // ─── Internal ────────────────────────────────────────────────────────

    function _checkRebalanceConditions() internal {
        if (block.timestamp - lastRebalanceSignal < cooldownPeriod) return;

        int24 tick = lastObservedTick;
        int24 rangeSize = upperTick - lowerTick;

        // Check 1: Hard trigger - price out of range
        if (tick <= lowerTick || tick >= upperTick) {
            _emitSignal(1, tick, _estimateIL());
            return;
        }

        // Check 2: Soft trigger - approaching boundary
        int24 distToLower = tick - lowerTick;
        int24 distToUpper = upperTick - tick;
        int24 minDist = distToLower < distToUpper ? distToLower : distToUpper;

        uint256 pctInRange = (uint256(uint24(minDist)) * 100) / uint256(uint24(rangeSize));
        // pctInRange = how far from the nearest edge (100 = center, 0 = edge)
        // softTriggerPct = 85 means trigger when within 15% of edge
        if (pctInRange < (100 - softTriggerPct)) {
            _emitSignal(0, tick, _estimateIL());
            return;
        }

        // Check 3: IL threshold
        uint256 il = _estimateIL();
        if (il > ilThresholdBps) {
            _emitSignal(2, tick, il);
            return;
        }
    }

    function _emitSignal(uint8 triggerType, int24 tick, uint256 il) internal {
        lastRebalanceSignal = block.timestamp;
        totalSignals++;
        emit RebalanceNeeded(
            triggerType,
            tick,
            lowerTick,
            upperTick,
            currentPrice,
            il,
            strategy
        );
    }

    /// @notice Simplified IL estimation based on price divergence
    function _estimateIL() internal view returns (uint256) {
        if (entryPrice == 0 || currentPrice == 0) return 0;

        uint256 priceRatio;
        if (currentPrice >= entryPrice) {
            priceRatio = (currentPrice * 10000) / entryPrice;
        } else {
            priceRatio = (entryPrice * 10000) / currentPrice;
        }

        // Simplified IL formula: IL ≈ 2*sqrt(r)/(1+r) - 1
        // For small deviations: IL ≈ (r-1)^2 / (4*r) in basis points
        if (priceRatio <= 10000) return 0;
        uint256 deviation = priceRatio - 10000;
        uint256 ilBps = (deviation * deviation) / (4 * priceRatio);
        return ilBps;
    }

    // ─── IGenesisModule Interface ────────────────────────────────────────

    function moduleId() external pure override returns (bytes32) {
        return keccak256("genesis.module.auto-rebalance.v1");
    }

    function getParams() external view override returns (bytes memory) {
        return abi.encode(
            lowerTick, upperTick, softTriggerPct, ilThresholdBps,
            cooldownPeriod, uint8(strategy), entryPrice, currentPrice,
            totalSignals, totalRebalances
        );
    }

    function updateParams(bytes calldata params) external override onlyAssembler {
        (
            int24 _lower, int24 _upper,
            uint256 _softPct, uint256 _ilThresh,
            uint256 _cooldown, uint8 _strat
        ) = abi.decode(params, (int24, int24, uint256, uint256, uint256, uint8));

        lowerTick = _lower;
        upperTick = _upper;
        softTriggerPct = _softPct;
        ilThresholdBps = _ilThresh;
        cooldownPeriod = _cooldown;
        strategy = RebalanceStrategy(_strat);

        emit PositionRangeUpdated(_lower, _upper);
    }
}
