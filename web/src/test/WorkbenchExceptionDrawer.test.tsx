import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import WorkbenchExceptionDrawer from "../components/workbench/WorkbenchExceptionDrawer";
import {
  WORKBENCH_AMOUNT_ANOMALY_CODES,
  WORKBENCH_AMOUNT_ANOMALY_LABELS,
  type WorkbenchAmountAnomalyCode,
  type WorkbenchAnomalyItem,
  type WorkbenchExceptionCounts,
  type WorkbenchExceptionView,
  type WorkbenchRelationGroup,
} from "../features/workbench/types";

const anomalyItems: WorkbenchAnomalyItem[] = [
  {
    code: "all_amounts_different",
    label: "三项不一致",
    displayLabel: "三项不一致",
    fingerprint: "b".repeat(64),
    comparisonUnitId: "CASE-1",
    sourceOaIds: ["oa-1"],
    sourceExpenseItemIds: [],
    oaTotal: "100.00",
    bankTotal: "90.00",
    invoiceTotal: "80.00",
    amountDelta: "20.00",
    invoiceRowIds: ["invoice-1"],
    attachmentFileCount: 0,
    displayScope: "group",
    displayPane: "group",
    displayRowId: "",
  },
];

const exceptionCounts: WorkbenchExceptionCounts = {
  total: 1,
  amountTotal: 1,
  documentOnly: 0,
  byCode: {
    oa_bank_equal_invoice_more: 0,
    oa_bank_equal_invoice_less: 0,
    oa_invoice_equal_bank_more: 0,
    oa_invoice_equal_bank_less: 0,
    bank_invoice_equal_oa_less: 0,
    bank_invoice_equal_oa_more: 0,
    all_amounts_different: 1,
  },
};

function group(zone: "paired" | "unpaired"): WorkbenchRelationGroup {
  return {
    id: "case:CASE-1",
    groupType: zone,
    matchConfidence: "high",
    reason: "active_formal_relation",
    rows: { oa: [], bank: [], invoice: [] },
    workbenchAnomaly: {
      code: "workbench_anomaly",
      fingerprint: "a".repeat(64),
      reviewDecision: zone === "paired" ? "accept_paired" : "pending",
      reviewNote: "",
      reviewedBy: zone === "paired" ? "reviewer" : "",
      items: anomalyItems.map((item) => zone === "paired"
        ? { ...item, reviewDecision: "accept_paired", reviewedBy: "reviewer" }
        : item),
    },
  };
}

function renderDrawer(
  bucket: "paired" | "unpaired",
  onReviewAnomaly = vi.fn(),
  canMutateData = true,
  anomalyGroup = group(bucket),
  options: {
    view?: WorkbenchExceptionView;
    selectedExceptionCode?: WorkbenchAmountAnomalyCode | null;
    counts?: WorkbenchExceptionCounts | null;
    onViewChange?: (view: WorkbenchExceptionView) => void;
    onExceptionCodeChange?: (code: WorkbenchAmountAnomalyCode) => void;
  } = {},
) {
  render(
    <WorkbenchExceptionDrawer
      bucket={bucket}
      canMutateData={canMutateData}
      contentGeneration={1}
      error={null}
      exceptionCounts={options.counts === undefined ? exceptionCounts : options.counts}
      groups={[anomalyGroup]}
      hasMore={false}
      loading={false}
      loadingMore={false}
      open
      selectedExceptionCode={options.selectedExceptionCode === undefined
        ? "all_amounts_different"
        : options.selectedExceptionCode}
      total={1}
      view={options.view ?? "amount"}
      onBucketChange={vi.fn()}
      onClose={vi.fn()}
      onExceptionCodeChange={options.onExceptionCodeChange ?? vi.fn()}
      onEnsureGroupDetail={async (value) => value}
      onInvoiceAssignment={vi.fn()}
      onInvoiceEntry={vi.fn()}
      onLoadMore={vi.fn()}
      onReviewAnomaly={onReviewAnomaly}
      onViewChange={options.onViewChange ?? vi.fn()}
    />,
  );
}

async function expandFirstGroup(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "展开异常明细" }));
}

