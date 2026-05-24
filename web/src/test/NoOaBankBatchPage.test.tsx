import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import { sidebarGroups } from "../components/shell/sidebarItems";
import NoOaBankBatchPage from "../pages/NoOaBankBatchPage";
import { expectCustomEventDetailContaining } from "./eventAssertions";

const listPayload = {
  summary: {
    draft_count: 2,
    submitted_count: 1,
    withdrawn_count: 1,
    conflict_count: 1,
    stale_count: 0,
    total_amount: "20088.00",
    categories: [
      { code: "fee", label: "手续费", total: 1, draft: 1, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_amount: "88.00" },
      { code: "salary", label: "工资", total: 1, draft: 0, submitted: 1, withdrawn: 0, conflict: 0, stale: 0, total_amount: "20000.00" },
      { code: "holiday_bonus", label: "过节费", total: 1, draft: 1, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_amount: "5000.00" },
      { code: "bonus", label: "奖金", total: 0, draft: 0, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_amount: "0.00" },
      { code: "tax_payment", label: "税款", total: 0, draft: 0, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_amount: "0.00" },
      { code: "treasury_tax_collection", label: "代理国库税收收缴", total: 0, draft: 0, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_amount: "0.00" },
      { code: "social_security", label: "社保款", total: 0, draft: 0, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_amount: "0.00" },
      { code: "internal_transfer", label: "内部往来款", total: 1, draft: 0, submitted: 0, withdrawn: 0, conflict: 1, stale: 0, total_amount: "30000.00" },
    ],
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
      status_bucket: "unsubmitted",
      row_count: 2,
      total_amount: "88.00",
      tag_counts: { fee: 2 },
      direction_counts: { expense: 2 },
      can_submit: true,
      can_withdraw: false,
      blocked_reason: "",
      version: 1,
    },
    {
      batch_id: "batch-draft-holiday",
      batch_type: "holiday_bonus",
      batch_label: "过节费",
      scope_month: "2026-05",
      account_key: "boc:7001",
      bank_name: "中国银行",
      account_last4: "7001",
      status: "draft",
      status_bucket: "unsubmitted",
      row_count: 5,
      total_amount: "5000.00",
      tag_counts: { holiday_bonus: 5 },
      direction_counts: { expense: 5 },
      can_submit: true,
      can_withdraw: false,
      blocked_reason: "",
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
      status_bucket: "submitted",
      row_count: 8,
      total_amount: "20000.00",
      tag_counts: { salary: 8 },
      direction_counts: { expense: 8 },
      can_submit: false,
      can_withdraw: true,
      blocked_reason: "已提交批次不可重复提交",
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
      status_bucket: "unsubmitted",
      row_count: 3,
      total_amount: "30000.00",
      tag_counts: { internal_transfer: 3 },
      direction_counts: { income: 1, expense: 2 },
      conflict_reason: "存在多解",
      can_submit: false,
      can_withdraw: false,
      blocked_reason: "存在多解",
      version: 1,
    },
  ],
};

