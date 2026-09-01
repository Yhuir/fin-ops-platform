import { afterEach, describe, expect, test, vi } from "vitest";

import {
  confirmEtcImportSession,
  confirmEtcReconciliationTask,
  createEtcReconciliationTask,
  createEtcBusinessBatch,
  createEtcBusinessBatchOaDraft,
  deleteEtcBusinessBatch,
  deleteEtcReconciliationTask,
  deleteEtcReconciliationTaskImportedInvoices,
  discardEtcImportSession,
  downloadEtcBusinessBatchInvoicePdf,
  fetchEtcBusinessBatchDetail,
  fetchEtcBusinessBatches,
  fetchEtcReconciliationTask,
  fetchEtcReconciliationTasks,
  fetchReadyEtcReconciliationTasks,
  fetchEtcInvoices,
  manualEtcBusinessBatchOaStatus,
  patchEtcReconciliationItem,
  previewEtcZipFiles,
  refreshEtcReconciliationMatches,
  reopenEtcReconciliationTask,
  revokeEtcBusinessBatchOaDraft,
  uploadEtcCreditCardStatement,
  uploadEtcSupplementEvidenceForCard,
  uploadEtcSupplementEvidences,
  uploadEtcTicketRootFiles,
  uploadEtcTicketRootTexts,
} from "../features/etc/api";
import * as etcApi from "../features/etc/api";

const originalFetch = global.fetch;
const API_IMPORT_AUDIT = {
  original_count: 4,
  unique_count: 3,
  duplicate_count: 1,
  duplicate_in_file_count: 1,
  duplicate_across_files_count: 0,
  existing_duplicate_count: 1,
  importable_count: 1,
  update_count: 0,
  merge_count: 1,
  suspected_duplicate_count: 0,
  error_count: 1,
  confirmable_count: 2,
  skipped_count: 2,
};

