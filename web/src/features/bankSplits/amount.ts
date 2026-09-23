export function amountCents(value: string): bigint | null {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value.trim())) return null;
  const [whole, fraction = ''] = value.trim().split('.');
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
}
export function centsText(cents: bigint) {
  const sign = cents < 0n ? '-' : '';
  const value = cents < 0n ? -cents : cents;
  return `${sign}${value / 100n}.${String(value % 100n).padStart(2, '0')}`;
}
