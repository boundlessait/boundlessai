import { ProofPacket } from "../core/types.js";

function getUsage(packet: ProofPacket) {
  return {
    spent24hUsd: typeof packet.usage?.spent24hUsd === "number" ? packet.usage.spent24hUsd : 0,
    remainingDailyUsd: typeof packet.usage?.remainingDailyUsd === "number" ? packet.usage.remainingDailyUsd : 0,
    receiptCount24h: typeof packet.usage?.receiptCount24h === "number" ? packet.usage.receiptCount24h : 0
  };
}

export function createProofPacket(packet: ProofPacket): ProofPacket {
  return {
    ...packet,
    generatedAt: packet.generatedAt || new Date().toISOString()
  };
}

export function summarizeProofPacket(packet: ProofPacket): string {
  const usage = getUsage(packet);
  return [
    `product=${packet.product}`,
    `operator=${packet.operator.mode}`,
    `lease=${packet.lease.leaseId}`,
    `consumer=${packet.lease.consumerName}`,
    `outcome=${packet.decision.outcome}`,
    `zone=${packet.decision.trustZone}`,
    `notional=${packet.decision.finalNotionalUsd}`,
    `spent24h=${usage.spent24hUsd.toFixed(2)}`,
    `tx=${packet.execution.txHash ?? "none"}`
  ].join(" | ");
}
