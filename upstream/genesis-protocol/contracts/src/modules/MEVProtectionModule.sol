// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IGenesisModule} from "../IGenesisModule.sol";

/// @title MEVProtectionModule - Sandwich attack detection and mitigation
/// @notice Detects potential sandwich attacks by tracking swap patterns within
///         the same block. If multiple same-direction swaps from different
///         senders occur in rapid succession, the module increases the
///         effective fee or blocks the swap entirely.
///
///  Detection heuristic (per-block):
///   1. Track the count of same-direction swaps in current block
///   2. Track cumulative volume in current block per direction
///   3. If count > threshold OR volume > volumeThreshold → flag as suspicious
///   4. Suspicious swaps incur a penalty fee or get blocked
///
///  This approach catches the most common sandwich pattern:
///    attacker buy → victim buy → attacker sell (same block)
contract MEVProtectionModule is IGenesisModule {

    // ─── State ───────────────────────────────────────────────────────────
    address public assembler;

    uint256 public swapCountThreshold;      // max same-direction swaps per block
    uint256 public volumeThreshold;         // max cumulative volume per direction per block
    uint24  public penaltyFee;              // extra fee for suspicious swaps
    bool    public blockSuspicious;         // if true, block rather than penalize

    // Per-block tracking
    uint256 private _currentBlock;
    uint256 private _buyCount;
    uint256 private _sellCount;
    uint256 private _buyVolume;
    uint256 private _sellVolume;
    address private _lastBuyer;
    address private _lastSeller;

    // Stats
    uint256 public totalBlocked;
    uint256 public totalPenalized;
    uint256 public totalInspected;

    // ─── Events ──────────────────────────────────────────────────────────
    event SandwichDetected(
        uint256 blockNumber,
        bool zeroForOne,
        uint256 directionCount,
        uint256 directionVolume,
        address sender
    );
    event SwapBlocked(address sender, uint256 blockNumber, string reason);
    event PenaltyApplied(address sender, uint24 penaltyFee, uint256 blockNumber);

    // ─── Errors ──────────────────────────────────────────────────────────
    error OnlyAssembler();
    error SwapBlockedByMEVProtection();

    modifier onlyAssembler() {
        if (msg.sender != assembler) revert OnlyAssembler();
        _;
    }

    constructor(
        address _assembler,
        uint256 _swapCountThreshold,
        uint256 _volumeThreshold,
        uint24 _penaltyFee,
        bool _blockSuspicious
    ) {
        assembler = _assembler;
        swapCountThreshold = _swapCountThreshold;
        volumeThreshold = _volumeThreshold;
        penaltyFee = _penaltyFee;
        blockSuspicious = _blockSuspicious;
    }

    // ─── Core Logic ──────────────────────────────────────────────────────

    function beforeSwapModule(
        address sender,
        uint256 amountIn,
        bool zeroForOne
    ) external override returns (uint24 fee, bool blocked) {
        totalInspected++;
        _resetIfNewBlock();

        // Track this swap
        if (zeroForOne) {
            _buyCount++;
            _buyVolume += amountIn;
            _lastBuyer = sender;
        } else {
            _sellCount++;
            _sellVolume += amountIn;
            _lastSeller = sender;
        }

        // Check for suspicious pattern
        bool isSuspicious = _checkSuspicious(zeroForOne);

        if (isSuspicious) {
            emit SandwichDetected(
                block.number,
                zeroForOne,
                zeroForOne ? _buyCount : _sellCount,
                zeroForOne ? _buyVolume : _sellVolume,
                sender
            );

            if (blockSuspicious) {
                totalBlocked++;
                emit SwapBlocked(sender, block.number, "MEV_PATTERN_DETECTED");
                return (0, true);
            } else {
                totalPenalized++;
                emit PenaltyApplied(sender, penaltyFee, block.number);
                return (penaltyFee, false);
            }
        }

        return (0, false); // No MEV concern, no fee override
    }

    function afterSwapModule(uint256, uint256, bool) external override {
        // No after-swap logic needed
    }

    // ─── Internal ────────────────────────────────────────────────────────

    function _resetIfNewBlock() internal {
        if (block.number != _currentBlock) {
            _currentBlock = block.number;
            _buyCount = 0;
            _sellCount = 0;
            _buyVolume = 0;
            _sellVolume = 0;
            _lastBuyer = address(0);
            _lastSeller = address(0);
        }
    }

    function _checkSuspicious(bool zeroForOne) internal view returns (bool) {
        uint256 count = zeroForOne ? _buyCount : _sellCount;
        uint256 volume = zeroForOne ? _buyVolume : _sellVolume;

        // Pattern 1: Too many same-direction swaps in one block
        if (count > swapCountThreshold) return true;

        // Pattern 2: Abnormally high volume in one direction
        if (volume > volumeThreshold) return true;

        // Pattern 3: Buy-then-sell from different addresses in same block
        // (classic sandwich: attacker buys, victim buys, attacker sells)
        if (_buyCount > 0 && _sellCount > 0 && _lastBuyer != _lastSeller) {
            if (_buyCount + _sellCount > swapCountThreshold) return true;
        }

        return false;
    }

    // ─── IGenesisModule Interface ────────────────────────────────────────

    function moduleId() external pure override returns (bytes32) {
        return keccak256("genesis.module.mev-protection.v1");
    }

    function getParams() external view override returns (bytes memory) {
        return abi.encode(
            swapCountThreshold, volumeThreshold, penaltyFee,
            blockSuspicious, totalBlocked, totalPenalized, totalInspected
        );
    }

    function updateParams(bytes calldata params) external override onlyAssembler {
        (
            uint256 _countThresh, uint256 _volThresh,
            uint24 _penalty, bool _block
        ) = abi.decode(params, (uint256, uint256, uint24, bool));

        swapCountThreshold = _countThresh;
        volumeThreshold = _volThresh;
        penaltyFee = _penalty;
        blockSuspicious = _block;
    }
}
