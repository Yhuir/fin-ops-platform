import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchTaxOffsetMonth, taxCertifiedImportConfirmedFromJob } from "../features/tax/api";
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

describe("tax API mappers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("maps page-owned statistics and rejects invalid counts", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      month: "2026-05",
      output_items: [],
      input_items: [],
      default_selected_output_ids: [],
      default_selected_input_ids: [],
      summary: {
        output_tax: "0.00",
        input_tax: "0.00",
        deductible_tax: "0.00",
        result_label: "应纳税额",
        result_amount: "0.00",
      },
      statistics: {
        input_invoice_count: "800",
        output_invoice_count: 600,
        certification_record_count: 500,
        matched_certification_count: -1,
        deductible_invoice_count: 2.5,
      },
      canonical_snapshot_version: "tax-offset-v1:test",
    }), { headers: { "Content-Type": "application/json" } })));

    const result = await fetchTaxOffsetMonth("2026-05");

    expect(result.statistics).toEqual(expect.objectContaining({
      inputInvoiceCount: 800,
      outputInvoiceCount: 600,
      certificationRecordCount: 500,
      matchedCertificationCount: undefined,
      deductibleInvoiceCount: undefined,
    }));
    expect(result.canonicalSnapshotVersion).toBe("tax-offset-v1:test");
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

  test("rejects a month payload without its canonical snapshot token", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      month: "2026-05",
      output_items: [],
      input_items: [],
      default_selected_output_ids: [],
      default_selected_input_ids: [],
      summary: {
        output_tax: "0.00",
        input_tax: "0.00",
        deductible_tax: "0.00",
        result_label: "应纳税额",
        result_amount: "0.00",
      },
    }), { headers: { "Content-Type": "application/json" } })));

    await expect(fetchTaxOffsetMonth("2026-05")).rejects.toThrow(
      "Tax offset canonical snapshot version is missing.",
    );
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
