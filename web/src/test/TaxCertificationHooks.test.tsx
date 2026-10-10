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
const preview: TaxCertifiedImportPreviewResult = { sessionId: "s1", importedBy: "user", fileCount: 1, status: "preview_ready", files: [{ id: "f1", fileName: "test.xlsx", month: "2026-03", missingMetadata: [], sourceCount: 1, newCount: 0, relinkCount: 0, recognizedCount: 1, invalidCount: 0, ignoredCount: 0, matchedInvoiceCount: 1, outsideInvoicesCount: 0, conflictCount: 1, duplicateCount: 0, rows: [{ id: "r1", uniqueKey: "key1", expectedVersion: 3, rowStatus: "recognized", matchStatus: "matched_invoice", dedupeStatus: "conflict", errorMessage: null, blocking: false, digitalInvoiceNo: "123", invoiceNo: null, sourceFileName: "test.xlsx", sourceRowNumber: 4 }] }], summary: { blockingCount: 0, sourceCount: 1, newCount: 0, relinkCount: 0, recognizedCount: 1, invalidCount: 0, ignoredCount: 0, matchedInvoiceCount: 1, outsideInvoicesCount: 0, conflictCount: 1, duplicateCount: 0 } };
const confirmed = { status: "confirmed" as const, batchId: "b1", sessionId: "s1", importedBy: "user", fileCount: 1, months: ["2026-03"], persistedRecordCount: 1, newRecordCount: 0, correctedRecordCount: 1, linkedRecordCount: 0, duplicateCount: 0, matchedRecordCount: 1, unmatchedRecordCount: 0 };
beforeEach(() => { vi.resetAllMocks(); sessionStorage.clear(); vi.mocked(api.fetchTaxCertifiedImportBatches).mockResolvedValue({ batches: [], records: [], records_total: 0, batches_total: 0, records_page: 1, batches_page: 1, page_size: 20 }); });

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
  await act(async () => result.current.selectFiles([new File(["x"], "test.xlsx")]));
  act(() => result.current.setCorrections(["key1"])); await act(async () => result.current.confirm());
  expect(api.confirmTaxCertifiedImport).toHaveBeenCalledWith("s1", [{ unique_key: "key1", expected_version: 3 }], expect.any(AbortSignal));
  expect(changed).toHaveBeenCalledWith(confirmed); expect(result.current.preview).toBeNull(); expect(result.current.completed).toBe("导入完成：新增 0 张，更正 1 张，补关联 0 张，重复跳过 0 张，待核对 0 张");
});
test("a job query failure preserves its ID and retries polling without submitting twice", async () => {
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValue(preview);
  vi.mocked(api.confirmTaxCertifiedImport).mockResolvedValue({ status: "queued", importJob: { importJobId: "job1", importType: "tax_certified_import", status: "queued", stage: "queued" } });
  vi.mocked(api.fetchTaxCertifiedImportJob).mockRejectedValueOnce(new Error("网络错误")).mockResolvedValue({ importJobId: "job1", importType: "tax_certified_import", status: "succeeded", stage: "completed" });
  vi.mocked(api.taxCertifiedImportConfirmedFromJob).mockReturnValue(confirmed);
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  await act(async () => result.current.selectFiles([new File(["x"], "test.xlsx")]));
  act(() => result.current.setCorrections(["key1"])); await act(async () => result.current.confirm()); expect(result.current.error).toBe("网络错误"); expect(result.current.jobId).toBe("job1");
  act(() => result.current.setCorrections(["key1"])); await act(async () => result.current.confirm()); expect(api.confirmTaxCertifiedImport).toHaveBeenCalledTimes(1); expect(result.current.completed).toBe("导入完成：新增 0 张，更正 1 张，补关联 0 张，重复跳过 0 张，待核对 0 张");
});
test("version rejection clears preview and a fresh analysis obtains the current version", async () => {
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValueOnce(preview).mockResolvedValue({ ...preview, files: [{ ...preview.files[0], rows: [{ ...preview.files[0].rows[0], expectedVersion: 4 }] }] });
  vi.mocked(api.confirmTaxCertifiedImport).mockRejectedValue(new ApiClientError("认证记录已变化", { status: 409, url: "/api/tax-offset/certified-import/confirm" }));
  const changed = vi.fn(); const { result } = renderHook(() => useTaxCertifiedImport("user", changed));
  await act(async () => result.current.selectFiles([new File(["x"], "test.xlsx")])); act(() => result.current.setCorrections(["key1"])); await act(async () => result.current.confirm());
  expect(result.current.error).toContain("认证记录已变化"); expect(result.current.preview).toBeNull(); expect(changed).not.toHaveBeenCalled();
  await act(async () => result.current.analyze({ month: "", buyerTaxNo: "" }));
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
  await act(async () => result.current.selectFiles([new File(["x"], "test.xlsx")]));
  expect(result.current.canConfirm).toBe(false); await act(async () => result.current.confirm());
  expect(api.confirmTaxCertifiedImport).not.toHaveBeenCalled();
  act(() => result.current.setCorrections(["key1"])); expect(result.current.canConfirm).toBe(true);
  await act(async () => result.current.analyze({ month: "", buyerTaxNo: "" })); act(() => result.current.setCorrections(["key1"]));
  expect(result.current.canConfirm).toBe(false); await act(async () => result.current.confirm()); expect(api.confirmTaxCertifiedImport).not.toHaveBeenCalled();
});
test("a definitive version conflict clears the session and retains source files for recognition", async () => {
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValue(preview);
  vi.mocked(api.confirmTaxCertifiedImport).mockRejectedValue(new ApiClientError("版本冲突", { status: 409, url: "/api/tax-offset/certified-import/confirm" }));
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  await act(async () => result.current.selectFiles([new File(["x"], "test.xlsx")]));
  act(() => result.current.setCorrections(["key1"])); await act(async () => result.current.confirm());
  expect(result.current.preview).toBeNull(); expect(result.current.files).toHaveLength(1); expect(result.current.error).toContain("请重新分析");
});
test("rejects xls and mixed file selections as a whole", async () => {
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  await act(async () => result.current.selectFiles([new File(["x"], "valid.xlsx"), new File(["x"], "old.xls")]));
  expect(result.current.files).toEqual([]); expect(result.current.error).toContain("仅支持 .xlsx");
});

