import { memo } from "react";

import { getWorkbenchColumns } from "../../features/workbench/tableConfig";
import type { WorkbenchRecord, WorkbenchRecordType } from "../../features/workbench/types";
import type { WorkbenchColumn } from "../../features/workbench/tableConfig";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import BankAccountValue from "../BankAccountValue";
import DirectionTag from "../DirectionTag";
import RowActions, { type WorkbenchInlineAction } from "./RowActions";

const COMPACT_BANK_NAME_BY_PREFIX: Record<string, string> = {
  中国工商银行: "工行",
  工商银行: "工行",
  中国建设银行: "建行",
  建设银行: "建行",
  中国农业银行: "农行",
  农业银行: "农行",
  中国银行: "中行",
  招商银行: "招行",
  交通银行: "交行",
  中国光大银行: "光大",
  光大银行: "光大",
  中国民生银行: "民生",
  民生银行: "民生",
  平安银行: "平安",
};

type WorkbenchRecordCardProps = {
  zoneId: "paired" | "open";
  paneId: WorkbenchRecordType;
  columns?: WorkbenchColumn[];
  columnGridStyle?: {
    gridTemplateColumns: string;
    minWidth: string;
  };
  row: WorkbenchRecord;
  rowState: WorkbenchRowState;
  actionMode?: "default" | "cancel-exception-only";
  highlighted?: boolean;
  sheetRowMode?: "stretched" | "split";
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "open") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  showWorkflowActions: boolean;
  canMutateData: boolean;
};

function WorkbenchRecordCard({
  zoneId,
  paneId,
  columns: columnsProp,
  columnGridStyle,
  row,
  rowState,
  actionMode = "default",
  highlighted = false,
  sheetRowMode = "split",
  onSelectRow,
  onOpenDetail,
  onRowAction,
  showWorkflowActions,
  canMutateData,
}: WorkbenchRecordCardProps) {
  const columns = columnsProp ?? getWorkbenchColumns(paneId);
  const hasActionColumn = actionMode === "cancel-exception-only" || paneId === "invoice";
  const showInlineDetail = actionMode === "default" && (paneId === "oa" || paneId === "bank");
  const sheetStateClass =
    rowState === "selected"
      ? " record-card-sheet-selected"
      : rowState === "related"
        ? " record-card-sheet-related"
        : "";
  const sheetHighlightClass = highlighted ? " record-card-sheet-highlighted" : "";

  return (
    <div
      aria-label={buildRowAriaLabel(row, paneId, columns)}
      className={`record-card record-card-sheet-row record-card-sheet-row-${sheetRowMode}${sheetStateClass}${sheetHighlightClass} workbench-row row-state-${rowState} record-card-${paneId} ${hasActionColumn ? "record-card-has-action" : "record-card-no-action"}${highlighted ? " search-target-highlighted" : ""}`}
      data-row-id={row.id}
      data-row-state={rowState}
      data-search-highlighted={highlighted ? "true" : "false"}
      role="row"
      style={columnGridStyle}
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
        <div className="record-card-cell record-card-action-cell record-card-action-cell-sheet" role="cell">
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

export default memo(WorkbenchRecordCard, (previousProps, nextProps) => (
  previousProps.zoneId === nextProps.zoneId
  && previousProps.paneId === nextProps.paneId
  && previousProps.columns === nextProps.columns
  && previousProps.columnGridStyle === nextProps.columnGridStyle
  && previousProps.row === nextProps.row
  && previousProps.rowState === nextProps.rowState
  && previousProps.actionMode === nextProps.actionMode
  && previousProps.highlighted === nextProps.highlighted
  && previousProps.sheetRowMode === nextProps.sheetRowMode
  && previousProps.showWorkflowActions === nextProps.showWorkflowActions
  && previousProps.canMutateData === nextProps.canMutateData
  && previousProps.onSelectRow === nextProps.onSelectRow
  && previousProps.onOpenDetail === nextProps.onOpenDetail
  && previousProps.onRowAction === nextProps.onRowAction
));

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
    pushValue(row.tableValues.invoiceCode);
    pushValue(row.tableValues.invoiceNo);
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
    pushValue(row.tableValues.applicationTime);
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
    return renderOaApplicantValue(value, row.tableValues.applicationTime ?? "", showInlineDetail, onOpenDetail);
  }

  if (paneId === "oa" && column.key === "projectName") {
    return renderOaProjectValue(
      value,
      row.tableValues.applicationType ?? "",
      row.tableValues.reconciliationStatus ?? "",
      row.tags ?? [],
    );
  }

  if (paneId === "bank" && column.kind === "money") {
    return renderBankMoneyValue(column.key, value, row.tableValues.direction ?? "", row.tableValues.paymentAccount ?? "");
  }

  if (paneId === "bank" && column.key === "note") {
    return renderBankNoteValue(value, row.tableValues.invoiceRelationStatus ?? "", showInlineDetail, onOpenDetail);
  }

  if (paneId === "bank" && column.key === "counterparty") {
    return renderBankCounterpartyValue(
      value,
      row.tableValues.transactionTime ?? "",
      row.tableValues.invoiceRelationStatus ?? "",
      false,
      onOpenDetail,
    );
  }

  if (paneId === "invoice" && column.key === "sellerName") {
    return renderInvoicePartyValue(value, row.tableValues.sellerTaxId ?? "", row.tableValues.invoiceType ?? "");
  }

  if (paneId === "invoice" && column.key === "buyerName") {
    return renderInvoicePartyValue(value, row.tableValues.buyerTaxId ?? "", "");
  }

  if (paneId === "invoice" && column.key === "issueDate") {
    return renderInvoiceIdentityValue(row.tableValues.invoiceCode ?? "", row.tableValues.invoiceNo ?? "", value);
  }

  if (paneId === "invoice" && column.key === "amount") {
    return renderInvoiceAmountValue(value, row.tableValues.taxRate ?? "", row.tableValues.taxAmount ?? "");
  }

  return <span className={buildTextValueClassName(column)}>{value}</span>;
}

