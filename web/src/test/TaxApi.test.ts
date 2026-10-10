import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchTaxCertifications, exportTaxCertifications, taxCertifiedImportConfirmedFromJob, previewTaxCertifiedImport } from "../features/tax/api";
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
    const payload = { rows: [{ amount: null, tax_amount: "0.00" }], total: 1,
      inventory_statistics: { input_invoice_count: 3, special_invoice_count: 1, general_invoice_count: 1,
        toll_invoice_count: 1, other_invoice_count: 0, unclassified_invoice_count: 0 } };
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
  test("maps server summary and explicit missing metadata without needing successful invoice rows", async () => {
    const summary = { source_count: 74, recognized_count: 25, new_count: 20, relink_count: 2, duplicate_count: 3, invalid_count: 0, ignored_count: 49, matched_invoice_count: 22, outside_invoices_count: 3, conflict_count: 0, blocking_count: 0 };
    const fetch = vi.fn(async () => new Response(JSON.stringify({ session: { id: "s1", imported_by: "user", file_count: 1, status: "preview_ready" }, files: [{ id: "f1", file_name: "mixed.xlsx", month: "2026-09", missing_metadata: [], ...summary, rows: [] }], summary }), { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);
    const result = await previewTaxCertifiedImport({ importedBy: "user", files: [new File(["fixture"], "mixed.xlsx")] });
    expect(result.summary).toEqual({ sourceCount: 74, recognizedCount: 25, newCount: 20, relinkCount: 2, duplicateCount: 3, invalidCount: 0, ignoredCount: 49, matchedInvoiceCount: 22, outsideInvoicesCount: 3, conflictCount: 0, blockingCount: 0 });
    expect(result.files[0].missingMetadata).toEqual([]);
    expect(result.files[0].rows).toEqual([]);
  });

  test("rejects incomplete, negative or nonnumeric analysis counts and unknown missing metadata fields", async () => {
    const summary = { source_count: 1, recognized_count: 1, new_count: 1, relink_count: 0, duplicate_count: 0, invalid_count: 0, ignored_count: 0, matched_invoice_count: 1, outside_invoices_count: 0, conflict_count: 0, blocking_count: 0 };
    for (const change of [{ new_count: undefined }, { new_count: -1 }, { new_count: "1" }]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ summary: { ...summary, ...change }, files: [] }), { headers: { "Content-Type": "application/json" } })));
      await expect(previewTaxCertifiedImport({ importedBy: "user", files: [] })).rejects.toThrow("认证文件统计不完整");
    }
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ summary, files: [{ missing_metadata: ["unknown"] }] }), { headers: { "Content-Type": "application/json" } })));
    await expect(previewTaxCertifiedImport({ importedBy: "user", files: [] })).rejects.toThrow("认证文件统计不完整");
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
          new_record_count: 15, corrected_record_count: 2, linked_record_count: 1, duplicate_count: 3, matched_record_count: 16, unmatched_record_count: 2,
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
      newRecordCount: 15, correctedRecordCount: 2, linkedRecordCount: 1, duplicateCount: 3, matchedRecordCount: 16, unmatchedRecordCount: 2,
    });
  });

  test("rejects a completed job missing result counts instead of reporting zero", () => {
    const batch = { id: "batch-001", session_id: "session-001", imported_by: "user", file_count: 1,
      months: ["2026-09"], persisted_record_count: 0 };
    expect(taxCertifiedImportConfirmedFromJob(importJob({ batch }))).toBeNull();
    expect(taxCertifiedImportConfirmedFromJob(importJob({ batch: { ...batch, new_record_count: 0, corrected_record_count: 0,
      linked_record_count: 0, duplicate_count: 25, matched_record_count: 0, unmatched_record_count: 0 } })))
      .toMatchObject({ newRecordCount: 0, duplicateCount: 25, persistedRecordCount: 0 });
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
          new_record_count: 15, corrected_record_count: 2, linked_record_count: 1, duplicate_count: 3, matched_record_count: 16, unmatched_record_count: 2,
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
          new_record_count: 15, corrected_record_count: 2, linked_record_count: 1, duplicate_count: 3, matched_record_count: 16, unmatched_record_count: 2,
          },
        }),
      ),
    ).toBeNull();
  });
});
