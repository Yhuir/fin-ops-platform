export function formatCostAmount(value: string | number | null | undefined): string {
  const raw = String(value ?? "").trim();
  if (!raw) {
    return "--";
  }
  const normalized = raw.replace(/,/g, "");
  const match = normalized.match(/^([+-]?)(\d+)(?:\.(\d+))?$/);
  if (!match) {
    return raw;
  }
  const sign = match[1] === "-" ? "-" : "";
  const integer = match[2].replace(/^0+(?=\d)/, "");
  const fraction = match[3] ?? "";
  let minorUnits = BigInt(integer) * 100n + BigInt(`${fraction}00`.slice(0, 2));
  if (Number(fraction[2] ?? "0") >= 5) {
    minorUnits += 1n;
  }
  const resolvedInteger = (minorUnits / 100n).toString();
  const resolvedFraction = (minorUnits % 100n).toString().padStart(2, "0");
  const displayedInteger = raw.includes(",")
    ? resolvedInteger.replace(/\B(?=(\d{3})+(?!\d))/g, ",")
    : resolvedInteger;
  return `${sign}${displayedInteger}.${resolvedFraction}`;
}
