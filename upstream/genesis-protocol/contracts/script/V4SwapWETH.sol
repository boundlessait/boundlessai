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

/// @notice Interface for WETH-like wrapper on X Layer
interface IWETH {
    function deposit() external payable;
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/// @notice Minimal ERC20 test token
contract TestTokenWETH {
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

/// @notice Swap Router for WETH pools
contract WETHSwapRouter is IUnlockCallback {
    IPoolManager public immutable poolManager;
    CallbackData internal _callbackData;

    struct CallbackData {
        PoolKey key;
        SwapParams params;
        address sender;
        bool isWETHPool;
    }

    constructor(IPoolManager _poolManager) {
        poolManager = _poolManager;
    }

    function swap(PoolKey memory key, SwapParams memory params) external returns (BalanceDelta delta) {
        _callbackData = CallbackData({key: key, params: params, sender: msg.sender, isWETHPool: true});
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
            // Use transferFrom for ERC20 tokens (including WETH)
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

/// @notice Liquidity helper for WETH pools
contract WETHLiquidityHelper is IUnlockCallback {
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

/// @title V4SwapWETH - Create V4 Pool with REAL WETH on X Layer Mainnet
/// @notice Pairs WETH (real value token) with GBETA through GenesisV4Hook
contract V4SwapWETH is Script {
    // X Layer Mainnet addresses
    address constant POOL_MANAGER = 0x360E68faCcca8cA495c1B759Fd9EEe466db9FB32;
    address constant GENESIS_HOOK = 0x174a2450b342042AAe7398545f04B199248E69c0;
    address constant WETH = 0x5A77f1443D16ee5761d310e38b62f77f726bC71c;

    uint24 constant DYNAMIC_FEE = 0x800000;
    int24 constant TICK_SPACING = 60;
    // sqrt(1e-4) * 2^96 ≈ for WETH/GBETA price ratio
    // Using 1:1 sqrt price since both are 18 decimals and test token
    uint160 constant SQRT_PRICE_1_1 = 79228162514264337593543950336;

    uint256 constant TEST_TOKEN_SUPPLY = 1_000_000 ether;
    uint256 constant WETH_AMOUNT = 0.001 ether; // Small amount - real value!

    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        console.log("=== Genesis V4 - WETH Pool on X Layer MAINNET ===");
        console.log("Deployer:", deployer);
        console.log("Chain ID:", block.chainid);
        console.log("WETH:", WETH);
        console.log("GenesisV4Hook:", GENESIS_HOOK);

        vm.startBroadcast(deployerKey);

        // Step 1: Wrap native OKB to get WETH (if WETH balance is 0)
        uint256 wethBal = IWETH(WETH).balanceOf(deployer);
        console.log("Current WETH balance:", wethBal);

        if (wethBal < WETH_AMOUNT) {
            console.log("Wrapping native token to WETH...");
            IWETH(WETH).deposit{value: WETH_AMOUNT}();
            wethBal = IWETH(WETH).balanceOf(deployer);
            console.log("New WETH balance:", wethBal);
        }

        // Step 2: Deploy test token GBETA
        TestTokenWETH gbeta = new TestTokenWETH("Genesis Beta", "GBETA", TEST_TOKEN_SUPPLY);
        console.log("GBETA deployed:", address(gbeta));

        // Step 3: Sort currencies (WETH vs GBETA)
        (Currency currency0, Currency currency1) = address(WETH) < address(gbeta)
            ? (Currency.wrap(WETH), Currency.wrap(address(gbeta)))
            : (Currency.wrap(address(gbeta)), Currency.wrap(WETH));
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
        console.log("Initializing WETH pool with Genesis Hook...");
        int24 tick = IPoolManager(POOL_MANAGER).initialize(key, SQRT_PRICE_1_1);
        console.log("Pool initialized at tick:");
        console.logInt(tick);

        // Step 6: Deploy helpers
        WETHLiquidityHelper liqHelper = new WETHLiquidityHelper(IPoolManager(POOL_MANAGER));
        WETHSwapRouter swapRouter = new WETHSwapRouter(IPoolManager(POOL_MANAGER));

        // Step 7: Approve tokens for helpers
        IWETH(WETH).approve(address(liqHelper), type(uint256).max);
        gbeta.approve(address(liqHelper), type(uint256).max);
        IWETH(WETH).approve(address(swapRouter), type(uint256).max);
        gbeta.approve(address(swapRouter), type(uint256).max);

        // Step 8: Add Liquidity with real WETH
        int24 tickLower = -TICK_SPACING * 100;
        int24 tickUpper = TICK_SPACING * 100;
        // Use smaller liquidity since we have limited WETH
        int256 liquidityDelta = 1e15; // 0.001 in liquidity units

        console.log("Adding WETH liquidity...");
        BalanceDelta liqDelta = liqHelper.addLiquidity(key, tickLower, tickUpper, liquidityDelta, deployer);
        console.log("WETH Liquidity added!");
        console.logInt(liqDelta.amount0());
        console.logInt(liqDelta.amount1());

        // Step 9: Execute swap through Genesis Hook
        console.log("Executing WETH swap through Genesis Hook...");
        // Swap a tiny amount of the test token for WETH
        bool wethIsCurrency0 = Currency.unwrap(currency0) == WETH;
        SwapParams memory swapParams = SwapParams({
            zeroForOne: !wethIsCurrency0, // Swap GBETA -> WETH
            amountSpecified: -0.0001 ether, // Tiny exactIn
            sqrtPriceLimitX96: wethIsCurrency0
                ? TickMath.MAX_SQRT_PRICE - 1
                : TickMath.MIN_SQRT_PRICE + 1
        });

        BalanceDelta swapDelta = swapRouter.swap(key, swapParams);
        console.log("WETH swap complete!");
        console.logInt(swapDelta.amount0());
        console.logInt(swapDelta.amount1());

        vm.stopBroadcast();

        console.log("");
        console.log("=== WETH POOL CREATED SUCCESSFULLY ===");
        console.log("This pool contains REAL VALUE (WETH) paired with GBETA");
        console.log("All swaps routed through GenesisV4Hook modules");
    }
}
