// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title StrategyNFT - On-chain representation of proven trading strategies
/// @notice When a Genesis strategy demonstrates profitability above a threshold,
///         the Agent mints a Strategy NFT encoding the full configuration.
///         Other agents can query the NFT to replicate or license the strategy.
///
///  NFT Metadata (stored on-chain, not IPFS — fully verifiable):
///   - Module composition (which modules + order)
///   - All module parameters at time of minting
///   - Performance stats (swaps, volume, P&L)
///   - Decision journal reference (count of decisions, last decision ID)
///   - Market conditions at minting (volatility, price)
///
///  This is a minimal ERC-721 implementation (no OpenZeppelin dependency
///  to keep deployment simple on X Layer).
contract StrategyNFT {

    // ─── ERC-721 Core ────────────────────────────────────────────────────
    string public name = "Genesis Strategy";
    string public symbol = "GSTRAT";

    uint256 public totalSupply;
    mapping(uint256 => address) public ownerOf;
    mapping(address => uint256) public balanceOf;
    mapping(uint256 => address) public getApproved;
    mapping(address => mapping(address => bool)) public isApprovedForAll;

    // ─── Strategy Metadata ───────────────────────────────────────────────
    struct StrategyMeta {
        address assembler;           // GenesisHookAssembler address
        uint256 strategyId;          // ID in the assembler
        bytes32 configHash;          // Hash of all module params
        address[] modules;           // Module addresses
        bytes[] moduleParams;        // Encoded params at mint time
        uint256 totalSwaps;
        uint256 totalVolume;
        int256  pnlBps;              // P&L at mint time
        uint256 decisionCount;       // Number of AI decisions made
        uint256 mintedAt;
        uint256 runDurationSeconds;  // How long strategy ran before mint
        uint256 marketVolatility;    // Vol at mint time (from Agent)
        uint256 marketPrice;         // Price at mint time (from Agent)
    }

    mapping(uint256 => StrategyMeta) public strategyMeta;

    // Access control
    address public minter;  // GenesisHookAssembler or Agent wallet

    // ─── Events ──────────────────────────────────────────────────────────
    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);
    event StrategyMinted(
        uint256 indexed tokenId,
        address indexed assembler,
        uint256 strategyId,
        int256 pnlBps,
        uint256 totalSwaps
    );

    error OnlyMinter();
    error NotOwnerOrApproved();
    error InvalidRecipient();
    error TokenDoesNotExist();

    constructor(address _minter) {
        minter = _minter;
    }

    // ─── Minting ─────────────────────────────────────────────────────────

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
    ) external returns (uint256 tokenId) {
        if (msg.sender != minter) revert OnlyMinter();
        if (_to == address(0)) revert InvalidRecipient();

        tokenId = totalSupply++;

        ownerOf[tokenId] = _to;
        balanceOf[_to]++;

        strategyMeta[tokenId] = StrategyMeta({
            assembler: _assembler,
            strategyId: _strategyId,
            configHash: _configHash,
            modules: _modules,
            moduleParams: _moduleParams,
            totalSwaps: _totalSwaps,
            totalVolume: _totalVolume,
            pnlBps: _pnlBps,
            decisionCount: _decisionCount,
            mintedAt: block.timestamp,
            runDurationSeconds: _runDuration,
            marketVolatility: _marketVol,
            marketPrice: _marketPrice
        });

        emit Transfer(address(0), _to, tokenId);
        emit StrategyMinted(tokenId, _assembler, _strategyId, _pnlBps, _totalSwaps);
    }

    // ─── View ────────────────────────────────────────────────────────────

    function getStrategyMeta(uint256 _tokenId) external view returns (StrategyMeta memory) {
        if (ownerOf[_tokenId] == address(0)) revert TokenDoesNotExist();
        return strategyMeta[_tokenId];
    }

    // ─── Minimal ERC-721 ─────────────────────────────────────────────────

    function approve(address _to, uint256 _tokenId) external {
        address tokenOwner = ownerOf[_tokenId];
        if (msg.sender != tokenOwner && !isApprovedForAll[tokenOwner][msg.sender])
            revert NotOwnerOrApproved();
        getApproved[_tokenId] = _to;
        emit Approval(tokenOwner, _to, _tokenId);
    }

    function setApprovalForAll(address _operator, bool _approved) external {
        isApprovedForAll[msg.sender][_operator] = _approved;
        emit ApprovalForAll(msg.sender, _operator, _approved);
    }

    function transferFrom(address _from, address _to, uint256 _tokenId) external {
        if (_to == address(0)) revert InvalidRecipient();
        address tokenOwner = ownerOf[_tokenId];
        if (_from != tokenOwner) revert NotOwnerOrApproved();
        if (
            msg.sender != tokenOwner &&
            msg.sender != getApproved[_tokenId] &&
            !isApprovedForAll[tokenOwner][msg.sender]
        ) revert NotOwnerOrApproved();

        balanceOf[_from]--;
        balanceOf[_to]++;
        ownerOf[_tokenId] = _to;
        delete getApproved[_tokenId];

        emit Transfer(_from, _to, _tokenId);
    }

    // ─── On-chain Metadata ────────────────────────────────────────────────

    function tokenURI(uint256 _tokenId) external view returns (string memory) {
        if (ownerOf[_tokenId] == address(0)) revert TokenDoesNotExist();

        StrategyMeta storage m = strategyMeta[_tokenId];

        // Compute derived display values
        string memory pnlPercent = string(abi.encodePacked(
            _toSignedString(m.pnlBps / 100), "%"
        ));
        string memory runtimeHours = _toString(m.runDurationSeconds / 3600);

        bytes memory json = abi.encodePacked(
            '{"name":"Genesis Strategy #', _toString(m.strategyId),
            '","description":"AI-generated Uniswap V4 Hook strategy on X Layer",'
            '"attributes":['
            '{"trait_type":"P&L","value":"', pnlPercent, '"},'
            '{"trait_type":"Total Swaps","value":"', _toString(m.totalSwaps), '"},'
            '{"trait_type":"Volume","value":"', _toString(m.totalVolume), '"},'
        );

        json = abi.encodePacked(
            json,
            '{"trait_type":"Decisions","value":"', _toString(m.decisionCount), '"},'
            '{"trait_type":"Runtime Hours","value":"', runtimeHours, '"},'
            '{"trait_type":"Modules","value":"', _toString(m.modules.length), '"},'
            '{"trait_type":"Market Volatility","value":"', _toString(m.marketVolatility), '"}'
            ']}'
        );

        return string(abi.encodePacked(
            "data:application/json;base64,",
            _encode(json)
        ));
    }

    // ─── ERC-165 ──────────────────────────────────────────────────────────

    function supportsInterface(bytes4 interfaceId) external pure returns (bool) {
        return interfaceId == 0x80ac58cd  // ERC-721
            || interfaceId == 0x01ffc9a7; // ERC-165
    }

    // ─── Internal Helpers ─────────────────────────────────────────────────

    /// @dev Converts a uint256 to its ASCII decimal string representation.
    function _toString(uint256 value) internal pure returns (string memory) {
        if (value == 0) return "0";
        uint256 temp = value;
        uint256 digits;
        while (temp != 0) {
            digits++;
            temp /= 10;
        }
        bytes memory buffer = new bytes(digits);
        while (value != 0) {
            digits--;
            buffer[digits] = bytes1(uint8(48 + (value % 10)));
            value /= 10;
        }
        return string(buffer);
    }

    /// @dev Converts an int256 to its ASCII decimal string with sign.
    function _toSignedString(int256 value) internal pure returns (string memory) {
        if (value >= 0) {
            return _toString(uint256(value));
        }
        return string(abi.encodePacked("-", _toString(uint256(-value))));
    }

    /// @dev Base64-encodes `data` (RFC 4648, standard alphabet, with padding).
    function _encode(bytes memory data) internal pure returns (string memory) {
        if (data.length == 0) return "";

        string memory table = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        uint256 encodedLen = 4 * ((data.length + 2) / 3);
        bytes memory result = new bytes(encodedLen);

        /// @solidity memory-safe-assembly
        assembly {
            let tablePtr := add(table, 1)
            let dataPtr := data
            let endPtr := add(dataPtr, mload(data))
            let resultPtr := add(result, 32)

            for {} lt(dataPtr, endPtr) {} {
                dataPtr := add(dataPtr, 3)
                let input := mload(dataPtr)

                mstore8(resultPtr,             mload(add(tablePtr, and(shr(18, input), 0x3F))))
                mstore8(add(resultPtr, 1),     mload(add(tablePtr, and(shr(12, input), 0x3F))))
                mstore8(add(resultPtr, 2),     mload(add(tablePtr, and(shr( 6, input), 0x3F))))
                mstore8(add(resultPtr, 3),     mload(add(tablePtr, and(        input,  0x3F))))

                resultPtr := add(resultPtr, 4)
            }

            // Padding with '='
            switch mod(mload(data), 3)
            case 1 {
                mstore8(sub(resultPtr, 1), 0x3d) // '='
                mstore8(sub(resultPtr, 2), 0x3d) // '='
            }
            case 2 {
                mstore8(sub(resultPtr, 1), 0x3d) // '='
            }
        }

        return string(result);
    }
}
