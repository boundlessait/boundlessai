// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract TrustLeaseController {
    enum LeaseStatus {
        None,
        Active,
        Revoked,
        Expired
    }

    enum OperatorMode {
        None,
        Active,
        Review,
        Paused
    }

    enum DecisionOutcome {
        None,
        Approve,
        Resize,
        Block,
        HumanApproval
    }

    enum ExecutionStatus {
        None,
        Ready,
        Simulated,
        Broadcasted,
        Failed,
        Blocked
    }

    struct LeaseRecord {
        bool exists;
        string leaseId;
        address issuer;
        address wallet;
        string consumerName;
        string baseAsset;
        uint64 issuedAt;
        uint64 expiresAt;
        LeaseStatus status;
        uint128 perTxUsd6;
        uint128 dailyBudgetUsd6;
        uint128 spentTodayUsd6;
        uint64 spentWindowStartedAt;
        bytes32 policyHash;
        bytes32 notesHash;
    }

    struct OperatorRecord {
        bool exists;
        string operatorName;
        OperatorMode mode;
        uint64 updatedAt;
        bytes32 noteHash;
        address updater;
    }

    struct ReceiptAnchor {
        bool exists;
        string leaseId;
        string requestId;
        string consumerName;
        DecisionOutcome outcome;
        ExecutionStatus executionStatus;
        uint128 spentUsd6;
        bytes32 txHash;
        bytes32 proofHash;
        string artifactUri;
        uint64 timestamp;
    }

    address public owner;
    uint256 public totalLeasesIssued;
    uint256 public totalReceiptsAnchored;
    uint256 public totalBroadcastedReceipts;
    uint256 public totalBlockedReceipts;

    mapping(address => bool) public authorizedExecutors;
    mapping(bytes32 => LeaseRecord) private leaseRecords;
    mapping(bytes32 => OperatorRecord) private operatorRecords;
    mapping(bytes32 => ReceiptAnchor) private receiptAnchors;
    mapping(bytes32 => uint128) public consumedSpendUsd6ByRequest;
    mapping(bytes32 => bytes32) public activeLeaseKeyByConsumer;
    mapping(bytes32 => bytes32) public latestReceiptKeyByConsumer;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event LeaseIssued(bytes32 indexed leaseKey, string leaseId, bytes32 indexed consumerKey, address indexed wallet, uint64 expiresAt, uint128 perTxUsd6, uint128 dailyBudgetUsd6, bytes32 policyHash);
    event LeaseStatusChanged(bytes32 indexed leaseKey, string leaseId, uint8 status, bytes32 noteHash, uint64 changedAt);
    event OperatorModeChanged(bytes32 indexed operatorKey, string operatorName, uint8 mode, bytes32 noteHash, uint64 changedAt);
    event ReceiptAnchored(bytes32 indexed requestKey, bytes32 indexed consumerKey, string leaseId, string requestId, uint8 outcome, uint8 executionStatus, uint128 spentUsd6, bytes32 txHash, bytes32 proofHash);
    event ExecutorAuthorizationUpdated(address indexed executor, bool allowed);
    event LeaseBudgetConsumed(bytes32 indexed leaseKey, bytes32 indexed requestKey, string leaseId, string requestId, uint128 spentUsd6, uint128 remainingDailyUsd6);

    modifier onlyOwner() {
        require(msg.sender == owner, 'Only owner');
        _;
    }

    modifier onlyAuthorizedExecutor() {
        require(authorizedExecutors[msg.sender], 'Executor not authorized');
        _;
    }

    constructor(address initialOwner) {
        owner = initialOwner == address(0) ? msg.sender : initialOwner;
        emit OwnershipTransferred(address(0), owner);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), 'Zero address');
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function setExecutor(address executor, bool allowed) external onlyOwner {
        require(executor != address(0), 'Zero executor');
        authorizedExecutors[executor] = allowed;
        emit ExecutorAuthorizationUpdated(executor, allowed);
    }

    function leaseKey(string memory leaseId) public pure returns (bytes32) {
        return keccak256(bytes(leaseId));
    }

    function operatorKey(string memory operatorName) public pure returns (bytes32) {
        return keccak256(bytes(operatorName));
    }

    function consumerKey(string memory consumerName) public pure returns (bytes32) {
        return keccak256(bytes(consumerName));
    }

    function requestKey(string memory requestId) public pure returns (bytes32) {
        return keccak256(bytes(requestId));
    }

    function issueLease(
        string calldata leaseId,
        string calldata consumerName,
        address wallet,
        string calldata baseAsset,
        uint64 expiresAt,
        uint128 perTxUsd6,
        uint128 dailyBudgetUsd6,
        bytes32 policyHash,
        bytes32 notesHash
    ) external onlyOwner returns (bytes32) {
        require(bytes(leaseId).length > 0, 'leaseId required');
        require(bytes(consumerName).length > 0, 'consumer required');
        require(expiresAt > block.timestamp, 'expiry in past');
        require(perTxUsd6 > 0, 'perTx required');
        require(dailyBudgetUsd6 >= perTxUsd6, 'daily < perTx');

        bytes32 key = leaseKey(leaseId);
        LeaseRecord storage lease = leaseRecords[key];
        require(!lease.exists, 'lease exists');

        lease.exists = true;
        lease.leaseId = leaseId;
        lease.issuer = msg.sender;
        lease.wallet = wallet;
        lease.consumerName = consumerName;
        lease.baseAsset = baseAsset;
        lease.issuedAt = uint64(block.timestamp);
        lease.expiresAt = expiresAt;
        lease.status = LeaseStatus.Active;
        lease.perTxUsd6 = perTxUsd6;
        lease.dailyBudgetUsd6 = dailyBudgetUsd6;
        lease.spentTodayUsd6 = 0;
        lease.spentWindowStartedAt = uint64(block.timestamp);
        lease.policyHash = policyHash;
        lease.notesHash = notesHash;

        bytes32 cKey = consumerKey(consumerName);
        activeLeaseKeyByConsumer[cKey] = key;
        totalLeasesIssued += 1;

        emit LeaseIssued(key, leaseId, cKey, wallet, expiresAt, perTxUsd6, dailyBudgetUsd6, policyHash);
        return key;
    }

    function setLeaseStatus(string calldata leaseId, LeaseStatus status, bytes32 noteHash) external onlyOwner {
        require(status != LeaseStatus.None, 'invalid status');
        bytes32 key = leaseKey(leaseId);
        LeaseRecord storage lease = leaseRecords[key];
        require(lease.exists, 'unknown lease');

        if (status == LeaseStatus.Expired) {
            require(block.timestamp >= lease.expiresAt, 'lease not expired');
        }

        lease.status = status;
        if (noteHash != bytes32(0)) {
            lease.notesHash = noteHash;
        }

        bytes32 cKey = consumerKey(lease.consumerName);
        if (status != LeaseStatus.Active && activeLeaseKeyByConsumer[cKey] == key) {
            activeLeaseKeyByConsumer[cKey] = bytes32(0);
        }

        emit LeaseStatusChanged(key, leaseId, uint8(status), noteHash, uint64(block.timestamp));
    }

    function setOperatorMode(string calldata operatorName, OperatorMode mode, bytes32 noteHash) external onlyOwner {
        require(bytes(operatorName).length > 0, 'operator required');
        require(mode != OperatorMode.None, 'invalid mode');

        bytes32 key = operatorKey(operatorName);
        OperatorRecord storage operator = operatorRecords[key];
        operator.exists = true;
        operator.operatorName = operatorName;
        operator.mode = mode;
        operator.updatedAt = uint64(block.timestamp);
        operator.noteHash = noteHash;
        operator.updater = msg.sender;

        emit OperatorModeChanged(key, operatorName, uint8(mode), noteHash, uint64(block.timestamp));
    }

    function anchorReceipt(
        string calldata leaseId,
        string calldata requestId,
        string calldata consumerName,
        DecisionOutcome outcome,
        ExecutionStatus executionStatus,
        uint128 spentUsd6,
        bytes32 txHash,
        bytes32 proofHash,
        string calldata artifactUri
    ) external onlyOwner returns (bytes32) {
        require(bytes(leaseId).length > 0, 'lease required');
        require(bytes(requestId).length > 0, 'request required');
        require(bytes(consumerName).length > 0, 'consumer required');

        bytes32 lKey = leaseKey(leaseId);
        LeaseRecord storage lease = leaseRecords[lKey];
        require(lease.exists, 'unknown lease');

        _refreshUsageWindow(lease);

        if (executionStatus == ExecutionStatus.Broadcasted && spentUsd6 > 0) {
            bytes32 reqKey = requestKey(requestId);
            uint128 preConsumedUsd6 = consumedSpendUsd6ByRequest[reqKey];
            if (preConsumedUsd6 > 0) {
                require(spentUsd6 == preConsumedUsd6, 'spent mismatch');
            } else {
                require(spentUsd6 <= lease.perTxUsd6, 'per-tx exceeded');
                require(spentUsd6 <= _remainingDailyBudget(lease), 'daily budget exceeded');
                lease.spentTodayUsd6 += spentUsd6;
            }
            totalBroadcastedReceipts += 1;
        }

        if (outcome == DecisionOutcome.Block || executionStatus == ExecutionStatus.Blocked) {
            totalBlockedReceipts += 1;
        }

        bytes32 rKey = requestKey(requestId);
        ReceiptAnchor storage receipt = receiptAnchors[rKey];
        receipt.exists = true;
        receipt.leaseId = leaseId;
        receipt.requestId = requestId;
        receipt.consumerName = consumerName;
        receipt.outcome = outcome;
        receipt.executionStatus = executionStatus;
        receipt.spentUsd6 = spentUsd6;
        receipt.txHash = txHash;
        receipt.proofHash = proofHash;
        receipt.artifactUri = artifactUri;
        receipt.timestamp = uint64(block.timestamp);

        bytes32 cKey = consumerKey(consumerName);
        latestReceiptKeyByConsumer[cKey] = rKey;
        totalReceiptsAnchored += 1;

        emit ReceiptAnchored(rKey, cKey, leaseId, requestId, uint8(outcome), uint8(executionStatus), spentUsd6, txHash, proofHash);
        return rKey;
    }

    function enforceAndConsume(
        string calldata leaseId,
        string calldata requestId,
        uint128 requestedUsd6
    ) external onlyAuthorizedExecutor returns (uint8 resolvedStatus, uint128 remainingDailyUsd6) {
        require(bytes(requestId).length > 0, 'request required');
        require(requestedUsd6 > 0, 'requested required');

        bytes32 lKey = leaseKey(leaseId);
        LeaseRecord storage lease = leaseRecords[lKey];
        require(lease.exists, 'unknown lease');

        bytes32 rKey = requestKey(requestId);
        require(consumedSpendUsd6ByRequest[rKey] == 0, 'request consumed');

        _refreshUsageWindow(lease);

        LeaseStatus status = _resolvedLeaseStatus(lease);
        require(status == LeaseStatus.Active, 'lease inactive');
        require(requestedUsd6 <= lease.perTxUsd6, 'per-tx exceeded');

        uint128 remaining = _remainingDailyBudget(lease);
        require(requestedUsd6 <= remaining, 'daily budget exceeded');

        lease.spentTodayUsd6 += requestedUsd6;
        uint128 remainingAfter = lease.dailyBudgetUsd6 - lease.spentTodayUsd6;
        consumedSpendUsd6ByRequest[rKey] = requestedUsd6;

        emit LeaseBudgetConsumed(lKey, rKey, leaseId, requestId, requestedUsd6, remainingAfter);

        return (uint8(status), remainingAfter);
    }

    function canExecute(string calldata leaseId, uint128 requestedUsd6) external view returns (bool allowed, uint8 resolvedStatus, uint128 remainingDailyUsd6) {
        bytes32 key = leaseKey(leaseId);
        LeaseRecord storage lease = leaseRecords[key];
        if (!lease.exists) {
            return (false, uint8(LeaseStatus.None), 0);
        }

        LeaseStatus status = _resolvedLeaseStatus(lease);
        uint128 remaining = _remainingDailyBudgetView(lease);
        bool ok = status == LeaseStatus.Active && requestedUsd6 <= lease.perTxUsd6 && requestedUsd6 <= remaining;
        return (ok, uint8(status), remaining);
    }

    function getActiveLeaseByConsumer(string calldata consumerName)
        external
        view
        returns (
            bool exists,
            string memory leaseId_,
            address wallet,
            string memory consumerName_,
            string memory baseAsset,
            uint64 issuedAt,
            uint64 expiresAt,
            uint8 status,
            uint128 perTxUsd6,
            uint128 dailyBudgetUsd6,
            uint128 spentTodayUsd6,
            uint64 spentWindowStartedAt,
            uint128 remainingDailyUsd6,
            bytes32 policyHash,
            bytes32 notesHash
        )
    {
        bytes32 key = activeLeaseKeyByConsumer[consumerKey(consumerName)];
        LeaseRecord storage lease = leaseRecords[key];
        if (!lease.exists) {
            return (false, '', address(0), '', '', 0, 0, uint8(LeaseStatus.None), 0, 0, 0, 0, 0, bytes32(0), bytes32(0));
        }

        LeaseStatus resolved = _resolvedLeaseStatus(lease);
        uint128 remaining = _remainingDailyBudgetView(lease);

        return (
            true,
            lease.leaseId,
            lease.wallet,
            lease.consumerName,
            lease.baseAsset,
            lease.issuedAt,
            lease.expiresAt,
            uint8(resolved),
            lease.perTxUsd6,
            lease.dailyBudgetUsd6,
            lease.spentTodayUsd6,
            lease.spentWindowStartedAt,
            remaining,
            lease.policyHash,
            lease.notesHash
        );
    }

    function getOperator(string calldata operatorName)
        external
        view
        returns (
            bool exists,
            string memory operatorName_,
            uint8 mode,
            uint64 updatedAt,
            bytes32 noteHash,
            address updater
        )
    {
        OperatorRecord storage operator = operatorRecords[operatorKey(operatorName)];
        if (!operator.exists) {
            return (false, operatorName, uint8(OperatorMode.None), 0, bytes32(0), address(0));
        }

        return (true, operator.operatorName, uint8(operator.mode), operator.updatedAt, operator.noteHash, operator.updater);
    }

    function getLatestReceiptByConsumer(string calldata consumerName)
        external
        view
        returns (
            bool exists,
            string memory leaseId_,
            string memory requestId_,
            string memory consumerName_,
            uint8 outcome,
            uint8 executionStatus,
            uint128 spentUsd6,
            bytes32 txHash,
            bytes32 proofHash,
            string memory artifactUri,
            uint64 timestamp
        )
    {
        ReceiptAnchor storage receipt = receiptAnchors[latestReceiptKeyByConsumer[consumerKey(consumerName)]];
        if (!receipt.exists) {
            return (false, '', '', '', uint8(DecisionOutcome.None), uint8(ExecutionStatus.None), 0, bytes32(0), bytes32(0), '', 0);
        }

        return (
            true,
            receipt.leaseId,
            receipt.requestId,
            receipt.consumerName,
            uint8(receipt.outcome),
            uint8(receipt.executionStatus),
            receipt.spentUsd6,
            receipt.txHash,
            receipt.proofHash,
            receipt.artifactUri,
            receipt.timestamp
        );
    }

    function _resolvedLeaseStatus(LeaseRecord storage lease) internal view returns (LeaseStatus) {
        if (lease.status == LeaseStatus.Active && block.timestamp >= lease.expiresAt) {
            return LeaseStatus.Expired;
        }
        return lease.status;
    }

    function _refreshUsageWindow(LeaseRecord storage lease) internal {
        if (block.timestamp >= lease.spentWindowStartedAt + 1 days) {
            lease.spentWindowStartedAt = uint64(block.timestamp);
            lease.spentTodayUsd6 = 0;
        }
    }

    function _remainingDailyBudget(LeaseRecord storage lease) internal view returns (uint128) {
        if (block.timestamp >= lease.spentWindowStartedAt + 1 days) {
            return lease.dailyBudgetUsd6;
        }
        if (lease.spentTodayUsd6 >= lease.dailyBudgetUsd6) {
            return 0;
        }
        return lease.dailyBudgetUsd6 - lease.spentTodayUsd6;
    }

    function _remainingDailyBudgetView(LeaseRecord storage lease) internal view returns (uint128) {
        return _remainingDailyBudget(lease);
    }
}
