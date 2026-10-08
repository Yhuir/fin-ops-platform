import { formatDateTimeText } from "../dateTime";
import type { PendingInvoiceRow } from "./types";

/** Summaries contain all displayed relation members; split purposes share their parent's time. */
export function bankTradeTimeLabel(row: PendingInvoiceRow): string {
  const multiple = row.bankTransactions.hasMultiple && (row.bankTransactions.originalTransactionCount ?? 0) > 1;
  const members = multiple ? row.bankTransactions.summaries : [row.bankTransaction];
  if (!members.length || (multiple && members.length < row.bankTransactions.originalTransactionCount!)) return "交易时间不完整";
  const values = members.map((member) => formatDateTimeText(member.tradeTime));
  const times = values.map((text) => {
    if (!/^\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?$/.test(text)) return NaN;
    return Date.parse(`${text.length === 10 ? `${text}T00:00:00` : text.replace(" ", "T")}+08:00`);
  });
  if (times.some((time) => !Number.isFinite(time))) return multiple ? "交易时间不完整" : "交易时间未提供";
  let first = 0;
  let last = 0;
  times.forEach((time, index) => {
    if (time < times[first]) first = index;
    if (time > times[last]) last = index;
  });
  return values[first] === values[last] ? values[first] : `${values[first]} 至 ${values[last]}`;
}
