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
  canMutateData: boolean;
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
  canMutateData,
}: WorkbenchRecordCardProps) {
  const columns = workbenchColumns[paneId];
  const hasActionColumn = actionMode === "cancel-exception-only" || paneId === "invoice";
  const showInlineDetail = actionMode === "default" && (paneId === "oa" || paneId === "bank");

  return (
    <div
      aria-label={buildRowAriaLabel(row, paneId, columns)}
      className={`record-card workbench-row row-state-${rowState} record-card-${paneId} ${hasActionColumn ? "record-card-has-action" : "record-card-no-action"}${highlighted ? " search-target-highlighted" : ""}`}
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
            <div className="record-card-cell-content">
              {renderCellValue(column, value, row, paneId, showInlineDetail, () => onOpenDetail(row))}
            </div>
          </div>
        );
      })}
      {hasActionColumn ? (
        <div className="record-card-cell record-card-action-cell" role="cell">
          <RowActions
            availableActions={row.availableActions}
            canMutateData={canMutateData}
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
      ) : null}
    </div>
  );
}

function buildRowAriaLabel(row: WorkbenchRecord, paneId: WorkbenchRecordType, columns: WorkbenchColumn[]) {
  const values: string[] = [];
  const pushValue = (value: string | undefined) => {
    if (!value || value === "--" || value === "—" || values.includes(value)) {
      return;
    }
    values.push(value);
  };

  if (paneId === "bank") {
    pushValue(row.tableValues.transactionTime);
  }

  if (paneId === "invoice") {
    pushValue(row.tableValues.sellerTaxId);
    pushValue(row.tableValues.sellerName);
    pushValue(row.tableValues.buyerTaxId);
    pushValue(row.tableValues.buyerName);
    pushValue(row.tableValues.issueDate);
    pushValue(row.tableValues.amount);
    pushValue(row.tableValues.taxRate);
    pushValue(row.tableValues.taxAmount);
    pushValue(row.tableValues.grossAmount);
    pushValue(row.tableValues.invoiceType);
    return values.join(" ");
  }

  for (const column of columns) {
    pushValue(row.tableValues[column.key]);
  }

  if (paneId === "oa") {
    pushValue(row.tableValues.applicationType);
    pushValue(row.tableValues.reconciliationStatus);
  }

  if (paneId === "bank") {
    pushValue(row.tableValues.paymentAccount);
    pushValue(row.tableValues.invoiceRelationStatus);
  }

  return values.join(" ");
}

function renderCellValue(
  column: WorkbenchColumn,
  value: string,
  row: WorkbenchRecord,
  paneId: WorkbenchRecordType,
  showInlineDetail: boolean,
  onOpenDetail: () => void,
) {
  if (column.kind === "status") {
    return <span className="status-tag">{value}</span>;
  }

  if (column.className?.includes("column-datetime-compact")) {
    return renderDateTimeValue(value);
  }

  if (paneId === "oa" && column.key === "applicant") {
    return renderInlineDetailCellValue(value, showInlineDetail, onOpenDetail);
  }

  if (paneId === "oa" && column.key === "projectName") {
    return renderOaProjectValue(
      value,
      row.tableValues.applicationType ?? "",
      row.tableValues.reconciliationStatus ?? "",
    );
  }

  if (paneId === "bank" && column.kind === "money") {
    return renderBankMoneyValue(column.key, value, row.tableValues.direction ?? "", row.tableValues.paymentAccount ?? "");
  }

  if (paneId === "bank" && column.key === "note") {
    return renderInlineDetailCellValue(value, showInlineDetail, onOpenDetail);
  }

  if (paneId === "bank" && column.key === "counterparty") {
    return renderBankCounterpartyValue(
      value,
      row.tableValues.transactionTime ?? "",
      row.tableValues.invoiceRelationStatus ?? "",
    );
  }

  if (paneId === "invoice" && column.key === "sellerName") {
    return renderInvoicePartyValue(value, row.tableValues.sellerTaxId ?? "", row.tableValues.invoiceType ?? "");
  }

  if (paneId === "invoice" && column.key === "buyerName") {
    return renderInvoicePartyValue(value, row.tableValues.buyerTaxId ?? "", "");
  }

  if (paneId === "invoice" && column.key === "amount") {
    return renderInvoiceAmountValue(value, row.tableValues.taxRate ?? "", row.tableValues.taxAmount ?? "");
  }

  return <span className={buildTextValueClassName(column)}>{value}</span>;
}

function renderInlineDetailCellValue(value: string, showInlineDetail: boolean, onOpenDetail: () => void) {
  return (
    <span className="compound-cell-value">
      <span className="compound-cell-primary cell-text-value cell-text-value-full">{value}</span>
      {showInlineDetail ? (
        <span className="inline-cell-action-row">
          <button
            className="row-action-btn row-action-btn-inline"
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenDetail();
            }}
          >
            详情
          </button>
        </span>
      ) : null}
    </span>
  );
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

