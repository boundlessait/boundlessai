// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {GenesisV4Hook} from "./GenesisV4Hook.sol";
import {GenesisHookAssembler} from "./GenesisHookAssembler.sol";
import {IPoolManager} from "v4-core/src/interfaces/IPoolManager.sol";

contract HookDeployer {
    function deploy(
        IPoolManager poolManager,
        GenesisHookAssembler assembler,
        bytes32 salt
    ) external returns (address) {
        GenesisV4Hook hook = new GenesisV4Hook{salt: salt}(poolManager, assembler);
        return address(hook);
    }

    function computeAddress(
        IPoolManager poolManager,
        GenesisHookAssembler assembler,
        bytes32 salt
    ) external view returns (address) {
        bytes32 initCodeHash = keccak256(
            abi.encodePacked(
                type(GenesisV4Hook).creationCode,
                abi.encode(poolManager, assembler)
            )
        );
        return address(uint160(uint256(keccak256(
            abi.encodePacked(bytes1(0xff), address(this), salt, initCodeHash)
        ))));
    }
}
