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
        amount: "10000.00",
        detailAvailable: true,
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
      id: "oa-payment-row-002",
      oa: {
        id: "oa-002",
        applicantName: "李四",
        applicationType: "付款",
        projectName: "多关联项目",
        amount: "15000.00",
        detailAvailable: true,
      },
      paymentStatus: {
        code: "merged_paid",
        label: "已支付（多条OA合并支付）",
        reason: "多条OA共享同一支出流水且合计金额匹配",
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
        directionLabel: "支出",
        accountName: "云南溯源科技有限公司",
        tradeTime: "20260106 09:50:25",
        debitAmount: "15000.00",
        creditAmount: "0.00",
        balance: "129698.00",
        currency: "人民币元",
        counterpartyName: "多流水供应商",
        counterpartyAccountNo: "2502124119024521402",
        counterpartyBankName: "中国建设银行昆明支行",
        bookedDate: "20260106",
        summary: "多流水转账",
        remark: "多流水备注",
        relationCount: 2,
        hasMultiple: true,
        detailMode: "list",
        summaries: [
          {
            bankTransactionId: "bank-002",
            bankName: "建设银行",
            accountNo: "622200005678",
            accountLast4: "5678",
            directionLabel: "支出",
            tradeTime: "20260106 09:50:25",
            amount: "15000.00",
            counterpartyName: "多流水供应商",
            summary: "多流水转账",
            remark: "多流水备注",
            relationCaseId: "case-bank-002",
          },
          {
            bankTransactionId: "bank-003",
            bankName: "建设银行",
            accountNo: "622200009999",
            accountLast4: "9999",
            directionLabel: "支出",
            tradeTime: "20260106 11:20:00",
            amount: "2000.00",
            counterpartyName: "多流水供应商",
            summary: "补充流水摘要",
            remark: "补充流水备注",
            relationCaseId: "case-bank-003",
          },
        ],
      },
      invoice: {
        primaryInvoiceId: "inv-002",
        digitalInvoiceNo: "26532000000999999999",
        sellerName: "多发票供应商",
        invoiceDate: "2026-01-09",
        totalWithTax: "15000.00",
        relationCount: 2,
        hasMultiple: true,
        detailMode: "list",
      },
    },
  ],
  pagination: { page: 1, pageSize: 20, total: 51 },
  summary: { rowCount: 51 },
  filterConfig: [
    {
      field: "oa_applicant",
      label: "OA申请人",
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
  ],
};

