import { describe, expect, test } from "vitest";

import { formatCostAmount } from "../features/cost-statistics/format";

describe("cost statistics amount formatting", () => {
  test.each([
    ["1584.350000", "1584.35"],
    ["1584", "1584.00"],
    ["-12.345", "-12.35"],
    ["2,000.000000", "2,000.00"],
    ["9007199254740993.125", "9007199254740993.13"],
    ["", "--"],
    ["--", "--"],
  ])("formats %s as %s", (value, expected) => {
    expect(formatCostAmount(value)).toBe(expected);
  });
});
