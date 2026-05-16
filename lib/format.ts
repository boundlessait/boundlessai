export function formatUsd(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

export function ratio(numerator: number, denominator: number): number {
  if (denominator <= 0) return 0;
  return Math.min(100, Math.max(0, (numerator / denominator) * 100));
}

export function shortHash(hash?: string): string {
  if (!hash || hash === 'none') return '—';
  if (hash.length < 10) return hash;
  return `${hash.slice(0, 6)}...${hash.slice(-4)}`;
}

export function titleCase(str: string): string {
  if (!str) return '';
  return str
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ');
}

export function formatTimestamp(value?: string): string {
  if (!value) return '—';

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(parsed);
}

export function sanitizeProofText(value?: string | null): string {
  if (!value) return '—';

  return value
    .replaceAll(/strategy-office/gi, 'bound agent')
    .replaceAll(/X Layer/gi, 'the network')
    .replaceAll(/leaseable/gi, 'allowed')
    .replaceAll(/trust lease/gi, 'rule')
    .replaceAll(/No material allocation drift produced a [^.]+/gi, 'No eligible governed action was produced in this round')
    .replaceAll(/No material allocation drift exceeded the minimum trade threshold for this [^.]+/gi, 'No request met the minimum threshold for this round');
}
