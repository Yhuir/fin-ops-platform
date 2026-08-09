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

const BUSINESS_TIME_ZONE = "Asia/Shanghai";

function businessDatePart(date: Date, part: "year" | "month") {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: BUSINESS_TIME_ZONE,
    [part]: part === "year" ? "numeric" : "2-digit",
  }).format(date);
}

export function currentBusinessYear(now = new Date()) {
  return businessDatePart(now, "year");
}

export function currentBusinessMonth(now = new Date()) {
  return `${currentBusinessYear(now)}-${businessDatePart(now, "month")}`;
}
