import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchBankDetailTransactions } from "../features/bankDetails/api";
import * as pendingInvoicesApi from "../features/pendingInvoices/api";
import { fetchWorkbenchSettings, saveWorkbenchSettings } from "../features/workbench/api";
import type {
  AttachExistingInvoiceConfirmRequest,
  AttachExistingInvoicePreviewRequest,
  AttachExistingInvoicesConfirmRequest,
  AttachExistingInvoicesPreviewRequest,
  FetchPendingInvoiceBatchCandidatesRequest,
  FetchPendingInvoiceCandidatesRequest,
  FetchPendingInvoiceRowsRequest,
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
    fetchPendingInvoiceRelationDetail: (transactionId: string, direction?: string, kind?: string) => Promise<unknown>;
    fetchPendingInvoiceObjectDetail: (target: PendingInvoiceObjectDetailTarget) => Promise<unknown>;
    fetchPendingInvoiceCandidates: (request: FetchPendingInvoiceCandidatesRequest) => Promise<unknown>;
    fetchPendingInvoiceCandidatesBatch: (request: FetchPendingInvoiceBatchCandidatesRequest) => Promise<unknown>;
    previewAttachExistingInvoice: (request: AttachExistingInvoicePreviewRequest) => Promise<unknown>;
    confirmAttachExistingInvoice: (request: AttachExistingInvoiceConfirmRequest) => Promise<unknown>;
    previewAttachExistingInvoices: (request: AttachExistingInvoicesPreviewRequest) => Promise<unknown>;
    confirmAttachExistingInvoices: (request: AttachExistingInvoicesConfirmRequest) => Promise<unknown>;
    fetchPendingInvoiceExportPreview: (request: FetchPendingInvoiceRowsRequest) => Promise<unknown>;
    downloadPendingInvoiceExport: (request: FetchPendingInvoiceRowsRequest) => Promise<{ blob: Blob; fileName: string }>;
    savePendingInvoiceIncomeStatuses: typeof pendingInvoicesApi.savePendingInvoiceIncomeStatuses;
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
          bank_transactions: {
            primary: null,
            relation_count: 2,
            linked_relation_count: 2,
            has_multiple: true,
            detail_mode: "list",
            summaries: [
              {
                id: "txn_001",
                counterparty_name: "云南供应商有限公司",
                trade_time: "2026-05-02T10:00:00+08:00",
                amount: "1200.00",
                debit_amount: "1200.00",
                bank_short_name: "工行",
                account_last4: "6386",
                summary: "电子转账",
                relation_case_id: "case_001",
                relation_status: "linked",
              },
              {
                id: "txn_002",
                counterparty_name: "云南供应商二号",
                trade_time: "2026-05-02T11:00:00+08:00",
                amount: "800.00",
                debit_amount: "800.00",
                bank_short_name: "建行",
                account_last4: "8106",
                summary: "电子转账",
                relation_case_id: "case_001",
                relation_status: "linked",
              },
            ],
            payment_summary: { paid_total: "2000.00" },
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
              relation_status: "linked",
            },
            relation_count: 2,
            linked_relation_count: 1,
            has_multiple: true,
            summaries: [
              { id: "inv_001", digital_invoice_no: "DIG-001", issue_date: "2026-05-03", seller_name: "云南供应商有限公司", seller_tax_no: "915300001111", total_with_tax: "2000.00", relation_status: "linked" },
              { id: "inv_002", digital_invoice_no: "DIG-002", issue_date: "2026-05-04", seller_name: "云南供应商二号", seller_tax_no: "915300002222", total_with_tax: "800.00", relation_status: "candidate" },
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
              id: "oa-001",
              applicant: "张三",
              application_type: "支付",
              project_name: "维护项目",
              status: "进行中",
              form_no: "2048",
              detail_available: true,
              relation_case_id: "candidate:api-oa-bank",
              relation_status: "candidate",
            },
            relation_count: 2,
            has_multiple: true,
            detail_available: true,
            summaries: [
              { id: "oa-001", applicant: "张三", application_type: "支付", project_name: "维护项目", status: "进行中", form_no: "2048", detail_available: true, relation_case_id: "candidate:api-oa-bank", relation_status: "candidate" },
              { id: "oa-002", applicant: "李四", application_type: "报销", project_name: "维护项目二期", status: "已完成", form_no: "2050", detail_available: true, relation_case_id: "candidate:api-oa-bank-2" },
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
      bankTransactions: {
        relationCount: 2,
        linkedRelationCount: 2,
        hasMultiple: true,
        detailMode: "list",
        paymentSummary: { paidTotal: "2000.00" },
      },
      invoiceAcquisitionStatus: {
        code: "invoice_not_fully_paid",
        label: "未支付完已开票",
        primaryAction: "view_payment_detail",
        matchedRule: { group: "requires_invoice", tagLabel: "手续费" },
      },
      inputInvoices: {
        relationCount: 2,
        linkedRelationCount: 1,
        hasMultiple: true,
        primary: { digitalInvoiceNo: "DIG-001", sellerTaxNo: "915300001111", relationStatus: "linked" },
        paymentSummary: { paidTotal: "1200.00", remainingAmount: "800.00" },
      },
      oa: {
        relationCount: 2,
        hasMultiple: true,
        detailAvailable: true,
        primary: { id: "oa-001", applicant: "张三", projectName: "维护项目", formNo: "2048", detailAvailable: true, relationCaseId: "candidate:api-oa-bank", relationStatus: "candidate" },
      },
    });
    expect(payload.rows[0].bankTransactions.summaries[1]).toMatchObject({
      id: "txn_002",
      counterpartyName: "云南供应商二号",
      relationStatus: "linked",
    });
    expect(payload.rows[0].inputInvoices.summaries[1]).toMatchObject({ id: "inv_002", relationStatus: "candidate" });
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
    expect(api().fetchPendingInvoiceCandidatesBatch).toBeTypeOf("function");
    expect(api().previewAttachExistingInvoice).toBeTypeOf("function");
    expect(api().confirmAttachExistingInvoice).toBeTypeOf("function");
    expect(api().previewAttachExistingInvoices).toBeTypeOf("function");
    expect(api().confirmAttachExistingInvoices).toBeTypeOf("function");
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
          version: 3,
          direction: "expense",
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
          related_invoices: [{ id: "inv_001", digital_invoice_no: "DIG-001", seller_name: "云南供应商", total_with_tax: "2000.00", relation_status: "candidate" }],
          related_oa: [
            { id: "oa_001", applicant: "杨丽萍", application_type: "支付申请", project_name: "云南溯源项目", relation_case_id: "case_001", detail_available: true, relation_status: "candidate" },
            { id: "oa_002", applicant: "刘晓宇", application_type: "日常报销", project_name: "云南溯源项目二期", relation_case_id: "case_002", detail_available: true },
          ],
          oa_summaries: [
            { id: "oa_001", applicant: "杨丽萍", application_type: "支付申请", project_name: "云南溯源项目", relation_case_id: "case_001", detail_available: true },
            { id: "oa_002", applicant: "刘晓宇", application_type: "日常报销", project_name: "云南溯源项目二期", relation_case_id: "case_002", detail_available: true },
          ],
          relation_case_ids: ["case_001", "case_002"],
          payment_rows: [{ id: "txn_001", trade_time: "2026-05-02", debit_amount: "1200.00", relation_case_id: "case_001", relation_status: "candidate" }],
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
            bank_relation_status: "unlinked",
            linked_bank_transaction_count: 0,
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
      relatedOa: [
        { id: "oa_001", applicant: "杨丽萍", applicationType: "支付申请", projectName: "云南溯源项目", relationStatus: "candidate" },
        { id: "oa_002", applicant: "刘晓宇", applicationType: "日常报销", projectName: "云南溯源项目二期" },
      ],
      relationCaseIds: ["case_001", "case_002"],
    });
    expect(relation.relatedInvoices[0]).toMatchObject({ id: "inv_001", relationStatus: "candidate" });
    expect(relation.paymentRows[0]).toMatchObject({ id: "txn_001", relationStatus: "candidate" });

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
    expect(candidates).toMatchObject({
      rows: [{
        invoiceId: "inv_001",
        candidateStatus: "available",
        bankRelationStatus: "unlinked",
        linkedBankTransactionCount: 0,
      }],
    });

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

  test("surfaces backend row-limit messages from failed export downloads", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      error: "pending_invoice_export_row_limit_exceeded",
      message: "待找发票导出超过 20000 行，请缩小筛选范围后重试。",
      details: { total: 20001, limit: 20000 },
    }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    })));

    await expect(api().downloadPendingInvoiceExport({
      direction: "expense",
      filter: "requires_invoice",
    })).rejects.toThrow("待找发票导出超过 20000 行，请缩小筛选范围后重试。");
  });

  test("maps batch candidate, preview, and confirm attach-existing invoice endpoints", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      const method = (init?.method ?? "GET").toUpperCase();
      const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
      if (url.pathname === "/api/pending-invoices/invoice-candidates/batch" && method === "POST") {
        expect(body).toMatchObject({
          transaction_ids: ["txn_001", "txn_002"],
          seller_name: "云南供应商",
          sort_field: "amount_difference_abs",
          sort_direction: "asc",
          page: 1,
          page_size: 20,
        });
        return new Response(JSON.stringify({
          transaction_ids: ["txn_001", "txn_002"],
          selection_summary: { transaction_count: 2, bank_total: "236.00" },
          rows: [
            {
              invoice_id: "inv_001",
              digital_invoice_no: "DIG-001",
              seller_name: "云南供应商",
              total_with_tax: "120.00",
              related_paid_total: "0.00",
              remaining_amount: "120.00",
              amount_difference_abs: "116.00",
              candidate_status: "available",
              bank_relation_status: "linked",
              linked_bank_transaction_count: 1,
            },
          ],
          pagination: { page: 1, page_size: 20, total: 1 },
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/pending-invoices/attach-existing-invoices/preview" && method === "POST") {
        expect(body).toMatchObject({
          transaction_ids: ["txn_001", "txn_002"],
          invoice_ids: ["inv_001", "inv_002"],
          request_id: "preview-batch",
        });
        return new Response(JSON.stringify({
          preview_id: "attach_batch_preview_001",
          request_key: "pending_invoice_attach_existing_batch:hash",
          can_confirm: true,
          transaction_summaries: [
            { id: "txn_001", counterparty_name: "云南供应商", trade_time: "2026-05-02", debit_amount: "120.00" },
            { id: "txn_002", counterparty_name: "云南供应商二号", trade_time: "2026-05-03", debit_amount: "116.00" },
          ],
          invoice_summaries: [
            { id: "inv_001", digital_invoice_no: "DIG-001", issue_date: "2026-05-04", seller_name: "云南供应商", total_with_tax: "120.00" },
            { id: "inv_002", digital_invoice_no: "DIG-002", issue_date: "2026-05-05", seller_name: "云南供应商二号", total_with_tax: "116.00" },
          ],
          selection_summary: {
            transaction_count: 2,
            invoice_count: 2,
            bank_total: "236.00",
            invoice_total: "236.00",
            difference_amount: "0.00",
          },
          payment_impact: {
            paid_total_before: "0.00",
            paid_total_after: "236.00",
            invoice_total: "236.00",
            remaining_amount_after: "0.00",
            difference_amount_after: "0.00",
          },
          affected_months: ["2026-05"],
          warnings: [],
          conflicts: [],
          expires_at: "2026-05-25T10:10:00+08:00",
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/pending-invoices/attach-existing-invoices" && method === "POST") {
        expect(body).toMatchObject({
          preview_id: "attach_batch_preview_001",
          transaction_ids: ["txn_001", "txn_002"],
          invoice_ids: ["inv_001", "inv_002"],
          request_id: "confirm-batch",
        });
        return new Response(JSON.stringify({
          status: "completed",
          request_id: "confirm-batch",
          request_key: "pending_invoice_attach_existing_batch:hash",
          transaction_ids: ["txn_001", "txn_002"],
          invoice_ids: ["inv_001", "inv_002"],
          relation_case_id: "case_batch",
          relation_mode: "pending_invoice_attach_existing_invoice",
          affected_transaction_ids: ["txn_001", "txn_002"],
          affected_invoice_ids: ["inv_001", "inv_002"],
          affected_months: ["2026-05"],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      throw new Error(`Unhandled request ${method} ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const candidates = await api().fetchPendingInvoiceCandidatesBatch({
      transactionIds: ["txn_001", "txn_002"],
      sellerName: "云南供应商",
      sortField: "amount_difference_abs",
      sortDirection: "asc",
      page: 1,
      pageSize: 20,
    });
    expect(candidates).toMatchObject({
      transactionIds: ["txn_001", "txn_002"],
      selectionSummary: { transactionCount: 2, bankTotal: "236.00" },
      rows: [{
        invoiceId: "inv_001",
        amountDifferenceAbs: "116.00",
        bankRelationStatus: "linked",
        linkedBankTransactionCount: 1,
      }],
      pagination: { page: 1, pageSize: 20, total: 1 },
    });

    const preview = await api().previewAttachExistingInvoices({
      transactionIds: ["txn_001", "txn_002"],
      invoiceIds: ["inv_001", "inv_002"],
      requestId: "preview-batch",
    });
    expect(preview).toMatchObject({
      previewId: "attach_batch_preview_001",
      transactionSummaries: [{ id: "txn_001" }, { id: "txn_002" }],
      invoiceSummaries: [{ id: "inv_001" }, { id: "inv_002" }],
      selectionSummary: { bankTotal: "236.00", invoiceTotal: "236.00", differenceAmount: "0.00" },
    });

    const confirm = await api().confirmAttachExistingInvoices({
      previewId: "attach_batch_preview_001",
      transactionIds: ["txn_001", "txn_002"],
      invoiceIds: ["inv_001", "inv_002"],
      requestId: "confirm-batch",
    });
    expect(confirm).toMatchObject({
      status: "completed",
      transactionIds: ["txn_001", "txn_002"],
      invoiceIds: ["inv_001", "inv_002"],
      relationCaseId: "case_batch",
      affectedTransactionIds: ["txn_001", "txn_002"],
      affectedInvoiceIds: ["inv_001", "inv_002"],
    });
  });

  test("maps attach-existing preview conflict objects into readable messages", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      preview_id: "attach_conflict_preview",
      request_key: "pending_invoice_attach_existing_batch:conflict",
      can_confirm: false,
      transaction_summaries: [],
      invoice_summaries: [],
      selection_summary: {
        transaction_count: 1,
        invoice_count: 1,
        bank_total: "100.00",
        invoice_total: "100.00",
        difference_amount: "0.00",
      },
      payment_impact: {
        paid_total_before: "0.00",
        paid_total_after: "100.00",
        invoice_total: "100.00",
        remaining_amount_after: "0.00",
        difference_amount_after: "0.00",
      },
      affected_months: ["2026-05"],
      warnings: ["关系状态已更新，请确认后再提交"],
      conflicts: [{
        relation_case_id: "case_conflict",
        relation_mode: "manual_confirmed",
        row_ids: ["claim_001", "inv_001"],
      }],
      expires_at: "2026-05-25T10:10:00+08:00",
    }), { status: 200, headers: { "Content-Type": "application/json" } })));

    const preview = await api().previewAttachExistingInvoices({
      transactionIds: ["txn_001"],
      invoiceIds: ["inv_001"],
      requestId: "preview-conflict",
    });

    expect(preview.canConfirm).toBe(false);
    expect(preview.conflicts).toEqual(["关系 case_conflict，模式 manual_confirmed，对象 claim_001, inv_001"]);
    expect(preview.warnings).toEqual(["关系状态已更新，请确认后再提交"]);
  });

  test("batch marks income invoice status with generated request id", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      expect(url.pathname).toBe("/api/pending-invoices/income-statuses");
      expect((init?.method ?? "GET").toUpperCase()).toBe("PUT");
      const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
      expect(body.transaction_ids).toEqual(["txn_income_001", "txn_income_002"]);
      expect(body.status_code).toBe("cash_income");
      expect(String(body.request_id)).toMatch(/^income-status-batch-cash_income-/);
      return new Response(JSON.stringify({
        status: "completed",
        request_id: body.request_id,
        request_key: "pending_invoice_income_status_batch:abc",
        transaction_ids: ["txn_income_001", "txn_income_002"],
        status_code: "cash_income",
        affected_transaction_ids: ["txn_income_001", "txn_income_002"],
        affected_invoice_ids: [],
        affected_months: ["2026-05"],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await pendingInvoicesApi.savePendingInvoiceIncomeStatuses(["txn_income_001", "txn_income_002"], "cash_income");

    expect(result).toMatchObject({
      status: "completed",
      requestKey: "pending_invoice_income_status_batch:abc",
      transactionIds: ["txn_income_001", "txn_income_002"],
      statusCode: "cash_income",
      affectedTransactionIds: ["txn_income_001", "txn_income_002"],
      affectedMonths: ["2026-05"],
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  test("maps settings tag dictionary and pending invoice tag groups both directions", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        expect(body).not.toHaveProperty("bank_transaction_tags");
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
        oa_import: {
          form_types: [],
          statuses: [],
          attachment_invoice_promotion_mode: "link_existing_only",
        },
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
      oaImport: {
        formTypes: [],
        statuses: [],
        attachmentInvoicePromotionMode: "link_existing_only",
      },
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
