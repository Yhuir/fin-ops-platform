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
        trade_time: "2026-04-19T10:52:02+08:00",
        booked_date: "2026-05-02",
        debit_amount: "1200.00",
        credit_amount: "0.00",
        balance: "9800.00",
        currency: "人民币元",
        bank_name: "建设银行",
        bank_short_name: "建行",
        account_name: "云南溯源科技有限公司",
        account_last4: "8106",
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
      can_create_invoice: true,
      available_actions: ["attach_existing_invoice", "manual_invoice"],
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
      can_create_invoice: false,
      available_actions: ["view_relation"],
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
      can_create_invoice: false,
      available_actions: ["view_rules"],
    },
  ];
}

type PendingInvoiceRulesMockOptions = {
  version?: number;
  feePrimaryLabel?: string;
  feeSubLabel?: string;
};

function pendingInvoiceRulesPayload({
  version = 7,
  feePrimaryLabel = "费用",
  feeSubLabel = "手续费",
}: PendingInvoiceRulesMockOptions = {}) {
  const feeTag = {
    code: "fee",
    label: feeSubLabel,
    status: "active",
    output_primary_label: feePrimaryLabel,
    output_sub_label: feeSubLabel,
  };
  const internalTransferTag = {
    code: "internal_transfer",
    label: "内部转账",
    status: "active",
    output_primary_label: "往来",
    output_sub_label: "内部转账",
  };
  const salaryTag = {
    code: "salary",
    label: "工资",
    status: "active",
    output_primary_label: "薪酬",
    output_sub_label: "工资",
  };
  const mealTag = {
    code: "custom_meal",
    label: "餐饮",
    status: "active",
    output_primary_label: "餐饮",
    output_sub_label: "",
  };
  return {
    version,
    permissions: { can_save: true },
    bank_transaction_tags: {
      version,
      tags: [feeTag, internalTransferTag, salaryTag, mealTag],
    },
    groups: {
      requires_invoice: {
        tag_codes: ["fee", "custom_meal"],
        tags: [feeTag, mealTag],
      },
      bank_statement_as_invoice: {
        tag_codes: ["internal_transfer"],
        tags: [internalTransferTag],
      },
      no_invoice_required: {
        tag_codes: ["salary"],
        tags: [salaryTag],
      },
    },
  };
}