test("new filters never expose a previous summary while waiting or after failure", async () => {
  vi.mocked(api.fetchTaxCertifications).mockResolvedValueOnce(taxCertificationFixture());
  const { result, rerender } = renderHook(({ query }) => useTaxCertifications(query, true, 0), { initialProps: { query } });
  await waitFor(() => expect(result.current.result).not.toBeNull());
  let reject!: (reason: Error) => void;
  vi.mocked(api.fetchTaxCertifications).mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
  rerender({ query: { ...query, issue_year: "2025" } });
  expect(result.current.result).toBeNull(); expect(result.current.loading).toBe(true);
  await act(async () => reject(new Error("查询失败")));
  expect(result.current.result).toBeNull(); expect(result.current.error).toBe("查询失败");
});

test("selecting a mixed invoice file analyzes once and history refresh cannot change its summary", async () => {
  const mixed = { ...preview, files: [{ ...preview.files[0], missingMetadata: [], rows: [] }], summary: { ...preview.summary, sourceCount: 74, recognizedCount: 25, newCount: 25, ignoredCount: 49, conflictCount: 0 } };
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValue(mixed);
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  expect(api.fetchTaxCertifiedImportBatches).not.toHaveBeenCalled();
  const file = new File(["x"], "用途确认信息.xlsx");
  await act(async () => result.current.selectFiles([file]));
  expect(api.previewTaxCertifiedImport).toHaveBeenCalledTimes(1);
  expect(api.previewTaxCertifiedImport).toHaveBeenCalledWith(expect.objectContaining({ files: [file], importedBy: "user", signal: expect.any(AbortSignal) }));
  expect(result.current.needsMetadata).toBe(false);
  expect(result.current.canConfirm).toBe(true);
  expect(result.current.preview?.summary).toMatchObject({ sourceCount: 74, recognizedCount: 25, ignoredCount: 49 });
  act(() => result.current.setHistoryOpen(true));
  await waitFor(() => expect(api.fetchTaxCertifiedImportBatches).toHaveBeenCalledTimes(1));
  await act(async () => result.current.loadBatches());
  expect(result.current.preview).toBe(mixed);
  expect(api.previewTaxCertifiedImport).toHaveBeenCalledTimes(1);
});

