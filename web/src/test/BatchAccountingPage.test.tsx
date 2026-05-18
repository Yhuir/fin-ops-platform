import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import { sidebarGroups } from "../components/shell/sidebarItems";
import BatchAccountingPage from "../pages/BatchAccountingPage";

const unsubmittedPayload = {
  summary: {
    unsubmitted_count: 2,
    submitted_count: 1,
  },
  bank_rows: [
    {
      id: "bank-row-001",
      trade_time: "2026-01-07 15:54:00",
      counterparty_name: "批量账务集中处理",
      direction: "expense",
      direction_label: "支出",
      amount: "1200.00",
      bank_name: "建行",
      account_last4: "8106",
      relation_id: "",
      version: 1,
    },
    {
      id: "bank-row-002",
      trade_time: "2026-01-08 09:00:00",
      counterparty_name: "批量账务集中处理",
      direction: "expense",
      direction_label: "支出",
      amount: "800.00",
      bank_name: "招行",
      account_last4: "1888",
      relation_id: "",
      version: 1,
    },
  ],
  oa_rows: [
    {
      id: "oa-exp-1001",
      applicant: "刘晨",
      apply_time: "2026-01-06",
      project_name: "品牌广告投放；市场活动项目",
      amount: "700.00",
      reason: "1月日常报销，包含广告素材制作和渠道投放费用",
      linked_invoice_row_ids: ["oa-att-inv-1001-01"],
    },
    {
      id: "oa-exp-1002",
      applicant: "王青",
      apply_time: "2026-01-07",
      project_name: "客户拜访差旅报销",
      amount: "500.00",
      reason: "上海客户拜访交通与餐费",
      linked_invoice_row_ids: [],
    },
  ],
};

const submittedPayload = {
  summary: {
    unsubmitted_count: 1,
    submitted_count: 2,
  },
  bank_rows: [
    {
      id: "bank-row-submitted-001",
      trade_time: "2026-02-10 12:30:00",
      counterparty_name: "批量账务集中处理",
      direction: "expense",
      direction_label: "支出",
      amount: "900.00",
      bank_name: "建行",
      account_last4: "8106",
      relation_id: "CASE-202602-001",
      version: 2,
    },
  ],
  oa_rows: [
    {
      id: "oa-exp-2001",
      applicant: "陈敏",
      apply_time: "2026-02-08",
      project_name: "办公室耗材采购",
      amount: "900.00",
      reason: "2月行政耗材日常报销",
      linked_invoice_row_ids: ["oa-att-inv-2001-01"],
    },
  ],
  relations_by_bank_row_id: {
    "bank-row-submitted-001": {
      relation_id: "CASE-202602-001",
      oa_rows: [
        {
          id: "oa-exp-2001",
          applicant: "陈敏",
          apply_time: "2026-02-08",
          project_name: "办公室耗材采购",
          amount: "900.00",
          reason: "2月行政耗材日常报销",
          linked_invoice_row_ids: ["oa-att-inv-2001-01"],
        },
      ],
      invoice_rows: [
        {
          id: "oa-att-inv-2001-01",
          type: "invoice",
        },
      ],
    },
  },
};

function renderPage() {
  return render(
    <MuiProviders>
      <BatchAccountingPage />
    </MuiProviders>,
  );
}

