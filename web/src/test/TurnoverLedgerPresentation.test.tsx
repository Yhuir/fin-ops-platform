import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";
import TurnoverFlowLabel from "../components/turnoverLedger/TurnoverFlowLabel";
import TurnoverLedgerSummary from "../components/turnoverLedger/TurnoverLedgerSummary";
import type { TurnoverLedgerGroupedResponse } from "../features/turnoverLedger/types";

describe("turnover presentation", () => {
  test.each([
    ["pending_collection", "待收款", "accent"],
    ["pending_repayment", "待还款", "warning"],
    ["collected", "已收款", "success"],
    ["repaid", "已还款", "success"],
    [null, "未设置", "default"],
    ["invalid_action", "标记无效", "default"],
  ])("shows the actual %s action without inferring settlement", (type, label, color) => {
    const { container } = render(<TurnoverFlowLabel row={{ categoryLabelPath: ["外部往来款付款", "保证金", "业务往来"], turnoverActionType: type, turnoverActionLabel: label! }} />);
    expect(screen.getByText("外部往来款付款 / 保证金 / 业务往来")).toBeVisible();
    expect(screen.getByText(label!)).toBeVisible();
    expect(container.querySelector(".turnover-flow-chip")).toHaveClass(`chip--${color}`);
    expect(container).not.toHaveTextContent("往来标记：");
  });

  const ledger: TurnoverLedgerGroupedResponse = {
    summary: { pendingRepaymentAmount: "0.00", pendingCollectionAmount: "100.00", repaidAmount: "0.00", collectedAmount: "20.00", closedAmount: "0.00", suggestedCount: 0, conflictCount: 0, rowCount: 1 },
    familySummaries: [
      { family: "personal", label: "个人往来", pendingRepaymentAmount: "0.00", pendingCollectionAmount: "100.00", repaidAmount: "0.00", collectedAmount: "20.00", pendingAmount: "100.00", closedAmount: "0.00", rowCount: 1 },
      { family: "business", label: "业务往来", pendingRepaymentAmount: "0.00", pendingCollectionAmount: "200.00", repaidAmount: "0.00", collectedAmount: "30.00", pendingAmount: "200.00", closedAmount: "0.00", rowCount: 1 },
    ], groups: [], pagination: { page: 1, pageSize: 20, total: 1 },
  };

  test("explains all-family scope while retaining current-family totals and keyboard dismissal", async () => {
    const user = userEvent.setup();
    render(<TurnoverLedgerSummary ledger={ledger} family="personal" />);
    expect(screen.getByTestId("turnover-summary-pending-collection")).toHaveTextContent("100.00");
    const trigger = screen.getByRole("button", { name: "查看分类明细" });
    await user.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "往来款分类明细" });
    expect(within(dialog).getByText("当前搜索及结算条件下的全部分类")).toBeVisible();
    expect(within(dialog).getByText("200.00")).toBeVisible();
    expect(within(dialog).getByText("当前").closest("tr")).toHaveTextContent("个人往来");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  test("does not present unavailable statistics as zero or keep an old breakdown", async () => {
    const user = userEvent.setup();
    const view = render(<TurnoverLedgerSummary ledger={ledger} family="all" />);
    await user.click(screen.getByRole("button", { name: "查看分类明细" }));
    view.rerender(<TurnoverLedgerSummary ledger={null} family="all" />);
    expect(screen.getByRole("button", { name: "查看分类明细" })).toBeDisabled();
    expect(screen.getByTestId("turnover-summary-collected")).toHaveTextContent("—");
    expect(screen.queryByText("200.00")).not.toBeInTheDocument();
  });

  test("states when the available response has no family statistics", async () => {
    const user = userEvent.setup();
    render(<TurnoverLedgerSummary ledger={{ ...ledger, familySummaries: [] }} family="all" />);
    await user.click(screen.getByRole("button", { name: "查看分类明细" }));
    expect(await screen.findByText("暂无分类统计")).toBeVisible();
  });
});
