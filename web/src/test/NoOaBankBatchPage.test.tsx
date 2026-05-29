import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import { sidebarGroups } from "../components/shell/sidebarItems";
import NoOaBankBatchPage from "../pages/NoOaBankBatchPage";
import { expectCustomEventDetailContaining } from "./eventAssertions";

const tagSelectionPayload = {
  version: 3,
  selected_tag_codes: ["fee", "salary", "holiday_bonus", "internal_transfer"],
  inactive_selected_tag_codes: [],
  active_tags: [
    { code: "fee", label: "手续费", output_primary_label: "费用", output_sub_label: "手续费", status: "active" },
    { code: "salary", label: "工资", output_primary_label: "人工成本", output_sub_label: "工资", status: "active" },
    { code: "holiday_bonus", label: "过节费", output_primary_label: "福利", output_sub_label: "过节费", status: "active" },
    { code: "internal_transfer", label: "内部往来款", output_primary_label: "往来", output_sub_label: "内部往来款", status: "active" },
    { code: "custom_no_sub", label: "其他免OA", output_primary_label: "其他免OA", output_sub_label: "", status: "active" },
  ],
};

const listPayload = {
  summary: {
    draft_count: 2,
    submitted_count: 1,
    withdrawn_count: 0,
    conflict_count: 1,
    stale_count: 0,
    total_amount: "20088.00",
    categories: [
      { code: "fee", label: "手续费", primary_label: "费用", sub_label: "手续费", total: 1, draft: 1, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_amount: "88.00" },
      { code: "salary", label: "工资", primary_label: "人工成本", sub_label: "工资", total: 1, draft: 0, submitted: 1, withdrawn: 0, conflict: 0, stale: 0, total_amount: "20000.00" },
      { code: "holiday_bonus", label: "过节费", primary_label: "福利", sub_label: "过节费", total: 1, draft: 1, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_amount: "5000.00" },
      { code: "internal_transfer", label: "内部往来款", primary_label: "往来", sub_label: "内部往来款", total: 1, draft: 0, submitted: 0, withdrawn: 0, conflict: 1, stale: 0, total_amount: "30000.00" },
    ],
  },
  batches: [
    {
      batch_id: "batch-draft-fee",
      batch_type: "fee",
      batch_label: "手续费",
      category_primary_label: "费用",
      category_sub_label: "手续费",
      category_label_path: ["费用", "手续费"],
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
      category_primary_label: "福利",
      category_sub_label: "过节费",
      category_label_path: ["福利", "过节费"],
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
      category_primary_label: "人工成本",
      category_sub_label: "工资",
      category_label_path: ["人工成本", "工资"],
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
      submitted_by: "finance-user",
      submitted_at: "2026-05-10T09:30:00",
      version: 2,
    },
    {
      batch_id: "batch-conflict-transfer",
      batch_type: "internal_transfer",
      batch_label: "内部往来款",
      category_primary_label: "往来",
      category_sub_label: "内部往来款",
      category_label_path: ["往来", "内部往来款"],
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

const feeDetailPayload = {
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
      account_key: "ccb:8106",
      summary: "网银手续费",
      purpose: "结算",
      remark: "月结",
      category_code: "fee",
      category_label: "手续费",
      category_primary_label: "费用",
      category_sub_label: "手续费",
      category_label_path: ["费用", "手续费"],
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

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

function batchesForBucket(payload: typeof listPayload, bucket: string | null) {
  return bucket && bucket !== "all"
    ? payload.batches.filter((batch) => batch.status_bucket === bucket)
    : payload.batches;
}

function installFetchMock(payload = listPayload) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/no-oa-bank-batches/tag-selection" && (!init?.method || init.method === "GET")) {
      return jsonResponse(tagSelectionPayload);
    }
    if (url.pathname === "/api/no-oa-bank-batches/tag-selection" && init?.method === "PUT") {
      const body = JSON.parse(String(init.body ?? "{}"));
      return jsonResponse({ ...tagSelectionPayload, version: 4, selected_tag_codes: body.selected_tag_codes ?? [] });
    }
    if (url.pathname === "/api/no-oa-bank-batches" && (!init?.method || init.method === "GET")) {
      return jsonResponse({ ...payload, batches: batchesForBucket(payload, url.searchParams.get("bucket")) });
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee") {
      return jsonResponse(feeDetailPayload);
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-draft-holiday") {
      return jsonResponse({ batch: payload.batches[1], tag_counts: { holiday_bonus: 5 }, direction_counts: { expense: 5 }, rows: [] });
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-submitted-salary") {
      return jsonResponse({ batch: payload.batches[2], tag_counts: { salary: 8 }, direction_counts: { expense: 8 }, rows: [] });
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-conflict-transfer") {
      return jsonResponse({ batch: payload.batches[3], tag_counts: { internal_transfer: 3 }, direction_counts: { income: 1, expense: 2 }, rows: [] });
    }
    if (url.pathname === "/api/no-oa-bank-batches/submit-selection") {
      return jsonResponse({ batch: payload.batches[0], affected_months: ["2026-05"], workbench_rebuild_queued: true, results: [] });
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-submitted-salary/withdraw") {
      return jsonResponse({ batch: payload.batches[2], affected_months: ["2026-05"], workbench_rebuild_queued: true, results: [] });
    }
    return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("NoOaBankBatchPage", () => {
  test("renders tag management and the three-column main/sub/transaction layout", async () => {
    installFetchMock();
    renderPage();

    expect(await screen.findByRole("heading", { name: "免OA流水批量处理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "免OA流水标签管理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "未提交 3" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "已提交 1" })).toBeInTheDocument();
    expect(screen.getByLabelText("月份")).toBeInTheDocument();
    expect(screen.getByLabelText("银行账户")).toBeInTheDocument();

    const primaryRegion = screen.getByRole("region", { name: "主标签" });
    await waitFor(() => {
      expect(within(primaryRegion).getByRole("button", { name: "费用 1 批 2 条" })).toHaveAttribute("aria-pressed", "true");
    });
    expect(within(primaryRegion).getByRole("button", { name: "福利 1 批 5 条" })).toBeInTheDocument();

    const subRegion = screen.getByRole("region", { name: "子标签" });
    await waitFor(() => {
      expect(within(subRegion).getByRole("button", { name: "手续费 1 批 2 条" })).toHaveAttribute("aria-pressed", "true");
    });

    const transactionRegion = screen.getByRole("region", { name: "流水" });
    expect(within(transactionRegion).getByText("建设银行8106")).toBeInTheDocument();
    expect(await within(transactionRegion).findByText("网银手续费")).toBeInTheDocument();
    expect(within(transactionRegion).getByRole("checkbox", { name: "建设银行8106全选" })).toBeInTheDocument();
    expect(within(transactionRegion).getByRole("checkbox", { name: "选择流水 bank-row-001" })).toBeInTheDocument();
    expect(within(transactionRegion).getByText("自动")).toBeInTheDocument();
  });

  test("saves drawer tag selection with main and child tag toggles", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "免OA流水标签管理" }));
    const drawer = screen.getByRole("dialog", { name: "免OA流水标签管理" });
    await user.click(within(drawer).getByRole("button", { name: "清空" }));
    expect(within(drawer).getByRole("checkbox", { name: "费用" })).not.toBeChecked();
    await user.click(within(drawer).getByRole("checkbox", { name: "费用" }));
    expect(within(drawer).getByRole("checkbox", { name: "费用 / 手续费" })).toBeChecked();
    await user.click(within(drawer).getByRole("checkbox", { name: "费用 / 手续费" }));
    expect(within(drawer).getByRole("checkbox", { name: "费用 / 手续费" })).not.toBeChecked();
    await user.click(within(drawer).getByRole("button", { name: "全选" }));
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/no-oa-bank-batches/tag-selection",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            expected_version: 3,
            selected_tag_codes: ["fee", "salary", "holiday_bonus", "internal_transfer", "custom_no_sub"],
          }),
        }),
      );
    });
    expect(await screen.findByText("免OA流水标签范围已保存")).toBeInTheDocument();
  });

  test("submits only the selected transaction rows and dispatches affected months", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    const relationListener = vi.fn();
    window.addEventListener("workbenchRelationUpdated", relationListener);

    try {
      renderPage();
      await user.click(await screen.findByRole("checkbox", { name: "选择流水 bank-row-001" }));
      await user.click(screen.getByRole("button", { name: "提交批次" }));

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/no-oa-bank-batches/submit-selection",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({ transaction_ids: ["bank-row-001"], note: "" }),
          }),
        );
      });
      expectCustomEventDetailContaining(relationListener, { affectedMonths: ["2026-05"] });
    } finally {
      window.removeEventListener("workbenchRelationUpdated", relationListener);
    }
  });

  test("prevents selecting rows from another bank before clearing the current bank region", async () => {
    const secondFeeBatch = {
      ...listPayload.batches[0],
      batch_id: "batch-draft-fee-boc",
      account_key: "boc:7001",
      bank_name: "中国银行",
      account_last4: "7001",
      total_amount: "18.80",
    };
    const payload = {
      ...listPayload,
      batches: [listPayload.batches[0], secondFeeBatch],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/no-oa-bank-batches/tag-selection") {
        return jsonResponse(tagSelectionPayload);
      }
      if (url.pathname === "/api/no-oa-bank-batches") {
        return jsonResponse({ ...payload, batches: batchesForBucket(payload, url.searchParams.get("bucket")) });
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee") {
        return jsonResponse(feeDetailPayload);
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee-boc") {
        return jsonResponse({
          batch: secondFeeBatch,
          tag_counts: { fee: 1 },
          direction_counts: { expense: 1 },
          rows: [{ ...feeDetailPayload.rows[0], transaction_id: "bank-row-002", account_key: "boc:7001", bank_name: "中国银行", account_last4: "7001" }],
        });
      }
      return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("checkbox", { name: "选择流水 bank-row-001" }));
    await user.click(await screen.findByRole("checkbox", { name: "选择流水 bank-row-002" }));

    expect(await screen.findByText("请先清空已选银行区域，再选择其他银行流水。")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "选择流水 bank-row-001" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "选择流水 bank-row-002" })).not.toBeChecked();
  });

  test("switches to submitted bucket and withdraws a submitted batch", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    const relationListener = vi.fn();
    window.addEventListener("workbenchRelationUpdated", relationListener);

    try {
      renderPage();
      await user.click(await screen.findByRole("button", { name: "已提交 1" }));
      await user.click(await screen.findByRole("button", { name: "人工成本 1 批 8 条" }));
      await user.click(await screen.findByRole("button", { name: "工资 1 批 8 条" }));
      await user.click(await screen.findByRole("button", { name: "撤回批次" }));
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
      expectCustomEventDetailContaining(relationListener, { affectedMonths: ["2026-05"] });
    } finally {
      window.removeEventListener("workbenchRelationUpdated", relationListener);
    }
  });

  test("refreshes tag selection, list, and detail cache after bank transaction category updates", async () => {
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
      const tagSelectionCalls = fetchMock.mock.calls.filter(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/no-oa-bank-batches/tag-selection";
      });
      expect(tagSelectionCalls.length).toBeGreaterThan(1);
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
