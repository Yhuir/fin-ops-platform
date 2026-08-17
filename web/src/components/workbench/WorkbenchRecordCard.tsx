import { Info } from "lucide-react";
import { memo, useState, type FocusEvent, type MouseEvent, type ReactNode, type TouchEvent } from "react";
import { Chip } from "@heroui/react";

import { getWorkbenchColumns } from "../../features/workbench/tableConfig";
import { formatMoney } from "../../features/money";
import {
  compactWorkbenchBankAccountLabel,
  workbenchInvoiceFlowLabel,
  workbenchInvoiceSourceLabel,
} from "../../features/workbench/groupDisplayModel";
import {
  formatWorkbenchAmountCents,
  parseWorkbenchAmountCents,
} from "../../features/workbench/selectionModel";
import type { WorkbenchRecord, WorkbenchRecordType, WorkbenchSourceKind } from "../../features/workbench/types";
import type { WorkbenchColumn } from "../../features/workbench/tableConfig";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import { splitBankAccountLabel } from "../BankAccountValue";
import RowActions, { type WorkbenchInlineAction } from "./RowActions";
import OaWorkflowStatusChip from "../common/OaWorkflowStatusChip";
import { FinanceStatusTag } from "../common/FinanceTable";

type WorkbenchRecordCardProps = {
  zoneId: "paired" | "unpaired";
  paneId: WorkbenchRecordType;
  columns?: WorkbenchColumn[];
  columnGridStyle?: {
    gridTemplateColumns: string;
    minWidth: string;
  };
  row: WorkbenchRecord;
  rowState: WorkbenchRowState;
  highlighted?: boolean;
  searchQuery?: string;
  sheetRowMode?: "stretched" | "split";
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "unpaired") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  showWorkflowActions: boolean;
  canMutateData: boolean;
  readOnly?: boolean;
  leadingControl?: ReactNode;
};

