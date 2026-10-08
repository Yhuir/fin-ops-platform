import { describe, expect, test } from "vitest";
import { bankTradeTimeLabel } from "../features/pendingInvoices/bankTradeTime";
import type { PendingInvoiceRow } from "../features/pendingInvoices/types";

function row(times: string[], count = times.length): PendingInvoiceRow {
  return { bankTransaction: { tradeTime: times[0] }, bankTransactions: {
    hasMultiple: count > 1, originalTransactionCount: count,
    summaries: times.map((tradeTime) => ({ tradeTime })),
  } } as PendingInvoiceRow;
}

describe("pending bank transaction times", () => {
  test("preserves date precision and uses Shanghai time for zoned input", () => {
    expect(bankTradeTimeLabel(row(["2026-10-08"]))).toBe("2026-10-08");
    expect(bankTradeTimeLabel(row(["2026-10-08T01:30:00Z"]))).toBe("2026-10-08 09:30:00");
  });
  test("orders all members and collapses identical split times", () => {
    expect(bankTradeTimeLabel(row(["2026-10-08 12:00:00", "2026-10-01 09:00:00", "2026-10-08 12:00:00"], 2)))
      .toBe("2026-10-01 09:00:00 至 2026-10-08 12:00:00");
    expect(bankTradeTimeLabel(row(["2026-10-08 12:00:00", "2026-10-08 12:00:00"])))
      .toBe("2026-10-08 12:00:00");
  });
  test("does not present partial or invalid member times as complete", () => {
    expect(bankTradeTimeLabel(row(["2026-10-08"], 2))).toBe("交易时间不完整");
    expect(bankTradeTimeLabel(row(["2026-10-08", ""]))).toBe("交易时间不完整");
    expect(bankTradeTimeLabel(row([""]))).toBe("交易时间未提供");
    expect(bankTradeTimeLabel(row(["invalid"]))).toBe("交易时间未提供");
  });
});
