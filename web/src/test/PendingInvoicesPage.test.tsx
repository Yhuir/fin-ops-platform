import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

function upgradedRows() {
  return [
    {
      id: "txn-paid-pending",
      bank_transaction: {
        id: "txn-paid-pending",
        counterparty_name: "云南开票供应商",
        counterparty_account_no: "6222000011112222",
        counterparty_bank_name: "工行昆明分行",
        trade_time: "2026-05-02 10:00:00",
        booked_date: "2026-05-02",
        debit_amount: "1200.00",
        credit_amount: "0.00",
        balance: "9800.00",
        currency: "人民币元",
        bank_name: "工商银行",
        account_name: "云南溯源科技有限公司",
        account_last4: "6386",
        summary: "电子转账",
        remark: "维护费",
        statement_serial_no: "stmt-paid-pending",
        enterprise_serial_no: "ent-paid-pending",
        voucher_type: "电子凭证",
        voucher_no: "v-paid-pending",
      },
      invoice_acquisition_status: {
        code: "paid_pending_invoice",
        label: "已支付待开票",
        reason: "未命中免票规则，且未发现进项发票关系",
        severity: "warning",
        primary_action: "attach_or_create_invoice",
        matched_rule: { source: "pending_invoice_tag_groups", group: "requires_invoice", tag_code: "fee", tag_label: "手续费" },
      },
      input_invoices: { primary: null, relation_count: 0, has_multiple: false, summaries: [], payment_summary: null },
      oa: {
        primary: { id: "oa-paid-pending", applicant: "张三", application_type: "支付", project_name: "维护项目", status: "进行中" },
        relation_count: 1,
        has_multiple: false,
        detail_available: true,
        summaries: [],
      },
    },
    {
      id: "txn-invoice-not-paid",
      bank_transaction: {
        id: "txn-invoice-not-paid",
        counterparty_name: "分期供应商",
        counterparty_account_no: "6222000033334444",
        counterparty_bank_name: "建行昆明分行",
        trade_time: "2026-05-03 09:00:00",
        booked_date: "2026-05-03",
        debit_amount: "1200.00",
        credit_amount: "0.00",
        balance: "8600.00",
        currency: "人民币元",
        bank_name: "建设银行",
        account_name: "云南溯源科技有限公司",
        account_last4: "8826",
        summary: "合同付款",
        remark: "第一期",
        statement_serial_no: "stmt-not-paid",
        enterprise_serial_no: "ent-not-paid",
        voucher_type: "电子凭证",
        voucher_no: "v-not-paid",
      },
      invoice_acquisition_status: {
        code: "invoice_not_fully_paid",
        label: "未支付完已开票",
        reason: "发票价税合计大于已付合计",
        severity: "warning",
        primary_action: "view_payment_detail",
        matched_rule: null,
      },
      input_invoices: {
        primary: {
          id: "inv-001",
          digital_invoice_no: "DIG-001",
          invoice_no: "INV-001",
          invoice_code: "CODE-001",
          issue_date: "2026-05-04",
          seller_name: "分期供应商",
          seller_tax_no: "915300001111",
          total_with_tax: "2000.00",
        },
        relation_count: 2,
        has_multiple: true,
        summaries: [
          { id: "inv-001", digital_invoice_no: "DIG-001", issue_date: "2026-05-04", seller_name: "分期供应商", seller_tax_no: "915300001111", total_with_tax: "2000.00" },
          { id: "inv-002", digital_invoice_no: "DIG-002", issue_date: "2026-05-05", seller_name: "分期供应商二号", seller_tax_no: "915300002222", total_with_tax: "800.00" },
        ],
        payment_summary: { paid_total: "1200.00", invoice_total: "2000.00", remaining_amount: "800.00", difference_amount: "-800.00" },
      },
      oa: {
        primary: { id: "oa-001", applicant: "李四", application_type: "支付", project_name: "建设项目", status: "进行中" },
        relation_count: 2,
        has_multiple: true,
        detail_available: true,
        summaries: [
          { id: "oa-001", applicant: "李四", application_type: "支付", project_name: "建设项目", status: "进行中" },
          { id: "oa-002", applicant: "王五", application_type: "报销", project_name: "建设项目二期", status: "已完成" },
        ],
      },
    },
    {
      id: "txn-no-required",
      bank_transaction: {
        id: "txn-no-required",
        counterparty_name: "无需发票供应商",
        trade_time: "2026-05-04 11:00:00",
        booked_date: "2026-05-04",
        debit_amount: "300.00",
        credit_amount: "0.00",
        balance: "8300.00",
        currency: "人民币元",
        bank_name: "工商银行",
        account_name: "云南溯源科技有限公司",
        account_last4: "6386",
        summary: "工资代发",
        remark: "无需开票",
        statement_serial_no: "stmt-no-required",
        enterprise_serial_no: "ent-no-required",
        voucher_type: "电子凭证",
        voucher_no: "v-no-required",
      },
      invoice_acquisition_status: {
        code: "no_invoice_required",
        label: "无需开票",
        reason: "命中无需开票规则：工资",
        severity: "success",
        primary_action: "view_rules",
        matched_rule: { source: "pending_invoice_tag_groups", group: "no_invoice_required", tag_code: "salary", tag_label: "工资" },
      },
      input_invoices: { primary: null, relation_count: 0, has_multiple: false, summaries: [], payment_summary: null },
      oa: { primary: null, relation_count: 0, has_multiple: false, detail_available: false, summaries: [] },
    },
  ];
}

