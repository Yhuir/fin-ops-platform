import { describe, expect, test } from "vitest";

import { formatMoney, normalizeMoneySearchQuery } from "../features/money";

describe("money display and search", () => {
  test.each([
    ["1584.350000", "1584.35"],
    ["1584", "1584.00"],
    ["-12.345", "-12.35"],
    ["2,000.000000", "2000.00"],
    ["9007199254740993.125", "9007199254740993.13"],
    ["", "0.00"],
    ["--", "--"],
  ])("formats %s as %s without grouping", (value, expected) => {
    expect(formatMoney(value)).toBe(expected);
  });

  test("normalizes only an amount-shaped search query", () => {
    expect(normalizeMoneySearchQuery(" 4,311.00 ")).toBe("4311.00");
    expect(normalizeMoneySearchQuery("云南,公司")).toBe("云南,公司");
  });
});
