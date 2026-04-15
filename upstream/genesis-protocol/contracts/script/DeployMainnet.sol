// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "forge-std/Script.sol";
import {GenesisHookAssembler} from "../src/GenesisHookAssembler.sol";
import {DynamicFeeModule} from "../src/modules/DynamicFeeModule.sol";
import {MEVProtectionModule} from "../src/modules/MEVProtectionModule.sol";
import {AutoRebalanceModule} from "../src/modules/AutoRebalanceModule.sol";
import {LiquidityShieldModule} from "../src/modules/LiquidityShieldModule.sol";
import {OracleModule} from "../src/modules/OracleModule.sol";
import {StrategyNFT} from "../src/StrategyNFT.sol";

/// @title DeployMainnet - Deploy Genesis Protocol to X Layer Mainnet (Chain 196)
/// @notice Run: forge script script/DeployMainnet.sol:DeployMainnet --rpc-url https://rpc.xlayer.tech --broadcast
contract DeployMainnet is Script {
    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        console.log("=== Genesis Protocol - X Layer Mainnet Deployment ===");
        console.log("Deployer:", deployer);
        console.log("Chain ID:", block.chainid);

        vm.startBroadcast(deployerKey);

        // 1. Deploy GenesisHookAssembler
        GenesisHookAssembler assembler = new GenesisHookAssembler(deployer);
        console.log("GenesisHookAssembler:", address(assembler));

        // 2. Deploy DynamicFeeModule
        DynamicFeeModule feeModule = new DynamicFeeModule(
            address(assembler),
            3000,   // baseFee 0.30%
            500,    // minFee 0.05%
            10000,  // maxFee 1.00%
            10000,  // sensitivity 1.0x
            200,    // lowThreshold 2%
            800     // highThreshold 8%
        );
        console.log("DynamicFeeModule:", address(feeModule));

        // 3. Deploy MEVProtectionModule
        MEVProtectionModule mevModule = new MEVProtectionModule(
            address(assembler),
            3,          // swapCountThreshold
            10000,      // volumeThreshold
            5000,       // penaltyFee 0.50%
            false       // blockSuspicious (start with penalty only)
        );
        console.log("MEVProtectionModule:", address(mevModule));

        // 4. Deploy AutoRebalanceModule
        AutoRebalanceModule rebalModule = new AutoRebalanceModule(
            address(assembler),
            -6000,  // lowerTick
            6000,   // upperTick
            85,     // softTriggerPct
            200,    // ilThresholdBps 2%
            300,    // cooldownPeriod 5min
            AutoRebalanceModule.RebalanceStrategy.IMMEDIATE
        );
        console.log("AutoRebalanceModule:", address(rebalModule));

        // 5. Deploy LiquidityShieldModule
        LiquidityShieldModule shieldModule = new LiquidityShieldModule(
            address(assembler),
            50,     // maxImpactBps 0.50% impact threshold
            15000,  // shieldFeeMultiplier 1.5x
            500     // blockImpactCap 5.00% cumulative per block
        );
        console.log("LiquidityShieldModule:", address(shieldModule));

        // 6. Deploy OracleModule
        OracleModule oracleModule = new OracleModule(
            address(assembler),
            1800,   // observationWindow 30 minutes
            120     // maxObservations (ring buffer size)
        );
        console.log("OracleModule:", address(oracleModule));

        // 7. Deploy StrategyNFT
        StrategyNFT nft = new StrategyNFT(deployer);
        console.log("StrategyNFT:", address(nft));

        // 8. Register modules
        assembler.registerModule(address(feeModule));
        assembler.registerModule(address(mevModule));
        assembler.registerModule(address(rebalModule));
        assembler.registerModule(address(shieldModule));
        assembler.registerModule(address(oracleModule));
        console.log("All modules registered (5 total).");

        vm.stopBroadcast();

        console.log("\n=== Deployment Complete ===");
        console.log("Update config.py and README.md with mainnet addresses.");
    }
}