function installPendingInvoiceFetch() {
  const baseFetch = installMockApiFetch();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.pathname === "/api/pending-invoices/rows") {
      const rows = upgradedRows();
      return new Response(JSON.stringify({
        direction: "expense",
        filter: url.searchParams.get("filter") ?? "all",
        rows,
        pagination: { page: Number(url.searchParams.get("page") ?? 1), page_size: 50, total: rows.length },
        summary: { total_rows: rows.length, missing_invoice_rows: 2, create_invoice_available_rows: 1 },
        read_model_status: "fresh",
        tag_dictionary: { version: 1, tags: [] },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/rules" && method === "GET") {
      return new Response(JSON.stringify({
        version: 7,
        permissions: { can_save: true },
        groups: {
          requires_invoice: { tag_codes: ["fee"], tags: [{ code: "fee", label: "手续费", status: "active" }] },
          bank_statement_as_invoice: { tag_codes: ["internal_transfer"], tags: [{ code: "internal_transfer", label: "内部转账", status: "active" }] },
          no_invoice_required: { tag_codes: ["salary"], tags: [{ code: "salary", label: "工资", status: "active" }] },
        },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/rules" && method === "PUT") {
      return new Response(JSON.stringify({
        version: 8,
        permissions: { can_save: true },
        groups: {
          requires_invoice: { tag_codes: ["fee"], tags: [{ code: "fee", label: "手续费", status: "active" }] },
          bank_statement_as_invoice: { tag_codes: ["internal_transfer"], tags: [{ code: "internal_transfer", label: "内部转账", status: "active" }] },
          no_invoice_required: { tag_codes: ["salary"], tags: [{ code: "salary", label: "工资", status: "active" }] },
        },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/rows/txn-invoice-not-paid/relation-detail") {
      return new Response(JSON.stringify({
        transaction_summary: { id: "txn-invoice-not-paid", counterparty_name: "分期供应商", trade_time: "2026-05-03", debit_amount: "1200.00" },
        related_invoices: [{ id: "inv-001", digital_invoice_no: "DIG-001", seller_name: "分期供应商", total_with_tax: "2000.00" }],
        payment_rows: [
          { id: "txn-invoice-not-paid", trade_time: "2026-05-03", counterparty_name: "分期供应商", debit_amount: "1200.00", relation_case_id: "case-001" },
          { id: "txn-old-payment", trade_time: "2026-04-20", counterparty_name: "分期供应商", debit_amount: "300.00", relation_case_id: "case-old" },
        ],
        paid_total: "1500.00",
        invoice_total: "2000.00",
        remaining_amount: "500.00",
        difference_amount: "-500.00",
        available_actions: ["attach_existing_invoice"],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/invoices/inv-001/detail") {
      return new Response(JSON.stringify({
        title: "DIG-001",
        subtitle: "分期供应商",
        detail_available: true,
        sections: [{ title: "发票字段", fields: [{ label: "销方", value: "分期供应商" }, { label: "发票代码", value: "CODE-001" }] }],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/invoice-candidates") {
      return new Response(JSON.stringify({
        rows: [{
          invoice_id: "inv-candidate",
          digital_invoice_no: "DIG-CAND-001",
          invoice_no: "INV-CAND-001",
          issue_date: "2026-05-06",
          seller_name: "云南开票供应商",
          seller_tax_no: "915300009999",
          total_with_tax: "1200.00",
          related_paid_total: "0.00",
          remaining_amount: "1200.00",
          amount_difference_abs: "0.00",
          candidate_status: "available",
        }],
        pagination: { page: 1, page_size: 20, total: 1 },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/rows/txn-paid-pending/attach-existing-invoice/preview") {
      return new Response(JSON.stringify({
        preview_id: "attach-preview-001",
        request_key: "pending_invoice_attach_existing:txn-paid-pending:inv-candidate",
        can_confirm: true,
        transaction_summary: { id: "txn-paid-pending", counterparty_name: "云南开票供应商", trade_time: "2026-05-02", debit_amount: "1200.00" },
        invoice_summary: { id: "inv-candidate", digital_invoice_no: "DIG-CAND-001", issue_date: "2026-05-06", seller_name: "云南开票供应商", seller_tax_no: "915300009999", total_with_tax: "1200.00" },
        payment_impact: { paid_total_before: "0.00", paid_total_after: "1200.00", invoice_total: "1200.00", remaining_amount_after: "0.00", difference_amount_after: "0.00" },
        affected_months: ["2026-05"],
        warnings: [],
        conflicts: [],
        expires_at: "2026-05-25T10:10:00+08:00",
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/rows/txn-paid-pending/attach-existing-invoice") {
      return new Response(JSON.stringify({
        status: "completed",
        request_id: "attach-confirm",
        request_key: "pending_invoice_attach_existing:txn-paid-pending:inv-candidate",
        transaction_id: "txn-paid-pending",
        invoice_id: "inv-candidate",
        relation_case_id: "case-candidate",
        relation_mode: "pending_invoice_attach_existing_invoice",
        affected_transaction_ids: ["txn-paid-pending"],
        affected_invoice_ids: ["inv-candidate"],
        affected_months: ["2026-05"],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/export-preview") {
      return new Response(JSON.stringify({
        file_name: "pending-invoices.xlsx",
        row_count: 128,
        scope_label: "当前筛选和排序",
        columns: ["对方户名", "状态"],
        sample_rows: [{ counterparty_name: "云南开票供应商", status_label: "已支付待开票" }],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/export") {
      return new Response(new Blob(["xlsx"], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }), {
        status: 200,
        headers: {
          "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "Content-Disposition": "attachment; filename*=UTF-8''pending-invoices.xlsx",
        },
      });
    }
    if (url.pathname === "/api/pending-invoices/manual-invoices/preview") {
      return new Response(JSON.stringify({
        preview_id: "preview-001",
        request_key: "manual-key",
        can_confirm: true,
        target_invoice_type: "input",
        bank_transaction_summary: { id: "txn-paid-pending", direction: "expense", counterparty_name: "云南开票供应商", trade_time: "2026-05-02", amount: "1200.00" },
        invoice_identity: { source_unique_key: "source-key", data_fingerprint: "fingerprint" },
        duplicate_check: { status: "clear", matched_invoice_id: null, message: "未发现重复发票" },
        relation_impact: { relation_mode: "pending_invoice_manual_invoice", affected_months: ["2026-05"] },
        warnings: [],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/manual-invoices") {
      return new Response(JSON.stringify({
        invoice_id: "inv-created",
        relation_case_id: "case-created",
        affected_transaction_ids: ["txn-paid-pending"],
        affected_invoice_ids: ["inv-created"],
        affected_months: ["2026-05"],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return baseFetch(input, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function pendingInvoiceRowsRequests(fetchMock: ReturnType<typeof installPendingInvoiceFetch>) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === "/api/pending-invoices/rows");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Pending invoices page", () => {
  test("renders upgraded four-zone MUI table without DataGrid and summarizes multiple relations", async () => {
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    expect(await screen.findByRole("link", { name: "待找发票" })).toHaveAttribute("href", "/pending-invoices");
    const page = await screen.findByTestId("pending-invoices-page");
    expect(within(page).queryByRole("grid")).not.toBeInTheDocument();
    expect(within(page).getByRole("table", { name: "待找发票四区表" })).toBeInTheDocument();
    expect(within(page).getByTestId("pending-invoices-table-shell")).toHaveStyle({ overflowX: "hidden" });

    expect(within(page).getByRole("columnheader", { name: "支出流水" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "发票获取状态" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "进项发票" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "OA" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "对方 / 时间" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "金额 / 银行账户" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "摘要 / 凭证" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "状态 / 依据 / 主操作" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "发票号码 / 开票日期" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "销方 / 识别号" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "金额 / 支付差额" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "申请人 / 类型" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "项目 / 详情" })).toBeInTheDocument();

    expect(await within(page).findByText("云南开票供应商")).toBeInTheDocument();
    expect(within(page).getByText("已支付待开票")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /云南开票供应商 选择发票/ })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /云南开票供应商 补票/ })).toBeInTheDocument();
    expect(within(page).getByText("DIG-001")).toBeInTheDocument();
    expect(within(page).getAllByText("+1").length).toBeGreaterThanOrEqual(2);
    expect(within(page).getByText("已付 1,200.00")).toBeInTheDocument();
    expect(within(page).getByText("待付 800.00")).toBeInTheDocument();

    const request = pendingInvoiceRowsRequests(fetchMock)[0];
    expect(request.searchParams.get("direction")).toBe("expense");
    expect(request.searchParams.get("sort_field")).toBe("trade_date");
    expect(request.searchParams.get("sort_direction")).toBe("desc");
  });

  test("opens relation, object detail, rules, and export drawers with loading callbacks", async () => {
    const user = userEvent.setup();
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await screen.findByTestId("pending-invoices-page");
    const relationRow = await within(page).findByRole("row", { name: /分期供应商/ });
    await user.click(within(relationRow).getByRole("button", { name: /分期供应商 查看支付明细/ }));
    expect(await screen.findByText("关系与支付明细")).toBeInTheDocument();
    expect(await screen.findByText("已付合计")).toBeInTheDocument();
    expect(screen.getByText("1,500.00")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭关系明细抽屉" }));

    await user.click(within(relationRow).getByRole("button", { name: /发票详情 DIG-001/ }));
    expect(await screen.findByRole("heading", { name: "DIG-001" })).toBeInTheDocument();
    expect(screen.getByText("发票字段")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "待找发票规则设置" }));
    expect(await screen.findByRole("heading", { name: "待找发票规则设置" })).toBeInTheDocument();
    expect(screen.getByText("需要开票")).toBeInTheDocument();
    expect(screen.getByText("手续费")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存规则" }));
    await waitFor(() => {
      const rulesPut = fetchMock.mock.calls.some(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/pending-invoices/rules" && (init?.method ?? "GET").toUpperCase() === "PUT";
      });
      expect(rulesPut).toBe(true);
    });
    await user.click(screen.getByRole("button", { name: "关闭规则抽屉" }));

    await user.click(within(page).getByRole("button", { name: "筛选内容导出" }));
    expect(await screen.findByRole("heading", { name: "导出预览" })).toBeInTheDocument();
    expect(screen.getByText("预计导出 128 行")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "下载导出" }));
    expect(await screen.findByText("已生成 pending-invoices.xlsx")).toBeInTheDocument();
  });

  test("opens invoice picker from status column, previews attach-existing, confirms, and refetches rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await screen.findByTestId("pending-invoices-page");
    const initialRequests = pendingInvoiceRowsRequests(fetchMock).length;
    const pendingRow = await within(page).findByRole("row", { name: /云南开票供应商/ });
    await user.click(within(pendingRow).getByRole("button", { name: /云南开票供应商 选择发票/ }));

    expect(await screen.findByRole("heading", { name: "选择已有进项发票" })).toBeInTheDocument();
    expect(await screen.findByText("DIG-CAND-001")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /预览关联 DIG-CAND-001/ }));
    expect(await screen.findByText(/pending_invoice_attach_existing/)).toBeInTheDocument();
    expect(screen.getByText("关联后待付 0.00")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认建立关系" }));

    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname);
      expect(paths).toContain("/api/pending-invoices/rows/txn-paid-pending/attach-existing-invoice/preview");
      expect(paths).toContain("/api/pending-invoices/rows/txn-paid-pending/attach-existing-invoice");
      expect(pendingInvoiceRowsRequests(fetchMock).length).toBeGreaterThan(initialRequests);
    });
  });

  test("manual invoice action still previews before confirm", async () => {
    const user = userEvent.setup();
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await screen.findByTestId("pending-invoices-page");
    const pendingRow = await within(page).findByRole("row", { name: /云南开票供应商/ });
    await user.click(within(pendingRow).getByRole("button", { name: /云南开票供应商 补票/ }));
    const dialog = await screen.findByRole("dialog", { name: "手工补录发票" });
    await user.type(within(dialog).getByLabelText("发票号码"), "INV-MANUAL");
    await user.type(within(dialog).getByLabelText("开票日期"), "2026-05-06");
    await user.type(within(dialog).getByLabelText("价税合计"), "1200.00");
    await user.type(within(dialog).getByLabelText("销方名称"), "手工销方");
    await user.type(within(dialog).getByLabelText("购方名称"), "云南溯源科技");
    await user.click(within(dialog).getByRole("button", { name: "预览" }));

    expect(await within(dialog).findByText(/manual-key/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "确认写入" }));

    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname);
      expect(paths).toContain("/api/pending-invoices/manual-invoices/preview");
      expect(paths).toContain("/api/pending-invoices/manual-invoices");
    });
  });

  test("refetches rows when bank detail tag settings update", async () => {
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    expect(await screen.findByText("云南开票供应商")).toBeInTheDocument();
    const initialRequests = pendingInvoiceRowsRequests(fetchMock).length;

    act(() => {
      window.dispatchEvent(new CustomEvent("finops:bank-transaction-tags-updated", { detail: { version: 2 } }));
    });

    await waitFor(() => {
      expect(pendingInvoiceRowsRequests(fetchMock).length).toBeGreaterThan(initialRequests);
    });
  });

  test("refetches rows on focus as bank detail tag update fallback", async () => {
    vi.stubGlobal("BroadcastChannel", undefined);
    const localStorageStore = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: vi.fn((key: string) => localStorageStore.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => {
        localStorageStore.set(key, value);
      }),
      removeItem: vi.fn((key: string) => {
        localStorageStore.delete(key);
      }),
      clear: vi.fn(() => {
        localStorageStore.clear();
      }),
    });
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    expect(await screen.findByText("云南开票供应商")).toBeInTheDocument();
    const initialRequests = pendingInvoiceRowsRequests(fetchMock).length;

    window.localStorage.setItem("finops.bankTransactionTags.version", "2");
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });

    await waitFor(() => {
      expect(pendingInvoiceRowsRequests(fetchMock).length).toBeGreaterThan(initialRequests);
    });
  });
});
