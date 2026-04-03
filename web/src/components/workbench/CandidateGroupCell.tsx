import type { WorkbenchRecord, WorkbenchRecordType } from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import type { WorkbenchInlineAction } from "./RowActions";
import WorkbenchRecordCard from "./WorkbenchRecordCard";

type CandidateGroupCellProps = {
  zoneId: "paired" | "open";
  paneId: WorkbenchRecordType;
  records: WorkbenchRecord[];
  scrollPaneId: WorkbenchRecordType;
  scrollTestId: string;
  actionMode?: "default" | "cancel-exception-only";
  highlightedRowId?: string | null;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "open") => WorkbenchRowState;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "open") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  showWorkflowActions: boolean;
};

export default function CandidateGroupCell({
  zoneId,
  paneId,
  records,
  scrollPaneId,
  scrollTestId,
  actionMode = "default",
  highlightedRowId,
  getRowState,
  onSelectRow,
  onOpenDetail,
  onRowAction,
  showWorkflowActions,
}: CandidateGroupCellProps) {
  if (records.length === 0) {
    return (
      <div
        className={`candidate-group-cell candidate-group-cell-${paneId} candidate-group-cell-empty`}
        data-scroll-pane={scrollPaneId}
        data-testid={scrollTestId}
      >
        <div className="candidate-group-empty-copy">当前栏暂无候选</div>
      </div>
    );
  }

  return (
    <div
      className={`candidate-group-cell candidate-group-cell-${paneId}`}
      data-scroll-pane={scrollPaneId}
      data-testid={scrollTestId}
    >
      <div className="candidate-group-stack">
        {records.map((row) => (
          <WorkbenchRecordCard
            actionMode={actionMode}
            highlighted={highlightedRowId === row.id}
            key={row.id}
            onOpenDetail={onOpenDetail}
            onRowAction={onRowAction}
            onSelectRow={onSelectRow}
            paneId={paneId}
            row={row}
            rowState={getRowState(row, zoneId)}
            showWorkflowActions={showWorkflowActions}
            zoneId={zoneId}
          />
        ))}
      </div>
    </div>
  );
}
