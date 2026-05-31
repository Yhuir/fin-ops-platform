import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { sidebarGroups } from "../components/shell/sidebarItems";
import { renderAuthenticatedAppAt } from "./renderHelpers";

const rowsPayload = {
  rows: [
    {
      id: "usage-row-001",
      invoice: {
        id: "invoice-001",
        displayNo: "SD-INV-2026-0001",
        invoiceNo: "0001",
        invoiceCode: "5300",
        digitalInvoiceNo: "SD-INV-2026-0001",
        issueDate: "2026-05-02",
        sellerName: "云南长文本供应商科技发展有限公司第一分公司",
        sellerTaxNo: "91530100MA6KTEST01",
        totalWithTax: "12345.67",
        amountWithoutTax: "11646.86",
        taxRate: "6%",
        taxAmount: "698.81",
        specificBusinessType: "企业管理咨询",
        taxableItemName: "很长很长的货物或应税劳务名称用于验证两行截断后出现展开按钮",
      },
      paymentStatus: {
        code: "pending",
        label: "待处理",
        reason: "规则不能自动闭环，需要财务复核后处理",
      },
      oa: {
        primary: {
          id: "oa-001",
          applicant: "陈秀云",
          applicationType: "报销",
          projectName: "云南省内项目名称很长很长需要换行显示并可展开",
          detailAvailable: true,
        },
        relationCount: 1,
        hasMultiple: false,
        detailMode: "single",
        summaries: [],
      },
      bank: {
        primary: {
          id: "bank-001",
          counterpartyName: "云南银行交易对方户名很长很长需要换行显示",
          tradeTime: "2026-05-03 10:30:00",
          amount: "12345.67",
          directionLabel: "支",
          bankName: "工商银行",
          accountLast4: "6386",
          summary: "项目付款摘要内容很长很长用于验证折叠展示",
          remark: "备注内容很长很长用于验证摘要备注列的展开控制",
          detailAvailable: true,
        },
        relationCount: 1,
        hasMultiple: false,
        detailMode: "single",
        summaries: [],
      },
    },
  ],
  pagination: {
    page: 1,
    pageSize: 20,
    total: 51,
  },
  filterConfig: [],
};

function installInputInvoiceUsageFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/input-invoice-usage/rows") {
      return new Response(JSON.stringify(rowsPayload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
	    if (url.pathname === "/api/input-invoice-usage/filter-options") {
	      return new Response(JSON.stringify({
        fields: [
          {
            field: "payment_status",
            label: "支付状态",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "pending", label: "待处理", count: 1 }],
          },
        ],
      }), {
        status: 200,
	        headers: { "Content-Type": "application/json" },
	      });
	    }
	    if (url.pathname === "/api/input-invoice-usage/export-preview") {
	      return new Response(JSON.stringify({
	        file_name: "进项发票使用情况-2026-05-31.xlsx",
	        row_count: 1,
	        scope_label: "当前筛选",
	        columns: ["序号", "发票号码", "销方名称"],
	        sample_rows: [{ "序号": 1, "发票号码": "SD-INV-2026-0001", "销方名称": "云南长文本供应商科技发展有限公司第一分公司" }],
	        readModelStatus: "fresh",
	      }), {
	        status: 200,
	        headers: { "Content-Type": "application/json" },
	      });
	    }
	    if (url.pathname === "/api/input-invoice-usage/export") {
	      return new Response(new Blob(["xlsx"], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }), {
	        status: 200,
	        headers: {
	          "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	          "Content-Disposition": "attachment; filename*=UTF-8''%E8%BF%9B%E9%A1%B9.xlsx",
	        },
	      });
	    }
	    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function rowsRequests(fetchMock: ReturnType<typeof installInputInvoiceUsageFetch>) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === "/api/input-invoice-usage/rows");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Input invoice usage page", () => {
  test("surfaces read model refresh state instead of silently showing an empty table", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/input-invoice-usage/rows") {
        return new Response(JSON.stringify({
          rows: [],
          pagination: { page: 1, pageSize: 20, total: 0 },
          filterConfig: [],
          read_model_status: "refreshing",
        }), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.pathname === "/api/input-invoice-usage/filter-options") {
        return new Response(JSON.stringify({ fields: [], read_model_status: "refreshing" }), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    expect(await within(page).findByText("进项发票使用情况读模型正在刷新，完成后页面会自动重新加载。")).toBeInTheDocument();
  });

	  test("adds sidebar route and renders the MUI Table layout without DataGrid", async () => {
    const user = userEvent.setup();
    const fetchMock = installInputInvoiceUsageFetch();

    const financeItems = sidebarGroups.find((group) => group.title === "财务业务")?.items ?? [];
    expect(financeItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "进项发票使用情况", to: "/input-invoice-usage" }),
      ]),
    );

    renderAuthenticatedAppAt("/input-invoice-usage");

	    const page = await screen.findByTestId("input-invoice-usage-page");
	    expect(within(page).getByRole("heading", { name: "进项发票使用情况" })).toBeInTheDocument();
	    expect(document.querySelector(".MuiDataGrid-root")).not.toBeInTheDocument();
	    expect(within(page).getByRole("button", { name: "筛选内容导出" })).toBeInTheDocument();

    const headerRows = within(page).getAllByRole("row").slice(0, 2);
    for (const label of ["进项发票", "支付状态", "OA", "流水"]) {
      expect(within(headerRows[0]).getByRole("columnheader", { name: label })).toBeInTheDocument();
    }
    for (const label of [
      "发票号码",
      "销方",
      "价税合计",
      "不含税/税率税额",
      "业务/货物劳务",
      "支付状态",
      "OA申请人",
      "项目名称",
      "对方户名",
      "金额",
      "摘要/备注",
    ]) {
      expect(within(headerRows[1]).getAllByText(label)).toHaveLength(1);
    }
    const bodyRows = within(page).getAllByRole("row").slice(2);
    expect(bodyRows.some((row) => within(row).queryByText("发票号码"))).toBe(false);
    expect(bodyRows.some((row) => within(row).queryByText("对方户名"))).toBe(false);

    expect(await within(page).findByText("SD-INV-2026-0001")).toBeInTheDocument();
    expect(within(page).getByText("2026-05-02").closest(".MuiChip-root")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "查看发票 SD-INV-2026-0001 详情" })).toBeInTheDocument();
    expect(within(page).getByText("2026-05-03 10:30:00").closest(".MuiChip-root")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "查看流水 云南银行交易对方户名很长很长需要换行显示 详情" })).toBeInTheDocument();
    expect(within(page).getByText("待处理").closest(".input-invoice-usage-payment-cell")).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: /展开.*货物或应税劳务名称/ }));
    expect(within(page).getByRole("button", { name: /收起.*货物或应税劳务名称/ })).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "发票号码 排序" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("sort_field")).toBe("invoice_no");
      expect(request?.searchParams.get("sort_direction")).toBe("asc");
    });

    await user.click(within(page).getByRole("button", { name: "筛选 支付状态" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "待处理 1" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toEqual([{ field: "payment_status", operator: "in", values: ["pending"] }]);
    });

    await user.click(within(page).getByRole("button", { name: "下一页" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("page")).toBe("2");
	    });
	  });

	  test("loads export preview and downloads the current filtered result set", async () => {
	    const user = userEvent.setup();
	    const fetchMock = installInputInvoiceUsageFetch();
	    Object.defineProperty(URL, "createObjectURL", {
	      configurable: true,
	      value: vi.fn(() => "blob:input-invoice-usage-export"),
	    });
	    Object.defineProperty(URL, "revokeObjectURL", {
	      configurable: true,
	      value: vi.fn(),
	    });
	    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

	    renderAuthenticatedAppAt("/input-invoice-usage");

	    const page = await screen.findByTestId("input-invoice-usage-page");
	    await user.click(within(page).getByRole("button", { name: "筛选内容导出" }));

	    expect(await screen.findByText("预计导出 1 行")).toBeInTheDocument();
	    expect(screen.getAllByText("SD-INV-2026-0001").length).toBeGreaterThanOrEqual(1);
	    expect(fetchMock.mock.calls.some(([input]) => {
	      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
	      return url.pathname === "/api/input-invoice-usage/export-preview";
	    })).toBe(true);

	    await user.click(screen.getByRole("button", { name: "下载导出" }));
	    await waitFor(() => {
	      expect(fetchMock.mock.calls.some(([input]) => {
	        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
	        return url.pathname === "/api/input-invoice-usage/export";
	      })).toBe(true);
	    });
	    expect(URL.createObjectURL).toHaveBeenCalled();
	  });
	});
