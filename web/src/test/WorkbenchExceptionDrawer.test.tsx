import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import WorkbenchExceptionDrawer from "../components/workbench/WorkbenchExceptionDrawer";
import type { WorkbenchAnomalyItem, WorkbenchRelationGroup } from "../features/workbench/types";

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
) {
  render(
    <WorkbenchExceptionDrawer
      bucket={bucket}
      canMutateData={canMutateData}
      contentGeneration={1}
      error={null}
      groups={[anomalyGroup]}
      hasMore={false}
      loading={false}
      loadingMore={false}
      open
      total={1}
      onBucketChange={vi.fn()}
      onClose={vi.fn()}
      onEnsureGroupDetail={async (value) => value}
      onLoadMore={vi.fn()}
      onReviewAnomaly={onReviewAnomaly}
    />,
  );
}

async function expandFirstGroup(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "展开异常明细" }));
}

describe("WorkbenchExceptionDrawer", () => {
  it("uses the unpaired and paired anomaly tab labels", () => {
    renderDrawer("unpaired");
    expect(screen.getByText("未配对异常")).toBeInTheDocument();
    expect(screen.getByText("已配对异常")).toBeInTheDocument();
  });

  it("keeps the collapsed row to the three pane summary and reveals chips only in the popover", async () => {
    const user = userEvent.setup();
    renderDrawer("unpaired");

    expect(screen.getByText("OA · 0项")).toBeInTheDocument();
    expect(screen.getByText("流水 · 0项")).toBeInTheDocument();
    expect(screen.getByText("发票 · 0项")).toBeInTheDocument();
    expect(screen.queryByText("三项不一致")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /人工金额判断/ })).not.toBeInTheDocument();

    const indicator = screen.getByRole("button", { name: "该关联组有 1 项异常，查看详情" });
    await user.hover(indicator);
    expect(await screen.findByText("三项不一致")).toBeVisible();
    expect(screen.getByText("OA 100.00 · 流水 90.00 · 发票 80.00")).toBeVisible();
    await user.click(indicator);
    await waitFor(() => expect(screen.queryByText("三项不一致")).not.toBeInTheDocument());
    await user.click(indicator);
    expect(await screen.findByText("三项不一致")).toBeVisible();
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
    expect(await screen.findByText("三项不一致")).toBeVisible();
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
