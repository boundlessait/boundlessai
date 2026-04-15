import type { ProofPacket } from './types';

export type Tone = 'ok' | 'warn' | 'fail';

export function isLeaseExpired(expiresAt?: string): boolean {
  if (!expiresAt) {
    return false;
  }

  const deadline = new Date(expiresAt).getTime();
  return Number.isFinite(deadline) && deadline <= Date.now();
}

export function deriveLeaseState(
  lease: ProofPacket['lease'] | null,
  _operatorMode?: string
): { label: string; tone: Tone } {
  if (!lease) {
    return { label: 'Not Issued', tone: 'fail' };
  }

  if (lease.status === 'revoked') {
    return { label: 'Revoked', tone: 'fail' };
  }

  if (isLeaseExpired(lease.expiresAt)) {
    return { label: 'Expired', tone: 'fail' };
  }

  return { label: 'Active', tone: 'ok' };
}

export function toneForOutcome(outcome?: string): Tone {
  switch (outcome) {
    case 'approve':
      return 'ok';
    case 'resize':
    case 'human_approval':
      return 'warn';
    default:
      return 'fail';
  }
}

export function toneForExecution(status?: string): Tone {
  switch (status) {
    case 'broadcasted':
      return 'ok';
    case 'ready':
    case 'simulated':
      return 'warn';
    default:
      return 'fail';
  }
}

export function toneForTrustZone(zone?: string): Tone {
  switch (zone) {
    case 'green':
      return 'ok';
    case 'yellow':
      return 'warn';
    default:
      return 'fail';
  }
}
