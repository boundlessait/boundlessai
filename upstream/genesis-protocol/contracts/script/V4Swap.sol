// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "forge-std/Script.sol";
import {IPoolManager} from "v4-core/src/interfaces/IPoolManager.sol";
import {IUnlockCallback} from "v4-core/src/interfaces/callback/IUnlockCallback.sol";
import {PoolKey} from "v4-core/src/types/PoolKey.sol";
import {Currency, CurrencyLibrary} from "v4-core/src/types/Currency.sol";
import {IHooks} from "v4-core/src/interfaces/IHooks.sol";
import {BalanceDelta} from "v4-core/src/types/BalanceDelta.sol";
import {ModifyLiquidityParams, SwapParams} from "v4-core/src/types/PoolOperation.sol";
import {LPFeeLibrary} from "v4-core/src/libraries/LPFeeLibrary.sol";
import {TickMath} from "v4-core/src/libraries/TickMath.sol";
import {GenesisV4Hook} from "../src/GenesisV4Hook.sol";
import {GenesisHookAssembler} from "../src/GenesisHookAssembler.sol";

// ─── Inline Test Token ──────────────────────────────────────────────────────
contract TestToken {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor(string memory _name, string memory _symbol, uint256 _initialSupply) {
        name = _name;
        symbol = _symbol;
        totalSupply = _initialSupply;
        balanceOf[msg.sender] = _initialSupply;
        emit Transfer(address(0), msg.sender, _initialSupply);
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        return _transfer(msg.sender, to, amount);
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        if (allowed != type(uint256).max) {
            allowance[from][msg.sender] = allowed - amount;
        }
        return _transfer(from, to, amount);
    }

    function _transfer(address from, address to, uint256 amount) internal returns (bool) {
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
        return true;
    }
}

// ─── Swap Router (implements unlock callback pattern) ────────────────────────
contract SwapRouter is IUnlockCallback {
    IPoolManager public immutable poolManager;

    // Transient storage for callback context
    struct CallbackData {
        PoolKey key;
        SwapParams params;
        address sender;
    }

    // We store callback data in a state variable since transient storage
    // requires Cancun opcodes that may not be available everywhere
    CallbackData internal _callbackData;

    constructor(IPoolManager _poolManager) {
        poolManager = _poolManager;
    }

    /// @notice Execute a swap through the PoolManager unlock pattern
    function swap(PoolKey memory key, SwapParams memory params) external returns (BalanceDelta delta) {
        _callbackData = CallbackData({key: key, params: params, sender: msg.sender});
        bytes memory result = poolManager.unlock(abi.encode(key, params, msg.sender));
        delta = abi.decode(result, (BalanceDelta));
    }

    /// @notice Called by PoolManager inside unlock
    function unlockCallback(bytes calldata data) external override returns (bytes memory) {
        require(msg.sender == address(poolManager), "only PM");

        (PoolKey memory key, SwapParams memory params, address sender) =
            abi.decode(data, (PoolKey, SwapParams, address));

        BalanceDelta delta = poolManager.swap(key, params, "");

        // Settle negative deltas (tokens owed to the pool) and take positive deltas
        _settleDelta(key.currency0, delta.amount0(), sender);
        _settleDelta(key.currency1, delta.amount1(), sender);

        return abi.encode(delta);
    }

    function _settleDelta(Currency currency, int128 amount, address sender) internal {
        if (amount < 0) {
            // We owe the pool: sync first, then transfer, then settle
            uint256 amountOwed = uint256(uint128(-amount));
            poolManager.sync(currency);
            TestToken(Currency.unwrap(currency)).transferFrom(sender, address(poolManager), amountOwed);
            poolManager.settle();
        } else if (amount > 0) {
            // Pool owes us: take tokens out
            uint256 amountOwed = uint256(uint128(amount));
            poolManager.take(currency, sender, amountOwed);
        }
    }
}

