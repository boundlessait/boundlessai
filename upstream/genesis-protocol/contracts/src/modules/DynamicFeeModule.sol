// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IGenesisModule} from "../IGenesisModule.sol";

/// @title DynamicFeeModule - Volatility-responsive fee adjustment
/// @notice Computes a dynamic swap fee based on realized volatility signals
///         fed by the off-chain Genesis Agent via periodic updates.
///
///  Fee curve:  fee = baseFee + (volatility * sensitivity / PRECISION)
///
///  - In calm markets (vol < lowThreshold):  fee drops to attract volume
///  - In volatile markets (vol > highThreshold): fee spikes to protect LPs
///  - Mid-range: linear interpolation
///
///  The Agent monitors OnchainOS Market data, computes 24h realized vol,
///  and calls `updateVolatility()` every N minutes. The hook reads this
///  cached value in `beforeSwap` — zero external calls, minimal gas.
contract DynamicFeeModule is IGenesisModule {

    // ─── State ───────────────────────────────────────────────────────────
    address public assembler;

    uint24 public baseFee;          // in hundredths of a bip, e.g. 3000 = 0.30%
    uint24 public minFee;           // floor
    uint24 public maxFee;           // ceiling
    uint256 public sensitivity;     // multiplier for vol → fee mapping
    uint256 public lowThreshold;    // vol below this → use minFee
    uint256 public highThreshold;   // vol above this → use maxFee

    uint256 public currentVolatility;   // latest vol pushed by Agent (basis points)
    uint256 public lastVolUpdate;       // timestamp of last vol push

    uint256 public totalSwaps;
    uint256 public totalFeeRevenue;     // cumulative fee (for Strategy NFT metadata)

    uint256 constant PRECISION = 10000;
    uint256 constant STALE_THRESHOLD = 3600; // 1 hour

    // ─── Events ──────────────────────────────────────────────────────────
    event VolatilityUpdated(uint256 oldVol, uint256 newVol, uint256 timestamp);
    event FeeComputed(uint24 fee, uint256 volatility, uint256 amountIn);
    event ParamsUpdated(uint24 baseFee, uint24 minFee, uint24 maxFee, uint256 sensitivity);

    // ─── Errors ──────────────────────────────────────────────────────────
    error OnlyAssembler();
    error InvalidParams();

    modifier onlyAssembler() {
        if (msg.sender != assembler) revert OnlyAssembler();
        _;
    }

    constructor(
        address _assembler,
        uint24 _baseFee,
        uint24 _minFee,
        uint24 _maxFee,
        uint256 _sensitivity,
        uint256 _lowThreshold,
        uint256 _highThreshold
    ) {
        assembler = _assembler;
        baseFee = _baseFee;
        minFee = _minFee;
        maxFee = _maxFee;
        sensitivity = _sensitivity;
        lowThreshold = _lowThreshold;
        highThreshold = _highThreshold;
    }

    // ─── Core Logic ──────────────────────────────────────────────────────

    function beforeSwapModule(
        address,
        uint256 amountIn,
        bool
    ) external override returns (uint24 fee, bool blocked) {
        fee = _computeFee();
        blocked = false;
        totalSwaps++;
        totalFeeRevenue += (uint256(fee) * amountIn) / 1e6;
        emit FeeComputed(fee, currentVolatility, amountIn);
    }

    function afterSwapModule(uint256, uint256, bool) external override {
        // DynamicFeeModule has no after-swap logic
    }

    /// @notice Agent calls this to push latest volatility reading
    function updateVolatility(uint256 _newVol) external onlyAssembler {
        uint256 old = currentVolatility;
        currentVolatility = _newVol;
        lastVolUpdate = block.timestamp;
        emit VolatilityUpdated(old, _newVol, block.timestamp);
    }

    // ─── Fee Calculation ─────────────────────────────────────────────────

    function _computeFee() internal view returns (uint24) {
        uint256 vol = currentVolatility;

        // If volatility data is stale, use conservative maxFee
        if (block.timestamp - lastVolUpdate > STALE_THRESHOLD) {
            return maxFee;
        }

        // Low vol regime → attract volume
        if (vol <= lowThreshold) {
            return minFee;
        }

        // High vol regime → protect LPs
        if (vol >= highThreshold) {
            return maxFee;
        }

        // Mid-range: linear interpolation
        uint256 range = highThreshold - lowThreshold;
        uint256 position = vol - lowThreshold;
        uint256 feeRange = uint256(maxFee) - uint256(minFee);
        uint256 dynamicFee = uint256(minFee) + (position * feeRange) / range;

        // Apply sensitivity multiplier
        dynamicFee = (dynamicFee * sensitivity) / PRECISION;

        // Clamp to [minFee, maxFee]
        if (dynamicFee < uint256(minFee)) return minFee;
        if (dynamicFee > uint256(maxFee)) return maxFee;
        return uint24(dynamicFee);
    }

    // ─── IGenesisModule Interface ────────────────────────────────────────

    function moduleId() external pure override returns (bytes32) {
        return keccak256("genesis.module.dynamic-fee.v1");
    }

    function getParams() external view override returns (bytes memory) {
        return abi.encode(
            baseFee, minFee, maxFee, sensitivity,
            lowThreshold, highThreshold,
            currentVolatility, totalSwaps, totalFeeRevenue
        );
    }

    function updateParams(bytes calldata params) external override onlyAssembler {
        (
            uint24 _baseFee, uint24 _minFee, uint24 _maxFee,
            uint256 _sensitivity, uint256 _low, uint256 _high
        ) = abi.decode(params, (uint24, uint24, uint24, uint256, uint256, uint256));

        if (_minFee > _maxFee || _low >= _high) revert InvalidParams();

        baseFee = _baseFee;
        minFee = _minFee;
        maxFee = _maxFee;
        sensitivity = _sensitivity;
        lowThreshold = _low;
        highThreshold = _high;

        emit ParamsUpdated(_baseFee, _minFee, _maxFee, _sensitivity);
    }
}
