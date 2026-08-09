import { Alert, Button, Chip, ListBox, Select, Tabs } from "@heroui/react";
import { ArrowLeft, RefreshCw, Trash2, UploadCloud } from "lucide-react";
import { type DragEvent, type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link as RouterLink } from "react-router-dom";

import AppDialog from "../common/AppDialog";
import {
  EmptyValue,
  FinanceDirectionTag,
  FinanceStatusTag,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTablePagination,
  FinanceTableRow,
  TruncatedCellText,
} from "../common/FinanceTable";
import PageScaffold from "../common/PageScaffold";
import PageBusinessAuditIcon from "../common/PageBusinessAuditIcon";
import {
  confirmImportFiles,
  fetchImportReviewRows,
  fetchImportSession,
  previewImportFiles,
  retryImportFiles,
  resolveImportApiErrorMessage,
} from "../../features/imports/api";
import { confirmEtcImportSession, fetchReadyEtcReconciliationTasks, previewEtcZipFiles } from "../../features/etc/api";
import { formatMoney } from "../../features/money";
import { fetchWorkbenchSettings } from "../../features/workbench/api";
import type {
  ImportBatchType,
  ImportFilePreview,
  ImportFilePreviewOverride,
  ImportPreviewAuditCounts,
  ImportPreviewDetailRow,
  ImportReviewRowsPage,
  ImportSessionPayload,
} from "../../features/imports/types";
import type {
  EtcImportItem,
  EtcImportPreviewResult,
  EtcReconciliationBlockingIssue,
  EtcReconciliationTaskSummary,
  EtcUnavailableReconciliationTaskSummary,
} from "../../features/etc/types";
import type { BankAccountMapping } from "../../features/workbench/types";
import { useImportWorkflowDraft } from "../../contexts/ImportWorkflowDraftContext";
import type { FileSelectionState } from "../../contexts/ImportWorkflowDraftContext";
import { useImportProgress } from "../../contexts/ImportProgressContext";
import { useAppHealthStatus } from "../../contexts/AppHealthStatusContext";
import { useOptionalPageActivation } from "../../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../../contexts/SessionContext";
import type { ImportWorkflowMode } from "../../features/imports/importRoutes";

type ImportWorkflowPageProps = {
  mode: ImportWorkflowMode;
};

type ImportFilePreviewRow = ImportFilePreview & {
  accountLabel: string;
  batchTypeLabel: string;
  auditOriginalCount: number;
  auditUniqueCount: number;
  auditDuplicateInFileCount: number;
  auditDuplicateAcrossFilesCount: number;
  auditExistingDuplicateCount: number;
  auditImportableCount: number;
  auditErrorCount: number;
  auditSuspectedDuplicateCount: number;
  auditSkippedCount: number;
};

type ImportPreviewDetailGridRow = ImportPreviewDetailRow & {
  id: string;
  fileId: string;
  fileName: string;
  rowNo: number;
  duplicateType?: string;
  recordType?: string;
};

type EtcPreviewRow = EtcImportItem & {
  id: string;
  statusLabel: string;
  filterStatusLabel: string;
};

const BATCH_TYPE_LABELS: Record<ImportBatchType, string> = {
  input_invoice: "进项发票",
  output_invoice: "销项发票",
  bank_transaction: "银行流水",
};

const STATUS_LABELS: Record<string, string> = {
  preview_ready: "待确认",
  preview_ready_with_errors: "待确认",
  duplicate_file: "重复文件",
  source_control_mismatch: "控制合计不一致",
  unrecognized_template: "无法识别",
  confirmed: "已确认导入",
  skipped: "已跳过",
  reverted: "已撤销",
};

const ETC_IMPORT_STATUS_LABELS: Record<string, string> = {
  imported: "新增",
  created: "新增",
  duplicate_skipped: "重复跳过",
  attachment_completed: "附件补齐",
  failed: "异常",
};

const ETC_FILTER_STATUS_LABELS: Record<string, string> = {
  included: "本次导入",
  excluded_extra_zip_invoice: "不在任务内",
  ambiguous_zip_match: "命中冲突",
  duplicate_requirement_invoice_match: "重复命中",
  not_in_reconciliation_preview: "未筛选",
};

const IMPORT_ROW_DECISION_LABELS: Record<string, string> = {
  created: "可导入",
  status_updated: "状态更新",
  duplicate_skipped: "已存在",
  suspected_duplicate: "需复核",
  error: "异常",
};

const STALE_RECONCILIATION_PREVIEW_MESSAGE = "对账任务已更新，请重新预览 ETC zip 后再确认导入。";

const DUPLICATE_TYPE_LABELS: Record<string, string> = {
  duplicate_in_file: "文件内重复",
  duplicate_across_files: "跨文件重复",
};

const DIRECTION_LABELS: Record<string, string> = {
  inflow: "收入",
  outflow: "支出",
  income: "收入",
  expense: "支出",
};

const TITLES: Record<ImportWorkflowMode, string> = {
  bank_transaction: "银行流水导入",
  invoice: "发票导入",
  etc_invoice: "ETC发票导入",
};

const UPLOAD_LABELS: Record<ImportWorkflowMode, string> = {
  bank_transaction: "上传银行流水文件",
  invoice: "上传发票文件",
  etc_invoice: "上传ETC zip",
};

function buildSelectedFileKey(file: File) {
  return `${file.name}::${file.size}::${file.lastModified}`;
}

function mergeSelectedFiles(currentFiles: File[], nextFiles: File[]) {
  const merged = [...currentFiles];
  const seen = new Set(currentFiles.map(buildSelectedFileKey));
  nextFiles.forEach((file) => {
    const key = buildSelectedFileKey(file);
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    merged.push(file);
  });
  return merged;
}

function isExcelFile(file: File) {
  const normalizedName = file.name.toLowerCase();
  return normalizedName.endsWith(".xls") || normalizedName.endsWith(".xlsx");
}

function isZipFile(file: File) {
  return file.name.toLowerCase().endsWith(".zip");
}

function canConfirmFile(file: ImportFilePreview) {
  return file.status === "preview_ready";
}

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

function sourceControlLabel(status?: string) {
  if (status === "verified") return "已核对";
  if (status === "mismatch") return "不一致";
  if (status === "not_applicable") return "不适用";
  return "未提供";
}

function batchTypeLabel(batchType?: ImportBatchType | null) {
  if (!batchType) {
    return "待指定";
  }
  return BATCH_TYPE_LABELS[batchType] ?? batchType;
}

function etcStatusLabel(status: string) {
  return ETC_IMPORT_STATUS_LABELS[status] ?? status;
}

function etcFilterStatusLabel(status?: string) {
  if (!status) {
    return "--";
  }
  return ETC_FILTER_STATUS_LABELS[status] ?? status;
}

function importRowDecisionLabel(decision?: string | null) {
  if (!decision) {
    return "--";
  }
  return IMPORT_ROW_DECISION_LABELS[decision] ?? decision;
}

function duplicateTypeLabel(type?: string | null) {
  if (!type) {
    return "--";
  }
  return DUPLICATE_TYPE_LABELS[type] ?? type;
}

function directionLabel(direction?: string | null) {
  if (!direction) {
    return "--";
  }
  return DIRECTION_LABELS[direction] ?? direction;
}

function displayValue(value?: string | number | null) {
  if (value === null || value === undefined || value === "") {
    return "--";
  }
  return String(value);
}

type ImportNoticeTone = "success" | "danger" | "accent" | "warning";

function ImportNotice({
  tone,
  children,
  ariaLabel,
}: {
  tone: ImportNoticeTone;
  children: ReactNode;
  ariaLabel?: string;
}) {
  return (
    <Alert
      aria-label={ariaLabel}
      className={`import-workflow-notice import-workflow-notice--${tone}`}
      role={tone === "danger" || tone === "warning" ? "alert" : "status"}
      status={tone}
    >
      <Alert.Indicator />
      <Alert.Content className="import-workflow-notice__content">
        <Alert.Description className="import-workflow-notice__description">{children}</Alert.Description>
      </Alert.Content>
    </Alert>
  );
}

function ImportChip({
  children,
  color = "default",
}: {
  children: ReactNode;
  color?: "default" | "accent" | "success" | "warning" | "danger";
}) {
  return (
    <Chip className="import-workflow-chip" color={color} size="sm" variant="secondary">
      {children}
    </Chip>
  );
}

function ImportSelect({
  id,
  label,
  value,
  disabled,
  children,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  disabled?: boolean;
  children: ReactNode;
  onChange: (value: string) => void;
}) {
  return (
    <div className="import-workflow-select-field">
      <label className="import-workflow-select-field__label" htmlFor={id}>
        {label}
      </label>
      <select
        aria-label={label}
        className="import-workflow-select-field__control"
        disabled={disabled}
        id={id}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {children}
      </select>
    </div>
  );
}

function isMissingEtcRequirementIssue(issue: EtcReconciliationBlockingIssue) {
  return issue.error === "missing_required_etc_invoice";
}