function renderOaApplicantValue(
  value: string,
  applicationTime: string,
  showInlineDetail: boolean,
  onOpenDetail: () => void,
) {
  const hasApplicationTime = applicationTime !== "--" && applicationTime !== "—" && applicationTime !== "";

  return (
    <span className="compound-cell-value">
      <span className="compound-cell-primary cell-text-value cell-text-value-full">{value}</span>
      {hasApplicationTime ? (
        <span className="compound-cell-secondary">
          {renderInlineDateTimeTag(applicationTime)}
        </span>
      ) : null}
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

function renderBankNoteValue(value: string, relationStatus: string, showInlineDetail: boolean, onOpenDetail: () => void) {
  const internalTransferRemark = parseInternalTransferRemark(value, relationStatus);

  return (
    <span className="compound-cell-value">
      {internalTransferRemark ? (
        <>
          <span className="compound-cell-primary">
            <span className="inline-meta-tag">{internalTransferRemark.accountLabel}</span>
          </span>
          {internalTransferRemark.note ? (
            <span className="compound-cell-secondary">
              <span className="cell-text-value cell-text-value-full">{internalTransferRemark.note}</span>
            </span>
          ) : null}
        </>
      ) : (
        <span className="compound-cell-primary cell-text-value cell-text-value-full">{value}</span>
      )}
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

function parseInternalTransferRemark(value: string, relationStatus: string) {
  if (relationStatus !== "已匹配：内部往来款") {
    return null;
  }

  const normalizedValue = value.trim();
  if (!normalizedValue || normalizedValue === "--" || normalizedValue === "—") {
    return null;
  }

  const segments = normalizedValue
    .split(/[；;]\s*/)
    .map((segment) => segment.trim())
    .filter(Boolean);
  const accountSegment = segments.find((segment) => /^(支付账户|收款账户)：/.test(segment));

  if (!accountSegment) {
    return null;
  }

  const note = segments.filter((segment) => segment !== accountSegment).join("；");
  return {
    accountLabel: accountSegment,
    note,
  };
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
              <BankAccountValue value={compactBankAccountLabel(paymentAccount)} variant="tag" />
            </span>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}

function compactBankAccountLabel(value: string) {
  const normalizedValue = value.replace(/\s+/g, " ").trim();
  for (const [bankName, shortName] of Object.entries(COMPACT_BANK_NAME_BY_PREFIX)) {
    if (normalizedValue === bankName) {
      return shortName;
    }
    if (normalizedValue.startsWith(`${bankName} `)) {
      return `${shortName}${normalizedValue.slice(bankName.length)}`;
    }
  }
  return value;
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

function renderOaProjectValue(
  projectName: string,
  applicationType: string,
  reconciliationStatus: string,
  tags: string[] = [],
) {
  const hasApplicationType = applicationType !== "--" && applicationType !== "—" && applicationType !== "";
  const hasReconciliationStatus =
    reconciliationStatus !== "--" && reconciliationStatus !== "—" && reconciliationStatus !== "";
  const visibleTags = tags.map((tag) => tag.trim()).filter(Boolean);

  return (
    <span className="compound-cell-value">
      <span className="compound-cell-primary cell-text-value cell-text-value-full">{projectName}</span>
      {hasApplicationType || hasReconciliationStatus || visibleTags.length > 0 ? (
        <span className="compound-cell-secondary compound-cell-secondary-nowrap">
          {hasApplicationType ? <span className="inline-meta-tag">{applicationType}</span> : null}
          {hasReconciliationStatus ? <span className="status-tag">{reconciliationStatus}</span> : null}
          {visibleTags.map((tag) => (
            <span key={tag} className="inline-meta-tag">
              {tag}
            </span>
          ))}
        </span>
      ) : null}
    </span>
  );
}

function renderBankCounterpartyValue(
  counterparty: string,
  transactionTime: string,
  relationStatus: string,
  showInlineDetail: boolean,
  onOpenDetail: () => void,
) {
  const hasTransactionTime = transactionTime !== "--" && transactionTime !== "—" && transactionTime !== "";
  const hasRelationStatus = relationStatus !== "--" && relationStatus !== "—" && relationStatus !== "";
  const relationTag = hasRelationStatus ? renderBankRelationStatusTag(relationStatus) : null;

  return (
    <span className="compound-cell-value">
      <span className="compound-cell-primary cell-text-value cell-text-value-full">{counterparty}</span>
      {hasTransactionTime || hasRelationStatus ? (
        <span className="compound-cell-secondary compound-cell-secondary-nowrap">
          {hasTransactionTime ? renderInlineDateTimeTag(transactionTime) : null}
          {relationTag}
        </span>
      ) : null}
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

function renderBankRelationStatusTag(relationStatus: string) {
  if (relationStatus === "已匹配：工资") {
    return (
      <span className="status-tag status-tag-split">
        <span className="status-tag-line">已匹配：</span>
        <span className="status-tag-line">工资</span>
      </span>
    );
  }

  if (relationStatus === "已匹配：内部往来款") {
    return (
      <span className="status-tag status-tag-split">
        <span className="status-tag-line">已匹配：</span>
        <span className="status-tag-line">内部往来款</span>
      </span>
    );
  }

  return <span className="status-tag">{relationStatus}</span>;
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

function renderInvoiceIdentityValue(invoiceCode: string, invoiceNo: string, issueDate: string) {
  const normalizedCode = normalizeDisplayText(invoiceCode);
  const normalizedNo = normalizeDisplayText(invoiceNo);
  const hasIssueDate = issueDate !== "--" && issueDate !== "—" && issueDate !== "";

  return (
    <span className="compound-cell-value invoice-identity-value">
      <span className="compound-cell-primary cell-text-value cell-text-value-full invoice-identity-code">
        {`${normalizedCode} /`}
      </span>
      <span className="compound-cell-secondary">
        <span className="cell-text-value cell-text-value-full invoice-identity-no">{normalizedNo}</span>
      </span>
      {hasIssueDate ? (
        <span className="compound-cell-tertiary">
          {renderInlineInvoiceDateTag(issueDate)}
        </span>
      ) : null}
    </span>
  );
}

function normalizeDisplayText(value: string) {
  return value && value !== "—" ? value : "--";
}

function renderInlineInvoiceDateTag(value: string) {
  const [datePart, ...rest] = value.trim().split(/\s+/);
  const timePart = rest.join(" ").trim();

  if (!timePart) {
    return <span className="inline-meta-tag inline-meta-tag-muted invoice-issue-date-tag">{datePart}</span>;
  }

  return (
    <span className="inline-meta-tag inline-meta-tag-muted inline-meta-tag-datetime invoice-issue-date-tag">
      <span className="inline-meta-tag-datetime-date">{datePart}</span>
      <span className="inline-meta-tag-datetime-time">{timePart}</span>
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
