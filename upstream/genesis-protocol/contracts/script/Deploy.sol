// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "forge-std/Script.sol";
import {GenesisHookAssembler} from "../src/GenesisHookAssembler.sol";
import {DynamicFeeModule} from "../src/modules/DynamicFeeModule.sol";
import {MEVProtectionModule} from "../src/modules/MEVProtectionModule.sol";
import {AutoRebalanceModule} from "../src/modules/AutoRebalanceModule.sol";
import {StrategyNFT} from "../src/StrategyNFT.sol";
import {GenesisV4Hook} from "../src/GenesisV4Hook.sol";
import {IPoolManager} from "v4-core/src/interfaces/IPoolManager.sol";

contract Deploy is Script {

    // Uniswap V4 on X Layer
    address constant POOL_MANAGER = 0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32;
    address constant UNIVERSAL_ROUTER = 0x112908daC86e20e7241B0927479Ea3Bf935d1fa0;

    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        console.log("Deployer:", deployer);
        console.log("Chain ID:", block.chainid);

        vm.startBroadcast(deployerKey);

        // 1. Deploy Assembler
        GenesisHookAssembler assembler = new GenesisHookAssembler(deployer);
        console.log("GenesisHookAssembler:", address(assembler));

        // 2. Deploy DynamicFeeModule
        DynamicFeeModule dynFee = new DynamicFeeModule(
            address(assembler),
            3000,   // baseFee (0.30%)
            500,    // minFee (0.05%)
            10000,  // maxFee (1.00%)
            10000,  // sensitivity (1.0x)
            200,    // lowThreshold (2% vol)
            800     // highThreshold (8% vol)
        );
        console.log("DynamicFeeModule:", address(dynFee));

        // 3. Deploy MEVProtectionModule
        MEVProtectionModule mevProt = new MEVProtectionModule(
            address(assembler),
            3,      // swapCountThreshold
            10000,  // volumeThreshold
            5000,   // penaltyFee (0.50%)
            false   // blockSuspicious
        );
        console.log("MEVProtectionModule:", address(mevProt));

        // 4. Deploy AutoRebalanceModule
        AutoRebalanceModule autoRebal = new AutoRebalanceModule(
            address(assembler),
            -887220,    // lowerTick
            887220,     // upperTick
            85,         // softTriggerPct
            200,        // ilThresholdBps (2%)
            300,        // cooldownPeriod (5 min)
            AutoRebalanceModule.RebalanceStrategy.IMMEDIATE
        );
        console.log("AutoRebalanceModule:", address(autoRebal));

        // 5. Deploy StrategyNFT
        StrategyNFT nft = new StrategyNFT(deployer);
        console.log("StrategyNFT:", address(nft));

        // 6. Deploy GenesisV4Hook
        GenesisV4Hook v4Hook = new GenesisV4Hook(IPoolManager(POOL_MANAGER), assembler);
        console.log("GenesisV4Hook:", address(v4Hook));

        // 7. Register modules with assembler
        assembler.registerModule(address(dynFee));
        assembler.registerModule(address(mevProt));
        assembler.registerModule(address(autoRebal));
        console.log("All modules registered.");

        vm.stopBroadcast();

        console.log("--- Deployment Complete ---");
        console.log("--- Uniswap V4 Integration ---");
        console.log("PoolManager:", POOL_MANAGER);
        console.log("UniversalRouter:", UNIVERSAL_ROUTER);
    }
}
