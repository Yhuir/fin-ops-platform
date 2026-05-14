import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import { sidebarGroups } from "../components/shell/sidebarItems";
import NoOaBankBatchPage from "../pages/NoOaBankBatchPage";

const listPayload = {
  summary: {
    draft_count: 1,
    submitted_count: 1,
    withdrawn_count: 1,
    conflict_count: 1,
    total_amount: "20088.00",
  },
  batches: [
    {
      batch_id: "batch-draft-fee",
      batch_type: "fee",
      batch_label: "手续费",
      scope_month: "2026-05",
      account_key: "ccb:8106",
      bank_name: "建设银行",
      account_last4: "8106",
      status: "draft",
      row_count: 2,
      total_amount: "88.00",
      version: 1,
    },
    {
      batch_id: "batch-submitted-salary",
      batch_type: "salary",
      batch_label: "工资",
      scope_month: "2026-05",
      account_key: "icbc:6386",
      bank_name: "工商银行",
      account_last4: "6386",
      status: "submitted",
      row_count: 8,
      total_amount: "20000.00",
      submitted_by: "finance-user",
      submitted_at: "2026-05-10T09:30:00",
      version: 2,
    },
    {
      batch_id: "batch-conflict-transfer",
      batch_type: "internal_transfer",
      batch_label: "内部往来款",
      scope_month: "2026-05",
      account_key: "",
      bank_name: "多账户",
      account_last4: "",
      status: "conflict",
      row_count: 3,
      total_amount: "30000.00",
      conflict_reason: "存在多解",
      version: 1,
    },
  ],
};

const detailPayload = {
  batch: listPayload.batches[0],
  rows: [
    {
      transaction_id: "bank-row-001",
      trade_time: "2026-05-03 10:20:00",
      counterparty_name: "建设银行",
      direction: "expense",
      direction_label: "支",
      amount: "8.80",
      summary: "网银手续费",
      purpose: "结算",
      remark: "月结",
      category_source: "auto",
    },
  ],
};

function renderPage() {
  return render(
    <MuiProviders>
      <NoOaBankBatchPage />
    </MuiProviders>,
  );
}

