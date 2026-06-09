import {
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  Plus,
  RefreshCw,
  Trash2,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { Button, Chip, Disclosure, DisclosureGroup, ToggleButton, ToggleButtonGroup } from "@heroui/react";
import type { Key } from "@heroui/react";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type DragEvent, type MouseEvent, type ReactNode } from "react";
import { Link as RouterLink } from "react-router-dom";

import AppDialog from "../components/common/AppDialog";
import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import { useBackgroundJobProgress } from "../features/backgroundJobs/BackgroundJobProgressProvider";
import { FINANCE_DOMAIN_EVENTS, emitFinanceDomainEvent } from "../features/domainEvents";
import {
  confirmEtcReconciliationTask,
  createEtcBusinessBatchOaDraft,
  createEtcReconciliationTask,
  deleteEtcBusinessBatch,
  deleteEtcBatch,
  deleteEtcReconciliationTask,
  deleteEtcReconciliationTaskImportedInvoices,
  deleteEtcReconciliationSourceFile,
  fetchEtcBusinessBatchDetail,
  fetchEtcBusinessBatches,
  fetchEtcBatchDetail,
  fetchEtcBatches,
  fetchEtcReconciliationTask,
  manualEtcBusinessBatchOaStatus,
  fetchEtcReconciliationTasks,
  patchEtcReconciliationItem,
  refreshEtcReconciliationMatches,
  reopenEtcReconciliationTask,
  uploadEtcCreditCardStatement,
  uploadEtcSupplementEvidenceForCard,
  uploadEtcTicketRootFiles,
} from "../features/etc/api";
import { buildEtcOaDraftReviewUrl } from "../features/etc/oaNavigation";
import type {
  EtcBatchCounts,
  EtcBatchDetail,
  EtcBatchStatus,
  EtcBatchSummary,
  EtcBusinessBatchDetail,
  EtcBusinessBatchStatus,
  EtcBusinessBatchSummary,
  EtcCreditCardItem,
  EtcInvoice,
  EtcOaDraftPayload,
  EtcReconciliationTask,
  EtcSourceFile,
  EtcSupplementEvidence,
  EtcTicketRootItem,
} from "../features/etc/types";

const initialCounts: EtcBatchCounts = {
  unsubmitted: 0,
  submitted: 0,
};

const MANUAL_OA_SUBMITTED_REASON = "用户确认 OA 草稿已提交。";
const MANUAL_OA_NOT_SUBMITTED_REASON = "用户确认 OA 草稿未提交。";

function formatMoney(value: string | number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return String(value);
  }
  return parsed.toFixed(2);
}

function sumInvoiceTotalAmount(items: EtcInvoice[]) {
  const totalCents = items.reduce((sum, item) => {
    const parsed = Number(item.totalAmount);
    return Number.isFinite(parsed) ? sum + Math.round(parsed * 100) : sum;
  }, 0);
  return (totalCents / 100).toFixed(2);
}

function formatDateRange(startDate: string | null, endDate: string | null) {
  if (!startDate && !endDate) {
    return "-";
  }
  if (!endDate || startDate === endDate) {
    return startDate ?? endDate ?? "-";
  }
  if (!startDate) {
    return endDate;
  }
  return `${startDate} 至 ${endDate}`;
}

function splitDateParts(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  const [datePart] = value.split("T");
  const [year, month, day] = datePart.split("-");
  if (!year || !month || !day) {
    return datePart || "-";
  }
  return `${year}-${month}-${day}`;
}

function splitDateTimeParts(value: string | null | undefined) {
  if (!value) {
    return { date: "-", time: "" };
  }
  const [date = "-", rawTime = ""] = value.split("T");
  const time = rawTime.split(/[.+-]/)[0] ?? "";
  return { date: date || "-", time };
}

function formatShortDateRange(startDate: string | null, endDate: string | null) {
  const compact = (value: string | null) => {
    if (!value) {
      return "";
    }
    const [, month = "", day = ""] = value.split("-");
    return month && day ? `${Number(month)}.${Number(day)}` : value;
  };
  const start = compact(startDate);
  const end = compact(endDate);
  if (!start && !end) {
    return "未记录日期";
  }
  if (!end || start === end) {
    return start || end;
  }
  return `${start}-${end}`;
}

function datePart(value: string | null | undefined) {
  if (!value) {
    return null;
  }
  const [date] = value.trim().split(/[T\s]/);
  return date || null;
}

function ticketRootSourceSummary(items: EtcTicketRootItem[]) {
  const plates = Array.from(new Set(items.map((item) => item.vehiclePlate).filter(Boolean)));
  const dates = items.map((item) => datePart(item.transactionAt)).filter((item): item is string => Boolean(item)).sort();
  const totalAmount = items.reduce((sum, item) => {
    const parsed = Number(item.amount);
    return Number.isFinite(parsed) ? sum + parsed : sum;
  }, 0);
  return {
    parsedCount: items.length,
    plateLabel: plates.length > 0 ? plates.join(" / ") : "未识别车牌",
    totalAmount: totalAmount.toFixed(2),
    dateRange: formatDateRange(dates[0] ?? null, dates[dates.length - 1] ?? null),
  };
}

function attachmentLabel(invoice: EtcInvoice) {
  if (invoice.hasPdf && invoice.hasXml) {
    return "PDF/XML完整";
  }
  if (!invoice.hasPdf && !invoice.hasXml) {
    return "缺PDF/XML";
  }
  return invoice.hasPdf ? "缺XML" : "缺PDF";
}

function batchStatusLabel(status: EtcBatchStatus) {
  const labels: Record<EtcBatchStatus, string> = {
    unsubmitted: "未提交",
    draft_creating: "草稿创建中",
    draft_created: "OA草稿已创建",
    not_submitted: "未提交OA",
    failed: "创建失败",
    submitted: "已提交",
  };
  return labels[status] ?? status;
}

function businessBatchStatusLabel(status: EtcBusinessBatchStatus) {
  const labels: Partial<Record<EtcBusinessBatchStatus, string>> = {
    draft: "草稿",
    reviewing: "核对中",
    ready_for_import: "待导入",
    importing: "导入中",
    imported: "已导入",
    import_failed: "导入失败",
    import_partial_failed: "部分导入失败",
    oa_draft_creating: "草稿创建中",
    oa_draft_failed: "草稿创建失败",
    oa_confirmation_pending: "待确认OA状态",
    oa_submitted: "OA已提交",
    not_submitted: "未提交OA",
    manually_marked_submitted: "人工确认已提交",
    manually_marked_not_submitted: "人工确认未提交",
    migration_conflict: "迁移冲突",
    business_batch_invariant_broken: "批次异常",
    closed: "已关闭",
    deleted: "已删除",
    superseded: "已替代",
  };
  return labels[status] ?? status;
}

function businessBatchTone(status: EtcBusinessBatchStatus): "default" | "primary" | "success" | "warning" | "error" {
  if (status === "oa_submitted" || status === "manually_marked_submitted" || status === "closed") {
    return "success";
  }
  if (status === "oa_draft_failed" || status === "import_failed" || status === "import_partial_failed") {
    return "warning";
  }
  if (status === "migration_conflict" || status === "business_batch_invariant_broken") {
    return "error";
  }
  return "primary";
}

function chipColorFromTone(tone: "default" | "primary" | "success" | "warning" | "error") {
  if (tone === "primary") {
    return "accent";
  }
  if (tone === "error") {
    return "danger";
  }
  if (tone === "success" || tone === "warning") {
    return tone;
  }
  return "default";
}

function statusTagClass(tone: "default" | "primary" | "success" | "warning" | "error" = "primary") {
  return `etc-status-tag etc-status-tag--${tone}`;
}

function CountChip({ children }: { children: ReactNode }) {
  return (
    <Chip className="etc-count-tag" color="accent" size="sm" variant="soft">
      <Chip.Label>{children}</Chip.Label>
    </Chip>
  );
}

function StatusChip({
  children,
  tone = "primary",
}: {
  children: ReactNode;
  tone?: "default" | "primary" | "success" | "warning" | "error";
}) {
  return (
    <Chip className={statusTagClass(tone)} color={chipColorFromTone(tone)} size="sm" variant="soft">
      <Chip.Label>{children}</Chip.Label>
    </Chip>
  );
}

function isSubmittedBusinessStatus(status: EtcBusinessBatchStatus) {
  return status === "oa_submitted" || status === "manually_marked_submitted" || status === "closed";
}

function businessBatchListBucket(status: EtcBusinessBatchStatus): "unsubmitted" | "submitted" | null {
  if (isSubmittedBusinessStatus(status)) {
    return "submitted";
  }
  if (status === "deleted" || status === "superseded") {
    return null;
  }
  return "unsubmitted";
}

function businessBatchBelongsToBatchStatus(status: EtcBusinessBatchStatus, activeStatus: EtcBatchStatus) {
  const bucket = businessBatchListBucket(status);
  const currentBucket = activeStatus === "submitted" ? "submitted" : "unsubmitted";
  return bucket === currentBucket;
}

function transitionBusinessBatchCounts(
  counts: EtcBatchCounts,
  previousStatus: EtcBusinessBatchStatus | null,
  nextStatus: EtcBusinessBatchStatus,
): EtcBatchCounts {
  const previousBucket = previousStatus ? businessBatchListBucket(previousStatus) : null;
  const nextBucket = businessBatchListBucket(nextStatus);
  if (previousBucket === nextBucket) {
    return counts;
  }
  const nextCounts = { ...counts };
  if (previousBucket === "submitted") {
    nextCounts.submitted = Math.max(0, nextCounts.submitted - 1);
  } else if (previousBucket === "unsubmitted") {
    nextCounts.unsubmitted = Math.max(0, nextCounts.unsubmitted - 1);
  }
  if (nextBucket === "submitted") {
    nextCounts.submitted += 1;
  } else if (nextBucket === "unsubmitted") {
    nextCounts.unsubmitted += 1;
  }
  return nextCounts;
}

function isOaConfirmationPendingStatus(status: EtcBusinessBatchStatus) {
  return status === "oa_confirmation_pending";
}

function canCreateOaDraft(status: EtcBusinessBatchStatus) {
  return status === "imported" || status === "oa_draft_failed" || status === "not_submitted" || status === "manually_marked_not_submitted";
}

function batchOaLabel(batch: EtcBatchSummary) {
  const parts = [
    batch.linkedOaApplicant,
    batch.linkedOaApplyDate,
    batch.linkedOaAmount ? `OA ${formatMoney(batch.linkedOaAmount)}` : "",
  ].filter(Boolean);
  return parts.join(" / ");
}

function reconciliationStatusLabel(status: EtcReconciliationTask["status"]) {
  const labels: Record<string, string> = {
    draft: "草稿",
    reviewing: "核对中",
    ready_for_import: "已确认",
    importing: "导入中",
    imported: "已导入",
    closed: "已关闭",
  };
  return labels[status] ?? status;
}

function sourceKindLabel(sourceKind: string) {
  const labels: Record<string, string> = {
    credit_card_statement: "信用卡账单",
    ticket_root: "票根网",
    supplement_evidence: "补充凭证",
  };
  return labels[sourceKind] ?? (sourceKind || "未知类型");
}

function isManualTicketRootSource(sourceFile: EtcSourceFile) {
  return sourceFile.sourceKind === "ticket_root" && sourceFile.originalName.startsWith("票根网手工粘贴-");
}

function isTextFileTicketRootSource(sourceFile: EtcSourceFile) {
  return sourceFile.sourceKind === "ticket_root"
    && (sourceFile.contentType ?? "").toLowerCase().startsWith("text/plain")
    && !isManualTicketRootSource(sourceFile);
}

function isDocumentTicketRootSource(sourceFile: EtcSourceFile) {
  return sourceFile.sourceKind === "ticket_root"
    && !isManualTicketRootSource(sourceFile)
    && !isTextFileTicketRootSource(sourceFile);
}

function parseIssueContextLabel(issue: Pick<EtcReconciliationTask["parseIssues"][number], "sourcePage" | "sourceLine" | "extractionMethod">) {
  const parts = [];
  if (issue.sourcePage !== null) {
    parts.push(`第 ${issue.sourcePage} 页`);
  }
  if (issue.sourceLine !== null) {
    parts.push(`第 ${issue.sourceLine} 行`);
  }
  if (issue.extractionMethod) {
    parts.push(issue.extractionMethod);
  }
  return parts.join(" / ");
}

function recommendationHighlight(status: string) {
  if (status === "missing_ticket") {
    return "missing";
  }
  if (status === "suggested_match") {
    return "suggested";
  }
  if (status === "extra_ticket" || status === "unmatched") {
    return "extra";
  }
  return status;
}

function manualHighlight(resolution: string) {
  if (resolution === "covered_by_supplement") {
    return "covered";
  }
  return "";
}

function formatTaskTitle(task: EtcReconciliationTask) {
  const title = (task.title || "").trim()
    .replace(/ETC\s*对账批次/g, "ETC批次")
    .replace(/ETC\s*对账/g, "ETC批次")
    .replace(/对账任务/g, "批次");
  return title || "ETC批次";
}

function formatEtcUiErrorMessage(error: unknown, fallback: string) {
  const message = error instanceof Error ? error.message : fallback;
  return message
    .replace(/ETC对账任务/g, "ETC批次流程")
    .replace(/对账任务/g, "批次");
}

function taskCountText(task: Pick<EtcReconciliationTask, "etcInvoiceCount" | "supplementCount">) {
  return `ETC票 ${task.etcInvoiceCount} + 补充凭证 ${task.supplementCount}`;
}

function taskHasSubmittedConfirmation(task: Pick<EtcReconciliationTask, "status" | "submittedConfirmedAt">) {
  return task.status === "closed" || Boolean(task.submittedConfirmedAt?.trim());
}

function taskCanAppearAsStandaloneBatch(task: EtcReconciliationTask) {
  return !taskHasSubmittedConfirmation(task);
}

function isBusinessBatchSource(batch: EtcBatchSummary) {
  return batch.sourceType === "business_batch" || batch.sourceType === "etc_business_batch";
}

function isEtcBusinessBatchNotFoundError(error: unknown, batchId?: string) {
  const message = error instanceof Error ? error.message : "";
  const code = typeof (error as { code?: unknown } | null)?.code === "string"
    ? (error as { code: string }).code
    : "";
  const status = typeof (error as { status?: unknown } | null)?.status === "number"
    ? (error as { status: number }).status
    : 0;
  if (code === "business_batch_not_found") {
    return true;
  }
  if (status === 404 && batchId && message.includes(batchId)) {
    return true;
  }
  return /ETC business batch not found:/i.test(message);
}

function emitEtcBusinessDomainUpdated(detail: { affectedMonths?: string[]; source: string }) {
  emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.etcBusinessBatchUpdated, detail);
  emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.invoiceFactUpdated, detail);
}

