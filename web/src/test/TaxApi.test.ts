import { describe, expect, test } from "vitest";

import { taxCertifiedImportConfirmedFromJob } from "../features/tax/api";
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
