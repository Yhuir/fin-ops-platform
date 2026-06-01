import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchBankDetailTransactions } from "../features/bankDetails/api";
import * as pendingInvoicesApi from "../features/pendingInvoices/api";
import { fetchWorkbenchSettings, saveWorkbenchSettings } from "../features/workbench/api";
import type {
  AttachExistingInvoiceConfirmRequest,
  AttachExistingInvoicePreviewRequest,
  FetchPendingInvoiceCandidatesRequest,
  FetchPendingInvoiceRowsRequest,
  ManualPendingInvoiceRequest,
  PendingInvoiceColumnFilter,
  PendingInvoiceObjectDetailTarget,
  PendingInvoiceRulesPayload,
} from "../features/pendingInvoices/types";

afterEach(() => {
  vi.unstubAllGlobals();
});

function api() {
  return pendingInvoicesApi as typeof pendingInvoicesApi & {
    fetchPendingInvoiceFilterOptions: (request: FetchPendingInvoiceRowsRequest) => Promise<unknown>;
    fetchPendingInvoiceRules: () => Promise<PendingInvoiceRulesPayload>;
    savePendingInvoiceRules: (payload: PendingInvoiceRulesPayload) => Promise<PendingInvoiceRulesPayload>;
    fetchPendingInvoiceRelationDetail: (transactionId: string, direction?: string) => Promise<unknown>;
    fetchPendingInvoiceObjectDetail: (target: PendingInvoiceObjectDetailTarget) => Promise<unknown>;
    fetchPendingInvoiceCandidates: (request: FetchPendingInvoiceCandidatesRequest) => Promise<unknown>;
    previewAttachExistingInvoice: (request: AttachExistingInvoicePreviewRequest) => Promise<unknown>;
    confirmAttachExistingInvoice: (request: AttachExistingInvoiceConfirmRequest) => Promise<unknown>;
    fetchPendingInvoiceExportPreview: (request: FetchPendingInvoiceRowsRequest) => Promise<unknown>;
    downloadPendingInvoiceExport: (request: FetchPendingInvoiceRowsRequest) => Promise<{ blob: Blob; fileName: string }>;
  };
}