const detailPayload = {
  batch: listPayload.batches[0],
  tag_counts: { fee: 1 },
  direction_counts: { expense: 1 },
  rows: [
    {
      transaction_id: "bank-row-001",
      trade_time: "2026-05-03 10:20:00",
      counterparty_name: "建设银行",
      direction: "expense",
      direction_label: "支",
      amount: "8.80",
      bank_name: "建设银行",
      account_last4: "8106",
      account_key: "建设银行:8106",
      summary: "网银手续费",
      purpose: "结算",
      remark: "月结",
      category_code: "fee",
      category_label: "手续费",
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
      const bucket = url.searchParams.get("bucket");
      const batches = bucket && bucket !== "all"
        ? listPayload.batches.filter((batch) => batch.status_bucket === bucket)
        : listPayload.batches;
      return new Response(JSON.stringify({ ...listPayload, batches }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee") {
      return new Response(JSON.stringify(detailPayload), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-submitted-salary") {
      return new Response(JSON.stringify({
        batch: listPayload.batches.find((batch) => batch.batch_id === "batch-submitted-salary"),
        tag_counts: { salary: 8 },
        direction_counts: { expense: 8 },
        rows: [],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
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
  test("renders bucket toggle, fixed category rail, batch tree, and right selected batch detail pane", async () => {
    installFetchMock();
    renderPage();

    expect(await screen.findByRole("heading", { name: "免OA流水批量处理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "未提交 3" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "已提交 1" })).toBeInTheDocument();
    expect(screen.getByLabelText("月份")).toBeInTheDocument();
    expect(screen.getByLabelText("银行账户")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新" })).toBeInTheDocument();
    const categoryRail = screen.getByRole("region", { name: "免OA分类" });
    expect(within(categoryRail).getByRole("button", { name: "手续费 1 批 2 条" })).toHaveAttribute("aria-pressed", "true");
    expect(within(categoryRail).getByRole("button", { name: "工资 0 批 0 条" })).toBeInTheDocument();
    expect(within(categoryRail).getByRole("button", { name: "过节费 1 批 5 条" })).toBeInTheDocument();
    expect(within(categoryRail).getByRole("button", { name: "奖金 0 批 0 条" })).toBeInTheDocument();
    expect(within(categoryRail).getByRole("button", { name: "税款 0 批 0 条" })).toBeInTheDocument();
    expect(within(categoryRail).getByRole("button", { name: "代理国库税收收缴 0 批 0 条" })).toBeInTheDocument();
    expect(within(categoryRail).getByRole("button", { name: "社保款 0 批 0 条" })).toBeInTheDocument();
    expect(within(categoryRail).getByRole("button", { name: "内部往来款 1 批 3 条" })).toBeInTheDocument();

    expect(screen.getByRole("region", { name: "免OA批次" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "批次明细" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "手续费 1 批 / 2 条" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /手续费.*建设银行8106.*2026-05.*2 条/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /内部往来款.*多账户.*2026-05.*3 条/ })).not.toBeInTheDocument();

    expect(await screen.findByText("网银手续费")).toBeInTheDocument();
    expect(screen.getByText("手续费 1")).toBeInTheDocument();
    expect(screen.getByText("自动")).toBeInTheDocument();
    expect(screen.getByText("交易时间")).toBeInTheDocument();
    expect(screen.getByText("对方户名")).toBeInTheDocument();
    expect(screen.queryByText("收/支")).not.toBeInTheDocument();
    expect(screen.getByText("支")).toBeInTheDocument();
    expect(screen.getAllByText("建设银行8106").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("摘要/用途/备注")).toBeInTheDocument();
    expect(screen.getByText("分类来源")).toBeInTheDocument();
  });

  test("shows draft-only submit selection and stale withdraw when allowed", async () => {
    installFetchMock();
    renderPage();

    await screen.findByRole("heading", { name: "手续费 1 批 / 2 条" });
    const list = screen.getByRole("region", { name: "免OA批次" });
    expect(within(list).getByRole("checkbox", { name: "选择 手续费 建设银行8106 2026-05" })).toBeEnabled();

    await userEvent.setup().click(screen.getByRole("button", { name: "内部往来款 1 批 3 条" }));
    expect(within(list).getByRole("checkbox", { name: "选择 内部往来款 多账户 2026-05" })).toBeDisabled();
  });

  test("switches bucket to submitted, updates category counts, and resets selected detail", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "已提交 1" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("bucket=submitted"),
        expect.objectContaining({ method: "GET" }),
      );
    });
    const categoryRail = screen.getByRole("region", { name: "免OA分类" });
    expect(within(categoryRail).getByRole("button", { name: "手续费 0 批 0 条" })).toHaveAttribute("aria-pressed", "true");
    expect(within(categoryRail).getByRole("button", { name: "工资 1 批 8 条" })).toBeInTheDocument();
    expect(within(categoryRail).getByRole("button", { name: "奖金 0 批 0 条" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "手续费 0 批 / 0 条" })).toBeInTheDocument();
    expect(screen.getByText("当前状态下暂无手续费批次")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "工资 1 批 8 条" }));
    expect(await screen.findByText(/finance-user/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "工资 1 批 / 8 条" })).toBeInTheDocument();
  });

  test("submits and withdraws batches, refreshes cache, and dispatches affected months", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    const relationListener = vi.fn();
    window.addEventListener("workbenchRelationUpdated", relationListener);

    try {
      renderPage();

      await user.click(await screen.findByRole("button", { name: "提交批次" }));
      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/no-oa-bank-batches/batch-draft-fee/submit",
          expect.objectContaining({ method: "POST" }),
        );
      });
      expectCustomEventDetailContaining(relationListener, { affectedMonths: ["2026-05"] });

      await user.click(screen.getByRole("button", { name: "已提交 1" }));
      await user.click(await screen.findByRole("button", { name: "工资 1 批 8 条" }));
      await user.click(screen.getByRole("button", { name: /工资.*工商银行6386/ }));
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

  test("moves a submitted draft batch into the submitted bucket and refreshes header counts", async () => {
    const user = userEvent.setup();
    let feeSubmitted = false;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      const currentPayload = feeSubmitted
        ? {
            ...listPayload,
            summary: {
              ...listPayload.summary,
              draft_count: 1,
              submitted_count: 2,
              categories: listPayload.summary.categories.map((category) => {
                if (category.code !== "fee") {
                  return category;
                }
                return { ...category, draft: 0, submitted: 1 };
              }),
            },
            batches: listPayload.batches.map((batch) => {
              if (batch.batch_id !== "batch-draft-fee") {
                return batch;
              }
              return {
                ...batch,
                status: "submitted",
                status_bucket: "submitted",
                can_submit: false,
                can_withdraw: true,
                submitted_by: "finance-user",
                submitted_at: "2026-05-18T01:30:00",
                version: 2,
              };
            }),
          }
        : listPayload;

      if (url.pathname === "/api/no-oa-bank-batches" && (!init?.method || init.method === "GET")) {
        const bucket = url.searchParams.get("bucket");
        const batches = bucket && bucket !== "all"
          ? currentPayload.batches.filter((batch) => batch.status_bucket === bucket)
          : currentPayload.batches;
        return new Response(JSON.stringify({ ...currentPayload, batches }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee") {
        return new Response(JSON.stringify({
          ...detailPayload,
          batch: currentPayload.batches.find((batch) => batch.batch_id === "batch-draft-fee"),
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee/submit") {
        feeSubmitted = true;
        return new Response(JSON.stringify({
          batch: currentPayload.batches.find((batch) => batch.batch_id === "batch-draft-fee"),
          affected_months: ["2026-05"],
          workbench_rebuild_queued: true,
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({ message: `Unhandled ${url.pathname}` }), { status: 404, headers: { "Content-Type": "application/json" } });
    }));

    renderPage();

    await user.click(await screen.findByRole("button", { name: "提交批次" }));

    expect(await screen.findByText("批次已提交")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "未提交 2" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "已提交 2" })).toBeInTheDocument();
    });
    expect(screen.getByText("当前状态下暂无手续费批次")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "已提交 2" }));

    expect(await screen.findByRole("heading", { name: "手续费 1 批 / 2 条" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /手续费.*建设银行8106.*2026-05.*2 条/ })).toBeInTheDocument();
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

  test("refreshes list and clears detail cache after bank transaction category updates", async () => {
    const fetchMock = installFetchMock();
    renderPage();

    await screen.findByText("网银手续费");
    const initialDetailCalls = fetchMock.mock.calls.filter(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/no-oa-bank-batches/batch-draft-fee";
    }).length;

    act(() => {
      window.dispatchEvent(new CustomEvent("bankTransactionCategoryUpdated", { detail: { affectedMonths: ["2026-05"] } }));
    });

    await waitFor(() => {
      const listCalls = fetchMock.mock.calls.filter(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/no-oa-bank-batches";
      });
      expect(listCalls.length).toBeGreaterThan(1);
    });
    await waitFor(() => {
      const detailCalls = fetchMock.mock.calls.filter(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/no-oa-bank-batches/batch-draft-fee";
      });
      expect(detailCalls.length).toBeGreaterThan(initialDetailCalls);
    });
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
