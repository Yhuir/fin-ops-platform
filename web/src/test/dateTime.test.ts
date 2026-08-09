import { describe, expect, it } from "vitest";

import { currentBusinessMonth, currentBusinessYear } from "../features/dateTime";

describe("business period", () => {
  it("uses the Asia/Shanghai calendar at the UTC year boundary", () => {
    const now = new Date("2025-12-31T16:30:00Z");

    expect(currentBusinessYear(now)).toBe("2026");
    expect(currentBusinessMonth(now)).toBe("2026-01");
  });
});