type UploadBlockProps = {
  label: string;
  accept: string;
  disabled: boolean;
  helperText: string;
  disabledReason?: string;
  multiple?: boolean;
  onFiles: (files: File[]) => void;
};

function UploadBlock({ label, accept, disabled, helperText, disabledReason, multiple = false, onFiles }: UploadBlockProps) {
  const [dragActive, setDragActive] = useState(false);
  const handleFiles = (files: File[]) => {
    if (disabled || files.length === 0) {
      return;
    }
    onFiles(files);
  };
  const handleDrag = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!disabled) {
      setDragActive(event.type === "dragenter" || event.type === "dragover");
    }
  };
  const handleDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setDragActive(false);
    handleFiles(Array.from(event.dataTransfer.files ?? []));
  };

  return (
    <label
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label={`上传${label}`}
      aria-disabled={disabled ? "true" : undefined}
      className={`etc-upload-drop-box${dragActive ? " dragging" : ""}`}
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
    >
      <UploadCloud aria-hidden="true" size={18} />
      <span className="etc-upload-drop-content">
        <strong>{label}</strong>
        <span>{helperText}</span>
        {disabled && disabledReason ? (
          <span className="etc-upload-drop-disabled-reason">{disabledReason}</span>
        ) : null}
      </span>
      <input
        hidden
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          event.target.value = "";
          handleFiles(files);
        }}
      />
    </label>
  );
}

type EtcDisclosureSectionProps = {
  id: string;
  title: string;
  summary?: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
};

function EtcDisclosureSection({ id, title, summary, meta, children, className }: EtcDisclosureSectionProps) {
  return (
    <Disclosure id={id} className={["etc-disclosure-section", className ?? ""].filter(Boolean).join(" ")}>
      <Disclosure.Heading>
        <Button slot="trigger" className="etc-disclosure-trigger" fullWidth size="sm" variant="tertiary">
          <span className="etc-disclosure-title-block">
            <span className="etc-disclosure-title">{title}</span>
            {summary ? <span className="etc-disclosure-summary">{summary}</span> : null}
          </span>
          <span className="etc-disclosure-meta">
            {meta}
            <Disclosure.Indicator className="etc-disclosure-indicator" />
          </span>
        </Button>
      </Disclosure.Heading>
      <Disclosure.Content>
        <Disclosure.Body className="etc-disclosure-body">
          {children}
        </Disclosure.Body>
      </Disclosure.Content>
    </Disclosure>
  );
}

type EvidenceRow = {
  id: string;
  source: "ticket" | "supplement";
  transactionTime: string;
  fallbackTimeLabel: string;
  plateOrMerchant: string;
  amount: string;
  invoiceCount: number;
  highlight: string;
  tags: string[];
};

type ReconciliationRow = {
  id: string;
  card: EtcCreditCardItem | null;
  evidence: EvidenceRow | null;
  highlight: string;
  cardHighlight: string;
  evidenceHighlight: string;
};

type ReconciliationSelectionSummary = {
  creditCardItemIds: string[];
  oaTotalAmount: string;
  periodStart: string | null;
  periodEnd: string | null;
  etcInvoiceCount: number;
  supplementCount: number;
};

type BatchDeletePlan =
  | { kind: "businessBatch"; batchId: string; expectedVersion?: number }
  | { kind: "legacyBatch"; batchId: string };

type DeleteTarget =
  | { kind: "batch"; item: EtcBatchSummary; plan: BatchDeletePlan }
  | { kind: "task"; item: EtcReconciliationTask }
  | { kind: "sourceFile"; task: EtcReconciliationTask; item: EtcSourceFile };

function businessBatchToBatchSummary(batch: EtcBusinessBatchSummary): EtcBatchSummary {
  const submitted = isSubmittedBusinessStatus(batch.status);
  return {
    id: batch.businessBatchId,
    etcBatchId: batch.externalEtcBatchId || batch.businessBatchId,
    externalBatchId: batch.externalEtcBatchId || batch.businessBatchId,
    status: submitted ? "submitted" : "unsubmitted",
    sourceType: "business_batch",
    invoiceCount: batch.invoiceSummary.count,
    totalAmount: batch.invoiceSummary.amount,
    taxAmount: "0.00",
    issueStartDate: null,
    issueEndDate: null,
    passageStartDate: null,
    passageEndDate: null,
    plateCount: 0,
    plateSummary: [],
    linkedOaRowId: batch.oaRowId,
    linkedOaCaseId: batch.oaRowId,
    linkedOaApplicant: "",
    linkedOaApplyDate: "",
    linkedOaAmount: batch.invoiceSummary.amount,
    amountDelta: "0.00",
    etcInvoiceCount: batch.invoiceSummary.count,
    supplementCount: 0,
    supplementAmount: "0.00",
    displayCountText: `ETC票 ${batch.invoiceSummary.count} + 补充凭证 0`,
    note: businessBatchStatusLabel(batch.status),
  };
}

function businessBatchToBatchDetail(batch: EtcBusinessBatchDetail): EtcBatchDetail {
  return {
    ...businessBatchToBatchSummary(batch),
    invoiceItems: batch.invoiceItems,
  };
}

function reconciliationTaskToBatchSummary(task: EtcReconciliationTask): EtcBatchSummary {
  const invoiceCount = task.importedInvoiceCount > 0 ? task.importedInvoiceCount : task.etcInvoiceCount;
  const totalAmount = Number(task.oaTotalAmount) > 0
    ? task.oaTotalAmount
    : Number(task.importedInvoiceAmount) > 0
      ? task.importedInvoiceAmount
      : task.etcInvoiceAmount;
  const plateSummary = task.vehiclePlates.map((plateNumber) => ({
    plateNumber,
    invoiceCount: 0,
    totalAmount: "0.00",
  }));
  return {
    id: task.taskId,
    etcBatchId: formatTaskTitle(task),
    externalBatchId: formatTaskTitle(task),
    status: task.status === "closed" ? "submitted" : "unsubmitted",
    sourceType: "reconciliation_task",
    invoiceCount,
    totalAmount: totalAmount || "0.00",
    taxAmount: "0.00",
    issueStartDate: task.periodStart,
    issueEndDate: task.periodEnd,
    passageStartDate: task.periodStart,
    passageEndDate: task.periodEnd,
    plateCount: task.vehiclePlates.length,
    plateSummary,
    linkedOaRowId: "",
    linkedOaCaseId: "",
    linkedOaApplicant: "",
    linkedOaApplyDate: "",
    linkedOaAmount: task.oaTotalAmount,
    amountDelta: task.approvedDelta,
    etcInvoiceCount: task.etcInvoiceCount,
    supplementCount: task.supplementCount,
    supplementAmount: task.supplementAmount,
    displayCountText: taskCountText(task),
    note: reconciliationStatusLabel(task.status),
  };
}

const DESCRIPTION_EXPANSION_UNITS = 12;

function estimatedDescriptionUnits(text: string) {
  return Array.from(text).reduce((sum, char) => sum + (char.charCodeAt(0) > 255 ? 1 : 0.55), 0);
}

