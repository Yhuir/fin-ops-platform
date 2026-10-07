import { describe, expect, it } from "vitest";

import { calendarMonthRange, currentBusinessMonth, currentBusinessYear, formatDateTimeText } from "../features/dateTime";

describe("business period", () => {
  it("uses the Asia/Shanghai calendar at the UTC year boundary", () => {
    const now = new Date("2025-12-31T16:30:00Z");

    expect(currentBusinessYear(now)).toBe("2026");
    expect(currentBusinessMonth(now)).toBe("2026-01");
  });

  it("renders API timestamps in Asia/Shanghai without exposing timezone suffixes", () => {
    expect(formatDateTimeText("2026-08-01T03:58:48.656000+08:00")).toBe("2026-08-01 03:58:48");
    expect(formatDateTimeText("2026-08-01T03:58:48+8:00")).toBe("2026-08-01 03:58:48");
    expect(formatDateTimeText("20260105 09:50:25")).toBe("2026-01-05 09:50:25");
    expect(formatDateTimeText("2026-07-31T19:58:48Z")).toBe("2026-08-01 03:58:48");
    expect(formatDateTimeText("2026-08-01 03:58")).toBe("2026-08-01 03:58:00");
    expect(formatDateTimeText("2026-08-01")).toBe("2026-08-01");
    expect(formatDateTimeText("not-a-date")).toBe("—");
  });
});


describe("calendarMonthRange", () => {
  it.each([["", "", ""], ["2024-02", "2024-02-01", "2024-02-29"], ["2026-02", "2026-02-01", "2026-02-28"], ["2026-12", "2026-12-01", "2026-12-31"]])("maps %s to inclusive calendar boundaries", (month, from, to) => {
    expect(calendarMonthRange(month)).toEqual({ from, to });
  });
  it.each(["2026-00", "2026-13", "2026-1", "invalid"])("rejects invalid month %s", month => {
    expect(() => calendarMonthRange(month)).toThrow("月份必须为 YYYY-MM");
  });
});
