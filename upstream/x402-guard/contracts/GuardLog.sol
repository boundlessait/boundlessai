// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract GuardLog {
    event GuardDecision(
        bytes32 indexed agentId,
        uint256 amount,
        uint8 indexed action, // 0=approve, 1=soft_alert, 2=block
        bytes32 indexed domain,
        uint256 timestamp
    );

    uint256 public totalApproved;
    uint256 public totalBlocked;
    uint256 public totalSoftAlerts;
    address public guardian;

    constructor() { guardian = msg.sender; }

    modifier onlyGuardian() {
        require(msg.sender == guardian, "Not guardian");
        _;
    }

    function logDecision(
        string calldata agentId,
        uint256 amount,
        uint8 action, // 0=approve, 1=soft_alert, 2=block
        string calldata domain
    ) external onlyGuardian {
        require(action <= 2, "Invalid action");
        if (action == 0) totalApproved++;
        else if (action == 1) totalSoftAlerts++;
        else totalBlocked++;
        emit GuardDecision(
            bytes32(bytes(agentId)),
            amount,
            action,
            bytes32(bytes(domain)),
            block.timestamp
        );
    }

    function getStats() external view returns (uint256, uint256, uint256) {
        return (totalApproved, totalSoftAlerts, totalBlocked);
    }

    // Transfer guardian role to a new address
    function transferGuardian(address newGuardian) external onlyGuardian {
        require(newGuardian != address(0), "Zero address");
        guardian = newGuardian;
    }
}
