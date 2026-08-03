export function formatMoney(
  value: string | number | null | undefined,
  emptyValue = "0.00",
): string {
  const raw = String(value ?? "").trim();
  if (!raw) {
    return emptyValue;
  }
  const match = raw.replace(/,/g, "").match(/^([+-]?)(\d+)(?:\.(\d+))?$/);
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
  return `${sign}${minorUnits / 100n}.${(minorUnits % 100n).toString().padStart(2, "0")}`;
}

export function normalizeMoneySearchQuery(value: string): string {
  const trimmed = value.trim();
  return /^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/.test(trimmed)
    ? trimmed.replace(/,/g, "")
    : trimmed;
}
