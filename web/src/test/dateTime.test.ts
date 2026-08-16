import { describe, expect, it } from "vitest";

import { currentBusinessMonth, currentBusinessYear, formatDateTimeText } from "../features/dateTime";

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
