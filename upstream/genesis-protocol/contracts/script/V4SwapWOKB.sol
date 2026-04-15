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
import {TickMath} from "v4-core/src/libraries/TickMath.sol";
import {GenesisHookAssembler} from "../src/GenesisHookAssembler.sol";

// ─── IWETH Interface (WOKB uses same WETH9 deposit/withdraw pattern) ────────
interface IWETH {
    function deposit() external payable;
    function withdraw(uint256 amount) external;
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

// ─── Inline Test Token ──────────────────────────────────────────────────────
contract TestTokenWOKB {
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

// ─── Swap Router for WOKB pools ────────────────────────────────────────────
contract WOKBSwapRouter is IUnlockCallback {
    IPoolManager public immutable poolManager;

    constructor(IPoolManager _poolManager) {
        poolManager = _poolManager;
    }

    function swap(PoolKey memory key, SwapParams memory params) external returns (BalanceDelta delta) {
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
            poolManager.sync(currency);
            (bool ok,) = Currency.unwrap(currency).call(
                abi.encodeWithSignature("transferFrom(address,address,uint256)", sender, address(poolManager), amountOwed)
            );
            require(ok, "transfer failed");
            poolManager.settle();
        } else if (amount > 0) {
            poolManager.take(currency, sender, uint256(uint128(amount)));
        }
    }
}

// ─── Liquidity Helper for WOKB pools ───────────────────────────────────────
contract WOKBLiquidityHelper is IUnlockCallback {
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
            poolManager.sync(currency);
            (bool ok,) = Currency.unwrap(currency).call(
                abi.encodeWithSignature("transferFrom(address,address,uint256)", sender, address(poolManager), amountOwed)
            );
            require(ok, "transfer failed");
            poolManager.settle();
        } else if (amount > 0) {
            poolManager.take(currency, sender, uint256(uint128(amount)));
        }
    }
}

