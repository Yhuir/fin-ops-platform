import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WorkbenchRecordCard from "../components/workbench/WorkbenchRecordCard";
import { getWorkbenchColumns, getWorkbenchPaneGridStyle } from "../features/workbench/tableConfig";
import type { WorkbenchRecord } from "../features/workbench/types";

const row: WorkbenchRecord = {
  id: "applicant-layout", recordType: "oa", label: "支付申请", status: "待处理",
  statusCode: "pending", statusTone: "warn", exceptionHandled: false,
  amount: "8000.00", counterparty: "设备供应商", actionVariant: "detail-only",
  availableActions: ["detail"], detailFields: [],
  tableValues: { applicant: "樊祖芳", projectName: "项目", amount: "8000.00", applicationType: "支付申请", applicationTime: "2026-08-14", workflowStatus: "completed" },
  workbenchAnomalies: [{ code: "oa_bank_equal_invoice_less", label: "票少", displayLabel: "票少", fingerprint: "existing-anomaly", comparisonUnitId: "layout", sourceOaIds: [], sourceExpenseItemIds: [], oaTotal: "8000", bankTotal: "8000", invoiceTotal: "0", amountDelta: "8000", invoiceRowIds: [], attachmentFileCount: 0, displayScope: "row", displayPane: "oa", displayRowId: "applicant-layout" }],
};

function renderRow(record = row, readOnly = false) {
  const onSelectRow = vi.fn();
  const onOpenDetail = vi.fn();
  const layouts = { oa: ["projectName", "applicant", "amount", "counterparty", "reason"] };
  const result = render(<WorkbenchRecordCard paneId="oa" zoneId="unpaired" row={record} rowState="idle"
    columns={getWorkbenchColumns("oa", layouts)} columnGridStyle={getWorkbenchPaneGridStyle("oa", layouts)}
    onSelectRow={onSelectRow} onOpenDetail={onOpenDetail} onRowAction={() => {}} showWorkflowActions canOperateData readOnly={readOnly} />);
  return { ...result, onSelectRow, onOpenDetail };
}

test("OA actions remain in the applicant cell after reorder and never select the row", async () => {
  const user = userEvent.setup({ skipHover: true });
  const { onSelectRow, onOpenDetail } = renderRow();
  const cell = screen.getByText("樊祖芳").closest('[role="cell"]') as HTMLElement;
  expect(within(cell).getByText("支付申请")).toBeInTheDocument();
  expect(within(cell).getByText("2026-08-14")).toBeInTheDocument();
  const detail = within(cell).getByRole("button", { name: "查看OA 樊祖芳 详情" });
  const anomaly = within(cell).getByRole("button", { name: "该OA有 1 项异常，查看详情" });
  expect(detail.closest(".workbench-oa-applicant-actions")).toContainElement(anomaly);
  await user.click(detail);
  expect(onOpenDetail).toHaveBeenCalledWith(row);
  await user.click(anomaly);
  expect(await screen.findByRole("dialog", { name: "该OA异常详情" })).toBeVisible();
  expect(onSelectRow).not.toHaveBeenCalled();
});

test("read-only OA keeps its anomaly but does not acquire a detail action", () => {
  renderRow(row, true);
  expect(screen.queryByRole("button", { name: /查看OA .*详情/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "该OA有 1 项异常，查看详情" })).toBeInTheDocument();
});

test("read-only OA without anomalies has no empty action row", () => {
  const { container } = renderRow({ ...row, workbenchAnomalies: [] }, true);
  expect(container.querySelector(".workbench-oa-applicant-actions")).toBeNull();
});

test("expense item keeps its own anomaly without duplicating parent applicant or detail", () => {
  renderRow({ ...row, displayRole: "expense-claim-item" });
  expect(screen.queryByText("樊祖芳")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /查看OA .*详情/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "该OA有 1 项异常，查看详情" })).toBeInTheDocument();
});