function installFetchMock() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/no-oa-bank-batches" && (!init?.method || init.method === "GET")) {
      return new Response(JSON.stringify(listPayload), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee") {
      return new Response(JSON.stringify(detailPayload), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname.endsWith("/submit") || url.pathname.endsWith("/withdraw")) {
      return new Response(JSON.stringify({ batch: listPayload.batches[0], affected_months: ["2026-05"], workbench_rebuild_queued: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify({ message: `Unhandled ${url.pathname}` }), { status: 404, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("NoOaBankBatchPage", () => {
  test("renders title, filters, summary cards, and detail rows", async () => {
    const user = userEvent.setup();
    installFetchMock();
    renderPage();

    expect(await screen.findByRole("heading", { name: "免OA流水批量处理" })).toBeInTheDocument();
    expect(screen.getByLabelText("月份")).toBeInTheDocument();
    expect(screen.getByLabelText("类型")).toBeInTheDocument();
    expect(screen.getByLabelText("状态")).toBeInTheDocument();
    expect(screen.getByLabelText("银行账户")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新" })).toBeInTheDocument();
    expect(screen.getByText("待提交批次")).toBeInTheDocument();
    expect(screen.getByText("已提交批次")).toBeInTheDocument();
    expect(screen.getByText("已撤回批次")).toBeInTheDocument();
    expect(screen.getByText("冲突批次")).toBeInTheDocument();
    expect(screen.getByText("金额合计")).toBeInTheDocument();
    expect(screen.getByText("建设银行 / 2026-05")).toBeInTheDocument();
    expect(screen.getByText("手续费")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "展开 手续费 建设银行8106 2026-05 明细" }));

    expect(await screen.findByText("网银手续费")).toBeInTheDocument();
    expect(screen.getByText("自动")).toBeInTheDocument();
  });

  test("shows draft, submitted, and conflict actions correctly", async () => {
    installFetchMock();
    renderPage();

    const draftRow = await screen.findByRole("row", { name: /手续费.*建设银行8106.*待提交/ });
    expect(within(draftRow).getByRole("button", { name: "提交批次" })).toBeEnabled();

    const submittedRow = screen.getByRole("row", { name: /工资.*工商银行6386.*已提交.*finance-user.*2026-05-10/ });
    expect(within(submittedRow).getByRole("button", { name: "撤回批次" })).toBeEnabled();

    const conflictRow = screen.getByRole("row", { name: /内部往来款.*多账户.*冲突.*存在多解/ });
    expect(within(conflictRow).getByRole("button", { name: "提交批次" })).toBeDisabled();
  });

  test("submits and withdraws batches, refreshes list, and dispatches workbench relation updates", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    const relationListener = vi.fn();
    window.addEventListener("workbenchRelationUpdated", relationListener);

    try {
      renderPage();

      const submitButton = (await screen.findAllByRole("button", { name: "提交批次" }))
        .find((button) => !button.hasAttribute("disabled"));
      expect(submitButton).toBeDefined();
      await user.click(submitButton as HTMLButtonElement);
      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/no-oa-bank-batches/batch-draft-fee/submit",
          expect.objectContaining({ method: "POST" }),
        );
      });
      expect(relationListener).toHaveBeenCalledTimes(1);

      await user.click(screen.getByRole("button", { name: "撤回批次" }));
      await user.type(screen.getByLabelText("撤回原因"), "金额复核");
      await user.click(screen.getByRole("button", { name: "确认撤回" }));

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/no-oa-bank-batches/batch-submitted-salary/withdraw",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({ expected_version: 2, reason: "金额复核" }),
          }),
        );
      });
      expect(relationListener).toHaveBeenCalledTimes(2);
      expect(fetchMock.mock.calls.filter(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/no-oa-bank-batches";
      }).length).toBeGreaterThan(2);
    } finally {
      window.removeEventListener("workbenchRelationUpdated", relationListener);
    }
  });

  test("bulk submits only selected draft batches", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderPage();

    await user.click(await screen.findByRole("checkbox", { name: "选择 手续费 建设银行8106 2026-05" }));
    await user.click(screen.getByRole("button", { name: "批量提交选中" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/no-oa-bank-batches/submit",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ batches: [{ batch_id: "batch-draft-fee", expected_version: 1 }] }),
        }),
      );
    });
  });

  test("bulk submit reports partial failures instead of showing all-success", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/no-oa-bank-batches" && (!init?.method || init.method === "GET")) {
        return new Response(JSON.stringify(listPayload), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/no-oa-bank-batches/submit") {
        return new Response(JSON.stringify({
          summary: { submitted: 0, failed: 1 },
          results: [{ batch_id: "batch-draft-fee", status: "failed", error: "no_oa_bank_batch_version_conflict" }],
          affected_months: [],
          workbench_rebuild_queued: false,
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({ message: `Unhandled ${url.pathname}` }), { status: 404, headers: { "Content-Type": "application/json" } });
    }));
    renderPage();

    await user.click(await screen.findByRole("checkbox", { name: "选择 手续费 建设银行8106 2026-05" }));
    await user.click(screen.getByRole("button", { name: "批量提交选中" }));

    expect(await screen.findByText("批量提交失败，请查看失败项后重试")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "选择 手续费 建设银行8106 2026-05" })).toBeChecked();
  });

  test("sidebar exposes the no OA bank batch entry", () => {
    const financeItems = sidebarGroups.find((group) => group.title === "财务业务")?.items ?? [];

    expect(financeItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          label: "免OA流水批量处理",
          to: "/no-oa-bank-batches",
        }),
      ]),
    );
  });
});
