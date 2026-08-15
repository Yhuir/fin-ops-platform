import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import WorkbenchExceptionDrawer from "../components/workbench/WorkbenchExceptionDrawer";
import type { WorkbenchRelationGroup } from "../features/workbench/types";

const anomalyItems = [
  {
    code: "oa_bank_amount_mismatch" as const,
    label: "OA流水金额不一致",
    displayLabel: "OA流水金额不一致",
    fingerprint: "b".repeat(64),
    comparisonUnitId: "CASE-1",
    sourceOaIds: ["oa-1"],
    sourceExpenseItemIds: [],
    oaTotal: "100.00",
    bankTotal: "90.00",
    amountDelta: "10.00",
    mismatchPair: ["oa", "bank"] as ["oa", "bank"],
    invoiceRowIds: [],
    attachmentFileCount: 0,
  },
  {
    code: "bank_invoice_amount_mismatch" as const,
    label: "流水发票金额不一致",
    displayLabel: "流水发票金额不一致",
    fingerprint: "c".repeat(64),
    comparisonUnitId: "CASE-1",
    sourceOaIds: ["oa-1"],
    sourceExpenseItemIds: [],
    bankTotal: "90.00",
    invoiceTotal: "80.00",
    amountDelta: "10.00",
    mismatchPair: ["bank", "invoice"] as ["bank", "invoice"],
    invoiceRowIds: ["invoice-1"],
    attachmentFileCount: 0,
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
      reviewedItemFingerprints: zone === "paired" ? anomalyItems.map((item) => item.fingerprint) : [],
      reviewClassificationCodes: zone === "paired"
        ? ["oa_bank_amount_mismatch", "bank_invoice_amount_mismatch"]
        : [],
      reviewNote: "",
      reviewedBy: zone === "paired" ? "reviewer" : "",
      items: anomalyItems,
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

describe("WorkbenchExceptionDrawer", () => {
  it("uses the unpaired and paired anomaly tab labels", () => {
    renderDrawer("unpaired");
    expect(screen.getByText("未配对异常")).toBeInTheDocument();
    expect(screen.getByText("已配对异常")).toBeInTheDocument();
  });

  it("requires a manual amount classification before either decision", async () => {
    const user = userEvent.setup();
    const onReview = vi.fn();
    renderDrawer("unpaired", onReview);
    const keep = screen.getByRole("button", { name: "留在未配对" });
    const accept = screen.getByRole("button", { name: "进入已配对" });
    expect(keep).toBeDisabled();
    expect(accept).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /人工金额判断/ }));
    await user.click(screen.getByRole("option", { name: "OA流水金额不一致" }));
    await user.click(screen.getByRole("option", { name: "流水发票金额不一致" }));
    await user.keyboard("{Escape}");
    expect(accept).toBeEnabled();
    await user.click(accept);

    expect(onReview).toHaveBeenCalledWith(
      expect.objectContaining({ id: "case:CASE-1" }),
      "accept_paired",
      anomalyItems.map((item) => item.fingerprint),
      ["oa_bank_amount_mismatch", "bank_invoice_amount_mismatch"],
    );
  });

  it("keeps no anomaly mutually exclusive with the mismatch classifications", async () => {
    const user = userEvent.setup();
    renderDrawer("unpaired");

    await user.click(screen.getByRole("button", { name: /人工金额判断/ }));
    await user.click(screen.getByRole("option", { name: "OA流水金额不一致" }));
    await user.click(screen.getByRole("option", { name: "无异常" }));

    expect(screen.getByRole("option", { name: "无异常" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("option", { name: "OA流水金额不一致" })).toHaveAttribute("aria-selected", "false");
  });

  it("shows only specific amount chips", () => {
    renderDrawer("unpaired");
    expect(screen.getAllByText("OA流水金额不一致").length).toBeGreaterThan(0);
    expect(screen.getAllByText("流水发票金额不一致").length).toBeGreaterThan(0);
    expect(screen.queryByText(/^金额不一致$/)).not.toBeInTheDocument();
  });

  it("keeps anomaly evidence readable without exposing local review controls to read-only users", () => {
    renderDrawer("unpaired", vi.fn(), false);
    expect(screen.getByText("OA流水金额不一致")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /人工金额判断/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "进入已配对" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "留在未配对" })).not.toBeInTheDocument();
  });

  it("withdraws an accepted anomaly back to unpaired", async () => {
    const user = userEvent.setup();
    const onReview = vi.fn();
    renderDrawer("paired", onReview);
    await user.click(screen.getByRole("button", { name: "撤回" }));
    expect(onReview).toHaveBeenCalledWith(
      expect.objectContaining({ id: "case:CASE-1" }),
      "keep_unpaired",
      anomalyItems.map((item) => item.fingerprint),
      ["oa_bank_amount_mismatch", "bank_invoice_amount_mismatch"],
    );
  });

  it("keeps historical paired anomaly chips visible and allows withdrawal before classification", async () => {
    const user = userEvent.setup();
    const onReview = vi.fn();
    const legacyGroup = group("paired");
    legacyGroup.workbenchAnomaly!.reviewClassificationCodes = [];
    renderDrawer("paired", onReview, true, legacyGroup);

    expect(screen.getByText("OA流水金额不一致")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "撤回" }));
    expect(onReview).toHaveBeenCalledWith(
      expect.objectContaining({ id: "case:CASE-1" }),
      "keep_unpaired",
      anomalyItems.map((item) => item.fingerprint),
      [],
    );
  });
});