function installFetchMock() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/batch-accounting" && (!init?.method || init.method === "GET")) {
      const bucket = url.searchParams.get("bucket");
      const payload = bucket === "submitted" ? submittedPayload : unsubmittedPayload;
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/batch-accounting/submit") {
      return new Response(JSON.stringify({
        success: true,
        relation_id: "CASE-202601-001",
        affected_row_ids: ["bank-row-001", "oa-exp-1001", "oa-exp-1002", "oa-att-inv-1001-01"],
        affected_months: ["2026-01"],
        message: "已关联批量账务流水与 2 项 OA。",
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/batch-accounting/CASE-202602-001/withdraw") {
      return new Response(JSON.stringify({
        success: true,
        relation_id: "CASE-202602-001",
        affected_months: ["2026-02"],
        message: "已撤回批量账务关联。",
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({ message: `Unhandled ${url.pathname}` }), { status: 404, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("BatchAccountingPage", () => {
  test("renders controls, bank list, and selectable OA table for unsubmitted rows", async () => {
    installFetchMock();
    renderPage();

    expect(await screen.findByRole("heading", { name: "日常报销批量账务管理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "未提交 2" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "已提交 1" })).toBeInTheDocument();
    expect(screen.getByLabelText("年份")).toHaveValue(2026);
    expect(screen.getByRole("button", { name: "刷新" })).toBeInTheDocument();

    const bankList = screen.getByRole("region", { name: "批量账务流水" });
    expect(within(bankList).getAllByRole("button")).toHaveLength(2);
    expect(within(bankList).queryByRole("table")).not.toBeInTheDocument();
    expect(within(bankList).getByRole("button", { name: /批量账务集中处理.*1,200.00.*2026-01-07 15:54:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true");

    const oaTable = screen.getByRole("table", { name: "可关联OA项" });
    expect(within(oaTable).getByRole("checkbox", { name: "选择 刘晨 2026-01-06" })).toBeInTheDocument();
    expect(within(oaTable).getByText("刘晨")).toBeInTheDocument();
    expect(within(oaTable).getByText("2026-01-06")).toBeInTheDocument();
    expect(within(oaTable).getByText("品牌广告投放；市场活动项目")).toBeInTheDocument();
    expect(within(oaTable).getByText("700.00")).toBeInTheDocument();
    expect(within(oaTable).getByText("1月日常报销，包含广告素材制作和渠道投放费用")).toBeInTheDocument();
  });

  test("updates selected totals, disables mismatches, and submits matching OA rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    const relationListener = vi.fn();
    window.addEventListener("workbenchRelationUpdated", relationListener);

    try {
      renderPage();

      await screen.findByRole("heading", { name: "日常报销批量账务管理" });
      expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();

      await user.click(screen.getByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
      expect(screen.getByText("已选 OA 1 项")).toBeInTheDocument();
      expect(screen.getByText("已选 OA 金额 700.00")).toBeInTheDocument();
      expect(screen.getByText("差额 500.00")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();

      await user.click(screen.getByRole("checkbox", { name: "选择 王青 2026-01-07" }));
      expect(screen.getByText("已选 OA 2 项")).toBeInTheDocument();
      expect(screen.getByText("已选 OA 金额 1,200.00")).toBeInTheDocument();
      expect(screen.getByText("差额 0.00")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeEnabled();

      await user.click(screen.getByRole("button", { name: "关联OA项与流水" }));

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/batch-accounting/submit",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({
              year: "2026",
              bank_row_id: "bank-row-001",
              oa_row_ids: ["oa-exp-1001", "oa-exp-1002"],
              expected_version: 1,
            }),
          }),
        );
      });
      expect(await screen.findByText("已关联批量账务流水与 2 项 OA。")).toBeInTheDocument();
      expect(relationListener).toHaveBeenCalledWith(expect.objectContaining({
        detail: { affectedMonths: ["2026-01"] },
      }));
    } finally {
      window.removeEventListener("workbenchRelationUpdated", relationListener);
    }
  });

  test("filters right side OA rows across applicant, project, amount, and reason", async () => {
    const user = userEvent.setup();
    installFetchMock();
    renderPage();

    const oaTable = await screen.findByRole("table", { name: "可关联OA项" });
    expect(within(oaTable).getByText("刘晨")).toBeInTheDocument();
    expect(within(oaTable).getByText("王青")).toBeInTheDocument();

    await user.type(screen.getByLabelText("搜索OA内容"), "上海客户");
    expect(within(oaTable).queryByText("刘晨")).not.toBeInTheDocument();
    expect(within(oaTable).getByText("王青")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "清空搜索" }));
    expect(within(oaTable).getByText("刘晨")).toBeInTheDocument();
    expect(within(oaTable).getByText("王青")).toBeInTheDocument();

    await user.type(screen.getByLabelText("搜索OA内容"), "700.00");
    expect(within(oaTable).getByText("刘晨")).toBeInTheDocument();
    expect(within(oaTable).queryByText("王青")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "清空搜索" }));
    await user.type(screen.getByLabelText("搜索OA内容"), "品牌广告");
    expect(within(oaTable).getByText("刘晨")).toBeInTheDocument();
    expect(within(oaTable).queryByText("王青")).not.toBeInTheDocument();
  });

  test("renders submitted bucket as read-only associated OA and withdraws with a reason", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    const relationListener = vi.fn();
    window.addEventListener("workbenchRelationUpdated", relationListener);

    try {
      renderPage();
      await user.click(await screen.findByRole("button", { name: "已提交 1" }));

      expect(await screen.findByRole("button", { name: /批量账务集中处理.*900.00.*2026-02-10 12:30:00.*支出.*建行 8106/ })).toBeInTheDocument();
      const associatedTable = screen.getByRole("table", { name: "已关联OA项" });
      expect(within(associatedTable).queryByRole("checkbox")).not.toBeInTheDocument();
      expect(within(associatedTable).getByText("陈敏")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "撤回关联" })).toBeEnabled();

      await user.click(screen.getByRole("button", { name: "撤回关联" }));
      await user.type(screen.getByLabelText("撤回原因"), "选择错误");
      await user.click(screen.getByRole("button", { name: "确认撤回" }));

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/batch-accounting/CASE-202602-001/withdraw",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({ expected_version: 2, reason: "选择错误" }),
          }),
        );
      });
      expect(await screen.findByText("已撤回批量账务关联。")).toBeInTheDocument();
      expect(relationListener).toHaveBeenCalledWith(expect.objectContaining({
        detail: { affectedMonths: ["2026-02"] },
      }));
    } finally {
      window.removeEventListener("workbenchRelationUpdated", relationListener);
    }
  });

  test("sidebar exposes the batch accounting entry near no OA bank batches", () => {
    const financeItems = sidebarGroups.find((group) => group.title === "财务业务")?.items ?? [];

    expect(financeItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          label: "批量账务",
          to: "/batch-accounting",
        }),
      ]),
    );
  });
});
