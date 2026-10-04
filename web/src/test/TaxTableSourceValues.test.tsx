import {render, screen, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";
import TaxTable from "../components/tax/TaxTable";

test("source tax labels remain visible and only complete tax amounts can be selected", async () => {
  const onToggleRow = vi.fn();
  const user = userEvent.setup();
  const base = {invoiceNo: "SOURCE-1", invoiceType: "进项发票", counterparty: "原件供应商", issueDate: "2026-09-29", amount: "—", taxRate: "免税"};
  render(<TaxTable title="原件发票" selectedIds={[]} onToggleRow={onToggleRow} rows={[
    {...base, id: "missing", taxAmount: "*", isSelectable: false},
    {...base, id: "zero", invoiceNo: "SOURCE-2", amount: "0.00", taxAmount: "0.00", taxRate: "0%", isSelectable: true},
  ]} />);
  const missing = screen.getByRole("checkbox", {name: "SOURCE-1 原件供应商"});
  expect(missing).toBeDisabled();
  const sourceRow = screen.getByRole("row", {name: /SOURCE-1/});
  expect(within(sourceRow).getByRole("gridcell", {name: "*", exact: true})).toBeVisible();
  expect(sourceRow).toHaveTextContent("—");
  await user.click(missing);
  expect(onToggleRow).not.toHaveBeenCalled();
  await user.click(screen.getByRole("checkbox", {name: "SOURCE-2 原件供应商"}));
  expect(onToggleRow).toHaveBeenCalledWith("zero");
});
