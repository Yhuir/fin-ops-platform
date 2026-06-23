import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { sidebarGroups } from "../components/shell/sidebarItems";
import { renderAuthenticatedAppAt } from "./renderHelpers";

const oaPendingPaymentsSourceFiles = [
  "src/pages/OaPendingPaymentsPage.tsx",
  "src/components/oaPendingPayments/OaPendingPaymentsTable.tsx",
] as const;

const rowsPayload = {
  rows: [
    {
      id: "oa-payment-row-001",
      oa: {
        id: "oa-001",
        applicantName: "张三",
        applicationType: "报销",
        projectName: "红河卷烟厂能源管理系统运维服务",
        applicationTime: "2026-01-03",
        amount: "10000.00",
        detailAvailable: true,
        reason: "红河卷烟厂运维服务保证金",
        counterpartyName: "中招国际招标有限公司云南分公司",
        workflowStatus: "completed",
      },
      paymentStatus: {
        code: "partially_paid",
        label: "支付少了",
        reason: "支出流水合计小于 OA 金额",
      },
      bankTransaction: {
        primaryBankTransactionId: "bank-001",
        accountDetailNo: "13288-5309050389CU4G9VQJG",
        enterpriseSerialNo: "",
        voucherKind: "电子转账凭证",
        voucherNo: "108102947921",
        bankName: "建设银行",
        accountNo: "622200001234",
        accountLast4: "1234",
        directionLabel: "支出",
        accountName: "云南溯源科技有限公司",
        tradeTime: "20260105 09:50:25",
        debitAmount: "10000.00",
        creditAmount: "0.00",
        balance: "144698.00",
        currency: "人民币元",
        counterpartyName: "中招国际招标有限公司云南分公司",
        counterpartyAccountNo: "2502124119024521401",
        counterpartyBankName: "中国工商银行股份有限公司昆明花园支行",
        bookedDate: "20260105",
        summary: "电子转账",
        remark: "红河卷烟厂2025-2028年度能源管理相关系统运维服务采购项目保证金",
        relationCount: 1,
        hasMultiple: false,
        detailMode: "single",
      },
      invoice: {
        primaryInvoiceId: "inv-001",
        digitalInvoiceNo: "26532000000123456789",
        sellerName: "云南恒昆机电设备有限公司",
        invoiceDate: "2026-01-08",
        totalWithTax: "10000.00",
        relationCount: 1,
        hasMultiple: false,
        detailMode: "single",
      },
    },
    {
      id: "oa-payment-group-case-001",
      oa: {
        id: "oa-group-001",
        primaryOaId: "oa-group-001",
        applicantName: "刘际涛",
        applicationType: "支付申请",
        projectName: "昭通卷烟厂能源集控平台维护",
        applicationTime: "2026-01-20 02:51:26",
        amount: "4450.00",
        detailAvailable: true,
        workflowStatus: "completed",
        relationCount: 3,
        hasMultiple: true,
        detailMode: "list",
        summaries: [
          {
            oaId: "oa-group-001",
            applicantName: "刘际涛",
            applicationType: "支付申请",
            projectName: "昭通卷烟厂2023-2025年度能源集控平台系统维护",
            applicationTime: "2026-01-20 02:51:26",
            amount: "1690.00",
            relationCaseId: "case-group-001",
          },
          {
            oaId: "oa-group-002",
            applicantName: "刘际涛",
            applicationType: "支付申请",
            projectName: "红塔集团2025年度信息化不可预见维护采购项目",
            applicationTime: "2026-01-20 02:50:23",
            amount: "1980.00",
            relationCaseId: "case-group-001",
          },
          {
            oaId: "oa-group-003",
            applicantName: "刘际涛",
            applicationType: "支付申请",
            projectName: "昭通卷烟厂2025-2028年度能源集控平台维护采购项目",
            applicationTime: "2026-01-20 02:51:06",
            amount: "780.00",
            relationCaseId: "case-group-001",
          },
        ],
      },
      paymentStatus: {
        code: "paid",
        label: "已支付",
        reason: "关联台配对组内支出流水合计等于 OA 合计金额",
      },
      oaPaymentWriteback: {
        code: "written",
        label: "已写回",
        flowIds: ["proc-group-001"],
        syncStatus: "ready",
      },
      bankTransaction: {
        primaryBankTransactionId: "bank-002",
        accountDetailNo: "multi-bank-main",
        enterpriseSerialNo: "",
        voucherKind: "电子转账凭证",
        voucherNo: "multi-voucher",
        bankName: "建设银行",
        accountNo: "622200005678",
        accountLast4: "5678",
        bankAccount: "建设银行 5678",
        directionLabel: "支出",
        accountName: "云南溯源科技有限公司",
        tradeTime: "2026-01-20 10:42:09",
        debitAmount: "3000.00",
        creditAmount: "0.00",
        balance: "129698.00",
        currency: "人民币元",
        counterpartyName: "张丽芬",
        counterpartyAccountNo: "2502124119024521402",
        counterpartyBankName: "中国建设银行昆明支行",
        bookedDate: "20260106",
        summary: "住宿费",
        remark: "昭通市昭阳区豪然精品酒店",
        amount: "3000.00",
        paidTotal: "4450.00",
        relationCount: 2,
        hasMultiple: true,
        detailMode: "list",
        summaries: [
          {
            bankTransactionId: "bank-002",
            bankName: "建设银行",
            accountNo: "622200005678",
            accountLast4: "5678",
            bankAccount: "建设银行 5678",
            directionLabel: "支出",
            tradeTime: "2026-01-20 10:42:09",
            amount: "3000.00",
            counterpartyName: "张丽芬",
            summary: "住宿费",
            remark: "昭通市昭阳区豪然精品酒店",
            relationCaseId: "case-group-001",
          },
          {
            bankTransactionId: "bank-003",
            bankName: "建设银行",
            accountNo: "622200009999",
            accountLast4: "9999",
            bankAccount: "建设银行 9999",
            directionLabel: "支出",
            tradeTime: "2026-01-20 11:20:00",
            amount: "1450.00",
            counterpartyName: "张丽芬",
            summary: "补充住宿费",
            remark: "补充流水备注",
            relationCaseId: "case-group-001",
          },
        ],
      },
      invoice: {
        primaryInvoiceId: "inv-002",
        digitalInvoiceNo: "2653400000008252281",
        sellerName: "昭通市昭阳区豪然精品酒店",
        invoiceDate: "2026-01-20",
        totalWithTax: "4450.00",
        relationCount: 2,
        hasMultiple: true,
        detailMode: "list",
        summaries: [
          {
            invoiceId: "inv-002",
            digitalInvoiceNo: "2653400000008252281",
            sellerName: "昭通市昭阳区豪然精品酒店",
            invoiceDate: "2026-01-20",
            totalWithTax: "3000.00",
            relationCaseId: "case-group-001",
          },
          {
            invoiceId: "inv-003",
            digitalInvoiceNo: "2653400000008252282",
            sellerName: "昭通市昭阳区豪然精品酒店",
            invoiceDate: "2026-01-20",
            totalWithTax: "1450.00",
            relationCaseId: "case-group-001",
          },
        ],
      },
    },
    {
      id: "oa-payment-row-003",
      oa: {
        id: "oa-003",
        applicantName: "王五",
        applicationType: "付款",
        projectName: "未关联发票项目",
        applicationTime: "2026-01-05",
        amount: "18200.00",
        detailAvailable: true,
        workflowStatus: "completed",
      },
      paymentStatus: {
        code: "paid",
        label: "已支付",
        reason: "支出流水合计等于 OA 金额",
      },
      bankTransaction: {
        primaryBankTransactionId: "bank-004",
        accountDetailNo: "no-invoice-bank",
        enterpriseSerialNo: "",
        voucherKind: "电子转账凭证",
        voucherNo: "no-invoice-voucher",
        bankName: "交通银行",
        accountNo: "622200003847",
        accountLast4: "3847",
        directionLabel: "支出",
        accountName: "云南溯源科技有限公司",
        tradeTime: "20260107 09:50:25",
        debitAmount: "18200.00",
        creditAmount: "0.00",
        balance: "111698.00",
        currency: "人民币元",
        counterpartyName: "无发票供应商",
        counterpartyAccountNo: "2502124119024521404",
        counterpartyBankName: "交通银行昆明支行",
        bookedDate: "20260107",
        summary: "货款",
        remark: "",
        relationCount: 1,
        hasMultiple: false,
        detailMode: "single",
      },
      invoice: {
        primaryInvoiceId: null,
        digitalInvoiceNo: "",
        sellerName: "",
        invoiceDate: "",
        totalWithTax: "",
        relationCount: 0,
        hasMultiple: false,
        detailMode: "none",
      },
    },
    {
      id: "oa-payment-row-004",
      oa: {
        id: "oa-004",
        applicantName: "杨丽萍",
        applicationType: "支付申请",
        projectName: "大理卷烟厂余热综合利用项目",
        applicationTime: "2026-05-23",
        amount: "977.00",
        detailAvailable: true,
        workflowStatus: "completed",
      },
      paymentStatus: {
        code: "unpaid",
        label: "未支付",
        reason: "未关联支出流水",
      },
      bankTransaction: {
        primaryBankTransactionId: null,
        accountDetailNo: "",
        enterpriseSerialNo: "",
        voucherKind: "",
        voucherNo: "",
        bankName: "",
        accountNo: "",
        accountLast4: "",
        bankAccount: "",
        directionLabel: "支出",
        accountName: "",
        tradeTime: "",
        debitAmount: "0.00",
        creditAmount: "0.00",
        balance: "",
        currency: "",
        counterpartyName: "",
        counterpartyAccountNo: "",
        counterpartyBankName: "",
        bookedDate: "",
        summary: "",
        remark: "",
        amount: "0.00",
        paidTotal: "0.00",
        relationCount: 0,
        hasMultiple: false,
        detailMode: "none",
      },
      invoice: {
        primaryInvoiceId: null,
        digitalInvoiceNo: "",
        sellerName: "",
        invoiceDate: "",
        totalWithTax: "",
        relationCount: 0,
        hasMultiple: false,
        detailMode: "none",
      },
    },
    {
      id: "oa-payment-row-candidate",
      oa: {
        id: "oa-candidate",
        primaryOaId: "oa-candidate",
        applicantName: "候选付款人",
        applicationType: "支付申请",
        projectName: "候选流水展示项目",
        applicationTime: "2026-05-24",
        amount: "977.00",
        detailAvailable: true,
        workflowStatus: "in_progress",
      },
      paymentStatus: {
        code: "unpaid",
        label: "未支付",
        reason: "候选流水不计入已支付金额",
      },
      bankTransaction: {
        primaryBankTransactionId: "bank-candidate-004",
        accountDetailNo: "candidate-bank-004",
        enterpriseSerialNo: "",
        voucherKind: "",
        voucherNo: "",
        bankName: "建设银行",
        accountNo: "",
        accountLast4: "8106",
        bankAccount: "建设银行 8106",
        directionLabel: "支出",
        accountName: "",
        tradeTime: "2026-05-24 12:00:00",
        debitAmount: "977.00",
        creditAmount: "0.00",
        balance: "",
        currency: "",
        counterpartyName: "候选供应商",
        counterpartyAccountNo: "",
        counterpartyBankName: "",
        bookedDate: "",
        summary: "候选支付流水",
        remark: "",
        amount: "977.00",
        paidTotal: "0.00",
        relationStatus: "candidate",
        relationCount: 1,
        hasMultiple: false,
        detailMode: "single",
      },
      invoice: {
        primaryInvoiceId: null,
        digitalInvoiceNo: "",
        sellerName: "",
        invoiceDate: "",
        totalWithTax: "",
        relationCount: 0,
        hasMultiple: false,
        detailMode: "none",
      },
    },
  ],
  pagination: { page: 1, pageSize: 20, total: 51 },
  summary: { rowCount: 51, viewCounts: { completed: 51, in_progress: 23 } },
  filterConfig: [
    {
      field: "oa_applicant",
      label: "OA申请人",
      mode: "enum_multi",
      sortable: true,
      operators: ["in"],
    },
    {
      field: "oa_project_name",
      label: "项目名称",
      mode: "enum_multi",
      sortable: true,
      operators: ["in"],
    },
    {
      field: "payment_status",
      label: "支付状态",
      mode: "enum_multi",
      sortable: true,
      operators: ["in"],
    },
    {
      field: "bank_counterparty_name",
      label: "对方户名",
      mode: "enum_multi",
      sortable: true,
      operators: ["in"],
    },
    {
      field: "bank_trade_time",
      label: "交易时间",
      mode: "date",
      sortable: true,
      operators: ["between", "equals"],
    },
    {
      field: "bank_account",
      label: "银行账户",
      mode: "enum_multi",
      sortable: false,
      operators: ["in"],
    },
    {
      field: "bank_direction",
      label: "收支",
      mode: "enum_multi",
      sortable: false,
      operators: ["in"],
    },
    {
      field: "seller_name",
      label: "发票方",
      mode: "enum_multi",
      sortable: true,
      operators: ["in"],
    },
    {
      field: "invoice_date",
      label: "开票日期",
      mode: "date",
      sortable: true,
      operators: ["between", "equals"],
    },
  ],
};

