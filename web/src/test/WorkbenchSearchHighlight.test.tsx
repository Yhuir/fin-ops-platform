import { render } from "@testing-library/react";
import WorkbenchRecordCard from "../components/workbench/WorkbenchRecordCard";
import type { WorkbenchRecord } from "../features/workbench/types";

const bank: WorkbenchRecord = {
  id: "search-bank", recordType: "bank", label: "银行流水", amount: "1006868.55", counterparty: "刘树刚",
  status: "待处理", statusCode: "pending", statusTone: "warning", exceptionHandled: false,
  actionVariant: "detail-only", availableActions: [], detailFields: [],
  tableValues: { counterparty: "刘树刚", amount: "1006868.55", note: "账号0093；原始标点%_" },
};

test.each([
  ["6868", ["6868"]], ["￥6,868.55", ["6868.55"]], [".55", [".55"]],
  ["刘树刚 6868", ["刘树刚", "6868"]], ["0093", ["0093"]], ["%_", ["%_"]],
])("highlights the same literal and amount fragments used by search: %s", (query, expected) => {
  const { container } = render(<WorkbenchRecordCard row={bank} paneId="bank" zoneId="unpaired" rowState="idle"
    searchQuery={query} canOperateData={false} showWorkflowActions={false}
    onSelectRow={vi.fn()} onRowAction={vi.fn()} onOpenDetail={vi.fn()} />);
  expect([...container.querySelectorAll("mark")].map(node => node.textContent)).toEqual(expected);
  expect(container.textContent).toContain("1006868.55");
  expect(container.textContent).toContain("账号0093");
});
