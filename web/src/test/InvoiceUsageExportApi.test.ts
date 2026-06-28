import { afterEach, describe, expect, test, vi } from "vitest";

import { downloadInputInvoiceUsageExport } from "../features/inputInvoiceUsage/api";
import { downloadOutputInvoiceCollectionExport } from "../features/outputInvoiceCollections/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("invoice usage export API", () => {
  test("uses direct export unavailable copy for JSON download fallbacks", async () => {
    const request = {
      page: 1,
      pageSize: 20,
      keyword: "",
      invoiceDateFrom: "",
      invoiceDateTo: "",
      month: "",
      filters: [],
      sortField: "invoiceDate",
      sortDirection: "desc",
    } as const;
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({}), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(downloadInputInvoiceUsageExport(request)).rejects.toThrow("导出数据暂不可用，请稍后再试。");
    await expect(downloadOutputInvoiceCollectionExport(request)).rejects.toThrow("导出数据暂不可用，请稍后再试。");
  });
});
