import { describe, expect, test } from "vitest";

import { formatCostAmount, formatProjectCostAmount } from "../features/cost-statistics/format";

describe("cost statistics amount formatting", () => {
  test.each([
    ["1584.350000", "1584.35"],
    ["1584", "1584.00"],
    ["-12.345", "-12.35"],
    ["2,000.000000", "2000.00"],
    ["9007199254740993.125", "9007199254740993.13"],
    ["", "--"],
    ["--", "--"],
  ])("formats %s as %s", (value, expected) => {
    expect(formatCostAmount(value)).toBe(expected);
  });
});

describe("project-view grouped amounts", () => {
  test.each([
    ["3838607.01", "3,838,607.01"],
    ["999.999", "1,000.00"],
    ["-1234567.895", "-1,234,567.90"],
    ["0", "0.00"],
    ["2,000.000000", "2,000.00"],
    ["9007199254740993.125", "9,007,199,254,740,993.13"],
    [null, "--"],
    [undefined, "--"],
    ["", "--"],
    ["--", "--"],
  ])("formats %s with exact decimal rounding", (value, expected) => {
    expect(formatProjectCostAmount(value)).toBe(expected);
  });
});
