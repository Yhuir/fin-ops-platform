import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchTaxCertifications, exportTaxCertifications, taxCertifiedImportConfirmedFromJob } from "../features/tax/api";
import type { TaxCertifiedImportJob } from "../features/tax/types";

function importJob(resultPayload: Record<string, unknown>): TaxCertifiedImportJob {
  return {
    importJobId: "tax-import-job-001",
    importType: "tax_certified_import",
    status: "succeeded",
    stage: "confirmed",
    resultPayload,
  };
}

describe("tax certification API", () => {
  afterEach(() => vi.unstubAllGlobals());
  test("serializes independent filters, server sorting and pagination without changing monetary source values", async () => {
    const payload = { rows: [{ amount: null, tax_amount: "0.00" }], total: 1 };
    const fetch = vi.fn(async () => new Response(JSON.stringify(payload), { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);
    expect(await fetchTaxCertifications({ status: "certified", issue_month: "2026-03", selection_month: "2026-04", search: "销方", sort_by: "selection_time", sort_direction: "asc", page: 2, page_size: 50 })).toEqual(payload);
    const url = new URL(String(fetch.mock.calls[0][0]), "http://localhost");
    expect(Object.fromEntries(url.searchParams)).toEqual({ status: "certified", issue_month: "2026-03", selection_month: "2026-04", search: "销方", sort_by: "selection_time", sort_direction: "asc", page: "2", page_size: "50" });
  });
  test("exports captured filters and chosen columns and rejects incorrect file format", async () => {
    const fetch = vi.fn(async () => new Response("{}", { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);
    await expect(exportTaxCertifications({ status: "all", sort_by: "issue_date", sort_direction: "desc" }, ["invoice_no"])).rejects.toThrow("导出文件格式错误");
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({ filters: { status: "all", sort_by: "issue_date", sort_direction: "desc" }, fields: ["invoice_no"] });
  });
  test("maps a completed certified import job batch result", () => {
    const result = taxCertifiedImportConfirmedFromJob(
      importJob({
        batch: {
          id: "batch-001",
          session_id: "session-001",
          imported_by: "finance-user",
          file_count: 2,
          months: ["2026-03", "2026-04"],
          persisted_record_count: 18,
        },
      }),
    );

    expect(result).toEqual({
      status: "confirmed",
      batchId: "batch-001",
      sessionId: "session-001",
      importedBy: "finance-user",
      fileCount: 2,
      months: ["2026-03", "2026-04"],
      persistedRecordCount: 18,
    });
  });

  test("rejects malformed certified import job batch contracts instead of sanitizing them", () => {
    expect(
      taxCertifiedImportConfirmedFromJob(
        importJob({
          batch: {
            id: "batch-001",
            session_id: "session-001",
            imported_by: "finance-user",
            file_count: 2,
            months: ["2026-03", 202604],
            persisted_record_count: 18,
          },
        }),
      ),
    ).toBeNull();

    expect(
      taxCertifiedImportConfirmedFromJob(
        importJob({
          batch: {
            id: "batch-001",
            session_id: "session-001",
            imported_by: "finance-user",
            file_count: "2",
            months: ["2026-03"],
            persisted_record_count: 18,
          },
        }),
      ),
    ).toBeNull();
  });
});
