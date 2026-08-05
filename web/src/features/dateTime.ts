export function formatDateTimeText(value: string | null | undefined) {
  const text = String(value ?? "").trim();
  if (!text) {
    return "-";
  }
  const match = text.match(/^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?(?:Z|[+-]\d{2}(?::?\d{2})?)?$/);
  if (!match) {
    return text;
  }
  return `${match[1]} ${match[2].length === 5 ? `${match[2]}:00` : match[2]}`;
}
