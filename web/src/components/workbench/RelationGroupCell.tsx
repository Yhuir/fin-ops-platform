import BankSplitChips from "../../features/bankSplits/BankSplitChips";
import { Dropdown } from "@heroui/react";
import { resolveWorkbenchBankSelection } from "../../features/workbench/selectionModel";
import { formatMoney } from "../../features/money";
import { memo, type ReactNode } from "react";

import type { WorkbenchRecord, WorkbenchRecordType } from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import type { WorkbenchInlineAction } from "./RowActions";
import WorkbenchRecordCard from "./WorkbenchRecordCard";
import type { WorkbenchColumn } from "../../features/workbench/tableConfig";

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
  highlightedRowId?: string | null;
  searchQuery?: string;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "unpaired") => WorkbenchRowState;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "unpaired", scope?: "unit") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  showWorkflowActions: boolean;
  canOperateData: boolean;
  readOnly?: boolean;
  allowInvoiceEntryInReadOnly?: boolean;
  leadingControl?: ReactNode;
  rowControls?: Map<string, ReactNode>;
  entryControl?: ReactNode;
};

function RelationGroupCell({
  zoneId,
  paneId,
  columns,
  columnGridStyle,
  records,
  scrollPaneId,
  scrollTestId,
  highlightedRowId,
  searchQuery = "",
  getRowState,
  onSelectRow,
  onOpenDetail,
  onRowAction,
  showWorkflowActions,
  canOperateData,
  readOnly = false,
  allowInvoiceEntryInReadOnly = false,
  leadingControl,
  rowControls,
  entryControl,
}: RelationGroupCellProps) {
  const splitGroups = new Map<string, WorkbenchRecord[]>();
  const displayRecords = records.filter(row => {
    if (paneId !== "bank" || !row.isSplit || !row.parentRowId) return true;
    const members = splitGroups.get(row.parentRowId);
    if (members) { members.push(row); return false; }
    splitGroups.set(row.parentRowId, [row]); return true;
  });
  const isSingleRecord = displayRecords.length === 1;

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
      className={`candidate-group-cell candidate-group-cell-${paneId} candidate-group-cell-sheet${entryControl ? " candidate-group-cell-with-entry-control" : ""} ${isSingleRecord ? "candidate-group-cell-sheet-single" : "candidate-group-cell-sheet-multi"}`}
      data-scroll-pane={scrollPaneId}
      data-testid={scrollTestId}
    >
      {entryControl}
      <div
        className={`candidate-group-stack candidate-group-stack-sheet ${isSingleRecord ? "candidate-group-stack-sheet-single" : "candidate-group-stack-sheet-multi"}`}
      >
        {displayRecords.map((row, index) => (
          <WorkbenchRecordCard
            bankPartsContent={row.isSplit && row.parentRowId ? <>
              <BankSplitChips parts={row.bankSplitParts ?? []} />
              {!readOnly && canOperateData && !row.displayOnly ? <span onClick={event => event.stopPropagation()}>
                <Dropdown>
                  <Dropdown.Trigger aria-label="选择流水子项" className="row-actions-compact-trigger">选择子项</Dropdown.Trigger>
                  <Dropdown.Popover placement="bottom end">
                    <Dropdown.Menu aria-label="流水子项" onAction={key => {
                      const [member] = resolveWorkbenchBankSelection(row, String(key));
                      onSelectRow(member, zoneId, "unit");
                    }}>
                      {(row.bankSplitParts ?? []).map(part => <Dropdown.Item key={part.id} id={part.id}
                        isDisabled={part.relation_case_id === undefined || (part.relation_case_id !== null && part.relation_case_id !== row.caseId)}
                        textValue={`${part.category_label} ${formatMoney(part.amount)}`}>
                        {part.category_path.join(" / ")} · {formatMoney(part.amount)}
                        {part.relation_case_id !== undefined && part.relation_case_id !== null && part.relation_case_id !== row.caseId ? " · 已关联" : ""}
                      </Dropdown.Item>)}
                    </Dropdown.Menu>
                  </Dropdown.Popover>
                </Dropdown>
              </span> : null}
            </> : undefined}
            columnGridStyle={columnGridStyle}
            columns={columns}
            highlighted={highlightedRowId === row.id || Boolean(row.parentRowId && splitGroups.get(row.parentRowId)?.some(part => part.id === highlightedRowId))}
            searchQuery={searchQuery}
            key={row.id}
            onOpenDetail={onOpenDetail}
            onRowAction={onRowAction}
            onSelectRow={onSelectRow}
            paneId={paneId}
            row={row}
            rowState={row.isSplit && row.bankSplitParts?.length
              ? row.bankSplitParts.every(part => getRowState({ ...row, id: part.id }, zoneId) === "selected")
                ? "selected"
                : row.bankSplitParts.some(part => getRowState({ ...row, id: part.id }, zoneId) !== "idle") ? "related" : "idle"
              : getRowState(row, zoneId)}
            sheetRowMode={isSingleRecord ? "stretched" : "split"}
            leadingControl={rowControls?.get(row.id) ?? (index === 0 ? leadingControl : undefined)}
            showWorkflowActions={showWorkflowActions}
            canOperateData={canOperateData}
            readOnly={readOnly}
            allowInvoiceEntryInReadOnly={allowInvoiceEntryInReadOnly}
            zoneId={zoneId}
          />
        ))}
      </div>
    </div>
  );
}

export default memo(RelationGroupCell);
