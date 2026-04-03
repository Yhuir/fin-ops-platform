import { describe, expect, test } from "vitest";

import { buildOaBankExceptionOptions } from "../features/workbench/oaBankExceptionOptions";

describe("OA-bank exception option rules", () => {
  test("single OA selection only allows missing bank flow", () => {
    const result = buildOaBankExceptionOptions({ oaCount: 1, bankCount: 0, invoiceCount: 0 });
    expect(result.mode).toBe("oa_only");
    expect(result.options.map((option) => option.code)).toEqual(["oa_missing_bank"]);
  });

  test("single bank selection allows supplement OA classifications", () => {
    const result = buildOaBankExceptionOptions({ oaCount: 0, bankCount: 1, invoiceCount: 0 });
    expect(result.mode).toBe("bank_only");
    expect(result.options.map((option) => option.code)).toEqual([
      "bank_missing_oa_fee",
      "bank_missing_oa_loan",
      "bank_missing_oa_interest",
      "bank_missing_oa_misc",
    ]);
  });

  test("one OA plus many bank rows exposes one-to-many handling", () => {
    const result = buildOaBankExceptionOptions({ oaCount: 1, bankCount: 2, invoiceCount: 0 });
    expect(result.mode).toBe("oa_bank");
    expect(result.options.map((option) => option.code)).toEqual([
      "oa_bank_amount_mismatch",
      "oa_one_to_many_bank",
    ]);
  });

  test("many OA plus one bank row exposes many-to-one handling", () => {
    const result = buildOaBankExceptionOptions({ oaCount: 2, bankCount: 1, invoiceCount: 0 });
    expect(result.mode).toBe("oa_bank");
    expect(result.options.map((option) => option.code)).toEqual([
      "oa_bank_amount_mismatch",
      "oa_many_to_one_bank",
    ]);
  });
});