// ─── Liquidity Helper (implements unlock callback for modifyLiquidity) ───────
contract LiquidityHelper is IUnlockCallback {
    IPoolManager public immutable poolManager;

    constructor(IPoolManager _poolManager) {
        poolManager = _poolManager;
    }

    function addLiquidity(
        PoolKey memory key,
        int24 tickLower,
        int24 tickUpper,
        int256 liquidityDelta,
        address sender
    ) external returns (BalanceDelta delta) {
        bytes memory result = poolManager.unlock(
            abi.encode(key, tickLower, tickUpper, liquidityDelta, sender)
        );
        delta = abi.decode(result, (BalanceDelta));
    }

    function unlockCallback(bytes calldata data) external override returns (bytes memory) {
        require(msg.sender == address(poolManager), "only PM");

        (PoolKey memory key, int24 tickLower, int24 tickUpper, int256 liquidityDelta, address sender) =
            abi.decode(data, (PoolKey, int24, int24, int256, address));

        ModifyLiquidityParams memory params = ModifyLiquidityParams({
            tickLower: tickLower,
            tickUpper: tickUpper,
            liquidityDelta: liquidityDelta,
            salt: bytes32(0)
        });

        (BalanceDelta delta,) = poolManager.modifyLiquidity(key, params, "");

        // Settle negative deltas (tokens we owe for providing liquidity)
        _settleDelta(key.currency0, delta.amount0(), sender);
        _settleDelta(key.currency1, delta.amount1(), sender);

        return abi.encode(delta);
    }

    function _settleDelta(Currency currency, int128 amount, address sender) internal {
        if (amount < 0) {
            uint256 amountOwed = uint256(uint128(-amount));
            poolManager.sync(currency);
            TestToken(Currency.unwrap(currency)).transferFrom(sender, address(poolManager), amountOwed);
            poolManager.settle();
        } else if (amount > 0) {
            uint256 amountOwed = uint256(uint128(amount));
            poolManager.take(currency, sender, amountOwed);
        }
    }
}