afterEach(() => {
  global.fetch = originalFetch;
  vi.useRealTimers();
  vi.restoreAllMocks();
  document.cookie = "Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("etc api", () => {
  test("downloads a merged ETC invoice PDF with the server filename", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      new Blob(["merged-pdf"], { type: "application/pdf" }),
      {
        status: 200,
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition": "attachment; filename=\"ETC_68.pdf\"; filename*=UTF-8''ETC%E5%8F%91%E7%A5%A8_68%E5%BC%A0.pdf",
        },
      },
    ));
    global.fetch = fetchMock as typeof fetch;

    const result = await downloadEtcBusinessBatchInvoicePdf("etc_business_batch_0001");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/business-batches/etc_business_batch_0001/invoice-pdf",
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
    expect(result.fileName).toBe("ETC发票_68张.pdf");
    expect(result.blob.type).toBe("application/pdf");
  });

  test("surfaces the structured ETC invoice PDF download error", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({
        error: {
          code: "invoice_pdf_page_count_invalid",
          message: "ETC 发票 001 的 PDF 必须恰好为 1 页。",
        },
      }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    )) as typeof fetch;

    await expect(downloadEtcBusinessBatchInvoicePdf("etc_business_batch_0001")).rejects.toMatchObject({
      code: "invoice_pdf_page_count_invalid",
      message: "ETC 发票 001 的 PDF 必须恰好为 1 页。",
    });
  });

  test("maps ETC business batches from envelope and legacy fields", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.startsWith("/api/etc/business-batches?")) {
        return new Response(
          JSON.stringify({
            ok: true,
            data: {
              counts: { unsubmitted: 0, staged: 1, submitted: 0 },
              statistics: {
                invoice_count: "10000",
                input_invoice_count: 1158,
              },
              items: [
                {
                  id: "etc_business_batch_0001",
                  task_id: "etc-recon-task-001",
                  title: "高速费三月批次",
                  status: "oa_confirmation_pending",
                  version: 7,
                  import_batch_ids: ["etc_import_batch_0004", "etc_import_batch_0005"],
                  submission_batch_id: "etc_batch_0027",
                  external_batch_id: "etc_20260519_001",
                  amountBreakdown: {
                    scope_month: "2026-05",
                    reported_amount: "1935.45",
                    oa_amount: "1935.45",
                    etc_invoice_amount: "1879.45",
                    gap_amount: "56.00",
                    gap_reason: "包含非 ETC 费用",
                  },
                  oa_draft_id: "oa-draft-001",
                  oa_draft_url: "https://oa.example.test/draft/001",
                  invoice_count: 37,
                  total_amount: "1673.30",
                  invoice_date_start: "2026-03-28",
                  invoice_date_end: "2026-04-27",
                  create_oa_draft_action: {
                    enabled: false,
                    code: "oa_confirmation_pending",
                    message: "审批草稿已创建，请先确认是否已在 OA 提交。",
                  },
                },
              ],
              pagination: { page: 1, page_size: 100, total: 1 },
            },
            error: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify({ ok: true, data: {} }), { status: 200 });
    });
    global.fetch = fetchMock as typeof fetch;

    const result = await fetchEtcBusinessBatches({ bucket: "staged", month: "2026-05", keyword: "001" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/business-batches?bucket=staged&month=2026-05&keyword=001&page=1&page_size=100",
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
    expect(result.counts).toEqual({ unsubmitted: 0, staged: 1, submitted: 0 });
    expect(result.statistics).toEqual(expect.objectContaining({
      inputInvoiceCount: 1158,
      invoiceCount: 10000,
    }));
    expect(result.items[0]).toMatchObject({
      businessBatchId: "etc_business_batch_0001",
      taskId: "etc-recon-task-001",
      title: "高速费三月批次",
      status: "oa_confirmation_pending",
      version: 7,
      importBatchIds: ["etc_import_batch_0004", "etc_import_batch_0005"],
      submissionBatchId: "etc_batch_0027",
      externalEtcBatchId: "etc_20260519_001",
      scopeMonth: "2026-05",
      oaDraftId: "oa-draft-001",
      oaDraftUrl: "https://oa.example.test/draft/001",
      invoiceSummary: { count: 37, amount: "1673.30" },
      invoiceDateStart: "2026-03-28",
      invoiceDateEnd: "2026-04-27",
      amountBreakdown: {
        reportedAmount: "1935.45",
        oaAmount: "1935.45",
        etcInvoiceAmount: "1879.45",
        gapAmount: "56.00",
        gapReason: "包含非 ETC 费用",
      },
      createOaDraftAction: expect.objectContaining({
        enabled: false,
        code: "oa_confirmation_pending",
      }),
    });
  });

  test("sends business-batch OA actions with expected version and reason", async () => {
    document.cookie = "Admin-Token=mock-cookie-token";
    const responsePayloads = [
      { businessBatch: { business_batch_id: "etc_business_batch_0001", status: "imported", version: 7 } },
      { item: { business_batch_id: "etc_business_batch_0001", status: "imported", version: 7 } },
      { detail: { business_batch_id: "etc_business_batch_0001", status: "oa_confirmation_pending", version: 8 } },
      { businessBatch: { business_batch_id: "etc_business_batch_0001", status: "not_submitted", version: 9 } },
      { businessBatch: { business_batch_id: "etc_business_batch_0001", status: "manually_marked_submitted", version: 10 } },
    ];
    const fetchMock = vi.fn().mockImplementation(async () => {
      const data = responsePayloads[Math.min(fetchMock.mock.calls.length - 1, responsePayloads.length - 1)];
      return new Response(
        JSON.stringify({
          ok: true,
          data,
          error: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    global.fetch = fetchMock as typeof fetch;

    const created = await createEtcBusinessBatch({ taskId: "etc-recon-task-001", idempotencyKey: "create-1" });
    const detail = await fetchEtcBusinessBatchDetail("etc_business_batch_0001");
    const draft = await createEtcBusinessBatchOaDraft("etc_business_batch_0001", { expectedVersion: 7, idempotencyKey: "draft-1" });
    const revoked = await revokeEtcBusinessBatchOaDraft("etc_business_batch_0001", { expectedVersion: 8, reason: "导入发票不足", idempotencyKey: "revoke-1" });
    const manual = await manualEtcBusinessBatchOaStatus("etc_business_batch_0001", {
      decision: "submitted",
      expectedVersion: 9,
      reason: "用户确认 OA 草稿已提交。",
    });
    await deleteEtcBusinessBatch("etc_business_batch_0001", { expectedVersion: 10, reason: "测试删除" });

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/etc/business-batches",
      "/api/etc/business-batches/etc_business_batch_0001",
      "/api/etc/business-batches/etc_business_batch_0001/oa-draft",
      "/api/etc/business-batches/etc_business_batch_0001/oa-draft/revoke",
      "/api/etc/business-batches/etc_business_batch_0001/manual-oa-status",
      "/api/etc/business-batches/etc_business_batch_0001",
    ]);
    expect(created).toMatchObject({ businessBatchId: "etc_business_batch_0001", status: "imported", version: 7 });
    expect(detail).toMatchObject({ businessBatchId: "etc_business_batch_0001", status: "imported", version: 7 });
    expect(draft).toMatchObject({ businessBatchId: "etc_business_batch_0001", status: "oa_confirmation_pending", version: 8 });
    expect(revoked).toMatchObject({ businessBatchId: "etc_business_batch_0001", status: "not_submitted", version: 9 });
    expect(manual).toMatchObject({ businessBatchId: "etc_business_batch_0001", status: "manually_marked_submitted", version: 10 });
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/etc/business-batches/etc_business_batch_0001/oa-draft/revoke",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ expectedVersion: 8, reason: "导入发票不足", idempotencyKey: "revoke-1" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/api/etc/business-batches/etc_business_batch_0001/manual-oa-status",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          decision: "submitted",
          expectedVersion: 9,
          reason: "用户确认 OA 草稿已提交。",
        }),
      }),
    );
    fetchMock.mock.calls.forEach(([, init]) => {
      const headers = init?.headers as Headers;
      expect(headers.get("Authorization")).toBe("Bearer mock-cookie-token");
    });
  });

  test("maps business-batch detail invoice items from backend envelope with nullable detection fields", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({
        ok: true,
        data: {
          businessBatch: {
            businessBatchId: "etc_business_batch_0001",
            taskId: "ETC-TASK-001",
            status: "imported",
            version: 3,
            invoiceSummary: { count: 1, amount: "13.07" },
            invoiceItems: [
              {
                id: "etc_invoice_0001",
                invoice_number: "ETC001",
                issue_date: "2026-02-27",
                plate_number: "云ADA0381",
                total_amount: "13.07",
                status: "unsubmitted",
                has_pdf: true,
                has_xml: true,
              },
            ],
          },
        },
        error: null,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
    global.fetch = fetchMock as typeof fetch;

    const detail = await fetchEtcBusinessBatchDetail("etc_business_batch_0001");

    expect(detail).toMatchObject({
      businessBatchId: "etc_business_batch_0001",
      status: "imported",
    });
    expect(detail.invoiceItems).toEqual([
      expect.objectContaining({
        id: "etc_invoice_0001",
        invoiceNumber: "ETC001",
        plateNumber: "云ADA0381",
        totalAmount: "13.07",
        hasPdf: true,
        hasXml: true,
      }),
    ]);
  });

  test("requires a reason for business-batch manual OA fallback", async () => {
    await expect(manualEtcBusinessBatchOaStatus("etc_business_batch_0001", {
      decision: "not_submitted",
      expectedVersion: 9,
      reason: "  ",
    })).rejects.toThrow("人工处理原因不能为空");
  });

  test("maps ETC invoice query payload and sends filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          counts: {
            unsubmitted: 2,
            submitted: 1,
          },
          items: [
            {
              id: "etc-inv-001",
              invoice_number: "ETC-2026-001",
              issue_date: "2026-02-27",
              passage_start_date: "2026-02-27",
              passage_end_date: "2026-02-27",
              plate_number: "云ADA0381",
              seller_name: "云南高速通行费",
              buyer_name: "云南溯源科技",
              amount_without_tax: "12.34",
              tax_amount: "0.73",
              total_amount: "13.07",
              status: "unsubmitted",
              has_pdf: true,
              has_xml: true,
            },
          ],
          pagination: {
            page: 1,
            page_size: 100,
            total: 1,
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    global.fetch = fetchMock as typeof fetch;

    const result = await fetchEtcInvoices({
      status: "unsubmitted",
      month: "2026-02",
      plate: "云ADA0381",
      keyword: "高速",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/invoices?status=unsubmitted&month=2026-02&plate=%E4%BA%91ADA0381&keyword=%E9%AB%98%E9%80%9F&page=1&page_size=100",
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
    expect(result.counts).toEqual({ unsubmitted: 2, submitted: 1 });
    expect(result.items[0]).toMatchObject({
      id: "etc-inv-001",
      invoiceNumber: "ETC-2026-001",
      plateNumber: "云ADA0381",
      totalAmount: "13.07",
      hasPdf: true,
      hasXml: true,
    });
  });

  test("sends Authorization header for state-changing actions", async () => {
    document.cookie = "Admin-Token=mock-cookie-token";
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url === "/api/etc/business-batches/etc_business_batch_001/oa-draft") {
        return new Response(
          JSON.stringify({
            ok: true,
            data: {
              businessBatchId: "etc_business_batch_001",
              status: "oa_confirmation_pending",
              version: 8,
              oaDraftId: "oa_draft_001",
              oaDraftUrl: "https://oa.example.test/draft/001",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    global.fetch = fetchMock as typeof fetch;

    const draftResult = await createEtcBusinessBatchOaDraft("etc_business_batch_001", {
      expectedVersion: 7,
      idempotencyKey: "draft-delete-contract-1",
    });
    await deleteEtcBusinessBatch("etc_business_batch_001", { expectedVersion: 8, reason: "测试删除" });
    await deleteEtcReconciliationTask("etc-recon-task-001", 3);
    await deleteEtcReconciliationTaskImportedInvoices("etc-recon-task-001", 4);

    expect(draftResult.oaDraftUrl).toBe("https://oa.example.test/draft/001");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/etc/business-batches/etc_business_batch_001/oa-draft",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ expectedVersion: 7, idempotencyKey: "draft-delete-contract-1" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/etc/business-batches/etc_business_batch_001",
      expect.objectContaining({
        method: "DELETE",
        credentials: "include",
        body: JSON.stringify({ expectedVersion: 8, reason: "测试删除" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/etc/reconciliation-tasks/etc-recon-task-001",
      expect.objectContaining({
        method: "DELETE",
        credentials: "include",
        body: JSON.stringify({ expectedVersion: 3 }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/etc/reconciliation-tasks/etc-recon-task-001/imported-invoices",
      expect.objectContaining({
        method: "DELETE",
        credentials: "include",
        body: JSON.stringify({ expectedVersion: 4 }),
      }),
    );
    fetchMock.mock.calls.forEach(([, init]) => {
      const headers = init?.headers as Headers;
      expect(headers.get("Authorization")).toBe("Bearer mock-cookie-token");
    });
  });

  test("reports HTML responses as deployment or proxy errors", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => (
      new Response("<html><head><title>405 Not Allowed</title></head></html>", {
        status: 405,
        headers: { "Content-Type": "text/html" },
      })
    ));
    global.fetch = fetchMock as typeof fetch;

    await expect(createEtcBusinessBatchOaDraft("etc_business_batch_001", {
      expectedVersion: 7,
      idempotencyKey: "draft-html-error-1",
    })).rejects.toThrow("ETC 接口返回了 HTML 页面");
  });

  test("prefers API error messages over raw error codes", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => (
      new Response(JSON.stringify({
        error: "reconciliation_task_has_submission_link",
        message: "已确认提交 OA 或存在不可删除的提交链路，不能删除。",
      }), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      })
    ));
    global.fetch = fetchMock as typeof fetch;

    await expect(deleteEtcReconciliationTask("etc-recon-task-001", 13)).rejects.toThrow("已确认提交 OA 或存在不可删除的提交链路，不能删除。");
  });

  test("retries alternate API entrypoint when current ETC endpoint returns HTML", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url === "/api/etc/business-batches/etc_business_batch_001/oa-draft") {
        return new Response("<html><head><title>405 Not Allowed</title></head></html>", {
          status: 405,
          headers: { "Content-Type": "text/html" },
        });
      }
      if (url === "/fin-ops-api/api/etc/business-batches/etc_business_batch_001/oa-draft") {
        return new Response(
          JSON.stringify({
            ok: true,
            data: {
              businessBatchId: "etc_business_batch_001",
              status: "oa_confirmation_pending",
              version: 8,
              oaDraftId: "oa_draft_001",
              oaDraftUrl: "https://oa.example.test/draft/001",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      throw new Error(`unexpected url ${url}`);
    });
    global.fetch = fetchMock as typeof fetch;

    const draftResult = await createEtcBusinessBatchOaDraft("etc_business_batch_001", {
      expectedVersion: 7,
      idempotencyKey: "draft-html-fallback-1",
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/etc/business-batches/etc_business_batch_001/oa-draft",
      "/fin-ops-api/api/etc/business-batches/etc_business_batch_001/oa-draft",
    ]);
    expect(draftResult.oaDraftUrl).toBe("https://oa.example.test/draft/001");
  });

  test("previews ETC zip files and maps camelCase import item fields", async () => {
    document.cookie = "Admin-Token=mock-cookie-token";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          sessionId: "etc_import_session_001",
          imported: 1,
          duplicatesSkipped: 2,
          attachmentsCompleted: 3,
          failed: 4,
          audit: API_IMPORT_AUDIT,
          importAudit: API_IMPORT_AUDIT,
          reconciliationFilter: {
            taskId: "etc_task_ready_001",
            taskVersion: 9,
            confirmedItemSetHash: "confirmed-hash",
            allowedInvoiceNumbers: [],
            blockingIssues: [
              {
                error: "missing_required_etc_invoice",
                requirementId: "REQ-1",
                requirementIds: ["REQ-1"],
                invoiceNumbers: [],
                transactionAt: "2026-07-15 21:53:48",
                amount: "147.25",
                invoiceCount: 1,
                matchedInvoiceCount: 0,
                missingInvoiceCount: 1,
                resolutionHint: "请补齐该行程对应的 ETC 发票后重新预览。",
              },
            ],
          },
          items: [
            {
              invoiceNumber: "ETC-2026-006",
              fileName: "etc-2026-03.zip",
              status: "created",
              reason: "新发票待导入",
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    global.fetch = fetchMock as typeof fetch;

    const result = await previewEtcZipFiles(
      [
        new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" }),
        new File(["zip-b"], "etc-2026-04.zip", { type: "application/zip" }),
      ],
      "etc_task_ready_001",
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/import/preview",
      expect.objectContaining({ method: "POST", credentials: "include", body: expect.any(FormData) }),
    );
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer mock-cookie-token");
    expect(((init.body as FormData).getAll("files") as File[]).map((file) => file.name)).toEqual([
      "etc-2026-03.zip",
      "etc-2026-04.zip",
    ]);
    expect((init.body as FormData).get("task_id")).toBe("etc_task_ready_001");
    expect(result).toMatchObject({
      sessionId: "etc_import_session_001",
      reconciliationFilter: {
        taskId: "etc_task_ready_001",
        taskVersion: 9,
        confirmedItemSetHash: "confirmed-hash",
        allowedInvoiceNumbers: [],
        blockingIssues: [expect.objectContaining({
          requirementId: "REQ-1",
          requirementIds: ["REQ-1"],
          invoiceNumbers: [],
          missingInvoiceCount: 1,
          resolutionHint: "请补齐该行程对应的 ETC 发票后重新预览。",
        })],
      },
      items: [
        {
          invoiceNumber: "ETC-2026-006",
          fileName: "etc-2026-03.zip",
          status: "created",
          reason: "新发票待导入",
        },
      ],
    });
  });

  test("keeps large ETC zip preview uploads alive beyond the default request timeout", async () => {
    vi.useFakeTimers();
    document.cookie = "Admin-Token=mock-cookie-token";
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
      const signal = init?.signal;
      signal?.addEventListener("abort", () => {
        reject(new DOMException("Aborted", "AbortError"));
      });
      window.setTimeout(() => {
        resolve(new Response(
          JSON.stringify({
            sessionId: "etc_import_session_001",
            summary: {
              imported: 1,
              duplicatesSkipped: 0,
              attachmentsCompleted: 0,
              failed: 0,
            },
            audit: { ...API_IMPORT_AUDIT, original_count: 1, unique_count: 1, duplicate_count: 0, duplicate_in_file_count: 0, existing_duplicate_count: 0, importable_count: 1, merge_count: 0, error_count: 0, confirmable_count: 1, skipped_count: 0 },
            importAudit: { ...API_IMPORT_AUDIT, original_count: 1, unique_count: 1, duplicate_count: 0, duplicate_in_file_count: 0, existing_duplicate_count: 0, importable_count: 1, merge_count: 0, error_count: 0, confirmable_count: 1, skipped_count: 0 },
            items: [
              {
                invoiceNumber: "ETC-2026-006",
                fileName: "large-etc.zip",
                status: "created",
                reason: "新发票待导入",
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ));
      }, 61_000);
    }));
    global.fetch = fetchMock as typeof fetch;

    const pendingPreview = previewEtcZipFiles(
      [new File(["zip-a"], "large-etc.zip", { type: "application/zip" })],
      "etc_task_ready_001",
    );
    const settled = vi.fn();
    pendingPreview.then(settled, settled);

    await vi.advanceTimersByTimeAsync(60_000);
    expect(settled).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1_000);
    await expect(pendingPreview).resolves.toMatchObject({
      sessionId: "etc_import_session_001",
      items: [{ invoiceNumber: "ETC-2026-006", fileName: "large-etc.zip" }],
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/import/preview",
      expect.objectContaining({ method: "POST", credentials: "include", body: expect.any(FormData) }),
    );
  });

  test("discards an ETC import preview with Authorization header", async () => {
    document.cookie = "Admin-Token=mock-cookie-token";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ sessionId: "etc_import_session_001", status: "reverted" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    global.fetch = fetchMock as typeof fetch;

    await discardEtcImportSession("etc_import_session_001");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/import/discard",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ sessionId: "etc_import_session_001" }),
      }),
    );
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer mock-cookie-token");
    expect((init.headers as Headers).get("Content-Type")).toBe("application/json");
  });

  test("confirms ETC import session and maps background job response", async () => {
    document.cookie = "Admin-Token=mock-cookie-token";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          job: {
            job_id: "job_etc_001",
            type: "etc_invoice_import",
            label: "导入 ETC发票",
            short_label: "正在导入 ETC发票 0/31",
            status: "queued",
            phase: "queued",
            current: 0,
            total: 31,
            percent: 0,
            message: "ETC发票导入任务已创建。",
            result_summary: {},
            error: null,
            created_at: "2026-05-03T10:00:00+00:00",
            updated_at: "2026-05-03T10:00:00+00:00",
            finished_at: null,
          },
        }),
        { status: 202, headers: { "Content-Type": "application/json" } },
      ),
    );
    global.fetch = fetchMock as typeof fetch;

    const result = await confirmEtcImportSession("etc_import_session_001", "etc_task_ready_001");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/import/confirm",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ sessionId: "etc_import_session_001", taskId: "etc_task_ready_001" }),
      }),
    );
    expect(result.job).toMatchObject({
      jobId: "job_etc_001",
      type: "etc_invoice_import",
      shortLabel: "正在导入 ETC发票 0/31",
      status: "queued",
      current: 0,
      total: 31,
    });
  });

  test("maps reconciliation task lifecycle endpoints and multipart uploads", async () => {
    const taskPayload = {
      taskId: "etc-recon-task-001",
      status: "reviewing",
      version: 3,
      title: "2026-02 ETC",
      periodStart: "2026-02-27",
      periodEnd: "2026-02-28",
      statementPeriodStart: "2026-02-01",
      statementPeriodEnd: "2026-02-29",
      oaTotalAmount: "120.00",
      etcInvoiceAmount: "90.00",
      supplementAmount: "30.00",
      etcInvoiceCount: 2,
      supplementCount: 1,
      canConfirm: true,
      vehiclePlates: ["云ADA0381"],
      creditCardItems: [
        {
          item_id: "card-item-001",
          transaction_date: "2026-02-27",
          posting_date: "2026-02-28",
          description: "财付通-微信支付-贵州黔通智联",
          settlement_amount: "30.00",
          is_etc_candidate: true,
          recommendation_status: "suggested_match",
          manual_resolution: "included_etc",
        },
      ],
      ticketRootItems: [
        {
          item_id: "ticket-item-001",
          ticket_file_id: "file-ticket-ok",
          vehicle_plate: "云ADA0381",
          transaction_at: "2026-02-27T10:00:00",
          amount: "30.00",
          entry_station: "昆明东",
          exit_station: "玉溪北",
          invoice_count: 1,
          recommendation_status: "matched",
        },
      ],
      supplementEvidences: [
        {
          evidence_id: "supplement-001",
          source_name: "parking.pdf",
          evidence_kind: "non_etc_invoice",
          amount: "30.00",
          tags: ["ETC补充凭证"],
        },
      ],
      sourceFiles: [
        {
          file_id: "file-ticket-ok",
          source_kind: "ticket_root",
          original_name: "票根网-成功.pdf",
          has_blocking_issue: false,
        },
        {
          fileId: "file-ticket-bad",
          sourceKind: "ticket_root",
          originalName: "票根网-失败.pdf",
          hasBlockingIssue: true,
        },
      ],
      parseIssues: [
        {
          issue_id: "parse-issue-001",
          file_id: "file-ticket-bad",
          source_kind: "ticket_root",
          original_name: "票根网-失败.pdf",
          severity: "blocking",
          message: "票根网缺少车牌号",
          source_page: 2,
          source_line: 9,
          extraction_method: "ocr",
          field_name: "vehicle_plate",
        },
      ],
    };
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url === "/api/etc/reconciliation-tasks" && init?.method === "GET") {
        return new Response(JSON.stringify({ tasks: [taskPayload] }), { status: 200 });
      }
      if (url === "/api/etc/reconciliation-tasks" && init?.method === "POST") {
        return new Response(JSON.stringify({ ...taskPayload, taskId: "etc-recon-task-002", version: 1 }), { status: 201 });
      }
      if (url === "/api/etc/reconciliation-tasks/etc-recon-task-001") {
        return new Response(JSON.stringify(taskPayload), { status: 200 });
      }
      if (url === "/api/etc/reconciliation-tasks/etc-recon-task-001/source-files/file-ticket-bad") {
        return new Response(JSON.stringify({ ...taskPayload, version: 4, sourceFiles: [taskPayload.sourceFiles[0]], parseIssues: [] }), { status: 200 });
      }
      if (url === "/api/etc/reconciliation-tasks/etc-recon-task-001/imported-invoices") {
        return new Response(JSON.stringify({ ...taskPayload, version: 4, status: "ready_for_import", etcBatchId: "", importBatchId: "" }), { status: 200 });
      }
      if (url === "/api/etc/reconciliation-tasks/etc-recon-task-001/refresh-matches") {
        return new Response(
          JSON.stringify({
            ...taskPayload,
            version: 4,
            ticketRootItems: [
              {
                ...taskPayload.ticketRootItems[0],
                linked_credit_card_item_ids: ["card-item-001"],
                recommendation_status: "suggested_match",
              },
            ],
          }),
          { status: 200 },
        );
      }
      if (
        url === "/api/etc/reconciliation-tasks/etc-recon-task-001/credit-card-statement"
        || url === "/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-files"
        || url === "/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-texts"
        || url === "/api/etc/reconciliation-tasks/etc-recon-task-001/supplement-evidences"
        || url === "/api/etc/reconciliation-tasks/etc-recon-task-001/supplement-evidences/card-item-001"
        || url === "/api/etc/reconciliation-tasks/etc-recon-task-001/items/card-item-001"
        || url === "/api/etc/reconciliation-tasks/etc-recon-task-001/confirm"
        || url === "/api/etc/reconciliation-tasks/etc-recon-task-001/reopen"
      ) {
        return new Response(JSON.stringify({ ...taskPayload, version: 4 }), { status: 200 });
      }
      throw new Error(`unexpected url ${url}`);
    });
    global.fetch = fetchMock as typeof fetch;

    expect((await fetchEtcReconciliationTasks()).items[0]).toMatchObject({
      taskId: "etc-recon-task-001",
      version: 3,
      canConfirm: true,
      creditCardItems: [{ itemId: "card-item-001", manualResolution: "included_etc" }],
      ticketRootItems: [{ itemId: "ticket-item-001", sourceFileId: "file-ticket-ok", vehiclePlate: "云ADA0381" }],
      supplementEvidences: [{ evidenceId: "supplement-001", tags: ["ETC补充凭证"] }],
      sourceFiles: [
        { fileId: "file-ticket-ok", sourceKind: "ticket_root", originalName: "票根网-成功.pdf", hasBlockingIssue: false },
        { fileId: "file-ticket-bad", sourceKind: "ticket_root", originalName: "票根网-失败.pdf", hasBlockingIssue: true },
      ],
      parseIssues: [
        {
          issueId: "parse-issue-001",
          fileId: "file-ticket-bad",
          sourceKind: "ticket_root",
          originalName: "票根网-失败.pdf",
          sourcePage: 2,
          sourceLine: 9,
          extractionMethod: "ocr",
          fieldName: "vehicle_plate",
          message: "票根网缺少车牌号",
        },
      ],
    });
    expect((await createEtcReconciliationTask({ title: "2026-02 ETC" })).taskId).toBe("etc-recon-task-002");
    expect((await fetchEtcReconciliationTask("etc-recon-task-001")).taskId).toBe("etc-recon-task-001");
    expect(await refreshEtcReconciliationMatches("etc-recon-task-001")).toMatchObject({
      taskId: "etc-recon-task-001",
      version: 4,
      ticketRootItems: [{ itemId: "ticket-item-001", linkedCreditCardItemIds: ["card-item-001"] }],
    });

    const deletedFileTask = await (etcApi as Record<string, (...args: unknown[]) => Promise<unknown>>).deleteEtcReconciliationSourceFile(
      "etc-recon-task-001",
      "file-ticket-bad",
      3,
    );
    expect(deletedFileTask).toMatchObject({
      taskId: "etc-recon-task-001",
      version: 4,
      sourceFiles: [{ fileId: "file-ticket-ok" }],
      parseIssues: [],
    });
    await expect(deleteEtcReconciliationTaskImportedInvoices("etc-recon-task-001", 3)).resolves.toMatchObject({
      taskId: "etc-recon-task-001",
      version: 4,
      status: "ready_for_import",
      etcBatchId: "",
      importBatchId: "",
    });
    await uploadEtcCreditCardStatement("etc-recon-task-001", new File(["statement"], "statement.pdf"), 3);
    await uploadEtcTicketRootFiles("etc-recon-task-001", [new File(["ticket"], "ticket.jpg")], 3);
    await uploadEtcTicketRootTexts("etc-recon-task-001", [{ clientId: "paste-1", text: "车牌号：云ADA0381" }], 3);
    await uploadEtcSupplementEvidences("etc-recon-task-001", [new File(["supplement"], "parking.pdf")], 3, { evidenceKind: "non_etc_invoice" });
    await uploadEtcSupplementEvidenceForCard("etc-recon-task-001", "card-item-001", [new File(["supplement"], "parking-row.pdf")], 3, {
      evidenceKind: "non_etc_invoice",
      note: "凭证金额差异已说明。",
    });
    await patchEtcReconciliationItem("etc-recon-task-001", "card-item-001", 3, { action: "set_manual_resolution", manualResolution: "included_etc" });
    await confirmEtcReconciliationTask("etc-recon-task-001", 3, {
      confirmedCreditCardItemIds: ["card-item-001", "card-item-002"],
    });
    await reopenEtcReconciliationTask("etc-recon-task-001", 3);

    const creditUpload = fetchMock.mock.calls.find(([url]) => url === "/api/etc/reconciliation-tasks/etc-recon-task-001/credit-card-statement")?.[1] as RequestInit;
    expect((creditUpload.body as FormData).get("expectedVersion")).toBe("3");
    const textUpload = fetchMock.mock.calls.find(([url]) => url === "/api/etc/reconciliation-tasks/etc-recon-task-001/ticket-root-texts")?.[1] as RequestInit;
    expect(textUpload.method).toBe("POST");
    expect(JSON.parse(String(textUpload.body))).toEqual({
      expectedVersion: 3,
      entries: [{ clientId: "paste-1", text: "车牌号：云ADA0381" }],
    });
    expect(((creditUpload.body as FormData).getAll("files") as File[])[0].name).toBe("statement.pdf");
    const supplementUpload = fetchMock.mock.calls.find(([url]) => url === "/api/etc/reconciliation-tasks/etc-recon-task-001/supplement-evidences")?.[1] as RequestInit;
    expect((supplementUpload.body as FormData).get("evidenceKind")).toBe("non_etc_invoice");
    const rowSupplementUpload = fetchMock.mock.calls.find(([url]) => url === "/api/etc/reconciliation-tasks/etc-recon-task-001/supplement-evidences/card-item-001")?.[1] as RequestInit;
    expect((rowSupplementUpload.body as FormData).get("evidenceKind")).toBe("non_etc_invoice");
    expect((rowSupplementUpload.body as FormData).get("note")).toBe("凭证金额差异已说明。");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/reconciliation-tasks/etc-recon-task-001/confirm",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          expectedVersion: 3,
          confirmedCreditCardItemIds: ["card-item-001", "card-item-002"],
        }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/reconciliation-tasks/etc-recon-task-001/source-files/file-ticket-bad",
      expect.objectContaining({
        method: "DELETE",
        body: JSON.stringify({ expectedVersion: 3 }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/reconciliation-tasks/etc-recon-task-001/imported-invoices",
      expect.objectContaining({
        method: "DELETE",
        body: JSON.stringify({ expectedVersion: 3 }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/reconciliation-tasks/etc-recon-task-001/refresh-matches",
      expect.objectContaining({
        method: "POST",
      }),
    );
    const refreshRequest = fetchMock.mock.calls.find(([url]) => url === "/api/etc/reconciliation-tasks/etc-recon-task-001/refresh-matches")?.[1] as RequestInit;
    expect(refreshRequest.body).toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/reconciliation-tasks/etc-recon-task-001/items/card-item-001",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ expectedVersion: 3, action: "set_manual_resolution", manualResolution: "included_etc" }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/reconciliation-tasks/etc-recon-task-001/confirm",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          expectedVersion: 3,
          confirmedCreditCardItemIds: ["card-item-001", "card-item-002"],
        }),
      }),
    );
  });

  test("fetches ready ETC reconciliation tasks from the ready-for-import endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          tasks: [
            {
              taskId: "etc_task_ready_001",
              status: "ready_for_import",
              version: 7,
              title: "2026-03 ETC 对账",
              periodStart: "2026-03-01",
              periodEnd: "2026-03-31",
              oaTotalAmount: "108.40",
              etcInvoiceCount: 8,
              supplementCount: 1,
              vehiclePlates: ["云ADA0381"],
            },
          ],
          unavailableTasks: [
            {
              taskId: "etc_task_reviewing_001",
              status: "reviewing",
              version: 3,
              title: "2026-04 ETC 对账",
              periodStart: "2026-04-01",
              periodEnd: "2026-04-30",
              oaTotalAmount: "90.00",
              etcInvoiceCount: 0,
              supplementCount: 0,
              vehiclePlates: ["云A516HJ"],
              importBlockers: [{ code: "not_confirmed", message: "请先在 ETC 对账页确认对账。" }],
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    global.fetch = fetchMock as typeof fetch;

    const result = await fetchReadyEtcReconciliationTasks();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/reconciliation-tasks/ready-for-import",
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
    expect(result).toEqual({
      items: [
        {
          taskId: "etc_task_ready_001",
          status: "ready_for_import",
          version: 7,
          title: "2026-03 ETC 对账",
          periodStart: "2026-03-01",
          periodEnd: "2026-03-31",
          oaTotalAmount: "108.40",
          etcInvoiceCount: 8,
          supplementCount: 1,
          vehiclePlates: ["云ADA0381"],
        },
      ],
      unavailableItems: [
        {
          taskId: "etc_task_reviewing_001",
          status: "reviewing",
          version: 3,
          title: "2026-04 ETC 对账",
          periodStart: "2026-04-01",
          periodEnd: "2026-04-30",
          oaTotalAmount: "90.00",
          etcInvoiceCount: 0,
          supplementCount: 0,
          vehiclePlates: ["云A516HJ"],
          importBlockers: [{ code: "not_confirmed", message: "请先在 ETC 对账页确认对账。" }],
        },
      ],
    });
  });

  test("passes import batch id when fetching ETC invoices", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          counts: { unsubmitted: 1, submitted: 0 },
          items: [
            {
              id: "etc_invoice_0001",
              invoice_number: "26537911970300092160",
              issue_date: "2026-03-27",
              passage_start_date: "2026-03-27",
              passage_end_date: "2026-03-27",
              plate_number: "云A361HX",
              seller_name: "云南昆玉高速公路开发有限公司",
              buyer_name: "云南溯源科技有限公司",
              amount_without_tax: "22.82",
              tax_amount: "0.68",
              total_amount: "23.50",
              status: "unsubmitted",
              has_pdf: true,
              has_xml: true,
            },
          ],
          pagination: {
            page: 1,
            page_size: 500,
            total: 1,
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    global.fetch = fetchMock as typeof fetch;

    const payload = await fetchEtcInvoices({ importBatchId: "etc_import_batch_0004", page: 1, pageSize: 500 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/invoices?importBatchId=etc_import_batch_0004&page=1&page_size=500",
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
    expect(payload.items).toHaveLength(1);
    expect(payload.items[0]).toMatchObject({
      id: "etc_invoice_0001",
      invoiceNumber: "26537911970300092160",
      totalAmount: "23.50",
    });
  });

  test("maps stale reconciliation task preview errors to a re-preview message", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: "stale_reconciliation_task_preview",
          message: "stale_reconciliation_task_preview",
        }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      ),
    );
    global.fetch = fetchMock as typeof fetch;

    await expect(confirmEtcImportSession("etc_import_session_001", "etc_task_ready_001")).rejects.toThrow(
      "对账任务已更新，请重新预览 ETC zip 后再确认导入。",
    );
  });
});