function formatMissingRequirementLine(issue: EtcReconciliationBlockingIssue) {
  const transactionAt = displayValue(issue.transactionAt || issue.transactionDate);
  const amount = formatMoney(issue.amount, "--");
  const plate = displayValue(issue.vehiclePlate);
  const invoiceCount = issue.invoiceCount ? ` / ${issue.invoiceCount} 张` : "";
  return `${transactionAt} / ${amount} / ${plate}${invoiceCount}`;
}

function formatEtcRejectedMessage(count: number) {
  return `ETC发票导入仅支持 zip 文件，已拒绝 ${count} 个非 zip 文件。`;
}

function formatFileSize(file: File) {
  if (file.size >= 1024 * 1024) {
    return `${(file.size / 1024 / 1024).toFixed(1)} MB`;
  }
  return `${(file.size / 1024).toFixed(1)} KB`;
}

function buildBankAccountOptionLabel(bankOption: BankAccountMapping) {
  return `${bankOption.bankName} ${bankOption.last4}`.trim();
}

function buildEtcTaskOptionLabel(task: EtcReconciliationTaskSummary) {
  const period = task.periodStart && task.periodEnd ? `${task.periodStart} 至 ${task.periodEnd}` : "未设置期间";
  const plates = task.vehiclePlates.length > 0 ? ` / ${task.vehiclePlates.join("、")}` : "";
  const amount = task.oaTotalAmount ? ` / OA ${formatMoney(task.oaTotalAmount)}` : "";
  return `${task.title || "未命名任务"} / ${period} / ETC票 ${task.etcInvoiceCount} + 补充凭证 ${task.supplementCount}${amount}${plates}`;
}

function buildUnavailableEtcTaskReason(task: EtcUnavailableReconciliationTaskSummary) {
  const explicitMessages = task.importBlockers
    .map((blocker) => blocker.message.trim())
    .filter(Boolean);
  if (explicitMessages.length > 0) {
    return explicitMessages.join("；");
  }
  if (task.status === "reviewing" || task.status === "draft") {
    return "任务尚未确认，请先在 ETC 对账页确认对账。";
  }
  if (task.status === "importing") {
    return "任务正在导入中，请等待导入完成。";
  }
  if (task.status === "imported") {
    return "任务已导入 ETC 发票；如需重导，请先在 ETC 对账页移除已导入发票。";
  }
  if (task.status === "closed") {
    return "任务已关闭，不能导入。";
  }
  return "任务当前状态不可导入。";
}

function formatSelectedBankAccountLabel(file: Pick<ImportFilePreview, "selectedBankName" | "selectedBankLast4">) {
  return `${file.selectedBankName ?? ""} ${file.selectedBankLast4 ?? ""}`.trim();
}

function emptyAuditCounts(): ImportPreviewAuditCounts {
  return {
    originalCount: 0,
    uniqueCount: 0,
    duplicateCount: 0,
    duplicateInFileCount: 0,
    duplicateAcrossFilesCount: 0,
    existingDuplicateCount: 0,
    importableCount: 0,
    updateCount: 0,
    mergeCount: 0,
    suspectedDuplicateCount: 0,
    errorCount: 0,
    confirmableCount: 0,
    skippedCount: 0,
  };
}

function addAuditCounts(left: ImportPreviewAuditCounts, right: ImportPreviewAuditCounts): ImportPreviewAuditCounts {
  return {
    originalCount: left.originalCount + right.originalCount,
    uniqueCount: left.uniqueCount + right.uniqueCount,
    duplicateCount: left.duplicateCount + right.duplicateCount,
    duplicateInFileCount: left.duplicateInFileCount + right.duplicateInFileCount,
    duplicateAcrossFilesCount: left.duplicateAcrossFilesCount + right.duplicateAcrossFilesCount,
    existingDuplicateCount: left.existingDuplicateCount + right.existingDuplicateCount,
    importableCount: left.importableCount + right.importableCount,
    updateCount: left.updateCount + right.updateCount,
    mergeCount: left.mergeCount + right.mergeCount,
    suspectedDuplicateCount: left.suspectedDuplicateCount + right.suspectedDuplicateCount,
    errorCount: left.errorCount + right.errorCount,
    confirmableCount: left.confirmableCount + right.confirmableCount,
    skippedCount: left.skippedCount + right.skippedCount,
  };
}

function legacyFileAudit(file: ImportFilePreview): ImportPreviewAuditCounts {
  const duplicateCount = file.duplicateCount ?? 0;
  const importableCount = file.successCount ?? 0;
  const updateCount = file.updatedCount ?? 0;
  const suspectedDuplicateCount = file.suspectedDuplicateCount ?? 0;
  const errorCount = file.errorCount ?? 0;
  return {
    originalCount: file.rowCount ?? 0,
    uniqueCount: Math.max(0, (file.rowCount ?? 0) - duplicateCount),
    duplicateCount,
    duplicateInFileCount: duplicateCount,
    duplicateAcrossFilesCount: 0,
    existingDuplicateCount: 0,
    importableCount,
    updateCount,
    mergeCount: 0,
    suspectedDuplicateCount,
    errorCount,
    confirmableCount: importableCount + updateCount,
    skippedCount: duplicateCount + suspectedDuplicateCount + errorCount,
  };
}

function fileAudit(file: ImportFilePreview): ImportPreviewAuditCounts {
  return file.audit ?? legacyFileAudit(file);
}

function importSessionAudit(payload: ImportSessionPayload | null): ImportPreviewAuditCounts | null {
  if (!payload) {
    return null;
  }
  if (payload.session.audit) {
    return payload.session.audit;
  }
  return payload.files.reduce((total, file) => addAuditCounts(total, fileAudit(file)), emptyAuditCounts());
}

function etcAudit(payload: EtcImportPreviewResult | null): ImportPreviewAuditCounts | null {
  if (!payload) {
    return null;
  }
  if (payload.audit) {
    return payload.audit;
  }
  const duplicateCount = payload.duplicatesSkipped ?? 0;
  const importableCount = payload.imported ?? 0;
  const mergeCount = payload.attachmentsCompleted ?? 0;
  const errorCount = payload.failed ?? 0;
  return {
    originalCount: importableCount + duplicateCount + mergeCount + errorCount,
    uniqueCount: importableCount + duplicateCount + mergeCount,
    duplicateCount,
    duplicateInFileCount: duplicateCount,
    duplicateAcrossFilesCount: 0,
    existingDuplicateCount: duplicateCount,
    importableCount,
    updateCount: 0,
    mergeCount,
    suspectedDuplicateCount: 0,
    errorCount,
    confirmableCount: importableCount + mergeCount,
    skippedCount: duplicateCount + errorCount,
  };
}

function formatConfirmAuditMessage(audit: ImportPreviewAuditCounts | null) {
  if (!audit) {
    return null;
  }
  const skippedDuplicateCount = audit.duplicateCount + audit.existingDuplicateCount;
  const reviewCount = audit.suspectedDuplicateCount + audit.errorCount;
  return `将导入 ${audit.confirmableCount} 条唯一记录，跳过 ${skippedDuplicateCount} 条重复${reviewCount > 0 ? `，${reviewCount} 条需复核` : ""}。`;
}

function AuditSummaryCards({ audit }: { audit: ImportPreviewAuditCounts | null }) {
  if (!audit) {
    return null;
  }
  const items = [
    ["原始", audit.originalCount],
    ["唯一", audit.uniqueCount],
    ["重复", audit.duplicateCount],
    ["已存在", audit.existingDuplicateCount],
    ["可导入", audit.confirmableCount],
    ["异常", audit.errorCount],
    ["未导入", audit.skippedCount],
  ] as const;
  return (
    <div aria-label="导入预览审计汇总" className="import-workflow-audit-grid">
      {items.map(([label, value]) => (
        <div
          key={label}
          aria-label={`审计汇总 ${label} ${value}`}
          className="import-workflow-audit-card"
        >
          <div className="import-workflow-audit-card__label">{label}</div>
          <div className="import-workflow-audit-card__value">{value}</div>
        </div>
      ))}
    </div>
  );
}

function PreviewTableEmptyRow({ message }: { message: string }) {
  return (
    <FinanceTableRow id="empty" textValue={message}>
      <FinanceTableCell columnRole="description" textValue={message}>
        <EmptyValue value={message} />
      </FinanceTableCell>
      {Array.from({ length: 16 }, (_, index) => (
        <FinanceTableCell key={index} columnRole="description" textValue="--">
          <EmptyValue value="--" />
        </FinanceTableCell>
      ))}
    </FinanceTableRow>
  );
}