test("a late analysis response cannot replace a newer file or make the wrong session confirmable", async () => {
  let resolveOld!: (value: TaxCertifiedImportPreviewResult) => void;
  const newer = { ...preview, sessionId: "new-session", files: [{ ...preview.files[0], rows: [] }], summary: { ...preview.summary, conflictCount: 0, newCount: 1 } };
  vi.mocked(api.previewTaxCertifiedImport).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; })).mockResolvedValueOnce(newer);
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  let oldAnalysis!: Promise<void>;
  act(() => { oldAnalysis = result.current.selectFiles([new File(["x"], "old.xlsx")]); });
  expect(result.current.analyzing).toBe(true);
  expect(result.current.canConfirm).toBe(false);
  await act(async () => result.current.selectFiles([new File(["x"], "new.xlsx")]));
  await act(async () => { resolveOld(preview); await oldAnalysis; });
  expect(result.current.files[0].name).toBe("new.xlsx");
  expect(result.current.preview?.sessionId).toBe("new-session");
  expect(result.current.canConfirm).toBe(true);
});

test("analysis errors retain selected file and retry uses it without a second selection", async () => {
  vi.mocked(api.previewTaxCertifiedImport).mockRejectedValueOnce(new Error("解析失败")).mockResolvedValueOnce(preview);
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  await act(async () => result.current.selectFiles([new File(["x"], "test.xlsx")]));
  expect(result.current.preview).toBeNull(); expect(result.current.error).toBe("解析失败"); expect(result.current.canConfirm).toBe(false);
  await act(async () => result.current.analyze({ month: "", buyerTaxNo: "" }));
  expect(result.current.preview).toBe(preview); expect(result.current.error).toBe("");
  expect(api.previewTaxCertifiedImport).toHaveBeenCalledTimes(2);
});

test("reopening the page resumes the saved job without analyzing or submitting again", async () => {
  sessionStorage.setItem("tax-certified-import:user", JSON.stringify({ sessionId: "s1", corrections: [], jobId: "saved-job" }));
  vi.mocked(api.fetchTaxCertifiedImportJob).mockResolvedValue({ importJobId: "saved-job", importType: "tax_certified_import", status: "succeeded", stage: "completed" });
  vi.mocked(api.taxCertifiedImportConfirmedFromJob).mockReturnValue(confirmed);
  const changed = vi.fn(); const { result } = renderHook(() => useTaxCertifiedImport("user", changed));
  await waitFor(() => expect(changed).toHaveBeenCalledWith(confirmed));
  expect(api.fetchTaxCertifiedImportJob).toHaveBeenCalledWith("saved-job", expect.any(AbortSignal));
  expect(api.confirmTaxCertifiedImport).not.toHaveBeenCalled();
  expect(api.previewTaxCertifiedImport).not.toHaveBeenCalled();
  expect(result.current.completed).toContain("导入完成");
  expect(sessionStorage.getItem("tax-certified-import:user")).toBeNull();
});

test("a lost submission response retries the original session and frozen corrections after remount", async () => {
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValue(preview);
  vi.mocked(api.confirmTaxCertifiedImport).mockRejectedValueOnce(new Error("网络中断"));
  const first = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  await act(async () => first.result.current.selectFiles([new File(["x"], "test.xlsx")]));
  act(() => first.result.current.setCorrections(["key1"]));
  await act(async () => first.result.current.confirm());
  expect(first.result.current.hasSubmission).toBe(true);
  expect(JSON.parse(sessionStorage.getItem("tax-certified-import:user")!)).toEqual({ sessionId: "s1", corrections: [{ unique_key: "key1", expected_version: 3 }], jobId: null });
  first.unmount();
  vi.mocked(api.confirmTaxCertifiedImport).mockResolvedValue({ status: "queued", importJob: { importJobId: "recovered", importType: "tax_certified_import", status: "queued", stage: "queued" } });
  vi.mocked(api.fetchTaxCertifiedImportJob).mockResolvedValue({ importJobId: "recovered", importType: "tax_certified_import", status: "succeeded", stage: "completed" });
  vi.mocked(api.taxCertifiedImportConfirmedFromJob).mockReturnValue(confirmed);
  const recovered = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  await waitFor(() => expect(recovered.result.current.completed).toContain("导入完成"));
  expect(api.confirmTaxCertifiedImport).toHaveBeenCalledTimes(2);
  expect(api.confirmTaxCertifiedImport).toHaveBeenLastCalledWith("s1", [{ unique_key: "key1", expected_version: 3 }], expect.any(AbortSignal));
});