function installPendingInvoiceFetch(options: {
  rulesPayload?: () => ReturnType<typeof pendingInvoiceRulesPayload>;
} = {}) {
  const baseFetch = installMockApiFetch();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.pathname === "/api/pending-invoices/rows") {
      const rows = upgradedRows();
      const direction = url.searchParams.get("direction") ?? "expense";
      return new Response(JSON.stringify({
        direction,
        filter: url.searchParams.get("filter") ?? "all",
        rows,
        pagination: { page: Number(url.searchParams.get("page") ?? 1), page_size: 50, total: rows.length },
        summary: {
          total_rows: rows.length,
          missing_invoice_rows: 2,
          create_invoice_available_rows: 1,
          source_summary: {
            bank_transaction_rows: 431,
            expense_rows: 356,
            income_rows: 75,
            current_direction_rows: direction === "income" ? 75 : 356,
            excluded_direction_rows: direction === "income" ? 356 : 75,
          },
        },
        read_model_status: "fresh",
        tag_dictionary: { version: 1, tags: [] },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/rules" && method === "GET") {
      return new Response(JSON.stringify((options.rulesPayload ?? pendingInvoiceRulesPayload)()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/pending-invoices/rules" && method === "PUT") {
      return new Response(JSON.stringify({
        version: 8,
        permissions: { can_save: true },
        bank_transaction_tags: {
          version: 8,
          tags: [
            { code: "fee", label: "手续费", status: "active", output_primary_label: "费用", output_sub_label: "手续费" },
            { code: "internal_transfer", label: "内部转账", status: "active", output_primary_label: "往来", output_sub_label: "内部转账" },
            { code: "salary", label: "工资", status: "active", output_primary_label: "薪酬", output_sub_label: "工资" },
            { code: "custom_meal", label: "餐饮", status: "active", output_primary_label: "餐饮", output_sub_label: "" },
          ],
        },
        groups: {
          requires_invoice: {
            tag_codes: ["fee", "custom_meal"],
            tags: [
              { code: "fee", label: "手续费", status: "active", output_primary_label: "费用", output_sub_label: "手续费" },
              { code: "custom_meal", label: "餐饮", status: "active", output_primary_label: "餐饮", output_sub_label: "" },
            ],
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
    if (url.pathname === "/api/pending-invoices/oa/oa-001/detail") {
      return new Response(JSON.stringify({
        title: "打印选择",
        subtitle: "支付申请",
        detail_available: true,
        oa_print_layout: {
          form_title: "支付申请",
          download_label: "打印下载",
          fields: [
            { label: "申请人", value: "李四" },
            { label: "申请日期", value: "2026-05-25" },
            { label: "申请类型", value: "设备贷款及材料费" },
            { label: "支付方式", value: "银行转账" },
            { label: "发票种类", value: "增值税专用发票" },
            { label: "项目名称", value: "建设项目" },
            { label: "金额", value: "¥ 7680.00元（大写：柒仟陆佰捌拾元整）" },
            { label: "收款方", value: "重庆维诺安工程技术有限公司" },
            { label: "开户行", value: "交通银行股份有限公司重庆人民路支行" },
            { label: "开户行账号", value: "500500037015003460594" },
            { label: "申请事由", value: "压力变送器尾款+底座、堵头4件" },
            { label: "电子签名", value: "李四" },
          ],
          approvals: [
            { title: "支付申请", lines: ["李四发起流程申请", "2026-05-25 11:20:27", "李四"], signature: "李四" },
            { title: "项目负责人审核", lines: ["同意", "2026-05-25 14:51:04", "刘涵静"], signature: "刘涵静" },
          ],
        },
        sections: [],
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

function pendingInvoiceRulesRequests(fetchMock: ReturnType<typeof installPendingInvoiceFetch>, method = "GET") {
  return fetchMock.mock.calls.filter(([input, init]) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    return url.pathname === "/api/pending-invoices/rules" && (init?.method ?? "GET").toUpperCase() === method;
  });
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
    expect(within(page).getByTestId("pending-invoices-table-shell")).toHaveStyle({ overflowY: "auto" });

    expect(within(page).getByRole("columnheader", { name: "支出流水" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "支出流水" })).toHaveStyle({ position: "sticky", top: "0px" });
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
    expect(within(page).getByText("全部流水 431")).toBeInTheDocument();
    expect(within(page).getByText("支出流水 356")).toBeInTheDocument();
    expect(within(page).getByText("收入流水 75")).toBeInTheDocument();

    expect(within(page).getByText("2026-04-19 10:52:02")).toBeInTheDocument();
    expect(within(page).getByText("建行 8106")).toBeInTheDocument();
    expect(within(page).queryByText("2026-04-19T10:52:02+08:00")).not.toBeInTheDocument();
    expect(within(page).queryByText("人民币元")).not.toBeInTheDocument();
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

  test("shows income rule-group filters and requests selected income scopes", async () => {
    const user = userEvent.setup();
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await screen.findByTestId("pending-invoices-page");
    await user.click(await within(page).findByRole("button", { name: /收入流水 75/ }));
    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      expect(latest?.searchParams.get("direction")).toBe("income");
    });

    await user.click(within(page).getByRole("button", { name: "全部" }));
    expect(await screen.findByRole("menuitem", { name: "待开发票" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "无需开票" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "现金收入" })).toBeInTheDocument();

    await user.click(screen.getByRole("menuitem", { name: "待开发票" }));
    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      expect(latest?.searchParams.get("direction")).toBe("income");
      expect(latest?.searchParams.get("filter")).toBe("requires_invoice");
    });

    await user.click(within(page).getByRole("button", { name: "待开发票" }));
    await user.click(await screen.findByRole("menuitem", { name: "现金收入" }));
    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      expect(latest?.searchParams.get("direction")).toBe("income");
      expect(latest?.searchParams.get("filter")).toBe("cash_income");
    });
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

    await user.click(within(relationRow).getByRole("button", { name: /OA详情 李四/ }));
    const oaDialog = await screen.findByRole("dialog", { name: "打印选择" });
    expect(within(oaDialog).getAllByText("支付申请").length).toBeGreaterThan(0);
    expect(within(oaDialog).getByRole("button", { name: "打印下载" })).toBeInTheDocument();
    expect(within(oaDialog).getByText("申请人")).toBeInTheDocument();
    expect(within(oaDialog).getAllByText("李四").length).toBeGreaterThan(0);
    expect(within(oaDialog).getByText("项目负责人审核")).toBeInTheDocument();
    await user.click(within(oaDialog).getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "待找发票规则设置" }));
    expect(await screen.findByRole("heading", { name: "待找发票规则设置" })).toBeInTheDocument();
    expect(screen.getByText("需要开票")).toBeInTheDocument();
    expect(screen.getAllByText("手续费").length).toBeGreaterThan(0);
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

  test("renders hierarchical pending invoice rule blocks with mutual exclusion", async () => {
    const user = userEvent.setup();
    installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await screen.findByTestId("pending-invoices-page");
    await user.click(within(page).getByRole("button", { name: "待找发票规则设置" }));

    const bankStatementBlock = await screen.findByRole("group", { name: "流水代替发票" });
    const noInvoiceBlock = screen.getByRole("group", { name: "无需开票" });
    const requiresInvoiceBlock = screen.getByRole("group", { name: "需要开票" });
    expect(within(bankStatementBlock).getByText("费用")).toBeInTheDocument();
    expect(within(bankStatementBlock).queryByRole("checkbox", { name: "费用" })).not.toBeInTheDocument();
    const bankStatementFee = within(bankStatementBlock).getByRole("checkbox", { name: "手续费" });
    expect(bankStatementFee).not.toBeChecked();
    expect(within(noInvoiceBlock).getByRole("checkbox", { name: "手续费" })).not.toBeDisabled();
    expect(within(requiresInvoiceBlock).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(requiresInvoiceBlock).getByText("手续费")).toBeInTheDocument();
    expect(within(requiresInvoiceBlock).getAllByText("餐饮")).toHaveLength(2);

    await user.click(bankStatementFee);

    expect(bankStatementFee).toBeChecked();
    expect(within(noInvoiceBlock).getByRole("checkbox", { name: "手续费" })).toBeDisabled();
    expect(within(requiresInvoiceBlock).queryByText("手续费")).not.toBeInTheDocument();

    await user.click(bankStatementFee);

    expect(bankStatementFee).not.toBeChecked();
    expect(within(noInvoiceBlock).getByRole("checkbox", { name: "手续费" })).not.toBeDisabled();
    expect(within(requiresInvoiceBlock).getByText("手续费")).toBeInTheDocument();
  });

  test("refreshes open rules drawer when bank detail auto tags update", async () => {
    const user = userEvent.setup();
    let rulesOptions: PendingInvoiceRulesMockOptions = {};
    const fetchMock = installPendingInvoiceFetch({
      rulesPayload: () => pendingInvoiceRulesPayload(rulesOptions),
    });
    renderAppAt("/pending-invoices");

    const page = await screen.findByTestId("pending-invoices-page");
    await user.click(within(page).getByRole("button", { name: "待找发票规则设置" }));

    const bankStatementBlock = await screen.findByRole("group", { name: "流水代替发票" });
    expect(within(bankStatementBlock).getByText("费用")).toBeInTheDocument();
    expect(within(bankStatementBlock).getByRole("checkbox", { name: "手续费" })).toBeInTheDocument();
    const initialRulesGets = pendingInvoiceRulesRequests(fetchMock).length;

    rulesOptions = { version: 8, feePrimaryLabel: "费用改名验证", feeSubLabel: "手续费改名验证" };
    act(() => {
      window.dispatchEvent(new CustomEvent("finops:bank-transaction-tags-updated", { detail: { version: 8 } }));
    });

    await waitFor(() => {
      expect(pendingInvoiceRulesRequests(fetchMock).length).toBeGreaterThan(initialRulesGets);
    });
    expect(await within(bankStatementBlock).findByText("费用改名验证")).toBeInTheDocument();
    expect(within(bankStatementBlock).getByRole("checkbox", { name: "手续费改名验证" })).toBeInTheDocument();
    expect(within(bankStatementBlock).queryByText("费用")).not.toBeInTheDocument();
  });

  test("preserves unsaved rule selections when refreshing renamed bank detail tags", async () => {
    const user = userEvent.setup();
    let rulesOptions: PendingInvoiceRulesMockOptions = {};
    const fetchMock = installPendingInvoiceFetch({
      rulesPayload: () => pendingInvoiceRulesPayload(rulesOptions),
    });
    renderAppAt("/pending-invoices");

    const page = await screen.findByTestId("pending-invoices-page");
    await user.click(within(page).getByRole("button", { name: "待找发票规则设置" }));

    const bankStatementBlock = await screen.findByRole("group", { name: "流水代替发票" });
    await user.click(within(bankStatementBlock).getByRole("checkbox", { name: "手续费" }));
    expect(within(bankStatementBlock).getByRole("checkbox", { name: "手续费" })).toBeChecked();

    rulesOptions = { version: 8, feePrimaryLabel: "费用改名验证", feeSubLabel: "手续费改名验证" };
    act(() => {
      window.dispatchEvent(new CustomEvent("finops:bank-transaction-tags-updated", { detail: { version: 8 } }));
    });

    const renamedFee = await within(bankStatementBlock).findByRole("checkbox", { name: "手续费改名验证" });
    expect(renamedFee).toBeChecked();
    expect(screen.getByText("银行明细自动标签已更新，已刷新标签名称并保留未保存选择。")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "保存规则" }));

    await waitFor(() => {
      expect(pendingInvoiceRulesRequests(fetchMock, "PUT").length).toBeGreaterThan(0);
    });
    const lastPut = pendingInvoiceRulesRequests(fetchMock, "PUT").at(-1);
    expect(JSON.parse(String(lastPut?.[1]?.body ?? "{}"))).toMatchObject({
      groups: {
        bank_statement_as_invoice: { tag_codes: ["internal_transfer", "fee"] },
        no_invoice_required: { tag_codes: ["salary"] },
      },
    });
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
    await user.type(screen.getByLabelText("销方"), "云南开票供应商");
    await user.click(screen.getByRole("button", { name: "搜索" }));
    await waitFor(() => {
      const candidateRequests = fetchMock.mock.calls
        .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
        .filter((url) => url.pathname === "/api/pending-invoices/invoice-candidates");
      expect(candidateRequests.at(-1)?.searchParams.get("seller_name")).toBe("云南开票供应商");
      expect(candidateRequests.at(-1)?.searchParams.get("page_size")).toBe("20");
    });
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
