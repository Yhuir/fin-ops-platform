import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import WorkbenchRecordCard from "../components/workbench/WorkbenchRecordCard";
import RowActions from "../components/workbench/RowActions";
import type { WorkbenchRecord } from "../features/workbench/types";

const cashActions = ["confirm_cash_pass_through", "confirm_cash_ticket_purchase", "cancel_cash_special"];
const bank: WorkbenchRecord = {
  id: "bank-actions", recordType: "bank", label: "银行流水", amount: "100.00", counterparty: "测试公司",
  status: "已关联", statusCode: "confirmed", statusTone: "success", exceptionHandled: false,
  actionVariant: "detail-only", availableActions: cashActions, detailFields: [],
  tableValues: { counterparty: "测试公司", amount: "100.00", note: "原始备注" },
};

function renderBank(overrides: { canOperateData?: boolean; readOnly?: boolean; showWorkflowActions?: boolean; row?: WorkbenchRecord } = {}) {
  const onAction = vi.fn(), onSelect = vi.fn();
  render(<WorkbenchRecordCard row={bank} paneId="bank" zoneId="paired" rowState="idle" canOperateData showWorkflowActions
    columns={[{ key: "counterparty", label: "对方户名" }, { key: "note", label: "备注" }]}
    onSelectRow={onSelect} onRowAction={onAction} onOpenDetail={vi.fn()} {...overrides} />);
  return { onAction, onSelect };
}

test("ordinary bank rows retain source details without a redundant menu or empty actions", () => {
  renderBank({ row: { ...bank, availableActions: ["detail"] } });
  expect(screen.getByRole("button", { name: /查看银行流水.*详情/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /更多|关联情况|确认为|取消现金处理/ })).not.toBeInTheDocument();
  expect(document.querySelector(".record-card-bank .row-actions")).toBeNull();
});

test("cash text actions stay inside the remark cell and preserve exact row identity without selecting it", async () => {
  const user = userEvent.setup();
  const { onAction, onSelect } = renderBank();
  const cell = screen.getByText("原始备注").closest('[role="cell"]') as HTMLElement;
  for (const [label, action] of [["确认为过账", "confirm-cash-pass-through"], ["确认为买票", "confirm-cash-ticket-purchase"], ["取消现金处理", "cancel-cash-special"]]) {
    await user.click(within(cell).getByRole("button", { name: label }));
    expect(onAction).toHaveBeenLastCalledWith(bank, action);
  }
  expect(onSelect).not.toHaveBeenCalled();
  expect(onAction).toHaveBeenCalledTimes(3);
});

test.each([{ canOperateData: false }, { readOnly: true }, { showWorkflowActions: false }])("cash actions remain unavailable for %j", props => {
  renderBank(props);
  expect(screen.queryByRole("button", { name: /确认为|取消现金处理/ })).not.toBeInTheDocument();
});

test("each special action is displayed only when explicitly available", () => {
  renderBank({ row: { ...bank, availableActions: ["cancel_cash_special"] } });
  expect(screen.getByRole("button", { name: "取消现金处理" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /确认为/ })).not.toBeInTheDocument();
});

test("the table action consumer still opens details and does not expose bank commands on OA", async () => {
  const user = userEvent.setup(), onOpen = vi.fn(), onAction = vi.fn();
  render(<RowActions recordType="oa" canOperateData showWorkflowActions availableActions={cashActions}
    onOpenDetail={onOpen} onAction={onAction} />);
  await user.click(screen.getByRole("button", { name: "详情" }));
  expect(onOpen).toHaveBeenCalledTimes(1);
  expect(onAction).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: /更多|确认为|取消现金/ })).not.toBeInTheDocument();
});
