// Display an estimate without rounding a small non-zero amount to zero.
export function formatUsd(value: string | number | null | undefined): string {
  if (value == null) return '—';
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) return '—';
  return `$${amount.toFixed(12).replace(/0+$/, '').replace(/\.$/, '')}`;
}
