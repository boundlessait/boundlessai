import { ExecutionIntent, ExecutionResult, LeaseRequest } from "../core/types.js";
import { networkLabelFromChainId } from "../../lib/chain-config.js";

export function buildExplorerUrl(baseUrl: string, txHash: string): string {
  return `${baseUrl.replace(/\/+$/, "")}/tx/${txHash}`;
}

export function createExecutionIntent(input: {
  request: LeaseRequest;
  chainId: number;
}): ExecutionIntent {
  return {
    network: networkLabelFromChainId(input.chainId),
    chainId: input.chainId,
    venueHint: input.request.venueHint,
    assetPair: input.request.assetPair,
    action: input.request.action,
    notionalUsd: input.request.notionalUsd
  };
}

export function blockedExecutionResult(input: {
  intent: ExecutionIntent;
  note: string;
}): ExecutionResult {
  return {
    status: "blocked",
    network: input.intent.network,
    chainId: input.intent.chainId,
    note: input.note
  };
}

export function simulatedExecutionResult(input: {
  intent: ExecutionIntent;
  note: string;
}): ExecutionResult {
  return {
    status: "simulated",
    network: input.intent.network,
    chainId: input.intent.chainId,
    note: input.note
  };
}
