import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import {
  AmountCell,
  EmptyValue,
  FinanceDirectionTag,
  FinanceStatusTag,
  FinanceTablePagination,
  TableCellStack,
} from "../components/common/FinanceTable";

describe("FinanceTable shared primitives", () => {
  test("clamps pagination display to valid ranges and disables unavailable navigation", () => {
    const onPageChange = vi.fn();

    render(<FinanceTablePagination page={99} pageSize={25} total={57} onPageChange={onPageChange} />);

    expect(screen.getByText("显示 51-57 / 57")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "3" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: /下一页/ })).toBeDisabled();
  });

  test("emits page changes from pagination controls without mutating totals", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();

    render(<FinanceTablePagination page={2} pageSize={25} total={75} onPageChange={onPageChange} />);

    expect(screen.getByText("显示 26-50 / 75")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /上一页/ }));
    await user.click(screen.getByRole("button", { name: "3" }));

    expect(onPageChange).toHaveBeenNthCalledWith(1, 1);
    expect(onPageChange).toHaveBeenNthCalledWith(2, 3);
  });

  test("keeps shared finance cell primitives semantically stable", () => {
    render(
      <div>
        <TableCellStack primary="云南溯源" secondary="工商银行" meta="2026-03" />
        <AmountCell account="6386" amount="1,234.56" direction={<FinanceDirectionTag direction="expense" />} />
        <FinanceStatusTag tone="warning">刷新中</FinanceStatusTag>
        <EmptyValue />
      </div>,
    );

    expect(screen.getByText("云南溯源")).toHaveClass("finance-cell-stack__primary");
    expect(screen.getByText("工商银行")).toHaveClass("finance-cell-stack__secondary");
    expect(screen.getByText("1,234.56")).toHaveClass("finance-amount-cell__value");
    expect(screen.getByText("支出").closest(".finance-direction-tag")).toHaveAttribute("data-direction", "expense");
    expect(screen.getByText("刷新中").closest(".finance-status-tag")).toHaveAttribute("data-tone", "warning");
    expect(screen.getByText("-")).toHaveClass("finance-empty-value");
  });
});
