import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import WorkbenchAnomalyIndicator from "../components/workbench/WorkbenchAnomalyIndicator";
import type { WorkbenchAnomalyItem } from "../features/workbench/types";

const anomaly: WorkbenchAnomalyItem = {
  code: "oa_bank_equal_invoice_less",
  label: "OA 流水一致，票少",
  displayLabel: "OA 流水一致，票少",
  fingerprint: "b".repeat(64),
  comparisonUnitId: "case:CASE-1",
  sourceOaIds: ["oa-1"],
  sourceExpenseItemIds: [],
  oaTotal: "100.00",
  bankTotal: "100.00",
  invoiceTotal: "99.00",
  amountDelta: "1.00",
  invoiceRowIds: ["invoice-1"],
  attachmentFileCount: 0,
  displayScope: "row",
  displayPane: "invoice",
  displayRowId: "invoice-1",
};

function renderIndicator() {
  render(<WorkbenchAnomalyIndicator anomalies={[anomaly]} levelLabel="该发票" />);
  return screen.getByRole("button", { name: "该发票有 1 项异常，查看详情" });
}

describe("WorkbenchAnomalyIndicator", () => {
  it("opens and closes from pointer clicks without a prior hover", async () => {
    const user = userEvent.setup({ skipHover: true });
    const trigger = renderIndicator();

    await user.click(trigger);
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();

    await user.click(trigger);
    await waitFor(() => expect(screen.queryByText("OA 流水一致，票少")).not.toBeInTheDocument());
  });

  it("dismisses a hover popover on the first click and reopens it on the second click", async () => {
    const user = userEvent.setup();
    const trigger = renderIndicator();

    await user.hover(trigger);
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();

    await user.click(trigger);
    await waitFor(() => expect(screen.queryByText("OA 流水一致，票少")).not.toBeInTheDocument());

    fireEvent.mouseEnter(trigger);
    expect(screen.queryByText("OA 流水一致，票少")).not.toBeInTheDocument();

    await user.click(trigger);
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();
  });

  it("resets click dismissal after a genuine pointer leave", async () => {
    const user = userEvent.setup();
    const trigger = renderIndicator();

    await user.hover(trigger);
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();
    await user.click(trigger);
    await waitFor(() => expect(screen.queryByText("OA 流水一致，票少")).not.toBeInTheDocument());

    await user.unhover(trigger);
    await user.hover(trigger);
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();
  });

  it("shows on keyboard focus and closes with Escape", async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.tab();
    expect(await screen.findByText("OA 流水一致，票少")).toBeVisible();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByText("OA 流水一致，票少")).not.toBeInTheDocument());
  });

  it("runs a row-level resolution action once and closes the popover", async () => {
    const user = userEvent.setup();
    const onPress = vi.fn();
    render(
      <WorkbenchAnomalyIndicator
        action={{ label: "选择 OA 明细", onPress }}
        anomalies={[{ ...anomaly, code: "oa_invoice_attachment_unassigned", displayLabel: "发票待归属" }]}
        levelLabel="该发票"
      />,
    );

    await user.hover(screen.getByRole("button", { name: "该发票有 1 项异常，查看详情" }));
    await user.click(await screen.findByRole("button", { name: "选择 OA 明细" }));

    expect(onPress).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole("button", { name: "选择 OA 明细" })).not.toBeInTheDocument());
  });

  it("shows the reviewer account snapshot and a normal business-time timestamp", async () => {
    const user = userEvent.setup({ skipHover: true });
    render(
      <WorkbenchAnomalyIndicator
        anomalies={[{
          ...anomaly,
          reviewDecision: "accept_paired",
          reviewedByAccount: "YNSYLP007",
          reviewedByName: "杨丽萍",
          reviewedAt: "2026-08-25T17:03:47.404624+08:00",
          reviewNote: "金额差异已核对",
        }]}
        confirmation={{ note: "票面金额少 1.00 元，经确认保留关联" }}
        levelLabel="该关联组"
      />,
    );

    await user.click(screen.getByRole("button", { name: "该关联组有 1 项异常，查看详情" }));

    expect(await screen.findByText("已接受该异常风险")).toBeVisible();
    expect(screen.getByText("YNSYLP007（杨丽萍）")).toBeVisible();
    expect(screen.getByText("2026-08-25 17:03:47")).toBeVisible();
    expect(screen.getByText("金额差异已核对")).toBeVisible();
    expect(screen.getByText("确认关联备注")).toBeVisible();
    expect(screen.getByText("票面金额少 1.00 元，经确认保留关联")).toBeVisible();
    expect(screen.queryByText("8")).not.toBeInTheDocument();
    expect(screen.queryByText(/\+08:00/)).not.toBeInTheDocument();
  });
});
