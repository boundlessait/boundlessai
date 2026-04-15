// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IGenesisModule} from "../IGenesisModule.sol";

/// @title LiquidityShieldModule - Just-in-time liquidity protection
/// @notice Detects when large swaps are about to cause significant price impact
///         and applies a proportional "shield fee" to protect passive LPs from
///         adverse selection by informed flow.
///
///  Shield fee logic:
///   1. Estimate price impact of the incoming swap as a fraction of pool depth
///   2. If impact exceeds `maxImpactBps`, apply shield fee proportional to impact
///   3. Track cumulative impact per block to prevent liquidity draining attacks
///   4. If cumulative block impact exceeds `blockImpactCap`, block further swaps
///
///  The shield fee formula:
///    shieldFee = (estimatedImpactBps * shieldFeeMultiplier) / PRECISION
///
///  This module complements DynamicFeeModule (volatility-based) by adding a
///  flow-toxicity dimension. Together they implement the full Genesis LP
///  protection stack on Uniswap V4.
///
///  Security: Follows v4-security-foundations guidelines from uniswap-ai:
///   - No beforeSwapReturnDelta usage (avoids NoOp rug pull risk)
///   - Gas budget stays within V4 recommended ceiling (~50k per callback)
///   - Per-block impact tracking prevents multi-swap drain vectors
contract LiquidityShieldModule is IGenesisModule {

    // ─── State ───────────────────────────────────────────────────────────
    address public assembler;

    uint256 public maxImpactBps;          // impact threshold before shield fee kicks in (bps)
    uint256 public shieldFeeMultiplier;   // multiplier for impact → fee mapping
    uint256 public blockImpactCap;        // max cumulative impact per block (bps) before blocking

    // Pool depth estimates (set by Agent via updatePoolDepth)
    uint256 public poolDepthToken0;       // estimated token0 liquidity in active range
    uint256 public poolDepthToken1;       // estimated token1 liquidity in active range
    uint256 public lastDepthUpdate;       // timestamp of last depth update

    // Per-block tracking
    uint256 private _currentBlock;
    uint256 private _blockCumulativeImpact;  // cumulative impact this block (bps)
    uint256 private _blockSwapCount;

    // Stats
    uint256 public totalShielded;         // swaps that incurred a shield fee
    uint256 public totalBlockedByCap;     // swaps blocked due to block impact cap
    uint256 public totalInspected;
    uint256 public totalShieldFeeRevenue; // cumulative shield fee (for Strategy NFT metadata)

    uint256 constant PRECISION = 10000;
    uint256 constant DEPTH_STALE_THRESHOLD = 1800; // 30 minutes

    // ─── Events ──────────────────────────────────────────────────────────
    event ShieldFeeApplied(
        address indexed sender,
        uint256 amountIn,
        uint256 estimatedImpactBps,
        uint24 shieldFee,
        uint256 blockCumulativeImpact
    );
    event SwapBlockedByImpactCap(
        address indexed sender,
        uint256 amountIn,
        uint256 blockCumulativeImpact,
        uint256 blockNumber
    );
    event PoolDepthUpdated(
        uint256 oldDepth0,
        uint256 newDepth0,
        uint256 oldDepth1,
        uint256 newDepth1,
        uint256 timestamp
    );
    event ParamsUpdated(
        uint256 maxImpactBps,
        uint256 shieldFeeMultiplier,
        uint256 blockImpactCap
    );

    // ─── Errors ──────────────────────────────────────────────────────────
    error OnlyAssembler();
    error InvalidParams();

    modifier onlyAssembler() {
        if (msg.sender != assembler) revert OnlyAssembler();
        _;
    }

    constructor(
        address _assembler,
        uint256 _maxImpactBps,
        uint256 _shieldFeeMultiplier,
        uint256 _blockImpactCap
    ) {
        assembler = _assembler;
        maxImpactBps = _maxImpactBps;
        shieldFeeMultiplier = _shieldFeeMultiplier;
        blockImpactCap = _blockImpactCap;
    }

    // ─── Core Logic ──────────────────────────────────────────────────────

    function beforeSwapModule(
        address sender,
        uint256 amountIn,
        bool zeroForOne
    ) external override returns (uint24 fee, bool blocked) {
        totalInspected++;
        _resetIfNewBlock();

        // Estimate price impact based on swap size vs pool depth
        uint256 impactBps = _estimateImpact(amountIn, zeroForOne);

        // Accumulate block-level impact
        _blockCumulativeImpact += impactBps;
        _blockSwapCount++;

        // Check 1: Block if cumulative impact exceeds per-block cap
        if (_blockCumulativeImpact > blockImpactCap) {
            totalBlockedByCap++;
            emit SwapBlockedByImpactCap(
                sender,
                amountIn,
                _blockCumulativeImpact,
                block.number
            );
            return (0, true);
        }

        // Check 2: Apply shield fee if individual impact exceeds threshold
        if (impactBps > maxImpactBps) {
            uint24 shieldFee = _computeShieldFee(impactBps);
            totalShielded++;
            totalShieldFeeRevenue += (uint256(shieldFee) * amountIn) / 1e6;
            emit ShieldFeeApplied(
                sender,
                amountIn,
                impactBps,
                shieldFee,
                _blockCumulativeImpact
            );
            return (shieldFee, false);
        }

        return (0, false); // No significant impact, no fee override
    }

    function afterSwapModule(uint256, uint256, bool) external override {
        // LiquidityShieldModule has no after-swap logic
    }

    /// @notice Agent pushes latest pool depth estimates from on-chain observation
    /// @dev Pool depth is read from V4 PoolManager by the off-chain Genesis Agent
    ///      and pushed periodically. This avoids expensive on-chain liquidity reads.
    function updatePoolDepth(
        uint256 _depth0,
        uint256 _depth1
    ) external onlyAssembler {
        uint256 oldD0 = poolDepthToken0;
        uint256 oldD1 = poolDepthToken1;
        poolDepthToken0 = _depth0;
        poolDepthToken1 = _depth1;
        lastDepthUpdate = block.timestamp;
        emit PoolDepthUpdated(oldD0, _depth0, oldD1, _depth1, block.timestamp);
    }

    // ─── Internal ────────────────────────────────────────────────────────

    function _resetIfNewBlock() internal {
        if (block.number != _currentBlock) {
            _currentBlock = block.number;
            _blockCumulativeImpact = 0;
            _blockSwapCount = 0;
        }
    }

    /// @notice Estimate price impact in basis points
    /// @dev Simple model: impact ≈ amountIn / poolDepth * 10000
    ///      If pool depth data is stale, assume worst case (high impact)
    function _estimateImpact(
        uint256 amountIn,
        bool zeroForOne
    ) internal view returns (uint256) {
        uint256 depth = zeroForOne ? poolDepthToken0 : poolDepthToken1;

        // If depth is unknown or stale, return conservative high estimate
        if (depth == 0 || block.timestamp - lastDepthUpdate > DEPTH_STALE_THRESHOLD) {
            return maxImpactBps + 1; // Trigger shield fee
        }

        // Impact in basis points = (amountIn * 10000) / depth
        return (amountIn * PRECISION) / depth;
    }

    /// @notice Compute shield fee proportional to estimated price impact
    /// @dev shieldFee = (impactBps * shieldFeeMultiplier) / PRECISION
    ///      Clamped to uint24 max (1677215 = ~167.72%)
    function _computeShieldFee(uint256 impactBps) internal view returns (uint24) {
        uint256 rawFee = (impactBps * shieldFeeMultiplier) / PRECISION;

        // Clamp to uint24 max
        if (rawFee > type(uint24).max) return type(uint24).max;
        return uint24(rawFee);
    }

    // ─── IGenesisModule Interface ────────────────────────────────────────

    function moduleId() external pure override returns (bytes32) {
        return keccak256("genesis.module.liquidity-shield.v1");
    }

    function getParams() external view override returns (bytes memory) {
        return abi.encode(
            maxImpactBps, shieldFeeMultiplier, blockImpactCap,
            poolDepthToken0, poolDepthToken1,
            totalShielded, totalBlockedByCap, totalInspected,
            totalShieldFeeRevenue
        );
    }

    function updateParams(bytes calldata params) external override onlyAssembler {
        (
            uint256 _maxImpactBps,
            uint256 _shieldFeeMultiplier,
            uint256 _blockImpactCap
        ) = abi.decode(params, (uint256, uint256, uint256));

        if (_maxImpactBps == 0 || _blockImpactCap == 0) revert InvalidParams();

        maxImpactBps = _maxImpactBps;
        shieldFeeMultiplier = _shieldFeeMultiplier;
        blockImpactCap = _blockImpactCap;

        emit ParamsUpdated(_maxImpactBps, _shieldFeeMultiplier, _blockImpactCap);
    }
}