// ─── Mainnet V4 WOKB Pool Script ───────────────────────────────────────────
/// @title V4SwapWOKB - Create V4 Pool with REAL WOKB on X Layer Mainnet
/// @notice Wraps native OKB into WOKB, pairs with GOKB test token through GenesisV4Hook
contract V4SwapWOKB is Script {
    // X Layer Mainnet addresses
    address constant POOL_MANAGER = 0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32;
    address constant GENESIS_HOOK = 0x174a2450b342042AAe7398545f04B199248E69c0;
    address constant ASSEMBLER   = 0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78;
    address constant WOKB        = 0xe538905cf8410324e03A5A23C1c177a474D59b2b;

    uint24  constant DYNAMIC_FEE = 0x800000;
    int24   constant TICK_SPACING = 60;
    uint160 constant SQRT_PRICE_1_1 = 79228162514264337593543950336; // 1:1 price

    uint256 constant TEST_TOKEN_SUPPLY = 1_000_000 ether;
    uint256 constant WOKB_AMOUNT = 0.01 ether; // Small wrap amount - wallet has ~0.099 OKB

    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        console.log("=== Genesis V4 - WOKB Pool on X Layer MAINNET ===");
        console.log("Deployer:", deployer);
        console.log("Chain ID:", block.chainid);
        console.log("WOKB:", WOKB);
        console.log("PoolManager:", POOL_MANAGER);
        console.log("GenesisV4Hook:", GENESIS_HOOK);
        console.log("Assembler:", ASSEMBLER);

        vm.startBroadcast(deployerKey);

        // Step 1: Wrap native OKB into WOKB
        uint256 wokbBal = IWETH(WOKB).balanceOf(deployer);
        console.log("Current WOKB balance:", wokbBal);

        if (wokbBal < WOKB_AMOUNT) {
            console.log("Wrapping native OKB into WOKB...");
            IWETH(WOKB).deposit{value: WOKB_AMOUNT}();
            wokbBal = IWETH(WOKB).balanceOf(deployer);
            console.log("New WOKB balance:", wokbBal);
        }

        // Step 2: Deploy test token GOKB (Genesis OKB Strategy Token)
        TestTokenWOKB gokb = new TestTokenWOKB("Genesis OKB Strategy Token", "GOKB", TEST_TOKEN_SUPPLY);
        console.log("GOKB deployed:", address(gokb));

        // Step 3: Sort currencies (WOKB vs GOKB) - lower address first
        (Currency currency0, Currency currency1) = address(WOKB) < address(gokb)
            ? (Currency.wrap(WOKB), Currency.wrap(address(gokb)))
            : (Currency.wrap(address(gokb)), Currency.wrap(WOKB));
        console.log("Currency0:", Currency.unwrap(currency0));
        console.log("Currency1:", Currency.unwrap(currency1));

        // Step 4: Build PoolKey with Genesis Hook
        PoolKey memory key = PoolKey({
            currency0: currency0,
            currency1: currency1,
            fee: DYNAMIC_FEE,
            tickSpacing: TICK_SPACING,
            hooks: IHooks(GENESIS_HOOK)
        });

        // Step 5: Initialize Pool
        console.log("Initializing WOKB pool with Genesis Hook...");
        int24 tick = IPoolManager(POOL_MANAGER).initialize(key, SQRT_PRICE_1_1);
        console.log("Pool initialized at tick:");
        console.logInt(tick);

        // Step 6: Deploy helpers
        WOKBLiquidityHelper liqHelper = new WOKBLiquidityHelper(IPoolManager(POOL_MANAGER));
        WOKBSwapRouter swapRouter = new WOKBSwapRouter(IPoolManager(POOL_MANAGER));
        console.log("LiquidityHelper:", address(liqHelper));
        console.log("SwapRouter:", address(swapRouter));

        // Step 7: Approve tokens for helpers
        IWETH(WOKB).approve(address(liqHelper), type(uint256).max);
        gokb.approve(address(liqHelper), type(uint256).max);
        IWETH(WOKB).approve(address(swapRouter), type(uint256).max);
        gokb.approve(address(swapRouter), type(uint256).max);

        // Step 8: Add Liquidity with real WOKB
        int24 tickLower = -TICK_SPACING * 100; // -6000
        int24 tickUpper = TICK_SPACING * 100;  //  6000
        int256 liquidityDelta = 1e15; // Tiny liquidity - conserve WOKB

        console.log("Adding WOKB/GOKB liquidity [-6000, +6000]...");
        BalanceDelta liqDelta = liqHelper.addLiquidity(key, tickLower, tickUpper, liquidityDelta, deployer);
        console.log("Liquidity added. Amount0 delta:");
        console.logInt(liqDelta.amount0());
        console.log("Amount1 delta:");
        console.logInt(liqDelta.amount1());

        // Step 9: Determine swap directions based on currency ordering
        bool wokbIsCurrency0 = Currency.unwrap(currency0) == WOKB;

        // Swap 1: GOKB -> WOKB (buy WOKB with test token)
        console.log("Executing Swap 1: GOKB -> WOKB...");
        // zeroForOne=true needs MIN limit, zeroForOne=false needs MAX limit
        bool swap1ZeroForOne = !wokbIsCurrency0;
        SwapParams memory swapParams1 = SwapParams({
            zeroForOne: swap1ZeroForOne,
            amountSpecified: -0.00001 ether, // Tiny exactIn
            sqrtPriceLimitX96: swap1ZeroForOne
                ? TickMath.MIN_SQRT_PRICE + 1
                : TickMath.MAX_SQRT_PRICE - 1
        });
        BalanceDelta delta1 = swapRouter.swap(key, swapParams1);
        console.log("Swap 1 complete. Amount0:");
        console.logInt(delta1.amount0());
        console.log("Amount1:");
        console.logInt(delta1.amount1());

        // Swap 2: WOKB -> GOKB (sell WOKB for test token)
        console.log("Executing Swap 2: WOKB -> GOKB...");
        bool swap2ZeroForOne = wokbIsCurrency0;
        SwapParams memory swapParams2 = SwapParams({
            zeroForOne: swap2ZeroForOne,
            amountSpecified: -0.000005 ether, // Even tinier exactIn
            sqrtPriceLimitX96: swap2ZeroForOne
                ? TickMath.MIN_SQRT_PRICE + 1
                : TickMath.MAX_SQRT_PRICE - 1
        });
        BalanceDelta delta2 = swapRouter.swap(key, swapParams2);
        console.log("Swap 2 complete. Amount0:");
        console.logInt(delta2.amount0());
        console.log("Amount1:");
        console.logInt(delta2.amount1());

        // Swap 3: GOKB -> WOKB again (another buy)
        console.log("Executing Swap 3: GOKB -> WOKB...");
        bool swap3ZeroForOne = !wokbIsCurrency0;
        SwapParams memory swapParams3 = SwapParams({
            zeroForOne: swap3ZeroForOne,
            amountSpecified: -0.00002 ether,
            sqrtPriceLimitX96: swap3ZeroForOne
                ? TickMath.MIN_SQRT_PRICE + 1
                : TickMath.MAX_SQRT_PRICE - 1
        });
        BalanceDelta delta3 = swapRouter.swap(key, swapParams3);
        console.log("Swap 3 complete. Amount0:");
        console.logInt(delta3.amount0());
        console.log("Amount1:");
        console.logInt(delta3.amount1());

        // Step 10: Log events via GenesisHookAssembler
        uint256 totalSwaps = GenesisHookAssembler(ASSEMBLER).totalSwapsProcessed();
        uint256 totalVolume = GenesisHookAssembler(ASSEMBLER).totalVolumeProcessed();
        console.log("=== Hook Verification ===");
        console.log("Total swaps processed:", totalSwaps);
        console.log("Total volume processed:", totalVolume);

        vm.stopBroadcast();

        console.log("");
        console.log("=== WOKB POOL CREATED SUCCESSFULLY ===");
        console.log("Pool: WOKB/GOKB with real OKB value via GenesisV4Hook");
        console.log("3 swaps executed through DynamicFee + MEV Protection modules");
    }
}
