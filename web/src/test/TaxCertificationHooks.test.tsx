import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { ApiClientError } from "../features/apiClient";
import * as api from "../features/tax/api";
import { useTaxCertifications } from "../features/tax/useTaxCertifications";
import { useTaxCertifiedImport } from "../features/tax/useTaxCertifiedImport";
import type { TaxCertifiedImportPreviewResult, TaxCertificationQuery } from "../features/tax/types";
import { taxCertificationFixture } from "./taxCertificationFixture";
vi.mock("../features/tax/api");
const query: TaxCertificationQuery = { status: "all", sort_by: "issue_date", sort_direction: "desc", page: 1, page_size: 50 };
const preview: TaxCertifiedImportPreviewResult = { sessionId: "s1", importedBy: "user", fileCount: 1, status: "preview_ready", files: [{ id: "f1", fileName: "test.xlsx", month: "2026-03", recognizedCount: 1, invalidCount: 0, ignoredCount: 0, matchedInvoiceCount: 1, outsideInvoicesCount: 0, conflictCount: 1, duplicateCount: 0, rows: [{ id: "r1", uniqueKey: "key1", expectedVersion: 3, month: "2026-03", buyerTaxNo: "buyer", rowStatus: "recognized", matchStatus: "matched_invoice", dedupeStatus: "conflict", errorMessage: null, blocking: false, digitalInvoiceNo: "123", invoiceCode: null, invoiceNo: null, issueDate: null, sellerTaxNo: null, sellerName: null, taxAmount: "10.00", deductibleTaxAmount: "10.00", selectionStatus: null, invoiceStatus: null, selectionTime: null, sourceFileName: "test.xlsx", sourceRowNumber: 4 }] }], summary: { blockingCount: 0, recognizedCount: 1, invalidCount: 0, ignoredCount: 0, matchedInvoiceCount: 1, outsideInvoicesCount: 0, conflictCount: 1, duplicateCount: 0 } };
const confirmed = { status: "confirmed" as const, batchId: "b1", sessionId: "s1", importedBy: "user", fileCount: 1, months: ["2026-03"], persistedRecordCount: 1 };
beforeEach(() => { vi.resetAllMocks(); vi.mocked(api.fetchTaxCertifiedImportBatches).mockResolvedValue({ batches: [], records: [], records_total: 0, batches_total: 0, records_page: 1, batches_page: 1, page_size: 20 }); });

