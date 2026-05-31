import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { sidebarGroups } from "../components/shell/sidebarItems";
import { renderAuthenticatedAppAt } from "./renderHelpers";

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
      },
      invoice: {
        primaryInvoiceId: "inv-001",
        digitalInvoiceNo: "26532000000123456789",
        sellerName: "云南恒昆机电设备有限公司",
        invoiceDate: "2026-01-08",
        totalWithTax: "10000.00",
        relationCount: 1,
        hasMultiple: false,
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

function installOaPendingPaymentsFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/oa-pending-payments/rows") {
      return new Response(JSON.stringify(rowsPayload), {
        status: 200,
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("OA pending payments page", () => {
  test("adds sidebar route and renders compact grouped MUI table from OA perspective", async () => {
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
    expect(document.querySelector(".MuiDataGrid-root")).not.toBeInTheDocument();

    const groupHeader = within(page).getAllByRole("row")[0];
    for (const label of ["凭证信息", "OA情况", "支付状态", "支出流水", "发票情况"]) {
      expect(within(groupHeader).getByRole("columnheader", { name: label })).toBeInTheDocument();
    }
    for (const label of ["OA申请人", "类型", "项目名称", "金额", "交易时间", "数电发票号码", "销方名称"]) {
      expect(within(page).getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(await within(page).findByText("张三")).toBeInTheDocument();
    expect(within(page).getByText("支付少了").closest(".oa-pending-payment-status-cell")).toBeInTheDocument();
    expect(within(page).getByText("26532000000123456789")).toBeInTheDocument();
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

  test("opens OA detail drawer and reuses pending invoice rules endpoint", async () => {
    const fetchMock = installOaPendingPaymentsFetch();
    const user = userEvent.setup();

    renderAuthenticatedAppAt("/oa-pending-payments");

    const page = await screen.findByTestId("oa-pending-payments-page");
    await user.click(within(page).getByRole("button", { name: "查看 OA 张三 详情" }));
    expect(await screen.findByRole("heading", { name: "OA详情" })).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "支出流水无需开票规则设置" }));
    await screen.findByText("待找发票规则设置");
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/pending-invoices/rules" && url.searchParams.get("direction") === "expense";
    })).toBe(true);
  });
});