function installOaPendingPaymentsFetch(overrides?: {
  rowsPayload?: Record<string, unknown>;
  detailPayloads?: Record<string, { status: number; payload: Record<string, unknown> }>;
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
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
            field: "payment_status",
            label: "支付状态",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "partially_paid", label: "支付少了", count: 1 }],
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
    if (url.pathname === "/api/oa-pending-payments/rows/oa-payment-row-002/relation-details") {
      const kind = url.searchParams.get("kind");
      return new Response(JSON.stringify({
        title: kind === "invoice" ? "发票关联明细" : "支出流水关联明细",
        subtitle: "李四",
        detailAvailable: true,
        sections: [{ title: kind === "invoice" ? "发票 1" : "流水 1", fields: [{ label: "数量", value: "2" }] }],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/rules") {
      return new Response(JSON.stringify({
        version: 1,
        direction: "expense",
        available_tags: [],
        groups: {
          requires_invoice: { tag_codes: [], tags: [] },
          bank_statement_as_invoice: { tag_codes: [], tags: [] },
          no_invoice_required: { tag_codes: [], tags: [] },
        },
        permissions: { can_save: false },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
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

function readWebSource(path: string) {
  return readFileSync(resolve(path), "utf8");
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
    expect(within(page).getByRole("heading", { name: "OA 待付款核对" })).toBeInTheDocument();
    expect(await within(page).findByRole("table", { name: "OA待付款核对表格" })).toBeInTheDocument();

    const groupHeader = within(page).getAllByRole("row")[0];
    for (const label of ["OA情况", "支付状态", "支出流水", "发票情况"]) {
      expect(within(groupHeader).getByRole("columnheader", { name: label })).toBeInTheDocument();
    }
    expect(within(groupHeader).queryByRole("columnheader", { name: "凭证信息" })).not.toBeInTheDocument();
    for (const label of ["OA申请人", "项目名称", "金额", "对方户名/交易时间", "金额/账户", "摘要/备注", "发票号码/发票方", "日期", "价税合计"]) {
      expect(within(page).getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(within(page).queryByRole("columnheader", { name: "类型" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("columnheader", { name: "OA详情" })).not.toBeInTheDocument();
    expect(within(page).queryByText("销方名称")).not.toBeInTheDocument();
    expect(await within(page).findByText("张三")).toBeInTheDocument();
    expect(within(page).getByText("报销")).toBeInTheDocument();
    expect(within(page).getAllByText("支付少了").some((element) => element.closest(".oa-pending-payment-status-cell"))).toBe(true);
    expect(within(page).getByText("26532000000123456789")).toBeInTheDocument();
    expect(within(page).getAllByText("进项发票方名称").length).toBeGreaterThan(0);
    expect(within(page).getByText("建设银行 1234")).toBeInTheDocument();
    expect(within(page).getByText(/补充流水摘要/)).toBeInTheDocument();
    expect(within(page).getByText(/补充流水备注/)).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "支出流水无需开票规则设置" })).toBeInTheDocument();

    await user.type(within(page).getByLabelText("全页面检索"), "张三");
    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(rowsRequests(fetchMock).at(-1)?.searchParams.get("keyword")).toBe("张三");
    });

    await user.click(within(page).getByRole("button", { name: "筛选 OA申请人" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "张三 1" }));
    await waitFor(() => {
      const filters = JSON.parse(decodeURIComponent(rowsRequests(fetchMock).at(-1)?.searchParams.get("filters") ?? "[]"));
      expect(filters).toEqual([{ field: "oa_applicant", operator: "in", values: ["张三"] }]);
    });

    await user.click(within(page).getByRole("button", { name: "交易时间 排序" }));
    await waitFor(() => {
      expect(rowsRequests(fetchMock).at(-1)?.searchParams.get("sort_field")).toBe("bank_trade_time");
    });
  });

  test("opens OA, bank, invoice, relation drawers and reuses pending invoice rules endpoint", async () => {
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

    await user.click(within(page).getByRole("button", { name: "查看李四关联流水 2 条" }));
    expect(await screen.findByRole("heading", { name: "支出流水关联明细" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看李四关联发票 2 张" }));
    expect(await screen.findByRole("heading", { name: "发票关联明细" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "支出流水无需开票规则设置" }));
    await screen.findByText("待找发票规则设置");
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
      return url.pathname === "/api/oa-pending-payments/invoices/inv-001/detail";
    })).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/oa-pending-payments/rows/oa-payment-row-002/relation-details" && url.searchParams.get("kind") === "bank";
    })).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/oa-pending-payments/rows/oa-payment-row-002/relation-details" && url.searchParams.get("kind") === "invoice";
    })).toBe(true);
  });

  test("keeps pending invoice rules drawer stable during parent refresh", async () => {
    const fetchMock = installOaPendingPaymentsFetch();
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await user.click(within(page).getByRole("button", { name: "支出流水无需开票规则设置" }));
    await screen.findByText("待找发票规则设置");
    expect(rulesRequests(fetchMock)).toHaveLength(1);

    const initialRowsRequestCount = rowsRequests(fetchMock).length;
    await user.click(within(page).getByRole("button", { name: "刷新", hidden: true }));

    await waitFor(() => {
      expect(rowsRequests(fetchMock).length).toBeGreaterThan(initialRowsRequestCount);
    });
    await waitFor(() => {
      expect(within(page).getByRole("button", { name: "刷新", hidden: true })).not.toBeDisabled();
    });
    expect(rulesRequests(fetchMock)).toHaveLength(1);
  });

  test("uses a standard empty state while read model refresh details stay hidden", async () => {
    installOaPendingPaymentsFetch({
      rowsPayload: {
        ...rowsPayload,
        rows: [],
        pagination: { page: 1, pageSize: 20, total: 0 },
        summary: { rowCount: 0 },
        readModelStatus: "refreshing",
        read_model_status: "refreshing",
        read_model_stale_reasons: ["oa_pending_payment_source_version_missing"],
      },
    });

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    expect(await within(page).findByText("当前条件下暂无记录。")).toBeInTheDocument();
    expect(within(page).queryByText(/OA 待付款核对数据正在刷新/)).not.toBeInTheDocument();
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
