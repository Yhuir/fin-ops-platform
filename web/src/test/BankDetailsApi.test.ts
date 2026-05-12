import { afterEach, describe, expect, test, vi } from "vitest";

import { saveBankTransactionCategories } from "../features/bankDetails/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("bank details API", () => {
  test("reports HTML API responses as a routing problem instead of a JSON parse error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<!DOCTYPE HTML><html><body>Unsupported method</body></html>", {
        status: 501,
        headers: { "Content-Type": "text/html;charset=utf-8" },
      })),
    );

    await expect(
      saveBankTransactionCategories({
        updates: [
          {
            transactionId: "bank-detail-001",
            categoryCode: "borrow_in_company_pending_repayment",
            expectedVersion: 1,
          },
        ],
      }),
    ).rejects.toThrow("接口返回了 HTML 页面");
  });
});
