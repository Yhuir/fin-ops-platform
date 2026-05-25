import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { sidebarGroups } from "../components/shell/sidebarItems";
import { renderAuthenticatedAppAt } from "./renderHelpers";

const rowsPayload = {
  rows: [
    {
      id: "output-collection-row-001",
      invoiceId: "out-001",
      invoice: {
        id: "out-001",
        displayNo: "XSFP-2026-0001",
        invoiceNo: "0001",
        invoiceCode: "5300",
        digitalInvoiceNo: "XSFP-2026-0001",
        invoiceDate: "2026-05-02",
        issueDate: "2026-05-02",
        buyerName: "云南客户科技有限公司",
        buyerTaxNo: "91530100BUYER01",
        sellerName: "云南溯源科技有限公司",
        sellerTaxNo: "91530000SELLER01",
        totalWithTax: "12345.67",
        amountWithoutTax: "11646.86",
        taxRate: "6%",
        taxAmount: "698.81",
        specificBusinessType: "信息技术服务",
        taxableItemName: "很长很长的销项发票货物或应税劳务名称用于验证展开按钮",
      },
      collectionStatus: {
        code: "partial_collected",
        label: "待收款，已收部分款",
        reason: "存在收入流水，但收入流水合计小于发票价税合计。",
        collectedAmount: "5000.00",
        pendingAmount: "7345.67",
      },
      bankTransactions: {
        primaryBankTransactionId: "bank-001",
        counterpartyName: "云南客户科技有限公司",
        tradeTime: "2026-05-03 10:30:00",
        amount: "5000.00",
        direction: "inflow",
        directionLabel: "收入",
        bankName: "工商银行",
        accountLast4: "6386",
        summary: "客户回款摘要内容很长很长用于验证折叠展示",
        remark: "银行备注",
        relationCount: 1,
        hasMultiple: false,
        detailMode: "single",
        summaries: [
          {
            bankTransactionId: "bank-001",
            counterpartyName: "云南客户科技有限公司",
            tradeTime: "2026-05-03 10:30:00",
            amount: "5000.00",
            direction: "inflow",
            directionLabel: "收入",
            bankName: "工商银行",
            accountLast4: "6386",
            summary: "客户回款摘要内容很长很长用于验证折叠展示",
            remark: "银行备注",
          },
        ],
      },
      redInvoiceRelation: {
        relationCount: 0,
        hasMultiple: false,
        detailMode: "none",
        summaries: [],
      },
      receipt: {
        status: "pending",
        label: "待出收据",
        reason: "可基于收入流水生成 Sheet7 预览；第一阶段不保存正式收据。",
        previewAvailable: true,
        sourceAvailable: false,
      },
    },
  ],
  pagination: {
    page: 1,
    pageSize: 20,
    total: 51,
  },
  filterConfig: [],
  readModelStatus: "live_query",
  generatedAt: "2026-05-24T00:00:00Z",
  sourceVersion: "output-invoice-collections:v1",
};

function installOutputInvoiceCollectionsFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/output-invoice-collections/rows") {
      return jsonResponse(rowsPayload);
    }
    if (url.pathname === "/api/output-invoice-collections/filter-options") {
      return jsonResponse({
        fields: [
          {
            field: "collection_status",
            label: "收款状态",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "partial_collected", label: "待收款，已收部分款", count: 1 }],
          },
        ],
      });
    }
    if (url.pathname === "/api/output-invoice-collections/status-rules") {
      return jsonResponse({
        version: "sheet6-static-v1",
        readOnly: true,
        rules: [
          {
            id: "partial_collected",
            label: "待收款，已收部分款",
            description: "收入流水金额小于销项发票金额",
            recognitionMode: "自动识别",
            requiredFacts: ["销项发票", "收入流水"],
            workbenchRequirement: "关联台能证明已收部分流水",
            priority: 4,
          },
        ],
      });
    }
    if (url.pathname === "/api/output-invoice-collections/receipts/history") {
      return jsonResponse({
        invoiceId: "out-001",
        sourceAvailable: false,
        receipts: [],
        message: "第一阶段没有正式收据历史事实源，不能伪造历史收据。",
      });
    }
    if (url.pathname === "/api/output-invoice-collections/receipt-preview") {
      return jsonResponse({
        canPreview: true,
        selectedBankTransactionId: "bank-001",
        candidates: [],
        receipt: {
          templateVersion: "sheet7-static-v1",
          companyName: "云南溯源科技有限公司",
          title: "收 据",
          date: "2026-05-03",
          dateParts: { year: "2026", month: "05", day: "03" },
          payerName: "云南客户科技有限公司",
          summary: "信息技术服务",
          amount: "5000.00",
          amountUppercase: "人民币伍仟元整",
          remark: "销项发票 XSFP-2026-0001",
          bankName: "工商银行",
          canCreateFormalReceipt: false,
        },
      });
    }
    if (url.pathname === "/api/output-invoice-collections/invoices/out-001/detail") {
      return jsonResponse({ id: "out-001", invoiceNo: "0001", buyerName: "云南客户科技有限公司" });
    }
    if (url.pathname === "/api/output-invoice-collections/bank-transactions/bank-001/detail") {
      return jsonResponse({ id: "bank-001", counterpartyName: "云南客户科技有限公司", amount: "5000.00" });
    }
    return jsonResponse({});
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function rowsRequests(fetchMock: ReturnType<typeof installOutputInvoiceCollectionsFetch>) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === "/api/output-invoice-collections/rows");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Output invoice collections page", () => {
  test("surfaces read model refresh state instead of silently showing an empty table", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/output-invoice-collections/rows") {
        return jsonResponse({
          rows: [],
          pagination: { page: 1, pageSize: 20, total: 0 },
          filterConfig: [],
          read_model_status: "refreshing",
          readModelStatus: "refreshing",
        }, 202);
      }
      if (url.pathname === "/api/output-invoice-collections/filter-options") {
        return jsonResponse({ fields: [], read_model_status: "refreshing", readModelStatus: "refreshing" }, 202);
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAuthenticatedAppAt("/output-invoice-collections");

    const page = await screen.findByTestId("output-invoice-collections-page");
    expect(await within(page).findByText("销项发票收款情况读模型正在刷新，完成后页面会自动重新加载。")).toBeInTheDocument();
  });

  test("adds sidebar route and renders grouped MUI Table layout without fake export", async () => {
    const user = userEvent.setup();
    const fetchMock = installOutputInvoiceCollectionsFetch();

    const financeItems = sidebarGroups.find((group) => group.title === "财务业务")?.items ?? [];
    expect(financeItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "销项发票收款情况", to: "/output-invoice-collections" }),
      ]),
    );

    renderAuthenticatedAppAt("/output-invoice-collections");

    const page = await screen.findByTestId("output-invoice-collections-page");
    expect(within(page).getByRole("heading", { name: "销项发票收款情况" })).toBeInTheDocument();
    expect(document.querySelector(".MuiDataGrid-root")).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: /导出/ })).not.toBeInTheDocument();
    expect(await within(page).findByText("XSFP-2026-0001")).toBeInTheDocument();

    const headerRows = within(page).getAllByRole("row").slice(0, 2);
    for (const label of ["销项发票", "收款状态", "收入流水", "收据"]) {
      expect(within(headerRows[0]).getByRole("columnheader", { name: label })).toBeInTheDocument();
    }
    for (const label of [
      "发票号码",
      "购方",
      "价税合计",
      "税额/税率",
      "业务/货物劳务",
      "收款状态",
      "付款方/日期",
      "收款金额",
      "银行/摘要",
      "收据情况",
    ]) {
      expect(within(headerRows[1]).getAllByText(label)).toHaveLength(1);
    }
    const bodyRows = within(page).getAllByRole("row").slice(2);
    expect(bodyRows.some((row) => within(row).queryByText("发票号码"))).toBe(false);
    expect(bodyRows.some((row) => within(row).queryByText("付款方/日期"))).toBe(false);

    expect(within(page).getAllByText("云南客户科技有限公司").length).toBeGreaterThan(0);
    expect(within(page).getByText("待收款，已收部分款").closest(".output-invoice-collection-status-cell")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "已出收据" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "待出收据" })).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: /展开.*销项发票货物或应税劳务名称/ }));
    expect(within(page).getByRole("button", { name: /收起.*销项发票货物或应税劳务名称/ })).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "发票号码 排序" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("sort_field")).toBe("invoice_no");
      expect(request?.searchParams.get("sort_direction")).toBe("asc");
    });

    await user.click(within(page).getByRole("button", { name: "筛选 收款状态" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "待收款，已收部分款 1" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toEqual([{ field: "collection_status", operator: "in", values: ["partial_collected"] }]);
    });

    await user.click(within(page).getByRole("button", { name: "下一页" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("page")).toBe("2");
    });
  });

  test("opens the three right-side workflow drawers without reloading the main rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installOutputInvoiceCollectionsFetch();
    renderAuthenticatedAppAt("/output-invoice-collections");

    const page = await screen.findByTestId("output-invoice-collections-page");
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBe(1));

    await user.click(within(page).getByRole("button", { name: "销项发票收款情况类型设置" }));
    expect(await screen.findByLabelText("销项发票收款情况类型设置")).toBeInTheDocument();
    expect(await screen.findByText("收入流水金额小于销项发票金额")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /保存|提交/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关闭销项发票收款情况类型设置" }));
    await user.click(within(page).getByRole("button", { name: "已出收据" }));
    expect(await screen.findByLabelText("已出收据历史")).toBeInTheDocument();
    expect(await screen.findByText("第一阶段没有正式收据历史事实源，不能伪造历史收据。")).toBeInTheDocument();
    expect(screen.queryByText("模拟收据")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关闭已出收据历史" }));
    await user.click(within(page).getByRole("button", { name: "待出收据" }));
    expect(await screen.findByLabelText("待出收据预览")).toBeInTheDocument();
    expect(await screen.findByText("收 据")).toBeInTheDocument();
    expect(screen.getByText(/人民币伍仟元整/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /生成正式收据|保存/ })).not.toBeInTheDocument();

    expect(rowsRequests(fetchMock).length).toBe(1);
  });
});
