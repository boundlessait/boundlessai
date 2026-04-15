// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IHooks} from "v4-core/src/interfaces/IHooks.sol";
import {IPoolManager} from "v4-core/src/interfaces/IPoolManager.sol";
import {PoolKey} from "v4-core/src/types/PoolKey.sol";
import {BalanceDelta, BalanceDeltaLibrary} from "v4-core/src/types/BalanceDelta.sol";
import {BeforeSwapDelta, BeforeSwapDeltaLibrary} from "v4-core/src/types/BeforeSwapDelta.sol";
import {ModifyLiquidityParams, SwapParams} from "v4-core/src/types/PoolOperation.sol";
import {LPFeeLibrary} from "v4-core/src/libraries/LPFeeLibrary.sol";
import {GenesisHookAssembler} from "./GenesisHookAssembler.sol";

/// @title GenesisV4Hook - Real Uniswap V4 Hook for Genesis Protocol
/// @notice This contract implements the real IHooks interface and delegates
///         module dispatch to GenesisHookAssembler. It is designed to be deployed
///         at a CREATE2-mined address with the correct hook permission flags.
/// @dev Hook flags required: BEFORE_SWAP | AFTER_SWAP (0xC0 in lowest byte)
///      Deployed via CREATE2 with salt mining to match address flags.
contract GenesisV4Hook is IHooks {

    /// @notice The V4 PoolManager on X Layer
    IPoolManager public immutable poolManager;

    /// @notice The Genesis strategy engine that dispatches to modules
    GenesisHookAssembler public immutable assembler;

    /// @notice Active strategy ID for this hook instance
    uint256 public activeStrategyId;

    /// @notice Owner for admin operations
    address public owner;

    error OnlyPoolManager();
    error OnlyOwner();

    modifier onlyPoolManager() {
        if (msg.sender != address(poolManager)) revert OnlyPoolManager();
        _;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert OnlyOwner();
        _;
    }

    constructor(IPoolManager _poolManager, GenesisHookAssembler _assembler) {
        poolManager = _poolManager;
        assembler = _assembler;
        owner = msg.sender;
    }

    /// @notice Set the active strategy for this hook
    function setActiveStrategy(uint256 _stratId) external onlyOwner {
        activeStrategyId = _stratId;
    }

    // ─── V4 Hook Callbacks (Real IHooks Implementation) ─────────────────

    /// @inheritdoc IHooks
    function beforeInitialize(address, PoolKey calldata, uint160)
        external pure override returns (bytes4)
    {
        return IHooks.beforeInitialize.selector;
    }

    /// @inheritdoc IHooks
    function afterInitialize(address, PoolKey calldata, uint160, int24)
        external pure override returns (bytes4)
    {
        return IHooks.afterInitialize.selector;
    }

    /// @inheritdoc IHooks
    function beforeAddLiquidity(address, PoolKey calldata, ModifyLiquidityParams calldata, bytes calldata)
        external pure override returns (bytes4)
    {
        return IHooks.beforeAddLiquidity.selector;
    }

    /// @inheritdoc IHooks
    function afterAddLiquidity(address, PoolKey calldata, ModifyLiquidityParams calldata, BalanceDelta, BalanceDelta, bytes calldata)
        external pure override returns (bytes4, BalanceDelta)
    {
        return (IHooks.afterAddLiquidity.selector, BalanceDeltaLibrary.ZERO_DELTA);
    }

    /// @inheritdoc IHooks
    function beforeRemoveLiquidity(address, PoolKey calldata, ModifyLiquidityParams calldata, bytes calldata)
        external pure override returns (bytes4)
    {
        return IHooks.beforeRemoveLiquidity.selector;
    }

    /// @inheritdoc IHooks
    function afterRemoveLiquidity(address, PoolKey calldata, ModifyLiquidityParams calldata, BalanceDelta, BalanceDelta, bytes calldata)
        external pure override returns (bytes4, BalanceDelta)
    {
        return (IHooks.afterRemoveLiquidity.selector, BalanceDeltaLibrary.ZERO_DELTA);
    }

    /// @inheritdoc IHooks
    /// @dev Core hook: dispatches to GenesisHookAssembler modules for fee computation
    ///      and MEV detection. Returns dynamic fee with OVERRIDE_FEE_FLAG set.
    function beforeSwap(
        address sender,
        PoolKey calldata,
        SwapParams calldata params,
        bytes calldata
    ) external override onlyPoolManager returns (bytes4, BeforeSwapDelta, uint24) {
        // Build the assembler's V4SwapParams from V4's real SwapParams
        GenesisHookAssembler.V4SwapParams memory asmParams = GenesisHookAssembler.V4SwapParams({
            zeroForOne: params.zeroForOne,
            amountSpecified: params.amountSpecified,
            sqrtPriceLimitX96: params.sqrtPriceLimitX96
        });

        (uint24 fee, bool blocked) = assembler.onBeforeSwap(
            activeStrategyId, sender, asmParams
        );

        // If blocked, return max fee to make swap uneconomical
        if (blocked) {
            fee = LPFeeLibrary.MAX_LP_FEE;
        }

        // Set OVERRIDE_FEE_FLAG to signal V4 to use this dynamic fee
        uint24 feeWithFlag = fee | LPFeeLibrary.OVERRIDE_FEE_FLAG;

        return (
            IHooks.beforeSwap.selector,
            BeforeSwapDeltaLibrary.ZERO_DELTA,
            feeWithFlag
        );
    }

    /// @inheritdoc IHooks
    /// @dev Dispatches to GenesisHookAssembler modules for post-swap state updates
    function afterSwap(
        address,
        PoolKey calldata,
        SwapParams calldata params,
        BalanceDelta delta,
        bytes calldata
    ) external override onlyPoolManager returns (bytes4, int128) {
        uint256 amountOut;
        if (params.zeroForOne) {
            amountOut = uint128(-delta.amount1());
        } else {
            amountOut = uint128(-delta.amount0());
        }

        GenesisHookAssembler.V4SwapParams memory asmParams = GenesisHookAssembler.V4SwapParams({
            zeroForOne: params.zeroForOne,
            amountSpecified: params.amountSpecified,
            sqrtPriceLimitX96: params.sqrtPriceLimitX96
        });

        assembler.onAfterSwap(activeStrategyId, asmParams, amountOut);

        return (IHooks.afterSwap.selector, 0);
    }

    /// @inheritdoc IHooks
    function beforeDonate(address, PoolKey calldata, uint256, uint256, bytes calldata)
        external pure override returns (bytes4)
    {
        return IHooks.beforeDonate.selector;
    }

    /// @inheritdoc IHooks
    function afterDonate(address, PoolKey calldata, uint256, uint256, bytes calldata)
        external pure override returns (bytes4)
    {
        return IHooks.afterDonate.selector;
    }
}
