// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "forge-std/Script.sol";
import {GenesisHookAssembler} from "../src/GenesisHookAssembler.sol";
import {LiquidityShieldModule} from "../src/modules/LiquidityShieldModule.sol";
import {OracleModule} from "../src/modules/OracleModule.sol";

contract DeployNewModules is Script {
    address constant ASSEMBLER = 0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78;

    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        console.log("=== Deploy New Modules to X Layer Testnet ===");
        console.log("Deployer:", deployer);
        console.log("Assembler:", ASSEMBLER);

        vm.startBroadcast(deployerKey);

        // Deploy LiquidityShieldModule
        LiquidityShieldModule shield = new LiquidityShieldModule(
            ASSEMBLER,
            50,     // maxImpactBps
            15000,  // shieldFeeMultiplier 1.5x
            500     // blockImpactCap
        );
        console.log("LiquidityShieldModule:", address(shield));

        // Deploy OracleModule
        OracleModule oracle = new OracleModule(
            ASSEMBLER,
            1800,   // observationWindow 30min
            120     // maxObservations
        );
        console.log("OracleModule:", address(oracle));

        // Note: modules are registered separately via cast or manual tx.
        // Previous deployment already registered moduleIds on the assembler.
        console.log("Deploy complete. Register via cast if needed.");

        vm.stopBroadcast();
    }
}