function installOaPendingPaymentsFetch(overrides?: {
  rowsPayload?: Record<string, unknown>;
  detailPayloads?: Record<string, { status: number; payload: Record<string, unknown> }>;
  operationBarrierDelay?: Promise<void>;
  rulesCanSave?: boolean;
  autoReconcilePayload?: Record<string, unknown>;
  autoReconcileResponses?: Array<{ status: number; payload: Record<string, unknown> }>;
}) {
  const autoReconcileResponses = [...(overrides?.autoReconcileResponses ?? [])];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    const detailPayload = overrides?.detailPayloads?.[url.pathname];
    if (detailPayload) {
      return new Response(JSON.stringify(detailPayload.payload), {
        status: detailPayload.status,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/oa-pending-payments/rows") {
      const payload: Record<string, unknown> = overrides?.rowsPayload ?? rowsPayload;
      const readModelStatus = payload.readModelStatus ?? payload.read_model_status;
      return new Response(JSON.stringify(payload), {
        status: readModelStatus === "refreshing" ? 202 : 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/operation-barrier/status") {
      await overrides?.operationBarrierDelay;
      return new Response(JSON.stringify({
        status: "fresh",
        fresh: true,
        targets: [
          {
            read_model_key: "oa_pending_payment",
            scope_type: "oa_pending_payment",
            scope_key: "all",
            status: "fresh",
            fresh: true,
            blocking: false,
            raw_status: "fresh",
          },
        ],
        blocked_targets: [],
        refreshing_targets: [],
      }), {
        status: init?.method === "POST" ? 200 : 405,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/oa-pending-payments/confirm-paid") {
      return new Response(JSON.stringify({
        success: true,
        action: "confirm_paid",
        oaRowId: "oa-candidate",
        bankTransactionIds: ["bank-candidate-004"],
        paymentStatus: { code: "paid", label: "已支付", reason: "已确认支出流水" },
        oaPaymentWriteback: { code: "written", label: "已写回", flowIds: ["proc-candidate"], syncStatus: "ready" },
        readModelRefresh: { scopeKeys: ["2026-05", "all"], enqueued: true, targetSeconds: 2 },
      }), {
        status: init?.method === "POST" ? 200 : 405,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/oa-pending-payments/auto-reconcile-bank-transactions") {
      const scriptedResponse = autoReconcileResponses.shift();
      const status = scriptedResponse?.status ?? (init?.method === "POST" ? 200 : 405);
      return new Response(JSON.stringify(scriptedResponse?.payload ?? overrides?.autoReconcilePayload ?? {
        success: true,
        action: "oa_pending_payment_auto_reconcile_bank_transactions",
        autoMatchedCount: 0,
        writebackCount: 0,
        readModelRefresh: { scopeKeys: ["all"], enqueued: false, targetSeconds: 2 },
      }), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/oa-pending-payments/bank-transaction-candidates") {
      return new Response(JSON.stringify({
        rows: [
          {
            id: "bank-drawer-001",
            counterpartyName: "抽屉供应商",
            tradeTime: "2026-05-25 09:30:00",
            amount: "977.00",
            bankAccount: "建设银行 8106",
            directionLabel: "支出",
            summary: "抽屉支出流水",
            relationStatus: "unmatched",
            relationStatusLabel: "未配对",
          },
          {
            id: "bank-drawer-progress",
            counterpartyName: "已关联供应商",
            tradeTime: "2026-05-26 09:30:00",
            amount: "100.00",
            bankAccount: "光大银行 8826",
            directionLabel: "支出",
            summary: "已关联进行中OA流水",
            relationStatus: "linked_in_progress",
            relationStatusLabel: "已关联进行中OA",
          },
        ],
        pagination: { page: 1, pageSize: 100, total: 2 },
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/oa-pending-payments/link-bank-transactions") {
      return new Response(JSON.stringify({
        success: true,
        action: "oa_pending_payment_link_bank_transactions",
        oaRowIds: ["oa-candidate"],
        bankTransactionIds: ["bank-drawer-001"],
        relation: { status: "confirmed" },
        autoWriteback: { code: "written", label: "已写回", matched: true, writebackCount: 1 },
        oaPaymentWritebacks: [{ code: "written", label: "已写回", flowId: "proc-candidate", syncStatus: "ready" }],
        readModelRefresh: { scopeKeys: ["2026-05", "all"], enqueued: true, targetSeconds: 2 },
      }), {
        status: init?.method === "POST" ? 200 : 405,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/oa-pending-payments/filter-options") {
      return new Response(JSON.stringify({
        fields: [
          {
            field: "oa_applicant",
            label: "OA申请人",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "张三", label: "张三", count: 1 }],
          },
          {
            field: "oa_application_type",
            label: "类型",
            mode: "enum_multi",
            sortable: false,
            operators: ["in"],
            options: [{ value: "报销", label: "报销", count: 1 }],
          },
          {
            field: "payment_status",
            label: "支付状态",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "partially_paid", label: "支付少了", count: 1 }],
          },
          {
            field: "oa_project_name",
            label: "项目名称",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "红河卷烟厂能源管理系统运维服务", label: "红河卷烟厂能源管理系统运维服务", count: 1 }],
          },
          {
            field: "bank_counterparty_name",
            label: "对方户名",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "中招国际招标有限公司云南分公司", label: "中招国际招标有限公司云南分公司", count: 1 }],
          },
          {
            field: "bank_trade_time",
            label: "交易时间",
            mode: "date",
            sortable: true,
            operators: ["between", "equals"],
            options: [],
          },
          {
            field: "bank_account",
            label: "银行账户",
            mode: "enum_multi",
            sortable: false,
            operators: ["in"],
            options: [{ value: "建设银行 1234", label: "建设银行 1234", count: 1 }],
          },
          {
            field: "bank_direction",
            label: "收支",
            mode: "enum_multi",
            sortable: false,
            operators: ["in"],
            options: [{ value: "outflow", label: "支出", count: 2 }],
          },
          {
            field: "seller_name",
            label: "发票方",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "云南恒昆机电设备有限公司", label: "云南恒昆机电设备有限公司", count: 1 }],
          },
          {
            field: "invoice_date",
            label: "开票日期",
            mode: "date",
            sortable: true,
            operators: ["between", "equals"],
            options: [],
          },
        ],
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/oa-pending-payments/oa/oa-001/detail") {
      return new Response(JSON.stringify({
        title: "OA详情",
        subtitle: "oa-001",
        detailAvailable: true,
        sections: [{ title: "OA信息", fields: [{ label: "申请人", value: "张三" }] }],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/oa-pending-payments/bank-transactions/bank-001/detail") {
      return new Response(JSON.stringify({
        title: "支出流水详情",
        subtitle: "bank-001",
        detailAvailable: true,
        sections: [{ title: "流水信息", fields: [{ label: "支出银行", value: "建设银行" }] }],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/oa-pending-payments/invoices/inv-001/detail") {
      return new Response(JSON.stringify({
        title: "发票详情",
        subtitle: "inv-001",
        detailAvailable: true,
        sections: [{ title: "发票情况", fields: [{ label: "进项发票方名称", value: "云南恒昆机电设备有限公司" }] }],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/oa-pending-payments/rows/oa-payment-group-case-001/relation-details") {
      const kind = url.searchParams.get("kind");
      const title = kind === "oa" ? "OA关联明细" : kind === "invoice" ? "发票关联明细" : "支出流水关联明细";
      const sectionTitle = kind === "oa" ? "OA 1" : kind === "invoice" ? "发票 1" : "流水 1";
      return new Response(JSON.stringify({
        title,
        subtitle: "刘际涛",
        detailAvailable: true,
        sections: [{ title: sectionTitle, fields: [{ label: "数量", value: kind === "oa" ? "3" : "2" }] }],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/rules") {
      const canSave = overrides?.rulesCanSave ?? false;
      return new Response(JSON.stringify({
        version: 1,
        direction: "expense",
        available_tags: [],
        groups: {
          requires_invoice: { tag_codes: [], tags: [] },
          bank_statement_as_invoice: { tag_codes: [], tags: [] },
          no_invoice_required: { tag_codes: [], tags: [] },
        },
        permissions: { can_save: canSave },
        read_model_status: "refreshing",
      }), { status: init?.method === "PUT" ? 200 : 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function rowsRequests(fetchMock: ReturnType<typeof installOaPendingPaymentsFetch>) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === "/api/oa-pending-payments/rows");
}

function rulesRequests(fetchMock: ReturnType<typeof installOaPendingPaymentsFetch>) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === "/api/pending-invoices/rules");
}

function rulesSaveRequests(fetchMock: ReturnType<typeof installOaPendingPaymentsFetch>) {
  return fetchMock.mock.calls.filter(([input, init]) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    return url.pathname === "/api/pending-invoices/rules" && init?.method === "PUT";
  });
}

function autoReconcileRequests(fetchMock: ReturnType<typeof installOaPendingPaymentsFetch>) {
  return fetchMock.mock.calls.filter(([input]) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    return url.pathname === "/api/oa-pending-payments/auto-reconcile-bank-transactions";
  });
}

function bankCandidateRequests(fetchMock: ReturnType<typeof installOaPendingPaymentsFetch>) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === "/api/oa-pending-payments/bank-transaction-candidates");
}

function linkBankRequests(fetchMock: ReturnType<typeof installOaPendingPaymentsFetch>) {
  return fetchMock.mock.calls.filter(([input]) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    return url.pathname === "/api/oa-pending-payments/link-bank-transactions";
  });
}

function operationBarrierRequests(fetchMock: ReturnType<typeof installOaPendingPaymentsFetch>) {
  return fetchMock.mock.calls.filter(([input]) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    return url.pathname === "/api/operation-barrier/status";
  });
}

function deferred<T = void>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

function readWebSource(path: string) {
  return readFileSync(resolve(path), "utf8");
}

function cssRule(source: string, selector: string) {
  const normalizedSelector = selector.replace(/\\n/g, "\n");
  const escapedSelector = normalizedSelector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`, "m"));
  return match?.[1] ?? "";
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("OA pending payments page", () => {
  test("targets project primitives for page shell and grouped table", () => {
    const sourceByPath = Object.fromEntries(oaPendingPaymentsSourceFiles.map((path) => [path, readWebSource(path)]));
    const forbiddenMuiImports = oaPendingPaymentsSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /from ["']@mui\/|import\s+[^;]*@mui\//.test(source) ? [path] : [];
    });
    const forbiddenMuiSelectors = oaPendingPaymentsSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /\.Mui[A-Z][A-Za-z-]*/.test(source) ? [path] : [];
    });
    const forbiddenLegacySurfaces = oaPendingPaymentsSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /TablePagination|TextField|Skeleton|Chip|IconButton|TableCell|TableRow|TableHead|TableBody/.test(source) ? [path] : [];
    });
    const missingPrimitiveTargets = [
      sourceByPath["src/pages/OaPendingPaymentsPage.tsx"].includes("PageScaffold") ? null : "OaPendingPaymentsPage.tsx should keep PageScaffold",
      sourceByPath["src/pages/OaPendingPaymentsPage.tsx"].includes("StatePanel") ? null : "OaPendingPaymentsPage.tsx should keep project empty/error state primitives",
      sourceByPath["src/components/oaPendingPayments/OaPendingPaymentsTable.tsx"].includes("InputInvoiceUsageFilterMenu")
        ? null
        : "OaPendingPaymentsTable.tsx should preserve shared InputInvoiceUsageFilterMenu contract",
      /FinanceTable|oa-pending-payments-table/.test(sourceByPath["src/components/oaPendingPayments/OaPendingPaymentsTable.tsx"])
        ? null
        : "OaPendingPaymentsTable.tsx should use a project table primitive or project table class",
    ].filter(Boolean);

    expect({
      forbiddenMuiImports,
      forbiddenMuiSelectors,
      forbiddenLegacySurfaces,
      missingPrimitiveTargets,
    }).toEqual({
      forbiddenMuiImports: [],
      forbiddenMuiSelectors: [],
      forbiddenLegacySurfaces: [],
      missingPrimitiveTargets: [],
    });
  });

  test("keeps premium compact table and interaction CSS contracts", () => {
    const styles = readWebSource("src/app/styles.css");
    const button = cssRule(styles, ".oa-pending-payments-button");
    const fieldControls = cssRule(styles, ".oa-pending-payments-field input,\\n.oa-pending-payments-field select");
    const tableShell = cssRule(styles, ".oa-pending-payments-table-shell");
    const loading = cssRule(styles, ".oa-pending-payments-loading__bar,\\n.oa-pending-payments-loading__panel");
    const detailButton = cssRule(styles, ".oa-pending-payments-detail-button");
    const sortButton = cssRule(styles, ".oa-pending-payments-sort-button");
    const paginationButton = cssRule(styles, ".oa-pending-payments-pagination-actions button");
    const viewToggle = cssRule(styles, ".oa-pending-payments-view-toggle");
    const writebackLine = cssRule(styles, ".oa-pending-payments-writeback-line");
    const tableCell = cssRule(styles, ".oa-pending-payments-table-cell");
    const invoiceColumn = cssRule(styles, ".oa-pending-payments-col-invoice");
    const statusColumn = cssRule(styles, ".oa-pending-payments-col-paymentStatus");
    const oaGrid = cssRule(styles, ".oa-pending-payments-oa-grid");
    const bankGrid = cssRule(styles, ".oa-pending-payments-bank-grid");
    const invoiceStack = cssRule(styles, ".oa-pending-payments-invoice-stack");
    const statusActionLine = cssRule(styles, ".oa-pending-payments-status-action-line");
    const successAlert = cssRule(styles, ".oa-pending-payments-alert--success");
    const groupOa = cssRule(styles, ".oa-pending-payments-table-group-header--oa");
    const groupStatus = cssRule(styles, ".oa-pending-payments-table-group-header--status");
    const groupBank = cssRule(styles, ".oa-pending-payments-table-group-header--bank");

    expect(button).toContain("var(--motion-fast)");
    expect(button).toContain("var(--ease-out-quart)");
    expect(fieldControls).toContain("var(--motion-fast)");
    expect(tableShell).toContain("min-height: 320px");
    expect(tableShell).toContain("max-height: calc(100vh - 214px)");
    expect(loading).toContain("border-radius: var(--fp-radius-sm)");
    expect(detailButton).toContain("var(--motion-fast)");
    expect(sortButton).toContain("var(--motion-fast)");
    expect(paginationButton).toContain("var(--motion-fast)");
    expect(viewToggle).toContain("display: inline-flex");
    expect(writebackLine).toContain("flex-wrap: wrap");
    expect(tableCell).toContain("font-size: 10.5px");
    expect(invoiceColumn).toContain("width: 13%");
    expect(statusColumn).toContain("width: 8%");
    expect(oaGrid).toContain("display: grid");
    expect(oaGrid).toContain("grid-template-columns: minmax(0, 0.73fr)");
    expect(bankGrid).toContain("display: grid");
    expect(bankGrid).toContain("grid-template-columns");
    expect(invoiceStack).toContain("display: grid");
    expect(statusActionLine).toContain("flex-wrap: wrap");
    expect(successAlert).toContain("var(--fp-success-soft)");
    expect(groupOa).toContain("color-mix(in srgb, var(--fp-surface-muted)");
    expect(groupStatus).toContain("color-mix(in srgb, var(--fp-warning-soft)");
    expect(groupBank).toContain("color-mix(in srgb, var(--fp-primary-soft)");
  });

  test("keeps bank amount and direction chip in a non-overlapping layout slot", async () => {
    installOaPendingPaymentsFetch();

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await within(page).findByText("张三");
    const row = within(page).getByRole("row", { name: /张三/ });
    const bankCell = row.querySelector(".oa-pending-payments-table-cell--bank") as HTMLElement;
    const amountLine = bankCell.querySelector(".oa-pending-payments-bank-amount-line");

    expect(bankCell).not.toBeNull();
    expect(amountLine).not.toBeNull();
    expect(amountLine).toContainElement(within(row).getAllByText("10000.00")[1]);
    expect(within(amountLine as HTMLElement).getByText("支出").closest(".finance-direction-tag")).not.toBeNull();
    expect(amountLine).toContainElement(within(row).getByText("建设银行 1234"));

    const styles = readWebSource("src/app/styles.css");
    const amountLineStyles = cssRule(styles, ".oa-pending-payments-bank-amount-line");
    const nonShrinkingChildren = cssRule(
      styles,
      ".oa-pending-payments-bank-amount-line > *",
    );

    expect(amountLineStyles).toContain("display: flex");
    expect(amountLineStyles).toContain("flex-wrap: wrap");
    expect(amountLineStyles).toContain("justify-content: flex-start");
    expect(nonShrinkingChildren).toContain("flex: 0 0 auto");
  });

  test("shows OA application time under project and renders missing bank transaction as dash only", async () => {
    installOaPendingPaymentsFetch();

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await within(page).findByText("张三");

    const paidRow = within(page).getByRole("row", { name: /张三/ });
    const paidCells = paidRow.querySelectorAll(".oa-pending-payments-table-cell");
    const projectCell = paidCells[0] as HTMLElement;
    expect(within(projectCell).getByText("红河卷烟厂能源管理系统运维服务")).toBeInTheDocument();
    expect(within(projectCell).getByText("2026-01-03")).toHaveClass("oa-pending-payments-table-tag");

    const missingBankRow = within(page).getByRole("row", { name: /杨丽萍/ });
    const missingBankCells = missingBankRow.querySelectorAll(".oa-pending-payments-table-cell");
    expect(within(missingBankCells[0] as HTMLElement).getByText("2026-05-23")).toHaveClass("oa-pending-payments-table-tag");
    expect(missingBankCells[2]?.textContent?.trim()).toBe("-");
    expect(within(missingBankRow).queryByText("交易时间为空")).not.toBeInTheDocument();
    expect(within(missingBankRow).queryByText("0.00")).not.toBeInTheDocument();
    expect(missingBankRow.querySelector(".finance-direction-tag")).toBeNull();
    expect(within(missingBankRow).queryByRole("button", { name: /查看流水/ })).not.toBeInTheDocument();
  });

  test("adds sidebar route and renders compact grouped project table from OA perspective", async () => {
    const fetchMock = installOaPendingPaymentsFetch();
    const user = userEvent.setup();

    const financeItems = sidebarGroups.find((group) => group.title === "财务业务")?.items ?? [];
    expect(financeItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "OA待付款核对", to: "/oa-pending-payments" }),
      ]),
    );

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBeGreaterThan(0));
    const initialRowsRequest = rowsRequests(fetchMock)[0];
    expect(initialRowsRequest.searchParams.get("page")).toBe("1");
    expect(initialRowsRequest.searchParams.get("page_size")).toBe("20");
    expect(initialRowsRequest.searchParams.get("view_mode")).toBe("completed");
    expect(within(page).getByRole("heading", { name: "OA 待付款核对" })).toBeInTheDocument();
    expect(await within(page).findByRole("table", { name: "OA待付款核对表格" })).toBeInTheDocument();

    const groupHeader = within(page).getAllByRole("row")[0];
    for (const label of ["OA", "支付状态", "流水", "发票"]) {
      expect(within(groupHeader).getByRole("columnheader", { name: label })).toBeInTheDocument();
    }
    expect(within(groupHeader).queryByRole("columnheader", { name: "凭证信息" })).not.toBeInTheDocument();
    const subHeader = within(page).getAllByRole("row")[1];
    for (const label of ["申请人", "项目", "申请事由", "金额", "状态", "写回", "对方户名", "流水摘要", "发票号", "发票方", "日期"]) {
      expect(within(subHeader).getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(within(subHeader).queryByText("OA")).not.toBeInTheDocument();
    expect(within(subHeader).queryByText("支付状态")).not.toBeInTheDocument();
    expect(within(subHeader).queryByText("流水")).not.toBeInTheDocument();
    expect(within(subHeader).queryByText("发票")).not.toBeInTheDocument();
    expect(within(page).queryByText("发票号码/发票方")).not.toBeInTheDocument();
    expect(within(page).queryByText("价税合计")).not.toBeInTheDocument();
    expect(within(page).queryByText("交易开始")).not.toBeInTheDocument();
    expect(within(page).queryByText("交易结束")).not.toBeInTheDocument();
    expect(within(page).queryByText("全页面检索")).not.toBeInTheDocument();
    const refreshButton = within(page).getByRole("button", { name: "刷新 OA 待付款核对" });
    expect(refreshButton).toBeInTheDocument();
    const rowsBeforeRefresh = rowsRequests(fetchMock).length;
    await user.click(refreshButton);
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBeGreaterThan(rowsBeforeRefresh));
    expect(within(page).queryByRole("columnheader", { name: "类型" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("columnheader", { name: "OA详情" })).not.toBeInTheDocument();
    expect(within(page).queryByText("销方名称")).not.toBeInTheDocument();
    expect(Array.from((within(page).getByLabelText("每页") as HTMLSelectElement).options).map((option) => option.value)).toEqual(["20", "50", "100"]);
    expect(await within(page).findByText("张三")).toBeInTheDocument();
    expect(within(page).getByText("报销")).toBeInTheDocument();
    expect(within(page).getAllByText("流程状态：已完成").length).toBeGreaterThan(0);
    expect(within(page).getAllByText("支付少了").some((element) => element.closest(".oa-pending-payment-status-cell"))).toBe(true);
    expect(within(page).getByText("26532000000123456789")).toBeInTheDocument();
    expect(within(page).getByText("2026-01-08")).toBeInTheDocument();
    const invoiceSeller = within(page).getByText("云南恒昆机电设备有限公司");
    expect(invoiceSeller.closest(".oa-pending-payments-table-tag")).toBeNull();
    expect(within(page).queryByText("进项发票方名称")).not.toBeInTheDocument();
    expect(within(page).getByText("建设银行 1234")).toBeInTheDocument();
    const paidRow = within(page).getByRole("row", { name: /张三/ });
    const paidCells = paidRow.querySelectorAll(".oa-pending-payments-table-cell");
    const oaGrid = paidCells[0]?.querySelector(".oa-pending-payments-oa-grid") as HTMLElement;
    const bankGrid = paidCells[2]?.querySelector(".oa-pending-payments-bank-grid") as HTMLElement;
    expect(oaGrid.querySelector(".oa-pending-payments-oa-grid__applicant")).toHaveTextContent("张三");
    expect(oaGrid.querySelector(".oa-pending-payments-oa-grid__applicant")).toHaveTextContent("报销");
    expect(oaGrid.querySelector(".oa-pending-payments-oa-grid__applicant")).toHaveTextContent("流程状态：已完成");
    expect(oaGrid.querySelector(".oa-pending-payments-oa-grid__project")).toHaveTextContent("红河卷烟厂能源管理系统运维服务");
    expect(oaGrid.querySelector(".oa-pending-payments-oa-grid__project")).toHaveTextContent("2026-01-03");
    expect(oaGrid.querySelector(".oa-pending-payments-oa-grid__reason")).toHaveTextContent("红河卷烟厂运维服务保证金");
    expect(oaGrid.querySelector(".oa-pending-payments-oa-grid__counterparty")).toHaveTextContent("中招国际招标有限公司云南分公司");
    expect(oaGrid.querySelector(".oa-pending-payments-oa-grid__amount")).toHaveTextContent("10000.00");
    expect(bankGrid.querySelector(".oa-pending-payments-bank-grid__counterparty")).toHaveTextContent("中招国际招标有限公司云南分公司");
    expect(bankGrid.querySelector(".oa-pending-payments-bank-grid__counterparty")).not.toHaveTextContent("对方户名：");
    expect(bankGrid.querySelector(".oa-pending-payments-bank-grid__counterparty")).toHaveTextContent("20260105 09:50:25");
    expect(bankGrid.querySelector(".oa-pending-payments-bank-grid__amount")).toHaveTextContent("10000.00");
    expect(bankGrid.querySelector(".oa-pending-payments-bank-grid__amount")).toHaveTextContent("建设银行 1234");
    expect(bankGrid.querySelector(".oa-pending-payments-bank-grid__summary")).toHaveTextContent("电子转账");
    const groupedRow = within(page).getByRole("row", { name: /刘际涛/ });
    const groupedCells = groupedRow.querySelectorAll(".oa-pending-payments-table-cell");
    expect(groupedCells[0]).toHaveTextContent("4450.00");
    expect(groupedCells[0]).toHaveTextContent("+2");
    expect(groupedCells[1]).toHaveTextContent("已写回");
    expect(within(page).queryByText("同步状态异常")).not.toBeInTheDocument();
    expect(groupedCells[1]).not.toHaveTextContent("OA写回状态");
    expect(groupedCells[1]).not.toHaveTextContent("写回失败");
    expect(groupedCells[2]).toHaveTextContent("4450.00");
    expect(groupedCells[2]).toHaveTextContent("+1");
    expect(groupedCells[2]).not.toHaveTextContent("3000.00");
    expect(within(page).getByText(/补充住宿费/)).toBeInTheDocument();
    expect(within(page).getByText(/补充流水备注/)).toBeInTheDocument();
    const noInvoiceRow = within(page).getByRole("row", { name: /王五/ });
    expect(noInvoiceRow.querySelector(".oa-pending-payments-empty-invoice-cell")).not.toBeNull();
    expect(within(noInvoiceRow).queryByText("开票日期为空")).not.toBeInTheDocument();
    expect(within(noInvoiceRow).queryByRole("button", { name: /查看发票/ })).not.toBeInTheDocument();
    const candidateRow = within(page).getByRole("row", { name: /候选付款人/ });
    expect(within(candidateRow).getByText("候选")).toBeInTheDocument();
    expect(within(candidateRow).getByText("待支付")).toBeInTheDocument();
    expect(within(candidateRow).queryByRole("button", { name: "确认已支付并写回" })).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "支出流水无需开票规则设置" })).toBeInTheDocument();

    const tableFrame = within(page).getByTestId("oa-pending-payments-table-frame");
    await user.type(within(tableFrame).getByLabelText("搜索OA待付款核对"), "张三");
    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(rowsRequests(fetchMock).at(-1)?.searchParams.get("keyword")).toBe("张三");
    });

    await user.click(within(page).getByRole("button", { name: "筛选 申请人" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "OA申请人：张三 1" }));
    await user.click(screen.getByRole("button", { name: "应用筛选" }));
    await waitFor(() => {
      const filters = JSON.parse(decodeURIComponent(rowsRequests(fetchMock).at(-1)?.searchParams.get("filters") ?? "[]"));
      expect(filters).toEqual([{ field: "oa_applicant", operator: "in", values: ["张三"] }]);
    });

    await user.click(within(page).getByRole("button", { name: "交易时间 排序" }));
    await waitFor(() => {
      expect(rowsRequests(fetchMock).at(-1)?.searchParams.get("sort_field")).toBe("bank_trade_time");
    });
  });

  test("applies column menu filters and sort params from table headers", async () => {
    const fetchMock = installOaPendingPaymentsFetch();
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");

    await user.click(await within(page).findByRole("button", { name: "筛选 支付状态" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "支付状态：支付少了 1" }));
    await user.click(screen.getByRole("button", { name: "应用筛选" }));
    await waitFor(() => {
      const filters = JSON.parse(decodeURIComponent(rowsRequests(fetchMock).at(-1)?.searchParams.get("filters") ?? "[]"));
      expect(filters).toContainEqual({ field: "payment_status", operator: "in", values: ["partially_paid"] });
    });

    await user.click(within(page).getByRole("button", { name: "筛选 项目" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "项目名称：红河卷烟厂能源管理系统运维服务 1" }));
    await user.click(screen.getByRole("button", { name: "应用筛选" }));
    await waitFor(() => {
      const filters = JSON.parse(decodeURIComponent(rowsRequests(fetchMock).at(-1)?.searchParams.get("filters") ?? "[]"));
      expect(filters).toContainEqual({ field: "oa_project_name", operator: "in", values: ["红河卷烟厂能源管理系统运维服务"] });
    });

    await user.click(within(page).getByRole("button", { name: "筛选 对方户名" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "对方户名：中招国际招标有限公司云南分公司 1" }));
    await user.click(screen.getByRole("button", { name: "应用筛选" }));
    await waitFor(() => {
      const filters = JSON.parse(decodeURIComponent(rowsRequests(fetchMock).at(-1)?.searchParams.get("filters") ?? "[]"));
      expect(filters).toContainEqual({ field: "bank_counterparty_name", operator: "in", values: ["中招国际招标有限公司云南分公司"] });
    });
    await user.click(within(page).getByRole("button", { name: "交易时间 排序" }));
    await waitFor(() => {
      expect(rowsRequests(fetchMock).at(-1)?.searchParams.get("sort_field")).toBe("bank_trade_time");
    });

    await user.click(within(page).getByRole("button", { name: "筛选 流水金额" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "银行账户：建设银行 1234 1" }));
    await user.click(screen.getByRole("menuitemcheckbox", { name: "收支：支出 2" }));
    await user.click(screen.getByRole("button", { name: "应用筛选" }));
    await waitFor(() => {
      const filters = JSON.parse(decodeURIComponent(rowsRequests(fetchMock).at(-1)?.searchParams.get("filters") ?? "[]"));
      expect(filters).toContainEqual({ field: "bank_account", operator: "in", values: ["建设银行 1234"] });
      expect(filters).toContainEqual({ field: "bank_direction", operator: "in", values: ["outflow"] });
    });

    await user.click(within(page).getByRole("button", { name: "筛选 发票方" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "发票方：云南恒昆机电设备有限公司 1" }));
    await user.click(screen.getByRole("button", { name: "应用筛选" }));
    await waitFor(() => {
      const filters = JSON.parse(decodeURIComponent(rowsRequests(fetchMock).at(-1)?.searchParams.get("filters") ?? "[]"));
      expect(filters).toContainEqual({ field: "seller_name", operator: "in", values: ["云南恒昆机电设备有限公司"] });
    });
    await user.click(within(page).getByRole("button", { name: "开票日期 排序" }));
    await waitFor(() => {
      expect(rowsRequests(fetchMock).at(-1)?.searchParams.get("sort_field")).toBe("invoice_date");
    });
  });

  test("switches to in-progress OA view and links bank payment with automatic writeback", async () => {
    const fetchMock = installOaPendingPaymentsFetch();
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await within(page).findByText("候选付款人");

    expect(within(page).getByRole("button", { name: /已完成 OA 51条/ })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /进行中 OA 23条/ })).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: /进行中 OA/ }));
    await waitFor(() => {
      expect(rowsRequests(fetchMock).at(-1)?.searchParams.get("view_mode")).toBe("in_progress");
    });

    const candidateRow = within(page).getByRole("row", { name: /候选付款人/ });
    expect(within(candidateRow).getByText("流程状态：进行中")).toBeInTheDocument();
    expect(within(page).getAllByRole("columnheader", { name: "发票" }).length).toBeGreaterThan(0);
    expect(within(page).getByRole("button", { name: "筛选 发票方" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "开票日期 排序" })).toBeInTheDocument();
    const candidateCells = candidateRow.querySelectorAll(".oa-pending-payments-table-cell");
    expect(candidateCells[3]?.textContent?.trim()).toBe("-");
    expect(within(candidateRow).queryByRole("button", { name: "确认已支付并写回" })).not.toBeInTheDocument();

    await user.click(within(candidateRow).getByRole("checkbox", { name: /候选付款人/ }));
    await user.click(within(page).getByRole("button", { name: "关联支出流水" }));
    expect(await screen.findByRole("heading", { name: "关联支出流水" })).toBeInTheDocument();
    await waitFor(() => expect(bankCandidateRequests(fetchMock).at(-1)?.searchParams.get("relation_status")).toBe("all"));
    expect(bankCandidateRequests(fetchMock).at(-1)?.searchParams.getAll("oa_row_ids")).toEqual(["oa-candidate"]);
    expect(await screen.findByText("抽屉供应商")).toBeInTheDocument();
    expect(screen.getAllByText("已关联进行中OA").length).toBeGreaterThan(0);
    expect(screen.getByRole("checkbox", { name: /已关联供应商/ })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /抽屉供应商/ }));
    await user.click(screen.getByRole("button", { name: "确认关联 1 条流水" }));
    await waitFor(() => expect(linkBankRequests(fetchMock)).toHaveLength(1));
    const [, linkInit] = linkBankRequests(fetchMock)[0];
    expect(linkInit?.method).toBe("POST");
    expect(JSON.parse(String(linkInit?.body))).toMatchObject({
      oa_row_ids: ["oa-candidate"],
      bank_transaction_ids: ["bank-drawer-001"],
    });
    expect(await within(page).findByText("已关联支出流水并写回 OA，等待核对表刷新。")).toBeInTheDocument();
    await waitFor(() => {
      expect(rowsRequests(fetchMock).at(-1)?.searchParams.get("view_mode")).toBe("in_progress");
    });
  });

  test("waits for the OA pending payment barrier before reloading after auto reconcile", async () => {
    const barrier = deferred();
    const fetchMock = installOaPendingPaymentsFetch({
      operationBarrierDelay: barrier.promise,
      autoReconcilePayload: {
        success: true,
        action: "oa_pending_payment_auto_reconcile_bank_transactions",
        autoMatchedCount: 1,
        writebackCount: 1,
        readModelRefresh: { scopeKeys: ["2026-05", "all"], enqueued: true, targetSeconds: 2 },
      },
    });

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await within(page).findByText("候选付款人");
    const rowsBeforeMutation = rowsRequests(fetchMock).length;

    await waitFor(() => expect(autoReconcileRequests(fetchMock)).toHaveLength(1));
    await waitFor(() => expect(operationBarrierRequests(fetchMock)).toHaveLength(1));
    const [, barrierInit] = operationBarrierRequests(fetchMock)[0];
    expect(JSON.parse(String(barrierInit?.body))).toEqual({
      targets: [{ read_model_key: "oa_pending_payment", scope_key: "2026-05" }],
    });
    expect(rowsRequests(fetchMock)).toHaveLength(rowsBeforeMutation);

    barrier.resolve();

    await waitFor(() => {
      expect(rowsRequests(fetchMock).length).toBeGreaterThan(rowsBeforeMutation);
    });
  });

  test("retries auto reconcile after a failed attempt when the user refreshes rows", async () => {
    const fetchMock = installOaPendingPaymentsFetch({
      autoReconcileResponses: [
        {
          status: 503,
          payload: {
            error: "temporary_api_error",
            message: "自动匹配和写回暂不可用。",
          },
        },
        {
          status: 200,
          payload: {
            success: true,
            action: "oa_pending_payment_auto_reconcile_bank_transactions",
            autoMatchedCount: 0,
            writebackCount: 0,
            readModelRefresh: { scopeKeys: [], enqueued: false, targetSeconds: 2 },
          },
        },
      ],
    });
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await within(page).findByText("候选付款人");
    await waitFor(() => expect(autoReconcileRequests(fetchMock)).toHaveLength(1));
    expect(await within(page).findByText("自动匹配和写回暂不可用。")).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "刷新 OA 待付款核对" }));

    await waitFor(() => expect(autoReconcileRequests(fetchMock)).toHaveLength(2));
    await waitFor(() => expect(within(page).queryByText("自动匹配和写回暂不可用。")).not.toBeInTheDocument());
  });

  test("does not auto reconcile while OA pending payment read model is still refreshing", async () => {
    const fetchMock = installOaPendingPaymentsFetch({
      rowsPayload: {
        rows: [],
        pagination: { page: 1, pageSize: 20, total: 0 },
        summary: { rowCount: 0, viewCounts: { completed: 0, in_progress: 0 } },
        filterConfig: [],
        read_model_status: "refreshing",
      },
    });

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    expect(await within(page).findByText("OA 待付款核对数据正在刷新")).toBeInTheDocument();
    expect(autoReconcileRequests(fetchMock)).toHaveLength(0);
  });

  test("waits for the OA pending payment barrier before reloading after bank link", async () => {
    const barrier = deferred();
    const fetchMock = installOaPendingPaymentsFetch({ operationBarrierDelay: barrier.promise });
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await within(page).findByText("候选付款人");
    await user.click(within(page).getByRole("button", { name: /进行中 OA/ }));
    await waitFor(() => {
      expect(rowsRequests(fetchMock).at(-1)?.searchParams.get("view_mode")).toBe("in_progress");
    });
    const candidateRow = within(page).getByRole("row", { name: /候选付款人/ });
    await user.click(within(candidateRow).getByRole("checkbox", { name: /候选付款人/ }));
    await user.click(within(page).getByRole("button", { name: "关联支出流水" }));
    expect(await screen.findByRole("heading", { name: "关联支出流水" })).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /抽屉供应商/ }));
    const rowsBeforeMutation = rowsRequests(fetchMock).length;

    await user.click(screen.getByRole("button", { name: "确认关联 1 条流水" }));

    await waitFor(() => expect(linkBankRequests(fetchMock)).toHaveLength(1));
    await waitFor(() => expect(operationBarrierRequests(fetchMock)).toHaveLength(1));
    const [, barrierInit] = operationBarrierRequests(fetchMock)[0];
    expect(JSON.parse(String(barrierInit?.body))).toEqual({
      targets: [{ read_model_key: "oa_pending_payment", scope_key: "2026-05" }],
    });
    expect(rowsRequests(fetchMock)).toHaveLength(rowsBeforeMutation);

    barrier.resolve();

    await waitFor(() => {
      expect(rowsRequests(fetchMock).length).toBeGreaterThan(rowsBeforeMutation);
    });
  });

  test("opens OA, bank, relation drawers and reuses pending invoice rules endpoint", async () => {
    const fetchMock = installOaPendingPaymentsFetch();
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await user.click(within(page).getByRole("button", { name: "查看 OA 张三 详情" }));
    expect(await screen.findByRole("heading", { name: "OA详情" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看流水 张三 详情" }));
    expect(await screen.findByRole("heading", { name: "支出流水详情" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看发票 张三 详情" }));
    expect(await screen.findByRole("heading", { name: "发票详情" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看刘际涛关联OA 3 条" }));
    expect(await screen.findByRole("heading", { name: "OA关联明细" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看刘际涛关联流水 2 条" }));
    expect(await screen.findByRole("heading", { name: "支出流水关联明细" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看刘际涛关联发票 2 张" }));
    expect(await screen.findByRole("heading", { name: "发票关联明细" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "支出流水无需开票规则设置" }));
    await screen.findByRole("heading", { name: "支出流水无需开票规则设置" });
    expect(screen.queryByRole("heading", { name: "待找发票规则设置" })).not.toBeInTheDocument();
    expect(screen.queryByText(/版本\s+\d+/)).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/pending-invoices/rules" && url.searchParams.get("direction") === "expense";
    })).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/oa-pending-payments/bank-transactions/bank-001/detail";
    })).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname.startsWith("/api/oa-pending-payments/invoices/");
    })).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/oa-pending-payments/rows/oa-payment-group-case-001/relation-details" && url.searchParams.get("kind") === "oa";
    })).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/oa-pending-payments/rows/oa-payment-group-case-001/relation-details" && url.searchParams.get("kind") === "bank";
    })).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/oa-pending-payments/rows/oa-payment-group-case-001/relation-details" && url.searchParams.get("kind") === "invoice";
    })).toBe(true);
  });

  test("waits for OA pending payment barrier before reloading after rule save", async () => {
    const user = userEvent.setup();
    const gate = deferred();
    const fetchMock = installOaPendingPaymentsFetch({
      operationBarrierDelay: gate.promise,
      rulesCanSave: true,
    });

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await within(page).findByText("张三");
    const initialRowsRequests = rowsRequests(fetchMock).length;

    await user.click(within(page).getByRole("button", { name: "支出流水无需开票规则设置" }));
    await screen.findByRole("heading", { name: "支出流水无需开票规则设置" });
    await user.click(screen.getByRole("button", { name: "保存规则" }));

    await waitFor(() => expect(rulesSaveRequests(fetchMock)).toHaveLength(1));
    await waitFor(() => expect(operationBarrierRequests(fetchMock)).toHaveLength(1));
    expect(JSON.parse(String(operationBarrierRequests(fetchMock)[0][1]?.body))).toEqual({
      targets: [{ read_model_key: "oa_pending_payment", scope_key: "all" }],
    });
    expect(rowsRequests(fetchMock)).toHaveLength(initialRowsRequests);

    gate.resolve();
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBeGreaterThan(initialRowsRequests));
  });

  test("keeps pending invoice rules drawer stable during parent query refresh", async () => {
    const fetchMock = installOaPendingPaymentsFetch();
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await user.click(within(page).getByRole("button", { name: "支出流水无需开票规则设置" }));
    await screen.findByRole("heading", { name: "支出流水无需开票规则设置" });
    expect(rulesRequests(fetchMock)).toHaveLength(1);

    const tableFrame = within(page).getByTestId("oa-pending-payments-table-frame");
    const initialRowsRequestCount = rowsRequests(fetchMock).length;
    await user.type(within(tableFrame).getByLabelText("搜索OA待付款核对"), "刘际涛");
    await user.click(within(tableFrame).getByRole("button", { name: "查询" }));

    await waitFor(() => {
      expect(rowsRequests(fetchMock).length).toBeGreaterThan(initialRowsRequestCount);
    });
    expect(rulesRequests(fetchMock)).toHaveLength(1);
  });

  test("shows a neutral refreshing state instead of a true empty state while rows read model refreshes", async () => {
    installOaPendingPaymentsFetch({
      rowsPayload: {
        ...rowsPayload,
        rows: [],
        pagination: { page: 1, pageSize: 20, total: 0 },
        summary: {},
        readModelStatus: "refreshing",
        read_model_status: "refreshing",
        read_model_stale_reasons: ["oa_pending_payment_source_version_missing"],
      },
    });

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    expect(await within(page).findByText("OA 待付款核对数据正在刷新")).toBeInTheDocument();
    expect(within(page).getByText("当前数据仍在刷新或等待后台任务完成，请稍后重试。")).toBeInTheDocument();
    expect(within(page).getByText("0-0 / 0")).toBeInTheDocument();
    expect(within(page).queryByText(/NaN|undefined/)).not.toBeInTheDocument();
    expect(within(page).queryByText("当前条件下暂无记录。")).not.toBeInTheDocument();
    expect(within(page).queryByText(/oa_pending_payment_source_version_missing/)).not.toBeInTheDocument();
  });

  test("shows neutral unavailable detail state while detail read model is refreshing", async () => {
    installOaPendingPaymentsFetch({
      rowsPayload: {
        ...rowsPayload,
        rows: [
          {
            ...(rowsPayload.rows[0] as Record<string, unknown>),
            oa: {
              ...(rowsPayload.rows[0].oa as Record<string, unknown>),
              id: "oa-refresh",
            },
          },
        ],
      },
      detailPayloads: {
        "/api/oa-pending-payments/oa/oa-refresh/detail": {
          status: 202,
          payload: {
            title: "OA详情",
            detailAvailable: false,
            unavailableReason: "详情数据正在刷新，请稍后重试。",
            sections: [],
            read_model_status: "refreshing",
          },
        },
      },
    });
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await user.click(within(page).getByRole("button", { name: "查看 OA 张三 详情" }));

    expect(await screen.findByRole("heading", { name: "OA详情" })).toBeInTheDocument();
    expect(await screen.findByText("详情暂不可用")).toBeInTheDocument();
    expect(screen.getByText("详情数据正在刷新，请稍后重试。")).toBeInTheDocument();
  });
});
