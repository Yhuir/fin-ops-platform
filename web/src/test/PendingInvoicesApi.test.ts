import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchBankDetailTransactions } from "../features/bankDetails/api";
import {
  confirmManualPendingInvoice,
  fetchPendingInvoiceRows,
  previewManualPendingInvoice,
} from "../features/pendingInvoices/api";
import { fetchWorkbenchSettings, saveWorkbenchSettings } from "../features/workbench/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("pending invoices and tag settings API mapping", () => {
  test("maps pending invoice rows, pagination, summary, and sends filter query", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      direction: "expense",
      filter: "requires_invoice",
      rows: [
        {
          id: "txn_001",
          bank_transaction: {
            id: "txn_001",
            counterparty_name: "云南供应商有限公司",
            trade_time: "2026-05-02 10:00:00",
            amount: "1200.00",
            bank_name: "工商银行",
            account_last4: "6386",
            effective_tag_code: "fee",
            effective_tag_label: "手续费",
          },
          invoices: [
            {
              id: "inv_001",
              invoice_no: "INV-001",
              digital_invoice_no: "DIG-001",
              issue_date: "2026-05-03",
              total_with_tax: "1200.00",
              seller_name: "云南供应商有限公司",
              buyer_name: "云南溯源科技有限公司",
              invoice_type: "input",
            },
          ],
          oa_applicant: "张三",
          can_create_invoice: true,
          relation_case_ids: ["case_001"],
        },
      ],
      pagination: { page: 2, page_size: 25, total: 51 },
      summary: { total_rows: 51, missing_invoice_rows: 8, create_invoice_available_rows: 7 },
      tag_dictionary: {
        version: 9,
        tags: [{ code: "fee", label: "手续费", path: ["自动识别", "手续费"], status: "active", source: "system" }],
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const payload = await fetchPendingInvoiceRows({
      direction: "expense",
      filter: "requires_invoice",
      page: 2,
      pageSize: 25,
      keyword: "供应商",
    });

    const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/pending-invoices/rows");
    expect(url.searchParams.get("direction")).toBe("expense");
    expect(url.searchParams.get("filter")).toBe("requires_invoice");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("page_size")).toBe("25");
    expect(url.searchParams.get("keyword")).toBe("供应商");
    expect(payload.rows[0]).toMatchObject({
      id: "txn_001",
      bankTransaction: {
        counterpartyName: "云南供应商有限公司",
        accountLast4: "6386",
        effectiveTagLabel: "手续费",
      },
      invoices: [{ invoiceNo: "INV-001", digitalInvoiceNo: "DIG-001", invoiceType: "input" }],
      oaApplicant: "张三",
      canCreateInvoice: true,
      relationCaseIds: ["case_001"],
    });
    expect(payload.pagination).toEqual({ page: 2, pageSize: 25, total: 51 });
    expect(payload.summary).toEqual({ totalRows: 51, missingInvoiceRows: 8, createInvoiceAvailableRows: 7 });
    expect(payload.tagDictionary?.version).toBe(9);
  });

  test("previews and confirms manual invoice with request id preserved", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
      if (url.pathname.endsWith("/preview")) {
        return new Response(JSON.stringify({
          preview_id: "preview_001",
          request_key: "manual-pending-invoice:txn_001:input:INV-001",
          can_confirm: true,
          target_invoice_type: "input",
          bank_transaction_summary: {
            id: "txn_001",
            direction: "expense",
            counterparty_name: "云南供应商有限公司",
            trade_time: "2026-05-02",
            amount: "1200.00",
          },
          invoice_identity: { source_unique_key: "manual-key", data_fingerprint: "fingerprint" },
          duplicate_check: { status: "clear", matched_invoice_id: null, message: "" },
          relation_impact: { relation_mode: "pending_invoice_manual_invoice", affected_months: ["2026-05"] },
          warnings: [],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      expect(body.request_id).toBe("request-001");
      return new Response(JSON.stringify({
        invoice_id: "inv_002",
        relation_case_id: "case_002",
        affected_transaction_ids: ["txn_001"],
        affected_invoice_ids: ["inv_002"],
        affected_months: ["2026-05"],
        row: { id: "txn_001", bank_transaction: { id: "txn_001" }, invoices: [], can_create_invoice: false },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const request = {
      requestId: "request-001",
      bankTransactionId: "txn_001",
      invoiceNo: "INV-001",
      issueDate: "2026-05-03",
      totalWithTax: "1200.00",
      sellerName: "云南供应商有限公司",
      buyerName: "云南溯源科技有限公司",
    };

    const preview = await previewManualPendingInvoice(request);
    const result = await confirmManualPendingInvoice({ ...request, previewId: preview.previewId });

    expect(preview).toMatchObject({
      previewId: "preview_001",
      requestKey: "manual-pending-invoice:txn_001:input:INV-001",
      targetInvoiceType: "input",
      affectedMonths: ["2026-05"],
    });
    expect(result).toMatchObject({ invoiceId: "inv_002", relationCaseId: "case_002", affectedMonths: ["2026-05"] });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test("maps settings tag dictionary and pending invoice tag groups both directions", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        expect(body.bank_transaction_tags).toMatchObject({ version: 3 });
        expect(body.pending_invoice_tag_groups).toEqual({
          groups: {
            requires_invoice: { tag_codes: ["fee"] },
            bank_statement_as_invoice: { tag_codes: ["internal_transfer"] },
            no_invoice_required: { tag_codes: ["salary"] },
          },
        });
      }
      return new Response(JSON.stringify({
        projects: { active: [], completed: [], completed_project_ids: [] },
        bank_account_mappings: [],
        access_control: { allowed_usernames: [], readonly_export_usernames: [], admin_usernames: [], full_access_usernames: [] },
        workbench_column_layouts: { oa: [], bank: [], invoice: [] },
        oa_retention: { cutoff_date: "2026-01-01" },
        oa_import: { form_types: [], statuses: [] },
        oa_invoice_offset: { applicant_names: [] },
        bank_transaction_tags: {
          version: 3,
          tags: [
            { code: "fee", label: "手续费", path: ["自动识别", "手续费"], status: "active", source: "system" },
            { code: "custom_meal", label: "餐费", path: ["自定义", "餐费"], status: "active", source: "custom" },
          ],
        },
        pending_invoice_tag_groups: {
          requires_invoice: ["fee"],
          bank_statement_as_invoice: ["internal_transfer"],
          no_invoice_required: ["salary"],
        },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const settings = await fetchWorkbenchSettings();
    expect(settings.bankTransactionTags).toMatchObject({
      version: 3,
    });
    expect(settings.bankTransactionTags.tags).toEqual(
      expect.arrayContaining([
        { code: "fee", label: "手续费", path: ["自动识别", "手续费"], status: "active", source: "system" },
      ]),
    );
    expect(settings.pendingInvoiceTagGroups).toEqual({
      requiresInvoice: ["fee"],
      bankStatementAsInvoice: ["internal_transfer"],
      noInvoiceRequired: ["salary"],
    });

    await saveWorkbenchSettings({
      completedProjectIds: [],
      bankAccountMappings: [],
      allowedUsernames: [],
      readonlyExportUsernames: [],
      adminUsernames: [],
      workbenchColumnLayouts: { oa: [], bank: [], invoice: [] },
      oaRetention: { cutoffDate: "2026-01-01" },
      oaImport: { formTypes: [], statuses: [] },
      oaInvoiceOffset: { applicantNames: [] },
      bankTransactionTags: settings.bankTransactionTags,
      pendingInvoiceTagGroups: settings.pendingInvoiceTagGroups,
    });
  });

  test("maps bank details tag dictionary version from transaction response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      rows: [],
      pagination: { page: 1, page_size: 100, total: 0 },
      category_counts: { uncategorized: 0 },
      tag_dictionary: {
        version: 12,
        tags: [{ code: "fee", label: "手续费", path: ["自动识别", "手续费"], status: "active", source: "system" }],
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } })));

    const payload = await fetchBankDetailTransactions({});

    expect(payload.tagDictionary?.version).toBe(12);
    expect(payload.tagDictionary?.tags[0]).toMatchObject({ code: "fee", label: "手续费", status: "active" });
  });
});
