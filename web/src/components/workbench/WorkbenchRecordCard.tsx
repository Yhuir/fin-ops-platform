import { workbenchColumns } from "../../features/workbench/tableConfig";
import type { WorkbenchRecord, WorkbenchRecordType } from "../../features/workbench/types";
import type { WorkbenchColumn } from "../../features/workbench/tableConfig";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import BankAccountValue from "../BankAccountValue";
import DirectionTag from "../DirectionTag";
import RowActions, { type WorkbenchInlineAction } from "./RowActions";

type WorkbenchRecordCardProps = {
  zoneId: "paired" | "open";
  paneId: WorkbenchRecordType;
  row: WorkbenchRecord;
  rowState: WorkbenchRowState;
  actionMode?: "default" | "cancel-exception-only";
  highlighted?: boolean;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "open") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  showWorkflowActions: boolean;
};

export default function WorkbenchRecordCard({
  zoneId,
  paneId,
  row,
  rowState,
  actionMode = "default",
  highlighted = false,
  onSelectRow,
  onOpenDetail,
  onRowAction,
  showWorkflowActions,
}: WorkbenchRecordCardProps) {
  const columns = workbenchColumns[paneId];

  return (
    <div
      aria-label={columns.map((column) => row.tableValues[column.key] ?? "--").join(" ")}
      className={`record-card workbench-row row-state-${rowState} record-card-${paneId}${highlighted ? " search-target-highlighted" : ""}`}
      data-row-id={row.id}
      data-row-state={rowState}
      data-search-highlighted={highlighted ? "true" : "false"}
      role="row"
      onClick={() => onSelectRow(row, zoneId)}
    >
      {columns.map((column) => {
        const value = row.tableValues[column.key] ?? "--";
        return (
          <div
            key={column.key}
            className={`record-card-cell cell-${column.kind ?? "text"}${column.className ? ` ${column.className}` : ""}`}
            role="cell"
          >
            {renderCellValue(column, value, row, paneId)}
          </div>
        );
      })}
      <div className="record-card-cell record-card-action-cell" role="cell">
        <RowActions
          availableActions={row.availableActions}
          mode={actionMode}
          recordType={row.recordType}
          showWorkflowActions={showWorkflowActions}
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
      </div>
    </div>
  );
}

function renderCellValue(
  column: WorkbenchColumn,
  value: string,
  row: WorkbenchRecord,
  paneId: WorkbenchRecordType,
) {
  if (column.kind === "status") {
    return <span className="status-tag">{value}</span>;
  }

  if (column.className?.includes("column-datetime-compact")) {
    return renderDateTimeValue(value);
  }

  if (paneId === "bank" && column.key === "paymentAccount") {
    return <BankAccountValue value={value} />;
  }

  if (paneId === "bank" && column.kind === "money") {
    return renderBankMoneyValue(column.key, value, row.tableValues.direction ?? "");
  }

  return <span className={buildTextValueClassName(column)}>{value}</span>;
}

function buildTextValueClassName(column: WorkbenchColumn) {
  return ["cell-text-value", "cell-text-value-full"].join(" ");
}

function renderDateTimeValue(value: string) {
  if (value === "--" || value === "—") {
    return value;
  }

  const [datePart, ...rest] = value.trim().split(/\s+/);
  const timePart = rest.join(" ").trim();

  if (!timePart) {
    return <span className="datetime-cell-value">{datePart}</span>;
  }

  return (
    <span className="datetime-cell-value">
      <span className="datetime-line">{datePart}</span>
      <span className="datetime-line datetime-line-secondary">{timePart}</span>
    </span>
  );
}

function renderBankMoneyValue(columnKey: string, value: string, direction: string) {
  const hasValue = value !== "--" && value !== "—" && value !== "";
  const normalizedDirection = resolveDirectionForMoneyCell(columnKey, direction, hasValue);
  const shouldShowDirectionTag = hasValue && normalizedDirection !== null;

  return (
    <span className="money-cell-value">
      <span>{hasValue ? value : "--"}</span>
      {shouldShowDirectionTag ? <DirectionTag direction={normalizedDirection} /> : null}
    </span>
  );
}

function resolveDirectionForMoneyCell(columnKey: string, direction: string, hasValue: boolean) {
  if (!hasValue) {
    return null;
  }
  if (direction === "支出" || direction === "收入") {
    return direction;
  }
  if (columnKey === "debitAmount") {
    return "支出";
  }
  if (columnKey === "creditAmount") {
    return "收入";
  }
  return null;
}