function WorkbenchRecordCard({
  zoneId,
  paneId,
  columns: columnsProp,
  columnGridStyle,
  row,
  rowState,
  highlighted = false,
  searchQuery = "",
  sheetRowMode = "split",
  onSelectRow,
  onOpenDetail,
  onRowAction,
  showWorkflowActions,
  canMutateData,
  readOnly = false,
  leadingControl,
}: WorkbenchRecordCardProps) {
  const columns = columnsProp ?? getWorkbenchColumns(paneId);
  const isSummaryRow = row.sourceKind === "etc_invoice_summary" || row.sourceKind === "bank_flow_rule_batch_summary";
  const showInlineDetail = !row.displayOnly && !isSummaryRow && !readOnly && (paneId === "oa" || paneId === "bank" || paneId === "invoice");
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
      className={`record-card record-card-sheet-row record-card-sheet-row-${sheetRowMode}${sheetStateClass}${sheetHighlightClass} workbench-row row-state-${rowState} record-card-${paneId}${highlighted ? " search-target-highlighted" : ""}${row.displayRole ? ` record-card-${row.displayRole}` : ""}`}
      data-row-id={row.id}
      data-row-state={rowState}
      data-search-highlighted={highlighted ? "true" : "false"}
      role="row"
      style={columnGridStyle}
      onClick={readOnly || row.displayOnly ? undefined : () => onSelectRow(row, zoneId)}
    >
      {columns.map((column, columnIndex) => {
        const value = row.tableValues[column.key] ?? "--";
        const showLeadingControl = columnIndex === 0 && leadingControl;
        return (
          <div
            key={column.key}
            className={`record-card-cell cell-${column.kind ?? "text"}${column.className ? ` ${column.className}` : ""}`}
            role="cell"
          >
            <div className={`record-card-cell-content${showLeadingControl ? " record-card-cell-content-with-inline-control" : ""}`}>
              {showLeadingControl ? <span className="record-card-inline-prefix-control">{leadingControl}</span> : null}
              {renderCellValue(column, value, row, paneId, zoneId, showInlineDetail, () => onOpenDetail(row), searchQuery)}
            </div>
          </div>
        );
      })}
      {paneId === "bank" && !readOnly ? (
        <div className="record-card-compact-actions">
          <RowActions
            compact
            availableActions={row.availableActions}
            canMutateData={canMutateData}
            recordType={row.recordType}
            showDetailAction={!isSummaryRow && !showInlineDetail}
            showWorkflowActions={showWorkflowActions}
            onAction={(action, event) => {
              event?.stopPropagation();
              onRowAction(row, action);
            }}
            onOpenDetail={(event) => {
              event?.stopPropagation();
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
  && previousProps.highlighted === nextProps.highlighted
  && previousProps.searchQuery === nextProps.searchQuery
  && previousProps.sheetRowMode === nextProps.sheetRowMode
  && previousProps.showWorkflowActions === nextProps.showWorkflowActions
  && previousProps.canMutateData === nextProps.canMutateData
  && previousProps.readOnly === nextProps.readOnly
  && previousProps.leadingControl === nextProps.leadingControl
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
    pushValue(row.categoryLabel);
  }

  return values.join(" ");
}

function renderCellValue(
  column: WorkbenchColumn,
  value: string,
  row: WorkbenchRecord,
  paneId: WorkbenchRecordType,
  zoneId: "paired" | "unpaired",
  showInlineDetail: boolean,
  onOpenDetail: () => void,
  searchQuery = "",
) {
  if (column.kind === "status") {
    return <span className="status-tag">{highlightSearchText(value, searchQuery)}</span>;
  }

  if (column.className?.includes("column-datetime-compact")) {
    return renderDateTimeValue(value, searchQuery);
  }

  if (paneId === "oa" && column.key === "applicant") {
    if (row.displayRole === "expense-claim-item") {
      return null;
    }
    return renderOaApplicantValue(
      value,
      row.tableValues.applicationTime ?? "",
      row.tableValues.applicationType ?? "",
      row.tableValues.workflowStatus ?? "completed",
      showInlineDetail,
      onOpenDetail,
      searchQuery,
    );
  }

  if (paneId === "oa" && column.key === "projectName") {
    return renderOaProjectValue(value, row, searchQuery);
  }

  if (paneId === "oa" && column.kind === "money") {
    if (row.displayRole === "expense-claim-summary") {
      return null;
    }
    return renderOaMoneyValue(value, searchQuery);
  }

  if (paneId === "oa" && row.displayRole === "expense-claim-item" && column.key !== "reason") {
    return null;
  }

  if (paneId === "bank" && column.kind === "money") {
    return renderBankMoneyValue(
      column.key,
      value,
      row.tableValues.direction ?? "",
      row.tableValues.paymentAccount ?? "",
      row,
      zoneId,
      searchQuery,
    );
  }

  if (paneId === "bank" && column.key === "note") {
    return renderBankNoteValue(
      value,
      row.tableValues.invoiceRelationStatus ?? "",
      false,
      onOpenDetail,
      row.bankTextFields,
      searchQuery,
    );
  }

  if (paneId === "bank" && column.key === "counterparty") {
    return renderBankCounterpartyValue(
      value,
      row.tableValues.transactionTime ?? "",
      showInlineDetail,
      onOpenDetail,
      searchQuery,
    );
  }

  if (paneId === "invoice" && column.key === "sellerName") {
    return renderInvoicePartyValue(
      value,
      row.tableValues.sellerTaxId ?? "",
      row.tableValues.invoiceType ?? "",
      row.sourceKind,
      row.oaInvoiceAnomaly,
      row.externalUrl,
      searchQuery,
    );
  }

  if (paneId === "invoice" && column.key === "buyerName") {
    return renderInvoicePartyValue(value, row.tableValues.buyerTaxId ?? "", "", undefined, undefined, undefined, searchQuery);
  }

  if (paneId === "invoice" && column.key === "issueDate") {
    return renderInvoiceIdentityValue(row.tableValues.invoiceNo ?? "", value, showInlineDetail, onOpenDetail, searchQuery);
  }

  if (paneId === "invoice" && column.key === "grossAmount") {
    return renderInvoiceAmountValue(
      value,
      row.tableValues.amount ?? "",
      row.tableValues.taxRate ?? "",
      row.tableValues.taxAmount ?? "",
      searchQuery,
    );
  }

  return <span className={buildTextValueClassName(column)}>{highlightSearchText(value, searchQuery)}</span>;
}

function renderOaApplicantValue(
  value: string,
  applicationTime: string,
  applicationType: string,
  workflowStatus: string,
  showInlineDetail: boolean,
  onOpenDetail: () => void,
  searchQuery: string,
) {
  const hasApplicationTime = applicationTime !== "--" && applicationTime !== "—" && applicationTime !== "";
  const hasApplicationType = applicationType !== "--" && applicationType !== "—" && applicationType !== "";

  return (
    <span className="compound-cell-value">
      <span className="compound-cell-primary workbench-oa-applicant-line">
        <span className="cell-text-value cell-text-value-full">{highlightSearchText(value, searchQuery)}</span>
        {showInlineDetail ? (
          <button
            aria-label={`查看OA ${value} 详情`}
            className="row-action-btn row-action-btn-inline row-action-btn-icon"
            title="查看OA详情"
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenDetail();
            }}
          >
            <Info aria-hidden="true" size={12} strokeWidth={2.2} />
          </button>
        ) : null}
      </span>
      <span className="compound-cell-secondary">
        {hasApplicationType ? <FinanceStatusTag>{highlightSearchText(applicationType, searchQuery)}</FinanceStatusTag> : null}
        <OaWorkflowStatusChip status={workflowStatus} />
        {hasApplicationTime
          ? renderInlineDateTimeTag(applicationTime, searchQuery)
          : <span className="inline-meta-tag inline-meta-tag-muted">时间缺失</span>}
      </span>
    </span>
  );
}

function renderBankNoteValue(
  value: string,
  relationStatus: string,
  showInlineDetail: boolean,
  onOpenDetail: () => void,
  bankTextFields: WorkbenchRecord["bankTextFields"] = [],
  searchQuery = "",
) {
  const internalTransferRemark = parseInternalTransferRemark(value, relationStatus);
  const visibleBankTextFields = (bankTextFields ?? []).filter((field) => field.label.trim() && field.value.trim());

  return (
    <span className="compound-cell-value">
      {visibleBankTextFields.length > 0 ? (
        <span className="compound-cell-primary bank-note-field-stack">
          {visibleBankTextFields.map((field) => (
            <span key={field.label} className="cell-text-value cell-text-value-full bank-note-field-line">
              {highlightSearchText(`${field.label}：${field.value}`, searchQuery)}
            </span>
          ))}
        </span>
      ) : internalTransferRemark ? (
        <>
          <span className="compound-cell-primary">
            <span className="inline-meta-tag">{highlightSearchText(internalTransferRemark.accountLabel, searchQuery)}</span>
          </span>
          {internalTransferRemark.note ? (
            <span className="compound-cell-secondary">
              <span className="cell-text-value cell-text-value-full">{highlightSearchText(internalTransferRemark.note, searchQuery)}</span>
            </span>
          ) : null}
        </>
      ) : (
        <span className="compound-cell-primary cell-text-value cell-text-value-full">{highlightSearchText(value, searchQuery)}</span>
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

function renderDateTimeValue(value: string, searchQuery = "") {
  if (value === "--" || value === "—") {
    return value;
  }

  const [datePart, ...rest] = value.trim().split(/\s+/);
  const timePart = rest.join(" ").trim();

  if (!timePart) {
    return <span className="datetime-cell-value">{highlightSearchText(datePart, searchQuery)}</span>;
  }

  return (
    <span className="datetime-cell-value">
      <span className="datetime-line">{highlightSearchText(datePart, searchQuery)}</span>
      <span className="datetime-line datetime-line-secondary">{highlightSearchText(timePart, searchQuery)}</span>
    </span>
  );
}

function renderBankMoneyValue(
  columnKey: string,
  value: string,
  direction: string,
  paymentAccount: string,
  row: WorkbenchRecord,
  zoneId: "paired" | "unpaired",
  searchQuery = "",
) {
  const hasValue = value !== "--" && value !== "—" && value !== "";
  const displayedValue = hasValue ? formatMoney(value) : "--";
  const normalizedDirection = resolveDirectionForMoneyCell(columnKey, direction, hasValue);
  const shouldShowDirectionTag = hasValue && normalizedDirection !== null;
  const shouldShowAccount = hasValue && paymentAccount !== "--" && paymentAccount !== "—" && paymentAccount !== "";
  const normalizedCategoryLabel = resolveBankCategoryDisplayLabel(row);
  const shouldShowCategory = normalizedCategoryLabel !== "" && normalizedCategoryLabel !== "--" && normalizedCategoryLabel !== "—";
  const pendingCategory = row.categoryResolutionStatus === "unmatched" || row.categoryResolutionStatus === "needs_confirmation";

  return (
    <span className="money-cell-stack">
      <span className="money-cell-value">
        <span>{highlightSearchText(displayedValue, searchQuery)}</span>
        {columnKey === "amount" && zoneId === "paired" ? <BankAmountMismatchWarning row={row} /> : null}
      </span>
      {shouldShowDirectionTag || shouldShowAccount ? (
        <span className="money-cell-meta-row">
          {shouldShowDirectionTag ? (
            <span className={`direction-tag direction-tag-${normalizedDirection === "收入" ? "inflow" : "outflow"}`}>
              {highlightSearchText(normalizedDirection, searchQuery)}
            </span>
          ) : null}
          {shouldShowAccount ? (
            <span className="money-cell-account">
              {renderHighlightedBankAccount(compactWorkbenchBankAccountLabel(paymentAccount), searchQuery)}
            </span>
          ) : null}
        </span>
      ) : null}
      {shouldShowCategory ? (
        <span className="money-cell-category-row">
          <Chip
            aria-label={`流水分类：${normalizedCategoryLabel}`}
            className="workbench-bank-category-chip"
            color={pendingCategory ? "warning" : "default"}
            size="sm"
            title={normalizedCategoryLabel}
            variant="soft"
          >
            <Chip.Label className="workbench-bank-category-chip-label">
              {highlightSearchText(normalizedCategoryLabel, searchQuery)}
            </Chip.Label>
          </Chip>
        </span>
      ) : null}
    </span>
  );
}

function resolveBankCategoryDisplayLabel(row: WorkbenchRecord) {
  if (row.categoryResolutionStatus === "needs_confirmation") {
    return "待确认";
  }
  if (row.categoryResolutionStatus === "unmatched") {
    return "待分类";
  }
  const categoryPath = (row.categoryLabelPath ?? []).map((label) => label.trim()).filter(Boolean);
  if (categoryPath.length > 0) {
    return categoryPath.join(" / ");
  }
  const primaryAndSubCategory = [row.categoryPrimaryLabel, row.categorySubLabel]
    .map((label) => (label ?? "").trim())
    .filter(Boolean);
  if (primaryAndSubCategory.length > 0) {
    return primaryAndSubCategory.join(" / ");
  }
  return (row.categoryLabel ?? "").trim();
}

function renderOaMoneyValue(
  value: string,
  searchQuery = "",
) {
  const hasValue = value !== "--" && value !== "—" && value !== "";
  const displayedValue = hasValue ? formatMoney(value) : "--";
  return (
    <span className="money-cell-stack">
      <span className="money-cell-value">
        <span>{highlightSearchText(displayedValue, searchQuery)}</span>
      </span>
    </span>
  );
}

function BankAmountMismatchWarning({ row }: { row: WorkbenchRecord }) {
  const [open, setOpen] = useState(false);
  const amountCheck = row.relationAmountCheck;
  const relationNote = (row.relationNote ?? "").trim();
  const shouldShow =
    row.recordType === "bank"
    && amountCheck?.status === "mismatch"
    && (relationNote.length > 0 || amountCheck.requiresNote === true);

  if (!shouldShow || !amountCheck) {
    return null;
  }

  const showTooltip = (
    event: MouseEvent<HTMLButtonElement> | FocusEvent<HTMLButtonElement> | TouchEvent<HTMLButtonElement>,
  ) => {
    event.stopPropagation();
    setOpen(true);
  };
  const hideTooltip = (event: MouseEvent<HTMLButtonElement> | FocusEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    setOpen(false);
  };

  return (
    <span className="record-warning-tooltip-wrap">
      <button
        aria-label="查看金额不一致差额说明"
        className="record-warning-icon-btn"
        type="button"
        onBlur={hideTooltip}
        onClick={showTooltip}
        onFocus={showTooltip}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onTouchStart={showTooltip}
      >
        <WarningTriangleIcon />
      </button>
      {open ? (
        <span className="bank-amount-mismatch-tooltip" role="tooltip">
          <strong>金额不一致</strong>
          <span>{`银行流水金额：${formatMismatchAmount(amountCheck.bankAmount)}`}</span>
          <span>{`OA合计：${formatMismatchAmount(amountCheck.oaAmount)}`}</span>
          <span>{`差额：${formatMismatchAmount(amountCheck.amountDelta)}`}</span>
          <span>{`差额说明：${relationNote || "—"}`}</span>
        </span>
      ) : null}
    </span>
  );
}

function WarningTriangleIcon() {
  return (
    <svg aria-hidden="true" className="record-warning-icon" viewBox="0 0 20 20">
      <path
        d="M10 3.1 18 16.4H2L10 3.1Z"
        fill="none"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.7"
      />
      <path d="M10 7.4v4.2" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
      <circle cx="10" cy="14.1" r="0.8" fill="currentColor" />
    </svg>
  );
}

function formatMismatchAmount(value: string | undefined) {
  const normalizedValue = (value ?? "").trim();
  if (!normalizedValue || normalizedValue === "--" || normalizedValue === "—") {
    return "—";
  }
  const numericValue = normalizedValue.replace(/,/g, "");
  if (!/^-?\d+(\.\d+)?$/.test(numericValue)) {
    return normalizedValue;
  }

  return formatMoney(numericValue);
}

function renderHighlightedBankAccount(value: string, searchQuery: string) {
  const parts = splitBankAccountLabel(value);
  if (!parts) {
    return <span className="bank-account-value bank-account-tag">{highlightSearchText(value, searchQuery)}</span>;
  }
  return (
    <span className="bank-account-value bank-account-tag">
      <span className="bank-account-primary">{highlightSearchText(parts.primary, searchQuery)}</span>
      <span className="bank-account-secondary">{highlightSearchText(parts.secondary, searchQuery)}</span>
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

function renderOaProjectValue(
  projectName: string,
  row: WorkbenchRecord,
  searchQuery = "",
) {
  if (row.displayRole === "expense-claim-summary") {
    return (
      <span className="oa-expense-summary">
        <span className="oa-expense-summary-chip">{highlightSearchText(projectName, searchQuery)}</span>
        <span className="oa-expense-summary-total">
          {`¥${formatWorkbenchAmountCents(parseWorkbenchAmountCents(row.amount))}`}
        </span>
      </span>
    );
  }

  return (
    <span className="compound-cell-value">
      <span className="compound-cell-primary cell-text-value cell-text-value-full">
        {highlightSearchText(projectName, searchQuery)}
      </span>
      {row.displayRole === "expense-claim-item" && row.expenseType ? (
        <Chip className="oa-expense-type-chip" color="default" size="sm" variant="soft">
          {highlightSearchText(row.expenseType, searchQuery)}
        </Chip>
      ) : null}
    </span>
  );
}

function highlightSearchText(value: string, query: string) {
  const normalizedQuery = query.trim().toLocaleLowerCase("zh-CN");
  if (!normalizedQuery) {
    return value;
  }
  const normalizedValue = value.toLocaleLowerCase("zh-CN");
  const queryParts = Array.from(new Set(normalizedQuery.split(/\s+/).filter(Boolean)))
    .sort((left, right) => right.length - left.length);
  const matches: Array<{ start: number; end: number }> = [];
  let offset = 0;
  while (offset < normalizedValue.length) {
    let nextMatch: { start: number; end: number } | null = null;
    for (const queryPart of queryParts) {
      const start = normalizedValue.indexOf(queryPart, offset);
      if (start < 0) {
        continue;
      }
      const candidate = { start, end: start + queryPart.length };
      if (!nextMatch || candidate.start < nextMatch.start || (
        candidate.start === nextMatch.start && candidate.end > nextMatch.end
      )) {
        nextMatch = candidate;
      }
    }
    if (!nextMatch) {
      break;
    }
    matches.push(nextMatch);
    offset = nextMatch.end;
  }
  if (matches.length === 0) {
    return value;
  }
  let cursor = 0;
  return (
    <>
      {matches.map((match, index) => {
        const prefix = value.slice(cursor, match.start);
        const hit = value.slice(match.start, match.end);
        cursor = match.end;
        return (
          <span key={`${match.start}-${index}`}>
            {prefix}
            <mark className="search-hit">{hit}</mark>
          </span>
        );
      })}
      {value.slice(cursor)}
    </>
  );
}

function renderBankCounterpartyValue(
  counterparty: string,
  transactionTime: string,
  showInlineDetail: boolean,
  onOpenDetail: () => void,
  searchQuery = "",
) {
  const hasTransactionTime = transactionTime !== "--" && transactionTime !== "—" && transactionTime !== "";

  return (
    <span className="compound-cell-value">
      <span className="compound-cell-primary bank-counterparty-primary">
        <span className="cell-text-value cell-text-value-full">{highlightSearchText(counterparty, searchQuery)}</span>
        {showInlineDetail ? (
          <button
            aria-label={`查看银行流水 ${counterparty} 详情`}
            className="row-action-btn row-action-btn-inline row-action-btn-icon"
            title="查看银行流水详情"
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenDetail();
            }}
          >
            <Info aria-hidden="true" size={12} strokeWidth={2.2} />
          </button>
        ) : null}
      </span>
      {hasTransactionTime ? (
        <span className="compound-cell-secondary compound-cell-secondary-nowrap">
          {renderInlineDateTimeTag(transactionTime, searchQuery)}
        </span>
      ) : null}
    </span>
  );
}

function renderInlineDateTimeTag(value: string, searchQuery = "") {
  const [datePart, ...rest] = value.trim().split(/\s+/);
  const timePart = rest.join(" ").trim();

  if (!timePart) {
    return <span className="inline-meta-tag inline-meta-tag-muted">{highlightSearchText(datePart, searchQuery)}</span>;
  }

  return (
    <span className="inline-meta-tag inline-meta-tag-muted inline-meta-tag-datetime">
      <span className="inline-meta-tag-datetime-date">{highlightSearchText(datePart, searchQuery)}</span>
      <span className="inline-meta-tag-datetime-time">{highlightSearchText(timePart, searchQuery)}</span>
    </span>
  );
}

function renderInvoicePartyValue(
  value: string,
  taxId: string,
  invoiceType: string,
  sourceKind?: WorkbenchSourceKind,
  anomaly?: WorkbenchRecord["oaInvoiceAnomaly"],
  externalUrl?: string,
  searchQuery = "",
) {
  const flowLabel = workbenchInvoiceFlowLabel(invoiceType);
  const sourceLabel = flowLabel || sourceKind ? workbenchInvoiceSourceLabel(sourceKind) : null;
  const hasTaxId = taxId !== "--" && taxId !== "—" && taxId !== "";

  return (
    <span className="compound-cell-value invoice-party-value">
      <span className="compound-cell-primary invoice-party-primary">
        <span className="invoice-party-text-stack">
          <span className="cell-text-value cell-text-value-full">{highlightSearchText(value, searchQuery)}</span>
          {hasTaxId ? <span className="cell-text-value cell-text-value-full cell-subtext-value">{highlightSearchText(taxId, searchQuery)}</span> : null}
          {flowLabel || sourceLabel ? (
            <span className="invoice-chip-row">
              {flowLabel ? (
                <span className={`invoice-flow-tag invoice-flow-tag-${flowLabel === "销" ? "output" : "input"}`}>{highlightSearchText(flowLabel, searchQuery)}</span>
              ) : null}
              {sourceLabel ? <span className="inline-meta-tag invoice-source-tag">{highlightSearchText(sourceLabel, searchQuery)}</span> : null}
            </span>
          ) : null}
          {anomaly ? renderInvoiceAnomalyChip(anomaly, externalUrl) : null}
        </span>
      </span>
    </span>
  );
}

function renderInvoiceAnomalyChip(
  anomaly: NonNullable<WorkbenchRecord["oaInvoiceAnomaly"]>,
  externalUrl?: string,
) {
  const chip = (
    <Chip
      className="invoice-oa-anomaly-chip"
      color={anomaly.code === "oa_invoice_amount_mismatch" ? "danger" : "warning"}
      size="sm"
      title={anomalyTitle(anomaly)}
      variant="soft"
    >
      <Chip.Label>{anomaly.displayLabel}</Chip.Label>
    </Chip>
  );
  if (!externalUrl) {
    return chip;
  }
  return (
    <a
      aria-label={`${anomaly.displayLabel}，在新窗口打开 OA`}
      className="invoice-oa-anomaly-link"
      href={externalUrl}
      rel="noopener noreferrer"
      target="_blank"
      onClick={(event) => event.stopPropagation()}
    >
      {chip}
    </a>
  );
}

function anomalyTitle(anomaly: NonNullable<WorkbenchRecord["oaInvoiceAnomaly"]>) {
  if (anomaly.code === "oa_invoice_attachment_missing") {
    return `OA子付款项已上传 ${anomaly.attachmentFileCount} 个附件，但未解析出发票`;
  }
  if (anomaly.code === "oa_invoice_attachment_parse_failed") {
    return `OA子付款项已有 ${anomaly.attachmentFileCount} 个附件，但发票解析失败`;
  }
  if (anomaly.code === "oa_invoice_attachment_unassigned") {
    return "OA 已解析出发票，但缺少明确的子付款项来源";
  }
  return `OA ${anomaly.oaTotal ?? "—"} / 发票 ${anomaly.invoiceTotal ?? "—"} / 差额 ${anomaly.amountDelta ?? "—"}`;
}

function renderInvoiceAmountValue(grossAmount: string, amount: string, taxRate: string, taxAmount: string, searchQuery = "") {
  const hasAmount = amount !== "--" && amount !== "—" && amount !== "";
  const showTaxMeta =
    taxRate !== "--" &&
    taxRate !== "—" &&
    taxRate !== "" &&
    taxAmount !== "--" &&
    taxAmount !== "—" &&
    taxAmount !== "";

  return (
    <span className="compound-cell-value invoice-amount-value">
      <span className="compound-cell-primary cell-text-value cell-text-value-full">{highlightSearchText(formatMoney(grossAmount, "--"), searchQuery)}</span>
      {hasAmount || showTaxMeta ? (
        <span className="compound-cell-secondary">
          <span className="cell-text-value cell-text-value-full cell-subtext-value">
            {highlightSearchText(`${hasAmount ? formatMoney(amount) : "--"}${showTaxMeta ? ` ${taxRate} (${formatMoney(taxAmount)})` : ""}`, searchQuery)}
          </span>
        </span>
      ) : null}
    </span>
  );
}

function renderInvoiceIdentityValue(
  invoiceNo: string,
  issueDate: string,
  showInlineDetail: boolean,
  onOpenDetail: () => void,
  searchQuery = "",
) {
  const normalizedNo = normalizeDisplayText(invoiceNo);
  const hasIssueDate = issueDate !== "--" && issueDate !== "—" && issueDate !== "";

  return (
    <span className="compound-cell-value invoice-identity-value">
      <span className="compound-cell-primary invoice-identity-primary">
        <span className="cell-text-value cell-text-value-full invoice-identity-no">{highlightSearchText(normalizedNo, searchQuery)}</span>
        {showInlineDetail ? (
          <button
            aria-label={`查看发票 ${normalizedNo} 详情`}
            className="row-action-btn row-action-btn-inline row-action-btn-icon"
            title="查看发票详情"
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenDetail();
            }}
          >
            <Info aria-hidden="true" size={12} strokeWidth={2.2} />
          </button>
        ) : null}
      </span>
      {hasIssueDate ? (
        <span className="compound-cell-tertiary">
          {renderInlineInvoiceDateTag(issueDate, searchQuery)}
        </span>
      ) : null}
    </span>
  );
}

function normalizeDisplayText(value: string) {
  return value && value !== "—" ? value : "--";
}

function renderInlineInvoiceDateTag(value: string, searchQuery = "") {
  const [datePart, ...rest] = value.trim().split(/\s+/);
  const timePart = rest.join(" ").trim();

  if (!timePart) {
    return <span className="inline-meta-tag inline-meta-tag-muted invoice-issue-date-tag">{highlightSearchText(datePart, searchQuery)}</span>;
  }

  return (
    <span className="inline-meta-tag inline-meta-tag-muted inline-meta-tag-datetime invoice-issue-date-tag">
      <span className="inline-meta-tag-datetime-date">{highlightSearchText(datePart, searchQuery)}</span>
      <span className="inline-meta-tag-datetime-time">{highlightSearchText(timePart, searchQuery)}</span>
    </span>
  );
}
