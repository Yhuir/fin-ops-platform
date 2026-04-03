import type { WorkbenchRecord, WorkbenchRecordType } from "../../features/workbench/types";
import { workbenchColumns } from "../../features/workbench/tableConfig";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import RowActions, { type WorkbenchInlineAction } from "./RowActions";

type PaneTableProps = {
  paneId: WorkbenchRecordType;
  title: string;
  rows: WorkbenchRecord[];
  getRowState: (row: WorkbenchRecord) => WorkbenchRowState;
  onSelectRow: (row: WorkbenchRecord) => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
};

export default function PaneTable({
  paneId,
  title,
  rows,
  getRowState,
  onSelectRow,
  onOpenDetail,
  onRowAction,
}: PaneTableProps) {
  const columns = workbenchColumns[paneId];

  return (
    <section className="pane-card" data-testid={`pane-${paneId}`}>
      <div className="pane-header">
        <span>{title}</span>
        <span>{rows.length} 条</span>
      </div>
      <div className="pane-table-wrap">
        <table className={`grid-table grid-table-${paneId}`}>
          <thead>
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  className={`cell-${column.kind ?? "text"}${column.className ? ` ${column.className}` : ""}`}
                >
                  {column.label}
                </th>
              ))}
              <th className="action-column">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr className="workbench-empty-row">
                <td className="workbench-empty-cell" colSpan={columns.length + 1}>
                  当前栏暂无记录
                </td>
              </tr>
            ) : null}
            {rows.map((row) => {
              const rowState = getRowState(row);

              return (
                <tr
                  key={row.id}
                  className={`workbench-row row-state-${rowState}`}
                  data-row-state={rowState}
                  onClick={() => onSelectRow(row)}
                >
                  {columns.map((column) => {
                    const value = row.tableValues[column.key] ?? "--";

                    return (
                      <td
                        key={column.key}
                        className={`cell-${column.kind ?? "text"}${column.className ? ` ${column.className}` : ""}`}
                      >
                        {column.kind === "status" ? <span className="status-tag">{value}</span> : value}
                      </td>
                    );
                  })}
                  <td className="action-cell">
                    <RowActions
                      availableActions={row.availableActions}
                      recordType={row.recordType}
                      showWorkflowActions
                      variant={row.actionVariant}
                      onAction={(action, event) => {
                        event.stopPropagation();
                        onRowAction(row, action);
                      }}
                      onOpenDetail={(event) => {
                        event.stopPropagation();
                        onOpenDetail(row);
                      }}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
