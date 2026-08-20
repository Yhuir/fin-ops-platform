import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

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
});