test("a canceled job clears its recovery pointer and requires fresh analysis", async () => {
  sessionStorage.setItem("tax-certified-import:user", JSON.stringify({ sessionId: "s1", corrections: [], jobId: "canceled-job" }));
  vi.mocked(api.fetchTaxCertifiedImportJob).mockResolvedValue({ importJobId: "canceled-job", importType: "tax_certified_import", status: "canceled", stage: "canceled" });
  const changed = vi.fn(); const { result } = renderHook(() => useTaxCertifiedImport("user", changed));
  await waitFor(() => expect(result.current.error).toContain("导入已取消"));
  expect(result.current.canConfirm).toBe(false); expect(result.current.hasSubmission).toBe(false);
  expect(sessionStorage.getItem("tax-certified-import:user")).toBeNull(); expect(changed).not.toHaveBeenCalled();
});

test("a success status without complete result stays queryable and never reports a false success", async () => {
  sessionStorage.setItem("tax-certified-import:user", JSON.stringify({ sessionId: "s1", corrections: [], jobId: "incomplete-job" }));
  vi.mocked(api.fetchTaxCertifiedImportJob).mockResolvedValue({ importJobId: "incomplete-job", importType: "tax_certified_import", status: "succeeded", stage: "completed" });
  vi.mocked(api.taxCertifiedImportConfirmedFromJob).mockReturnValue(null);
  const changed = vi.fn(); const { result } = renderHook(() => useTaxCertifiedImport("user", changed));
  await waitFor(() => expect(result.current.error).toContain("缺少完整结果"));
  expect(result.current.jobId).toBe("incomplete-job"); expect(result.current.canConfirm).toBe(true);
  expect(result.current.completed).toBe(""); expect(changed).not.toHaveBeenCalled(); expect(api.confirmTaxCertifiedImport).not.toHaveBeenCalled();
});

test("missing metadata blocks confirmation and its input remains available after explicit reanalysis", async () => {
  const complete = { ...preview, files: [{ ...preview.files[0], rows: [], missingMetadata: [] }], summary: { ...preview.summary, newCount: 1, conflictCount: 0 } };
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValueOnce({ ...complete, files: [{ ...complete.files[0], missingMetadata: ["month"] }] }).mockResolvedValueOnce(complete);
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  await act(async () => result.current.selectFiles([new File(["x"], "test.xlsx")]));
  expect(result.current.canConfirm).toBe(false); expect(result.current.missingMetadata).toEqual(["month"]);
  act(() => result.current.updateMetadata({ month: "2026-09", buyerTaxNo: "" }));
  expect(result.current.preview).toBeNull();
  expect(api.previewTaxCertifiedImport).toHaveBeenCalledTimes(1);
  await act(async () => result.current.analyze());
  expect(result.current.canConfirm).toBe(true);
  expect(result.current.metadataFields).toEqual(["month"]);
  expect(api.previewTaxCertifiedImport).toHaveBeenLastCalledWith(expect.objectContaining({ month: "2026-09" }));
  expect(api.previewTaxCertifiedImport).toHaveBeenCalledTimes(2);
});

