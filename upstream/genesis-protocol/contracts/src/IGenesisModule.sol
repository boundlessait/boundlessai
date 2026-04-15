// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title IGenesisModule - Interface for composable hook modules
/// @notice Each module implements a specific strategy behavior that can be
///         combined by the HookAssembler into a single deployable V4 Hook.
interface IGenesisModule {
    /// @notice Called before a swap to potentially modify fee or block the swap
    /// @param sender The swap initiator
    /// @param amountIn The input amount
    /// @param zeroForOne Direction of the swap
    /// @return fee The dynamic fee in hundredths of a bip (0 = no override)
    /// @return blocked Whether this module wants to block the swap
    function beforeSwapModule(
        address sender,
        uint256 amountIn,
        bool zeroForOne
    ) external returns (uint24 fee, bool blocked);

    /// @notice Called after a swap to update internal state
    /// @param amountIn Actual input amount
    /// @param amountOut Actual output amount
    /// @param zeroForOne Direction of the swap
    function afterSwapModule(
        uint256 amountIn,
        uint256 amountOut,
        bool zeroForOne
    ) external;

    /// @notice Returns the module's identifier
    function moduleId() external pure returns (bytes32);

    /// @notice Returns current module parameters as encoded bytes
    function getParams() external view returns (bytes memory);

    /// @notice Updates module parameters (only callable by assembler)
    /// @param params New parameters encoded as bytes
    function updateParams(bytes calldata params) external;
}
