import { memo } from "react";

import type { WorkbenchRecord, WorkbenchRecordType } from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import type { WorkbenchInlineAction } from "./RowActions";
import WorkbenchRecordCard from "./WorkbenchRecordCard";
import type { WorkbenchColumn } from "../../features/workbench/tableConfig";

type CandidateGroupCellProps = {
  zoneId: "paired" | "open";
  paneId: WorkbenchRecordType;
  columns: WorkbenchColumn[];
  columnGridStyle?: {
    gridTemplateColumns: string;
    minWidth: string;
  };
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
  canMutateData: boolean;
};

function CandidateGroupCell({
  zoneId,
  paneId,
  columns,
  columnGridStyle,
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
  canMutateData,
}: CandidateGroupCellProps) {
  const isSingleRecord = records.length === 1;

  if (records.length === 0) {
    return (
      <div
        className={`candidate-group-cell candidate-group-cell-${paneId} candidate-group-cell-sheet candidate-group-cell-empty candidate-group-cell-empty-sheet`}
        data-scroll-pane={scrollPaneId}
        data-testid={scrollTestId}
      >
        <div className="candidate-group-empty-copy">-</div>
      </div>
    );
  }

  return (
    <div
      className={`candidate-group-cell candidate-group-cell-${paneId} candidate-group-cell-sheet ${isSingleRecord ? "candidate-group-cell-sheet-single" : "candidate-group-cell-sheet-multi"}`}
      data-scroll-pane={scrollPaneId}
      data-testid={scrollTestId}
    >
      <div
        className={`candidate-group-stack candidate-group-stack-sheet ${isSingleRecord ? "candidate-group-stack-sheet-single" : "candidate-group-stack-sheet-multi"}`}
      >
        {records.map((row) => (
          <WorkbenchRecordCard
            actionMode={actionMode}
            columnGridStyle={columnGridStyle}
            columns={columns}
            highlighted={highlightedRowId === row.id}
            key={row.id}
            onOpenDetail={onOpenDetail}
            onRowAction={onRowAction}
            onSelectRow={onSelectRow}
            paneId={paneId}
            row={row}
            rowState={getRowState(row, zoneId)}
            sheetRowMode={isSingleRecord ? "stretched" : "split"}
            showWorkflowActions={showWorkflowActions}
            canMutateData={canMutateData}
            zoneId={zoneId}
          />
        ))}
      </div>
    </div>
  );
}

export default memo(CandidateGroupCell);
