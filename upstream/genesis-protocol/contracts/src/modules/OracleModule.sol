// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IGenesisModule} from "../IGenesisModule.sol";

/// @title OracleModule - On-chain TWAP oracle for Genesis V4 hook pools
/// @notice Maintains a ring buffer of cumulative price observations and exposes
///         time-weighted average price (TWAP) queries over configurable windows.
///         Designed to feed DynamicFeeModule with better volatility estimation
///         and provide on-chain price data to the Genesis ecosystem.
///
///  Architecture:
///   1. afterSwap records a price observation (cumulative price tick)
///   2. Observations are stored in a fixed-size ring buffer
///   3. TWAP is computed as (cumulativeLast - cumulativeFirst) / elapsed
///   4. Realized volatility is derived from observation variance
///
///  Integration with Uniswap V4:
///   - Price data is derived from swap ratios (amountOut/amountIn)
///   - The off-chain Genesis Agent can also push tick observations from
///     V4 PoolManager.getSlot0() for higher fidelity
///   - TWAP feeds into DynamicFeeModule.updateVolatility() for fee optimization
///
///  Security: Follows v4-security-foundations guidelines from uniswap-ai:
///   - No beforeSwapReturnDelta usage (avoids NoOp rug pull risk)
///   - Ring buffer prevents unbounded storage growth
///   - Observation timestamps prevent stale-data manipulation
contract OracleModule is IGenesisModule {

    // ─── Types ───────────────────────────────────────────────────────────

    /// @notice A single price observation in the ring buffer
    struct Observation {
        uint256 timestamp;          // block.timestamp when recorded
        uint256 cumulativePrice;    // cumulative price (scaled by 1e18)
        uint256 spotPrice;          // instantaneous price at observation time
    }

    // ─── State ───────────────────────────────────────────────────────────
    address public assembler;

    uint256 public observationWindow;   // target TWAP window in seconds (e.g. 1800 = 30min)
    uint256 public maxObservations;     // ring buffer size

    // Ring buffer
    Observation[] public observations;
    uint256 public observationIndex;    // next write position
    uint256 public observationCount;    // total observations written (may exceed maxObservations)

    // Latest derived values
    uint256 public lastTwap;            // last computed TWAP (scaled 1e18)
    uint256 public lastVolatility;      // last computed realized vol (basis points)
    uint256 public lastUpdateTimestamp;

    // Stats
    uint256 public totalObservations;
    uint256 public totalTwapQueries;

    uint256 constant PRICE_PRECISION = 1e18;
    uint256 constant BPS = 10000;

    // ─── Events ──────────────────────────────────────────────────────────
    event ObservationRecorded(
        uint256 indexed index,
        uint256 timestamp,
        uint256 spotPrice,
        uint256 cumulativePrice
    );
    event TwapComputed(
        uint256 twap,
        uint256 windowSeconds,
        uint256 observationsUsed
    );
    event VolatilityComputed(
        uint256 realizedVol,
        uint256 windowSeconds,
        uint256 observationsUsed
    );
    event ParamsUpdated(
        uint256 observationWindow,
        uint256 maxObservations
    );

    // ─── Errors ──────────────────────────────────────────────────────────
    error OnlyAssembler();
    error InvalidParams();
    error InsufficientObservations();

    modifier onlyAssembler() {
        if (msg.sender != assembler) revert OnlyAssembler();
        _;
    }

    constructor(
        address _assembler,
        uint256 _observationWindow,
        uint256 _maxObservations
    ) {
        assembler = _assembler;
        observationWindow = _observationWindow;
        maxObservations = _maxObservations;

        // Initialize ring buffer storage
        for (uint256 i = 0; i < _maxObservations; i++) {
            observations.push(Observation(0, 0, 0));
        }
    }

    // ─── Core Logic ──────────────────────────────────────────────────────

    function beforeSwapModule(
        address,
        uint256,
        bool
    ) external pure override returns (uint24 fee, bool blocked) {
        // OracleModule has no before-swap fee logic
        return (0, false);
    }

    function afterSwapModule(
        uint256 amountIn,
        uint256 amountOut,
        bool
    ) external override {
        if (amountIn == 0) return;

        // Derive spot price from swap ratio: price = amountOut * 1e18 / amountIn
        uint256 spotPrice = (amountOut * PRICE_PRECISION) / amountIn;

        _recordObservation(spotPrice);
    }

    /// @notice Agent can push a tick-derived price observation from V4 PoolManager
    /// @dev Higher fidelity than swap-ratio observations; uses getSlot0() off-chain
    function pushObservation(uint256 _spotPrice) external onlyAssembler {
        _recordObservation(_spotPrice);
    }

    // ─── TWAP Queries ────────────────────────────────────────────────────

    /// @notice Compute TWAP over the configured observation window
    /// @return twap The time-weighted average price (scaled 1e18)
    /// @return observationsUsed Number of observations in the window
    function getTwap() external returns (uint256 twap, uint256 observationsUsed) {
        return getTwapForWindow(observationWindow);
    }

    /// @notice Compute TWAP over an arbitrary window
    /// @param windowSeconds The lookback window in seconds
    /// @return twap The time-weighted average price (scaled 1e18)
    /// @return observationsUsed Number of observations in the window
    function getTwapForWindow(
        uint256 windowSeconds
    ) public returns (uint256 twap, uint256 observationsUsed) {
        totalTwapQueries++;

        if (observationCount < 2) revert InsufficientObservations();

        uint256 cutoff = block.timestamp - windowSeconds;
        uint256 count = observationCount < maxObservations ? observationCount : maxObservations;

        // Find the oldest observation within the window
        uint256 oldestIdx = _findOldestInWindow(cutoff, count);
        uint256 newestIdx = observationIndex == 0 ? maxObservations - 1 : observationIndex - 1;

        Observation storage oldest = observations[oldestIdx];
        Observation storage newest = observations[newestIdx];

        uint256 elapsed = newest.timestamp - oldest.timestamp;
        if (elapsed == 0) revert InsufficientObservations();

        twap = (newest.cumulativePrice - oldest.cumulativePrice) / elapsed;
        observationsUsed = _countObservationsInWindow(cutoff, count);

        lastTwap = twap;
        lastUpdateTimestamp = block.timestamp;

        emit TwapComputed(twap, windowSeconds, observationsUsed);
    }

    /// @notice Compute realized volatility from recent observations
    /// @dev Uses simple standard deviation of log returns (approximated)
    /// @return volBps Realized volatility in basis points
    /// @return observationsUsed Number of observations used
    function getVolatility() external returns (uint256 volBps, uint256 observationsUsed) {
        if (observationCount < 3) revert InsufficientObservations();

        uint256 cutoff = block.timestamp - observationWindow;
        uint256 count = observationCount < maxObservations ? observationCount : maxObservations;

        // Collect returns within window
        uint256 sumSqDev = 0;
        uint256 sumReturn = 0;
        uint256 returnCount = 0;

        for (uint256 i = 1; i < count; i++) {
            uint256 currIdx = (observationIndex + maxObservations - i) % maxObservations;
            uint256 prevIdx = (observationIndex + maxObservations - i - 1) % maxObservations;

            Observation storage curr = observations[currIdx];
            Observation storage prev = observations[prevIdx];

            if (curr.timestamp < cutoff || prev.timestamp == 0) break;
            if (prev.spotPrice == 0) continue;

            // Approximate return in basis points
            uint256 ret;
            if (curr.spotPrice >= prev.spotPrice) {
                ret = ((curr.spotPrice - prev.spotPrice) * BPS) / prev.spotPrice;
            } else {
                ret = ((prev.spotPrice - curr.spotPrice) * BPS) / prev.spotPrice;
            }

            sumReturn += ret;
            sumSqDev += ret * ret;
            returnCount++;
        }

        if (returnCount < 2) revert InsufficientObservations();

        // Variance = E[X^2] - E[X]^2 (in bps^2)
        uint256 meanReturn = sumReturn / returnCount;
        uint256 variance = (sumSqDev / returnCount) - (meanReturn * meanReturn);

        // Approximate sqrt via Babylonian method for small values
        volBps = _sqrt(variance);
        observationsUsed = returnCount;

        lastVolatility = volBps;

        emit VolatilityComputed(volBps, observationWindow, returnCount);
    }

    // ─── Internal ────────────────────────────────────────────────────────

    function _recordObservation(uint256 spotPrice) internal {
        // Compute cumulative price
        uint256 prevCumulative = 0;
        uint256 prevTimestamp = 0;

        if (observationCount > 0) {
            uint256 prevIdx = observationIndex == 0
                ? maxObservations - 1
                : observationIndex - 1;
            prevCumulative = observations[prevIdx].cumulativePrice;
            prevTimestamp = observations[prevIdx].timestamp;
        }

        uint256 elapsed = prevTimestamp > 0 ? block.timestamp - prevTimestamp : 0;
        uint256 cumulativePrice = prevCumulative + (spotPrice * elapsed);

        observations[observationIndex] = Observation({
            timestamp: block.timestamp,
            cumulativePrice: cumulativePrice,
            spotPrice: spotPrice
        });

        emit ObservationRecorded(
            observationIndex,
            block.timestamp,
            spotPrice,
            cumulativePrice
        );

        observationIndex = (observationIndex + 1) % maxObservations;
        observationCount++;
        totalObservations++;
    }

    function _findOldestInWindow(
        uint256 cutoff,
        uint256 count
    ) internal view returns (uint256) {
        // Walk backward from newest to find the oldest observation within window
        for (uint256 i = count - 1; i > 0; i--) {
            uint256 idx = (observationIndex + maxObservations - i) % maxObservations;
            if (observations[idx].timestamp >= cutoff && observations[idx].timestamp > 0) {
                return idx;
            }
        }
        // Fallback: return the oldest available observation
        return observationIndex < count
            ? observationIndex
            : (observationIndex + maxObservations - count) % maxObservations;
    }

    function _countObservationsInWindow(
        uint256 cutoff,
        uint256 count
    ) internal view returns (uint256) {
        uint256 inWindow = 0;
        for (uint256 i = 0; i < count; i++) {
            uint256 idx = (observationIndex + maxObservations - 1 - i) % maxObservations;
            if (observations[idx].timestamp >= cutoff && observations[idx].timestamp > 0) {
                inWindow++;
            } else if (observations[idx].timestamp > 0) {
                break; // Past the window
            }
        }
        return inWindow;
    }

    /// @notice Integer square root via Babylonian method
    function _sqrt(uint256 x) internal pure returns (uint256) {
        if (x == 0) return 0;
        uint256 z = (x + 1) / 2;
        uint256 y = x;
        while (z < y) {
            y = z;
            z = (x / z + z) / 2;
        }
        return y;
    }

    // ─── IGenesisModule Interface ────────────────────────────────────────

    function moduleId() external pure override returns (bytes32) {
        return keccak256("genesis.module.oracle.v1");
    }

    function getParams() external view override returns (bytes memory) {
        return abi.encode(
            observationWindow, maxObservations,
            lastTwap, lastVolatility, lastUpdateTimestamp,
            totalObservations, totalTwapQueries
        );
    }

    function updateParams(bytes calldata params) external override onlyAssembler {
        (
            uint256 _observationWindow,
            uint256 _maxObservations
        ) = abi.decode(params, (uint256, uint256));

        if (_observationWindow == 0 || _maxObservations < 2) revert InvalidParams();

        observationWindow = _observationWindow;

        // If maxObservations increased, expand the ring buffer
        if (_maxObservations > maxObservations) {
            uint256 toAdd = _maxObservations - maxObservations;
            for (uint256 i = 0; i < toAdd; i++) {
                observations.push(Observation(0, 0, 0));
            }
        }
        maxObservations = _maxObservations;

        emit ParamsUpdated(_observationWindow, _maxObservations);
    }
}
