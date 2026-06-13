import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import useWorkbenchSelection from "../hooks/useWorkbenchSelection";
import type { WorkbenchRecord } from "../features/workbench/types";

const pairedRow: WorkbenchRecord = {
  id: "paired-row-1",
  caseId: "case:paired-row-1",
  recordType: "bank",
  label: "银行流水",
  status: "已关联",
  statusCode: "paired",
  statusTone: "success",
  exceptionHandled: false,
  amount: "100.00",
  counterparty: "测试供应商",
  tableValues: {},
  detailFields: [],
  actionVariant: "detail-only",
  availableActions: ["detail"],
};

function SelectionHarness() {
  const selection = useWorkbenchSelection();
  return (
    <div>
      <div data-testid="paired-state">{selection.getRowState(pairedRow, "paired")}</div>
      <div data-testid="paired-selected-count">{selection.selectedPairedRows.length}</div>
      <button type="button" onClick={() => selection.openDetail(pairedRow)}>
        打开详情
      </button>
      <button type="button" onClick={() => selection.togglePairedRowSelection(pairedRow)}>
        切换选中
      </button>
    </div>
  );
}

describe("useWorkbenchSelection", () => {
  test("detail focus does not masquerade as explicit paired row selection", async () => {
    const user = userEvent.setup();
    render(<SelectionHarness />);

    expect(screen.getByTestId("paired-state")).toHaveTextContent("idle");
    expect(screen.getByTestId("paired-selected-count")).toHaveTextContent("0");

    await user.click(screen.getByRole("button", { name: "打开详情" }));

    expect(screen.getByTestId("paired-selected-count")).toHaveTextContent("0");
    expect(screen.getByTestId("paired-state")).not.toHaveTextContent("selected");

    await user.click(screen.getByRole("button", { name: "切换选中" }));

    expect(screen.getByTestId("paired-selected-count")).toHaveTextContent("1");
    expect(screen.getByTestId("paired-state")).toHaveTextContent("selected");
  });
});
