import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import ImportReviewTable from "../components/imports/ImportReviewTable";
import type { ImportReviewRowsPage } from "../features/imports/types";

function rows(): ImportReviewRowsPage["rows"] {
  return Array.from({ length: 33 }, (_, index) => ({
    id: `row-${index}`, fileId: "file-1", rowNo: index + 1,
    category: index < 4 ? "review" : index < 23 ? "new" : "existing",
    invoiceNo: `2699000000000000${String(index).padStart(4, "0")}`, invoiceDate: "2026-09-16",
    sellerName: "一个很长但必须完整显示的销方公司名称", buyerName: "云南溯源科技有限公司",
    amount: "133.03", taxAmount: "11.97", totalWithTax: "145.00", currentSource: "OA附件解析",
    conflicts: index < 4 ? [{ field: "amount", fileValue: "133.03", currentValue: "145.00" }, { field: "tax_amount", fileValue: "11.97", currentValue: "0.00" }] : [],
  }));
}

test("all 33 rows distinguish 4 issues, 19 new and 10 existing with full values and comparisons", async () => {
  const user = userEvent.setup();
  render(<ImportReviewTable rows={rows()} loading={false} invoiceMode page={1} pageSize={100} total={33} onPageChange={vi.fn()} />);
  const grid = screen.getByRole("grid", { name: "导入文件全部明细" });
  expect(within(grid).getAllByRole("row")).toHaveLength(34);
  expect(grid.querySelectorAll(".import-review-row--review")).toHaveLength(4);
  expect(grid.querySelectorAll(".import-review-row--new")).toHaveLength(19);
  expect(grid.querySelectorAll(".import-review-row--existing")).toHaveLength(10);
  expect(screen.queryByRole("columnheader", { name: "文件", exact: true })).not.toBeInTheDocument();
  const first = within(grid).getAllByRole("row")[1];
  expect(first).toHaveTextContent("26990000000000000000");
  expect(first).toHaveTextContent("133.03税额 11.97合计 145.00");
  await user.click(within(first).getByText("金额、税额不一致"));
  expect(within(first).getByText("文件：133.03")).toBeVisible();
  expect(within(first).getByText("App 当前：145.00")).toBeVisible();
  expect(within(first).getByText("App 来源：OA附件解析")).toBeVisible();
});

test("bank mode uses bank fields, full amount, review state and bounded pagination", async () => {
  const user = userEvent.setup(); const onPageChange = vi.fn();
  render(<ImportReviewTable rows={[{ ...rows()[0], accountNo: "622200000000123456", tradeTime: "2026-09-16 12:34:56", direction: "outflow", amount: "987654321.09", counterpartyName: "银行对方公司", conflicts: [], decisionReason: "关键字段相似，请核对" }]} loading={false} invoiceMode={false} page={1} pageSize={100} total={101} onPageChange={onPageChange} />);
  expect(screen.getByText("987654321.09")).toBeVisible();
  expect(screen.getByText("支出")).toBeVisible();
  expect(screen.queryByText("销方 / 购方")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "下一页" }));
  expect(onPageChange).toHaveBeenCalledWith(2);
});