test("unmount aborts file analysis and never submits a late result", async () => {
  let resolve!: (value: TaxCertifiedImportPreviewResult) => void;
  vi.mocked(api.previewTaxCertifiedImport).mockImplementation(() => new Promise(done => { resolve = done; }));
  const { result, unmount } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  let analysis!: Promise<void>;
  act(() => { analysis = result.current.selectFiles([new File(["x"], "test.xlsx")]); });
  const signal = vi.mocked(api.previewTaxCertifiedImport).mock.calls[0][0].signal!;
  unmount(); expect(signal.aborted).toBe(true);
  await act(async () => { resolve(preview); await analysis; });
  expect(api.confirmTaxCertifiedImport).not.toHaveBeenCalled();
});

test("revoking a batch reanalyzes selected files so an obsolete classification cannot be confirmed", async () => {
  const initial = { ...preview, files: [{ ...preview.files[0], rows: [] }], summary: { ...preview.summary, conflictCount: 0, duplicateCount: 1 } };
  const refreshed = { ...initial, sessionId: "after-revoke", summary: { ...initial.summary, duplicateCount: 0, newCount: 1 } };
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValueOnce(initial).mockResolvedValueOnce(refreshed);
  vi.mocked(api.revokeTaxCertifiedImportBatch).mockResolvedValue({});
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  await act(async () => result.current.selectFiles([new File(["x"], "test.xlsx")]));
  await act(async () => result.current.revoke({ id: "b1", session_id: "old", imported_by: "user", file_count: 1, months: ["2026-03"], persisted_record_count: 1, duplicate_count: 0, status: "confirmed", version: 2, created_at: "2026-03-31" }));
  expect(result.current.preview?.sessionId).toBe("after-revoke");
  expect(result.current.preview?.summary).toMatchObject({ duplicateCount: 0, newCount: 1 });
  expect(api.previewTaxCertifiedImport).toHaveBeenCalledTimes(2);
});

test("history opened during submission reloads when the job completes", async () => {
  let resolveJob!: (value: Awaited<ReturnType<typeof api.fetchTaxCertifiedImportJob>>) => void;
  vi.mocked(api.previewTaxCertifiedImport).mockResolvedValue({ ...preview, files: [{ ...preview.files[0], rows: [] }], summary: { ...preview.summary, conflictCount: 0, newCount: 1 } });
  vi.mocked(api.confirmTaxCertifiedImport).mockResolvedValue({ status: "queued", importJob: { importJobId: "job1", importType: "tax_certified_import", status: "queued", stage: "queued" } });
  vi.mocked(api.fetchTaxCertifiedImportJob).mockImplementation(() => new Promise(resolve => { resolveJob = resolve; }));
  vi.mocked(api.taxCertifiedImportConfirmedFromJob).mockReturnValue(confirmed);
  const { result } = renderHook(() => useTaxCertifiedImport("user", vi.fn()));
  await act(async () => result.current.selectFiles([new File(["x"], "test.xlsx")]));
  let submission!: Promise<void>;
  act(() => { submission = result.current.confirm(); });
  await waitFor(() => expect(api.fetchTaxCertifiedImportJob).toHaveBeenCalledTimes(1));
  act(() => result.current.setHistoryOpen(true));
  await waitFor(() => expect(api.fetchTaxCertifiedImportBatches).toHaveBeenCalledTimes(1));
  await act(async () => { resolveJob({ importJobId: "job1", importType: "tax_certified_import", status: "succeeded", stage: "completed" }); await submission; });
  expect(api.fetchTaxCertifiedImportBatches).toHaveBeenCalledTimes(2);
});

test("a job that is definitively unavailable clears its recovery pointer without reporting success", async () => {
  sessionStorage.setItem("tax-certified-import:user", JSON.stringify({ sessionId: "s1", corrections: [], jobId: "missing-job" }));
  vi.mocked(api.fetchTaxCertifiedImportJob).mockRejectedValue(new ApiClientError("任务不存在", { status: 404, url: "/api/tax-offset/certified-import/jobs/missing-job" }));
  const changed = vi.fn(); const { result } = renderHook(() => useTaxCertifiedImport("user", changed));
  await waitFor(() => expect(result.current.error).toContain("任务不存在"));
  expect(result.current.hasSubmission).toBe(false); expect(result.current.canConfirm).toBe(false);
  expect(sessionStorage.getItem("tax-certified-import:user")).toBeNull(); expect(changed).not.toHaveBeenCalled();
});