function ImportPreviewTable({ rows, loading }: { rows: ImportFilePreviewRow[]; loading: boolean }) {
  const emptyMessage = loading ? "正在加载..." : "--";

  return (
    <FinanceTable ariaLabel="导入预览结果" minWidth={1600}>
      <FinanceTableHeader>
        <FinanceTableColumn columnRole="identity" id="fileName" isRowHeader>文件</FinanceTableColumn>
        <FinanceTableColumn columnRole="status" id="status">状态</FinanceTableColumn>
        <FinanceTableColumn columnRole="status" id="batchTypeLabel">类型</FinanceTableColumn>
        <FinanceTableColumn columnRole="account" id="accountLabel">账户</FinanceTableColumn>
        <FinanceTableColumn columnRole="status" id="sourceControl">控制合计</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity" id="auditOriginalCount">原始</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity" id="auditUniqueCount">唯一</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity" id="auditDuplicateInFileCount">文件内重复</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity" id="auditDuplicateAcrossFilesCount">跨文件重复</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity" id="auditExistingDuplicateCount">已存在</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity" id="auditImportableCount">可导入</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity" id="auditSuspectedDuplicateCount">需复核</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity" id="auditErrorCount">异常</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity" id="auditSkippedCount">未导入</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity" id="rowCount">行数</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity" id="successCount">新增</FinanceTableColumn>
        <FinanceTableColumn columnRole="description" id="message">消息</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
        {rows.length === 0 ? (
          <PreviewTableEmptyRow message={emptyMessage} />
        ) : rows.map((row) => (
          <FinanceTableRow key={row.id} id={row.id} textValue={row.fileName}>
            <FinanceTableCell columnRole="identity" textValue={row.fileName}>
              <TruncatedCellText value={row.fileName} />
            </FinanceTableCell>
            <FinanceTableCell columnRole="status" textValue={statusLabel(row.status)}>
              <FinanceStatusTag tone={row.status === "preview_ready" ? "success" : "warning"}>
                {statusLabel(row.status)}
              </FinanceStatusTag>
            </FinanceTableCell>
            <FinanceTableCell columnRole="status" textValue={row.batchTypeLabel}>{row.batchTypeLabel}</FinanceTableCell>
            <FinanceTableCell columnRole="account" textValue={row.accountLabel}>
              <TruncatedCellText value={row.accountLabel} />
            </FinanceTableCell>
            <FinanceTableCell columnRole="status" textValue={sourceControlLabel(row.sourceControl?.status)}>
              <FinanceStatusTag
                tone={row.sourceControl?.status === "verified"
                  ? "success"
                  : row.sourceControl?.status === "mismatch"
                    ? "danger"
                    : row.sourceControl?.status === "unavailable"
                      ? "warning"
                      : "neutral"}
              >
                {sourceControlLabel(row.sourceControl?.status)}
              </FinanceStatusTag>
            </FinanceTableCell>
            <FinanceTableCell columnRole="quantity" textValue={String(row.auditOriginalCount)}>{row.auditOriginalCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity" textValue={String(row.auditUniqueCount)}>{row.auditUniqueCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity" textValue={String(row.auditDuplicateInFileCount)}>{row.auditDuplicateInFileCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity" textValue={String(row.auditDuplicateAcrossFilesCount)}>{row.auditDuplicateAcrossFilesCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity" textValue={String(row.auditExistingDuplicateCount)}>{row.auditExistingDuplicateCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity" textValue={String(row.auditImportableCount)}>{row.auditImportableCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity" textValue={String(row.auditSuspectedDuplicateCount)}>{row.auditSuspectedDuplicateCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity" textValue={String(row.auditErrorCount)}>{row.auditErrorCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity" textValue={String(row.auditSkippedCount)}>{row.auditSkippedCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity" textValue={String(row.rowCount)}>{displayValue(row.rowCount)}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity" textValue={String(row.successCount)}>{displayValue(row.successCount)}</FinanceTableCell>
            <FinanceTableCell columnRole="description" textValue={displayValue(row.message)}>
              <TruncatedCellText value={displayValue(row.message)} />
            </FinanceTableCell>
          </FinanceTableRow>
        ))}
      </FinanceTableBody>
    </FinanceTable>
  );
}

function DetailTableEmptyRow({ message, columnCount }: { message: string; columnCount: number }) {
  return (
    <FinanceTableRow id="empty" textValue={message}>
      <FinanceTableCell columnRole="description" textValue={message}>
        <EmptyValue value={message} />
      </FinanceTableCell>
      {Array.from({ length: columnCount - 1 }, (_, index) => (
        <FinanceTableCell key={index} columnRole="description" textValue="--">
          <EmptyValue value="--" />
        </FinanceTableCell>
      ))}
    </FinanceTableRow>
  );
}

function ImportPreviewDetailTable({
  ariaLabel,
  rows,
  loading,
  invoiceMode,
  page,
  pageSize,
  total,
  onPageChange,
}: {
  ariaLabel: "重复项明细" | "未导入项明细";
  rows: ImportPreviewDetailGridRow[];
  loading: boolean;
  invoiceMode: boolean;
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const emptyMessage = loading ? "正在加载..." : "--";
  const columnCount = invoiceMode ? 12 : 10;

  return (
    <FinanceTable
      ariaLabel={ariaLabel}
      footer={total > pageSize ? (
        <FinanceTablePagination
          compact
          isDisabled={loading}
          onPageChange={onPageChange}
          page={page}
          pageSize={pageSize}
          total={total}
        />
      ) : null}
      minWidth={invoiceMode ? 1520 : 1240}
    >
      <FinanceTableHeader>
        <FinanceTableColumn columnRole="identity" id="fileName" isRowHeader>文件</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity" id="rowNo">行号</FinanceTableColumn>
        {invoiceMode ? (
          <>
            <FinanceTableColumn columnRole="identity" id="invoiceNo">发票号码</FinanceTableColumn>
            <FinanceTableColumn columnRole="date" id="invoiceDate">开票日期</FinanceTableColumn>
            <FinanceTableColumn columnRole="description" id="sellerName">销方名称</FinanceTableColumn>
            <FinanceTableColumn columnRole="description" id="buyerName">购方名称</FinanceTableColumn>
            <FinanceTableColumn columnRole="amount" id="amount">金额</FinanceTableColumn>
            <FinanceTableColumn columnRole="amount" id="taxAmount">税额</FinanceTableColumn>
            <FinanceTableColumn columnRole="amount" id="totalWithTax">价税合计</FinanceTableColumn>
          </>
        ) : (
          <>
            <FinanceTableColumn columnRole="account" id="accountNo">账户</FinanceTableColumn>
            <FinanceTableColumn columnRole="date" id="tradeTime">交易时间</FinanceTableColumn>
            <FinanceTableColumn columnRole="direction" id="direction">方向</FinanceTableColumn>
            <FinanceTableColumn columnRole="amount" id="amount">金额</FinanceTableColumn>
            <FinanceTableColumn columnRole="description" id="counterpartyName">对方户名</FinanceTableColumn>
          </>
        )}
        <FinanceTableColumn columnRole="status" id="duplicateType">类型</FinanceTableColumn>
        <FinanceTableColumn columnRole="status" id="decision">决策</FinanceTableColumn>
        <FinanceTableColumn columnRole="description" id="decisionReason">原因</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
        {rows.length === 0 ? (
          <DetailTableEmptyRow columnCount={columnCount} message={emptyMessage} />
        ) : rows.map((row) => {
          const direction = directionLabel(row.direction);
          return (
            <FinanceTableRow key={row.id} id={row.id} textValue={`${row.fileName} ${row.rowNo}`}>
              <FinanceTableCell columnRole="identity" textValue={row.fileName}>
                <TruncatedCellText value={row.fileName} />
              </FinanceTableCell>
              <FinanceTableCell columnRole="quantity" textValue={String(row.rowNo)}>{row.rowNo}</FinanceTableCell>
              {invoiceMode ? (
                <>
                  <FinanceTableCell columnRole="identity" textValue={displayValue(row.invoiceNo)}>
                    <TruncatedCellText value={displayValue(row.invoiceNo)} />
                  </FinanceTableCell>
                  <FinanceTableCell columnRole="date" textValue={displayValue(row.invoiceDate)}>{displayValue(row.invoiceDate)}</FinanceTableCell>
                  <FinanceTableCell columnRole="description" textValue={displayValue(row.sellerName)}>
                    <TruncatedCellText value={displayValue(row.sellerName)} />
                  </FinanceTableCell>
                  <FinanceTableCell columnRole="description" textValue={displayValue(row.buyerName)}>
                    <TruncatedCellText value={displayValue(row.buyerName)} />
                  </FinanceTableCell>
                  <FinanceTableCell columnRole="amount" textValue={formatMoney(row.amount, "--")}>{formatMoney(row.amount, "--")}</FinanceTableCell>
                  <FinanceTableCell columnRole="amount" textValue={formatMoney(row.taxAmount, "--")}>{formatMoney(row.taxAmount, "--")}</FinanceTableCell>
                  <FinanceTableCell columnRole="amount" textValue={formatMoney(row.totalWithTax, "--")}>{formatMoney(row.totalWithTax, "--")}</FinanceTableCell>
                </>
              ) : (
                <>
                  <FinanceTableCell columnRole="account" textValue={displayValue(row.accountNo)}>
                    <TruncatedCellText value={displayValue(row.accountNo)} />
                  </FinanceTableCell>
                  <FinanceTableCell columnRole="date" textValue={displayValue(row.tradeTime)}>{displayValue(row.tradeTime)}</FinanceTableCell>
                  <FinanceTableCell columnRole="direction" textValue={direction}>
                    {direction === "--" ? <EmptyValue value="--" /> : <FinanceDirectionTag direction={direction}>{direction}</FinanceDirectionTag>}
                  </FinanceTableCell>
                  <FinanceTableCell columnRole="amount" textValue={formatMoney(row.amount, "--")}>{formatMoney(row.amount, "--")}</FinanceTableCell>
                  <FinanceTableCell columnRole="description" textValue={displayValue(row.counterpartyName)}>
                    <TruncatedCellText value={displayValue(row.counterpartyName)} />
                  </FinanceTableCell>
                </>
              )}
              <FinanceTableCell columnRole="status" textValue={duplicateTypeLabel(row.duplicateType)}>
                {duplicateTypeLabel(row.duplicateType)}
              </FinanceTableCell>
              <FinanceTableCell columnRole="status" textValue={importRowDecisionLabel(row.decision)}>
                <FinanceStatusTag tone={row.decision === "error" ? "danger" : row.decision === "suspected_duplicate" ? "warning" : "neutral"}>
                  {importRowDecisionLabel(row.decision)}
                </FinanceStatusTag>
              </FinanceTableCell>
              <FinanceTableCell columnRole="description" textValue={displayValue(row.decisionReason)}>
                <TruncatedCellText value={displayValue(row.decisionReason)} />
              </FinanceTableCell>
            </FinanceTableRow>
          );
        })}
      </FinanceTableBody>
    </FinanceTable>
  );
}

function EtcTableEmptyRow({ message }: { message: string }) {
  return (
    <FinanceTableRow id="empty" textValue={message}>
      <FinanceTableCell columnRole="description" textValue={message}>
        <EmptyValue value={message} />
      </FinanceTableCell>
      {Array.from({ length: 4 }, (_, index) => (
        <FinanceTableCell key={index} columnRole="description" textValue="--">
          <EmptyValue value="--" />
        </FinanceTableCell>
      ))}
    </FinanceTableRow>
  );
}

function EtcPreviewTable({ rows, loading }: { rows: EtcPreviewRow[]; loading: boolean }) {
  const emptyMessage = loading ? "正在加载..." : "--";

  return (
    <FinanceTable ariaLabel="ETC导入预览结果" minWidth={980}>
      <FinanceTableHeader>
        <FinanceTableColumn columnRole="identity" id="invoiceNumber" isRowHeader>发票号</FinanceTableColumn>
        <FinanceTableColumn columnRole="description" id="fileName">文件</FinanceTableColumn>
        <FinanceTableColumn columnRole="status" id="statusLabel">状态</FinanceTableColumn>
        <FinanceTableColumn columnRole="status" id="filterStatusLabel">对账筛选</FinanceTableColumn>
        <FinanceTableColumn columnRole="description" id="reason">原因</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
        {rows.length === 0 ? (
          <EtcTableEmptyRow message={emptyMessage} />
        ) : rows.map((row) => (
          <FinanceTableRow key={row.id} id={row.id} textValue={displayValue(row.invoiceNumber || row.fileName)}>
            <FinanceTableCell columnRole="identity" textValue={displayValue(row.invoiceNumber)}>
              <TruncatedCellText value={displayValue(row.invoiceNumber)} />
            </FinanceTableCell>
            <FinanceTableCell columnRole="description" textValue={displayValue(row.fileName)}>
              <TruncatedCellText value={displayValue(row.fileName)} />
            </FinanceTableCell>
            <FinanceTableCell columnRole="status" textValue={row.statusLabel}>
              <FinanceStatusTag tone={row.status === "failed" ? "danger" : row.status === "duplicate_skipped" ? "warning" : "success"}>
                {row.statusLabel}
              </FinanceStatusTag>
            </FinanceTableCell>
            <FinanceTableCell columnRole="status" textValue={row.filterStatusLabel}>{row.filterStatusLabel}</FinanceTableCell>
            <FinanceTableCell columnRole="description" textValue={displayValue(row.reason)}>
              <TruncatedCellText value={displayValue(row.reason)} />
            </FinanceTableCell>
          </FinanceTableRow>
        ))}
      </FinanceTableBody>
    </FinanceTable>
  );
}

export default function ImportWorkflowPage({ mode }: ImportWorkflowPageProps) {
  const { active: pageActive, activationGeneration } = useOptionalPageActivation();
  const inputId = useId();
  const { setProgress, clearProgress } = useImportProgress();
  const {
    draft,
    updateDraft,
    resetDraft,
    clearPersistedSession,
    readPersistedSessionId,
    persistSessionId,
    setSelectedFiles,
    setFileSelections,
    setPreviewPayload,
    setEtcPreviewPayload,
    setSelectedEtcTaskId,
    setEtcImported,
    setFeedbackMessage,
    setErrorMessage,
    setIsPreviewing,
    setIsConfirming,
  } = useImportWorkflowDraft(mode);
  const healthStatus = useAppHealthStatus();
  const { canAdminAccess, canMutateData } = useSessionPermissions();
  const {
    selectedFiles,
    fileSelections,
    previewPayload,
    etcPreviewPayload,
    selectedEtcTaskId,
    etcImported,
    feedbackMessage,
    errorMessage,
    isPreviewing,
    isConfirming,
  } = draft;
  const [bankOptions, setBankOptions] = useState<BankAccountMapping[]>([]);
  const [readyEtcTasks, setReadyEtcTasks] = useState<EtcReconciliationTaskSummary[]>([]);
  const [unavailableEtcTasks, setUnavailableEtcTasks] = useState<EtcUnavailableReconciliationTaskSummary[]>([]);
  const [readyEtcTasksLoading, setReadyEtcTasksLoading] = useState(mode === "etc_invoice");
  const [settingsLoading, setSettingsLoading] = useState(mode === "bank_transaction");
  const [conflictDialogOpen, setConflictDialogOpen] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [previewDetailTab, setPreviewDetailTab] = useState<"duplicates" | "unimported">("duplicates");
  const [previewDetailOffset, setPreviewDetailOffset] = useState(0);
  const [previewDetailPage, setPreviewDetailPage] = useState<ImportReviewRowsPage | null>(null);
  const [previewDetailLoading, setPreviewDetailLoading] = useState(false);
  const [previewDetailError, setPreviewDetailError] = useState<string | null>(null);
  const [contextRefreshToken, setContextRefreshToken] = useState(0);
  const [isRefreshingContext, setIsRefreshingContext] = useState(false);
  const [mappingDrafts, setMappingDrafts] = useState<Record<string, Record<string, string>>>({});
  const [mappingRetryingFileId, setMappingRetryingFileId] = useState<string | null>(null);
  const mountedRef = useRef(false);

  const title = TITLES[mode];
  const uploadLabel = UPLOAD_LABELS[mode];

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (mode === "etc_invoice") {
        updateDraft((current) => ({
          ...current,
          isPreviewing: false,
          isConfirming: false,
        }));
      }
    };
  }, [mode, updateDraft]);

  useEffect(() => {
    const controller = new AbortController();
    if (!pageActive || mode !== "bank_transaction") {
      setSettingsLoading(false);
      setBankOptions([]);
      return () => controller.abort();
    }

    setSettingsLoading(true);
    fetchWorkbenchSettings(controller.signal)
      .then((settings) => {
        setBankOptions(
          [...settings.bankAccountMappings].sort((left, right) => (
            buildBankAccountOptionLabel(left).localeCompare(buildBankAccountOptionLabel(right), "zh-Hans-CN")
          )),
        );
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setErrorMessage(resolveImportApiErrorMessage(error, "银行账户映射加载失败。"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setSettingsLoading(false);
        }
      });

    return () => controller.abort();
  }, [activationGeneration, contextRefreshToken, mode, pageActive, setErrorMessage]);

  useEffect(() => {
    const controller = new AbortController();
    if (!pageActive || mode !== "etc_invoice") {
      setReadyEtcTasks([]);
      setUnavailableEtcTasks([]);
      setReadyEtcTasksLoading(false);
      return () => controller.abort();
    }

    setReadyEtcTasksLoading(true);
    fetchReadyEtcReconciliationTasks(controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) {
          return;
        }
        setReadyEtcTasks(payload.items);
        setUnavailableEtcTasks(payload.unavailableItems);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setErrorMessage(resolveImportApiErrorMessage(error, "ETC 对账任务加载失败，请稍后重试。"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setReadyEtcTasksLoading(false);
        }
      });

    return () => controller.abort();
  }, [activationGeneration, contextRefreshToken, mode, pageActive, setErrorMessage]);

  useEffect(() => {
    if (!pageActive || mode === "etc_invoice" || selectedFiles.length > 0 || previewPayload) {
      return undefined;
    }
    const sessionId = readPersistedSessionId();
    if (!sessionId) {
      return undefined;
    }

    let active = true;
    setIsPreviewing(true);
    setErrorMessage(null);
    fetchImportSession(sessionId)
      .then((payload) => {
        if (!active) {
          return;
        }
        setIsPreviewing(false);
        setPreviewPayload(payload);
        setFeedbackMessage(`已恢复上次 ${payload.files.length} 个文件的预览识别。`);
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setIsPreviewing(false);
        clearPersistedSession();
        resetDraft();
        setErrorMessage("上次预览会话已失效，请重新选择文件。");
      });

    return () => {
      active = false;
    };
  }, [
    activationGeneration,
    clearPersistedSession,
    contextRefreshToken,
    mode,
    pageActive,
    previewPayload,
    readPersistedSessionId,
    resetDraft,
    selectedFiles.length,
    setErrorMessage,
    setFeedbackMessage,
    setIsPreviewing,
    setPreviewPayload,
  ]);

  useEffect(() => {
    const sessionId = previewPayload?.session.id;
    if (!pageActive || mode === "etc_invoice" || !sessionId) {
      setPreviewDetailPage(null);
      setPreviewDetailLoading(false);
      setPreviewDetailError(null);
      return undefined;
    }
    const controller = new AbortController();
    setPreviewDetailLoading(true);
    setPreviewDetailError(null);
    fetchImportReviewRows(sessionId, previewDetailTab, previewDetailOffset, controller.signal)
      .then((payload) => {
        if (!controller.signal.aborted) setPreviewDetailPage(payload);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setPreviewDetailError(resolveImportApiErrorMessage(error, "导入复核明细加载失败。"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setPreviewDetailLoading(false);
      });
    return () => controller.abort();
  }, [mode, pageActive, previewDetailOffset, previewDetailTab, previewPayload]);

  const bankOptionMap = useMemo(
    () => new Map(bankOptions.map((item) => [item.id, item])),
    [bankOptions],
  );
  const selectedEtcTask = useMemo(
    () => readyEtcTasks.find((task) => task.taskId === selectedEtcTaskId) ?? null,
    [readyEtcTasks, selectedEtcTaskId],
  );
  const hasSelectedEtcTask = mode !== "etc_invoice" || Boolean(selectedEtcTask);

  const canUseBankImport = mode !== "bank_transaction" || bankOptions.length > 0;
  const allFilesConfigured = selectedFiles.length > 0 && selectedFiles.every((file) => {
    if (mode === "etc_invoice") {
      return isZipFile(file);
    }
    const selection = fileSelections[buildSelectedFileKey(file)];
    return mode === "bank_transaction" ? Boolean(selection?.bankMappingId) : Boolean(selection?.invoiceBatchType);
  });
  const canPreview = canUseBankImport
    && canMutateData
    && hasSelectedEtcTask
    && allFilesConfigured
    && !isPreviewing
    && !isConfirming
    && !settingsLoading
    && !readyEtcTasksLoading;
  const confirmableFileIds = useMemo(
    () => previewPayload?.files.filter(canConfirmFile).map((file) => file.id) ?? [],
    [previewPayload],
  );
  const etcBlockingIssues = useMemo(
    () => etcPreviewPayload?.reconciliationFilter?.blockingIssues ?? [],
    [etcPreviewPayload],
  );
  const missingEtcRequirementIssues = useMemo(
    () => etcBlockingIssues.filter(isMissingEtcRequirementIssue),
    [etcBlockingIssues],
  );
  const canConfirm = canMutateData && confirmableFileIds.length > 0 && !isPreviewing && !isConfirming;
  const canConfirmEtc = Boolean(etcPreviewPayload?.sessionId)
    && canMutateData
    && Boolean(selectedEtcTaskId)
    && Boolean(selectedEtcTask)
    && etcBlockingIssues.length === 0
    && !etcImported
    && !isPreviewing
    && !isConfirming;
  const hasDraftContent = selectedFiles.length > 0
    || Boolean(previewPayload)
    || Boolean(etcPreviewPayload)
    || Boolean(selectedEtcTaskId)
    || Object.keys(fileSelections).length > 0
    || Boolean(feedbackMessage)
    || Boolean(errorMessage);
  const conflictingPreviewFiles = useMemo(
    () => previewPayload?.files.filter((file) => canConfirmFile(file) && file.bankSelectionConflict) ?? [],
    [previewPayload],
  );
  const mappingRequiredFiles = useMemo(
    () => previewPayload?.files.filter((file) => (
      file.status === "unrecognized_template" && file.mappingCandidates.length > 0 && file.mappingFields.length > 0
    )) ?? [],
    [previewPayload],
  );
  const conflictConfirmLabel = useMemo(() => {
    const selectedAccountLabel = formatSelectedBankAccountLabel(conflictingPreviewFiles[0] ?? {});
    return selectedAccountLabel
      ? `仍按所选账户 ${selectedAccountLabel} 导入`
      : "仍按所选账户导入";
  }, [conflictingPreviewFiles]);
  const previewAudit = useMemo(() => importSessionAudit(previewPayload), [previewPayload]);
  const etcPreviewAudit = useMemo(() => etcAudit(etcPreviewPayload), [etcPreviewPayload]);
  const confirmAuditMessage = useMemo(
    () => formatConfirmAuditMessage(mode === "etc_invoice" ? (etcPreviewPayload?.importAudit ?? etcPreviewAudit) : previewAudit),
    [etcPreviewAudit, etcPreviewPayload?.importAudit, mode, previewAudit],
  );

  const previewRows = useMemo<ImportFilePreviewRow[]>(() => (
    previewPayload?.files.map((file) => {
      const audit = fileAudit(file);
      return {
        ...file,
        accountLabel: formatSelectedBankAccountLabel(file) || "--",
        batchTypeLabel: batchTypeLabel(file.batchType),
        auditOriginalCount: audit.originalCount,
        auditUniqueCount: audit.uniqueCount,
        auditDuplicateInFileCount: audit.duplicateInFileCount,
        auditDuplicateAcrossFilesCount: audit.duplicateAcrossFilesCount,
        auditExistingDuplicateCount: audit.existingDuplicateCount,
        auditImportableCount: audit.importableCount,
        auditErrorCount: audit.errorCount,
        auditSuspectedDuplicateCount: audit.suspectedDuplicateCount,
        auditSkippedCount: audit.skippedCount,
      };
    }) ?? []
  ), [previewPayload]);

  const previewDetailRows = previewDetailPage?.rows ?? [];
  const previewDetailPageSize = previewDetailPage?.limit ?? 100;
  const previewDetailTotal = previewDetailPage?.total ?? (
    previewDetailTab === "duplicates" ? previewAudit?.duplicateCount : previewAudit?.skippedCount
  ) ?? 0;

  const etcRows = useMemo<EtcPreviewRow[]>(() => (
    etcPreviewPayload?.items.map((item, index) => ({
      ...item,
      id: `${item.invoiceNumber || item.fileName || "etc"}-${index}`,
      statusLabel: etcStatusLabel(item.status),
      filterStatusLabel: etcFilterStatusLabel(item.filterStatus),
    })) ?? []
  ), [etcPreviewPayload]);

  function resetPreviewState() {
    setPreviewPayload(null);
    setEtcPreviewPayload(null);
    setEtcImported(false);
    setConflictDialogOpen(false);
    setMappingDrafts({});
    setMappingRetryingFileId(null);
    setFeedbackMessage(null);
    setErrorMessage(null);
    setPreviewDetailOffset(0);
    setPreviewDetailPage(null);
    setPreviewDetailError(null);
    clearPersistedSession();
  }

  function updateFiles(nextFiles: File[]) {
    setSelectedFiles((current) => mergeSelectedFiles(current, nextFiles));
    resetPreviewState();
  }

  function applyDroppedFiles(files: File[]) {
    if (!canMutateData) {
      return;
    }
    const isSupportedFile = mode === "etc_invoice" ? isZipFile : isExcelFile;
    const validFiles = files.filter(isSupportedFile);
    const invalidFiles = files.filter((file) => !isSupportedFile(file));
    if (validFiles.length > 0) {
      updateFiles(validFiles);
    } else if (invalidFiles.length > 0) {
      resetPreviewState();
    }
    if (invalidFiles.length > 0) {
      setErrorMessage(mode === "etc_invoice" ? formatEtcRejectedMessage(invalidFiles.length) : "仅支持 .xls/.xlsx");
    }
  }

  function handleDropzoneDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (canMutateData && !isPreviewing && !isConfirming) {
      setIsDragActive(true);
    }
  }

  function handleDropzoneDragLeave(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setIsDragActive(false);
    }
  }

  function handleDropzoneDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragActive(false);
    if (!canMutateData || isPreviewing || isConfirming) {
      return;
    }
    const nextFiles = Array.from(event.dataTransfer.files ?? []);
    if (nextFiles.length > 0) {
      applyDroppedFiles(nextFiles);
    }
  }

  function handleSelectionChange(file: File, field: "bankMappingId" | "invoiceBatchType", value: string) {
    const key = buildSelectedFileKey(file);
    setFileSelections((current) => ({
      ...current,
      [key]: field === "bankMappingId"
        ? (() => {
          const bankOption = bankOptionMap.get(value);
          return {
            bankMappingId: value,
            bankName: bankOption?.bankName ?? "",
            bankShortName: bankOption?.shortName ?? "",
            last4: bankOption?.last4 ?? "",
            invoiceBatchType: current[key]?.invoiceBatchType ?? "",
          };
        })()
        : {
          bankMappingId: current[key]?.bankMappingId ?? "",
          bankName: current[key]?.bankName ?? "",
          bankShortName: current[key]?.bankShortName ?? "",
          last4: current[key]?.last4 ?? "",
          invoiceBatchType: value as ImportBatchType | "",
        },
    }));
    resetPreviewState();
  }

  function handleEtcTaskChange(taskId: string) {
    setSelectedEtcTaskId(taskId);
    resetPreviewState();
  }

  function handleRemoveFile(file: File) {
    const key = buildSelectedFileKey(file);
    setSelectedFiles((current) => current.filter((item) => buildSelectedFileKey(item) !== key));
    setFileSelections((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    resetPreviewState();
  }

  function handleClearFiles() {
    setSelectedFiles([]);
    setFileSelections({});
    resetPreviewState();
  }

  async function handleRefresh() {
    if (isRefreshingContext || isPreviewing || isConfirming) return;
    setContextRefreshToken((current) => current + 1);
    if (mode === "etc_invoice" || !previewPayload?.session.id) return;
    setIsRefreshingContext(true);
    setErrorMessage(null);
    try {
      const payload = await fetchImportSession(previewPayload.session.id);
      setPreviewPayload(payload);
      setFeedbackMessage("导入预览已刷新。");
    } catch (caught) {
      setErrorMessage(resolveImportApiErrorMessage(caught, "导入预览刷新失败。"));
    } finally {
      setIsRefreshingContext(false);
    }
  }

  function buildPreviewOverrides(): ImportFilePreviewOverride[] {
    return selectedFiles.map((file) => {
      const selection = fileSelections[buildSelectedFileKey(file)];
      if (mode === "bank_transaction") {
        return {
          fileName: file.name,
          batchType: "bank_transaction",
          bankMappingId: selection?.bankMappingId ?? "",
          bankName: selection?.bankName ?? "",
          bankShortName: selection?.bankShortName ?? "",
          last4: selection?.last4 ?? "",
        };
      }
      return {
        fileName: file.name,
        templateCode: "invoice_export",
        batchType: selection?.invoiceBatchType || undefined,
      };
    });
  }

  async function handlePreview() {
    if (mode === "etc_invoice") {
      if (!selectedEtcTask) {
        setErrorMessage("请选择已确认的 ETC 对账任务后再预览 ETC zip。");
        return;
      }
      if (selectedFiles.length === 0) {
        setErrorMessage("请先选择至少一个 ETC zip 文件。");
        return;
      }
      if (!selectedFiles.every(isZipFile)) {
        setErrorMessage("ETC发票导入仅支持 zip 文件。");
        return;
      }
      setIsPreviewing(true);
      setErrorMessage(null);
      setFeedbackMessage(null);
      try {
        const payload = await previewEtcZipFiles(selectedFiles, selectedEtcTask.taskId);
        if (!mountedRef.current) {
          return;
        }
        updateDraft((current) => ({
          ...current,
          etcPreviewPayload: payload,
          etcImported: false,
          previewPayload: null,
          feedbackMessage: `已完成 ${selectedFiles.length} 个 ETC zip 文件预览。`,
          errorMessage: null,
        }));
      } catch (error) {
        if (!mountedRef.current) {
          return;
        }
        setErrorMessage(resolveImportApiErrorMessage(error, "ETC zip 预览失败，请稍后重试。"));
      } finally {
        if (mountedRef.current) {
          setIsPreviewing(false);
        }
      }
      return;
    }

    if (!canUseBankImport) {
      setErrorMessage("设置里还没有银行账户映射，请先在设置中维护银行。");
      return;
    }
    if (!allFilesConfigured) {
      setErrorMessage(mode === "bank_transaction" ? "请为每个文件选择对应账户。" : "请为每个文件选择进项票或销项票。");
      return;
    }
    setIsPreviewing(true);
    setErrorMessage(null);
    setFeedbackMessage(null);
    setConflictDialogOpen(false);
    try {
      const payload = await previewImportFiles(selectedFiles, "web_finance_user", buildPreviewOverrides());
      persistSessionId(payload.session.id);
      updateDraft((current) => ({
        ...current,
        previewPayload: payload,
        feedbackMessage: `已完成 ${payload.files.length} 个文件的预览识别。`,
        errorMessage: null,
      }));
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "文件预览失败，请稍后重试。"));
    } finally {
      setIsPreviewing(false);
    }
  }

  async function handleApplyFieldMapping(file: ImportFilePreview) {
    if (!previewPayload || mappingRetryingFileId) return;
    const fieldMapping = { ...file.fieldMapping, ...(mappingDrafts[file.id] ?? {}) };
    setMappingRetryingFileId(file.id);
    setErrorMessage(null);
    try {
      const payload = await retryImportFiles(previewPayload.session.id, [file.id], {
        [file.id]: {
          batchType: "bank_transaction",
          bankMappingId: file.selectedBankMappingId,
          bankName: file.selectedBankName,
          bankShortName: file.selectedBankShortName,
          last4: file.selectedBankLast4,
          fieldMapping,
        },
      });
      setPreviewPayload(payload);
      setMappingDrafts((current) => {
        const next = { ...current };
        delete next[file.id];
        return next;
      });
      const refreshed = payload.files.find((item) => item.id === file.id);
      setFeedbackMessage(refreshed?.status === "preview_ready" ? "字段映射已保存并重新完成预览。" : null);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "字段映射保存失败，请重试。"));
    } finally {
      setMappingRetryingFileId(null);
    }
  }

  function completeImportFeedback(payload: ImportSessionPayload) {
    const confirmedCount = payload.files.filter((file) => file.status === "confirmed").length;
    setProgress({ tone: "success", label: `已导入 ${confirmedCount} 个文件。` });
  }

  async function submitConfirm() {
    if (healthStatus.blocksMutations) {
      setErrorMessage("登录已失效或系统不可用，请返回 OA 系统重新进入。");
      return;
    }
    if (mode === "etc_invoice") {
      if (!selectedEtcTask) {
        setErrorMessage("请选择已确认的 ETC 对账任务后再预览 ETC zip。");
        return;
      }
      if (!etcPreviewPayload?.sessionId) {
        setErrorMessage("请先预览 ETC zip 文件。");
        return;
      }
      setIsConfirming(true);
      setErrorMessage(null);
      try {
        const payload = await confirmEtcImportSession(etcPreviewPayload.sessionId, selectedEtcTask.taskId);
        setEtcImported(true);
        setFeedbackMessage(payload.job ? "已开始后台导入" : "已导入 ETC票据管理");
      } catch (error) {
        if (error instanceof Error && error.message === STALE_RECONCILIATION_PREVIEW_MESSAGE) {
          setEtcPreviewPayload(null);
          setEtcImported(false);
        }
        setErrorMessage(resolveImportApiErrorMessage(error, "确认导入失败，请稍后重试。"));
      } finally {
        setIsConfirming(false);
      }
      return;
    }

    if (!previewPayload || confirmableFileIds.length === 0) {
      setErrorMessage("没有可确认导入的文件。");
      return;
    }
    setIsConfirming(true);
    setErrorMessage(null);
    try {
      const payload = await confirmImportFiles(previewPayload.session.id, confirmableFileIds);
      setConflictDialogOpen(false);
      if (payload.job) {
        resetDraft();
        if (payload.job.status === "succeeded" || payload.job.status === "partial_success") {
          setFeedbackMessage("已确认导入");
          void completeImportFeedback(payload);
        } else {
          setFeedbackMessage("已开始后台导入");
        }
        return;
      }
      resetDraft();
      setFeedbackMessage("已确认导入");
      void completeImportFeedback(payload);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "确认导入失败，请稍后重试。"));
    } finally {
      setIsConfirming(false);
    }
  }

  async function handleConfirm() {
    if (conflictingPreviewFiles.length > 0) {
      setConflictDialogOpen(true);
      return;
    }
    await submitConfirm();
  }

  return (
    <div className="import-workflow-page" data-testid="import-workflow-page">
      <PageScaffold
        title={title}
        titleAccessory={canAdminAccess ? (
          mode === "bank_transaction" ? (
            <PageBusinessAuditIcon
              ariaLabel="Audit 银行流水导入"
              label="银行流水导入"
              pageKey="imports.bank-transactions"
            />
          ) : mode === "invoice" ? (
            <PageBusinessAuditIcon
              ariaLabel="Audit 发票导入"
              label="发票导入"
              pageKey="imports.invoices"
            />
          ) : (
            <PageBusinessAuditIcon
              ariaLabel="Audit ETC发票导入"
              label="ETC发票导入"
              pageKey="imports.etc-invoices"
            />
          )
        ) : null}
        actions={
          <div className="import-workflow-actions" data-testid="import-workflow-actions">
            <RouterLink className="button button--secondary button--sm import-workflow-back-link" to="/">
              <ArrowLeft aria-hidden="true" size={16} strokeWidth={2.2} />
              返回关联台
            </RouterLink>
            <Button
              isDisabled={isPreviewing || isConfirming || isRefreshingContext || settingsLoading || readyEtcTasksLoading}
              onPress={handleRefresh}
              size="sm"
              type="button"
              variant="secondary"
            >
              <RefreshCw aria-hidden="true" size={16} />
              刷新
            </Button>
            <Button
              isDisabled={!hasDraftContent || isPreviewing || isConfirming}
              onPress={handleClearFiles}
              size="sm"
              type="button"
              variant="secondary"
            >
              清空
            </Button>
            <Button isDisabled={!canPreview} onPress={handlePreview} size="sm" type="button" variant="secondary">
              {isPreviewing ? "预览中..." : "开始预览"}
            </Button>
            <Button
              isDisabled={healthStatus.blocksMutations || (mode === "etc_invoice" ? !canConfirmEtc : !canConfirm)}
              onPress={handleConfirm}
              type="button"
            >
              {isConfirming ? "确认中..." : "确认导入"}
            </Button>
          </div>
        }
      >
        <div className="import-workflow-content">
          {feedbackMessage ? <ImportNotice tone="success">{feedbackMessage}</ImportNotice> : null}
          {errorMessage ? <ImportNotice tone="danger">{errorMessage}</ImportNotice> : null}
          {confirmAuditMessage ? <ImportNotice tone="accent">{confirmAuditMessage}</ImportNotice> : null}
          {settingsLoading ? <ImportNotice tone="accent">正在加载银行账户映射...</ImportNotice> : null}
          {!settingsLoading && !canUseBankImport ? <ImportNotice tone="warning">设置里还没有银行账户映射，请先在设置中维护银行。</ImportNotice> : null}
          {mode === "etc_invoice" && readyEtcTasksLoading ? <ImportNotice tone="accent">正在加载可导入的 ETC 对账任务...</ImportNotice> : null}
          {mode === "etc_invoice" && !readyEtcTasksLoading && readyEtcTasks.length === 0 ? (
            <ImportNotice tone="warning">
              <div className="import-workflow-notice-stack">
                <p className="import-workflow-notice-strong">
                  当前没有已确认且可导入的 ETC 对账任务。导入页不能新建任务，请先在 ETC 对账页完成确认。
                </p>
                {unavailableEtcTasks.length > 0 ? (
                  <div className="import-workflow-notice-stack import-workflow-notice-stack--compact">
                    <p className="import-workflow-muted-text">
                      已找到 {unavailableEtcTasks.length} 个 ETC 对账任务，但当前不可导入：
                    </p>
                    {unavailableEtcTasks.slice(0, 5).map((task) => (
                      <div
                        key={task.taskId}
                        className="import-workflow-task-row"
                      >
                        <ImportChip>{`${task.title || "未命名任务"} / ${task.status}`}</ImportChip>
                        <span className="import-workflow-muted-text">{buildUnavailableEtcTaskReason(task)}</span>
                      </div>
                    ))}
                    {unavailableEtcTasks.length > 5 ? (
                      <p className="import-workflow-muted-text">
                        还有 {unavailableEtcTasks.length - 5} 个不可导入任务，请到 ETC 对账页处理。
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </ImportNotice>
          ) : null}
          {mode === "etc_invoice" && !readyEtcTasksLoading && readyEtcTasks.length > 0 && !selectedEtcTask ? (
            <ImportNotice tone="warning">请选择已确认的 ETC 对账任务后再预览 ETC zip。</ImportNotice>
          ) : null}
          {!canMutateData ? (
            <ImportNotice tone="accent">当前账号仅支持查看和导出，不能导入文件。</ImportNotice>
          ) : null}

          <div className="import-workflow-layout">
            <section className="import-workflow-panel">
              <div className="import-workflow-panel__content">
                <div className="import-workflow-panel__header">
                  <h2 className="import-workflow-panel__title">文件</h2>
                  <ImportChip>{`已选 ${selectedFiles.length}`}</ImportChip>
                </div>

                {mode === "etc_invoice" ? (
                  <div className="import-workflow-field-stack">
                    <ImportSelect
                      disabled={isPreviewing || isConfirming || readyEtcTasksLoading || readyEtcTasks.length === 0}
                      id="etc-reconciliation-task"
                      label="ETC对账任务"
                      onChange={handleEtcTaskChange}
                      value={selectedEtcTaskId}
                    >
                        <option aria-label="未选择ETC对账任务" value="" />
                        {readyEtcTasks.map((task) => (
                          <option key={task.taskId} value={task.taskId}>
                            {buildEtcTaskOptionLabel(task)}
                          </option>
                        ))}
                    </ImportSelect>
                    {selectedEtcTask ? (
                      <div aria-label="已选ETC对账任务" className="import-workflow-chip-row">
                        <ImportChip>{`任务 ${selectedEtcTask.title || selectedEtcTask.taskId}`}</ImportChip>
                        <ImportChip>{`ETC票 ${selectedEtcTask.etcInvoiceCount}`}</ImportChip>
                        <ImportChip>{`补充凭证 ${selectedEtcTask.supplementCount}`}</ImportChip>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                <label
                  className={`import-workflow-upload-zone${isDragActive ? " import-workflow-upload-zone--active" : ""}${!canMutateData || isPreviewing || isConfirming ? " import-workflow-upload-zone--disabled" : ""}`}
                  htmlFor={inputId}
                  aria-label={uploadLabel}
                  onDragEnter={handleDropzoneDragOver}
                  onDragOver={handleDropzoneDragOver}
                  onDragLeave={handleDropzoneDragLeave}
                  onDrop={handleDropzoneDrop}
                >
                  <UploadCloud aria-hidden="true" size={24} strokeWidth={2.2} />
                  <span className="import-workflow-upload-zone__title">{uploadLabel}</span>
                  <span className="import-workflow-upload-zone__description">
                    {mode === "etc_invoice" ? "支持 .zip" : "支持 .xls / .xlsx"}
                  </span>
                  <input
                    id={inputId}
                    multiple
                    type="file"
                    accept={mode === "etc_invoice" ? ".zip,application/zip" : ".xlsx,.xls"}
                    disabled={!canMutateData || isPreviewing || isConfirming}
                    onChange={(event) => {
                      setIsDragActive(false);
                      applyDroppedFiles(Array.from(event.currentTarget.files ?? []));
                      event.currentTarget.value = "";
                    }}
                    className="import-workflow-upload-zone__input"
                  />
                </label>

                {selectedFiles.length > 0 ? (
                  <div className="import-workflow-file-list" aria-label="待导入文件">
                    {selectedFiles.map((file) => {
                      const key = buildSelectedFileKey(file);
                      const selection = fileSelections[key] ?? {
                        bankMappingId: "",
                        bankName: "",
                        bankShortName: "",
                        last4: "",
                        invoiceBatchType: "",
                      };

                      return (
                        <div key={key} className="import-workflow-file-card">
                          <div className="import-workflow-file-card__content">
                            <div className="import-workflow-file-card__header">
                              <div className="import-workflow-file-card__identity">
                                <div className="import-workflow-file-card__name" title={file.name}>{file.name}</div>
                                <div className="import-workflow-muted-text">{formatFileSize(file)}</div>
                              </div>
                              <Button
                                className="import-workflow-file-card__remove"
                                isDisabled={isPreviewing || isConfirming}
                                onPress={() => handleRemoveFile(file)}
                                size="sm"
                                type="button"
                                variant="danger"
                              >
                                <Trash2 aria-hidden="true" size={14} strokeWidth={2.2} />
                                移除
                              </Button>
                            </div>

                            {mode === "bank_transaction" ? (
                              <ImportSelect
                                disabled={isPreviewing || isConfirming || bankOptions.length === 0}
                                id={`${key}-bank`}
                                label={`对应账户 ${file.name}`}
                                onChange={(value) => handleSelectionChange(file, "bankMappingId", value)}
                                value={selection.bankMappingId}
                              >
                                  <option aria-label="未选择账户" value="" />
                                  {bankOptions.map((bankOption) => (
                                    <option key={bankOption.id} value={bankOption.id}>
                                      {buildBankAccountOptionLabel(bankOption)}
                                    </option>
                                  ))}
                              </ImportSelect>
                            ) : mode === "invoice" ? (
                              <ImportSelect
                                disabled={isPreviewing || isConfirming}
                                id={`${key}-invoice`}
                                label={`票据方向 ${file.name}`}
                                onChange={(value) => handleSelectionChange(file, "invoiceBatchType", value)}
                                value={selection.invoiceBatchType}
                              >
                                  <option aria-label="未选择票据方向" value="" />
                                  <option value="input_invoice">进项发票</option>
                                  <option value="output_invoice">销项发票</option>
                              </ImportSelect>
                            ) : (
                              <div className="import-workflow-chip-row">
                                <ImportChip>ETC zip</ImportChip>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <ImportNotice tone="accent">当前还没有选择文件。</ImportNotice>
                )}
              </div>
            </section>

            <section className="import-workflow-panel">
              <div className="import-workflow-panel__content">
                <div className="import-workflow-panel__header">
                  <h2 className="import-workflow-panel__title">预览</h2>
                  {isPreviewing || isConfirming ? (
                    <ImportChip color="accent">{isPreviewing ? "预览中" : "确认中"}</ImportChip>
                  ) : null}
                </div>

                {mode === "etc_invoice" ? (
                  <div className="import-workflow-preview-stack">
                    {etcPreviewPayload ? (
                      <div className="import-workflow-preview-heading">
                        <h3 className="import-workflow-preview-title">ETC导入预览</h3>
                        <ImportChip>{etcPreviewPayload.sessionId}</ImportChip>
                      </div>
                    ) : null}
                    <AuditSummaryCards audit={etcPreviewAudit} />
                    {etcPreviewPayload ? (
                      <div className="import-workflow-chip-row">
                        <ImportChip color="success">{`本次导入新增 ${etcPreviewPayload.imported}`}</ImportChip>
                        <ImportChip>{`本次重复跳过 ${etcPreviewPayload.duplicatesSkipped}`}</ImportChip>
                        <ImportChip color="accent">{`本次附件补齐 ${etcPreviewPayload.attachmentsCompleted}`}</ImportChip>
                        <ImportChip color={etcPreviewPayload.failed > 0 ? "warning" : "default"}>{`异常 ${etcPreviewPayload.failed}`}</ImportChip>
                      </div>
                    ) : null}
                    {missingEtcRequirementIssues.length > 0 ? (
                      <ImportNotice ariaLabel="ETC对账任务缺失项" tone="warning">
                        <div className="import-workflow-notice-stack">
                          <p className="import-workflow-notice-strong">ETC对账任务缺失项</p>
                          <div className="import-workflow-notice-stack import-workflow-notice-stack--compact">
                            {missingEtcRequirementIssues.map((issue) => (
                              <div
                                key={issue.requirementId || formatMissingRequirementLine(issue)}
                                className="import-workflow-issue-card"
                              >
                                <div className="import-workflow-chip-row">
                                  <ImportChip color="warning">{displayValue(issue.transactionAt || issue.transactionDate)}</ImportChip>
                                  <ImportChip>{formatMoney(issue.amount, "--")}</ImportChip>
                                  <ImportChip>{displayValue(issue.vehiclePlate)}</ImportChip>
                                  {issue.invoiceCount ? <ImportChip>{`${issue.invoiceCount} 张`}</ImportChip> : null}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </ImportNotice>
                    ) : null}
                    {etcBlockingIssues.length > 0 && missingEtcRequirementIssues.length === 0 ? (
                      <ImportNotice tone="warning">ETC 对账任务仍有 {etcBlockingIssues.length} 个阻塞项，请处理后重新预览。</ImportNotice>
                    ) : null}
                    <div className="import-workflow-grid-shell import-workflow-grid-shell--etc">
                      <EtcPreviewTable loading={isPreviewing} rows={etcRows} />
                    </div>
                  </div>
                ) : (
                  <div className="import-workflow-preview-stack">
                    <AuditSummaryCards audit={previewAudit} />
                    <div className="import-workflow-grid-shell import-workflow-grid-shell--preview">
                      <ImportPreviewTable loading={isPreviewing} rows={previewRows} />
                    </div>
                    {mappingRequiredFiles.map((file) => {
                      const values = { ...file.fieldMapping, ...(mappingDrafts[file.id] ?? {}) };
                      return (
                        <section key={file.id} aria-label={`${file.fileName} 字段映射`} className="import-workflow-mapping-panel">
                          <div className="import-workflow-mapping-panel__header">
                            <div>
                              <h3 className="import-workflow-preview-title">字段映射</h3>
                              <p className="import-workflow-muted-text">{file.fileName} · {file.message}</p>
                            </div>
                            <Button
                              isDisabled={mappingRetryingFileId !== null}
                              onPress={() => { void handleApplyFieldMapping(file); }}
                              size="sm"
                              type="button"
                            >
                              {mappingRetryingFileId === file.id ? "解析中..." : "保存并重新解析"}
                            </Button>
                          </div>
                          <div className="import-workflow-mapping-grid">
                            {file.mappingFields.map((field) => (
                              <label key={field.key} className="import-workflow-mapping-field">
                                <span>{field.label}{field.required ? " *" : ""}</span>
                                <Select
                                  aria-label={`${field.label}源列`}
                                  onSelectionChange={(key) => {
                                    setMappingDrafts((current) => ({
                                      ...current,
                                      [file.id]: {
                                        ...file.fieldMapping,
                                        ...(current[file.id] ?? {}),
                                        [field.key]: String(key),
                                      },
                                    }));
                                  }}
                                  selectedKey={values[field.key] ?? ""}
                                >
                                  <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
                                  <Select.Popover>
                                    <ListBox>
                                      {file.mappingCandidates.map((candidate) => (
                                        <ListBox.Item id={candidate.key} key={candidate.key} textValue={candidate.label}>
                                          {candidate.label}
                                        </ListBox.Item>
                                      ))}
                                    </ListBox>
                                  </Select.Popover>
                                </Select>
                              </label>
                            ))}
                          </div>
                        </section>
                      );
                    })}
                    <div className="import-workflow-detail-shell">
                      <Tabs
                        className="import-workflow-detail-tabs-root"
                        onSelectionChange={(key) => {
                          setPreviewDetailTab(key as "duplicates" | "unimported");
                          setPreviewDetailOffset(0);
                          setPreviewDetailPage(null);
                        }}
                        selectedKey={previewDetailTab}
                        variant="secondary"
                      >
                        <Tabs.ListContainer className="import-workflow-detail-tabs-container">
                          <Tabs.List aria-label="导入预览明细" className="import-workflow-detail-tabs">
                            <Tabs.Tab id="duplicates">
                              重复项 {previewAudit?.duplicateCount ?? 0}
                              <Tabs.Indicator />
                            </Tabs.Tab>
                            <Tabs.Tab id="unimported">
                              未导入项 {previewAudit?.skippedCount ?? 0}
                              <Tabs.Indicator />
                            </Tabs.Tab>
                          </Tabs.List>
                        </Tabs.ListContainer>
                      </Tabs>
                      {previewDetailError ? <ImportNotice tone="danger">{previewDetailError}</ImportNotice> : null}
                      <div className="import-workflow-grid-shell import-workflow-grid-shell--detail">
                        <ImportPreviewDetailTable
                          ariaLabel={previewDetailTab === "duplicates" ? "重复项明细" : "未导入项明细"}
                          invoiceMode={mode === "invoice"}
                          loading={previewDetailLoading}
                          onPageChange={(page) => setPreviewDetailOffset((page - 1) * previewDetailPageSize)}
                          page={Math.floor(previewDetailOffset / previewDetailPageSize) + 1}
                          pageSize={previewDetailPageSize}
                          rows={previewDetailRows}
                          total={previewDetailTotal}
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </section>
          </div>
        </div>
      </PageScaffold>

      <AppDialog
        maxWidth="sm"
        onClose={() => setConflictDialogOpen(false)}
        open={conflictDialogOpen}
        title="银行账户冲突确认"
        actions={(
          <>
            <Button isDisabled={isConfirming} onPress={() => setConflictDialogOpen(false)} type="button" variant="secondary">取消</Button>
            <Button
              isDisabled={isConfirming || healthStatus.blocksMutations}
              onPress={() => { void submitConfirm(); }}
              type="button"
            >
              {isConfirming ? "确认中..." : conflictConfirmLabel}
            </Button>
          </>
        )}
      >
          <div className="import-workflow-dialog-stack">
            <ImportNotice tone="warning">以下文件的系统识别结果与所选账户不一致，确认后仍会按你选择的账户导入。</ImportNotice>
            {conflictingPreviewFiles.map((file) => (
              <div key={file.id} className="import-workflow-conflict-card">
                <div className="import-workflow-conflict-card__title">{file.fileName}</div>
                <p className="import-workflow-muted-text">
                  所选：{`${file.selectedBankName ?? "--"} ${file.selectedBankLast4 ?? "--"}`} / 识别：{`${file.detectedBankName ?? "--"} ${file.detectedLast4 ?? "--"}`}
                </p>
                {file.conflictMessage ? <p className="import-workflow-conflict-card__message">{file.conflictMessage}</p> : null}
              </div>
            ))}
          </div>
      </AppDialog>
    </div>
  );
}
