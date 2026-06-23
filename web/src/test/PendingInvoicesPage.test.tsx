import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

const pendingInvoicesSourceFiles = [
  "src/pages/PendingInvoicesPage.tsx",
  "src/components/pendingInvoices/PendingInvoicesTable.tsx",
  "src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx",
  "src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx",
  "src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx",
  "src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx",
  "src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx",
  "src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx",
] as const;

function readWebSource(path: string) {
  return readFileSync(resolve(path), "utf8");
}

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
        effective_tag_code: "equipment_purchase",
        effective_tag_label: "设备采购",
        effective_tag_primary_label: "货款",
        effective_tag_sub_label: "设备采购",
        effective_tag_label_path: ["货款", "设备采购"],
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
      available_actions: ["attach_existing_invoice"],
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
      bank_transactions: {
        primary: null,
        relation_count: 2,
        linked_relation_count: 2,
        has_multiple: true,
        detail_mode: "list",
        summaries: [
          {
            id: "txn-invoice-not-paid",
            counterparty_name: "分期供应商",
            trade_time: "2026-05-03 09:00:00",
            amount: "1200.00",
            debit_amount: "1200.00",
            bank_name: "建设银行",
            account_last4: "8826",
            summary: "合同付款",
            relation_case_id: "case-001",
            relation_status: "linked",
          },
          {
            id: "txn-old-payment",
            counterparty_name: "分期供应商二号",
            trade_time: "2026-04-20 09:00:00",
            amount: "300.00",
            debit_amount: "300.00",
            bank_name: "建设银行",
            account_last4: "8826",
            summary: "历史付款",
            relation_case_id: "case-old",
            relation_status: "linked",
          },
        ],
        payment_summary: { paid_total: "1500.00" },
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
        payment_summary: { paid_total: "1500.00", invoice_total: "2800.00", remaining_amount: "1300.00", difference_amount: "-1300.00" },
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
    {
      id: "txn-candidate-oa",
      bank_transaction: {
        id: "txn-candidate-oa",
        counterparty_name: "候选OA供应商",
        trade_time: "2026-05-05 11:00:00",
        debit_amount: "400.00",
        credit_amount: "0.00",
        amount: "400.00",
        bank_name: "建设银行",
        account_name: "云南溯源科技有限公司",
        account_last4: "8106",
        summary: "候选关系",
      },
      invoice_acquisition_status: {
        code: "paid_invoiced",
        label: "已支付已开票",
        reason: "候选关系已关联发票但 OA 投影不可用",
        severity: "success",
        primary_action: "view_relation",
        matched_rule: null,
      },
      input_invoices: {
        primary: {
          id: "inv-candidate-oa",
          digital_invoice_no: "DIG-CAND-OA",
          issue_date: "2026-05-05",
          seller_name: "候选OA供应商",
          total_with_tax: "400.00",
        },
        relation_count: 1,
        has_multiple: false,
        summaries: [],
        payment_summary: { paid_total: "400.00", invoice_total: "400.00", remaining_amount: "0.00", difference_amount: "0.00" },
      },
      oa: {
        primary: {
          id: "candidate:030404426078",
          applicant: "赵六",
          application_type: "支付",
          project_name: "候选项目",
          status: "",
          detail_available: false,
          relation_case_id: "candidate:030404426078",
        },
        relation_count: 1,
        has_multiple: false,
        detail_available: false,
        summaries: [],
      },
      can_create_invoice: false,
      available_actions: ["view_relation"],
      relation_case_ids: ["candidate:030404426078"],
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

function pendingRuleClosureRow(id: string, counterpartyName: string, statusLabel: string, matchedGroup: string) {
  return {
    id,
    bank_transaction: {
      id,
      counterparty_name: counterpartyName,
      trade_time: "2026-05-08 10:00:00",
      debit_amount: "118.00",
      credit_amount: "0.00",
      amount: "118.00",
      bank_name: "建设银行",
      account_name: "云南溯源科技有限公司",
      account_last4: "8106",
      summary: "规则闭环验证",
    },
    invoice_acquisition_status: {
      code: matchedGroup === "no_invoice_required" ? "no_invoice_required" : "paid_pending_invoice",
      label: statusLabel,
      reason: `命中${statusLabel}规则`,
      severity: matchedGroup === "no_invoice_required" ? "success" : "warning",
      primary_action: matchedGroup === "no_invoice_required" ? "view_rules" : "attach_or_create_invoice",
      matched_rule: { source: "pending_invoice_tag_groups", group: matchedGroup, tag_code: id, tag_label: statusLabel },
    },
    input_invoices: { primary: null, relation_count: 0, has_multiple: false, summaries: [], payment_summary: null },
    oa: { primary: null, relation_count: 0, has_multiple: false, detail_available: false, summaries: [] },
    can_create_invoice: matchedGroup !== "no_invoice_required",
    available_actions: matchedGroup === "no_invoice_required" ? ["view_rules"] : ["attach_existing_invoice"],
  };
}

function batchAttachRow() {
  const base = upgradedRows()[0];
  return {
    ...base,
    id: "txn-paid-pending-2",
    bank_transaction: {
      ...base.bank_transaction,
      id: "txn-paid-pending-2",
      counterparty_name: "云南开票供应商二号",
      debit_amount: "36.00",
      amount: "36.00",
      trade_time: "2026-04-20T10:52:02+08:00",
      booked_date: "2026-05-03",
      summary: "小额设备款",
      remark: "批量选择验证",
      statement_serial_no: "stmt-paid-pending-2",
      enterprise_serial_no: "ent-paid-pending-2",
      voucher_no: "v-paid-pending-2",
    },
    oa: {
      primary: { id: "oa-paid-pending-2", applicant: "张三", application_type: "支付", project_name: "维护项目二期", status: "进行中" },
      relation_count: 1,
      has_multiple: false,
      detail_available: true,
      summaries: [],
    },
  };
}

function installPendingInvoiceFetch(options: {
  rulesPayload?: () => ReturnType<typeof pendingInvoiceRulesPayload>;
  rowsPayload?: (url: URL) => Array<Record<string, unknown>>;
  readModelStatus?: string;
  operationBarrierResponse?: (body: Record<string, unknown>, url: URL) => Response | Promise<Response>;
  attachExistingInvoicesPreviewResponse?: (body: Record<string, unknown>, url: URL) => Response | Promise<Response>;
  exportDownloadResponse?: (url: URL) => Response;
  onRulesSaved?: () => void;
  rulesSaveResponse?: (body: Record<string, unknown>, url: URL) => Response;
} = {}) {
  const baseFetch = installMockApiFetch();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.pathname === "/api/pending-invoices/rows") {
      const rows = options.rowsPayload?.(url) ?? upgradedRows();
      const direction = url.searchParams.get("direction") ?? "expense";
      const pageSize = Number(url.searchParams.get("page_size") ?? 50);
      return new Response(JSON.stringify({
        direction,
        filter: url.searchParams.get("filter") ?? "all",
        rows,
        pagination: { page: Number(url.searchParams.get("page") ?? 1), page_size: pageSize, total: rows.length },
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
        read_model_status: options.readModelStatus ?? "fresh",
        tag_dictionary: { version: 1, tags: [] },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/rules" && method === "GET") {
      return new Response(JSON.stringify((options.rulesPayload ?? pendingInvoiceRulesPayload)()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/operation-barrier/status" && method === "POST" && options.operationBarrierResponse) {
      const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
      return options.operationBarrierResponse(body, url);
    }
    if (url.pathname === "/api/pending-invoices/filter-options") {
      return new Response(JSON.stringify({
        fields: [
          {
            field: "counterparty_name",
            label: "对方户名",
            operators: ["in", "contains"],
            options: [
              { value: "云南开票供应商", label: "云南开票供应商", count: 1 },
              { value: "分期供应商", label: "分期供应商", count: 1 },
            ],
          },
          {
            field: "transaction_tag",
            label: "流水标签",
            operators: ["in", "contains"],
            options: [
              { value: "货款 / 设备采购", label: "货款 / 设备采购", count: 1 },
              { value: "费用 / 手续费", label: "费用 / 手续费", count: 2 },
            ],
          },
          {
            field: "bank_account",
            label: "银行账户",
            operators: ["in", "contains"],
            options: [
              { value: "建行 8106", label: "建行 8106", count: 3 },
              { value: "光大 8826", label: "光大 8826", count: 1 },
            ],
          },
          {
            field: "direction",
            label: "收支",
            operators: ["in"],
            options: [
              { value: "expense", label: "支出", count: 356 },
              { value: "income", label: "收入", count: 75 },
            ],
          },
          {
            field: "seller_name",
            label: "销方",
            operators: ["in", "contains"],
            options: [{ value: "分期供应商", label: "分期供应商", count: 1 }],
          },
          {
            field: "oa_applicant",
            label: "申请人",
            operators: ["in", "contains"],
            options: [{ value: "李四", label: "李四", count: 1 }],
          },
          {
            field: "oa_application_type",
            label: "类型",
            operators: ["in", "contains"],
            options: [
              { value: "支付", label: "支付", count: 2 },
              { value: "报销", label: "报销", count: 1 },
            ],
          },
          {
            field: "project_name",
            label: "项目",
            operators: ["in", "contains"],
            options: [{ value: "建设项目", label: "建设项目", count: 1 }],
          },
        ],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/rules" && method === "PUT") {
      const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
      if (options.rulesSaveResponse) {
        return options.rulesSaveResponse(body, url);
      }
      options.onRulesSaved?.();
      return new Response(JSON.stringify({
        version: 8,
        direction: url.searchParams.get("direction") ?? "expense",
        read_model_status: "refreshing",
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
        related_invoices: [
          { id: "inv-001", digital_invoice_no: "DIG-001", seller_name: "分期供应商", total_with_tax: "2000.00" },
          { id: "inv-002", digital_invoice_no: "DIG-002", seller_name: "分期供应商二号", total_with_tax: "800.00" },
        ],
        related_oa: [
          { id: "oa-001", applicant: "李四", application_type: "支付", project_name: "建设项目", status: "进行中", relation_case_id: "case-001" },
          { id: "oa-002", applicant: "王五", application_type: "报销", project_name: "建设项目二期", status: "已完成", relation_case_id: "case-old" },
        ],
        relation_case_ids: ["case-001", "case-old"],
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
    if (url.pathname === "/api/pending-invoices/invoice-candidates/batch" && method === "POST") {
      const body = JSON.parse(String(init?.body ?? "{}")) as { transaction_ids?: string[]; invoice_ids?: string[] };
      const transactionIds = Array.isArray(body.transaction_ids) ? body.transaction_ids : [];
      const multi = transactionIds.includes("txn-paid-pending-2");
      return new Response(JSON.stringify({
        transaction_ids: transactionIds,
        selection_summary: {
          transaction_count: transactionIds.length,
          bank_total: multi ? "1236.00" : "1200.00",
        },
        rows: [
          {
            invoice_id: "inv-candidate",
            digital_invoice_no: "DIG-CAND-001",
            invoice_no: "INV-CAND-001",
            issue_date: "2026-05-06",
            seller_name: "云南开票供应商",
            seller_tax_no: "915300009999",
            total_with_tax: "1200.00",
            related_paid_total: "0.00",
            remaining_amount: "1200.00",
            amount_difference_abs: multi ? "36.00" : "0.00",
            candidate_status: "available",
            bank_relation_status: "unlinked",
            linked_bank_transaction_count: 0,
          },
          ...(multi ? [{
            invoice_id: "inv-candidate-2",
            digital_invoice_no: "DIG-CAND-002",
            invoice_no: "INV-CAND-002",
            issue_date: "2026-05-07",
            seller_name: "云南开票供应商二号",
            seller_tax_no: "915300008888",
            total_with_tax: "36.00",
            related_paid_total: "0.00",
            remaining_amount: "36.00",
            amount_difference_abs: "1200.00",
            candidate_status: "available",
            bank_relation_status: "linked",
            linked_bank_transaction_count: 1,
          }] : []),
        ],
        pagination: { page: 1, page_size: 20, total: multi ? 2 : 1 },
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
          bank_relation_status: "unlinked",
          linked_bank_transaction_count: 0,
        }],
        pagination: { page: 1, page_size: 20, total: 1 },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/attach-existing-invoices/preview" && method === "POST") {
      const body = JSON.parse(String(init?.body ?? "{}")) as { transaction_ids?: string[]; invoice_ids?: string[] };
      if (options.attachExistingInvoicesPreviewResponse) {
        return options.attachExistingInvoicesPreviewResponse(body, url);
      }
      const transactionIds = Array.isArray(body.transaction_ids) ? body.transaction_ids : [];
      const invoiceIds = Array.isArray(body.invoice_ids) ? body.invoice_ids : [];
      const multi = transactionIds.includes("txn-paid-pending-2") || invoiceIds.includes("inv-candidate-2");
      return new Response(JSON.stringify({
        preview_id: multi ? "attach-preview-batch" : "attach-preview-001",
        request_key: multi ? "pending_invoice_attach_existing_batch:multi" : "pending_invoice_attach_existing:txn-paid-pending:inv-candidate",
        can_confirm: true,
        transaction_summaries: transactionIds.map((id) => ({
          id,
          counterparty_name: id === "txn-paid-pending-2" ? "云南开票供应商二号" : "云南开票供应商",
          trade_time: id === "txn-paid-pending-2" ? "2026-05-03" : "2026-05-02",
          debit_amount: id === "txn-paid-pending-2" ? "36.00" : "1200.00",
        })),
        invoice_summaries: invoiceIds.map((id) => ({
          id,
          digital_invoice_no: id === "inv-candidate-2" ? "DIG-CAND-002" : "DIG-CAND-001",
          issue_date: id === "inv-candidate-2" ? "2026-05-07" : "2026-05-06",
          seller_name: id === "inv-candidate-2" ? "云南开票供应商二号" : "云南开票供应商",
          seller_tax_no: id === "inv-candidate-2" ? "915300008888" : "915300009999",
          total_with_tax: id === "inv-candidate-2" ? "36.00" : "1200.00",
        })),
        selection_summary: {
          transaction_count: transactionIds.length,
          invoice_count: invoiceIds.length,
          bank_total: multi ? "1236.00" : "1200.00",
          invoice_total: multi ? "1236.00" : "1200.00",
          difference_amount: "0.00",
        },
        payment_impact: {
          paid_total_before: "0.00",
          paid_total_after: multi ? "1236.00" : "1200.00",
          invoice_total: multi ? "1236.00" : "1200.00",
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
      const body = JSON.parse(String(init?.body ?? "{}")) as { transaction_ids?: string[]; invoice_ids?: string[]; request_id?: string };
      const transactionIds = Array.isArray(body.transaction_ids) ? body.transaction_ids : [];
      const invoiceIds = Array.isArray(body.invoice_ids) ? body.invoice_ids : [];
      const multi = transactionIds.includes("txn-paid-pending-2") || invoiceIds.includes("inv-candidate-2");
      return new Response(JSON.stringify({
        status: "completed",
        request_id: body.request_id ?? "attach-confirm",
        request_key: multi ? "pending_invoice_attach_existing_batch:multi" : "pending_invoice_attach_existing:txn-paid-pending:inv-candidate",
        transaction_ids: transactionIds,
        invoice_ids: invoiceIds,
        relation_case_id: multi ? "case-candidate-batch" : "case-candidate",
        relation_mode: "pending_invoice_attach_existing_invoice",
        affected_transaction_ids: transactionIds,
        affected_invoice_ids: invoiceIds,
        affected_months: ["2026-05"],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/income-statuses" && method === "PUT") {
      const body = JSON.parse(String(init?.body ?? "{}")) as { transaction_ids?: string[]; status_code?: string; request_id?: string };
      const transactionIds = Array.isArray(body.transaction_ids) ? body.transaction_ids : [];
      return new Response(JSON.stringify({
        status: "completed",
        request_id: body.request_id ?? "income-status-batch",
        request_key: "pending_invoice_income_status_batch:mock",
        transaction_ids: transactionIds,
        status_code: body.status_code ?? "cash_income",
        affected_transaction_ids: transactionIds,
        affected_invoice_ids: [],
        affected_months: ["2026-05"],
        rows: [],
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
      if (options.exportDownloadResponse) {
        return options.exportDownloadResponse(url);
      }
      return new Response(new Blob(["xlsx"], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }), {
        status: 200,
        headers: {
          "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "Content-Disposition": "attachment; filename*=UTF-8''pending-invoices.xlsx",
        },
      });
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

function operationBarrierRequests(fetchMock: ReturnType<typeof installPendingInvoiceFetch>) {
  return fetchMock.mock.calls
    .filter(([input, init]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/operation-barrier/status" && (init?.method ?? "GET").toUpperCase() === "POST";
    })
    .map(([, init]) => JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>);
}

function findPendingInvoicesPage() {
  return screen.findByTestId("pending-invoices-page", undefined, { timeout: 10_000 });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Pending invoices page", () => {
  test("targets project primitives for page shell, tables, drawers, and dialogs", () => {
    const forbiddenMuiImports = pendingInvoicesSourceFiles.flatMap((path) => {
      const source = readWebSource(path);
      const hasMuiImport = /from ["']@mui\/|import\s+[^;]*@mui\//.test(source);
      return hasMuiImport ? [path] : [];
    });
    const sourceByPath = Object.fromEntries(pendingInvoicesSourceFiles.map((path) => [path, readWebSource(path)]));
    const pendingInvoicesTableSource = sourceByPath["src/components/pendingInvoices/PendingInvoicesTable.tsx"];
    const missingPrimitiveTargets = [
      sourceByPath["src/pages/PendingInvoicesPage.tsx"].includes("PageScaffold") ? null : "PendingInvoicesPage.tsx should use PageScaffold or equivalent project shell",
      sourceByPath["src/pages/PendingInvoicesPage.tsx"].includes("PageToolbar") ? null : "PendingInvoicesPage.tsx should use PageToolbar or equivalent project toolbar",
      pendingInvoicesTableSource.includes("@heroui/react") ? null : "PendingInvoicesTable.tsx should use HeroUI React primitives",
      pendingInvoicesTableSource.includes("Table.ScrollContainer") && pendingInvoicesTableSource.includes("<table") ? null : "PendingInvoicesTable.tsx should keep the HeroUI shell with native table content",
      !pendingInvoicesTableSource.includes("Table.Content") && !pendingInvoicesTableSource.includes("Table.Column") ? null : "PendingInvoicesTable.tsx should not use RAC table content because it blocks body text selection",
      pendingInvoicesTableSource.includes("aria-sort") && pendingInvoicesTableSource.includes("handleNativeSort") ? null : "PendingInvoicesTable.tsx should keep native accessible sorting",
      pendingInvoicesTableSource.includes("Dropdown.Menu") && pendingInvoicesTableSource.includes('selectionMode="multiple"') ? null : "PendingInvoicesTable.tsx should use HeroUI Dropdown multi-select filtering",
      sourceByPath["src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx"].includes("AppDrawer") ? null : "PendingInvoiceDrawerFrame.tsx should use AppDrawer for right drawer shape",
      sourceByPath["src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx"].includes("AppDialog") ? null : "PendingInvoiceDetailDrawer.tsx should use AppDialog for OA print dialog",
    ].filter(Boolean);

    expect({
      forbiddenMuiImports,
      missingPrimitiveTargets,
    }).toEqual({
      forbiddenMuiImports: [],
      missingPrimitiveTargets: [],
    });
  });

  test("locks compact premium table, drawer, and motion styling contracts", () => {
    const css = readWebSource("src/app/styles.css");

    expect(css).toMatch(/\.pending-invoices-page\s*{[^}]*padding:\s*var\(--fp-space-4\) var\(--fp-space-5\)/s);
    expect(css).toMatch(/\.pending-invoices-button,\s*\.pending-invoice-status-filter-button\s*{[^}]*transition:[^}]*var\(--motion-fast\)/s);
    expect(css).toMatch(/\.pending-invoices-table-frame\s*{[^}]*border-radius:\s*var\(--fp-radius-sm\) var\(--fp-radius-sm\) 0 0/s);
    expect(css).toMatch(/\.pending-invoices-table-shell\s*{[^}]*max-height:\s*calc\(100vh - 176px\);[^}]*min-height:\s*292px/s);
    expect(css).toMatch(/\.pending-invoices-table-cell\s*{[^}]*transition:\s*background-color var\(--motion-fast\)/s);
    expect(css).toMatch(/\.pending-invoices-table-cell\s*{[^}]*user-select:\s*text/s);
    expect(css).toMatch(/\.pending-invoices-sort-button\s*{[^}]*transition:[^}]*var\(--motion-fast\)/s);
    expect(css).not.toMatch(/\.pending-invoices-sort-button\s*{[^}]*pointer-events:\s*none/s);
    expect(css).toMatch(/\.pending-invoices-table-zone-header-grid\s*{[^}]*grid-template-columns:\s*14fr 10fr 11fr 11fr 11fr 10fr 7fr 11fr 15fr/s);
    expect(css).toMatch(/\.pending-invoices-icon-button,\s*\.pending-invoices-inline-action\s*{[^}]*transition:[^}]*var\(--motion-fast\)/s);
    expect(css).toMatch(/\.pending-invoice-drawer\s+\.finance-drawer__header\s*{[^}]*padding:\s*10px var\(--fp-space-4\)/s);
    expect(css).toMatch(/\.pending-invoice-drawer__body\s*{[^}]*padding:\s*var\(--fp-space-3\)/s);
    expect(css).toMatch(/\.pending-invoice-metric-grid\s*{[^}]*gap:\s*var\(--fp-space-2\)/s);
  });

  test("renders project four-zone table contract and summarizes multiple relations", async () => {
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    expect(await screen.findByRole("link", { name: "待找发票" })).toHaveAttribute("href", "/pending-invoices");
    const page = await findPendingInvoicesPage();
    expect(within(page).getByRole("grid", { name: "待找发票四区表" })).toBeInTheDocument();
    expect(within(page).queryByRole("table", { name: "待找发票四区表" })).not.toBeInTheDocument();
    expect(within(page).getByTestId("pending-invoices-table-shell")).toHaveClass("pending-invoices-table-shell");
    expect(readWebSource("src/app/styles.css")).toMatch(
      /\.pending-invoices-table-shell\s*{[^}]*overflow-x:\s*hidden;[^}]*overflow-y:\s*auto;/s,
    );

    expect(within(page).getByText("支出流水")).toHaveClass("pending-invoices-table-group-header");
    expect(within(page).getByText("发票获取状态")).toHaveClass("pending-invoices-table-group-header");
    expect(within(page).getByText("进项发票")).toHaveClass("pending-invoices-table-group-header");
    expect(within(page).getByText("OA")).toHaveClass("pending-invoices-table-group-header");
    expect(within(page).getByRole("columnheader", { name: "对方户名 / 时间" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "金额 / 银行账户" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "摘要 / 凭证" })).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "状态" })).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "筛选发票获取状态：已选 2 项" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "发票号码 / 开票日期" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "供应商 / 识别号" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "金额 / 支付差额" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "申请人 / 类型" })).toBeInTheDocument();
    expect(within(page).getByRole("columnheader", { name: "项目" })).toBeInTheDocument();

    expect(await within(page).findByText("云南开票供应商")).toBeInTheDocument();
    expect(within(page).queryByText("正在加载待找发票。")).not.toBeInTheDocument();
    expect(within(page).queryByText(/对方尾号/)).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "全部 431" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "支出 356" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "收入 75" })).toBeInTheDocument();
    expect(within(page).getByRole("heading", { name: "待找发票" }).parentElement).toContainElement(within(page).getByRole("button", { name: "全部 431" }));
    expect(within(page).getByRole("button", { name: "支出待找发票规则设置" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "收入待找发票规则设置" })).toBeInTheDocument();

    expect(within(page).getByText("2026-04-19 10:52:02")).toBeInTheDocument();
    expect(within(page).getByText("货款 / 设备采购")).toBeInTheDocument();
    expect(within(page).getAllByText("支").length).toBeGreaterThan(0);
    expect(within(page).getAllByText("1,200.00").length).toBeGreaterThan(0);
    expect(within(page).getByText("建行 8106")).toBeInTheDocument();
    expect(within(page).queryByText("2026-04-19T10:52:02+08:00")).not.toBeInTheDocument();
    expect(within(page).queryByText("人民币元")).not.toBeInTheDocument();
    expect(within(page).getAllByText("已支付待开票").length).toBeGreaterThan(0);
    expect(within(page).queryByText("未命中免票规则，且未发现进项发票关系")).not.toBeInTheDocument();
    expect(within(page).queryByText("命中无需开票规则：工资")).not.toBeInTheDocument();
    expect(within(page).queryByText("发票价税合计大于已付合计")).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: /打开规则设置/ })).not.toBeInTheDocument();
    const pendingRow = within(page).getByRole("row", { name: /云南开票供应商/ });
    expect(within(pendingRow).queryByRole("button", { name: /云南开票供应商 选择发票/ })).not.toBeInTheDocument();
    expect(within(pendingRow).queryByRole("button", { name: /云南开票供应商 补票/ })).not.toBeInTheDocument();
    expect(within(pendingRow).queryByRole("button", { name: "云南开票供应商 发票获取操作" })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "补票" })).not.toBeInTheDocument();
    expect(within(page).queryByText("DIG-001")).not.toBeInTheDocument();
    expect(within(page).queryByText("李四")).not.toBeInTheDocument();
    expect(within(page).getAllByText("+2").length).toBeGreaterThanOrEqual(3);
    expect(within(page).getByText("2,800.00")).toBeInTheDocument();
    expect(within(page).getByText("已付 1,500.00")).toBeInTheDocument();
    expect(within(page).getByText("待付 1,300.00")).toBeInTheDocument();

    const request = pendingInvoiceRowsRequests(fetchMock)[0];
    expect(request.searchParams.get("direction")).toBe("expense");
    expect(request.searchParams.get("filter")).toBe("requires_invoice");
    expect(JSON.parse(request.searchParams.get("filters") ?? "[]")).toEqual([
      { field: "status_code", operator: "in", values: ["paid_pending_invoice", "paid_invoiced"] },
    ]);
    expect(request.searchParams.get("page")).toBe("1");
    expect(request.searchParams.get("page_size")).toBe("50");
    expect(request.searchParams.get("sort_field")).toBe("trade_date");
    expect(request.searchParams.get("sort_direction")).toBe("desc");
    const pageSizeSelect = within(page).getByLabelText("每页行数") as HTMLSelectElement;
    expect(Array.from(pageSizeSelect.options).map((option) => option.value)).toEqual(["25", "50", "100"]);
  });

  test("supports multi-select invoice acquisition status filters for expense rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    await within(page).findByText("云南开票供应商");

    await user.click(within(page).getByRole("button", { name: "筛选发票获取状态：已选 2 项" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).queryByRole("menuitemcheckbox", { name: "需要开票" })).not.toBeInTheDocument();
    expect(within(menu).getAllByRole("menuitemcheckbox").map((item) => item.textContent?.replace("✓", ""))).toEqual([
      "已支付待开票",
      "已支付已开票",
      "流水代替发票",
      "无需开票",
    ]);
    expect(within(menu).getByRole("menuitem", { name: "全选" })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: "清空" })).toBeInTheDocument();

    await user.click(within(menu).getByRole("menuitemcheckbox", { name: "已支付已开票" }));
    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      expect(latest?.searchParams.get("filter")).toBe("requires_invoice");
      expect(JSON.parse(latest?.searchParams.get("filters") ?? "[]")).toEqual([
        { field: "status_code", operator: "in", values: ["paid_pending_invoice"] },
      ]);
    });
    expect(within(page).getByRole("button", { name: "筛选发票获取状态：已支付待开票" })).toBeInTheDocument();

    await user.click(within(menu).getByRole("menuitem", { name: "清空" }));
    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      expect(latest?.searchParams.get("filter")).toBe("all");
      expect(latest?.searchParams.get("filters")).toBeNull();
    });
    expect(within(page).getByRole("button", { name: "筛选发票获取状态：全部" })).toBeInTheDocument();

    await user.click(within(menu).getByRole("menuitem", { name: "全选" }));
    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      expect(latest?.searchParams.get("filter")).toBe("all");
      expect(JSON.parse(latest?.searchParams.get("filters") ?? "[]")).toEqual([
        { field: "status_code", operator: "in", values: ["paid_pending_invoice", "paid_invoiced", "bank_statement_as_invoice", "no_invoice_required"] },
      ]);
    });
  });

  test("applies header dropdown filters as AND field clauses", async () => {
    const user = userEvent.setup();
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    await within(page).findByText("云南开票供应商");

    await user.click(within(page).getByRole("button", { name: "筛选 对方户名 / 时间" }));
    const filterMenu = await screen.findByRole("menu", { hidden: true });
    expect(filterMenu).toHaveAttribute("aria-label", "对方户名 / 时间筛选");
    await user.click(within(filterMenu).getByRole("menuitemcheckbox", { hidden: true, name: /对方户名：分期供应商/ }));
    await user.click(within(filterMenu).getByRole("menuitemcheckbox", { hidden: true, name: /流水标签：货款 \/ 设备采购/ }));
    await user.click(screen.getByRole("button", { name: "应用筛选" }));

    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(latest?.searchParams.get("filters") ?? "[]") as Array<{ field: string; operator: string; values?: string[] }>;
      expect(filters).toEqual([
        { field: "counterparty_name", operator: "in", values: ["分期供应商"] },
        { field: "transaction_tag", operator: "in", values: ["货款 / 设备采购"] },
        { field: "status_code", operator: "in", values: ["paid_pending_invoice", "paid_invoiced"] },
      ]);
    });

    await user.click(within(page).getByRole("button", { name: "筛选 金额 / 银行账户" }));
    const accountMenu = await screen.findByRole("menu", { hidden: true });
    expect(accountMenu).toHaveAttribute("aria-label", "金额 / 银行账户筛选");
    await user.click(within(accountMenu).getByRole("menuitemcheckbox", { hidden: true, name: /银行账户：光大 8826/ }));
    await user.click(within(accountMenu).getByRole("menuitemcheckbox", { hidden: true, name: /收支：支出/ }));
    await user.click(screen.getByRole("button", { name: "应用筛选" }));

    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(latest?.searchParams.get("filters") ?? "[]") as Array<{ field: string; operator: string; values?: string[] }>;
      expect(filters).toEqual([
        { field: "counterparty_name", operator: "in", values: ["分期供应商"] },
        { field: "transaction_tag", operator: "in", values: ["货款 / 设备采购"] },
        { field: "bank_account", operator: "in", values: ["光大 8826"] },
        { field: "direction", operator: "in", values: ["expense"] },
        { field: "status_code", operator: "in", values: ["paid_pending_invoice", "paid_invoiced"] },
      ]);
    });
  });

  test("shows income rule-group filters and requests selected income scopes", async () => {
    const user = userEvent.setup();
    const incomeRow = {
      ...pendingRuleClosureRow("income-service", "收入服务客户", "未开票", "requires_invoice"),
      bank_transaction: {
        ...pendingRuleClosureRow("income-service", "收入服务客户", "未开票", "requires_invoice").bank_transaction,
        debit_amount: "0.00",
        credit_amount: "300.00",
        amount: "300.00",
        effective_tag_code: "service_income",
        effective_tag_label: "服务收入",
        effective_tag_primary_label: "收入",
        effective_tag_sub_label: "服务收入",
        effective_tag_label_path: ["收入", "服务收入"],
      },
      invoice_acquisition_status: {
        code: "income_pending_invoice",
        label: "未开票",
        reason: "收入流水未关联销项发票。",
        severity: "warning",
        primary_action: "mark_income_status",
        matched_rule: { source: "pending_output_invoice_tag_groups", group: "requires_invoice", tag_code: "service_income", tag_label: "服务收入" },
      },
      can_create_invoice: false,
      available_actions: ["mark_income_status"],
    };
    const fetchMock = installPendingInvoiceFetch({
      rowsPayload: (url) => (url.searchParams.get("direction") === "income" ? [incomeRow] : upgradedRows()),
    });
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    await user.click(await within(page).findByRole("button", { name: "收入 75" }));
    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      expect(latest?.searchParams.get("direction")).toBe("income");
    });
    expect(await within(page).findByText("收入 / 服务收入")).toBeInTheDocument();
    expect(within(page).getByText("收")).toBeInTheDocument();
    expect(within(page).getByText("300.00")).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "筛选发票获取状态：全部" }));
    expect(await screen.findByRole("menuitemcheckbox", { name: "待开发票" })).toBeInTheDocument();
    expect(screen.getByRole("menuitemcheckbox", { name: "无需开票" })).toBeInTheDocument();
    expect(screen.getByRole("menuitemcheckbox", { name: "现金收入" })).toBeInTheDocument();

    await user.click(screen.getByRole("menuitemcheckbox", { name: "待开发票" }));
    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      expect(latest?.searchParams.get("direction")).toBe("income");
      expect(latest?.searchParams.get("filter")).toBe("requires_invoice");
      expect(JSON.parse(latest?.searchParams.get("filters") ?? "[]")).toEqual([
        { field: "status_code", operator: "in", values: ["income_pending_invoice"] },
      ]);
    });

    await user.click(await screen.findByRole("menuitemcheckbox", { name: "现金收入" }));
    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      expect(latest?.searchParams.get("direction")).toBe("income");
      expect(latest?.searchParams.get("filter")).toBe("all");
      expect(JSON.parse(latest?.searchParams.get("filters") ?? "[]")).toEqual([
        { field: "status_code", operator: "in", values: ["income_pending_invoice", "cash_income"] },
      ]);
    });
  }, 30_000);

  test("opens relation, rules, and export drawers with loading callbacks", async () => {
    const user = userEvent.setup();
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    await within(page).findByText("云南开票供应商");
    await user.click(within(page).getByRole("button", { name: "查看全部发票关系" }));
    expect(await screen.findByText("关系与支付明细")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "关闭关系明细抽屉" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "已关联发票" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "历史支付流水" })).not.toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "已关联 OA" })).not.toBeInTheDocument();
    expect(await screen.findByText("已付合计")).toBeInTheDocument();
    expect(screen.getAllByText("1,500.00").length).toBeGreaterThan(0);
    expect(screen.getByText("DIG-002")).toBeInTheDocument();
    expect(screen.getByText("分期供应商二号")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭关系明细抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看全部流水关系" }));
    expect(await screen.findByRole("table", { name: "历史支付流水" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "已关联发票" })).not.toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "已关联 OA" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭关系明细抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看全部 OA 关系" }));
    expect(await screen.findByRole("table", { name: "已关联 OA" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "已关联发票" })).not.toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "历史支付流水" })).not.toBeInTheDocument();
    expect(screen.getByText("王五")).toBeInTheDocument();
    expect(screen.getByText("建设项目二期")).toBeInTheDocument();
    expect(screen.getAllByText("case-old").length).toBeGreaterThanOrEqual(1);
    await user.click(screen.getByRole("button", { name: "关闭关系明细抽屉" }));

    await user.click(within(page).getByRole("button", { name: "支出待找发票规则设置" }));
    expect(await screen.findByRole("heading", { name: "支出待找发票规则设置" })).toBeInTheDocument();
    expect(screen.queryByText(/版本\s+\d+/)).not.toBeInTheDocument();
    expect(screen.getByText("需要开票")).toBeInTheDocument();
    expect(screen.getAllByText("手续费").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "保存规则" }));
    await waitFor(() => {
      expect(pendingInvoiceRulesRequests(fetchMock, "PUT").length).toBeGreaterThan(0);
    });
    const rulesPut = pendingInvoiceRulesRequests(fetchMock, "PUT")[0];
    const rulesBody = JSON.parse(String(rulesPut[1]?.body ?? "{}")) as Record<string, unknown>;
    expect(rulesBody).toMatchObject({ version: 7, direction: "expense" });
    expect(await screen.findByText("规则已保存，相关数据正在刷新。")).toBeInTheDocument();
    expect(pendingInvoiceRowsRequests(fetchMock).length).toBeGreaterThan(1);
    await user.click(screen.getByRole("button", { name: "关闭规则抽屉" }));

    await user.click(within(page).getByRole("button", { name: "收入待找发票规则设置" }));
    expect(await screen.findByRole("heading", { name: "收入待找发票规则设置" })).toBeInTheDocument();
    await waitFor(() => {
      const latestRulesGet = pendingInvoiceRulesRequests(fetchMock).at(-1);
      const url = new URL(typeof latestRulesGet?.[0] === "string" ? latestRulesGet[0] : latestRulesGet?.[0] instanceof URL ? latestRulesGet[0].toString() : latestRulesGet?.[0]?.url ?? "", "http://localhost");
      expect(url.searchParams.get("direction")).toBe("income");
    });
    await user.click(screen.getByRole("button", { name: "关闭规则抽屉" }));

    await user.click(within(page).getByRole("button", { name: "筛选内容导出" }));
    expect(await screen.findByRole("heading", { name: "导出预览" })).toBeInTheDocument();
    expect(screen.getByText("预计导出 128 行")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "导出样例" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "下载导出" }));
    expect(await screen.findByText("已生成 pending-invoices.xlsx")).toBeInTheDocument();
  }, 45_000);

  test("shows backend export row-limit messages inside the export drawer", async () => {
    const user = userEvent.setup();
    installPendingInvoiceFetch({
      exportDownloadResponse: () => new Response(JSON.stringify({
        error: "pending_invoice_export_row_limit_exceeded",
        message: "待找发票导出超过 20000 行，请缩小筛选范围后重试。",
        details: { total: 20001, limit: 20000 },
      }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    });
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    await user.click(within(page).getByRole("button", { name: "筛选内容导出" }));
    expect(await screen.findByRole("heading", { name: "导出预览" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "下载导出" }));

    expect(await screen.findByText("待找发票导出超过 20000 行，请缩小筛选范围后重试。")).toBeInTheDocument();
    expect(screen.queryByText("已生成 pending-invoices.xlsx")).not.toBeInTheDocument();
  });

  test("keeps pending invoice rule draft and shows conflict feedback on stale version", async () => {
    const user = userEvent.setup();
    const fetchMock = installPendingInvoiceFetch({
      rulesSaveResponse: () => new Response(JSON.stringify({
        error: "pending_invoice_tag_groups_version_conflict",
        message: "待找发票规则已变化，请刷新后重试。",
      }), { status: 409, headers: { "Content-Type": "application/json" } }),
    });
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    await user.click(within(page).getByRole("button", { name: "支出待找发票规则设置" }));
    expect(await screen.findByRole("heading", { name: "支出待找发票规则设置" })).toBeInTheDocument();

    const noInvoiceGroup = screen.getByRole("group", { name: "无需开票" });
    const mealCheckbox = within(noInvoiceGroup).getByRole("checkbox", { name: "餐饮" });
    await user.click(mealCheckbox);
    expect(mealCheckbox).toBeChecked();

    await user.click(screen.getByRole("button", { name: "保存规则" }));
    expect(await screen.findByText("规则已被其他人更新。请刷新规则后再保存，当前勾选内容已保留。")).toBeInTheDocument();
    expect(within(noInvoiceGroup).getByRole("checkbox", { name: "餐饮" })).toBeChecked();

    const rulesPut = pendingInvoiceRulesRequests(fetchMock, "PUT")[0];
    const rulesBody = JSON.parse(String(rulesPut[1]?.body ?? "{}")) as {
      version?: number;
      direction?: string;
      groups?: Record<string, { tag_codes?: string[] }>;
    };
    expect(rulesBody.version).toBe(7);
    expect(rulesBody.direction).toBe("expense");
    expect(rulesBody.groups?.no_invoice_required?.tag_codes).toEqual(["salary", "custom_meal"]);
  });

  test("does not request OA detail when row only has a candidate relation id", async () => {
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    const candidateRow = await within(page).findByRole("row", { name: /候选OA供应商/ });
    const oaDetailButton = within(candidateRow).getByRole("button", { name: /OA详情 赵六/ });

    expect(oaDetailButton).toBeDisabled();

    const candidateDetailRequests = fetchMock.mock.calls
      .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
      .filter((url) => url.pathname.includes("/api/pending-invoices/oa/candidate"));
    expect(candidateDetailRequests).toHaveLength(0);
  });

  test("renders hierarchical pending invoice rule blocks with mutual exclusion", async () => {
    const user = userEvent.setup();
    installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    await user.click(within(page).getByRole("button", { name: "支出待找发票规则设置" }));

    expect(await screen.findByTestId("pending-invoice-rules-grid")).toBeInTheDocument();
    const bankStatementBlock = await screen.findByRole("group", { name: "流水代替发票" });
    const noInvoiceBlock = screen.getByRole("group", { name: "无需开票" });
    const requiresInvoiceBlock = screen.getByRole("group", { name: "需要开票" });
    const ruleLists = screen.getAllByTestId("pending-invoice-rule-list");
    expect(ruleLists).toHaveLength(3);
    ruleLists.forEach((list) => {
      expect(list).not.toHaveStyle({ overflowY: "auto" });
    });
    expect(within(bankStatementBlock).getByText("费用")).toBeInTheDocument();
    expect(within(bankStatementBlock).queryByRole("checkbox", { name: "费用" })).not.toBeInTheDocument();
    const bankStatementFee = within(bankStatementBlock).getByRole("checkbox", { name: "手续费" });
    expect(bankStatementFee).not.toBeChecked();
    expect(within(noInvoiceBlock).getByRole("checkbox", { name: "手续费" })).not.toBeDisabled();
    expect(within(requiresInvoiceBlock).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(requiresInvoiceBlock).getByText("自动归类")).toBeInTheDocument();
    const readonlyPrimaryLabels = within(requiresInvoiceBlock).getAllByTestId("pending-invoice-rule-primary-label");
    const readonlyTags = within(requiresInvoiceBlock).getAllByTestId("pending-invoice-rule-readonly-tag");
    const readonlyFeePrimary = readonlyPrimaryLabels.find((node) => node.textContent === "费用");
    expect(readonlyFeePrimary).toBeInTheDocument();
    expect(readonlyTags).not.toContain(readonlyFeePrimary);
    expect(readonlyTags.some((node) => node.textContent?.includes("手续费"))).toBe(true);
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

    const page = await findPendingInvoicesPage();
    await user.click(within(page).getByRole("button", { name: "支出待找发票规则设置" }));

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

    const page = await findPendingInvoicesPage();
    await user.click(within(page).getByRole("button", { name: "支出待找发票规则设置" }));

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
  }, 30_000);

  test("refetches rows after saving rules and displays refreshed rule filter buckets", async () => {
    const user = userEvent.setup();
    let rulesSaved = false;
    let releaseBarrier: (() => void) | null = null;
    const requiresRow = pendingRuleClosureRow("fee", "需要开票闭环供应商", "已支付待开票", "requires_invoice");
    const statementRow = pendingRuleClosureRow("internal_transfer", "流水代替闭环供应商", "流水代替发票", "bank_statement_as_invoice");
    const noInvoiceRow = pendingRuleClosureRow("salary", "无需开票闭环供应商", "无需开票", "no_invoice_required");
    const unknownRow = pendingRuleClosureRow("unknown_external_code", "未知标签闭环供应商", "未分类", "unknown");
    const barrierGate = new Promise<void>((resolve) => {
      releaseBarrier = resolve;
    });
    const fetchMock = installPendingInvoiceFetch({
      onRulesSaved: () => {
        rulesSaved = true;
      },
      operationBarrierResponse: async () => {
        await barrierGate;
        return new Response(JSON.stringify({
          status: "fresh",
          fresh: true,
          targets: [],
          blocked_targets: [],
          refreshing_targets: [],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      },
      rowsPayload: (url) => {
        if (!rulesSaved) {
          return upgradedRows();
        }
        const filter = url.searchParams.get("filter") ?? "all";
        if (filter === "requires_invoice") {
          return [requiresRow];
        }
        if (filter === "bank_statement_as_invoice") {
          return [statementRow];
        }
        if (filter === "no_invoice_required") {
          return [noInvoiceRow];
        }
        return [requiresRow, statementRow, noInvoiceRow, unknownRow];
      },
    });
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    await user.click(within(page).getByRole("button", { name: "筛选发票获取状态：已选 2 项" }));
    await user.click(await screen.findByRole("menuitem", { name: "清空" }));
    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      expect(latest?.searchParams.get("filter")).toBe("all");
    });
    await user.keyboard("{Escape}");
    const initialRequests = pendingInvoiceRowsRequests(fetchMock).length;
    await user.click(within(page).getByRole("button", { name: "支出待找发票规则设置" }));
    await user.click(await screen.findByRole("button", { name: "保存规则" }));

    await waitFor(() => {
      expect(operationBarrierRequests(fetchMock).at(-1)).toMatchObject({
        targets: [
          { read_model_key: "pending_invoice", scope_key: "expense:all" },
        ],
      });
    });
    expect(pendingInvoiceRowsRequests(fetchMock).length).toBe(initialRequests);
    releaseBarrier?.();

    await waitFor(() => {
      expect(rulesSaved).toBe(true);
      expect(pendingInvoiceRowsRequests(fetchMock).length).toBeGreaterThan(initialRequests);
    });
    expect(await within(page).findByText("需要开票闭环供应商")).toBeInTheDocument();
    expect(within(page).getByText("流水代替闭环供应商")).toBeInTheDocument();
    expect(within(page).getByText("无需开票闭环供应商")).toBeInTheDocument();
    expect(within(page).getByText("未知标签闭环供应商")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭规则抽屉" }));

    await user.click(within(page).getByRole("button", { name: "筛选发票获取状态：全部" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "流水代替发票" }));
    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      expect(latest?.searchParams.get("filter")).toBe("bank_statement_as_invoice");
      expect(within(page).getByText("流水代替闭环供应商")).toBeInTheDocument();
      expect(within(page).queryByText("需要开票闭环供应商")).not.toBeInTheDocument();
      expect(within(page).queryByText("无需开票闭环供应商")).not.toBeInTheDocument();
      expect(within(page).queryByText("未知标签闭环供应商")).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("menuitem", { name: "清空" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "无需开票" }));
    await waitFor(() => {
      const latest = pendingInvoiceRowsRequests(fetchMock).at(-1);
      expect(latest?.searchParams.get("filter")).toBe("no_invoice_required");
      expect(within(page).getByText("无需开票闭环供应商")).toBeInTheDocument();
      expect(within(page).queryByText("流水代替闭环供应商")).not.toBeInTheDocument();
      expect(within(page).queryByText("未知标签闭环供应商")).not.toBeInTheDocument();
    });
  }, 45_000);

  test("opens invoice picker from the selected-row toolbar, previews attach-existing, confirms, and refetches rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    const initialRequests = pendingInvoiceRowsRequests(fetchMock).length;
    await user.click(await within(page).findByRole("checkbox", { name: "选择流水 云南开票供应商" }));
    expect(within(page).getByText("已选 1 条流水")).toBeInTheDocument();
    await user.click(within(page).getByRole("button", { name: "选择发票" }));

    expect(await screen.findByRole("heading", { name: "选择已有进项发票" })).toBeInTheDocument();
    const candidateTable = await screen.findByRole("table", { name: "发票候选" });
    expect(within(candidateTable).getByRole("columnheader", { name: "流水关联" })).toBeInTheDocument();
    expect(within(candidateTable).queryByRole("columnheader", { name: "待支付" })).not.toBeInTheDocument();
    expect(await screen.findByText("DIG-CAND-001")).toBeInTheDocument();
    expect(within(candidateTable).getByText("未关联流水")).toBeInTheDocument();
    await user.type(screen.getByLabelText("销方"), "云南开票供应商");
    await user.click(screen.getByRole("button", { name: "搜索" }));
    await waitFor(() => {
      const candidateRequests = fetchMock.mock.calls
        .filter(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname === "/api/pending-invoices/invoice-candidates/batch");
      const latestBody = JSON.parse(String(candidateRequests.at(-1)?.[1]?.body ?? "{}"));
      expect(latestBody.seller_name).toBe("云南开票供应商");
      expect(latestBody.page_size).toBe(20);
    });
    await user.click(screen.getByRole("checkbox", { name: "选择发票 DIG-CAND-001" }));
    await user.click(screen.getByRole("button", { name: "预览关联" }));
    expect(await screen.findByText(/pending_invoice_attach_existing/)).toBeInTheDocument();
    expect(screen.getByText("关联后待付 0.00")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认建立关系" }));

    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname);
      expect(paths).toContain("/api/pending-invoices/attach-existing-invoices/preview");
      expect(paths).toContain("/api/pending-invoices/attach-existing-invoices");
      expect(paths).toContain("/api/operation-barrier/status");
      expect(pendingInvoiceRowsRequests(fetchMock).length).toBeGreaterThan(initialRequests);
    });
    const barrierCall = fetchMock.mock.calls.find(([input, init]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/operation-barrier/status" && (init?.method ?? "GET").toUpperCase() === "POST";
    });
    expect(JSON.parse(String(barrierCall?.[1]?.body ?? "{}")).targets).toEqual([
      { read_model_key: "workbench_relation", scope_key: "2026-05" },
      { read_model_key: "pending_invoice", scope_key: "expense:requires_invoice:2026-05" },
    ]);
  }, 45_000);

  test("shows preview conflicts and keeps confirm disabled when attach-existing cannot be confirmed", async () => {
    const user = userEvent.setup();
    installPendingInvoiceFetch({
      attachExistingInvoicesPreviewResponse: () => new Response(JSON.stringify({
        preview_id: "attach-preview-conflict",
        request_key: "pending_invoice_attach_existing_batch:conflict",
        can_confirm: false,
        transaction_summaries: [{
          id: "txn-paid-pending",
          counterparty_name: "云南开票供应商",
          trade_time: "2026-05-02",
          debit_amount: "1200.00",
        }],
        invoice_summaries: [{
          id: "inv-candidate",
          digital_invoice_no: "DIG-CAND-001",
          issue_date: "2026-05-06",
          seller_name: "云南开票供应商",
          seller_tax_no: "915300009999",
          total_with_tax: "1200.00",
        }],
        selection_summary: {
          transaction_count: 1,
          invoice_count: 1,
          bank_total: "1200.00",
          invoice_total: "1200.00",
          difference_amount: "0.00",
        },
        payment_impact: {
          paid_total_before: "0.00",
          paid_total_after: "1200.00",
          invoice_total: "1200.00",
          remaining_amount_after: "0.00",
          difference_amount_after: "0.00",
        },
        affected_months: ["2026-05"],
        warnings: [],
        conflicts: [{
          relation_case_id: "case-conflict",
          relation_mode: "manual_confirmed",
          row_ids: ["claim-001", "inv-candidate"],
        }],
        expires_at: "2026-05-25T10:10:00+08:00",
      }), { status: 200, headers: { "Content-Type": "application/json" } }),
    });
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    await user.click(await within(page).findByRole("checkbox", { name: "选择流水 云南开票供应商" }));
    await user.click(within(page).getByRole("button", { name: "选择发票" }));
    await user.click(await screen.findByRole("checkbox", { name: "选择发票 DIG-CAND-001" }));
    await user.click(screen.getByRole("button", { name: "预览关联" }));

    expect(await screen.findByText("不可确认原因")).toBeInTheDocument();
    expect(screen.getByText("关系 case-conflict，模式 manual_confirmed，对象 claim-001, inv-candidate")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认建立关系" })).toBeDisabled();
  }, 45_000);

  test("selects multiple expense rows and multiple invoices from the existing invoice drawer", async () => {
    const user = userEvent.setup();
    const fetchMock = installPendingInvoiceFetch({
      rowsPayload: () => [upgradedRows()[0], batchAttachRow()],
    });
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    const initialRequests = pendingInvoiceRowsRequests(fetchMock).length;
    await user.click(await within(page).findByRole("checkbox", { name: "选择流水 云南开票供应商" }));
    await user.click(await within(page).findByRole("checkbox", { name: "选择流水 云南开票供应商二号" }));

    expect(within(page).getByText("已选 2 条流水")).toBeInTheDocument();
    expect(within(page).getByText("流水合计 1,236.00")).toBeInTheDocument();
    await user.click(within(page).getByRole("button", { name: "选择发票" }));

    expect(await screen.findByRole("heading", { name: "选择已有进项发票" })).toBeInTheDocument();
    expect(screen.getByText("已选流水金额")).toBeInTheDocument();
    expect(screen.getByText("1,236.00")).toBeInTheDocument();
    await user.click(await screen.findByRole("checkbox", { name: "选择发票 DIG-CAND-001" }));
    await user.click(await screen.findByRole("checkbox", { name: "选择发票 DIG-CAND-002" }));
    expect(screen.getByText("已选发票金额")).toBeInTheDocument();
    expect(screen.getByText("本次选择差额")).toBeInTheDocument();
    expect(screen.getByText("0.00")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "预览关联" }));
    expect(await screen.findByText("pending_invoice_attach_existing_batch:multi")).toBeInTheDocument();
    expect(screen.getByText("关联后待付")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认建立关系" }));

    await waitFor(() => {
      const previewCall = fetchMock.mock.calls.find(([input]) => (
        new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname === "/api/pending-invoices/attach-existing-invoices/preview"
      ));
      const confirmCall = fetchMock.mock.calls.find(([input]) => (
        new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname === "/api/pending-invoices/attach-existing-invoices"
      ));
      expect(JSON.parse(String(previewCall?.[1]?.body ?? "{}"))).toMatchObject({
        transaction_ids: ["txn-paid-pending", "txn-paid-pending-2"],
        invoice_ids: ["inv-candidate", "inv-candidate-2"],
      });
      expect(JSON.parse(String(confirmCall?.[1]?.body ?? "{}"))).toMatchObject({
        transaction_ids: ["txn-paid-pending", "txn-paid-pending-2"],
        invoice_ids: ["inv-candidate", "inv-candidate-2"],
      });
      expect(pendingInvoiceRowsRequests(fetchMock).length).toBeGreaterThan(initialRequests);
    });
  }, 45_000);

  test("selects income rows and batch marks invoice status from the toolbar", async () => {
    const user = userEvent.setup();
    const firstIncomeRow = {
      ...pendingRuleClosureRow("income-batch-a", "收入批量客户A", "未开票", "requires_invoice"),
      bank_transaction: {
        ...pendingRuleClosureRow("income-batch-a", "收入批量客户A", "未开票", "requires_invoice").bank_transaction,
        debit_amount: "0.00",
        credit_amount: "300.00",
        amount: "300.00",
        effective_tag_primary_label: "收入",
        effective_tag_sub_label: "服务收入",
        effective_tag_label_path: ["收入", "服务收入"],
      },
      invoice_acquisition_status: {
        code: "income_pending_invoice",
        label: "未开票",
        reason: "收入流水未关联销项发票。",
        severity: "warning",
        primary_action: "mark_income_status",
        matched_rule: { source: "pending_output_invoice_tag_groups", group: "requires_invoice", tag_code: "income-batch-a", tag_label: "服务收入" },
      },
      can_create_invoice: false,
      available_actions: ["mark_income_status"],
    };
    const secondIncomeRow = {
      ...firstIncomeRow,
      id: "income-batch-b",
      bank_transaction: {
        ...firstIncomeRow.bank_transaction,
        id: "income-batch-b",
        counterparty_name: "收入批量客户B",
        credit_amount: "200.00",
        amount: "200.00",
      },
    };
    const fetchMock = installPendingInvoiceFetch({
      rowsPayload: (url) => (url.searchParams.get("direction") === "income" ? [firstIncomeRow, secondIncomeRow] : upgradedRows()),
    });
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    await user.click(await within(page).findByRole("button", { name: "收入 75" }));
    await within(page).findByText("收入批量客户A");
    expect(within(page).queryByRole("button", { name: "标记无需开票" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "标记现金收入" })).not.toBeInTheDocument();

    await user.click(await within(page).findByRole("checkbox", { name: "选择流水 收入批量客户A" }));
    await user.click(await within(page).findByRole("checkbox", { name: "选择流水 收入批量客户B" }));

    expect(within(page).getByText("已选 2 条流水")).toBeInTheDocument();
    expect(within(page).getByText("流水合计 500.00")).toBeInTheDocument();
    await user.click(within(page).getByRole("button", { name: "标记现金收入" }));

    await waitFor(() => {
      const batchCall = fetchMock.mock.calls.find(([input]) => (
        new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname === "/api/pending-invoices/income-statuses"
      ));
      expect(JSON.parse(String(batchCall?.[1]?.body ?? "{}"))).toMatchObject({
        transaction_ids: ["income-batch-a", "income-batch-b"],
        status_code: "cash_income",
      });
      expect(pendingInvoiceRowsRequests(fetchMock).length).toBeGreaterThan(2);
    });
  }, 45_000);

  test("does not expose manual invoice dialog or API calls", async () => {
    const fetchMock = installPendingInvoiceFetch();
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    const pendingRow = await within(page).findByRole("row", { name: /云南开票供应商/ });

    expect(within(pendingRow).queryByRole("button", { name: "云南开票供应商 发票获取操作" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "手工补录发票" })).not.toBeInTheDocument();
    expect(screen.queryByText("补票")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.map(([input]) => (
      new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname
    ))).not.toEqual(expect.arrayContaining([
      "/api/pending-invoices/manual-invoices/preview",
      "/api/pending-invoices/manual-invoices",
    ]));
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

  test("keeps row status actions available while the list read model is refreshing", async () => {
    const user = userEvent.setup();
    installPendingInvoiceFetch({ readModelStatus: "refreshing" });
    renderAppAt("/pending-invoices");

    const page = await findPendingInvoicesPage();
    expect(await within(page).findByText("数据刷新中")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "筛选内容导出" })).toBeDisabled();

    const pendingRow = await within(page).findByRole("row", { name: /云南开票供应商/ });
    await user.click(within(pendingRow).getByRole("checkbox", { name: "选择流水 云南开票供应商" }));
    expect(within(page).getByRole("button", { name: "选择发票" })).toBeEnabled();
    expect(within(pendingRow).queryByRole("button", { name: "云南开票供应商 发票获取操作" })).not.toBeInTheDocument();
    expect(screen.queryByText("补票")).not.toBeInTheDocument();
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
