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

// ─── Swap Router ────────────────────────────────────────────────────────────
contract SwapRouter is IUnlockCallback {
    IPoolManager public immutable poolManager;
    CallbackData internal _callbackData;

    struct CallbackData {
        PoolKey key;
        SwapParams params;
        address sender;
    }

    constructor(IPoolManager _poolManager) {
        poolManager = _poolManager;
    }

    function swap(PoolKey memory key, SwapParams memory params) external returns (BalanceDelta delta) {
        _callbackData = CallbackData({key: key, params: params, sender: msg.sender});
        bytes memory result = poolManager.unlock(abi.encode(key, params, msg.sender));
        delta = abi.decode(result, (BalanceDelta));
    }

    function unlockCallback(bytes calldata data) external override returns (bytes memory) {
        require(msg.sender == address(poolManager), "only PM");
        (PoolKey memory key, SwapParams memory params, address sender) =
            abi.decode(data, (PoolKey, SwapParams, address));
        BalanceDelta delta = poolManager.swap(key, params, "");
        _settleDelta(key.currency0, delta.amount0(), sender);
        _settleDelta(key.currency1, delta.amount1(), sender);
        return abi.encode(delta);
    }

    function _settleDelta(Currency currency, int128 amount, address sender) internal {
        if (amount < 0) {
            uint256 amountOwed = uint256(uint128(-amount));
            // sync BEFORE transfer so settle() can detect the new tokens
            poolManager.sync(currency);
            TestToken(Currency.unwrap(currency)).transferFrom(sender, address(poolManager), amountOwed);
            poolManager.settle();
        } else if (amount > 0) {
            poolManager.take(currency, sender, uint256(uint128(amount)));
        }
    }
}

// ─── Liquidity Helper ───────────────────────────────────────────────────────
contract LiquidityHelper is IUnlockCallback {
    IPoolManager public immutable poolManager;

    constructor(IPoolManager _poolManager) {
        poolManager = _poolManager;
    }

    function addLiquidity(
        PoolKey memory key, int24 tickLower, int24 tickUpper,
        int256 liquidityDelta, address sender
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
            tickLower: tickLower, tickUpper: tickUpper,
            liquidityDelta: liquidityDelta, salt: bytes32(0)
        });
        (BalanceDelta delta,) = poolManager.modifyLiquidity(key, params, "");
        _settleDelta(key.currency0, delta.amount0(), sender);
        _settleDelta(key.currency1, delta.amount1(), sender);
        return abi.encode(delta);
    }

    function _settleDelta(Currency currency, int128 amount, address sender) internal {
        if (amount < 0) {
            uint256 amountOwed = uint256(uint128(-amount));
            // sync BEFORE transfer so settle() can detect the new tokens
            poolManager.sync(currency);
            TestToken(Currency.unwrap(currency)).transferFrom(sender, address(poolManager), amountOwed);
            poolManager.settle();
        } else if (amount > 0) {
            poolManager.take(currency, sender, uint256(uint128(amount)));
        }
    }
}

