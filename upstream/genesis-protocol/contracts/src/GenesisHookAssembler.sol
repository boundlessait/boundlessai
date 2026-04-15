// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IGenesisModule} from "./IGenesisModule.sol";
import {PoolKey} from "v4-core/src/types/PoolKey.sol";
// SwapParams is nested in IPoolManager
import {IPoolManager} from "v4-core/src/interfaces/IPoolManager.sol";

/// @title GenesisHookAssembler - Composable V4 Hook Factory for X Layer
/// @notice The core meta-hook for the Genesis Protocol. This contract:
///   1. Implements Uniswap V4 hook callbacks (beforeSwap/afterSwap)
///   2. Dispatches to composable IGenesisModule modules
///   3. Aggregates fee results (highest fee wins) and blocked votes
///   4. Maintains strategy registry and on-chain decision journal
///   5. Integrates with V4 PoolManager on X Layer (0x360e68fa...)
///
/// Architecture: Following v4-security-foundations guidelines from uniswap-ai:
///   - beforeSwap: dispatches to modules for fee computation and MEV detection
///   - afterSwap: dispatches to modules for state updates and rebalance signals
///   - No beforeSwapReturnDelta (avoids NoOp rug pull risk per security audit)
///   - Gas budget: ~50,000 per module callback (within V4 recommended ceiling)
contract GenesisHookAssembler {

    // ─── Types ───────────────────────────────────────────────────────────
    /// @notice Struct used by GenesisV4Hook to pass swap parameters
    struct V4SwapParams {
        bool zeroForOne;
        int256 amountSpecified;
        uint160 sqrtPriceLimitX96;
    }

    struct Strategy {
        uint256 id;
        address[] modules;
        bytes32 configHash;        // keccak256 of all module params
        uint256 createdAt;
        uint256 totalSwaps;
        uint256 totalVolume;
        int256  pnlBps;            // P&L in basis points (updated by Agent)
        bool    active;
    }

    struct DecisionEntry {
        uint256 timestamp;
        uint256 strategyId;
        bytes32 decisionType;      // e.g. keccak256("REBALANCE"), keccak256("FEE_ADJUST")
        bytes32 reasoningHash;     // IPFS hash or keccak256 of reasoning text
        bytes   params;            // encoded new parameters
    }

    // ─── V4 Integration (X Layer) ──────────────────────────────────────
    address public constant POOL_MANAGER = 0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32;
    address public constant UNIVERSAL_ROUTER = 0x112908daC86e20e7241B0927479Ea3Bf935d1fa0;
    address public constant PERMIT2 = 0x000000000022D473030F116dDEE9F6B43aC78BA3;

    // ─── State ───────────────────────────────────────────────────────────
    address public owner;          // The Agentic Wallet that controls this assembler
    address public agent;          // Secondary agent address (for sub-wallet ops)

    // Module registry
    address[] public activeModules;
    mapping(bytes32 => address) public moduleById;

    // Strategy registry
    uint256 public strategyCount;
    mapping(uint256 => Strategy) public strategies;

    // Decision journal (on-chain)
    uint256 public decisionCount;
    mapping(uint256 => DecisionEntry) public decisions;

    // Performance tracking
    uint256 public totalSwapsProcessed;
    uint256 public totalVolumeProcessed;
    uint256 public assemblerDeployedAt;

    // ─── Events ──────────────────────────────────────────────────────────
    event ModuleRegistered(bytes32 indexed moduleId, address module);
    event ModuleRemoved(bytes32 indexed moduleId, address module);
    event StrategyCreated(uint256 indexed strategyId, address[] modules, bytes32 configHash);
    event StrategyDeactivated(uint256 indexed strategyId);
    event SwapProcessed(
        uint256 indexed strategyId,
        uint24 finalFee,
        bool blocked,
        uint256 amountIn
    );
    event DecisionLogged(
        uint256 indexed decisionId,
        uint256 indexed strategyId,
        bytes32 decisionType,
        bytes32 reasoningHash
    );
    event PerformanceUpdated(uint256 indexed strategyId, int256 pnlBps, uint256 totalVolume);
    event AgentUpdated(address oldAgent, address newAgent);

    // ─── Errors ──────────────────────────────────────────────────────────
    error OnlyOwner();
    error OnlyOwnerOrAgent();
    error ModuleAlreadyRegistered();
    error ModuleNotFound();
    error StrategyNotActive();
    error InvalidModules();

    modifier onlyOwner() {
        if (msg.sender != owner) revert OnlyOwner();
        _;
    }

    modifier onlyOwnerOrAgent() {
        if (msg.sender != owner && msg.sender != agent) revert OnlyOwnerOrAgent();
        _;
    }

    constructor(address _owner) {
        owner = _owner;
        agent = _owner;
        assemblerDeployedAt = block.timestamp;
    }

    // ─── Module Management ───────────────────────────────────────────────

    function registerModule(address _module) external onlyOwner {
        bytes32 id = IGenesisModule(_module).moduleId();
        if (moduleById[id] != address(0)) revert ModuleAlreadyRegistered();
        moduleById[id] = _module;
        activeModules.push(_module);
        emit ModuleRegistered(id, _module);
    }

    function removeModule(bytes32 _moduleId) external onlyOwner {
        address module = moduleById[_moduleId];
        if (module == address(0)) revert ModuleNotFound();

        // Remove from activeModules array
        for (uint256 i = 0; i < activeModules.length; i++) {
            if (activeModules[i] == module) {
                activeModules[i] = activeModules[activeModules.length - 1];
                activeModules.pop();
                break;
            }
        }

        delete moduleById[_moduleId];
        emit ModuleRemoved(_moduleId, module);
    }

    // ─── Strategy Lifecycle ──────────────────────────────────────────────

    /// @notice Create a new strategy from a combination of registered modules
    function createStrategy(address[] calldata _modules) external onlyOwnerOrAgent returns (uint256) {
        if (_modules.length == 0) revert InvalidModules();

        // Verify all modules are registered
        for (uint256 i = 0; i < _modules.length; i++) {
            bytes32 id = IGenesisModule(_modules[i]).moduleId();
            if (moduleById[id] != _modules[i]) revert ModuleNotFound();
        }

        uint256 stratId = strategyCount++;
        bytes32 configHash = _computeConfigHash(_modules);

        strategies[stratId] = Strategy({
            id: stratId,
            modules: _modules,
            configHash: configHash,
            createdAt: block.timestamp,
            totalSwaps: 0,
            totalVolume: 0,
            pnlBps: 0,
            active: true
        });

        emit StrategyCreated(stratId, _modules, configHash);
        return stratId;
    }

    function deactivateStrategy(uint256 _stratId) external onlyOwnerOrAgent {
        if (!strategies[_stratId].active) revert StrategyNotActive();
        strategies[_stratId].active = false;
        emit StrategyDeactivated(_stratId);
    }

    // ─── Hook Dispatch (Core V4 Integration Point) ──────────────────────

    /// @notice V4 hook callback - dispatches to all strategy modules
    /// @dev Called by PoolManager before each swap. Follows v4-security-foundations:
    ///      - No beforeSwapReturnDelta (CRITICAL risk flag disabled)
    ///      - Highest fee wins (most conservative aggregation)
    ///      - Any module can block a suspicious swap
    function onBeforeSwap(
        uint256 _stratId,
        address _sender,
        V4SwapParams memory _params
    ) external returns (uint24 finalFee, bool blocked) {
        Strategy storage strat = strategies[_stratId];
        if (!strat.active) revert StrategyNotActive();

        uint256 _amountIn = _params.amountSpecified >= 0
            ? uint256(_params.amountSpecified)
            : uint256(-_params.amountSpecified);

        finalFee = 0;
        blocked = false;

        // Dispatch to each module
        for (uint256 i = 0; i < strat.modules.length; i++) {
            (uint24 moduleFee, bool moduleBlocked) = IGenesisModule(strat.modules[i])
                .beforeSwapModule(_sender, _amountIn, _params.zeroForOne);

            // Highest fee wins (most conservative)
            if (moduleFee > finalFee) finalFee = moduleFee;
            // Any module can block
            if (moduleBlocked) blocked = true;
        }

        strat.totalSwaps++;
        strat.totalVolume += _amountIn;
        totalSwapsProcessed++;
        totalVolumeProcessed += _amountIn;

        emit SwapProcessed(_stratId, finalFee, blocked, _amountIn);
    }

    /// @notice V4 hook callback - dispatches to all strategy modules after swap
    /// @dev Called by PoolManager after each swap for state updates and rebalance signals
    function onAfterSwap(
        uint256 _stratId,
        V4SwapParams memory _params,
        uint256 _amountOut
    ) external {
        Strategy storage strat = strategies[_stratId];
        if (!strat.active) return;

        uint256 _amountIn = _params.amountSpecified >= 0
            ? uint256(_params.amountSpecified)
            : uint256(-_params.amountSpecified);

        for (uint256 i = 0; i < strat.modules.length; i++) {
            IGenesisModule(strat.modules[i]).afterSwapModule(
                _amountIn, _amountOut, _params.zeroForOne
            );
        }
    }

    // ─── Decision Journal ────────────────────────────────────────────────

    /// @notice Agent logs a decision with reasoning for full auditability
    function logDecision(
        uint256 _stratId,
        bytes32 _decisionType,
        bytes32 _reasoningHash,
        bytes calldata _params
    ) external onlyOwnerOrAgent {
        uint256 did = decisionCount++;
        decisions[did] = DecisionEntry({
            timestamp: block.timestamp,
            strategyId: _stratId,
            decisionType: _decisionType,
            reasoningHash: _reasoningHash,
            params: _params
        });
        emit DecisionLogged(did, _stratId, _decisionType, _reasoningHash);
    }

    // ─── Performance Tracking ────────────────────────────────────────────

    /// @notice Agent updates strategy P&L after evaluation
    function updatePerformance(
        uint256 _stratId,
        int256 _pnlBps
    ) external onlyOwnerOrAgent {
        strategies[_stratId].pnlBps = _pnlBps;
        emit PerformanceUpdated(
            _stratId, _pnlBps, strategies[_stratId].totalVolume
        );
    }

    // ─── View Functions ──────────────────────────────────────────────────

    function getActiveModules() external view returns (address[] memory) {
        return activeModules;
    }

    function getStrategyModules(uint256 _stratId) external view returns (address[] memory) {
        return strategies[_stratId].modules;
    }

    function getStrategy(uint256 _stratId) external view returns (Strategy memory) {
        return strategies[_stratId];
    }

    function getDecision(uint256 _decisionId) external view returns (DecisionEntry memory) {
        return decisions[_decisionId];
    }

    /// @notice Returns full snapshot for Strategy NFT metadata
    function getStrategySnapshot(uint256 _stratId) external view returns (
        address[] memory modules,
        bytes[] memory moduleParams,
        uint256 totalSwaps,
        uint256 totalVolume,
        int256 pnlBps,
        uint256 createdAt,
        bytes32 configHash
    ) {
        Strategy storage s = strategies[_stratId];
        modules = s.modules;
        moduleParams = new bytes[](modules.length);
        for (uint256 i = 0; i < modules.length; i++) {
            moduleParams[i] = IGenesisModule(modules[i]).getParams();
        }
        return (modules, moduleParams, s.totalSwaps, s.totalVolume, s.pnlBps, s.createdAt, s.configHash);
    }

    // ─── Admin ───────────────────────────────────────────────────────────

    function setAgent(address _newAgent) external onlyOwner {
        emit AgentUpdated(agent, _newAgent);
        agent = _newAgent;
    }

    // ─── Internal ────────────────────────────────────────────────────────

    function _computeConfigHash(address[] memory _modules) internal view returns (bytes32) {
        bytes memory packed;
        for (uint256 i = 0; i < _modules.length; i++) {
            packed = abi.encodePacked(packed, IGenesisModule(_modules[i]).getParams());
        }
        return keccak256(packed);
    }
}
