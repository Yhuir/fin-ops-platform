export function formatDateTimeText(value: string | null | undefined) {
  const text = String(value ?? "").trim();
  if (!text) {
    return "-";
  }
  if (/^\d{4}-\d{2}(?:-\d{2})?$/.test(text)) {
    return text;
  }
  const compactMatch = text.match(/^(\d{4})(\d{2})(\d{2})[T\s](\d{2}:\d{2})(?::(\d{2}))?(?:\.\d+)?$/);
  if (compactMatch) {
    return `${compactMatch[1]}-${compactMatch[2]}-${compactMatch[3]} ${compactMatch[4]}:${compactMatch[5] ?? "00"}`;
  }
  const localMatch = text.match(/^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2})(?::(\d{2}))?(?:\.\d+)?$/);
  if (localMatch) {
    return `${localMatch[1]} ${localMatch[2]}:${localMatch[3] ?? "00"}`;
  }
  const zonedText = normalizeOffset(text);
  if (!/^(?:\d{4}-\d{2}-\d{2})[T\s]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(zonedText)) {
    return "—";
  }
  const date = new Date(zonedText.replace(" ", "T"));
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  const parts = new Intl.DateTimeFormat("zh-CN", {
    day: "2-digit",
    hour: "2-digit",
    hour12: false,
    minute: "2-digit",
    month: "2-digit",
    second: "2-digit",
    timeZone: BUSINESS_TIME_ZONE,
    year: "numeric",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`;
}

const BUSINESS_TIME_ZONE = "Asia/Shanghai";

function normalizeOffset(value: string) {
  return value
    .replace(/([+-])(\d):(\d{2})$/, "$10$2:$3")
    .replace(/([+-])(\d)$/, "$10$2:00")
    .replace(/([+-]\d{2})(\d{2})$/, "$1:$2")
    .replace(/([+-]\d{2})$/, "$1:00");
}

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