// ─── Main Deployment & Swap Script ──────────────────────────────────────────
contract V4Swap is Script {
    // Deployed contract addresses on X Layer Testnet
    address constant POOL_MANAGER = 0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32;
    address constant GENESIS_HOOK = 0x79a96bB2Ab2342cf6f1dD3c622F5CB01f9F7A8d4;
    address constant ASSEMBLER = 0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78;
    address constant DYNAMIC_FEE_MODULE = 0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed;
    address constant MEV_PROTECTION_MODULE = 0xA4f6ABd6F77928b06F075637ccBACA8f89e17386;
    address constant AUTO_REBALANCE_MODULE = 0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee;

    // Pool parameters
    uint24 constant DYNAMIC_FEE = 0x800000; // LPFeeLibrary.DYNAMIC_FEE_FLAG
    int24 constant TICK_SPACING = 60;
    uint160 constant SQRT_PRICE_1_1 = 79228162514264337593543950336; // sqrt(1) * 2^96

    // Token amounts
    uint256 constant INITIAL_SUPPLY = 1_000_000 ether;
    uint256 constant LIQUIDITY_AMOUNT = 100_000 ether;
    int256 constant SWAP_AMOUNT = -1 ether; // exactIn: swap 1 token

    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        console.log("=== Genesis V4 Swap Script ===");
        console.log("Deployer:", deployer);
        console.log("Chain ID:", block.chainid);
        console.log("PoolManager:", POOL_MANAGER);
        console.log("GenesisV4Hook:", GENESIS_HOOK);

        vm.startBroadcast(deployerKey);

        // ─── Step 1: Deploy Test Tokens ─────────────────────────────────
        TestToken tokenA = new TestToken("Genesis Test A", "GTA", INITIAL_SUPPLY);
        TestToken tokenB = new TestToken("Genesis Test B", "GTB", INITIAL_SUPPLY);
        console.log("TestTokenA:", address(tokenA));
        console.log("TestTokenB:", address(tokenB));

        // Sort tokens: currency0 < currency1
        (Currency currency0, Currency currency1) = address(tokenA) < address(tokenB)
            ? (Currency.wrap(address(tokenA)), Currency.wrap(address(tokenB)))
            : (Currency.wrap(address(tokenB)), Currency.wrap(address(tokenA)));
        console.log("Currency0:", Currency.unwrap(currency0));
        console.log("Currency1:", Currency.unwrap(currency1));

        // ─── Step 2: Build PoolKey ──────────────────────────────────────
        PoolKey memory key = PoolKey({
            currency0: currency0,
            currency1: currency1,
            fee: DYNAMIC_FEE,
            tickSpacing: TICK_SPACING,
            hooks: IHooks(GENESIS_HOOK)
        });

        // ─── Step 3: Initialize Pool ────────────────────────────────────
        console.log("Initializing pool...");
        int24 tick = IPoolManager(POOL_MANAGER).initialize(key, SQRT_PRICE_1_1);
        console.log("Pool initialized at tick:");
        console.logInt(tick);

        // ─── Step 4: Deploy helper contracts ────────────────────────────
        LiquidityHelper liqHelper = new LiquidityHelper(IPoolManager(POOL_MANAGER));
        SwapRouter swapRouter = new SwapRouter(IPoolManager(POOL_MANAGER));
        console.log("LiquidityHelper:", address(liqHelper));
        console.log("SwapRouter:", address(swapRouter));

        // ─── Step 5: Approve tokens for helpers ─────────────────────────
        TestToken(Currency.unwrap(currency0)).approve(address(liqHelper), type(uint256).max);
        TestToken(Currency.unwrap(currency1)).approve(address(liqHelper), type(uint256).max);
        TestToken(Currency.unwrap(currency0)).approve(address(swapRouter), type(uint256).max);
        TestToken(Currency.unwrap(currency1)).approve(address(swapRouter), type(uint256).max);

        // ─── Step 6: Add Liquidity ──────────────────────────────────────
        // Use wide tick range around current price (tick 0 for 1:1)
        int24 tickLower = -TICK_SPACING * 100; // -6000
        int24 tickUpper = TICK_SPACING * 100;  //  6000
        int256 liquidityDelta = 100_000e18;    // large liquidity amount

        console.log("Adding liquidity...");
        BalanceDelta liqDelta = liqHelper.addLiquidity(
            key, tickLower, tickUpper, liquidityDelta, deployer
        );
        console.log("Liquidity added. Delta amount0:");
        console.logInt(liqDelta.amount0());
        console.log("Delta amount1:");
        console.logInt(liqDelta.amount1());

        // ─── Step 7: Execute Swap ───────────────────────────────────────
        console.log("Executing swap (1 token0 -> token1)...");
        SwapParams memory swapParams = SwapParams({
            zeroForOne: true,
            amountSpecified: SWAP_AMOUNT, // negative = exactIn
            sqrtPriceLimitX96: TickMath.MIN_SQRT_PRICE + 1
        });

        BalanceDelta swapDelta = swapRouter.swap(key, swapParams);
        console.log("Swap executed! Delta amount0:");
        console.logInt(swapDelta.amount0());
        console.log("Delta amount1:");
        console.logInt(swapDelta.amount1());

        // ─── Step 8: Verify Hook State ──────────────────────────────────
        uint256 totalSwaps = GenesisHookAssembler(ASSEMBLER).totalSwapsProcessed();
        uint256 totalVolume = GenesisHookAssembler(ASSEMBLER).totalVolumeProcessed();
        console.log("=== Hook Verification ===");
        console.log("Total swaps processed:", totalSwaps);
        console.log("Total volume processed:", totalVolume);

        vm.stopBroadcast();

        console.log("=== V4 Swap Complete ===");
    }
}
