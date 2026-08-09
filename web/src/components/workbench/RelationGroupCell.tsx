import { memo, type ReactNode } from "react";

import type { WorkbenchRecord, WorkbenchRecordType } from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import type { WorkbenchInlineAction } from "./RowActions";
import WorkbenchRecordCard from "./WorkbenchRecordCard";
import type { WorkbenchColumn } from "../../features/workbench/tableConfig";
import type { WorkbenchLayoutMode } from "../../features/workbench/tableConfig";

type RelationGroupCellProps = {
  zoneId: "paired" | "unpaired";
  paneId: WorkbenchRecordType;
  columns: WorkbenchColumn[];
  columnGridStyle?: {
    gridTemplateColumns: string;
    minWidth: string;
  };
  records: WorkbenchRecord[];
  scrollPaneId: WorkbenchRecordType;
  scrollTestId: string;
  showActionColumn?: boolean;
  highlightedRowId?: string | null;
  searchQuery?: string;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "unpaired") => WorkbenchRowState;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "unpaired") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  showWorkflowActions: boolean;
  canMutateData: boolean;
  readOnly?: boolean;
  leadingControl?: ReactNode;
  layoutMode?: WorkbenchLayoutMode;
};

function RelationGroupCell({
  zoneId,
  paneId,
  columns,
  columnGridStyle,
  records,
  scrollPaneId,
  scrollTestId,
  showActionColumn = false,
  highlightedRowId,
  searchQuery = "",
  getRowState,
  onSelectRow,
  onOpenDetail,
  onRowAction,
  showWorkflowActions,
  canMutateData,
  readOnly = false,
  leadingControl,
  layoutMode = "classic",
}: RelationGroupCellProps) {
  const isSingleRecord = records.length === 1;

  if (records.length === 0) {
    return (
      <div
        className={`candidate-group-cell candidate-group-cell-${paneId} candidate-group-cell-sheet candidate-group-cell-empty candidate-group-cell-empty-sheet`}
        data-scroll-pane={scrollPaneId}
        data-testid={scrollTestId}
      >
        {leadingControl ? <div className="candidate-group-empty-control">{leadingControl}</div> : null}
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
        {records.map((row, index) => (
          <WorkbenchRecordCard
            columnGridStyle={columnGridStyle}
            columns={columns}
            highlighted={highlightedRowId === row.id}
            searchQuery={searchQuery}
            key={row.id}
            onOpenDetail={onOpenDetail}
            onRowAction={onRowAction}
            onSelectRow={onSelectRow}
            paneId={paneId}
            row={row}
            rowState={getRowState(row, zoneId)}
            sheetRowMode={isSingleRecord ? "stretched" : "split"}
            leadingControl={index === 0 ? leadingControl : undefined}
            showActionColumn={showActionColumn}
            showWorkflowActions={showWorkflowActions}
            canMutateData={canMutateData}
            layoutMode={layoutMode}
            readOnly={readOnly}
            zoneId={zoneId}
          />
        ))}
      </div>
    </div>
  );
}

export default memo(RelationGroupCell);