describe("WorkbenchExceptionDrawer", () => {
  it("uses status tabs, view counts, and seven compact server-classification entries", () => {
    renderDrawer("unpaired");
    expect(screen.getByText("未配对异常")).toBeInTheDocument();
    expect(screen.getByText("已配对异常")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "金额异常 1" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "仅资料异常 0" })).toBeInTheDocument();
    const amountFilters = screen.getByRole("radiogroup", { name: "金额异常分类" });
    const amountFilterOptions = within(amountFilters).getAllByRole("radio");
    expect(amountFilterOptions).toHaveLength(7);
    expect(amountFilterOptions.map((option) => option.getAttribute("aria-label"))).toEqual(
      WORKBENCH_AMOUNT_ANOMALY_CODES.map((code) => (
        `${WORKBENCH_AMOUNT_ANOMALY_LABELS[code]} ${exceptionCounts.byCode[code]}`
      )),
    );
    expect(
      Array.from(amountFilters.querySelectorAll(".workbench-anomaly-drawer__amount-family-label")).map(
        (label) => label.textContent,
      ),
    ).toEqual(["OA = 流水", "OA = 发票", "流水 = 发票", "三项互异"]);
    expect(document.querySelector(".workbench-anomaly-drawer__amount-filter-scroll")).not.toBeInTheDocument();
    expect(document.querySelector(".workbench-anomaly-drawer__count")).toHaveTextContent(
      "状态总计 1 项 · 当前 1 项",
    );
  });

  it("hides the amount classification group in the document-only view", () => {
    renderDrawer("unpaired", vi.fn(), true, group("unpaired"), {
      view: "document_only",
      selectedExceptionCode: null,
    });

    expect(screen.getByRole("radio", { name: "仅资料异常 0" })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByRole("radiogroup", { name: "金额异常分类" })).not.toBeInTheDocument();
  });

  it("reports view and amount-category changes through controlled HeroUI groups", async () => {
    const user = userEvent.setup();
    const onViewChange = vi.fn();
    const onExceptionCodeChange = vi.fn();
    renderDrawer("unpaired", vi.fn(), true, group("unpaired"), {
      onViewChange,
      onExceptionCodeChange,
    });

    await user.click(screen.getByRole("radio", { name: "仅资料异常 0" }));
    expect(onViewChange).toHaveBeenCalledWith("document_only");
    await user.click(screen.getByRole("radio", { name: "OA 流水一致，票多 0" }));
    expect(onExceptionCodeChange).toHaveBeenCalledWith("oa_bank_equal_invoice_more");
  });

  it("keeps the collapsed row to the three pane summary and reveals chips only in the popover", async () => {
    const user = userEvent.setup();
    renderDrawer("unpaired");

    expect(screen.getByText("OA · 0项")).toBeInTheDocument();
    expect(screen.getByText("流水 · 0项")).toBeInTheDocument();
    expect(screen.getByText("发票 · 0项")).toBeInTheDocument();
    const heading = screen.getByRole("button", { name: "展开异常明细" }).closest(".workbench-anomaly-drawer__heading");
    expect(heading).not.toBeNull();
    expect(heading).not.toHaveTextContent("三项不一致");
    expect(screen.queryByRole("button", { name: /人工金额判断/ })).not.toBeInTheDocument();

    const indicator = screen.getByRole("button", { name: "该关联组有 1 项异常，查看详情" });
    await user.hover(indicator);
    const popover = await screen.findByRole("dialog", { name: "该关联组异常详情" });
    expect(within(popover).getByText("三项不一致")).toBeVisible();
    expect(within(popover).getByText("OA 100.00 · 流水 90.00 · 发票 80.00")).toBeVisible();
    await user.click(indicator);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "该关联组异常详情" })).not.toBeInTheDocument());
    await user.click(indicator);
    expect(await screen.findByRole("dialog", { name: "该关联组异常详情" })).toBeVisible();
  });

  it("uses the shared three-pane grid and accepts the server classification without a manual gate", async () => {
    const user = userEvent.setup();
    const onReview = vi.fn();
    renderDrawer("unpaired", onReview);

    await expandFirstGroup(user);
    expect(await screen.findByRole("grid", { name: "未配对三栏关联表" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /人工金额判断/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();

    const accept = screen.getByRole("button", { name: "接受异常并进入已配对" });
    expect(accept).toBeEnabled();
    await user.click(accept);
    expect(onReview).toHaveBeenCalledWith(
      expect.objectContaining({ id: "case:CASE-1" }),
      "accept_paired",
    );
  });

  it("keeps evidence available but hides mutation controls from read-only users", async () => {
    const user = userEvent.setup();
    renderDrawer("unpaired", vi.fn(), false);

    await user.hover(screen.getByRole("button", { name: "该关联组有 1 项异常，查看详情" }));
    const popover = await screen.findByRole("dialog", { name: "该关联组异常详情" });
    expect(within(popover).getByText("三项不一致")).toBeVisible();
    await user.keyboard("{Escape}");
    await expandFirstGroup(user);
    expect(screen.queryByRole("region", { name: "异常审阅" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "接受异常并进入已配对" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "留在未配对" })).not.toBeInTheDocument();
  });

  it("withdraws an accepted anomaly back to unpaired", async () => {
    const user = userEvent.setup();
    const onReview = vi.fn();
    renderDrawer("paired", onReview);

    await expandFirstGroup(user);
    await user.click(screen.getByRole("button", { name: "撤回到未配对" }));
    expect(onReview).toHaveBeenCalledWith(
      expect.objectContaining({ id: "case:CASE-1" }),
      "keep_unpaired",
    );
  });

  it("uses the same automatic flow for attachment anomalies", async () => {
    const user = userEvent.setup();
    const attachmentGroup = group("unpaired");
    attachmentGroup.workbenchAnomaly!.items = [{
      code: "oa_invoice_attachment_absent",
      label: "发票附件缺失",
      displayLabel: "发票附件缺失",
      fingerprint: "d".repeat(64),
      comparisonUnitId: "CASE-1:item:0",
      sourceOaIds: ["oa-1"],
      sourceExpenseItemIds: ["oa-1:item:0"],
      oaTotal: "100.00",
      invoiceRowIds: [],
      attachmentFileCount: 0,
      displayScope: "expense_item",
      displayPane: "oa",
      displayRowId: "oa-1:item:0",
    }];
    const onReview = vi.fn();
    renderDrawer("unpaired", onReview, true, attachmentGroup);

    await user.hover(screen.getByRole("button", { name: "该关联组有 1 项异常，查看详情" }));
    expect(await screen.findByText("发票附件缺失")).toBeVisible();
    expect(screen.getByText("未发现可用发票附件")).toBeVisible();
    await user.keyboard("{Escape}");

    await expandFirstGroup(user);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "接受异常并进入已配对" }));
    expect(onReview).toHaveBeenCalledWith(
      expect.objectContaining({ id: "case:CASE-1" }),
      "accept_paired",
    );
  });
});
