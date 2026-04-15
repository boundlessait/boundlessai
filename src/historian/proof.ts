import { ProofPacket } from "../core/types.js";

export function createProofPacket(packet: ProofPacket): ProofPacket {
  return {
    ...packet,
    generatedAt: packet.generatedAt || new Date().toISOString()
  };
}

export function summarizeProofPacket(packet: ProofPacket): string {
  return [
    `product=${packet.product}`,
    `operator=${packet.operator.mode}`,
    `lease=${packet.lease.leaseId}`,
    `consumer=${packet.lease.consumerName}`,
    `outcome=${packet.decision.outcome}`,
    `zone=${packet.decision.trustZone}`,
    `notional=${packet.decision.finalNotionalUsd}`,
    `spent24h=${packet.usage.spent24hUsd.toFixed(2)}`,
    `tx=${packet.execution.txHash ?? "none"}`
  ].join(" | ");
}