function ReconciliationDescriptionCell({
  cardId,
  description,
  expanded,
  onToggle,
}: {
  cardId: string;
  description: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  const textRef = useRef<HTMLSpanElement | null>(null);
  const [measuredOverflow, setMeasuredOverflow] = useState(false);
  const text = description || "-";

  useEffect(() => {
    const element = textRef.current;
    if (!element) {
      return undefined;
    }

    const measure = () => {
      setMeasuredOverflow(element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1);
    };

    measure();
    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(measure);
      observer.observe(element);
      return () => observer.disconnect();
    }
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [text, expanded]);

  const canExpand = expanded || measuredOverflow || estimatedDescriptionUnits(text) > DESCRIPTION_EXPANSION_UNITS;

  return (
    <span className="etc-reconciliation-description-cell">
      <span
        ref={textRef}
        title={text}
        data-testid={`etc-reconciliation-description-${cardId}`}
        className={`etc-reconciliation-description ${expanded ? "etc-reconciliation-description--expanded" : "etc-reconciliation-description--collapsed"}`}
      >
        {text}
      </span>
      {canExpand ? (
        <button
          type="button"
          className="etc-reconciliation-description-toggle"
          aria-label={`${expanded ? "收起" : "展开"}交易描述 ${cardId}`}
          onClick={(event) => {
            event.stopPropagation();
            onToggle();
          }}
        >
          {expanded ? "收起" : "展开"}
        </button>
      ) : null}
    </span>
  );
}

export default function EtcTicketManagementPage() {
  const { jobs } = useBackgroundJobProgress();
  const [activeStatus, setActiveStatus] = useState<EtcBatchStatus>("unsubmitted");
  const [month, setMonth] = useState("");
  const [plate, setPlate] = useState("");
  const [keyword, setKeyword] = useState("");
  const [counts, setCounts] = useState(initialCounts);
  const [batches, setBatches] = useState<EtcBatchSummary[]>([]);
  const [businessBatches, setBusinessBatches] = useState<EtcBusinessBatchSummary[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [batchDetail, setBatchDetail] = useState<EtcBatchDetail | null>(null);
  const [businessBatchDetail, setBusinessBatchDetail] = useState<EtcBusinessBatchDetail | null>(null);
  const [taskImportBatchDetail, setTaskImportBatchDetail] = useState<EtcBatchDetail | null>(null);
  const [reconciliationTasks, setReconciliationTasks] = useState<EtcReconciliationTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [selectedCardItemId, setSelectedCardItemId] = useState("");
  const [selectedEvidenceRowId, setSelectedEvidenceRowId] = useState("");
  const [selectedReconciliationRowIds, setSelectedReconciliationRowIds] = useState<Set<string>>(() => new Set());
  const [expandedDescriptionRowIds, setExpandedDescriptionRowIds] = useState<Set<string>>(() => new Set());
  const [reviewNote, setReviewNote] = useState("");
  const [supplementUploadCard, setSupplementUploadCard] = useState<EtcCreditCardItem | null>(null);
  const [supplementUploadFiles, setSupplementUploadFiles] = useState<File[]>([]);
  const [supplementUploadNote, setSupplementUploadNote] = useState("");
  const [supplementUploadSubmitting, setSupplementUploadSubmitting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [taskLoading, setTaskLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [taskImportDetailLoading, setTaskImportDetailLoading] = useState(false);
  const [taskImportDetailError, setTaskImportDetailError] = useState<string | null>(null);
  const [batchListError, setBatchListError] = useState<string | null>(null);
  const [taskListError, setTaskListError] = useState<string | null>(null);
  const [batchDetailError, setBatchDetailError] = useState<string | null>(null);
  const [taskActionLoading, setTaskActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [workflowExpandedKeys, setWorkflowExpandedKeys] = useState<Set<Key>>(() => new Set(["upload", "reconciliation"]));
  const [batchDetailExpandedKeys, setBatchDetailExpandedKeys] = useState<Set<Key>>(() => new Set(["summary", "invoices"]));
  const [locallySubmittedTaskIds, setLocallySubmittedTaskIds] = useState<Set<string>>(() => new Set());
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [removeImportedInvoicesDialogOpen, setRemoveImportedInvoicesDialogOpen] = useState(false);
  const [removeImportedInvoicesSubmitting, setRemoveImportedInvoicesSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [draftCreating, setDraftCreating] = useState(false);
  const [draftResult, setDraftResult] = useState<EtcOaDraftPayload | null>(null);
  const [oaActionLoading, setOaActionLoading] = useState(false);
  const refreshedImportJobIdsRef = useRef<Set<string>>(new Set());

  const loadBatches = useCallback(async (
    signal?: AbortSignal,
    statusOverride?: "unsubmitted" | "submitted",
  ) => {
    setLoading(true);
    setBatchListError(null);
    setActionError(null);
    const effectiveStatus = statusOverride ?? activeStatus;
    try {
      const payload = await fetchEtcBusinessBatches({
        status: effectiveStatus === "submitted" ? "submitted" : "active",
        month,
        plate: plate.trim(),
        keyword: keyword.trim(),
        signal,
      });
      setBusinessBatches(payload.items);
      const visibleItems = payload.items.map(businessBatchToBatchSummary);
      setCounts({ unsubmitted: payload.counts.active, submitted: payload.counts.submitted });
      setBatches(visibleItems);
      setSelectedBatchId((current) => {
        if (payload.items.some((batch) => batch.businessBatchId === current)) {
          return current;
        }
        return payload.items[0]?.businessBatchId ?? "";
      });
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setBatchListError(formatEtcUiErrorMessage(caught, "ETC业务批次加载失败。"));
      }
    } finally {
      setLoading(false);
    }
  }, [activeStatus, keyword, month, plate]);

  const loadReconciliationTasks = useCallback(async (signal?: AbortSignal) => {
    setTaskLoading(true);
    setTaskListError(null);
    try {
      const payload = await fetchEtcReconciliationTasks(signal);
      setReconciliationTasks(payload.items);
      setLocallySubmittedTaskIds((current) => {
        const next = new Set(current);
        payload.items.forEach((task) => {
          if (taskHasSubmittedConfirmation(task)) {
            next.add(task.taskId);
          }
        });
        return next;
      });
      setSelectedTaskId((current) => {
        if (payload.items.some((task) => task.taskId === current)) {
          return current;
        }
        return payload.items[0]?.taskId ?? "";
      });
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setTaskListError(formatEtcUiErrorMessage(caught, "ETC批次流程加载失败。"));
      }
    } finally {
      setTaskLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadBatches(controller.signal);
    return () => controller.abort();
  }, [loadBatches]);

  useEffect(() => {
    if (activeStatus !== "unsubmitted") {
      return undefined;
    }
    const controller = new AbortController();
    void loadReconciliationTasks(controller.signal);
    return () => controller.abort();
  }, [activeStatus, loadReconciliationTasks]);

  useEffect(() => {
    if (!selectedBatchId) {
      setBatchDetail(null);
      setBusinessBatchDetail(null);
      setBatchDetailError(null);
      return undefined;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setBatchDetailError(null);
    setActionError(null);
    void fetchEtcBusinessBatchDetail(selectedBatchId, controller.signal)
      .then((detail) => {
        if (!controller.signal.aborted) {
          setBatchDetailError(null);
          setBusinessBatchDetail(detail);
          setBatchDetail(businessBatchToBatchDetail(detail));
        }
      })
      .catch((caught) => {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          if (isEtcBusinessBatchNotFoundError(caught, selectedBatchId)) {
            setBusinessBatches((current) => current.filter((batch) => batch.businessBatchId !== selectedBatchId));
            setBatches((current) => current.filter((batch) =>
              batch.id !== selectedBatchId
              && batch.etcBatchId !== selectedBatchId
              && batch.externalBatchId !== selectedBatchId
            ));
            setSelectedBatchId((current) => (current === selectedBatchId ? "" : current));
            setBatchDetail(null);
            setBusinessBatchDetail(null);
            setBatchDetailError(null);
            return;
          }
          setBatchDetailError(formatEtcUiErrorMessage(caught, "ETC业务批次明细加载失败。"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setDetailLoading(false);
        }
      });
    return () => controller.abort();
  }, [selectedBatchId]);

  useEffect(() => {
    const completedImportJobs = jobs.filter(
      (job) =>
        job.type === "etc_invoice_import"
        && (job.status === "succeeded" || job.status === "partial_success")
        && !refreshedImportJobIdsRef.current.has(job.jobId),
    );
    if (completedImportJobs.length === 0) {
      return;
    }
    completedImportJobs.forEach((job) => refreshedImportJobIdsRef.current.add(job.jobId));
    emitEtcBusinessDomainUpdated({
      affectedMonths: completedImportJobs.flatMap((job) => job.affectedMonths ?? []),
      source: "etc_import_job_completed",
    });
    void loadBatches();
    if (activeStatus === "unsubmitted") {
      void loadReconciliationTasks();
    }
  }, [activeStatus, jobs, loadBatches, loadReconciliationTasks]);

  const selectedBatch = useMemo(
    () => batchDetail ?? batches.find((batch) => batch.id === selectedBatchId) ?? null,
    [batchDetail, batches, selectedBatchId],
  );
  const selectedBusinessBatch = useMemo(
    () => businessBatchDetail ?? businessBatches.find((batch) => batch.businessBatchId === selectedBatchId) ?? null,
    [businessBatchDetail, businessBatches, selectedBatchId],
  );
  const selectedTask = useMemo(
    () => reconciliationTasks.find((task) => task.taskId === selectedTaskId) ?? null,
    [reconciliationTasks, selectedTaskId],
  );
  const businessBatchTaskIds = useMemo(
    () => new Set(businessBatches.map((batch) => batch.taskId).filter(Boolean)),
    [businessBatches],
  );
  const businessBatchLinkIds = useMemo(() => {
    const ids = new Set<string>();
    businessBatches.forEach((batch) => {
      if (batch.businessBatchId) {
        ids.add(batch.businessBatchId);
      }
      if (batch.externalEtcBatchId) {
        ids.add(batch.externalEtcBatchId);
      }
      if (batch.submissionBatchId) {
        ids.add(batch.submissionBatchId);
      }
      batch.importBatchIds.forEach((importBatchId) => {
        if (importBatchId) {
          ids.add(importBatchId);
        }
      });
    });
    return ids;
  }, [businessBatches]);
  const taskOnlyBatches = useMemo(
    () => activeStatus === "unsubmitted"
      ? reconciliationTasks
        .filter((task) =>
          !businessBatchTaskIds.has(task.taskId)
          && !(task.importBatchId && businessBatchLinkIds.has(task.importBatchId))
          && !(task.etcBatchId && businessBatchLinkIds.has(task.etcBatchId))
          && taskCanAppearAsStandaloneBatch(task)
          && !locallySubmittedTaskIds.has(task.taskId)
        )
        .map(reconciliationTaskToBatchSummary)
      : [],
    [activeStatus, businessBatchLinkIds, businessBatchTaskIds, locallySubmittedTaskIds, reconciliationTasks],
  );
  const visibleBusinessBatchSummaries = useMemo(
    () => batches,
    [batches],
  );
  const visibleBatches = useMemo(
    () => [...taskOnlyBatches, ...visibleBusinessBatchSummaries],
    [taskOnlyBatches, visibleBusinessBatchSummaries],
  );
  const visibleWorkflowTaskIds = useMemo(() => {
    const ids = new Set<string>();
    visibleBatches.forEach((batch) => {
      if (batch.sourceType === "reconciliation_task") {
        ids.add(batch.id);
        return;
      }
      const businessBatch = businessBatches.find((item) => item.businessBatchId === batch.id);
      if (businessBatch?.taskId) {
        ids.add(businessBatch.taskId);
      }
    });
    return ids;
  }, [businessBatches, visibleBatches]);
  useEffect(() => {
    setSelectedTaskId((current) => {
      if (!current || visibleWorkflowTaskIds.has(current)) {
        return current;
      }
      return "";
    });
  }, [visibleWorkflowTaskIds]);
  const selectedTaskBusinessBatch = useMemo(
    () => selectedTask
      ? businessBatches.find((batch) => batch.taskId === selectedTask.taskId) ?? null
      : null,
    [businessBatches, selectedTask],
  );
  const selectedTaskImportBatchId = selectedTaskBusinessBatch?.businessBatchId || selectedTask?.importBatchId || "";
  const taskImportInvoiceItems = taskImportBatchDetail?.invoiceItems ?? [];
  const importedInvoiceCount = taskImportBatchDetail
    ? (taskImportBatchDetail.invoiceCount > 0 ? taskImportBatchDetail.invoiceCount : taskImportInvoiceItems.length)
    : (selectedTask?.importedInvoiceCount ?? 0);
  const importedInvoiceAmount = taskImportBatchDetail
    ? (Number(taskImportBatchDetail.totalAmount) > 0 || taskImportInvoiceItems.length === 0
      ? taskImportBatchDetail.totalAmount
      : sumInvoiceTotalAmount(taskImportInvoiceItems))
    : (selectedTask?.importedInvoiceAmount || "0.00");
  const canRemoveImportedInvoices = Boolean(
    selectedTask
    && selectedTaskImportBatchId
    && !selectedTaskBusinessBatch
    && importedInvoiceCount > 0
    && !taskHasOaDraftOrSubmittedLink(selectedTask),
  );
  const showTaskImportedInvoices = Boolean(selectedTask && selectedTaskImportBatchId && !selectedTaskBusinessBatch);

  useEffect(() => {
    if (!selectedTaskImportBatchId) {
      setTaskImportBatchDetail(null);
      setTaskImportDetailError(null);
      setTaskImportDetailLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    setTaskImportBatchDetail(null);
    setTaskImportDetailError(null);
    setTaskImportDetailLoading(true);
    const detailLoader = selectedTaskBusinessBatch
      ? fetchEtcBusinessBatchDetail(selectedTaskImportBatchId, controller.signal).then(businessBatchToBatchDetail)
      : fetchEtcBatchDetail(selectedTaskImportBatchId, controller.signal);
    void detailLoader
      .then((detail) => {
        if (!controller.signal.aborted) {
          setTaskImportBatchDetail(detail);
        }
      })
      .catch((caught) => {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setTaskImportDetailError(formatEtcUiErrorMessage(caught, "已导入发票加载失败。"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setTaskImportDetailLoading(false);
        }
      });
    return () => controller.abort();
  }, [selectedTaskBusinessBatch, selectedTaskImportBatchId]);

  useEffect(() => {
    if (batches.length === 0 && selectedBatchId) {
      setSelectedBatchId("");
      setBatchDetail(null);
      setBusinessBatchDetail(null);
      return;
    }
    if (visibleBatches.some((batch) => batch.id === selectedBatchId)) {
      return;
    }
    const firstBusinessBatch = visibleBatches.find((batch) => batch.sourceType !== "reconciliation_task");
    setBatchDetail(null);
    setBusinessBatchDetail(null);
    setSelectedBatchId(firstBusinessBatch?.id ?? "");
  }, [batches.length, selectedBatchId, visibleBatches]);

  useEffect(() => {
    if (!selectedTaskId) {
      return;
    }
    if (activeStatus === "unsubmitted" && visibleWorkflowTaskIds.has(selectedTaskId)) {
      return;
    }
    setSelectedTaskId("");
    setTaskImportBatchDetail(null);
    setTaskImportDetailError(null);
    setTaskImportDetailLoading(false);
  }, [activeStatus, selectedTaskId, visibleWorkflowTaskIds]);

  const ticketRootManualSources = useMemo(
    () => (selectedTask?.sourceFiles ?? []).filter(isManualTicketRootSource),
    [selectedTask],
  );
  const ticketRootDocumentSources = useMemo(
    () => (selectedTask?.sourceFiles ?? []).filter(isDocumentTicketRootSource),
    [selectedTask],
  );
  const ticketRootItemsBySourceFileId = useMemo(() => {
    const itemsBySource = new Map<string, EtcTicketRootItem[]>();
    for (const item of selectedTask?.ticketRootItems ?? []) {
      if (!item.sourceFileId) {
        continue;
      }
      const sourceItems = itemsBySource.get(item.sourceFileId) ?? [];
      sourceItems.push(item);
      itemsBySource.set(item.sourceFileId, sourceItems);
    }
    return itemsBySource;
  }, [selectedTask]);
  const ticketRootSourceSummaryBySourceFileId = useMemo(() => {
    const summaries = new Map<string, ReturnType<typeof ticketRootSourceSummary>>();
    for (const sourceFile of selectedTask?.sourceFiles ?? []) {
      if (sourceFile.sourceKind !== "ticket_root") {
        continue;
      }
      summaries.set(sourceFile.fileId, ticketRootSourceSummary(ticketRootItemsBySourceFileId.get(sourceFile.fileId) ?? []));
    }
    return summaries;
  }, [selectedTask, ticketRootItemsBySourceFileId]);
  const hasTicketRootManualSource = ticketRootManualSources.length > 0;
  const hasTicketRootDocumentSource = ticketRootDocumentSources.length > 0;
  const hasLegacyNonTxtTicketRootSource = hasTicketRootManualSource || hasTicketRootDocumentSource;

  useEffect(() => {
    setSelectedCardItemId("");
    setSelectedEvidenceRowId("");
    setSelectedReconciliationRowIds(new Set());
    setExpandedDescriptionRowIds(new Set());
    setReviewNote("");
  }, [selectedTaskId]);

  const invoiceRows = batchDetail?.invoiceItems ?? [];
  function taskHasOaDraftOrSubmittedLink(task: EtcReconciliationTask) {
    return Boolean(task.oaDraftBatchId?.trim() || task.submittedConfirmedAt?.trim());
  }
  const businessBatchDeleteBlockReason = (_batch: EtcBusinessBatchSummary) => "";
  const canDeleteBusinessBatch = (batch: EtcBusinessBatchSummary) => !businessBatchDeleteBlockReason(batch);
  const taskLinkedBusinessBatch = (task: EtcReconciliationTask) => {
    const importBatchId = task.importBatchId?.trim();
    return businessBatches.find((batch) =>
      batch.taskId === task.taskId
      && (!importBatchId || batch.importBatchIds.includes(importBatchId))
    ) ?? null;
  };
  const canRemoveImportedInvoicesFromTask = (task: EtcReconciliationTask) =>
    task.status === "imported" && Boolean(task.importBatchId?.trim()) && !task.submittedConfirmedAt?.trim();
  const canDeleteTask = (_task: EtcReconciliationTask) => true;
  const removeImportedInvoicesDisabledReason = (task: EtcReconciliationTask) => {
    if (task.submittedConfirmedAt?.trim()) {
      return "OA已提交，不能移除已导入发票";
    }
    if (task.status === "importing") {
      return "导入中，不能移除已导入发票";
    }
    if (task.status === "closed") {
      return "已关闭批次不能移除已导入发票";
    }
    return "当前任务不能移除已导入发票";
  };
  const deleteTaskDescription = (task: EtcReconciliationTask) => {
    if (task.status === "imported") {
      return "将删除本地 ETC 批次、上传文件、核对结果和已导入发票。OA 系统中的草稿和已提交记录不会删除。";
    }
    if (task.status === "ready_for_import") {
      return "将删除本地 ETC 批次、上传文件和核对结果。OA 系统中的草稿和已提交记录不会删除。";
    }
    return "将删除本地 ETC 批次、上传文件和核对结果。OA 系统中的草稿和已提交记录不会删除。";
  };
  const businessBatchForBatchSummary = (batch: EtcBatchSummary) => {
    const candidateIds = new Set(
      [batch.id, batch.etcBatchId, batch.externalBatchId]
        .map((value) => value.trim())
        .filter(Boolean),
    );
    return businessBatches.find((item) => {
      if (
        candidateIds.has(item.businessBatchId)
        || candidateIds.has(item.submissionBatchId)
        || candidateIds.has(item.externalEtcBatchId)
      ) {
        return true;
      }
      return item.importBatchIds.some((importBatchId) => candidateIds.has(importBatchId));
    }) ?? null;
  };
  const deleteBatchDescription = (target: Extract<DeleteTarget, { kind: "batch" }>) => {
    const businessBatch = businessBatchForBatchSummary(target.item);
    if (businessBatch && isSubmittedBusinessStatus(businessBatch.status)) {
      return "将删除本地 ETC 批次并取消发票合并，OA 系统中的草稿和已提交记录不会删除。";
    }
    return "将删除本地 ETC 批次及已导入内容，OA 系统中的草稿和已提交记录不会删除。";
  };
  const batchDeletePlan = (batch: EtcBatchSummary): BatchDeletePlan => {
    const businessBatch = businessBatchForBatchSummary(batch);
    if (businessBatch || isBusinessBatchSource(batch)) {
      return {
        kind: "businessBatch",
        batchId: businessBatch?.businessBatchId || batch.id,
        ...(businessBatch ? { expectedVersion: businessBatch.version } : {}),
      };
    }
    return { kind: "legacyBatch", batchId: batch.id };
  };
  const canDeleteBatch = (batch: EtcBatchSummary) => {
    const businessBatch = businessBatchForBatchSummary(batch);
    if (businessBatch) {
      return canDeleteBusinessBatch(businessBatch);
    }
    if (isBusinessBatchSource(batch)) {
      return true;
    }
    return true;
  };
  const deleteBusinessBatchDisabledReason = (batch: EtcBusinessBatchSummary) =>
    businessBatchDeleteBlockReason(batch) || "当前批次暂不可删除";
  const deleteBatchDisabledReason = (batch: EtcBatchSummary) => {
    const businessBatch = businessBatchForBatchSummary(batch);
    if (businessBatch) {
      return deleteBusinessBatchDisabledReason(businessBatch);
    }
    return "当前批次暂不可删除";
  };
  const evidenceRows = useMemo<EvidenceRow[]>(() => {
    const ticketRows = (selectedTask?.ticketRootItems ?? []).map((item: EtcTicketRootItem) => ({
      id: item.itemId,
      source: "ticket" as const,
      transactionTime: item.transactionAt,
      fallbackTimeLabel: "-",
      plateOrMerchant: item.vehiclePlate || "未记录车牌",
      amount: item.amount,
      invoiceCount: item.invoiceCount,
      highlight: recommendationHighlight(item.recommendationStatus),
      tags: [],
    }));
    const supplementRows = (selectedTask?.supplementEvidences ?? []).map((item: EtcSupplementEvidence) => ({
      id: item.evidenceId,
      source: "supplement" as const,
      transactionTime: item.paidAt,
      fallbackTimeLabel: item.sourceName || "补充凭证",
      plateOrMerchant: item.merchantName || "补充凭证",
      amount: item.amount,
      invoiceCount: 0,
      highlight: "covered",
      tags: item.tags,
    }));
    return [...ticketRows, ...supplementRows];
  }, [selectedTask]);
  const reconciliationRows = useMemo<ReconciliationRow[]>(() => {
    if (!selectedTask) {
      return [];
    }

    const evidenceById = new Map(evidenceRows.map((item) => [item.id, item]));
    const reconciledByCardId = new Map(
      (selectedTask.reconciledItems ?? []).map((item) => [item.creditCardItemId, item]),
    );
    const consumedEvidenceIds = new Set<string>();
    const rows: ReconciliationRow[] = [];

    selectedTask.creditCardItems.forEach((card) => {
      const linkedTicket = selectedTask.ticketRootItems.find((ticket) =>
        ticket.linkedCreditCardItemIds.includes(card.itemId)
      );
      const linkedSupplementId = reconciledByCardId.get(card.itemId)?.supplementEvidenceIds[0] ?? "";
      const matchedEvidence = linkedTicket
        ? evidenceById.get(linkedTicket.itemId) ?? null
        : evidenceById.get(linkedSupplementId) ?? null;
      if (matchedEvidence) {
        consumedEvidenceIds.add(matchedEvidence.id);
      }

      const manual = manualHighlight(card.manualResolution);
      const rowHighlight = matchedEvidence ? "matched" : manual || "missing";
      const evidenceHighlight = matchedEvidence
        ? (matchedEvidence.source === "supplement" ? "covered" : "matched")
        : "";
      rows.push({
        id: card.itemId,
        card,
        evidence: matchedEvidence,
        highlight: matchedEvidence?.source === "supplement" ? "covered" : rowHighlight,
        cardHighlight: matchedEvidence ? "matched" : rowHighlight,
        evidenceHighlight,
      });
    });

    evidenceRows.forEach((evidence) => {
      if (consumedEvidenceIds.has(evidence.id)) {
        return;
      }
      rows.push({
        id: `right-${evidence.id}`,
        card: null,
        evidence,
        highlight: "extra",
        cardHighlight: "",
        evidenceHighlight: "extra",
      });
    });

    return rows;
  }, [evidenceRows, selectedTask]);
  const visibleReconciliationRowIds = useMemo(
    () => reconciliationRows.map((row) => row.id),
    [reconciliationRows],
  );
  const pairedReconciliationRowIds = useMemo(
    () => reconciliationRows
      .filter((row) =>
        Boolean(row.card)
        && Boolean(row.evidence)
        && ["matched", "manual", "covered"].includes(row.highlight)
      )
      .map((row) => row.id),
    [reconciliationRows],
  );
  const selectedReconciliationSummary = useMemo<ReconciliationSelectionSummary>(() => {
    const creditCardItemIds: string[] = [];
    const seenCardIds = new Set<string>();
    const selectedDates: string[] = [];
    let totalAmount = 0;
    let etcInvoiceCount = 0;
    let supplementCount = 0;

    for (const row of reconciliationRows) {
      if (!selectedReconciliationRowIds.has(row.id) || !row.card || !row.evidence) {
        continue;
      }
      if (seenCardIds.has(row.card.itemId)) {
        continue;
      }
      seenCardIds.add(row.card.itemId);
      creditCardItemIds.push(row.card.itemId);

      const parsedAmount = Number(row.card.settlementAmount);
      if (Number.isFinite(parsedAmount)) {
        totalAmount += parsedAmount;
      }
      const transactionDate = datePart(row.card.transactionDate);
      if (transactionDate) {
        selectedDates.push(transactionDate);
      }
      if (row.evidence.source === "ticket") {
        etcInvoiceCount += row.evidence.invoiceCount || 1;
      } else {
        supplementCount += 1;
      }
    }

    selectedDates.sort();
    return {
      creditCardItemIds,
      oaTotalAmount: totalAmount.toFixed(2),
      periodStart: selectedDates[0] ?? null,
      periodEnd: selectedDates[selectedDates.length - 1] ?? null,
      etcInvoiceCount,
      supplementCount,
    };
  }, [reconciliationRows, selectedReconciliationRowIds]);
  const selectedConfirmedCreditCardItemIds = selectedReconciliationSummary.creditCardItemIds;
  const selectedTaskImportBatchSelected = Boolean(selectedTask && selectedTaskImportBatchId);
  const selectedTaskImportBatchCanSubmit = Boolean(
    selectedTask
    && selectedTaskImportBatchId
    && selectedTaskBusinessBatch
    && canCreateOaDraft(selectedTaskBusinessBatch.status)
    && importedInvoiceCount > 0
    && !taskImportDetailLoading,
  );
  const currentBusinessBatch = selectedTaskImportBatchSelected
    ? selectedTaskBusinessBatch
    : selectedBusinessBatch;
  const currentOaDraftBatchId = currentBusinessBatch?.businessBatchId ?? "";
  const currentOaDraftBatchLabel = selectedTaskImportBatchSelected
    ? (selectedTaskBusinessBatch?.externalEtcBatchId || selectedTaskBusinessBatch?.businessBatchId || "")
    : (selectedBusinessBatch?.externalEtcBatchId || selectedBusinessBatch?.businessBatchId || "");
  const currentOaDraftDescription = selectedTaskImportBatchSelected
    ? `为当前任务的 ${importedInvoiceCount} 张发票创建 OA 草稿，合计 ${importedInvoiceAmount}。`
    : "为当前批次创建 OA 草稿。";
  const canSubmitCurrentBatch = activeStatus === "unsubmitted"
    && (selectedTaskImportBatchSelected
      ? selectedTaskImportBatchCanSubmit
      : currentBusinessBatch !== null && canCreateOaDraft(currentBusinessBatch.status) && !detailLoading);
  const currentOaActionBatch = useMemo(() => {
    if (draftResult?.batchId) {
      return businessBatches.find((batch) => batch.businessBatchId === draftResult.batchId) ?? currentBusinessBatch;
    }
    return currentBusinessBatch;
  }, [businessBatches, currentBusinessBatch, draftResult?.batchId]);
  const taskIsMutable = Boolean(selectedTask && ["draft", "reviewing"].includes(selectedTask.status));
  const canConfirmSelectedTask = taskIsMutable && selectedConfirmedCreditCardItemIds.length > 0;
  const selectedCardItem = useMemo(
    () => selectedTask?.creditCardItems.find((item) => item.itemId === selectedCardItemId) ?? null,
    [selectedCardItemId, selectedTask],
  );
  const selectedEvidenceRow = useMemo(
    () => evidenceRows.find((item) => item.id === selectedEvidenceRowId) ?? null,
    [evidenceRows, selectedEvidenceRowId],
  );
  const suggestedTicket = useMemo(() => {
    if (!selectedTask || !selectedCardItem) {
      return null;
    }
    return selectedTask.ticketRootItems.find((item) =>
      item.linkedCreditCardItemIds.includes(selectedCardItem.itemId)
    ) ?? null;
  }, [selectedCardItem, selectedTask]);

  useEffect(() => {
    const visibleIds = new Set(visibleReconciliationRowIds);
    setSelectedReconciliationRowIds((current) => {
      const next = new Set([...current].filter((rowId) => visibleIds.has(rowId)));
      return next.size === current.size ? current : next;
    });
    setExpandedDescriptionRowIds((current) => {
      const next = new Set([...current].filter((rowId) => visibleIds.has(rowId)));
      return next.size === current.size ? current : next;
    });
  }, [visibleReconciliationRowIds]);

  const mergeReconciliationTask = useCallback((task: EtcReconciliationTask) => {
    setReconciliationTasks((current) => {
      const exists = current.some((item) => item.taskId === task.taskId);
      if (!exists) {
        return [task, ...current];
      }
      return current.map((item) => (item.taskId === task.taskId ? task : item));
    });
    setSelectedTaskId(task.taskId);
  }, []);

  const mergeBusinessBatch = useCallback((
    batch: EtcBusinessBatchDetail | EtcBusinessBatchSummary,
    previousStatusOverride?: EtcBusinessBatchStatus | null,
  ) => {
    const previousBatch = businessBatches.find((item) => item.businessBatchId === batch.businessBatchId) ?? null;
    setCounts((current) => transitionBusinessBatchCounts(current, previousStatusOverride ?? previousBatch?.status ?? null, batch.status));
    const belongsToCurrentStatus = businessBatchBelongsToBatchStatus(batch.status, activeStatus);
    setBusinessBatches((current) => {
      const exists = current.some((item) => item.businessBatchId === batch.businessBatchId);
      if (!belongsToCurrentStatus) {
        return current.filter((item) => item.businessBatchId !== batch.businessBatchId);
      }
      if (!exists) {
        return [batch, ...current];
      }
      return current.map((item) => (item.businessBatchId === batch.businessBatchId ? batch : item));
    });
    setBatches((current) => {
      const mapped = businessBatchToBatchSummary(batch);
      const exists = current.some((item) => item.id === mapped.id);
      if (!belongsToCurrentStatus) {
        return current.filter((item) => item.id !== mapped.id);
      }
      if (!exists) {
        return [mapped, ...current];
      }
      return current.map((item) => (item.id === mapped.id ? mapped : item));
    });
    if (!belongsToCurrentStatus) {
      setSelectedBatchId((current) => (current === batch.businessBatchId ? "" : current));
      setBusinessBatchDetail((current) => (current?.businessBatchId === batch.businessBatchId ? null : current));
      setBatchDetail((current) => (current?.id === batch.businessBatchId ? null : current));
    } else if ("invoiceItems" in batch) {
      setBusinessBatchDetail(batch);
      setBatchDetail(businessBatchToBatchDetail(batch));
    }
  }, [activeStatus, businessBatches]);

  const handleStatusChange = (nextStatus: EtcBatchStatus) => {
    if (nextStatus === activeStatus) {
      return;
    }
    setActiveStatus(nextStatus);
    setSelectedBatchId("");
    setBatchDetail(null);
  };

  const runTaskAction = async (action: () => Promise<EtcReconciliationTask>) => {
    setTaskActionLoading(true);
    setActionError(null);
    try {
      const task = await action();
      mergeReconciliationTask(task);
    } catch (caught) {
      setActionError(formatEtcUiErrorMessage(caught, "ETC批次操作失败。"));
    } finally {
      setTaskActionLoading(false);
    }
  };

  const handleCreateReconciliationTask = async () => {
    await runTaskAction(() => createEtcReconciliationTask({ title: "新建ETC对账批次" }));
  };

  const handleUploadCreditCardStatement = async (files: File[]) => {
    if (!selectedTask || files.length === 0) {
      return;
    }
    await runTaskAction(() => uploadEtcCreditCardStatement(selectedTask.taskId, files[0], selectedTask.version));
  };

  const handleUploadTicketRootFiles = async (files: File[]) => {
    if (!selectedTask || files.length === 0) {
      return;
    }
    await runTaskAction(() => uploadEtcTicketRootFiles(selectedTask.taskId, files, selectedTask.version));
  };

  const handleRefreshReconciliationMatches = async () => {
    if (!selectedTask) {
      return;
    }
    await runTaskAction(() => refreshEtcReconciliationMatches(selectedTask.taskId));
  };

  const handleToggleReconciliationRow = (rowId: string) => {
    setSelectedReconciliationRowIds((current) => {
      const next = new Set(current);
      if (next.has(rowId)) {
        next.delete(rowId);
      } else {
        next.add(rowId);
      }
      return next;
    });
  };

  const handleSelectAllReconciliationRows = () => {
    setSelectedReconciliationRowIds(new Set(visibleReconciliationRowIds));
  };

  const handleSelectPairedReconciliationRows = () => {
    setSelectedReconciliationRowIds(new Set(pairedReconciliationRowIds));
  };

  const handleClearReconciliationSelection = () => {
    setSelectedReconciliationRowIds(new Set());
  };

  const handleToggleDescriptionExpansion = (rowId: string) => {
    setExpandedDescriptionRowIds((current) => {
      const next = new Set(current);
      if (next.has(rowId)) {
        next.delete(rowId);
      } else {
        next.add(rowId);
      }
      return next;
    });
  };

  const openSupplementUploadDialog = (card: EtcCreditCardItem) => {
    setActionError(null);
    setSupplementUploadCard(card);
    setSupplementUploadFiles([]);
    setSupplementUploadNote(card.reviewNote || "");
  };

  const closeSupplementUploadDialog = () => {
    if (supplementUploadSubmitting) {
      return;
    }
    setSupplementUploadCard(null);
    setSupplementUploadFiles([]);
    setSupplementUploadNote("");
  };

  const handleUploadSupplementForCard = async () => {
    if (!selectedTask || !supplementUploadCard || supplementUploadFiles.length === 0) {
      setActionError("请先选择补充凭证文件。");
      return;
    }
    setSupplementUploadSubmitting(true);
    setActionError(null);
    try {
      const task = await uploadEtcSupplementEvidenceForCard(
        selectedTask.taskId,
        supplementUploadCard.itemId,
        supplementUploadFiles,
        selectedTask.version,
        {
          evidenceKind: "non_etc_invoice",
          note: supplementUploadNote.trim(),
        },
      );
      mergeReconciliationTask(task);
      setSupplementUploadCard(null);
      setSupplementUploadFiles([]);
      setSupplementUploadNote("");
      setSelectedCardItemId(supplementUploadCard.itemId);
    } catch (caught) {
      setActionError(formatEtcUiErrorMessage(caught, "补充凭证上传失败。"));
    } finally {
      setSupplementUploadSubmitting(false);
    }
  };

  const patchSelectedCard = async (payload: Parameters<typeof patchEtcReconciliationItem>[3]) => {
    if (!selectedTask || !selectedCardItem) {
      setActionError("请先选择一条信用卡账单明细。");
      return;
    }
    await runTaskAction(() => patchEtcReconciliationItem(selectedTask.taskId, selectedCardItem.itemId, selectedTask.version, payload));
  };

  const handleAcceptSuggestedTicket = async () => {
    if (!suggestedTicket) {
      setActionError("当前信用卡明细没有可接受的推荐票根。");
      return;
    }
    await patchSelectedCard({
      action: "link_ticket",
      ticketItemId: suggestedTicket.itemId,
    });
  };

  const handleLinkSelectedEvidence = async () => {
    if (!selectedEvidenceRow) {
      setActionError("请先选择一条票根或补充凭证。");
      return;
    }
    if (selectedEvidenceRow.source === "ticket") {
      await patchSelectedCard({
        action: "link_ticket",
        ticketItemId: selectedEvidenceRow.id,
      });
      return;
    }
    await patchSelectedCard({
      action: "link_supplement",
      supplementEvidenceId: selectedEvidenceRow.id,
      note: reviewNote.trim(),
    });
  };

  const handleExcludeCard = async (manualResolution: "excluded_non_etc" | "excluded_error") => {
    const note = reviewNote.trim();
    if (!note) {
      setActionError("排除信用卡明细前需要填写处理说明。");
      return;
    }
    await patchSelectedCard({
      action: "exclude_card",
      manualResolution,
      reason: note,
    });
  };

  const handleManualConfirmCard = async () => {
    if (!selectedTask) {
      return;
    }
    const note = reviewNote.trim();
    if (!note) {
      setActionError("手工确认前需要填写处理说明。");
      return;
    }
    await patchSelectedCard({
      action: "manual_confirm",
      note,
    });
  };

  const handleConfirmReconciliationTask = async () => {
    if (!selectedTask) {
      return;
    }
    if (selectedConfirmedCreditCardItemIds.length === 0) {
      setActionError("请先选择要确认的配对项。");
      return;
    }
    await runTaskAction(() => confirmEtcReconciliationTask(
      selectedTask.taskId,
      selectedTask.version,
      { confirmedCreditCardItemIds: selectedConfirmedCreditCardItemIds },
    ));
  };

  const handleReopenReconciliationTask = async () => {
    if (!selectedTask) {
      return;
    }
    await runTaskAction(() => reopenEtcReconciliationTask(selectedTask.taskId, selectedTask.version));
  };

  const handleRemoveImportedInvoices = async () => {
    if (!selectedTask || !selectedTaskImportBatchId) {
      return;
    }
    const removedBatchId = selectedTaskImportBatchId;
    setRemoveImportedInvoicesSubmitting(true);
    setActionError(null);
    try {
      const latestTask = await fetchEtcReconciliationTask(selectedTask.taskId);
      mergeReconciliationTask(latestTask);
      if (!canRemoveImportedInvoicesFromTask(latestTask)) {
        throw new Error(removeImportedInvoicesDisabledReason(latestTask));
      }
      const task = await deleteEtcReconciliationTaskImportedInvoices(latestTask.taskId, latestTask.version);
      setTaskImportBatchDetail(null);
      setTaskImportDetailError(null);
      setBatches((current) => current.filter((batch) =>
        batch.id !== removedBatchId
        && batch.etcBatchId !== removedBatchId
        && batch.externalBatchId !== removedBatchId
      ));
      mergeReconciliationTask(task);
      setRemoveImportedInvoicesDialogOpen(false);
    } catch (caught) {
      setActionError(formatEtcUiErrorMessage(caught, "移除发票失败。"));
    } finally {
      setRemoveImportedInvoicesSubmitting(false);
    }
  };

  const openDeleteTaskDialog = (task: EtcReconciliationTask, event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!canDeleteTask(task)) {
      return;
    }
    setActionError(null);
    setDeleteTarget({ kind: "task", item: task });
  };

  const openDeleteBatchDialog = (batch: EtcBatchSummary, event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!canDeleteBatch(batch)) {
      return;
    }
    setActionError(null);
    setDeleteTarget({ kind: "batch", item: batch, plan: batchDeletePlan(batch) });
  };

  const openDeleteSourceFileDialog = (sourceFile: EtcSourceFile, event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!selectedTask || !taskIsMutable) {
      return;
    }
    setActionError(null);
    setDeleteTarget({ kind: "sourceFile", task: selectedTask, item: sourceFile });
  };

  const fetchLatestDeletableTask = async (task: EtcReconciliationTask) => {
    const latestTask = await fetchEtcReconciliationTask(task.taskId);
    mergeReconciliationTask(latestTask);
    const linkedBusinessBatch = taskLinkedBusinessBatch(latestTask);
    if (linkedBusinessBatch) {
      const latestBusinessBatch = await fetchEtcBusinessBatchDetail(linkedBusinessBatch.businessBatchId);
      mergeBusinessBatch(latestBusinessBatch);
      const linkedBusinessBatchReason = businessBatchDeleteBlockReason(latestBusinessBatch);
      if (linkedBusinessBatchReason) {
        throw new Error(linkedBusinessBatchReason);
      }
    }
    return latestTask;
  };

  const removeDeletedBatchFromState = (batchId: string) => {
    setBusinessBatches((current) => current.filter((batch) => batch.businessBatchId !== batchId));
    setBatches((current) => current.filter((batch) =>
      batch.id !== batchId
      && batch.etcBatchId !== batchId
      && batch.externalBatchId !== batchId
    ));
    setSelectedBatchId((current) => (current === batchId ? "" : current));
    setBatchDetail((current) => (current?.id === batchId ? null : current));
    setBusinessBatchDetail((current) => (current?.businessBatchId === batchId ? null : current));
  };

  const deleteBusinessBatchByPlan = async (plan: Extract<BatchDeletePlan, { kind: "businessBatch" }>) => {
    let payload: { expectedVersion?: number; reason: string } = {
      ...(plan.expectedVersion !== undefined ? { expectedVersion: plan.expectedVersion } : {}),
      reason: "用户在 ETC 页面删除未提交业务批次。",
    };
    try {
      const latestBusinessBatch = await fetchEtcBusinessBatchDetail(plan.batchId);
      mergeBusinessBatch(latestBusinessBatch);
      if (!canDeleteBusinessBatch(latestBusinessBatch)) {
        throw new Error(deleteBusinessBatchDisabledReason(latestBusinessBatch));
      }
      payload = {
        expectedVersion: latestBusinessBatch.version,
        reason: isSubmittedBusinessStatus(latestBusinessBatch.status)
          ? "用户在 ETC 页面删除已提交业务批次并释放发票。"
          : payload.reason,
      };
    } catch (caught) {
      if (!isEtcBusinessBatchNotFoundError(caught, plan.batchId)) {
        throw caught;
      }
      payload = { reason: payload.reason };
    }
    try {
      await deleteEtcBusinessBatch(plan.batchId, payload);
    } catch (caught) {
      if (!isEtcBusinessBatchNotFoundError(caught, plan.batchId)) {
        throw caught;
      }
    }
    removeDeletedBatchFromState(plan.batchId);
    emitEtcBusinessDomainUpdated({ source: "etc_business_batch_delete" });
  };

  const handleDeleteConfirmed = async () => {
    if (!deleteTarget) {
      return;
    }
    setDeleteSubmitting(true);
    setActionError(null);
    try {
      if (deleteTarget.kind === "task") {
        const latestTask = await fetchLatestDeletableTask(deleteTarget.item);
        const taskId = latestTask.taskId;
        const wasSelectedTask = selectedTaskId === taskId;
        const removedBatchId = latestTask.etcBatchId || latestTask.importBatchId || "";
        await deleteEtcReconciliationTask(taskId, latestTask.version);
        setReconciliationTasks((current) => current.filter((task) => task.taskId !== taskId));
        setTaskImportBatchDetail(null);
        setTaskImportDetailError(null);
        setTaskImportDetailLoading(false);
        if (removedBatchId) {
          setBatches((current) => current.filter((batch) =>
            batch.id !== removedBatchId
            && batch.etcBatchId !== removedBatchId
            && batch.externalBatchId !== removedBatchId
          ));
        }
        if (wasSelectedTask) {
          setSelectedTaskId("");
        }
        void loadReconciliationTasks();
      } else if (deleteTarget.kind === "sourceFile") {
        const latestTask = await fetchEtcReconciliationTask(deleteTarget.task.taskId);
        mergeReconciliationTask(latestTask);
        if (!["draft", "reviewing"].includes(latestTask.status)) {
          throw new Error("当前任务状态不能删除源文件");
        }
        const sourceFileExists = latestTask.sourceFiles.some((sourceFile) => sourceFile.fileId === deleteTarget.item.fileId);
        if (!sourceFileExists) {
          throw new Error("源文件已变化，请刷新后重试。");
        }
        const task = await deleteEtcReconciliationSourceFile(
          latestTask.taskId,
          deleteTarget.item.fileId,
          latestTask.version,
        );
        mergeReconciliationTask(task);
      } else {
        const { plan } = deleteTarget;
        const batchId = plan.batchId;
        if (plan.kind === "businessBatch") {
          await deleteBusinessBatchByPlan(plan);
        } else {
          await deleteEtcBatch(batchId);
          removeDeletedBatchFromState(batchId);
        }
        await loadBatches();
      }
      setDeleteTarget(null);
    } catch (caught) {
      setActionError(formatEtcUiErrorMessage(caught, "删除失败。"));
    } finally {
      setDeleteSubmitting(false);
    }
  };

  const handleCreateDraft = async () => {
    if (!currentBusinessBatch || !currentOaDraftBatchId) {
      return;
    }
    setActionError(null);
    setDraftCreating(true);
    try {
      const result = await createEtcBusinessBatchOaDraft(currentOaDraftBatchId, {
        expectedVersion: currentBusinessBatch.version,
      });
      mergeBusinessBatch(result);
      emitEtcBusinessDomainUpdated({ source: "etc_business_batch_oa_draft_create" });
      setDraftResult({
        batchId: result.businessBatchId,
        etcBatchId: result.externalEtcBatchId,
        oaDraftId: result.oaDraftId,
        oaDraftUrl: result.oaDraftUrl,
      });
    } catch (caught) {
      setActionError(formatEtcUiErrorMessage(caught, "OA 草稿创建失败。"));
    } finally {
      setDraftCreating(false);
    }
  };

  const resolveOaActionBatch = (batch?: EtcBusinessBatchDetail | EtcBusinessBatchSummary | null) => {
    if (draftResult?.batchId) {
      return businessBatches.find((item) => item.businessBatchId === draftResult.batchId) ?? batch ?? currentOaActionBatch;
    }
    return batch ?? currentOaActionBatch;
  };

  const openOaDraftUrl = (draftUrl: string) => {
    if (!draftUrl) {
      return;
    }
    window.open(buildEtcOaDraftReviewUrl(draftUrl), "_blank", "noopener,noreferrer");
  };

  const handleOpenCurrentDraft = () => {
    openOaDraftUrl(draftResult?.oaDraftUrl || currentOaActionBatch?.oaDraftUrl || "");
  };

  const handleManualBusinessBatchOaStatus = async (
    decision: "submitted" | "not_submitted",
    batch?: EtcBusinessBatchDetail | EtcBusinessBatchSummary | null,
  ) => {
    const target = resolveOaActionBatch(batch);
    if (!target) {
      return;
    }
    const reason = decision === "submitted" ? MANUAL_OA_SUBMITTED_REASON : MANUAL_OA_NOT_SUBMITTED_REASON;
    setOaActionLoading(true);
    setActionError(null);
    try {
      const result = await manualEtcBusinessBatchOaStatus(target.businessBatchId, {
        decision,
        reason,
        expectedVersion: target.version,
      });
      mergeBusinessBatch(result, target.status);
      const nextStatus = decision === "submitted" ? "submitted" : "unsubmitted";
      if (result.taskId) {
        setLocallySubmittedTaskIds((current) => {
          const next = new Set(current);
          if (decision === "submitted") {
            next.add(result.taskId);
          } else {
            next.delete(result.taskId);
          }
          return next;
        });
        if (decision === "submitted") {
          setSelectedTaskId((current) => (current === result.taskId ? "" : current));
        }
      }
      emitEtcBusinessDomainUpdated({ source: "etc_business_batch_manual_oa_status" });
      if (decision === "submitted") {
        setActiveStatus("submitted");
        setSelectedBatchId(result.businessBatchId);
      }
      setDraftResult(null);
      setCreateDialogOpen(false);
      await Promise.all([
        loadReconciliationTasks(),
        loadBatches(undefined, nextStatus),
      ]);
    } catch (caught) {
      setActionError(formatEtcUiErrorMessage(caught, "人工处理失败。"));
    } finally {
      setOaActionLoading(false);
    }
  };

  const renderOaStatusPanel = (batch: EtcBusinessBatchDetail | EtcBusinessBatchSummary) => (
    <section className="etc-oa-status-panel" aria-label="OA提交确认">
      <div className="etc-oa-status-header">
        <div>
          <strong>OA草稿已创建，等待提交确认。</strong>
          <p>请选择 OA 草稿的实际提交状态。</p>
        </div>
        <div className="etc-oa-status-actions">
          {batch.oaDraftUrl ? (
            <button
              type="button"
              className="etc-secondary-action"
              onClick={() => openOaDraftUrl(batch.oaDraftUrl)}
            >
              <ExternalLink aria-hidden="true" size={16} />
              打开草稿
            </button>
          ) : null}
          <button
            type="button"
            className="etc-primary-action"
            disabled={oaActionLoading}
            onClick={() => void handleManualBusinessBatchOaStatus("submitted", batch)}
          >
            <CheckCircle2 aria-hidden="true" size={16} />
            已提交
          </button>
          <button
            type="button"
            className="etc-secondary-action"
            disabled={oaActionLoading}
            onClick={() => void handleManualBusinessBatchOaStatus("not_submitted", batch)}
          >
            <XCircle aria-hidden="true" size={16} />
            未提交
          </button>
        </div>
      </div>
    </section>
  );

  const renderCardDateCell = (card: EtcCreditCardItem | null) => {
    if (!card) {
      return <span className="etc-reconciliation-empty">-</span>;
    }
    const transactionDate = splitDateParts(card.transactionDate);
    return (
      <span className="etc-reconciliation-date-pair" data-testid={`etc-card-date-transaction-${card.itemId}`}>
        <span>{transactionDate}</span>
      </span>
    );
  };

  const renderCardDescriptionCell = (card: EtcCreditCardItem | null) => {
    if (!card) {
      return <span className="etc-reconciliation-empty">未配对信用卡项</span>;
    }
    return (
      <ReconciliationDescriptionCell
        cardId={card.itemId}
        description={card.description || "-"}
        expanded={expandedDescriptionRowIds.has(card.itemId)}
        onToggle={() => handleToggleDescriptionExpansion(card.itemId)}
      />
    );
  };

  const renderCardAmountCell = (card: EtcCreditCardItem | null) => {
    if (!card) {
      return <span className="etc-reconciliation-empty">-</span>;
    }
    return (
      <span className="etc-reconciliation-amount-cell">
        <span className="etc-reconciliation-money">{formatMoney(card.settlementAmount)}</span>
      </span>
    );
  };

  const renderEvidenceTimeCell = (evidence: EvidenceRow | null) => {
    if (!evidence) {
      return <span className="etc-reconciliation-empty">未找到票根/凭证</span>;
    }
    const parts = splitDateTimeParts(evidence.transactionTime);
    const showFallback = parts.date === "-" && evidence.fallbackTimeLabel;
    return (
      <span className="etc-reconciliation-time-cell">
        <span>{showFallback ? evidence.fallbackTimeLabel : parts.date}</span>
        {parts.time ? <span>{parts.time}</span> : null}
      </span>
    );
  };

  const renderEvidenceSummaryCell = (evidence: EvidenceRow | null, card: EtcCreditCardItem | null) => {
    if (!evidence) {
      if (!card || !taskIsMutable || card.manualResolution !== "unresolved") {
        return <span className="etc-reconciliation-empty">-</span>;
      }
      const label = `上传补充凭证覆盖 ${card.description || card.itemId}`;
      return (
        <span className="etc-reconciliation-empty-action">
          <span>未匹配</span>
          <button
            type="button"
            className="etc-inline-icon-action"
            aria-label={label}
            title="上传补充凭证并覆盖该信用卡项"
            disabled={taskActionLoading}
            onClick={(event) => {
              event.stopPropagation();
              openSupplementUploadDialog(card);
            }}
          >
            <UploadCloud aria-hidden="true" size={16} />
          </button>
        </span>
      );
    }
    return (
      <span className="etc-reconciliation-evidence-cell">
        <span className="etc-reconciliation-chip-line">
          <span className="etc-reconciliation-money">{formatMoney(evidence.amount)}</span>
          <span className="etc-status-tag">{evidence.plateOrMerchant || (evidence.source === "ticket" ? "未记录车牌" : "补充凭证")}</span>
        </span>
        {evidence.source === "supplement" && evidence.tags.length > 0 ? (
          <span className="etc-reconciliation-chip-line">
            {evidence.tags.map((tag) => <span key={tag} className="etc-status-tag etc-status-tag--warning">{tag}</span>)}
          </span>
        ) : null}
      </span>
    );
  };

  const renderEtcInvoiceTable = (
    rows: EtcInvoice[],
    {
      ariaLabel,
      emptyText,
      loadingText,
      tableKey,
    }: { ariaLabel: string; emptyText: string; loadingText: string; tableKey: string },
  ) => (
    <div className="etc-invoice-table-container">
      <table
        key={tableKey}
        aria-label={ariaLabel}
        className="etc-invoice-table"
      >
        <thead>
          <tr>
            <th className="etc-invoice-number-column">发票号码</th>
            <th className="etc-invoice-issue-column">开票日期</th>
            <th className="etc-invoice-passage-column">通行日期</th>
            <th className="etc-invoice-plate-column">车牌</th>
            <th className="etc-invoice-seller-column">销方</th>
            <th className="etc-invoice-money-column">金额</th>
            <th className="etc-invoice-tax-column">税额</th>
            <th className="etc-invoice-attachment-column">附件状态</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={8} className="etc-invoice-table-empty">
                {loadingText || emptyText}
              </td>
            </tr>
          ) : (
            rows.map((invoice) => (
              <tr key={invoice.id}>
                <td>{invoice.invoiceNumber}</td>
                <td>{invoice.issueDate}</td>
                <td>{formatDateRange(invoice.passageStartDate, invoice.passageEndDate)}</td>
                <td>{invoice.plateNumber || "-"}</td>
                <td>{invoice.sellerName || "-"}</td>
                <td className="etc-invoice-money-cell">{formatMoney(invoice.totalAmount)}</td>
                <td className="etc-invoice-money-cell">{formatMoney(invoice.taxAmount)}</td>
                <td>{attachmentLabel(invoice)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );

  return (
    <div data-testid="etc-ticket-management-page">
      <PageScaffold
        className="etc-page"
        title="ETC票据"
        actions={
          <RouterLink className="button button--sm button--outline etc-page-action-link" to="/imports/etc-invoices">
            导入发票
            <ArrowRight aria-hidden="true" size={16} />
          </RouterLink>
        }
      >
        <div className="etc-page-content">
          {actionError ? <StatePanel tone="error">{actionError}</StatePanel> : null}

          <div className="etc-filter-bar" aria-label="ETC筛选">
            <ToggleButtonGroup
              aria-label="ETC批次状态"
              className="etc-status-segmented"
              disallowEmptySelection
              selectedKeys={new Set<Key>([activeStatus])}
              selectionMode="single"
              size="sm"
              onSelectionChange={(keys) => {
                const [next] = Array.from(keys);
                if (next === "submitted" || next === "unsubmitted") {
                  handleStatusChange(next);
                }
              }}
            >
              <ToggleButton id="unsubmitted" className="etc-status-segmented__button">
                未提交 {counts.unsubmitted}
              </ToggleButton>
              <ToggleButton id="submitted" className="etc-status-segmented__button">
                <ToggleButtonGroup.Separator />
                已提交 {counts.submitted}
              </ToggleButton>
            </ToggleButtonGroup>
            <label className="etc-filter-field">
              <span>月份</span>
              <input
                type="month"
                value={month}
                onChange={(event) => setMonth(event.target.value)}
              />
            </label>
            <label className="etc-filter-field">
              <span>车牌</span>
              <input
                value={plate}
                placeholder="云ADA0381"
                onChange={(event) => setPlate(event.target.value)}
              />
            </label>
            <label className="etc-filter-field">
              <span>关键词</span>
              <input
                value={keyword}
                placeholder="批次号/OA/发票号"
                onChange={(event) => setKeyword(event.target.value)}
              />
            </label>
            {activeStatus === "unsubmitted" ? (
              <Button
                className="etc-primary-action"
                isDisabled={!canSubmitCurrentBatch || draftCreating}
                isPending={draftCreating}
                onPress={() => setCreateDialogOpen(true)}
                size="sm"
                variant="primary"
              >
                提交OA
              </Button>
            ) : null}
          </div>

          <div className="etc-layout">
            <section className="etc-batch-list-panel" aria-label="ETC批次列表区">
              <div className="etc-panel-heading">
                <div className="etc-panel-heading__title">
                  <h2>批次列表</h2>
                  <CountChip>{visibleBatches.length} 批</CountChip>
                </div>
                {activeStatus === "unsubmitted" ? (
                  <Button
                    className="etc-secondary-action"
                    isDisabled={taskActionLoading}
                    isPending={taskActionLoading}
                    onPress={handleCreateReconciliationTask}
                    size="sm"
                    variant="secondary"
                  >
                    <Plus aria-hidden="true" size={16} />
                    新建批次
                  </Button>
                ) : null}
              </div>
              {loading ? <StatePanel tone="loading" compact>加载中。</StatePanel> : null}
              {batchListError ? <StatePanel tone="error" compact>{batchListError}</StatePanel> : null}
              {!loading && !batchListError && visibleBatches.length === 0 ? <StatePanel tone="empty" compact>无匹配批次。</StatePanel> : null}
              <ul className="etc-batch-list" aria-label="ETC批次列表">
                {visibleBatches.map((batch) => {
                  const taskRow = batch.sourceType === "reconciliation_task"
                    ? reconciliationTasks.find((task) => task.taskId === batch.id) ?? null
                    : null;
                  const deletable = taskRow ? canDeleteTask(taskRow) : canDeleteBatch(batch);
                  const batchTitle = batch.externalBatchId || batch.etcBatchId;
                  const businessBatch = businessBatches.find((item) => item.businessBatchId === batch.id);
                  const rowLinkedTask = taskRow ?? (
                    businessBatch?.taskId
                      ? reconciliationTasks.find((task) => task.taskId === businessBatch.taskId) ?? null
                      : null
                  );
                  const selected = taskRow ? selectedTaskId === taskRow.taskId : selectedBatchId === batch.id;
                  const rowStartDate = rowLinkedTask?.periodStart ?? batch.passageStartDate;
                  const rowEndDate = rowLinkedTask?.periodEnd ?? batch.passageEndDate;
                  const rowCountText = rowLinkedTask
                    ? taskCountText(rowLinkedTask)
                    : batch.displayCountText || taskCountText({ etcInvoiceCount: batch.etcInvoiceCount, supplementCount: batch.supplementCount });
                  const rowAmount = rowLinkedTask && Number(rowLinkedTask.oaTotalAmount) > 0
                    ? rowLinkedTask.oaTotalAmount
                    : batch.totalAmount;
                  const rowAmountText = rowLinkedTask
                    ? `金额 ${formatMoney(rowAmount)} 元`
                    : `${batch.invoiceCount} 张 / ${formatMoney(batch.totalAmount)} 元`;
                  return (
                    <li
                      key={batch.id}
                      className={`etc-batch-row ${batch.status}`}
                      data-testid={taskRow ? `etc-reconciliation-task-row-${taskRow.taskId}` : `etc-batch-row-${batch.id}`}
                    >
                      <button
                        type="button"
                        className="etc-list-row-button"
                        aria-label={`查看ETC批次 ${batchTitle}`}
                        aria-current={selected ? "true" : undefined}
                        data-selected={selected ? "true" : undefined}
                        onClick={() => {
                          if (taskRow) {
                            setSelectedTaskId(taskRow.taskId);
                            setSelectedBatchId("");
                            setBatchDetail(null);
                            setBusinessBatchDetail(null);
                            return;
                          }
                          setBatchDetail(null);
                          setSelectedBatchId(batch.id);
                          if (businessBatch?.taskId) {
                            setSelectedTaskId(businessBatch.taskId);
                          }
                        }}
                      >
                        <span className="etc-row-title">
                          <strong>{formatShortDateRange(rowStartDate, rowEndDate)}</strong>
                          <StatusChip tone={businessBatch ? businessBatchTone(businessBatch.status) : (batch.status === "submitted" ? "success" : "primary")}>
                            {businessBatch ? businessBatchStatusLabel(businessBatch.status) : batchStatusLabel(batch.status)}
                          </StatusChip>
                        </span>
                        <span className="etc-batch-fields">
                          <span>{batchTitle}</span>
                          <span>{rowCountText}</span>
                          <span>{rowAmountText}</span>
                          {businessBatch?.importAttempts.length ? <span>导入记录 {businessBatch.importAttempts.length} 次</span> : <span>{batch.plateCount} 个车牌</span>}
                          {batch.status === "submitted" && batchOaLabel(batch) ? <span>{batchOaLabel(batch)}</span> : null}
                        </span>
                      </button>
                      <button
                        type="button"
                        className="etc-icon-action etc-icon-action--danger"
                        aria-label={deletable ? `删除批次 ${batchTitle}` : deleteBatchDisabledReason(batch)}
                        title={deletable ? "删除批次" : deleteBatchDisabledReason(batch)}
                        disabled={!deletable || deleteSubmitting}
                        onClick={(event) => {
                          if (taskRow) {
                            openDeleteTaskDialog(taskRow, event);
                            return;
                          }
                          openDeleteBatchDialog(batch, event);
                        }}
                      >
                        <Trash2 aria-hidden="true" size={16} />
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>

            <div className="etc-right-column">
              {activeStatus === "unsubmitted" ? (
              <section className="etc-reconciliation-workspace" aria-label="ETC批次流程">
                <div className="etc-reconciliation-workspace-content">
                  <div className="etc-detail-heading">
                    <div>
                      <h2>批次流程</h2>
                      <p>{selectedTask ? `${formatTaskTitle(selectedTask)} / v${selectedTask.version}` : "选择左侧批次，或新建批次。"}</p>
                    </div>
                    <div className="etc-section-actions">
                      {selectedTask && selectedTask.status === "ready_for_import" ? (
                        <Button className="etc-secondary-action" isDisabled={taskActionLoading} onPress={handleReopenReconciliationTask} size="sm" variant="secondary">
                          重新打开
                        </Button>
                      ) : null}
                      <Button
                        className="etc-primary-action"
                        isDisabled={!selectedTask || !canConfirmSelectedTask || taskActionLoading}
                        isPending={taskActionLoading}
                        onPress={handleConfirmReconciliationTask}
                        size="sm"
                        variant="primary"
                      >
                        确认对账
                      </Button>
                      <Button
                        className="etc-secondary-action"
                        isDisabled={!selectedTask}
                        onPress={() => {
                          setWorkflowExpandedKeys((current) =>
                            current.size > 0
                              ? new Set()
                              : new Set(["upload", "sources", "review", "reconciliation", "imported"])
                          );
                        }}
                        size="sm"
                        variant="secondary"
                      >
                        {workflowExpandedKeys.size > 0 ? "全部折叠" : "展开流程"}
                      </Button>
                    </div>
                  </div>

                  <div id="etc-reconciliation-task-content">
                    {taskLoading ? <StatePanel tone="loading" compact>加载中。</StatePanel> : null}
                    {taskListError ? <StatePanel tone="error" compact>{taskListError}</StatePanel> : null}
                    {!taskLoading && !taskListError && selectedTask ? (
                      <div className="etc-reconciliation-task-content">
                        <div className="etc-workflow-command-strip" aria-label="本次确认预览">
                          <div>
                            <span>金额</span>
                            <strong>{formatMoney(selectedReconciliationSummary.oaTotalAmount)}</strong>
                          </div>
                          <div>
                            <span>范围</span>
                            <strong>{formatDateRange(selectedReconciliationSummary.periodStart, selectedReconciliationSummary.periodEnd)}</strong>
                          </div>
                          <div>
                            <span>数量</span>
                            <strong>{taskCountText(selectedReconciliationSummary)}</strong>
                          </div>
                        </div>

                        <DisclosureGroup
                          allowsMultipleExpanded
                          className="etc-disclosure-group"
                          expandedKeys={workflowExpandedKeys}
                          onExpandedChange={setWorkflowExpandedKeys}
                        >
                          <EtcDisclosureSection
                            id="upload"
                            title="上传文件"
                            summary="信用卡账单 / 票根网"
                            meta={<CountChip>{selectedTask.sourceFiles.length} 个文件</CountChip>}
                          >
                            <div className="etc-upload-blocks" aria-label="ETC对账文件上传">
                              <div className="etc-upload-drop-grid" aria-label="ETC导入动作">
                                <UploadBlock
                                  label="信用卡账单"
                                  accept=".pdf,application/pdf"
                                  helperText="拖拽 PDF 到这里，或点击选择文件。"
                                  disabled={!taskIsMutable || taskActionLoading}
                                  onFiles={handleUploadCreditCardStatement}
                                />
                                <UploadBlock
                                  label="票根网"
                                  accept=".txt,text/plain"
                                  helperText="支持多个 TXT 文件。"
                                  multiple
                                  disabled={!taskIsMutable || taskActionLoading || hasLegacyNonTxtTicketRootSource}
                                  disabledReason={hasLegacyNonTxtTicketRootSource ? "已有非 TXT 来源，删除后可导入。" : undefined}
                                  onFiles={handleUploadTicketRootFiles}
                                />
                              </div>
                            </div>
                          </EtcDisclosureSection>

                          <EtcDisclosureSection
                            id="sources"
                            title="已上传文件"
                            summary={selectedTask.sourceFiles.length === 0 ? "暂无文件" : `${selectedTask.sourceFiles.length} 个来源`}
                            meta={<CountChip>{selectedTask.sourceFiles.length} 个文件</CountChip>}
                          >
                            <section aria-label="已上传文件">
                              <div className="etc-source-file-section">
                                {selectedTask.sourceFiles.length === 0 ? (
                                  <StatePanel tone="empty" compact>暂无文件。</StatePanel>
                                ) : (
                                  <ul className="etc-source-file-list" aria-label="已上传文件列表">
                                    {selectedTask.sourceFiles.map((sourceFile) => {
                                      const sourceSummary = ticketRootSourceSummaryBySourceFileId.get(sourceFile.fileId);
                                      return (
                                        <li
                                          key={sourceFile.fileId}
                                          className="etc-source-file-row"
                                        >
                                          <div className="etc-source-file-main">
                                            <div className="etc-source-file-title">
                                              <strong>{sourceFile.originalName || sourceFile.fileId}</strong>
                                              <span className="etc-status-tag">{sourceKindLabel(sourceFile.sourceKind)}</span>
                                              {sourceSummary ? (
                                                <>
                                                  <span className="etc-status-tag">{sourceSummary.plateLabel} / 已解析 {sourceSummary.parsedCount} 条</span>
                                                  <span className="etc-status-tag">金额合计 {sourceSummary.totalAmount}</span>
                                                  <span className="etc-status-tag">日期 {sourceSummary.dateRange}</span>
                                                </>
                                              ) : null}
                                              {sourceFile.hasBlockingIssue ? <span className="etc-status-tag etc-status-tag--error">blocking</span> : null}
                                            </div>
                                            {sourceSummary ? (
                                              <span className="etc-source-file-id">{sourceSummary.dateRange}</span>
                                            ) : null}
                                          </div>
                                          <button
                                            type="button"
                                            className="etc-icon-action etc-icon-action--danger"
                                            aria-label={taskIsMutable ? `删除源文件 ${sourceFile.originalName}` : "已确认/已导入批次不能删除源文件"}
                                            title={taskIsMutable ? "删除源文件" : "已确认/已导入批次不能删除源文件"}
                                            disabled={!taskIsMutable || taskActionLoading || deleteSubmitting}
                                            onClick={(event) => openDeleteSourceFileDialog(sourceFile, event)}
                                          >
                                            <Trash2 aria-hidden="true" size={16} />
                                          </button>
                                        </li>
                                      );
                                    })}
                                  </ul>
                                )}
                              </div>
                            </section>
                          </EtcDisclosureSection>

                          <EtcDisclosureSection
                            id="review"
                            title="人工处理"
                            summary={selectedCardItem ? `${selectedCardItem.transactionDate} / ${formatMoney(selectedCardItem.settlementAmount)}` : "选择信用卡侧明细"}
                            meta={<StatusChip tone={selectedCardItem ? "primary" : "default"}>{selectedCardItem ? "已选择" : "待选择"}</StatusChip>}
                          >
                            <section className="etc-manual-review-panel" aria-label="人工核对处理">
                              <div className="etc-manual-review-grid">
                                <div className="etc-manual-review-card">
                                  <span className="etc-manual-review-label">当前信用卡项</span>
                                  <strong>{selectedCardItem ? `${selectedCardItem.transactionDate} / ${formatMoney(selectedCardItem.settlementAmount)}` : "未选择"}</strong>
                                  <span>{selectedCardItem?.description ?? "点击信用卡侧明细行后处理。"}</span>
                                </div>
                                <div className="etc-manual-review-card">
                                  <span className="etc-manual-review-label">推荐票根</span>
                                  <strong>{suggestedTicket ? `${suggestedTicket.vehiclePlate} / ${formatMoney(suggestedTicket.amount)}` : "无可接受建议"}</strong>
                                  <span>{suggestedTicket ? "金额与信用卡项一致，可人工确认后接受。" : "仅在推荐候选命中时可直接接受。"}</span>
                                </div>
                                <label className="etc-manual-review-field">
                                  <span>选择票根/凭证</span>
                                  <select
                                    value={selectedEvidenceRowId}
                                    onChange={(event) => setSelectedEvidenceRowId(event.target.value)}
                                    disabled={!taskIsMutable || taskActionLoading}
                                  >
                                    <option value="">选择一条记录</option>
                                    {evidenceRows.map((item) => (
                                      <option key={item.id} value={item.id}>
                                        {item.source === "ticket" ? "票根" : "补充"} / {formatMoney(item.amount)} / {item.plateOrMerchant}
                                      </option>
                                    ))}
                                  </select>
                                </label>
                              </div>
                              <label className="etc-manual-review-field">
                                <span>处理说明</span>
                                <input
                                  value={reviewNote}
                                  onChange={(event) => setReviewNote(event.target.value)}
                                  placeholder="排除、异常或手工确认时必填"
                                  disabled={!taskIsMutable || taskActionLoading}
                                />
                              </label>
                              <div className="etc-manual-review-actions">
                                <button
                                  type="button"
                                  className="etc-primary-action"
                                  disabled={!taskIsMutable || taskActionLoading || !selectedCardItem || !suggestedTicket}
                                  onClick={handleAcceptSuggestedTicket}
                                >
                                  接受推荐票根
                                </button>
                                <button
                                  type="button"
                                  className="etc-secondary-action"
                                  disabled={!taskIsMutable || taskActionLoading || !selectedCardItem || !selectedEvidenceRow}
                                  onClick={handleLinkSelectedEvidence}
                                >
                                  关联所选记录
                                </button>
                                <button
                                  type="button"
                                  className="etc-secondary-action etc-secondary-action--warning"
                                  disabled={!taskIsMutable || taskActionLoading || !selectedCardItem}
                                  onClick={() => handleExcludeCard("excluded_non_etc")}
                                >
                                  排除非ETC
                                </button>
                                <button
                                  type="button"
                                  className="etc-secondary-action etc-secondary-action--warning"
                                  disabled={!taskIsMutable || taskActionLoading || !selectedCardItem}
                                  onClick={() => handleExcludeCard("excluded_error")}
                                >
                                  标记异常
                                </button>
                                <button
                                  type="button"
                                  className="etc-secondary-action"
                                  disabled={!taskIsMutable || taskActionLoading || !selectedCardItem}
                                  onClick={handleManualConfirmCard}
                                >
                                  手工确认
                                </button>
                              </div>
                            </section>
                          </EtcDisclosureSection>

                          {selectedTask.parseIssues.length > 0 ? (
                            <EtcDisclosureSection
                              id="issues"
                              title="解析异常"
                              summary={`${selectedTask.parseIssues.length} 条`}
                              meta={<StatusChip tone="warning">{selectedTask.parseIssues.length} 条</StatusChip>}
                            >
                              <div className="etc-source-issue-list">
                                {selectedTask.parseIssues.map((issue) => (
                                  <div
                                    key={issue.issueId || `${issue.fileId}-${issue.sourcePage ?? ""}-${issue.sourceLine ?? ""}-${issue.message}`}
                                    role="alert"
                                    className={`etc-source-issue etc-source-issue--${issue.severity === "blocking" ? "error" : "warning"}`}
                                  >
                                    <div className="etc-source-issue__header">
                                      <strong>{issue.originalName || issue.fileId || "未知文件"}</strong>
                                      <span className="etc-status-tag">{sourceKindLabel(issue.sourceKind)}</span>
                                      {parseIssueContextLabel(issue) ? (
                                        <span>{parseIssueContextLabel(issue)}</span>
                                      ) : null}
                                    </div>
                                    <p>{issue.message}</p>
                                  </div>
                                ))}
                              </div>
                            </EtcDisclosureSection>
                          ) : null}

                          <EtcDisclosureSection
                            id="reconciliation"
                            title="双侧核对"
                            summary={`${reconciliationRows.length} 行 / 已选 ${selectedReconciliationRowIds.size}`}
                            meta={<CountChip>{pairedReconciliationRowIds.length} 个配对</CountChip>}
                          >
                            <div
                              className="etc-reconciliation-table-block"
                              style={{ "--etc-reconciliation-row-height": "32px" } as CSSProperties}
                            >
                              <div className="etc-reconciliation-table-toolbar">
                                <span className="etc-count-tag">{reconciliationRows.length} 行</span>
                                <button
                                  type="button"
                                  className="etc-secondary-action"
                                  disabled={reconciliationRows.length === 0}
                                  onClick={handleSelectAllReconciliationRows}
                                >
                                  全选
                                </button>
                                <button
                                  type="button"
                                  className="etc-secondary-action"
                                  disabled={pairedReconciliationRowIds.length === 0}
                                  onClick={handleSelectPairedReconciliationRows}
                                >
                                  全选配对项
                                </button>
                                <button
                                  type="button"
                                  className="etc-secondary-action"
                                  disabled={selectedReconciliationRowIds.size === 0}
                                  onClick={handleClearReconciliationSelection}
                                >
                                  清空
                                </button>
                                <button
                                  type="button"
                                  className="etc-secondary-action"
                                  title="重新计算匹配"
                                  disabled={!selectedTask || taskActionLoading}
                                  onClick={handleRefreshReconciliationMatches}
                                >
                                  <RefreshCw aria-hidden="true" size={16} />
                                  刷新匹配
                                </button>
                              </div>
                              <div className="etc-reconciliation-table-container">
                                <table
                                  aria-label="ETC双侧核对明细"
                                  className="etc-reconciliation-table"
                                >
                                  <thead>
                                    <tr>
                                      <th className="etc-reconciliation-select-column" aria-label="选择列" />
                                      <th className="etc-reconciliation-table-side-heading" colSpan={3}>
                                        信用卡侧
                                      </th>
                                      <th className="etc-reconciliation-table-side-heading etc-reconciliation-divider" colSpan={2}>
                                        票根/补充凭证侧
                                      </th>
                                    </tr>
                                    <tr>
                                      <th className="etc-reconciliation-select-column">选择</th>
                                      <th className="etc-reconciliation-date-column">交易日</th>
                                      <th className="etc-reconciliation-description-column">交易描述</th>
                                      <th className="etc-reconciliation-amount-column">金额</th>
                                      <th className="etc-reconciliation-time-column etc-reconciliation-divider">交易时间</th>
                                      <th className="etc-reconciliation-evidence-column">金额 / 车牌</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {reconciliationRows.map((row) => (
                                      <tr
                                        key={row.id}
                                        className="etc-reconciliation-table-row"
                                        data-testid={`etc-reconciliation-row-${row.id}`}
                                        data-highlight={row.highlight || undefined}
                                      >
                                        <td className="etc-reconciliation-select-column">
                                          <input
                                            type="checkbox"
                                            checked={selectedReconciliationRowIds.has(row.id)}
                                            onChange={() => handleToggleReconciliationRow(row.id)}
                                            onClick={(event) => event.stopPropagation()}
                                            aria-label={`选择核对行 ${row.id}`}
                                          />
                                        </td>
                                        <td
                                          className="etc-reconciliation-card-cell etc-reconciliation-date-column"
                                          data-highlight={row.cardHighlight || undefined}
                                          onClick={() => row.card && setSelectedCardItemId(row.card.itemId)}
                                        >
                                          {renderCardDateCell(row.card)}
                                        </td>
                                        <td
                                          className="etc-reconciliation-card-cell etc-reconciliation-description-column"
                                          data-testid={row.card ? `etc-reconciliation-card-cell-${row.card.itemId}` : undefined}
                                          data-highlight={row.cardHighlight || undefined}
                                          onClick={() => row.card && setSelectedCardItemId(row.card.itemId)}
                                        >
                                          {renderCardDescriptionCell(row.card)}
                                        </td>
                                        <td
                                          className="etc-reconciliation-card-cell etc-reconciliation-amount-column"
                                          data-highlight={row.cardHighlight || undefined}
                                          onClick={() => row.card && setSelectedCardItemId(row.card.itemId)}
                                        >
                                          {renderCardAmountCell(row.card)}
                                        </td>
                                        <td
                                          className="etc-reconciliation-evidence-side-cell etc-reconciliation-time-column etc-reconciliation-divider"
                                          data-highlight={row.evidenceHighlight || undefined}
                                          onClick={() => row.evidence && setSelectedEvidenceRowId(row.evidence.id)}
                                        >
                                          {renderEvidenceTimeCell(row.evidence)}
                                        </td>
                                        <td
                                          className="etc-reconciliation-evidence-side-cell etc-reconciliation-evidence-column"
                                          data-testid={row.evidence ? `etc-reconciliation-evidence-cell-${row.evidence.id}` : undefined}
                                          data-highlight={row.evidenceHighlight || undefined}
                                          onClick={() => row.evidence && setSelectedEvidenceRowId(row.evidence.id)}
                                        >
                                          {renderEvidenceSummaryCell(row.evidence, row.card)}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          </EtcDisclosureSection>

                          {showTaskImportedInvoices ? (
                            <EtcDisclosureSection
                              id="imported"
                              title="已导入发票"
                              summary={importedInvoiceCount > 0 ? `${importedInvoiceCount} 张 / ${importedInvoiceAmount}` : "暂无明细"}
                              meta={Number(importedInvoiceAmount) > 0 ? <StatusChip tone="success">合计 {importedInvoiceAmount}</StatusChip> : null}
                            >
                              <section className="etc-task-imported-invoices" aria-label="已导入ETC发票">
                                <div className="etc-section-heading etc-section-heading--compact">
                                  {canRemoveImportedInvoices ? (
                                    <button
                                      type="button"
                                      className="etc-secondary-action etc-secondary-action--warning"
                                      disabled={removeImportedInvoicesSubmitting || taskActionLoading}
                                      onClick={() => setRemoveImportedInvoicesDialogOpen(true)}
                                    >
                                      <Trash2 aria-hidden="true" size={16} />
                                      移除发票
                                    </button>
                                  ) : null}
                                </div>
                                {!selectedTaskImportBatchId ? (
                                  <StatePanel tone="info" compact>确认后导入 ZIP。</StatePanel>
                                ) : taskImportDetailError ? (
                                  <StatePanel tone="error" compact>{taskImportDetailError}</StatePanel>
                                ) : (
                                  renderEtcInvoiceTable(
                                    taskImportBatchDetail?.invoiceItems ?? [],
                                    {
                                      ariaLabel: "已导入ETC发票明细",
                                      emptyText: "暂无明细。",
                                      loadingText: taskImportDetailLoading ? "加载中。" : "",
                                      tableKey: selectedTaskImportBatchId,
                                    },
                                  )
                                )}
                              </section>
                            </EtcDisclosureSection>
                          ) : null}
                        </DisclosureGroup>

                        {selectedTaskBusinessBatch && isOaConfirmationPendingStatus(selectedTaskBusinessBatch.status)
                          ? renderOaStatusPanel(selectedTaskBusinessBatch)
                          : null}
                      </div>
                    ) : !taskLoading && !taskListError ? (
                      <StatePanel tone="empty">暂无批次流程。</StatePanel>
                    ) : null}
                  </div>
                </div>
              </section>
              ) : null}

              <section className="etc-batch-detail-panel" aria-label="ETC批次详情">
                <div className="etc-batch-detail-content">
                  <div className="etc-detail-heading">
                    <div>
                      <h2>批次详情</h2>
                      <p>{selectedBatch ? selectedBatch.externalBatchId || selectedBatch.etcBatchId : "选择左侧批次。"}</p>
                    </div>
                    {selectedBatch ? (
                      <Button
                        className="etc-secondary-action"
                        onPress={() => {
                          setBatchDetailExpandedKeys((current) =>
                            current.size > 0 ? new Set() : new Set(["summary", "invoices", "attempts"])
                          );
                        }}
                        size="sm"
                        variant="secondary"
                      >
                        {batchDetailExpandedKeys.size > 0 ? "全部折叠" : "展开详情"}
                      </Button>
                    ) : null}
                  </div>
                  <div id="etc-batch-detail-content">
                    {!selectedBatch ? (
                      <StatePanel tone="empty">选择左侧批次。</StatePanel>
                    ) : (
                      <div className="etc-batch-detail-content">
                  <div className="etc-detail-heading">
                    <div>
                      <div className="etc-detail-title-line">
                        <h2>{selectedBatch.externalBatchId || selectedBatch.etcBatchId}</h2>
                        <StatusChip tone={selectedBusinessBatch ? businessBatchTone(selectedBusinessBatch.status) : (selectedBatch.status === "submitted" ? "success" : "primary")}>
                          {selectedBusinessBatch ? businessBatchStatusLabel(selectedBusinessBatch.status) : batchStatusLabel(selectedBatch.status)}
                        </StatusChip>
                      </div>
                      {selectedBatch.status === "submitted" && batchOaLabel(selectedBatch) ? (
                        <p>{batchOaLabel(selectedBatch)}</p>
                      ) : null}
                    </div>
                  </div>

                  {selectedBusinessBatch
                    && isOaConfirmationPendingStatus(selectedBusinessBatch.status)
                    && (
                      activeStatus !== "unsubmitted"
                      || !selectedTaskBusinessBatch
                      || selectedTaskBusinessBatch.businessBatchId !== selectedBusinessBatch.businessBatchId
                    )
                    ? renderOaStatusPanel(selectedBusinessBatch)
                    : null}

                  <DisclosureGroup
                    allowsMultipleExpanded
                    className="etc-disclosure-group etc-disclosure-group--detail"
                    expandedKeys={batchDetailExpandedKeys}
                    onExpandedChange={setBatchDetailExpandedKeys}
                  >
                    <EtcDisclosureSection
                      id="summary"
                      title="批次摘要"
                      summary={`${selectedBatch.invoiceCount} 张 / ${formatMoney(selectedBatch.totalAmount)}`}
                      meta={<StatusChip tone={selectedBatch.status === "submitted" ? "success" : "primary"}>{batchStatusLabel(selectedBatch.status)}</StatusChip>}
                    >
                      <div className="etc-detail-metrics" aria-label="批次指标">
                        <div>
                          <span>总金额</span>
                          <strong>{formatMoney(selectedBatch.totalAmount)}</strong>
                        </div>
                        <div>
                          <span>发票数</span>
                          <strong>{selectedBatch.invoiceCount} 张</strong>
                        </div>
                        <div>
                          <span>开票日期</span>
                          <strong>{formatDateRange(selectedBatch.issueStartDate, selectedBatch.issueEndDate)}</strong>
                        </div>
                        <div>
                          <span>通行日期</span>
                          <strong>{formatDateRange(selectedBatch.passageStartDate, selectedBatch.passageEndDate)}</strong>
                        </div>
                      </div>

                      <div className="etc-plate-summary" aria-label="车牌汇总">
                        {selectedBatch.plateSummary.map((item) => (
                          <div key={item.plateNumber} className="etc-plate-summary-item">
                            <strong>{item.plateNumber || "未记录车牌"}</strong>
                            <span>{item.invoiceCount} 张</span>
                            <strong>{formatMoney(item.totalAmount)}</strong>
                          </div>
                        ))}
                      </div>
                    </EtcDisclosureSection>

                    <EtcDisclosureSection
                      id="invoices"
                      title="发票明细"
                      summary={`${invoiceRows.length} 行`}
                      meta={<CountChip>{invoiceRows.length} 行</CountChip>}
                    >
                      {detailLoading ? <StatePanel tone="loading" compact>加载中。</StatePanel> : null}
                      {batchDetailError ? (
                        <StatePanel tone="error" compact>{batchDetailError}</StatePanel>
                      ) : renderEtcInvoiceTable(
                        invoiceRows,
                        {
                          ariaLabel: "ETC发票明细",
                          emptyText: "暂无明细。",
                          loadingText: detailLoading ? "加载中。" : "",
                          tableKey: selectedBatchId,
                        },
                      )}
                    </EtcDisclosureSection>

                    {selectedBusinessBatch?.importAttempts.length ? (
                      <EtcDisclosureSection
                        id="attempts"
                        title="导入记录"
                        summary={`${selectedBusinessBatch.importAttempts.length} 次`}
                        meta={<CountChip>{selectedBusinessBatch.importAttempts.length} 次</CountChip>}
                      >
                        <section className="etc-import-attempts" aria-label="导入记录">
                          <div className="etc-import-attempt-list">
                            {selectedBusinessBatch.importAttempts.map((attempt, index) => (
                              <div key={attempt.attemptId || `${attempt.importBatchId}-${index}`} className="etc-import-attempt-row">
                                <strong>{attempt.importBatchId || `第 ${index + 1} 次导入`}</strong>
                                <span>
                                  导入 {attempt.imported}，重复 {attempt.duplicatesSkipped}，补齐 {attempt.attachmentsCompleted}，失败 {attempt.failed}
                                </span>
                                <span>{splitDateTimeParts(attempt.createdAt).date}</span>
                              </div>
                            ))}
                          </div>
                        </section>
                      </EtcDisclosureSection>
                    ) : null}
                  </DisclosureGroup>
                      </div>
                    )}
                  </div>
                </div>
              </section>
            </div>
          </div>
        </div>

        <AppDialog
          open={Boolean(supplementUploadCard)}
          title="上传补充凭证"
          description="补充凭证会直接覆盖当前信用卡项；金额不一致或无法识别时，差异说明会进入审计和 OA 提交口径。"
          onClose={closeSupplementUploadDialog}
          actions={
            <>
              <button type="button" className="etc-secondary-action" onClick={closeSupplementUploadDialog} disabled={supplementUploadSubmitting}>取消</button>
              <button
                type="button"
                className="etc-primary-action"
                onClick={() => void handleUploadSupplementForCard()}
                disabled={supplementUploadSubmitting || supplementUploadFiles.length === 0}
              >
                {supplementUploadSubmitting ? "正在上传..." : "上传并覆盖"}
              </button>
            </>
          }
        >
          {supplementUploadCard ? (
            <div className="etc-dialog-stack">
              <div className="etc-supplement-upload-target">
                <span>信用卡项</span>
                <strong>{supplementUploadCard.transactionDate} / {formatMoney(supplementUploadCard.settlementAmount)}</strong>
                <p>{supplementUploadCard.description || "-"}</p>
              </div>
              <label
                className={`etc-file-picker${supplementUploadSubmitting ? " etc-file-picker--disabled" : ""}`}
              >
                <UploadCloud aria-hidden="true" size={16} />
                {supplementUploadFiles.length > 0 ? supplementUploadFiles.map((file) => file.name).join("、") : "选择补充凭证文件"}
                <input
                  aria-label="选择补充凭证文件"
                  hidden
                  type="file"
                  accept=".pdf,.jpg,.jpeg,image/jpeg,application/pdf"
                  disabled={supplementUploadSubmitting}
                  onChange={(event) => {
                    setSupplementUploadFiles(Array.from(event.target.files ?? []));
                    event.target.value = "";
                  }}
                />
              </label>
              <label className="etc-dialog-field">
                <span>差异说明</span>
                <textarea
                  value={supplementUploadNote}
                  onChange={(event) => setSupplementUploadNote(event.target.value)}
                  placeholder="金额不一致、金额无法识别或业务特殊情况时必填"
                  disabled={supplementUploadSubmitting}
                  rows={3}
                />
              </label>
            </div>
          ) : null}
        </AppDialog>

        <AppDialog
          open={Boolean(deleteTarget)}
          title={deleteTarget?.kind === "task" ? "删除批次" : deleteTarget?.kind === "sourceFile" ? "删除源文件" : "删除批次"}
          description={deleteTarget?.kind === "task"
            ? deleteTaskDescription(deleteTarget.item)
            : deleteTarget?.kind === "sourceFile"
              ? "将删除该上传源文件及其解析结果、解析错误和解析产物。"
              : deleteTarget?.kind === "batch"
                ? deleteBatchDescription(deleteTarget)
                : ""}
          onClose={() => {
            if (!deleteSubmitting) {
              setDeleteTarget(null);
            }
          }}
          actions={
            <>
              <button type="button" className="etc-secondary-action" onClick={() => setDeleteTarget(null)} disabled={deleteSubmitting}>取消</button>
              <button type="button" className="etc-danger-action" onClick={handleDeleteConfirmed} disabled={deleteSubmitting}>
                {deleteSubmitting ? "正在删除..." : "确认删除"}
              </button>
            </>
          }
        >
          {deleteTarget?.kind === "task" ? (
            <div className="etc-dialog-detail-list">
              <p>批次：{formatTaskTitle(deleteTarget.item)}</p>
              <p>期间：{formatDateRange(deleteTarget.item.periodStart, deleteTarget.item.periodEnd)}</p>
              <p>数量：{taskCountText(deleteTarget.item)}</p>
              {deleteTarget.item.status === "imported" || deleteTarget.item.hasImportedInvoices ? (
                <p className="etc-dialog-warning">将一并删除已导入发票；如需恢复，需重新确认并导入 ZIP。</p>
              ) : null}
              <p>版本：v{deleteTarget.item.version}</p>
            </div>
          ) : deleteTarget?.kind === "sourceFile" ? (
            <div className="etc-dialog-detail-list">
              <p>文件：{deleteTarget.item.originalName || deleteTarget.item.fileId}</p>
              <p>类型：{sourceKindLabel(deleteTarget.item.sourceKind)}</p>
              <p>批次：{formatTaskTitle(deleteTarget.task)}</p>
              <p>版本：v{deleteTarget.task.version}</p>
            </div>
          ) : deleteTarget?.kind === "batch" ? (
            <div className="etc-dialog-detail-list">
              <p>批次：{deleteTarget.item.externalBatchId || deleteTarget.item.etcBatchId}</p>
              <p>通行期间：{formatDateRange(deleteTarget.item.passageStartDate, deleteTarget.item.passageEndDate)}</p>
              <p>数量：{deleteTarget.item.displayCountText || taskCountText({ etcInvoiceCount: deleteTarget.item.etcInvoiceCount, supplementCount: deleteTarget.item.supplementCount })}</p>
              <p>金额：{formatMoney(deleteTarget.item.totalAmount)} 元</p>
            </div>
          ) : null}
        </AppDialog>

        <AppDialog
          open={removeImportedInvoicesDialogOpen}
          title="移除发票"
          description="清空本批次下已导入发票，批次可重新导入。"
          onClose={() => {
            if (!removeImportedInvoicesSubmitting) {
              setRemoveImportedInvoicesDialogOpen(false);
            }
          }}
          actions={
            <>
              <button
                type="button"
                className="etc-secondary-action"
                onClick={() => setRemoveImportedInvoicesDialogOpen(false)}
                disabled={removeImportedInvoicesSubmitting}
              >
                取消
              </button>
              <button
                type="button"
                className="etc-secondary-action etc-secondary-action--warning"
                onClick={() => void handleRemoveImportedInvoices()}
                disabled={removeImportedInvoicesSubmitting}
              >
                {removeImportedInvoicesSubmitting ? "正在移除..." : "确认移除"}
              </button>
            </>
          }
        >
          {selectedTask ? (
            <div className="etc-dialog-detail-list">
              <p>批次：{formatTaskTitle(selectedTask)}</p>
              <p>期间：{formatDateRange(selectedTask.periodStart, selectedTask.periodEnd)}</p>
              <p>已导入：{importedInvoiceCount} 张</p>
              <p>版本：v{selectedTask.version}</p>
            </div>
          ) : null}
        </AppDialog>

        <AppDialog
          open={createDialogOpen}
          title={draftResult ? "OA提交确认" : "创建OA草稿"}
          onClose={() => setCreateDialogOpen(false)}
          actions={
            draftResult ? (
              <>
                {draftResult.oaDraftUrl ? (
                  <button
                    type="button"
                    className="etc-secondary-action"
                    onClick={handleOpenCurrentDraft}
                  >
                    <ExternalLink aria-hidden="true" size={16} />
                    打开草稿
                  </button>
                ) : null}
                <button
                  type="button"
                  className="etc-primary-action"
                  disabled={oaActionLoading}
                  onClick={() => void handleManualBusinessBatchOaStatus("submitted")}
                >
                  <CheckCircle2 aria-hidden="true" size={16} />
                  已提交
                </button>
                <button
                  type="button"
                  className="etc-secondary-action"
                  disabled={oaActionLoading}
                  onClick={() => void handleManualBusinessBatchOaStatus("not_submitted")}
                >
                  <XCircle aria-hidden="true" size={16} />
                  未提交
                </button>
                <button type="button" className="etc-secondary-action" onClick={() => setCreateDialogOpen(false)}>关闭</button>
              </>
            ) : (
              <>
                <button type="button" className="etc-secondary-action" onClick={() => setCreateDialogOpen(false)}>取消</button>
                <button type="button" className="etc-primary-action" onClick={handleCreateDraft} disabled={draftCreating}>
                  {draftCreating ? "正在创建..." : "创建草稿"}
                </button>
              </>
            )
          }
        >
          {draftResult ? (
            <div className="etc-dialog-detail-list">
              <p>OA草稿已创建，等待提交确认。</p>
              <p>批次：{draftResult.etcBatchId}</p>
            </div>
          ) : (
            <div className="etc-dialog-detail-list">
              <p>{currentOaDraftDescription}</p>
              <p>批次：{currentOaDraftBatchLabel || "-"}</p>
            </div>
          )}
        </AppDialog>
      </PageScaffold>
    </div>
  );
}