describe("pending invoices and tag settings API mapping", () => {
  test("does not infer pending invoice status or primary action when backend contract is missing", () => {
    expect(() => pendingInvoicesApi.mapPendingInvoiceRow({
      id: "txn_legacy",
      bank_transaction: { id: "txn_legacy", counterparty_name: "旧数据供应商" },
      invoices: [{ id: "inv_legacy", invoice_no: "INV-LEGACY" }],
      can_create_invoice: true,
    } as Parameters<typeof pendingInvoicesApi.mapPendingInvoiceRow>[0])).toThrow(/invoice_acquisition_status/);
  });

  test("maps upgraded four-zone pending invoice rows and sends filters/sort query", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      direction: "expense",
      filter: "requires_invoice",
      rows: [
        {
          id: "txn_001",
          bank_transaction: {
            id: "txn_001",
            counterparty_name: "云南供应商有限公司",
            counterparty_account_no: "6222000011112222",
            counterparty_bank_name: "工行昆明分行",
            trade_time: "2026-05-02T10:00:00+08:00",
            booked_date: "2026-05-02",
            debit_amount: "1200.00",
            credit_amount: "0.00",
            balance: "9800.00",
            currency: "人民币元",
            bank_name: "工商银行",
            bank_short_name: "工行",
            account_name: "云南溯源科技有限公司",
            account_last4: "6386",
            summary: "电子转账",
            remark: "维护费",
            statement_serial_no: "stmt-001",
            enterprise_serial_no: "ent-001",
            voucher_type: "电子凭证",
            voucher_no: "v-001",
          },
          invoice_acquisition_status: {
            code: "invoice_not_fully_paid",
            label: "未支付完已开票",
            reason: "发票价税合计大于已付合计",
            severity: "warning",
            primary_action: "view_payment_detail",
            matched_rule: {
              source: "pending_invoice_tag_groups",
              group: "requires_invoice",
              tag_code: "fee",
              tag_label: "手续费",
            },
          },
          input_invoices: {
            primary: {
              id: "inv_001",
              digital_invoice_no: "DIG-001",
              invoice_no: "INV-001",
              invoice_code: "CODE-001",
              issue_date: "2026-05-03",
              seller_name: "云南供应商有限公司",
              seller_tax_no: "915300001111",
              total_with_tax: "2000.00",
            },
            relation_count: 2,
            has_multiple: true,
            summaries: [
              { id: "inv_001", digital_invoice_no: "DIG-001", issue_date: "2026-05-03", seller_name: "云南供应商有限公司", seller_tax_no: "915300001111", total_with_tax: "2000.00" },
              { id: "inv_002", digital_invoice_no: "DIG-002", issue_date: "2026-05-04", seller_name: "云南供应商二号", seller_tax_no: "915300002222", total_with_tax: "800.00" },
            ],
            payment_summary: {
              paid_total: "1200.00",
              invoice_total: "2000.00",
              remaining_amount: "800.00",
              difference_amount: "-800.00",
            },
          },
          oa: {
            primary: {
              id: "oa_001",
              applicant: "张三",
              application_type: "支付",
              project_name: "维护项目",
              status: "进行中",
            },
            relation_count: 2,
            has_multiple: true,
            detail_available: true,
            summaries: [
              { id: "oa_001", applicant: "张三", application_type: "支付", project_name: "维护项目", status: "进行中" },
              { id: "oa_002", applicant: "李四", application_type: "报销", project_name: "维护项目二期", status: "已完成" },
            ],
          },
          can_create_invoice: false,
          available_actions: ["view_relation"],
        },
      ],
      pagination: { page: 2, page_size: 25, total: 51 },
      summary: {
        total_rows: 51,
        missing_invoice_rows: 8,
        create_invoice_available_rows: 7,
        source_summary: {
          bank_transaction_rows: 431,
          expense_rows: 356,
          income_rows: 75,
          current_direction_rows: 356,
          excluded_direction_rows: 75,
        },
      },
      read_model_status: "fresh",
      tag_dictionary: {
        version: 9,
        tags: [{ code: "fee", label: "手续费", path: ["自动识别", "手续费"], status: "active", source: "system" }],
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const filters: PendingInvoiceColumnFilter[] = [
      { field: "status_code", operator: "in", values: ["invoice_not_fully_paid"] },
      { field: "amount", operator: "between", value: { min: "1000.00", max: "2000.00" } },
    ];

    const payload = await pendingInvoicesApi.fetchPendingInvoiceRows({
      direction: "expense",
      filter: "requires_invoice",
      dateFrom: "2026-05-01",
      dateTo: "2026-05-31",
      page: 2,
      pageSize: 25,
      keyword: "供应商",
      filters,
      sortField: "invoice_total",
      sortDirection: "asc",
    });

    const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/pending-invoices/rows");
    expect(url.searchParams.get("direction")).toBe("expense");
    expect(url.searchParams.get("filter")).toBe("requires_invoice");
    expect(url.searchParams.get("date_from")).toBe("2026-05-01");
    expect(url.searchParams.get("date_to")).toBe("2026-05-31");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("page_size")).toBe("25");
    expect(url.searchParams.get("keyword")).toBe("供应商");
    expect(url.searchParams.get("sort_field")).toBe("invoice_total");
    expect(url.searchParams.get("sort_direction")).toBe("asc");
    expect(JSON.parse(url.searchParams.get("filters") ?? "[]")).toEqual(filters);
    expect(payload.summary.sourceSummary).toEqual({
      bankTransactionRows: 431,
      expenseRows: 356,
      incomeRows: 75,
      currentDirectionRows: 356,
      excludedDirectionRows: 75,
    });
    expect(payload.rows[0]).toMatchObject({
      id: "txn_001",
      bankTransaction: {
        counterpartyName: "云南供应商有限公司",
        counterpartyAccountNo: "6222000011112222",
        tradeTime: "2026-05-02 10:00:00",
        debitAmount: "1200.00",
        bankShortName: "工行",
        accountName: "云南溯源科技有限公司",
        summary: "电子转账",
        voucherNo: "v-001",
      },
      invoiceAcquisitionStatus: {
        code: "invoice_not_fully_paid",
        label: "未支付完已开票",
        primaryAction: "view_payment_detail",
        matchedRule: { group: "requires_invoice", tagLabel: "手续费" },
      },
      inputInvoices: {
        relationCount: 2,
        hasMultiple: true,
        primary: { digitalInvoiceNo: "DIG-001", sellerTaxNo: "915300001111" },
        paymentSummary: { paidTotal: "1200.00", remainingAmount: "800.00" },
      },
      oa: {
        relationCount: 2,
        hasMultiple: true,
        detailAvailable: true,
        primary: { applicant: "张三", projectName: "维护项目" },
      },
    });
    expect(payload.pagination).toEqual({ page: 2, pageSize: 25, total: 51 });
    expect(payload.summary).toEqual({
      totalRows: 51,
      missingInvoiceRows: 8,
      createInvoiceAvailableRows: 7,
      sourceSummary: {
        bankTransactionRows: 431,
        expenseRows: 356,
        incomeRows: 75,
        currentDirectionRows: 356,
        excludedDirectionRows: 75,
      },
    });
    expect(payload.readModelStatus).toBe("fresh");
    expect(payload.tagDictionary?.version).toBe(9);
  });

  test("maps filter options from top-level backend options map", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      fields: [
        { field: "status_code", label: "发票获取状态", operators: ["in"] },
        { field: "seller_name", label: "销方", operators: ["contains", "in"] },
      ],
      options: {
        status_code: [{ value: "paid_pending_invoice", label: "已支付待开票", count: 3 }],
        seller_name: [{ value: "云南供应商", label: "云南供应商", count: 2 }],
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const payload = await api().fetchPendingInvoiceFilterOptions({ direction: "expense", filter: "all" });

    expect(payload.fields).toEqual([
      {
        field: "status_code",
        label: "发票获取状态",
        operators: ["in"],
        options: [{ value: "paid_pending_invoice", label: "已支付待开票", count: 3 }],
      },
      {
        field: "seller_name",
        label: "销方",
        operators: ["contains", "in"],
        options: [{ value: "云南供应商", label: "云南供应商", count: 2 }],
      },
    ]);
  });

  test("maps rules, relation detail, object detail, candidates, attach-existing, and export endpoints", async () => {
    expect(api().fetchPendingInvoiceRules).toBeTypeOf("function");
    expect(api().savePendingInvoiceRules).toBeTypeOf("function");
    expect(api().fetchPendingInvoiceRelationDetail).toBeTypeOf("function");
    expect(api().fetchPendingInvoiceObjectDetail).toBeTypeOf("function");
    expect(api().fetchPendingInvoiceCandidates).toBeTypeOf("function");
    expect(api().previewAttachExistingInvoice).toBeTypeOf("function");
    expect(api().confirmAttachExistingInvoice).toBeTypeOf("function");
    expect(api().fetchPendingInvoiceExportPreview).toBeTypeOf("function");
    expect(api().downloadPendingInvoiceExport).toBeTypeOf("function");

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.pathname === "/api/pending-invoices/rules" && method === "GET") {
        return new Response(JSON.stringify({
          version: 3,
          permissions: { can_save: true },
          available_tags: [
            { code: "fee", label: "手续费", status: "active", output_primary_label: "费用", output_sub_label: "手续费" },
            { code: "internal_transfer", label: "内部往来款", status: "active", output_primary_label: "内部往来款", output_sub_label: "" },
            { code: "salary", label: "工资", status: "active", output_primary_label: "薪酬", output_sub_label: "工资" },
          ],
          bank_transaction_tags: {
            version: 3,
            tags: [
              { code: "fee", label: "手续费", status: "active", output_primary_label: "费用", output_sub_label: "手续费" },
              { code: "internal_transfer", label: "内部转账", status: "active", output_primary_label: "往来", output_sub_label: "内部转账" },
              { code: "salary", label: "工资", status: "active", output_primary_label: "薪酬", output_sub_label: "工资" },
              { code: "borrow_in_company_repaid", label: "公司暂借款：已还款", status: "active", output_primary_label: "公司暂借款：已还款", output_sub_label: "" },
              { code: "inactive_tag", label: "停用", status: "inactive", output_primary_label: "停用", output_sub_label: "" },
              { code: "archived_tag", label: "归档", status: "archived", output_primary_label: "归档", output_sub_label: "" },
            ],
          },
          groups: {
            requires_invoice: {
              tag_codes: ["fee"],
              tags: [{ code: "fee", label: "手续费", status: "active", output_primary_label: "费用", output_sub_label: "手续费" }],
            },
            bank_statement_as_invoice: {
              tag_codes: ["internal_transfer"],
              tags: [{ code: "internal_transfer", label: "内部转账", status: "active", output_primary_label: "往来", output_sub_label: "内部转账" }],
            },
            no_invoice_required: {
              tag_codes: ["salary"],
              tags: [{ code: "salary", label: "工资", status: "active", output_primary_label: "薪酬", output_sub_label: "工资" }],
            },
          },
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/pending-invoices/rules" && method === "PUT") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        expect(body).toEqual({
          groups: {
            bank_statement_as_invoice: { tag_codes: ["internal_transfer"] },
            no_invoice_required: { tag_codes: ["salary"] },
          },
        });
        return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/pending-invoices/rows/txn_001/relation-detail") {
        return new Response(JSON.stringify({
          transaction_summary: { id: "txn_001", counterparty_name: "云南供应商", trade_time: "2026-05-02", debit_amount: "1200.00" },
          related_invoices: [{ id: "inv_001", digital_invoice_no: "DIG-001", seller_name: "云南供应商", total_with_tax: "2000.00" }],
          payment_rows: [{ id: "txn_001", trade_time: "2026-05-02", debit_amount: "1200.00", relation_case_id: "case_001" }],
          paid_total: "1200.00",
          invoice_total: "2000.00",
          remaining_amount: "800.00",
          difference_amount: "-800.00",
          available_actions: ["attach_existing_invoice"],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/pending-invoices/invoices/inv_001/detail") {
        return new Response(JSON.stringify({
          title: "DIG-001",
          detail_available: true,
          sections: [{ title: "发票字段", fields: [{ label: "销方", value: "云南供应商" }] }],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/pending-invoices/oa/oa_001/detail") {
        return new Response(JSON.stringify({
          title: "打印选择",
          subtitle: "支付申请",
          detail_available: true,
          oa_print_layout: {
            form_title: "支付申请",
            download_label: "打印下载",
            fields: [{ label: "申请人", value: "杨丽萍" }],
            approvals: [{ title: "项目负责人审核", lines: ["同意"], signature: "刘涵静" }],
          },
          sections: [],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/pending-invoices/invoice-candidates") {
        expect(url.searchParams.get("transaction_id")).toBe("txn_001");
        expect(url.searchParams.get("sort_field")).toBe("amount_difference_abs");
        return new Response(JSON.stringify({
          rows: [{
            invoice_id: "inv_001",
            digital_invoice_no: "DIG-001",
            seller_name: "云南供应商",
            total_with_tax: "1200.00",
            related_paid_total: "0.00",
            remaining_amount: "1200.00",
            amount_difference_abs: "0.00",
            candidate_status: "available",
          }],
          pagination: { page: 1, page_size: 20, total: 1 },
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/pending-invoices/rows/txn_001/attach-existing-invoice/preview") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        expect(body).toMatchObject({ invoice_id: "inv_001", request_id: "preview-request" });
        return new Response(JSON.stringify({
          preview_id: "attach_preview_001",
          request_key: "pending_invoice_attach_existing:txn_001:inv_001",
          can_confirm: true,
          transaction_summary: { id: "txn_001", counterparty_name: "云南供应商", trade_time: "2026-05-02", debit_amount: "1200.00" },
          invoice_summary: { id: "inv_001", digital_invoice_no: "DIG-001", issue_date: "2026-05-03", seller_name: "云南供应商", seller_tax_no: "9153", total_with_tax: "1200.00" },
          payment_impact: { paid_total_before: "0.00", paid_total_after: "1200.00", invoice_total: "1200.00", remaining_amount_after: "0.00", difference_amount_after: "0.00" },
          affected_months: ["2026-05"],
          warnings: [],
          conflicts: [],
          expires_at: "2026-05-25T10:10:00+08:00",
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/pending-invoices/rows/txn_001/attach-existing-invoice") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        expect(body).toMatchObject({ preview_id: "attach_preview_001", invoice_id: "inv_001", request_id: "confirm-request" });
        return new Response(JSON.stringify({
          status: "completed",
          request_id: "confirm-request",
          request_key: "pending_invoice_attach_existing:txn_001:inv_001",
          transaction_id: "txn_001",
          invoice_id: "inv_001",
          relation_case_id: "case_001",
          relation_mode: "pending_invoice_attach_existing_invoice",
          affected_transaction_ids: ["txn_001"],
          affected_invoice_ids: ["inv_001"],
          affected_months: ["2026-05"],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/pending-invoices/export-preview") {
        expect(url.searchParams.get("page")).toBeNull();
        return new Response(JSON.stringify({
          file_name: "pending-invoices.xlsx",
          row_count: 128,
          scope_label: "当前筛选",
          columns: ["对方户名", "发票状态"],
          sample_rows: [{ counterparty_name: "云南供应商", status_label: "已支付待开票" }],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/pending-invoices/export") {
        expect(url.searchParams.get("page")).toBeNull();
        return new Response(new Blob(["xlsx"], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }), {
          status: 200,
          headers: {
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Content-Disposition": "attachment; filename*=UTF-8''pending-invoices.xlsx",
          },
        });
      }
      throw new Error(`Unhandled request ${method} ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const rules = await api().fetchPendingInvoiceRules();
    expect(rules.groups.requiresInvoice.tags[0]).toMatchObject({
      code: "fee",
      label: "手续费",
      outputPrimaryLabel: "费用",
      outputSubLabel: "手续费",
    });
    expect(rules.availableTags.map((tag) => tag.code)).toEqual(["fee", "internal_transfer", "salary"]);
    expect(rules.availableTags.some((tag) => tag.code === "borrow_in_company_repaid")).toBe(false);
    await api().savePendingInvoiceRules(rules);

    const relation = await api().fetchPendingInvoiceRelationDetail("txn_001");
    expect(relation).toMatchObject({
      paidTotal: "1200.00",
      invoiceTotal: "2000.00",
      availableActions: ["attach_existing_invoice"],
    });

    const detail = await api().fetchPendingInvoiceObjectDetail({ kind: "invoice", id: "inv_001", rowId: "txn_001" });
    expect(detail).toMatchObject({ title: "DIG-001", sections: [{ title: "发票字段" }] });
    const oaDetail = await api().fetchPendingInvoiceObjectDetail({ kind: "oa", id: "oa_001", rowId: "txn_001" });
    expect(oaDetail.oaPrintLayout).toMatchObject({
      formTitle: "支付申请",
      fields: [{ label: "申请人", value: "杨丽萍" }],
      approvals: [{ title: "项目负责人审核", signature: "刘涵静" }],
    });

    const candidates = await api().fetchPendingInvoiceCandidates({
      transactionId: "txn_001",
      sortField: "amount_difference_abs",
      sortDirection: "asc",
      page: 1,
      pageSize: 20,
    });
    expect(candidates).toMatchObject({ rows: [{ invoiceId: "inv_001", candidateStatus: "available" }] });

    const preview = await api().previewAttachExistingInvoice({ transactionId: "txn_001", invoiceId: "inv_001", requestId: "preview-request" });
    expect(preview).toMatchObject({ previewId: "attach_preview_001", paymentImpact: { remainingAmountAfter: "0.00" } });
    const confirm = await api().confirmAttachExistingInvoice({
      transactionId: "txn_001",
      invoiceId: "inv_001",
      previewId: "attach_preview_001",
      requestId: "confirm-request",
    });
    expect(confirm).toMatchObject({ status: "completed", relationCaseId: "case_001", affectedMonths: ["2026-05"] });

    const exportPreview = await api().fetchPendingInvoiceExportPreview({
      direction: "expense",
      filter: "requires_invoice",
      page: 7,
      pageSize: 25,
      sortField: "trade_date",
      sortDirection: "desc",
    });
    expect(exportPreview).toMatchObject({ fileName: "pending-invoices.xlsx", rowCount: 128, sampleRows: [{ counterpartyName: "云南供应商" }] });

    const downloaded = await api().downloadPendingInvoiceExport({ direction: "expense", filter: "requires_invoice", page: 7, pageSize: 25 });
    expect(downloaded.fileName).toBe("pending-invoices.xlsx");
    expect(downloaded.blob).toBeInstanceOf(Blob);
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
        row: {
          id: "txn_001",
          bank_transaction: { id: "txn_001" },
          invoice_acquisition_status: { code: "paid_invoiced", label: "已支付已开票", primary_action: "view_relation" },
          available_actions: ["view_relation"],
        },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const request: ManualPendingInvoiceRequest = {
      requestId: "request-001",
      bankTransactionId: "txn_001",
      invoiceNo: "INV-001",
      issueDate: "2026-05-03",
      totalWithTax: "1200.00",
      sellerName: "云南供应商有限公司",
      buyerName: "云南溯源科技有限公司",
    };

    const preview = await pendingInvoicesApi.previewManualPendingInvoice(request);
    const result = await pendingInvoicesApi.confirmManualPendingInvoice({ ...request, previewId: preview.previewId });

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
            {
              code: "fee",
              label: "手续费",
              path: ["自动识别", "手续费"],
              output_primary_label: "费用",
              output_sub_label: "手续费",
              status: "active",
              source: "system",
            },
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
        {
          code: "fee",
          label: "手续费",
          path: ["自动识别", "手续费"],
          outputPrimaryLabel: "费用",
          outputSubLabel: "手续费",
          status: "active",
          source: "system",
        },
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