test("a slower obsolete query never overwrites the most recent filter", async () => {
  let resolveOld!: (value: ReturnType<typeof taxCertificationFixture>) => void;
  vi.mocked(api.fetchTaxCertifications).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; })).mockResolvedValue(taxCertificationFixture(new URLSearchParams("search=材料")));
  const { result, rerender } = renderHook(({ query }) => useTaxCertifications(query, true, 0), { initialProps: { query } });
  rerender({ query: { ...query, search: "材料" } });
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => resolveOld(taxCertificationFixture()));
  expect(result.current.result?.rows).toHaveLength(1); expect(result.current.result?.rows[0].seller_name).toBe("材料供应商");
});
test("only explicit conflict selections and their expected version are sent", async () => {
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValue(preview); vi.mocked(api.confirmTaxCertifiedImport).mockResolvedValue({ status: "queued", importJob: { importJobId: "job1", importType: "tax_certified_import", status: "queued", stage: "queued" } });
  vi.mocked(api.fetchTaxCertifiedImportJob).mockResolvedValue({ importJobId: "job1", importType: "tax_certified_import", status: "succeeded", stage: "completed" });
  vi.mocked(api.taxCertifiedImportConfirmedFromJob).mockReturnValue(confirmed);
  const changed = vi.fn(); const { result } = renderHook(() => useTaxCertifiedImport("user", changed));
  act(() => result.current.selectFiles([new File(["x"], "test.xlsx")]));
  await act(async () => result.current.recognize({ month: "", buyerTaxNo: "" }));
  act(() => result.current.setCorrections(["key1"])); await act(async () => result.current.confirm());
  expect(api.confirmTaxCertifiedImport).toHaveBeenCalledWith("s1", [{ unique_key: "key1", expected_version: 3 }]);
  expect(changed).toHaveBeenCalledWith(confirmed); expect(result.current.preview).toBeNull(); expect(result.current.completed).toBe("已导入 1 条");
});
test("a job query failure preserves its ID and retries polling without submitting twice", async () => {
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValue(preview);
  vi.mocked(api.confirmTaxCertifiedImport).mockResolvedValue({ status: "queued", importJob: { importJobId: "job1", importType: "tax_certified_import", status: "queued", stage: "queued" } });
  vi.mocked(api.fetchTaxCertifiedImportJob).mockRejectedValueOnce(new Error("网络错误")).mockResolvedValue({ importJobId: "job1", importType: "tax_certified_import", status: "succeeded", stage: "completed" });
  vi.mocked(api.taxCertifiedImportConfirmedFromJob).mockReturnValue(confirmed);
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  act(() => result.current.selectFiles([new File(["x"], "test.xlsx")])); await act(async () => result.current.recognize({ month: "", buyerTaxNo: "" }));
  act(() => result.current.setCorrections(["key1"])); await act(async () => result.current.confirm()); expect(result.current.error).toBe("网络错误"); expect(result.current.jobId).toBe("job1");
  act(() => result.current.setCorrections(["key1"])); await act(async () => result.current.confirm()); expect(api.confirmTaxCertifiedImport).toHaveBeenCalledTimes(1); expect(result.current.completed).toBe("已导入 1 条");
});
test("failed correction retains preview and a fresh recognition replaces the stale version", async () => {
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValueOnce(preview).mockResolvedValue({ ...preview, files: [{ ...preview.files[0], rows: [{ ...preview.files[0].rows[0], expectedVersion: 4 }] }] });
  vi.mocked(api.confirmTaxCertifiedImport).mockRejectedValue(new Error("认证记录已变化"));
  const changed = vi.fn(); const { result } = renderHook(() => useTaxCertifiedImport("user", changed));
  await act(async () => result.current.recognize({ month: "", buyerTaxNo: "" })); act(() => result.current.setCorrections(["key1"])); await act(async () => result.current.confirm());
  expect(result.current.error).toBe("认证记录已变化"); expect(changed).not.toHaveBeenCalled();
  await act(async () => result.current.recognize({ month: "", buyerTaxNo: "" }));
  expect(result.current.preview?.files[0].rows[0].expectedVersion).toBe(4); expect(result.current.corrections).toEqual([]);
});
test("revoke failure preserves batches, then successful retry refreshes the parent", async () => {
  vi.mocked(api.revokeTaxCertifiedImportBatch).mockRejectedValueOnce(new Error("版本冲突")).mockResolvedValue({});
  const changed = vi.fn(); const { result } = renderHook(() => useTaxCertifiedImport("user", changed));
  const batch = { id: "b1", session_id: "s1", imported_by: "user", file_count: 1, months: ["2026-03"], persisted_record_count: 1, duplicate_count: 0, status: "confirmed" as const, version: 2, created_at: "2026-03-31" };
  await act(async () => result.current.revoke(batch)); expect(result.current.error).toBe("版本冲突"); expect(changed).not.toHaveBeenCalled();
  await act(async () => result.current.revoke(batch)); expect(api.revokeTaxCertifiedImportBatch).toHaveBeenCalledWith("b1", 2); expect(changed).toHaveBeenCalledTimes(1);
});

test("unresolved corrections and canonical blocking rows cannot start a job", async () => {
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValueOnce(preview).mockResolvedValueOnce({ ...preview, summary: { ...preview.summary, blockingCount: 1 } });
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  await act(async () => result.current.recognize({ month: "", buyerTaxNo: "" }));
  expect(result.current.canConfirm).toBe(false); await act(async () => result.current.confirm());
  expect(api.confirmTaxCertifiedImport).not.toHaveBeenCalled();
  act(() => result.current.setCorrections(["key1"])); expect(result.current.canConfirm).toBe(true);
  await act(async () => result.current.recognize({ month: "", buyerTaxNo: "" })); act(() => result.current.setCorrections(["key1"]));
  expect(result.current.canConfirm).toBe(false); await act(async () => result.current.confirm()); expect(api.confirmTaxCertifiedImport).not.toHaveBeenCalled();
});
test("a definitive version conflict clears the session and retains source files for recognition", async () => {
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValue(preview);
  vi.mocked(api.confirmTaxCertifiedImport).mockRejectedValue(new ApiClientError("版本冲突", { status: 409, url: "/api/tax-offset/certified-import/confirm" }));
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  act(() => result.current.selectFiles([new File(["x"], "test.xlsx")])); await act(async () => result.current.recognize({ month: "", buyerTaxNo: "" }));
  act(() => result.current.setCorrections(["key1"])); await act(async () => result.current.confirm());
  expect(result.current.preview).toBeNull(); expect(result.current.files).toHaveLength(1); expect(result.current.error).toContain("请重新识别");
});
test("rejects xls and mixed file selections as a whole", async () => {
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  act(() => result.current.selectFiles([new File(["x"], "valid.xlsx"), new File(["x"], "old.xls")]));
  expect(result.current.files).toEqual([]); expect(result.current.error).toBe("仅支持 .xlsx");
});
