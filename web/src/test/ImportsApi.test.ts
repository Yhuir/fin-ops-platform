import { afterEach, describe, expect, test, vi } from "vitest";

import {
  confirmImportFiles,
  discardImportSession,
  fetchImportReviewRows,
  fetchImportSession,
  previewManualInvoices,
  previewManualBankTransactions,
  previewImportFiles,
  recognizeManualInvoice,
  resolveImportApiErrorMessage,
  retryImportFiles,
} from "../features/imports/api";
import { ApiClientError } from "../features/apiClient";

const originalFetch = global.fetch;
const EMPTY_API_AUDIT = {
  original_count: 0,
  unique_count: 0,
  duplicate_count: 0,
  duplicate_in_file_count: 0,
  duplicate_across_files_count: 0,
  existing_duplicate_count: 0,
  importable_count: 0,
  update_count: 0,
  merge_count: 0,
  suspected_duplicate_count: 0,
  error_count: 0,
  confirmable_count: 0,
  skipped_count: 0,
};

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
  document.cookie = "Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("imports api", () => {
  test("serializes manual bank entries and maps the server-authoritative preview", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      values: [{
        bank_mapping_id: "ccb-8106",
        bank_name: "中国建设银行",
        bank_short_name: "建行",
        last4: "8106",
        account_no: "6227000012348106",
        account_name: "云南溯源科技有限公司",
        direction: "outflow",
        amount: "100.00",
        balance: "900.00",
        trade_time: "2026-08-28 09:01:02",
        currency: "CNY",
        counterparty_name: "测试供应商",
        counterparty_account_no: "",
        counterparty_bank_name: "",
        summary: "电子转账",
        remark: "人工录入",
      }],
      file_ids: ["manual_bank_file_1"],
      import_session: {
        session: {
          id: "manual_bank_session_1",
          imported_by: "web_finance_user",
          file_count: 1,
          status: "preview_ready",
          created_at: "2026-08-28T09:02:00+08:00",
          audit: { ...EMPTY_API_AUDIT, original_count: 1, unique_count: 1, importable_count: 1, confirmable_count: 1 },
        },
        files: [{
          id: "manual_bank_file_1",
          file_name: "新流水1",
          template_code: "manual_bank_transaction_entry",
          batch_type: "bank_transaction",
          status: "preview_ready",
          message: "预览成功",
          row_count: 1,
          success_count: 1,
          error_count: 0,
          duplicate_count: 0,
          suspected_duplicate_count: 0,
          updated_count: 0,
          audit: { ...EMPTY_API_AUDIT, original_count: 1, unique_count: 1, importable_count: 1, confirmable_count: 1 },
          row_results: [{
            id: "row-1",
            row_no: 1,
            source_record_type: "bank_transaction",
            decision: "created",
            decision_reason: "Ready to create new bank transaction.",
          }],
        }],
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    global.fetch = fetchMock as typeof fetch;

    const preview = await previewManualBankTransactions([{
      bankMappingId: "ccb-8106",
      bankName: "中国建设银行",
      bankShortName: "建行",
      last4: "8106",
      accountNo: "6227000012348106",
      accountName: "云南溯源科技有限公司",
      direction: "outflow",
      amount: "100",
      balance: "900",
      tradeTime: "2026-08-28T09:01:02",
      currency: "CNY",
      counterpartyName: "测试供应商",
      counterpartyAccountNo: "",
      counterpartyBankName: "",
      summary: "电子转账",
      remark: "人工录入",
    }]);

    expect(preview.fileIds).toEqual(["manual_bank_file_1"]);
    expect(preview.values[0]).toMatchObject({
      direction: "outflow",
    });
    expect(preview.importSession.files[0].rowResults).toEqual([
      expect.objectContaining({
        decision: "created",
        decisionReason: "Ready to create new bank transaction.",
      }),
    ]);
    expect(fetchMock).toHaveBeenCalledWith(
      "/imports/bank-transactions/manual/preview",
      expect.objectContaining({ method: "POST" }),
    );
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      transactions: [{
        bank_mapping_id: "ccb-8106",
        direction: "outflow",
      }],
    });
    expect(JSON.parse(String(request.body)).transactions[0]).not.toHaveProperty("account_detail_no");
  });

  test("rejects a manual bank preview that omits its row decision", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      values: [{ direction: "outflow" }],
      file_ids: ["manual_bank_file_1"],
      import_session: {
        session: {
          id: "manual_bank_session_1",
          imported_by: "web_finance_user",
          file_count: 1,
          status: "preview_ready",
          created_at: "2026-08-28T09:02:00+08:00",
          audit: { ...EMPTY_API_AUDIT, original_count: 1, unique_count: 1, importable_count: 1, confirmable_count: 1 },
        },
        files: [{
          id: "manual_bank_file_1",
          file_name: "新流水1",
          status: "preview_ready",
          message: "预览成功",
          row_count: 1,
          success_count: 1,
          error_count: 0,
          duplicate_count: 0,
          suspected_duplicate_count: 0,
          updated_count: 0,
          audit: { ...EMPTY_API_AUDIT, original_count: 1, unique_count: 1, importable_count: 1, confirmable_count: 1 },
          row_results: [],
        }],
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } })) as typeof fetch;

    await expect(previewManualBankTransactions([])).rejects.toThrow("流水预览响应不完整，请重新预览。");
  });

  test("maps OCR prefill and serializes the server-authoritative manual invoice preview", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        values: {
          seller_name: "云南供应商",
          invoice_number: "12345678901234567890",
          tax_rate: "13",
        },
      }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        values: [{
          invoice_direction: "input",
          invoice_nature: "red",
          seller_name: "云南供应商",
          seller_tax_no: "915300001",
          buyer_name: "云南采购方",
          buyer_tax_no: "915300002",
          invoice_number: "12345678901234567890",
          invoice_code: "",
          invoice_date: "2026-08-14",
          net_amount: "100.00",
          tax_rate: "13",
          tax_amount: "13.00",
          total_with_tax: "113.00",
        }],
        file_ids: ["manual_file_1"],
        import_session: {
          session: {
            id: "manual_session_1",
            imported_by: "web_finance_user",
            file_count: 1,
            status: "awaiting_confirmation",
            created_at: "2026-08-14T10:00:00+08:00",
            audit: { ...EMPTY_API_AUDIT, original_count: 1, unique_count: 1, importable_count: 1, confirmable_count: 1 },
          },
          files: [{
            id: "manual_file_1",
            file_name: "发票录入",
            template_code: "manual_invoice_entry",
            batch_type: "input_invoice",
            status: "preview_ready",
            message: "预览成功",
            row_count: 1,
            success_count: 1,
            error_count: 0,
            duplicate_count: 0,
            suspected_duplicate_count: 0,
            updated_count: 0,
            audit: { ...EMPTY_API_AUDIT, original_count: 1, unique_count: 1, importable_count: 1, confirmable_count: 1 },
            row_results: [],
          }],
        },
      }), { status: 200, headers: { "Content-Type": "application/json" } }));
    global.fetch = fetchMock as typeof fetch;

    const recognized = await recognizeManualInvoice(new File(["jpg"], "invoice.jpg", { type: "image/jpeg" }));
    const preview = await previewManualInvoices([{
      invoiceDirection: "input",
      invoiceNature: "red",
      sellerName: "云南供应商",
      sellerTaxNo: "915300001",
      buyerName: "云南采购方",
      buyerTaxNo: "915300002",
      invoiceNumber: "12345678901234567890",
      invoiceCode: "",
      invoiceDate: "2026-08-14",
      netAmount: "100",
      taxRate: "13",
      taxAmount: "13",
      totalWithTax: "113",
    }]);

    expect(recognized).toMatchObject({ sellerName: "云南供应商", taxRate: "13" });
    expect(preview.fileIds).toEqual(["manual_file_1"]);
    expect(preview.values[0]?.invoiceNature).toBe("red");
    expect(preview.importSession.files[0]?.templateCode).toBe("manual_invoice_entry");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/imports/invoices/manual/recognize",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    );
    const previewRequest = fetchMock.mock.calls[1]?.[1] as RequestInit;
    expect(JSON.parse(String(previewRequest.body))).toMatchObject({
      invoices: [{
        invoice_direction: "input",
        invoice_nature: "red",
        invoice_number: "12345678901234567890",
        tax_rate: "13",
      }],
    });
  });

  test("extracts backend message from json-shaped request errors", () => {
    expect(
      resolveImportApiErrorMessage(
        new Error(JSON.stringify({ error: "invalid_multipart_body", message: "文件读取失败，请确认文件未损坏且为受支持的 Excel 模板。" })),
        "文件预览失败，请稍后重试。",
      ),
    ).toBe("文件读取失败，请确认文件未损坏且为受支持的 Excel 模板。");
  });

  test("falls back when the error is not a json payload", () => {
    expect(resolveImportApiErrorMessage(new Error("network down"), "文件预览失败，请稍后重试。")).toBe("network down");
    expect(resolveImportApiErrorMessage(null, "文件预览失败，请稍后重试。")).toBe("文件预览失败，请稍后重试。");
  });

  test("preserves the backend request id in import errors", () => {
    const error = new ApiClientError("导入任务暂时不可用。", {
      status: 503,
      code: "import_queue_unavailable",
      payload: { message: "导入任务暂时不可用。", requestId: "req-import-001" },
      url: "/imports/files/confirm",
    });

    expect(resolveImportApiErrorMessage(error, "确认导入失败，请稍后重试。"))
      .toBe("导入任务暂时不可用。（请求编号：req-import-001）");
  });

  test("sends Authorization header and credentials for preview uploads", async () => {
    document.cookie = "Admin-Token=mock-cookie-token";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          session: {
            id: "import_session_0001",
            imported_by: "web_finance_user",
            file_count: 1,
            status: "preview_ready",
            created_at: "2026-04-14T10:00:00Z",
            audit: { ...EMPTY_API_AUDIT, original_count: 1, unique_count: 1, importable_count: 1, confirmable_count: 1 },
          },
          files: [
            {
              id: "import_file_0001",
              file_name: "销项发票.xlsx",
              template_code: "invoice_export",
              batch_type: "output_invoice",
              status: "preview_ready",
              message: "预览成功",
              row_count: 1,
              success_count: 1,
              error_count: 0,
              duplicate_count: 0,
              suspected_duplicate_count: 0,
              updated_count: 0,
              audit: { ...EMPTY_API_AUDIT, original_count: 1, unique_count: 1, importable_count: 1, confirmable_count: 1 },
              row_results: [],
            },
          ],
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );
    global.fetch = fetchMock as typeof fetch;

    await previewImportFiles([
      new File(["demo"], "销项发票.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
    ]);

    expect(fetchMock).toHaveBeenCalledWith(
      "/imports/files/preview",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.any(Headers),
      }),
    );
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer mock-cookie-token");
    expect(init.body).toBeInstanceOf(FormData);
  });

  test("sends Authorization header and credentials for json import actions", async () => {
    document.cookie = "Admin-Token=mock-cookie-token";
    const fetchMock = vi.fn().mockImplementation(async () =>
      new Response(
        JSON.stringify({
          session: {
            id: "import_session_0001",
            imported_by: "web_finance_user",
            file_count: 1,
            status: "preview_ready",
            created_at: "2026-04-14T10:00:00Z",
            audit: EMPTY_API_AUDIT,
          },
          files: [],
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      )
    );
    global.fetch = fetchMock as typeof fetch;

    await retryImportFiles("import_session_0001", ["import_file_0001"], {
      import_file_0001: {
        templateCode: "bank_statement",
        batchType: "bank_transaction",
        fieldMapping: { credit_amount: "2" },
      },
    });
    await confirmImportFiles("import_session_0001", ["import_file_0001"]);
    await fetchImportSession("import_session_0001");
    await discardImportSession("import_session_0001");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/imports/files/retry",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.any(Headers),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/imports/files/confirm",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.any(Headers),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/imports/files/sessions/import_session_0001",
      expect.objectContaining({
        method: "GET",
        credentials: "include",
        headers: expect.any(Headers),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/imports/files/discard",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );

    fetchMock.mock.calls.forEach(([, init]) => {
      const headers = init?.headers as Headers;
      expect(headers.get("Authorization")).toBe("Bearer mock-cookie-token");
    });
    expect(JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body))).toMatchObject({
      overrides: {
        import_file_0001: {
          template_code: "bank_statement",
          batch_type: "bank_transaction",
          field_mapping: { credit_amount: "2" },
        },
      },
    });
  });

  test("maps duplicate group and skipped row detail fields from preview response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          session: {
            id: "import_session_0001",
            imported_by: "web_finance_user",
            file_count: 1,
            status: "preview_ready",
            created_at: "2026-04-14T10:00:00Z",
            audit: {
              ...EMPTY_API_AUDIT,
              original_count: 2,
              unique_count: 1,
              duplicate_count: 1,
              duplicate_in_file_count: 1,
              duplicate_across_files_count: 0,
              existing_duplicate_count: 0,
              importable_count: 1,
              confirmable_count: 1,
              skipped_count: 1,
            },
          },
          files: [
            {
              id: "import_file_0001",
              file_name: "建行流水.xlsx",
              template_code: "bank_ccb",
              batch_type: "bank_transaction",
              status: "preview_ready",
              message: "预览成功",
              row_count: 2,
              success_count: 1,
              error_count: 0,
              duplicate_count: 1,
              suspected_duplicate_count: 0,
              updated_count: 0,
              audit: {
                ...EMPTY_API_AUDIT,
                original_count: 2,
                unique_count: 1,
                duplicate_count: 1,
                duplicate_in_file_count: 1,
                importable_count: 1,
                confirmable_count: 1,
                skipped_count: 1,
              },
              row_results: [
                {
                  id: "row_1",
                  row_no: 2,
                  source_record_type: "bank_transaction",
                  decision: "duplicate_skipped",
                  decision_reason: "文件内重复",
                  account_no: "6222",
                  trade_time: "2026-03-01 09:00:00",
                  direction: "outflow",
                  amount: "100.00",
                  counterparty_name: "云南供应商",
                  linked_object_type: "bank_transaction",
                  linked_object_id: "bank_001",
                  identity_kind: "stable",
                },
              ],
            },
          ],
          duplicate_groups: [
            {
              identity_key: "bank:6222:2026-03-01 09:00:00:outflow:100.00:云南供应商",
              record_type: "bank_transaction",
              duplicate_type: "duplicate_in_file",
              rows: [
                {
                  file_id: "import_file_0001",
                  file_name: "建行流水.xlsx",
                  row_no: 2,
                  decision: "duplicate_skipped",
                  decision_reason: "文件内重复",
                  linked_object_type: "bank_transaction",
                  linked_object_id: "bank_001",
                  identity_kind: "stable",
                  account_no: "6222",
                  trade_time: "2026-03-01 09:00:00",
                  direction: "outflow",
                  amount: "100.00",
                  counterparty_name: "云南供应商",
                },
              ],
            },
          ],
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );
    global.fetch = fetchMock as typeof fetch;

    const payload = await previewImportFiles([
      new File(["demo"], "建行流水.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
    ]);

    expect(payload.session.audit?.skippedCount).toBe(1);
    expect(payload.duplicateGroups[0].rows[0]).toMatchObject({
      fileId: "import_file_0001",
      fileName: "建行流水.xlsx",
      rowNo: 2,
      decision: "duplicate_skipped",
      decisionReason: "文件内重复",
      linkedObjectType: "bank_transaction",
      linkedObjectId: "bank_001",
      identityKind: "stable",
      accountNo: "6222",
      tradeTime: "2026-03-01 09:00:00",
      direction: "outflow",
      amount: "100.00",
      counterpartyName: "云南供应商",
    });
    expect(payload.files[0].rowResults[0]).toMatchObject({
      decision: "duplicate_skipped",
      accountNo: "6222",
      tradeTime: "2026-03-01 09:00:00",
      direction: "outflow",
      amount: "100.00",
      counterpartyName: "云南供应商",
      identityKind: "stable",
    });
  });

  test("rejects malformed successful review-row responses instead of showing an empty result", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ total: 1 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ) as typeof fetch;

    await expect(fetchImportReviewRows("import_session_0001", "duplicates", 0)).rejects.toThrow(
      "导入复核数据响应格式错误，请刷新后重试。",
    );
  });
});
