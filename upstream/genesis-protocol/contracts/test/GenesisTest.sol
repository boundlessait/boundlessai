// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "forge-std/Test.sol";
import {IGenesisModule} from "../src/IGenesisModule.sol";
import {GenesisHookAssembler} from "../src/GenesisHookAssembler.sol";
import {StrategyNFT} from "../src/StrategyNFT.sol";
import {DynamicFeeModule} from "../src/modules/DynamicFeeModule.sol";
import {MEVProtectionModule} from "../src/modules/MEVProtectionModule.sol";
import {AutoRebalanceModule} from "../src/modules/AutoRebalanceModule.sol";
import {GenesisV4Hook} from "../src/GenesisV4Hook.sol";
import {IPoolManager} from "v4-core/src/interfaces/IPoolManager.sol";

contract GenesisTest is Test {
    // --- Actors ---
    address owner = address(0xA1);
    address agent = address(0xA2);
    address alice = address(0xB1);
    address bob   = address(0xB2);

    // --- Contracts ---
    GenesisHookAssembler assembler;
    DynamicFeeModule     feeModule;
    MEVProtectionModule  mevModule;
    AutoRebalanceModule  rebalModule;
    StrategyNFT          nft;

    // --- Module IDs ---
    bytes32 feeModId;
    bytes32 mevModId;
    bytes32 rebalModId;

    // --- Placeholder: filled in by sections below ---

    function setUp() public {
        vm.startPrank(owner);

        assembler = new GenesisHookAssembler(owner);
        assembler.setAgent(agent);

        // Deploy modules with assembler as their controller
        feeModule = new DynamicFeeModule(
            address(assembler),
            3000,   // baseFee
            1000,   // minFee
            10000,  // maxFee
            10000,  // sensitivity (1x at PRECISION=10000)
            200,    // lowThreshold
            800     // highThreshold
        );

        mevModule = new MEVProtectionModule(
            address(assembler),
            2,          // swapCountThreshold
            100 ether,  // volumeThreshold
            5000,       // penaltyFee
            true        // blockSuspicious
        );

        rebalModule = new AutoRebalanceModule(
            address(assembler),
            -1000,  // lowerTick
            1000,   // upperTick
            85,     // softTriggerPct
            500,    // ilThresholdBps
            60,     // cooldownPeriod (60s)
            AutoRebalanceModule.RebalanceStrategy.IMMEDIATE
        );

        nft = new StrategyNFT(owner);

        // Cache module IDs
        feeModId   = feeModule.moduleId();
        mevModId   = mevModule.moduleId();
        rebalModId = rebalModule.moduleId();

        // Register all modules
        assembler.registerModule(address(feeModule));
        assembler.registerModule(address(mevModule));
        assembler.registerModule(address(rebalModule));

        vm.stopPrank();
    }

    // ================================================================
    // Helper: construct V4 SwapParams
    // ================================================================

    function _swapParams(bool zeroForOne, int256 amount) internal pure returns (GenesisHookAssembler.V4SwapParams memory) {
        return GenesisHookAssembler.V4SwapParams({
            zeroForOne: zeroForOne,
            amountSpecified: amount,
            sqrtPriceLimitX96: 0
        });
    }

    // ================================================================
    // 1. Module Registration & Removal
    // ================================================================

    function test_registerModule_storesAddress() public view {
        assertEq(assembler.moduleById(feeModId), address(feeModule));
        assertEq(assembler.moduleById(mevModId), address(mevModule));
        address[] memory active = assembler.getActiveModules();
        assertEq(active.length, 3);
    }

    function test_registerModule_revertsDuplicate() public {
        vm.prank(owner);
        vm.expectRevert(GenesisHookAssembler.ModuleAlreadyRegistered.selector);
        assembler.registerModule(address(feeModule));
    }

    function test_removeModule_success() public {
        vm.prank(owner);
        assembler.removeModule(feeModId);

        assertEq(assembler.moduleById(feeModId), address(0));
        address[] memory active = assembler.getActiveModules();
        assertEq(active.length, 2);
    }

    function test_removeModule_revertsNotFound() public {
        vm.prank(owner);
        vm.expectRevert(GenesisHookAssembler.ModuleNotFound.selector);
        assembler.removeModule(keccak256("nonexistent"));
    }

    // ================================================================
    // 2. Strategy Creation
    // ================================================================

    function test_createStrategy_withAllModules() public {
        address[] memory mods = new address[](3);
        mods[0] = address(feeModule);
        mods[1] = address(mevModule);
        mods[2] = address(rebalModule);

        vm.prank(owner);
        uint256 id = assembler.createStrategy(mods);

        assertEq(id, 0);
        GenesisHookAssembler.Strategy memory s = assembler.getStrategy(0);
        assertTrue(s.active);
        assertEq(s.modules.length, 3);
    }

    function test_createStrategy_revertsEmpty() public {
        address[] memory mods = new address[](0);
        vm.prank(owner);
        vm.expectRevert(GenesisHookAssembler.InvalidModules.selector);
        assembler.createStrategy(mods);
    }

    function test_createStrategy_revertsUnregistered() public {
        address[] memory mods = new address[](1);
        mods[0] = address(0xDEAD);
        vm.prank(owner);
        vm.expectRevert(); // call to moduleId() on non-contract will revert
        assembler.createStrategy(mods);
    }

    function test_createStrategy_agentCanCreate() public {
        address[] memory mods = new address[](1);
        mods[0] = address(feeModule);
        vm.prank(agent);
        uint256 id = assembler.createStrategy(mods);
        assertEq(id, 0);
    }

    // ================================================================
    // 3. onBeforeSwap Dispatch (fee aggregation & blocking)
    // ================================================================

    function test_onBeforeSwap_aggregatesFees() public {
        // Create a strategy with fee + rebalance (rebalance returns fee=0)
        address[] memory mods = new address[](2);
        mods[0] = address(feeModule);
        mods[1] = address(rebalModule);

        vm.prank(owner);
        uint256 sid = assembler.createStrategy(mods);

        // Set volatility to low so fee = minFee (1000)
        vm.prank(address(assembler));
        feeModule.updateVolatility(100); // below lowThreshold

        (uint24 fee, bool blocked) = assembler.onBeforeSwap(sid, alice, _swapParams(true, 1 ether));
        assertEq(fee, 1000); // minFee wins (rebalance returns 0)
        assertFalse(blocked);
    }

    function test_onBeforeSwap_anyModuleCanBlock() public {
        // Strategy with MEV module (blockSuspicious = true, threshold = 2)
        address[] memory mods = new address[](1);
        mods[0] = address(mevModule);

        vm.prank(owner);
        uint256 sid = assembler.createStrategy(mods);

        // First two swaps are fine (count <= threshold)
        assembler.onBeforeSwap(sid, alice, _swapParams(true, 1 ether));
        assembler.onBeforeSwap(sid, bob, _swapParams(true, 1 ether));

        // Third same-direction swap exceeds swapCountThreshold of 2
        (, bool blocked) = assembler.onBeforeSwap(sid, alice, _swapParams(true, 1 ether));
        assertTrue(blocked);
    }

    function test_onBeforeSwap_updatesVolumeAndSwaps() public {
        address[] memory mods = new address[](1);
        mods[0] = address(rebalModule);

        vm.prank(owner);
        uint256 sid = assembler.createStrategy(mods);

        assembler.onBeforeSwap(sid, alice, _swapParams(true, 5 ether));
        assembler.onBeforeSwap(sid, alice, _swapParams(false, 3 ether));

        GenesisHookAssembler.Strategy memory s = assembler.getStrategy(sid);
        assertEq(s.totalSwaps, 2);
        assertEq(s.totalVolume, 8 ether);
        assertEq(assembler.totalSwapsProcessed(), 2);
        assertEq(assembler.totalVolumeProcessed(), 8 ether);
    }

    function test_onBeforeSwap_revertsInactiveStrategy() public {
        address[] memory mods = new address[](1);
        mods[0] = address(rebalModule);
        vm.prank(owner);
        uint256 sid = assembler.createStrategy(mods);

        vm.prank(owner);
        assembler.deactivateStrategy(sid);

        vm.expectRevert(GenesisHookAssembler.StrategyNotActive.selector);
        assembler.onBeforeSwap(sid, alice, _swapParams(true, 1 ether));
    }

    // ================================================================
    // 4. DynamicFeeModule: fee at different volatility levels
    // ================================================================

    function test_dynamicFee_lowVol_returnsMinFee() public {
        vm.prank(address(assembler));
        feeModule.updateVolatility(100); // below lowThreshold=200

        (uint24 fee,) = feeModule.beforeSwapModule(alice, 1 ether, true);
        assertEq(fee, 1000); // minFee
    }

    function test_dynamicFee_highVol_returnsMaxFee() public {
        vm.prank(address(assembler));
        feeModule.updateVolatility(900); // above highThreshold=800

        (uint24 fee,) = feeModule.beforeSwapModule(alice, 1 ether, true);
        assertEq(fee, 10000); // maxFee
    }

    function test_dynamicFee_midVol_returnsInterpolated() public {
        vm.prank(address(assembler));
        feeModule.updateVolatility(500); // midpoint of [200, 800]

        (uint24 fee,) = feeModule.beforeSwapModule(alice, 1 ether, true);
        // Mid-range: minFee + (300/600) * (maxFee - minFee) = 1000 + 0.5*9000 = 5500
        // sensitivity = 10000 (1x), so dynamicFee = 5500 * 10000 / 10000 = 5500
        assertEq(fee, 5500);
    }

    function test_dynamicFee_staleVol_returnsMaxFee() public {
        vm.prank(address(assembler));
        feeModule.updateVolatility(100);

        // Warp past STALE_THRESHOLD (3600s)
        vm.warp(block.timestamp + 3601);

        (uint24 fee,) = feeModule.beforeSwapModule(alice, 1 ether, true);
        assertEq(fee, 10000); // maxFee (conservative fallback)
    }

    // ================================================================
    // 5. MEVProtectionModule: sandwich detection
    // ================================================================

    function test_mev_firstSwapPasses() public {
        (uint24 fee, bool blocked) = mevModule.beforeSwapModule(alice, 1 ether, true);
        assertEq(fee, 0);
        assertFalse(blocked);
    }

    function test_mev_exceedCountThreshold_blocks() public {
        // threshold = 2, so 3rd same-direction swap triggers
        mevModule.beforeSwapModule(alice, 1 ether, true);
        mevModule.beforeSwapModule(bob, 1 ether, true);
        (, bool blocked) = mevModule.beforeSwapModule(alice, 1 ether, true);
        assertTrue(blocked);
        assertEq(mevModule.totalBlocked(), 1);
    }

    function test_mev_exceedVolumeThreshold_blocks() public {
        // volumeThreshold = 100 ether
        mevModule.beforeSwapModule(alice, 50 ether, true);
        (, bool blocked) = mevModule.beforeSwapModule(bob, 51 ether, true);
        assertTrue(blocked); // cumulative 101 ether > 100 ether
    }

    function test_mev_newBlockResetsCounters() public {
        mevModule.beforeSwapModule(alice, 1 ether, true);
        mevModule.beforeSwapModule(bob, 1 ether, true);

        // Advance to new block
        vm.roll(block.number + 1);

        (uint24 fee, bool blocked) = mevModule.beforeSwapModule(alice, 1 ether, true);
        assertEq(fee, 0);
        assertFalse(blocked); // counters reset
    }

    // ================================================================
    // 6. AutoRebalanceModule: signal emission at boundary
    // ================================================================

    function test_rebalance_outOfRange_emitsSignal() public {
        vm.warp(100); // advance past initial cooldown
        vm.prank(address(assembler));
        rebalModule.updateMarketState(1001, 2000e18); // tick > upperTick

        assertEq(rebalModule.totalSignals(), 1);
    }

    function test_rebalance_cooldownPreventsRepeat() public {
        vm.warp(100); // advance past initial cooldown
        vm.prank(address(assembler));
        rebalModule.updateMarketState(1001, 2000e18);
        assertEq(rebalModule.totalSignals(), 1);

        // Still within cooldown (60s)
        vm.warp(block.timestamp + 30);
        vm.prank(address(assembler));
        rebalModule.updateMarketState(1002, 2100e18);
        assertEq(rebalModule.totalSignals(), 1); // no new signal

        // Past cooldown
        vm.warp(block.timestamp + 61);
        vm.prank(address(assembler));
        rebalModule.updateMarketState(1003, 2200e18);
        assertEq(rebalModule.totalSignals(), 2);
    }

    function test_rebalance_confirmUpdatesRange() public {
        vm.prank(address(assembler));
        rebalModule.confirmRebalance(-500, 500);

        assertEq(rebalModule.lowerTick(), -500);
        assertEq(rebalModule.upperTick(), 500);
        assertEq(rebalModule.totalRebalances(), 1);
    }

    // ================================================================
    // 7. StrategyNFT: minting with full metadata
    // ================================================================

    function test_nft_mintAndReadMeta() public {
        address[] memory mods = new address[](1);
        mods[0] = address(feeModule);
        bytes[] memory params = new bytes[](1);
        params[0] = feeModule.getParams();

        vm.prank(owner);
        uint256 tokenId = nft.mint(
            alice,
            address(assembler),
            0,                          // strategyId
            keccak256("config"),        // configHash
            mods,
            params,
            42,                         // totalSwaps
            100 ether,                  // totalVolume
            350,                        // pnlBps
            5,                          // decisionCount
            7 days,                     // runDuration
            600,                        // marketVol
            1800e18                     // marketPrice
        );

        assertEq(tokenId, 0);
        assertEq(nft.ownerOf(0), alice);
        assertEq(nft.balanceOf(alice), 1);
        assertEq(nft.totalSupply(), 1);

        StrategyNFT.StrategyMeta memory meta = nft.getStrategyMeta(0);
        assertEq(meta.assembler, address(assembler));
        assertEq(meta.pnlBps, 350);
        assertEq(meta.totalSwaps, 42);
    }

    function test_nft_onlyMinterCanMint() public {
        address[] memory mods = new address[](0);
        bytes[] memory params = new bytes[](0);

        vm.prank(alice);
        vm.expectRevert(StrategyNFT.OnlyMinter.selector);
        nft.mint(alice, address(0), 0, bytes32(0), mods, params, 0, 0, 0, 0, 0, 0, 0);
    }

    function test_nft_cannotMintToZero() public {
        address[] memory mods = new address[](0);
        bytes[] memory params = new bytes[](0);

        vm.prank(owner);
        vm.expectRevert(StrategyNFT.InvalidRecipient.selector);
        nft.mint(address(0), address(0), 0, bytes32(0), mods, params, 0, 0, 0, 0, 0, 0, 0);
    }

    function test_nft_getMetaRevertsForNonexistent() public {
        vm.expectRevert(StrategyNFT.TokenDoesNotExist.selector);
        nft.getStrategyMeta(999);
    }

    // ================================================================
    // 8. Decision Journal
    // ================================================================

    function test_decisionJournal_logAndRetrieve() public {
        bytes32 decType = keccak256("FEE_ADJUST");
        bytes32 reasonHash = keccak256("vol spike detected");
        bytes memory paramsData = abi.encode(uint24(5000));

        vm.prank(agent);
        assembler.logDecision(0, decType, reasonHash, paramsData);

        assertEq(assembler.decisionCount(), 1);

        GenesisHookAssembler.DecisionEntry memory d = assembler.getDecision(0);
        assertEq(d.strategyId, 0);
        assertEq(d.decisionType, decType);
        assertEq(d.reasoningHash, reasonHash);
    }

    function test_decisionJournal_multipleEntries() public {
        vm.startPrank(agent);
        assembler.logDecision(0, keccak256("REBALANCE"), bytes32(0), "");
        assembler.logDecision(1, keccak256("FEE_ADJUST"), bytes32(0), "");
        vm.stopPrank();

        assertEq(assembler.decisionCount(), 2);
        GenesisHookAssembler.DecisionEntry memory d1 = assembler.getDecision(1);
        assertEq(d1.strategyId, 1);
    }

    // ================================================================
    // 9. Performance Updates
    // ================================================================

    function test_performance_updatePnl() public {
        // Create a strategy first
        address[] memory mods = new address[](1);
        mods[0] = address(feeModule);
        vm.prank(owner);
        assembler.createStrategy(mods);

        vm.prank(agent);
        assembler.updatePerformance(0, 250);

        GenesisHookAssembler.Strategy memory s = assembler.getStrategy(0);
        assertEq(s.pnlBps, 250);
    }

    function test_performance_negativePnl() public {
        address[] memory mods = new address[](1);
        mods[0] = address(feeModule);
        vm.prank(owner);
        assembler.createStrategy(mods);

        vm.prank(agent);
        assembler.updatePerformance(0, -150);

        GenesisHookAssembler.Strategy memory s = assembler.getStrategy(0);
        assertEq(s.pnlBps, -150);
    }

    // ================================================================
    // 10. Access Control
    // ================================================================

    function test_acl_onlyOwner_registerModule() public {
        DynamicFeeModule newMod = new DynamicFeeModule(
            address(assembler), 3000, 1000, 10000, 10000, 200, 800
        );
        vm.prank(alice);
        vm.expectRevert(GenesisHookAssembler.OnlyOwner.selector);
        assembler.registerModule(address(newMod));
    }

    function test_acl_onlyOwner_removeModule() public {
        vm.prank(alice);
        vm.expectRevert(GenesisHookAssembler.OnlyOwner.selector);
        assembler.removeModule(feeModId);
    }

    function test_acl_onlyOwner_setAgent() public {
        vm.prank(alice);
        vm.expectRevert(GenesisHookAssembler.OnlyOwner.selector);
        assembler.setAgent(alice);
    }

    function test_acl_onlyOwnerOrAgent_createStrategy() public {
        address[] memory mods = new address[](1);
        mods[0] = address(feeModule);

        vm.prank(alice);
        vm.expectRevert(GenesisHookAssembler.OnlyOwnerOrAgent.selector);
        assembler.createStrategy(mods);
    }

    function test_acl_onlyOwnerOrAgent_logDecision() public {
        vm.prank(alice);
        vm.expectRevert(GenesisHookAssembler.OnlyOwnerOrAgent.selector);
        assembler.logDecision(0, bytes32(0), bytes32(0), "");
    }

    function test_acl_onlyOwnerOrAgent_updatePerformance() public {
        vm.prank(alice);
        vm.expectRevert(GenesisHookAssembler.OnlyOwnerOrAgent.selector);
        assembler.updatePerformance(0, 100);
    }

    function test_acl_onlyAssembler_feeModuleUpdateVol() public {
        vm.prank(alice);
        vm.expectRevert(DynamicFeeModule.OnlyAssembler.selector);
        feeModule.updateVolatility(500);
    }

    function test_acl_onlyAssembler_rebalModuleUpdate() public {
        vm.prank(alice);
        vm.expectRevert(AutoRebalanceModule.OnlyAssembler.selector);
        rebalModule.updateMarketState(0, 0);
    }

    // ================================================================
    // 12. GenesisV4Hook Integration (compile check)
    // ================================================================

    function test_v4Hook_deploys() public {
        // Use a mock address for PoolManager since we just need compile verification
        GenesisV4Hook hook = new GenesisV4Hook(IPoolManager(address(0xF001)), assembler);
        assertEq(address(hook.poolManager()), address(0xF001));
        assertEq(address(hook.assembler()), address(assembler));
    }

    function test_v4Hook_ownerCanSetStrategy() public {
        GenesisV4Hook hook = new GenesisV4Hook(IPoolManager(address(0xF001)), assembler);
        hook.setActiveStrategy(42);
        assertEq(hook.activeStrategyId(), 42);
    }

    function test_v4Hook_nonOwnerCannotSetStrategy() public {
        GenesisV4Hook hook = new GenesisV4Hook(IPoolManager(address(0xF001)), assembler);
        vm.prank(alice);
        vm.expectRevert(GenesisV4Hook.OnlyOwner.selector);
        hook.setActiveStrategy(1);
    }

    // ================================================================
    // 11. Strategy Snapshot (for NFT metadata)
    // ================================================================

    function test_strategySnapshot_returnsModuleParams() public {
        address[] memory mods = new address[](2);
        mods[0] = address(feeModule);
        mods[1] = address(mevModule);

        vm.prank(owner);
        uint256 sid = assembler.createStrategy(mods);

        (
            address[] memory snapMods,
            bytes[] memory snapParams,
            uint256 totalSwaps,
            uint256 totalVolume,
            int256 pnlBps,
            uint256 createdAt,
            bytes32 configHash
        ) = assembler.getStrategySnapshot(sid);

        assertEq(snapMods.length, 2);
        assertEq(snapParams.length, 2);
        assertEq(totalSwaps, 0);
        assertEq(totalVolume, 0);
        assertEq(pnlBps, 0);
        assertGt(createdAt, 0);
        assertTrue(configHash != bytes32(0));
    }
}
