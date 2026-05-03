import { afterEach, describe, expect, test, vi } from "vitest";

import {
  confirmEtcBatchSubmitted,
  confirmEtcImportSession,
  createEtcOaDraft,
  fetchEtcInvoices,
  markEtcBatchNotSubmitted,
  previewEtcZipFiles,
  revokeEtcSubmittedInvoices,
} from "../features/etc/api";

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
  document.cookie = "Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("etc api", () => {
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
      if (url === "/api/etc/batches/draft") {
        return new Response(
          JSON.stringify({
            batchId: "etc_batch_001",
            oaDraftId: "oa_draft_001",
            oaDraftUrl: "https://oa.example.test/draft/001",
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

    const draftResult = await createEtcOaDraft(["etc-inv-001"]);
    await confirmEtcBatchSubmitted("etc_batch_001");
    await markEtcBatchNotSubmitted("etc_batch_001");
    await revokeEtcSubmittedInvoices(["etc-inv-002"]);

    expect(draftResult.oaDraftUrl).toBe("https://oa.example.test/draft/001");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/etc/batches/draft",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ invoiceIds: ["etc-inv-001"] }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/etc/batches/etc_batch_001/confirm-submitted",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/etc/batches/etc_batch_001/mark-not-submitted",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/etc/invoices/revoke-submitted",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ invoiceIds: ["etc-inv-002"] }),
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

    await expect(createEtcOaDraft(["etc-inv-001"])).rejects.toThrow("ETC 接口返回了 HTML 页面");
  });

  test("retries alternate API entrypoint when current ETC endpoint returns HTML", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url === "/api/etc/batches/draft") {
        return new Response("<html><head><title>405 Not Allowed</title></head></html>", {
          status: 405,
          headers: { "Content-Type": "text/html" },
        });
      }
      if (url === "/fin-ops-api/api/etc/batches/draft") {
        return new Response(
          JSON.stringify({
            batchId: "etc_batch_001",
            etcBatchId: "etc_20260503_001",
            oaDraftId: "oa_draft_001",
            oaDraftUrl: "https://oa.example.test/draft/001",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      throw new Error(`unexpected url ${url}`);
    });
    global.fetch = fetchMock as typeof fetch;

    const draftResult = await createEtcOaDraft(["etc-inv-001"]);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/etc/batches/draft",
      "/fin-ops-api/api/etc/batches/draft",
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

    const result = await previewEtcZipFiles([
      new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" }),
      new File(["zip-b"], "etc-2026-04.zip", { type: "application/zip" }),
    ]);

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
    expect(result).toEqual({
      sessionId: "etc_import_session_001",
      imported: 1,
      duplicatesSkipped: 2,
      attachmentsCompleted: 3,
      failed: 4,
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

  test("confirms ETC import session with Authorization header and maps snake_case fallback fields", async () => {
    document.cookie = "Admin-Token=mock-cookie-token";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          session_id: "etc_import_session_001",
          summary: {
            imported: 1,
            duplicates_skipped: 2,
            attachments_completed: 3,
            failed: 4,
          },
          items: [
            {
              invoice_number: "ETC-2026-006",
              file_name: "etc-2026-03.zip",
              status: "duplicate_skipped",
              message: "发票号码已存在",
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    global.fetch = fetchMock as typeof fetch;

    const result = await confirmEtcImportSession("etc_import_session_001");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/import/confirm",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ sessionId: "etc_import_session_001" }),
      }),
    );
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer mock-cookie-token");
    expect((init.headers as Headers).get("Content-Type")).toBe("application/json");
    expect(result).toEqual({
      sessionId: "etc_import_session_001",
      imported: 1,
      duplicatesSkipped: 2,
      attachmentsCompleted: 3,
      failed: 4,
      items: [
        {
          invoiceNumber: "ETC-2026-006",
          fileName: "etc-2026-03.zip",
          status: "duplicate_skipped",
          reason: "发票号码已存在",
        },
      ],
    });
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

    const result = await confirmEtcImportSession("etc_import_session_001");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/import/confirm",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ sessionId: "etc_import_session_001" }),
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
});