// ─── Mainnet V4 Swap Script ────────────────────────────────────────────────
/// @title V4SwapMainnet - Create V4 Pool with Genesis Hook on X Layer Mainnet
/// @notice Deploys test tokens, creates pool with GenesisV4Hook, adds liquidity, executes swaps
contract V4SwapMainnet is Script {
    // X Layer Mainnet addresses
    address constant POOL_MANAGER = 0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32;
    address constant GENESIS_HOOK = 0x174a2450b342042AAe7398545f04B199248E69c0; // CREATE2-mined, flags: 0xC0
    address constant ASSEMBLER = 0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78;

    uint24 constant DYNAMIC_FEE = 0x800000;
    int24 constant TICK_SPACING = 60;
    uint160 constant SQRT_PRICE_1_1 = 79228162514264337593543950336;

    uint256 constant INITIAL_SUPPLY = 1_000_000 ether;
    int256 constant SWAP_AMOUNT = -1 ether;

    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        console.log("=== Genesis V4 Swap - X Layer MAINNET ===");
        console.log("Deployer:", deployer);
        console.log("Chain ID:", block.chainid);
        console.log("PoolManager:", POOL_MANAGER);
        console.log("GenesisV4Hook:", GENESIS_HOOK);
        console.log("Assembler:", ASSEMBLER);

        vm.startBroadcast(deployerKey);

        // Step 1: Deploy Test Tokens
        TestToken tokenA = new TestToken("Genesis Alpha", "GALPHA", INITIAL_SUPPLY);
        TestToken tokenB = new TestToken("Genesis Beta", "GBETA", INITIAL_SUPPLY);
        console.log("TokenA (GALPHA):", address(tokenA));
        console.log("TokenB (GBETA):", address(tokenB));

        // Sort currencies
        (Currency currency0, Currency currency1) = address(tokenA) < address(tokenB)
            ? (Currency.wrap(address(tokenA)), Currency.wrap(address(tokenB)))
            : (Currency.wrap(address(tokenB)), Currency.wrap(address(tokenA)));
        console.log("Currency0:", Currency.unwrap(currency0));
        console.log("Currency1:", Currency.unwrap(currency1));

        // Step 2: Build PoolKey with Genesis Hook
        PoolKey memory key = PoolKey({
            currency0: currency0,
            currency1: currency1,
            fee: DYNAMIC_FEE,
            tickSpacing: TICK_SPACING,
            hooks: IHooks(GENESIS_HOOK)
        });

        // Step 3: Initialize Pool
        console.log("Initializing V4 pool with Genesis Hook...");
        int24 tick = IPoolManager(POOL_MANAGER).initialize(key, SQRT_PRICE_1_1);
        console.log("Pool initialized at tick:");
        console.logInt(tick);

        // Step 4: Deploy helpers
        LiquidityHelper liqHelper = new LiquidityHelper(IPoolManager(POOL_MANAGER));
        SwapRouter swapRouter = new SwapRouter(IPoolManager(POOL_MANAGER));
        console.log("LiquidityHelper:", address(liqHelper));
        console.log("SwapRouter:", address(swapRouter));

        // Step 5: Approve tokens
        TestToken(Currency.unwrap(currency0)).approve(address(liqHelper), type(uint256).max);
        TestToken(Currency.unwrap(currency1)).approve(address(liqHelper), type(uint256).max);
        TestToken(Currency.unwrap(currency0)).approve(address(swapRouter), type(uint256).max);
        TestToken(Currency.unwrap(currency1)).approve(address(swapRouter), type(uint256).max);

        // Step 6: Add Liquidity (wide range)
        int24 tickLower = -TICK_SPACING * 100; // -6000
        int24 tickUpper = TICK_SPACING * 100;  //  6000
        int256 liquidityDelta = 100_000e18;

        console.log("Adding liquidity [-6000, +6000]...");
        BalanceDelta liqDelta = liqHelper.addLiquidity(key, tickLower, tickUpper, liquidityDelta, deployer);
        console.log("Liquidity added. Amount0 delta:");
        console.logInt(liqDelta.amount0());
        console.log("Amount1 delta:");
        console.logInt(liqDelta.amount1());

        // Step 7: Execute Swap 1 (buy)
        console.log("Executing Swap 1: 1 token0 -> token1 (through Genesis Hook)...");
        SwapParams memory swapParams1 = SwapParams({
            zeroForOne: true,
            amountSpecified: SWAP_AMOUNT,
            sqrtPriceLimitX96: TickMath.MIN_SQRT_PRICE + 1
        });
        BalanceDelta delta1 = swapRouter.swap(key, swapParams1);
        console.log("Swap 1 complete. Amount0:");
        console.logInt(delta1.amount0());
        console.log("Amount1:");
        console.logInt(delta1.amount1());

        // Step 8: Execute Swap 2 (sell - opposite direction)
        console.log("Executing Swap 2: 1 token1 -> token0 (reverse direction)...");
        SwapParams memory swapParams2 = SwapParams({
            zeroForOne: false,
            amountSpecified: SWAP_AMOUNT,
            sqrtPriceLimitX96: TickMath.MAX_SQRT_PRICE - 1
        });
        BalanceDelta delta2 = swapRouter.swap(key, swapParams2);
        console.log("Swap 2 complete. Amount0:");
        console.logInt(delta2.amount0());
        console.log("Amount1:");
        console.logInt(delta2.amount1());

        // Step 9: Execute Swap 3 (larger buy)
        console.log("Executing Swap 3: 10 token0 -> token1 (large swap)...");
        SwapParams memory swapParams3 = SwapParams({
            zeroForOne: true,
            amountSpecified: -10 ether,
            sqrtPriceLimitX96: TickMath.MIN_SQRT_PRICE + 1
        });
        BalanceDelta delta3 = swapRouter.swap(key, swapParams3);
        console.log("Swap 3 complete. Amount0:");
        console.logInt(delta3.amount0());

        // Step 10: Verify Hook State
        uint256 totalSwaps = GenesisHookAssembler(ASSEMBLER).totalSwapsProcessed();
        uint256 totalVolume = GenesisHookAssembler(ASSEMBLER).totalVolumeProcessed();
        console.log("=== Hook Verification ===");
        console.log("Total swaps processed:", totalSwaps);
        console.log("Total volume processed:", totalVolume);

        vm.stopBroadcast();

        console.log("\n=== V4 MAINNET SWAP COMPLETE ===");
        console.log("Pool created with Genesis Hook on X Layer Mainnet!");
        console.log("3 swaps executed through DynamicFee + MEV Protection modules");
    }
}
