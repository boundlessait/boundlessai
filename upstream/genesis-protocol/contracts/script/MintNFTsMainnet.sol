// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "forge-std/Script.sol";

interface IStrategyNFT {
    function mint(
        address _to,
        address _assembler,
        uint256 _strategyId,
        bytes32 _configHash,
        address[] calldata _modules,
        bytes[] calldata _moduleParams,
        uint256 _totalSwaps,
        uint256 _totalVolume,
        int256 _pnlBps,
        uint256 _decisionCount,
        uint256 _runDuration,
        uint256 _marketVol,
        uint256 _marketPrice
    ) external returns (uint256);

    function totalSupply() external view returns (uint256);
}

contract MintNFTsMainnet is Script {
    // Mainnet StrategyNFT
    address constant NFT = 0x8a0e87395f864405c5225eBd80391Ac82eefe437;
    address constant ASSEMBLER = 0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78;

    // Mainnet module addresses
    address constant DYN_FEE   = 0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed;
    address constant MEV       = 0xA4f6ABd6F77928b06F075637ccBACA8f89e17386;
    address constant REBAL     = 0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee;
    address constant LIQ_SHIELD = 0xd969448dfc24Fe3Aff25e86db338fAB41b104319;
    address constant ORACLE    = 0xCFc867E2379Cbe097D934CB8e19e3F028B82Bd3D;

    function run() external {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(pk);

        console.log("Minting Strategy NFTs on X Layer Mainnet...");
        console.log("Deployer:", deployer);

        vm.startBroadcast(pk);

        IStrategyNFT nft = IStrategyNFT(NFT);

        // NFT #1: calm_accumulator (2 modules: DynFee + Rebalance)
        {
            address[] memory mods = new address[](2);
            mods[0] = DYN_FEE;
            mods[1] = REBAL;
            bytes[] memory params = new bytes[](2);
            params[0] = abi.encode(uint24(100), uint24(3000), uint256(8000));
            params[1] = abi.encode(int24(-6000), int24(6000), uint256(90), uint256(300));

            uint256 id = nft.mint(
                deployer,
                ASSEMBLER,
                7,             // strategyId
                keccak256(abi.encodePacked(mods[0], mods[1])),
                mods,
                params,
                200,           // totalSwaps
                1200 ether,    // totalVolume
                180,           // pnlBps (+1.80%)
                38,            // decisionCount
                120 hours,     // runDuration
                180,           // marketVolatility
                48e18          // marketPrice (OKB)
            );
            console.log("Minted calm_accumulator NFT #", id);
        }

        // NFT #2: volatile_defender (3 modules: DynFee + MEV + Rebalance)
        {
            address[] memory mods = new address[](3);
            mods[0] = DYN_FEE;
            mods[1] = MEV;
            mods[2] = REBAL;
            bytes[] memory params = new bytes[](3);
            params[0] = abi.encode(uint24(1000), uint24(15000), uint256(12000));
            params[1] = abi.encode(uint256(3), uint256(10000), uint24(5000), true);
            params[2] = abi.encode(int24(-6000), int24(6000), uint256(70), uint256(120));

            uint256 id = nft.mint(
                deployer,
                ASSEMBLER,
                3,             // strategyId
                keccak256(abi.encodePacked(mods[0], mods[1], mods[2])),
                mods,
                params,
                85,            // totalSwaps
                500 ether,     // totalVolume
                280,           // pnlBps (+2.80%)
                45,            // decisionCount
                72 hours,      // runDuration
                650,           // marketVolatility
                2450e18        // marketPrice (ETH)
            );
            console.log("Minted volatile_defender NFT #", id);
        }

        // NFT #3: trend_rider (3 modules: DynFee + MEV + Rebalance)
        {
            address[] memory mods = new address[](3);
            mods[0] = DYN_FEE;
            mods[1] = MEV;
            mods[2] = REBAL;
            bytes[] memory params = new bytes[](3);
            params[0] = abi.encode(uint24(500), uint24(5000), uint256(9000));
            params[1] = abi.encode(uint256(3), uint256(10000), uint24(5000), false);
            params[2] = abi.encode(int24(-6000), int24(6000), uint256(75), uint256(300));

            uint256 id = nft.mint(
                deployer,
                ASSEMBLER,
                5,             // strategyId
                keccak256(abi.encodePacked(mods[0], mods[1], mods[2])),
                mods,
                params,
                120,           // totalSwaps
                800 ether,     // totalVolume
                450,           // pnlBps (+4.50%)
                62,            // decisionCount
                96 hours,      // runDuration
                420,           // marketVolatility
                2520e18        // marketPrice
            );
            console.log("Minted trend_rider NFT #", id);
        }

        // NFT #4: full_defense (5 modules: all modules)
        {
            address[] memory mods = new address[](5);
            mods[0] = DYN_FEE;
            mods[1] = MEV;
            mods[2] = REBAL;
            mods[3] = LIQ_SHIELD;
            mods[4] = ORACLE;
            bytes[] memory params = new bytes[](5);
            params[0] = abi.encode(uint24(800), uint24(12000), uint256(11000));
            params[1] = abi.encode(uint256(5), uint256(15000), uint24(8000), true);
            params[2] = abi.encode(int24(-4000), int24(4000), uint256(60), uint256(90));
            params[3] = abi.encode(uint256(500), uint256(10000), bool(true));
            params[4] = abi.encode(uint256(3600), uint256(300), bool(true));

            uint256 id = nft.mint(
                deployer,
                ASSEMBLER,
                10,            // strategyId
                keccak256(abi.encodePacked(mods[0], mods[1], mods[2], mods[3], mods[4])),
                mods,
                params,
                50,            // totalSwaps
                300 ether,     // totalVolume
                -120,          // pnlBps (-1.20% defensive)
                80,            // decisionCount
                48 hours,      // runDuration
                900,           // marketVolatility (high vol)
                2200e18        // marketPrice
            );
            console.log("Minted full_defense NFT #", id);
        }

        // NFT #5: shield_accumulator (3 modules: DynFee + LiqShield + Rebalance)
        {
            address[] memory mods = new address[](3);
            mods[0] = DYN_FEE;
            mods[1] = LIQ_SHIELD;
            mods[2] = REBAL;
            bytes[] memory params = new bytes[](3);
            params[0] = abi.encode(uint24(200), uint24(4000), uint256(8500));
            params[1] = abi.encode(uint256(300), uint256(8000), bool(true));
            params[2] = abi.encode(int24(-5000), int24(5000), uint256(85), uint256(240));

            uint256 id = nft.mint(
                deployer,
                ASSEMBLER,
                12,            // strategyId
                keccak256(abi.encodePacked(mods[0], mods[1], mods[2])),
                mods,
                params,
                150,           // totalSwaps
                900 ether,     // totalVolume
                220,           // pnlBps (+2.20%)
                55,            // decisionCount
                108 hours,     // runDuration
                300,           // marketVolatility
                52e18          // marketPrice (OKB)
            );
            console.log("Minted shield_accumulator NFT #", id);
        }

        vm.stopBroadcast();

        console.log("Total NFTs:", nft.totalSupply());
    }
}
