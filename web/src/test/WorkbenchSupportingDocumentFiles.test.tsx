import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WorkbenchRecordCard from "../components/workbench/WorkbenchRecordCard";
import type { WorkbenchRecord } from "../features/workbench/types";

const row: WorkbenchRecord = {
  id: "supporting-documents:oa-1:item-1", recordType: "invoice",
  sourceKind: "oa_supporting_document", sourceOaId: "oa-1", sourceExpenseItemIds: ["item-1"],
  label: "补充凭证", status: "资料已补齐", statusCode: "supporting_document", statusTone: "info",
  exceptionHandled: true, displayOnly: true, amount: "", counterparty: "", tableValues: {},
  detailFields: [], actionVariant: "detail-only", availableActions: [],
  supportingDocuments: ["罚款缴费凭证.png", "附加说明.pdf"].map((fileName, i) => ({
    id: String(i), fileName, contentType: i ? "application/pdf" : "image/png", sizeBytes: 10,
    createdAt: "2026-09-11", contentUrl: `/api/workbench/oa-invoice-supplements/documents/${i}/content`,
  })),
};

test("renders all supporting files in one full-width cell and manages the exact item", async () => {
  const onRowAction = vi.fn(); const onSelectRow = vi.fn();
  render(<WorkbenchRecordCard row={row} paneId="invoice" zoneId="unpaired" rowState="idle"
    canOperateData showWorkflowActions onRowAction={onRowAction} onSelectRow={onSelectRow} onOpenDetail={vi.fn()} />);
  expect(screen.getAllByRole("cell")).toHaveLength(1);
  expect(screen.getAllByRole("link")).toHaveLength(2);
  expect(screen.getByRole("link", { name: "罚款缴费凭证.png" })).toHaveAttribute("target", "_blank");
  expect(screen.queryByText("录入发票")).not.toBeInTheDocument();
  expect(screen.queryByText("—")).not.toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole("button", { name: "管理凭证" }));
  expect(onRowAction).toHaveBeenCalledWith(row, "manage-supporting-documents");
  expect(onSelectRow).not.toHaveBeenCalled();
});

test("read-only rendering keeps previews and hides management", () => {
  render(<WorkbenchRecordCard row={row} paneId="invoice" zoneId="paired" rowState="idle"
    canOperateData={false} showWorkflowActions={false} readOnly onRowAction={vi.fn()} onSelectRow={vi.fn()} onOpenDetail={vi.fn()} />);
  expect(screen.getAllByRole("link")).toHaveLength(2);
  expect(screen.queryByRole("button", { name: "管理凭证" })).not.toBeInTheDocument();
});