function renderBankMoneyValue(columnKey: string, value: string, direction: string, paymentAccount: string) {
  const hasValue = value !== "--" && value !== "—" && value !== "";
  const normalizedDirection = resolveDirectionForMoneyCell(columnKey, direction, hasValue);
  const shouldShowDirectionTag = hasValue && normalizedDirection !== null;
  const shouldShowAccount = hasValue && paymentAccount !== "--" && paymentAccount !== "—" && paymentAccount !== "";

  return (
    <span className="money-cell-stack">
      <span className="money-cell-value">
        <span>{hasValue ? value : "--"}</span>
      </span>
      {shouldShowDirectionTag || shouldShowAccount ? (
        <span className="money-cell-meta-row">
          {shouldShowDirectionTag ? <DirectionTag direction={normalizedDirection} /> : null}
          {shouldShowAccount ? (
            <span className="money-cell-account">
              <BankAccountValue value={paymentAccount} variant="tag" />
            </span>
          ) : null}
        </span>
      ) : null}
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

function renderOaProjectValue(projectName: string, applicationType: string, reconciliationStatus: string) {
  const hasApplicationType = applicationType !== "--" && applicationType !== "—" && applicationType !== "";
  const hasReconciliationStatus =
    reconciliationStatus !== "--" && reconciliationStatus !== "—" && reconciliationStatus !== "";

  return (
    <span className="compound-cell-value">
      <span className="compound-cell-primary cell-text-value cell-text-value-full">{projectName}</span>
      {hasApplicationType || hasReconciliationStatus ? (
        <span className="compound-cell-secondary compound-cell-secondary-nowrap">
          {hasApplicationType ? <span className="inline-meta-tag">{applicationType}</span> : null}
          {hasReconciliationStatus ? <span className="status-tag">{reconciliationStatus}</span> : null}
        </span>
      ) : null}
    </span>
  );
}

function renderBankCounterpartyValue(counterparty: string, transactionTime: string, relationStatus: string) {
  const hasTransactionTime = transactionTime !== "--" && transactionTime !== "—" && transactionTime !== "";
  const hasRelationStatus = relationStatus !== "--" && relationStatus !== "—" && relationStatus !== "";

  return (
    <span className="compound-cell-value">
      <span className="compound-cell-primary cell-text-value cell-text-value-full">{counterparty}</span>
      {hasTransactionTime || hasRelationStatus ? (
        <span className="compound-cell-secondary">
          {hasTransactionTime ? renderInlineDateTimeTag(transactionTime) : null}
          {hasRelationStatus ? <span className="status-tag">{relationStatus}</span> : null}
        </span>
      ) : null}
    </span>
  );
}

function renderInlineDateTimeTag(value: string) {
  const [datePart, ...rest] = value.trim().split(/\s+/);
  const timePart = rest.join(" ").trim();

  if (!timePart) {
    return <span className="inline-meta-tag inline-meta-tag-muted">{datePart}</span>;
  }

  return (
    <span className="inline-meta-tag inline-meta-tag-muted inline-meta-tag-datetime">
      <span className="inline-meta-tag-datetime-date">{datePart}</span>
      <span className="inline-meta-tag-datetime-time">{timePart}</span>
    </span>
  );
}

function renderInvoicePartyValue(value: string, taxId: string, invoiceType: string) {
  const flowLabel = resolveInvoiceFlowLabel(invoiceType);

  return (
    <span className="compound-cell-value invoice-party-value">
      <span className="compound-cell-primary invoice-tax-id-value">
        {flowLabel ? (
          <span className={`invoice-flow-tag invoice-flow-tag-${flowLabel === "销" ? "output" : "input"}`}>{flowLabel}</span>
        ) : null}
        <span className="cell-text-value cell-text-value-full">{value}</span>
      </span>
      {taxId !== "--" && taxId !== "—" && taxId !== "" ? (
        <span className="compound-cell-secondary">
          <span className="cell-text-value cell-text-value-full cell-subtext-value">{taxId}</span>
        </span>
      ) : null}
    </span>
  );
}

function renderInvoiceAmountValue(amount: string, taxRate: string, taxAmount: string) {
  const showTaxMeta =
    taxRate !== "--" &&
    taxRate !== "—" &&
    taxRate !== "" &&
    taxAmount !== "--" &&
    taxAmount !== "—" &&
    taxAmount !== "";

  return (
    <span className="compound-cell-value invoice-amount-value">
      <span className="compound-cell-primary cell-text-value cell-text-value-full">{amount}</span>
      {showTaxMeta ? (
        <span className="compound-cell-secondary">
          <span className="cell-text-value cell-text-value-full cell-subtext-value">
            {`${taxRate} (${taxAmount})`}
          </span>
        </span>
      ) : null}
    </span>
  );
}

function resolveInvoiceFlowLabel(invoiceType: string) {
  if (invoiceType.includes("销")) {
    return "销";
  }
  if (invoiceType.includes("进")) {
    return "进";
  }
  return null;
}
