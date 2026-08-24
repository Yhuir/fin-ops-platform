import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import {
  AmountCell,
  EmptyValue,
  FinanceDirectionTag,
  FinanceStatusTag,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTablePagination,
  FinanceTableRow,
  TableCellStack,
} from "../components/common/FinanceTable";

describe("FinanceTable shared primitives", () => {
  test("exposes one contained scroll surface while keeping HeroUI table semantics", () => {
    render(
      <FinanceTable ariaLabel="测试表格" scrollMode="contained">
        <FinanceTableHeader>
          <FinanceTableColumn id="name" isRowHeader>名称</FinanceTableColumn>
        </FinanceTableHeader>
        <FinanceTableBody>
          <FinanceTableRow id="row-1" textValue="测试行">
            <FinanceTableCell columnRole="identity" textValue="测试行">测试行</FinanceTableCell>
          </FinanceTableRow>
        </FinanceTableBody>
      </FinanceTable>,
    );

    const table = screen.getByRole("grid", { name: "测试表格" });
    expect(table.closest(".finance-table")).toHaveClass("finance-table--contained");
    expect(table.closest(".finance-table__scroll")).toBeInTheDocument();
  });

  test("enables native business-text selection only when a table opts in", () => {
    const { rerender } = render(
      <FinanceTable ariaLabel="默认表格">
        <FinanceTableHeader>
          <FinanceTableColumn id="name" isRowHeader>名称</FinanceTableColumn>
        </FinanceTableHeader>
        <FinanceTableBody>
          <FinanceTableRow id="row-1" textValue="默认行">
            <FinanceTableCell columnRole="identity" textValue="默认行">默认行</FinanceTableCell>
          </FinanceTableRow>
        </FinanceTableBody>
      </FinanceTable>,
    );

    expect(screen.getByRole("grid", { name: "默认表格" }).closest(".finance-table"))
      .not.toHaveClass("finance-table--selectable-text");

    rerender(
      <FinanceTable ariaLabel="可选择表格" selectableText>
        <FinanceTableHeader>
          <FinanceTableColumn id="name" isRowHeader>名称</FinanceTableColumn>
        </FinanceTableHeader>
        <FinanceTableBody>
          <FinanceTableRow id="row-1" textValue="可选择行">
            <FinanceTableCell columnRole="identity" textValue="可选择行">可选择行</FinanceTableCell>
          </FinanceTableRow>
        </FinanceTableBody>
      </FinanceTable>,
    );

    expect(screen.getByRole("grid", { name: "可选择表格" }).closest(".finance-table"))
      .toHaveClass("finance-table--selectable-text");
  });

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

  test("keeps pagination DOM bounded for very large exact totals", () => {
    const onPageChange = vi.fn();

    render(<FinanceTablePagination page={25_000} pageSize={20} total={1_000_000} onPageChange={onPageChange} />);

    expect(screen.getByText("显示 499981-500000 / 1000000")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "25000" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "50000" })).toBeInTheDocument();
    expect(screen.getAllByLabelText("省略的页码")).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: /^\d+$/ })).toHaveLength(5);
  });

  test("keeps first and last pages keyboard reachable in a large exact result set", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();

    render(<FinanceTablePagination page={25_000} pageSize={20} total={1_000_000} onPageChange={onPageChange} />);

    expect(screen.getByRole("button", { name: "25000" })).toHaveAttribute("aria-current", "page");

    act(() => screen.getByRole("button", { name: "1" }).focus());
    await user.keyboard("{Enter}");
    act(() => screen.getByRole("button", { name: "50000" }).focus());
    await user.keyboard(" ");

    expect(onPageChange).toHaveBeenNthCalledWith(1, 1);
    expect(onPageChange).toHaveBeenNthCalledWith(2, 50_000);
  });

  test("renders compact pagination without numeric links", () => {
    const onPageChange = vi.fn();

    render(<FinanceTablePagination compact page={2} pageSize={50} total={121} onPageChange={onPageChange} />);

    expect(screen.getByText("显示 51-100 / 121")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "1" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /上一页/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /下一页/ })).toBeEnabled();
  });

  test("disables every pagination action while a list request is active", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();

    render(<FinanceTablePagination isDisabled page={2} pageSize={50} total={121} onPageChange={onPageChange} />);

    const previous = screen.getByRole("button", { name: /上一页/ });
    const current = screen.getByRole("button", { name: "2" });
    const next = screen.getByRole("button", { name: /下一页/ });
    expect(previous).toBeDisabled();
    expect(current).toBeDisabled();
    expect(next).toBeDisabled();
    await user.click(previous);
    await user.click(current);
    await user.click(next);
    expect(onPageChange).not.toHaveBeenCalled();
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
    expect(screen.getByText("1234.56")).toHaveClass("finance-amount-cell__value");
    expect(screen.getByText("支出").closest(".finance-direction-tag")).toHaveAttribute("data-direction", "expense");
    expect(screen.getByText("刷新中").closest(".finance-status-tag")).toHaveAttribute("data-tone", "warning");
    expect(screen.getByText("-")).toHaveClass("finance-empty-value");
  });
});
