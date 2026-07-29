import {
  ArrowRight,
  CheckCircle2,
  Download,
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
import PageBusinessAuditIcon from "../components/common/PageBusinessAuditIcon";
import PageScaffold from "../components/common/PageScaffold";
import PageStatisticsPopover from "../components/common/PageStatisticsPopover";
import StatePanel from "../components/common/StatePanel";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { useBackgroundJobProgress } from "../features/backgroundJobs/BackgroundJobProgressProvider";
import {
  EtcApiError,
  confirmEtcReconciliationTask,
  createEtcBusinessBatch,
  createEtcBusinessBatchOaDraft,
  deleteEtcBusinessBatch,
  deleteEtcReconciliationSourceFile,
  downloadEtcBusinessBatchInvoicePdf,
  fetchEtcBusinessBatchDetail,
  fetchEtcBusinessBatches,
  fetchEtcReconciliationTask,
  manualEtcBusinessBatchOaStatus,
  patchEtcReconciliationItem,
  refreshEtcReconciliationMatches,
  reopenEtcReconciliationTask,
  updateEtcBusinessBatchTitle,
  uploadEtcCreditCardStatement,
  uploadEtcSupplementEvidenceForCard,
  uploadEtcTicketRootFiles,
} from "../features/etc/api";
import { buildEtcOaDraftReviewUrl } from "../features/etc/oaNavigation";
import type {
  EtcBusinessBatchCounts,
  EtcBusinessBatchDetail,
  EtcBusinessBatchBucket,
  EtcBusinessBatchStatus,
  EtcBusinessBatchSummary,
  EtcCreditCardItem,
  EtcInvoice,
  EtcPageStatistics,
  EtcReconciliationTask,
  EtcSourceFile,
  EtcSupplementEvidence,
  EtcTicketRootItem,
} from "../features/etc/types";

const initialCounts: EtcBusinessBatchCounts = {
  unsubmitted: 0,
  staged: 0,
  submitted: 0,
};

const MANUAL_OA_SUBMITTED_REASON = "用户确认已在 OA 系统完成 OA 草稿提交。";
const MANUAL_OA_NOT_SUBMITTED_REASON = "用户确认已在 OA 系统删除 OA 草稿。";

function formatMoney(value: string | number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return String(value);
  }
  return parsed.toFixed(2);
}

function moneyDifference(left: string | number, right: string | number) {
  const leftCents = Math.round(Number(left) * 100);
  const rightCents = Math.round(Number(right) * 100);
  if (!Number.isFinite(leftCents) || !Number.isFinite(rightCents)) {
    return "0.00";
  }
  return (Math.abs(leftCents - rightCents) / 100).toFixed(2);
}

function sumInvoiceMoney(items: EtcInvoice[], key: "totalAmount" | "taxAmount") {
  const totalCents = items.reduce((sum, item) => {
    const parsed = Number(item[key]);
    return Number.isFinite(parsed) ? sum + Math.round(parsed * 100) : sum;
  }, 0);
  return (totalCents / 100).toFixed(2);
}

function sumInvoiceTotalAmount(items: EtcInvoice[]) {
  return sumInvoiceMoney(items, "totalAmount");
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
    oa_confirmation_pending: "待确认提交",
    oa_submitted: "已提交审批",
    not_submitted: "未提交审批",
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

function businessBatchListBucket(status: EtcBusinessBatchStatus): EtcBusinessBatchBucket | null {
  if (isSubmittedBusinessStatus(status)) {
    return "submitted";
  }
  if (status === "oa_confirmation_pending") {
    return "staged";
  }
  if (status === "deleted" || status === "superseded") {
    return null;
  }
  return "unsubmitted";
}

function businessBatchBelongsToBatchStatus(status: EtcBusinessBatchStatus, activeStatus: EtcBusinessBatchBucket) {
  return businessBatchListBucket(status) === activeStatus;
}

function transitionBusinessBatchCounts(
  counts: EtcBusinessBatchCounts,
  previousStatus: EtcBusinessBatchStatus | null,
  nextStatus: EtcBusinessBatchStatus,
): EtcBusinessBatchCounts {
  const previousBucket = previousStatus ? businessBatchListBucket(previousStatus) : null;
  const nextBucket = businessBatchListBucket(nextStatus);
  if (previousBucket === nextBucket) {
    return counts;
  }
  const nextCounts = { ...counts };
  if (previousBucket === "submitted") {
    nextCounts.submitted = Math.max(0, nextCounts.submitted - 1);
  } else if (previousBucket === "staged") {
    nextCounts.staged = Math.max(0, nextCounts.staged - 1);
  } else if (previousBucket === "unsubmitted") {
    nextCounts.unsubmitted = Math.max(0, nextCounts.unsubmitted - 1);
  }
  if (nextBucket === "submitted") {
    nextCounts.submitted += 1;
  } else if (nextBucket === "staged") {
    nextCounts.staged += 1;
  } else if (nextBucket === "unsubmitted") {
    nextCounts.unsubmitted += 1;
  }
  return nextCounts;
}

function isOaConfirmationPendingStatus(status: EtcBusinessBatchStatus) {
  return status === "oa_confirmation_pending";
}

function formatMonthName(value: string | null | undefined) {
  const [year, month] = String(value || "").split("-");
  if (!year || !month) {
    return "";
  }
  const parsedMonth = Number(month);
  return Number.isFinite(parsedMonth) && parsedMonth > 0 ? `${parsedMonth}月` : "";
}

function monthFromBatchIdentifier(value: string | null | undefined) {
  const text = String(value || "");
  const dashed = text.match(/(20\d{2})[-/年](0?[1-9]|1[0-2])/);
  if (dashed) {
    return `${dashed[1]}-${String(dashed[2]).padStart(2, "0")}`;
  }
  const compact = text.match(/(20\d{2})(0[1-9]|1[0-2])(?:\d{2})?/);
  return compact ? `${compact[1]}-${compact[2]}` : "";
}

function batchDisplayTitle(
  batch: Pick<EtcBusinessBatchSummary, "scopeMonth" | "externalEtcBatchId" | "businessBatchId" | "title">,
) {
  const explicitTitle = String(batch.title ?? "").trim();
  if (explicitTitle) {
    return explicitTitle;
  }
  const monthLabel = formatMonthName(
    batch.scopeMonth
    || monthFromBatchIdentifier(batch.externalEtcBatchId)
    || monthFromBatchIdentifier(batch.businessBatchId),
  );
  if (monthLabel) {
    return `${monthLabel}批次`;
  }
  return "未记录月份批次";
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
    .replace(/OA\s*草稿/g, "审批草稿")
    .replace(/ETC对账任务/g, "ETC批次流程")
    .replace(/对账任务/g, "批次");
}

function taskCountText(task: Pick<EtcReconciliationTask, "etcInvoiceCount" | "supplementCount">) {
  return `发票 ${task.etcInvoiceCount} + 补充凭证 ${task.supplementCount}`;
}

function taskHasSubmittedConfirmation(task: Pick<EtcReconciliationTask, "status" | "submittedConfirmedAt">) {
  return task.status === "closed" || Boolean(task.submittedConfirmedAt?.trim());
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
  headerAction?: ReactNode;
  children: ReactNode;
  className?: string;
};

function EtcDisclosureSection({
  id,
  title,
  summary,
  meta,
  headerAction,
  children,
  className,
}: EtcDisclosureSectionProps) {
  return (
    <Disclosure id={id} className={["etc-disclosure-section", className ?? ""].filter(Boolean).join(" ")}>
      <div className="etc-disclosure-header">
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
        {headerAction ? <div className="etc-disclosure-header-action">{headerAction}</div> : null}
      </div>
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
  | { kind: "businessBatch"; batchId: string; expectedVersion?: number };

type DeleteTarget =
  | { kind: "batch"; item: EtcBusinessBatchSummary; plan: BatchDeletePlan }
  | { kind: "sourceFile"; task: EtcReconciliationTask; item: EtcSourceFile };

function businessBatchInvoiceMetrics(batch: EtcBusinessBatchSummary | EtcBusinessBatchDetail) {
  const invoiceItems = "invoiceItems" in batch ? batch.invoiceItems : [];
  const issueDates = invoiceItems.map((invoice) => invoice.issueDate).filter(Boolean).sort();
  const passageDates = invoiceItems
    .flatMap((invoice) => [invoice.passageStartDate, invoice.passageEndDate])
    .filter((value): value is string => Boolean(value))
    .sort();
  const plateCounts = new Map<string, { invoiceCount: number; totalAmount: number }>();
  invoiceItems.forEach((invoice) => {
    const plateNumber = invoice.plateNumber || "未识别车牌";
    const current = plateCounts.get(plateNumber) ?? { invoiceCount: 0, totalAmount: 0 };
    current.invoiceCount += 1;
    const amount = Number(invoice.totalAmount);
    current.totalAmount += Number.isFinite(amount) ? amount : 0;
    plateCounts.set(plateNumber, current);
  });
  return {
    issueStartDate: issueDates[0] ?? null,
    issueEndDate: issueDates[issueDates.length - 1] ?? null,
    passageStartDate: passageDates[0] ?? null,
    passageEndDate: passageDates[passageDates.length - 1] ?? null,
    plateCount: plateCounts.size,
    plateSummary: Array.from(plateCounts.entries()).map(([plateNumber, item]) => ({
      plateNumber,
      invoiceCount: item.invoiceCount,
      totalAmount: item.totalAmount.toFixed(2),
    })),
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
  const { active, activationGeneration } = useOptionalPageActivation("etc-tickets");
  const { jobs } = useBackgroundJobProgress();
  const { canMutateData } = useSessionPermissions();
  const [activeStatus, setActiveStatus] = useState<EtcBusinessBatchBucket>("unsubmitted");
  const [plate, setPlate] = useState("");
  const [keyword, setKeyword] = useState("");
  const [counts, setCounts] = useState(initialCounts);
  const [statistics, setStatistics] = useState<EtcPageStatistics | null>(null);
  const [businessBatches, setBusinessBatches] = useState<EtcBusinessBatchSummary[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [businessBatchDetail, setBusinessBatchDetail] = useState<EtcBusinessBatchDetail | null>(null);
  const [detailReloadKey, setDetailReloadKey] = useState(0);
  const [selectedTask, setSelectedTask] = useState<EtcReconciliationTask | null>(null);
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
  const [batchListError, setBatchListError] = useState<string | null>(null);
  const [taskListError, setTaskListError] = useState<string | null>(null);
  const [batchDetailError, setBatchDetailError] = useState<string | null>(null);
  const [taskActionLoading, setTaskActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [workflowExpandedKeys, setWorkflowExpandedKeys] = useState<Set<Key>>(() => new Set(["upload", "reconciliation"]));
  const [batchDetailExpandedKeys, setBatchDetailExpandedKeys] = useState<Set<Key>>(() => new Set(["summary", "invoices"]));
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [draftCreating, setDraftCreating] = useState(false);
  const [invoicePdfDownloadingBatchId, setInvoicePdfDownloadingBatchId] = useState("");
  const [draftResult, setDraftResult] = useState<EtcBusinessBatchDetail | null>(null);
  const [draftOaAmount, setDraftOaAmount] = useState("0.00");
  const [oaActionDecision, setOaActionDecision] = useState<"submitted" | "not_submitted" | null>(null);
  const oaActionLoading = oaActionDecision !== null;
  const [editingBatchTitleId, setEditingBatchTitleId] = useState("");
  const [editingBatchTitle, setEditingBatchTitle] = useState("");
  const [titleSavingBatchId, setTitleSavingBatchId] = useState("");
  const refreshedImportJobIdsRef = useRef<Set<string>>(new Set());
  const oaDraftIntentRef = useRef<{ businessBatchId: string; idempotencyKey: string } | null>(null);
  const titleEditCancelRef = useRef(false);
  const selectedBatchIdRef = useRef(selectedBatchId);
  selectedBatchIdRef.current = selectedBatchId;
  const selectedBusinessBatchTaskId = businessBatches.find(
    (batch) => batch.businessBatchId === selectedBatchId,
  )?.taskId ?? "";

  const loadBatches = useCallback(async (
    signal?: AbortSignal,
    statusOverride?: EtcBusinessBatchBucket,
  ) => {
    setLoading(true);
    setBatchListError(null);
    setActionError(null);
    const effectiveStatus = statusOverride ?? activeStatus;
    try {
      const payload = await fetchEtcBusinessBatches({
        bucket: effectiveStatus,
        plate: plate.trim(),
        keyword: keyword.trim(),
        signal,
      });
      setBusinessBatches(payload.items);
      setCounts(payload.counts);
      setStatistics(payload.statistics ?? null);
      const currentSelection = selectedBatchIdRef.current;
      const nextSelection = payload.items.some((batch) => batch.businessBatchId === currentSelection)
        ? currentSelection
        : payload.items[0]?.businessBatchId ?? "";
      if (nextSelection !== currentSelection) {
        setSelectedTask(null);
        setTaskListError(null);
        setTaskLoading(Boolean(nextSelection));
      }
      selectedBatchIdRef.current = nextSelection;
      setSelectedBatchId(nextSelection);
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setStatistics(null);
        setBatchListError(formatEtcUiErrorMessage(caught, "ETC业务批次加载失败。"));
      }
    } finally {
      setLoading(false);
    }
  }, [activeStatus, keyword, plate]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    void loadBatches(controller.signal);
    return () => controller.abort();
  }, [active, activationGeneration, loadBatches]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    if (oaDraftIntentRef.current?.businessBatchId !== selectedBatchId) {
      oaDraftIntentRef.current = null;
    }
    if (!selectedBatchId) {
      setBusinessBatchDetail(null);
      setSelectedTask(null);
      setBatchDetailError(null);
      return undefined;
    }
    const controller = new AbortController();
    setSelectedTask(null);
    setDetailLoading(true);
    setTaskLoading(Boolean(selectedBusinessBatchTaskId));
    setTaskListError(selectedBusinessBatchTaskId ? null : "当前批次缺少绑定的 ETC 流程，请刷新后重试。");
    setBatchDetailError(null);
    setActionError(null);
    if (selectedBusinessBatchTaskId) {
      void fetchEtcReconciliationTask(selectedBusinessBatchTaskId, controller.signal)
        .then((task) => {
          if (!controller.signal.aborted) {
            setSelectedTask(task);
          }
        })
        .catch((caught) => {
          if (!(caught instanceof DOMException && caught.name === "AbortError")) {
            setSelectedTask(null);
            setTaskListError(formatEtcUiErrorMessage(caught, "ETC批次流程加载失败。"));
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setTaskLoading(false);
          }
        });
    }
    void fetchEtcBusinessBatchDetail(selectedBatchId, controller.signal)
      .then((detail) => {
        if (!controller.signal.aborted) {
          setBatchDetailError(null);
          setBusinessBatchDetail(detail);
        }
      })
      .catch((caught) => {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          if (isEtcBusinessBatchNotFoundError(caught, selectedBatchId)) {
            setBusinessBatches((current) => current.filter((batch) => batch.businessBatchId !== selectedBatchId));
            setSelectedBatchId((current) => (current === selectedBatchId ? "" : current));
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
  }, [active, activationGeneration, detailReloadKey, selectedBatchId, selectedBusinessBatchTaskId]);

  useEffect(() => {
    if (!active) {
      return;
    }
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
    void (async () => {
      await loadBatches();
      setDetailReloadKey((current) => current + 1);
    })();
  }, [active, jobs, loadBatches]);

  const selectedBusinessBatch = useMemo(
    () => businessBatchDetail ?? businessBatches.find((batch) => batch.businessBatchId === selectedBatchId) ?? null,
    [businessBatchDetail, businessBatches, selectedBatchId],
  );
  const selectedBatch = selectedBusinessBatch;
  const visibleBatches = businessBatches;
  const importedInvoiceCount = businessBatchDetail?.invoiceSummary.count ?? selectedTask?.importedInvoiceCount ?? 0;
  const importedInvoiceAmount = businessBatchDetail?.invoiceSummary.amount ?? selectedTask?.importedInvoiceAmount ?? "0.00";
  const showTaskImportedInvoices = Boolean(selectedTask && businessBatchDetail?.invoiceItems?.length);

  useEffect(() => {
    if (businessBatches.length === 0 && selectedBatchId) {
      setSelectedBatchId("");
      setBusinessBatchDetail(null);
      return;
    }
    if (visibleBatches.some((batch) => batch.businessBatchId === selectedBatchId)) {
      return;
    }
    const firstBusinessBatch = visibleBatches[0];
    setBusinessBatchDetail(null);
    setSelectedBatchId(firstBusinessBatch?.businessBatchId ?? "");
  }, [businessBatches.length, selectedBatchId, visibleBatches]);

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
  }, [selectedTask?.taskId]);

  const invoiceRows = businessBatchDetail?.invoiceItems ?? [];
  const businessBatchDeleteBlockReason = (_batch: EtcBusinessBatchSummary) => canMutateData ? "" : "当前账号仅支持查看和导出，不能删除 ETC 批次。";
  const canDeleteBusinessBatch = (batch: EtcBusinessBatchSummary) => !businessBatchDeleteBlockReason(batch);
  const deleteBatchDescription = (target: Extract<DeleteTarget, { kind: "batch" }>) => {
    if (isSubmittedBusinessStatus(target.item.status)) {
      return "将删除本地批次并取消发票合并，审批系统中的草稿和已提交记录不会删除。";
    }
    return "将删除本地批次及已导入内容，审批系统中的草稿和已提交记录不会删除。";
  };
  const batchDeletePlan = (batch: EtcBusinessBatchSummary): BatchDeletePlan => ({
    kind: "businessBatch",
    batchId: batch.businessBatchId,
    expectedVersion: batch.version,
  });
  const canDeleteBatch = (batch: EtcBusinessBatchSummary) => canDeleteBusinessBatch(batch);
  const deleteBusinessBatchDisabledReason = (batch: EtcBusinessBatchSummary) =>
    businessBatchDeleteBlockReason(batch) || "当前批次暂不可删除";
  const deleteBatchDisabledReason = (batch: EtcBusinessBatchSummary) => deleteBusinessBatchDisabledReason(batch);
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
  const currentBusinessBatch = selectedBusinessBatch;
  const currentOaDraftBatchId = currentBusinessBatch?.businessBatchId ?? "";
  const currentOaDraftBatchLabel = selectedBatch ? batchDisplayTitle(selectedBatch) : "";
  const oaDraftAmount = selectedTask?.oaTotalAmount ?? "0.00";
  const displayedOaDraftAmount = draftResult ? draftOaAmount : oaDraftAmount;
  const oaInvoiceAmountDifference = moneyDifference(oaDraftAmount, importedInvoiceAmount);
  const hasOaInvoiceAmountDifference = Number(oaInvoiceAmountDifference) > 0;
  const hasCurrentOaAmountContract = Boolean(
    selectedTask
    && currentBusinessBatch
    && selectedTask.taskId === currentBusinessBatch.taskId
    && !taskLoading,
  );
  const selectedBatchMetrics = useMemo(
    () => selectedBatch ? businessBatchInvoiceMetrics(selectedBatch) : null,
    [selectedBatch],
  );
  const canSubmitCurrentBatch = activeStatus === "unsubmitted"
    && canMutateData
    && currentBusinessBatch !== null
    && currentBusinessBatch.createOaDraftAction?.enabled === true
    && hasCurrentOaAmountContract
    && !detailLoading;
  const submitDisabledReason = !canMutateData
    ? "当前账号仅支持查看和导出，不能创建审批草稿。"
    : !hasCurrentOaAmountContract
      ? "正在加载对账任务金额。"
    : detailLoading
      ? "正在加载批次详情。"
      : currentBusinessBatch?.createOaDraftAction?.message || "当前批次缺少审批资格信息，请刷新后重试。";
  const currentOaActionBatch = useMemo(() => {
    if (draftResult) {
      return draftResult;
    }
    return currentBusinessBatch;
  }, [currentBusinessBatch, draftResult]);
  const taskMutationTarget = selectedTask?.taskId === selectedBusinessBatchTaskId && !taskLoading
    ? selectedTask
    : null;
  const taskIsMutable = Boolean(canMutateData && taskMutationTarget && ["draft", "reviewing"].includes(taskMutationTarget.status));
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
    setSelectedTask(task);
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
    if (!belongsToCurrentStatus) {
      setSelectedBatchId((current) => (current === batch.businessBatchId ? "" : current));
      setBusinessBatchDetail((current) => (current?.businessBatchId === batch.businessBatchId ? null : current));
    } else if ("invoiceItems" in batch) {
      setBusinessBatchDetail(batch);
    }
  }, [activeStatus, businessBatches]);

  const handleStatusChange = (nextStatus: EtcBusinessBatchBucket) => {
    if (nextStatus === activeStatus) {
      return;
    }
    setActiveStatus(nextStatus);
    setSelectedBatchId("");
    setBusinessBatchDetail(null);
  };

  const startBusinessBatchTitleEdit = (businessBatch: EtcBusinessBatchSummary) => {
    if (!canMutateData || activeStatus !== "unsubmitted") {
      return;
    }
    setEditingBatchTitleId(businessBatch.businessBatchId);
    setEditingBatchTitle(batchDisplayTitle(businessBatch));
    titleEditCancelRef.current = false;
    setActionError(null);
  };

  const cancelBusinessBatchTitleEdit = () => {
    titleEditCancelRef.current = true;
    setEditingBatchTitleId("");
    setEditingBatchTitle("");
  };

  const saveBusinessBatchTitle = async (
    businessBatch: EtcBusinessBatchSummary,
  ) => {
    if (titleSavingBatchId === businessBatch.businessBatchId) {
      return;
    }
    const title = editingBatchTitle.trim();
    if (!title) {
      setActionError("批次标题不能为空。");
      return;
    }
    if (title === batchDisplayTitle(businessBatch)) {
      cancelBusinessBatchTitleEdit();
      return;
    }
    setTitleSavingBatchId(businessBatch.businessBatchId);
    setActionError(null);
    try {
      const updatedBatch = await updateEtcBusinessBatchTitle(businessBatch.businessBatchId, {
        title,
        expectedVersion: businessBatch.version,
      });
      mergeBusinessBatch(updatedBatch, businessBatch.status);
      cancelBusinessBatchTitleEdit();
      setDetailReloadKey((current) => current + 1);
    } catch (caught) {
      setActionError(formatEtcUiErrorMessage(caught, "批次标题保存失败。"));
    } finally {
      setTitleSavingBatchId("");
    }
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
    if (!canMutateData) {
      setActionError("当前账号仅支持查看和导出，不能新建 ETC 批次。");
      return;
    }
    setTaskActionLoading(true);
    setActionError(null);
    try {
      const businessBatch = await createEtcBusinessBatch({});
      setBusinessBatches((current) => [
        businessBatch,
        ...current.filter((item) => item.businessBatchId !== businessBatch.businessBatchId),
      ]);
      const bucket = businessBatchListBucket(businessBatch.status);
      if (bucket === "unsubmitted") {
        setCounts((current) => ({ ...current, unsubmitted: current.unsubmitted + 1 }));
        setActiveStatus("unsubmitted");
      } else if (bucket === "staged") {
        setCounts((current) => ({ ...current, staged: current.staged + 1 }));
        setActiveStatus("staged");
      } else if (bucket === "submitted") {
        setCounts((current) => ({ ...current, submitted: current.submitted + 1 }));
        setActiveStatus("submitted");
      }
      setSelectedBatchId(businessBatch.businessBatchId);
      setBusinessBatchDetail(businessBatch);
    } catch (caught) {
      setActionError(formatEtcUiErrorMessage(caught, "新建 ETC 批次失败，请稍后重试。"));
    } finally {
      setTaskActionLoading(false);
    }
  };

  const handleUploadCreditCardStatement = async (files: File[]) => {
    if (!taskMutationTarget || files.length === 0) {
      return;
    }
    await runTaskAction(() => uploadEtcCreditCardStatement(taskMutationTarget.taskId, files[0], taskMutationTarget.version));
  };

  const handleUploadTicketRootFiles = async (files: File[]) => {
    if (!taskMutationTarget || files.length === 0) {
      return;
    }
    await runTaskAction(() => uploadEtcTicketRootFiles(taskMutationTarget.taskId, files, taskMutationTarget.version));
  };

  const handleRefreshReconciliationMatches = async () => {
    if (!taskMutationTarget) {
      return;
    }
    await runTaskAction(() => refreshEtcReconciliationMatches(taskMutationTarget.taskId));
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
    if (!taskMutationTarget || !supplementUploadCard || supplementUploadFiles.length === 0) {
      setActionError("请先选择补充凭证文件。");
      return;
    }
    setSupplementUploadSubmitting(true);
    setActionError(null);
    try {
      const task = await uploadEtcSupplementEvidenceForCard(
        taskMutationTarget.taskId,
        supplementUploadCard.itemId,
        supplementUploadFiles,
        taskMutationTarget.version,
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
    if (!taskMutationTarget || !selectedCardItem) {
      setActionError("请先选择一条信用卡账单明细。");
      return;
    }
    await runTaskAction(() => patchEtcReconciliationItem(taskMutationTarget.taskId, selectedCardItem.itemId, taskMutationTarget.version, payload));
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
    if (!taskMutationTarget) {
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
    if (!taskMutationTarget) {
      return;
    }
    if (selectedConfirmedCreditCardItemIds.length === 0) {
      setActionError("请先选择要确认的配对项。");
      return;
    }
    await runTaskAction(() => confirmEtcReconciliationTask(
      taskMutationTarget.taskId,
      taskMutationTarget.version,
      { confirmedCreditCardItemIds: selectedConfirmedCreditCardItemIds },
    ));
  };

  const handleReopenReconciliationTask = async () => {
    if (!taskMutationTarget) {
      return;
    }
    await runTaskAction(() => reopenEtcReconciliationTask(taskMutationTarget.taskId, taskMutationTarget.version));
  };

  const openDeleteBatchDialog = (batch: EtcBusinessBatchSummary, event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!canDeleteBatch(batch)) {
      return;
    }
    setActionError(null);
    setDeleteTarget({ kind: "batch", item: batch, plan: batchDeletePlan(batch) });
  };

  const openDeleteSourceFileDialog = (sourceFile: EtcSourceFile, event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!taskMutationTarget || !taskIsMutable) {
      return;
    }
    setActionError(null);
    setDeleteTarget({ kind: "sourceFile", task: taskMutationTarget, item: sourceFile });
  };

  const removeDeletedBatchFromState = (batchId: string) => {
    setBusinessBatches((current) => current.filter((batch) => batch.businessBatchId !== batchId));
    setSelectedBatchId((current) => (current === batchId ? "" : current));
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
  };

  const handleDeleteConfirmed = async () => {
    if (!deleteTarget) {
      return;
    }
    setDeleteSubmitting(true);
    setActionError(null);
    try {
      if (deleteTarget.kind === "sourceFile") {
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
        await deleteBusinessBatchByPlan(plan);
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
    if (!canMutateData || !currentBusinessBatch || !currentOaDraftBatchId || !hasCurrentOaAmountContract) {
      return;
    }
    setActionError(null);
    setDraftCreating(true);
    setDraftOaAmount(oaDraftAmount);
    const intent = oaDraftIntentRef.current?.businessBatchId === currentOaDraftBatchId
      ? oaDraftIntentRef.current
      : { businessBatchId: currentOaDraftBatchId, idempotencyKey: crypto.randomUUID() };
    oaDraftIntentRef.current = intent;
    try {
      const result = await createEtcBusinessBatchOaDraft(currentOaDraftBatchId, {
        expectedVersion: currentBusinessBatch.version,
        idempotencyKey: intent.idempotencyKey,
      });
      oaDraftIntentRef.current = null;
      mergeBusinessBatch(result);
      setDraftResult(result);
    } catch (caught) {
      if (caught instanceof EtcApiError && caught.code !== "oa_draft_outcome_unknown") {
        oaDraftIntentRef.current = null;
      }
      setActionError(formatEtcUiErrorMessage(caught, "审批草稿创建失败。"));
    } finally {
      setDraftCreating(false);
    }
  };

  const resolveOaActionBatch = (batch?: EtcBusinessBatchDetail | EtcBusinessBatchSummary | null) => {
    return batch ?? draftResult ?? currentOaActionBatch;
  };

  const openOaDraftUrl = (draftUrl: string) => {
    if (!draftUrl) {
      return;
    }
    window.open(buildEtcOaDraftReviewUrl(draftUrl), "_blank", "noopener,noreferrer");
  };

  const handleDownloadInvoicePdf = async (batch: EtcBusinessBatchDetail | EtcBusinessBatchSummary) => {
    setActionError(null);
    setInvoicePdfDownloadingBatchId(batch.businessBatchId);
    try {
      const result = await downloadEtcBusinessBatchInvoicePdf(batch.businessBatchId);
      if (typeof URL.createObjectURL !== "function") {
        throw new Error("当前浏览器不支持文件下载。");
      }
      const objectUrl = URL.createObjectURL(result.blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = result.fileName;
      anchor.rel = "noopener";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (caught) {
      setActionError(formatEtcUiErrorMessage(caught, "ETC 发票 PDF 下载失败。"));
    } finally {
      setInvoicePdfDownloadingBatchId("");
    }
  };

  const handleManualBusinessBatchOaStatus = async (
    decision: "submitted" | "not_submitted",
    batch?: EtcBusinessBatchDetail | EtcBusinessBatchSummary | null,
  ) => {
    const target = resolveOaActionBatch(batch);
    if (!canMutateData || !target) {
      return;
    }
    const reason = decision === "submitted" ? MANUAL_OA_SUBMITTED_REASON : MANUAL_OA_NOT_SUBMITTED_REASON;
    setOaActionDecision(decision);
    setActionError(null);
    try {
      const result = await manualEtcBusinessBatchOaStatus(target.businessBatchId, {
        decision,
        reason,
        expectedVersion: target.version,
      });
      mergeBusinessBatch(result, target.status);
      const nextStatus = decision === "submitted" ? "submitted" : "unsubmitted";
      setActiveStatus(nextStatus);
      setSelectedBatchId(result.businessBatchId);
      setDraftResult(null);
      setCreateDialogOpen(false);
      setDetailReloadKey((current) => current + 1);
    } catch (caught) {
      setActionError(formatEtcUiErrorMessage(caught, "人工处理失败。"));
    } finally {
      setOaActionDecision(null);
    }
  };

  const renderOaDecisionActions = (
    batch?: EtcBusinessBatchDetail | EtcBusinessBatchSummary | null,
  ) => (
    <div className="etc-oa-decision-actions">
      <button
        type="button"
        className="etc-oa-decision-button etc-oa-decision-button--submitted"
        aria-label="我已在 OA 系统上完成 OA 草稿的提交"
        aria-busy={oaActionDecision === "submitted"}
        disabled={!canMutateData || oaActionLoading}
        onClick={() => void handleManualBusinessBatchOaStatus("submitted", batch)}
      >
        <CheckCircle2 aria-hidden="true" size={20} />
        <span>
          <strong>我已在 OA 系统上完成 OA 草稿的提交</strong>
          <small>{oaActionDecision === "submitted" ? "正在处理…" : "该批次进入已提交状态"}</small>
        </span>
      </button>
      <button
        type="button"
        className="etc-oa-decision-button"
        aria-label="我已在 OA 系统上删除该 OA 草稿"
        aria-busy={oaActionDecision === "not_submitted"}
        disabled={!canMutateData || oaActionLoading}
        onClick={() => void handleManualBusinessBatchOaStatus("not_submitted", batch)}
      >
        <XCircle aria-hidden="true" size={20} />
        <span>
          <strong>我已在 OA 系统上删除该 OA 草稿</strong>
          <small>{oaActionDecision === "not_submitted" ? "正在处理…" : "本批次进入未提交状态"}</small>
        </span>
      </button>
    </div>
  );

  const renderOaStatusPanel = (batch: EtcBusinessBatchDetail | EtcBusinessBatchSummary) => (
    <section className="etc-oa-status-panel" aria-label="审批提交确认">
      <div className="etc-oa-status-header">
        <div>
          <strong>审批草稿已创建，等待提交确认。</strong>
          <p>请选择审批草稿的实际提交状态。</p>
        </div>
        <div className="etc-oa-status-utilities">
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
            className="etc-secondary-action"
            disabled={invoicePdfDownloadingBatchId === batch.businessBatchId}
            onClick={() => void handleDownloadInvoicePdf(batch)}
          >
            <Download aria-hidden="true" size={16} />
            {invoicePdfDownloadingBatchId === batch.businessBatchId ? "正在合并..." : "下载发票PDF"}
          </button>
        </div>
      </div>
      {renderOaDecisionActions(batch)}
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
  ) => {
    const totalAmount = sumInvoiceMoney(rows, "totalAmount");
    const totalTaxAmount = sumInvoiceMoney(rows, "taxAmount");

    return (
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
              <th className="etc-invoice-money-column">
                <span className="etc-invoice-header-total">
                  <span>金额</span>
                  <span>{totalAmount}</span>
                </span>
              </th>
              <th className="etc-invoice-tax-column">
                <span className="etc-invoice-header-total">
                  <span>税额</span>
                  <span>{totalTaxAmount}</span>
                </span>
              </th>
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
  };

  return (
    <div data-testid="etc-ticket-management-page">
      <PageScaffold
        className="etc-page"
        title="ETC票据"
        titleAccessory={
          <PageStatisticsPopover
            ariaLabel="ETC票据数据统计"
            loading={loading && !statistics}
            coreItems={[
              { label: "ETC 发票", value: statistics?.invoiceCount, unit: "张" },
              { label: "业务批次", value: statistics?.businessBatchCount, unit: "批" },
              { label: "已提交", value: statistics?.submittedBatchCount, unit: "批", tone: "success" },
            ]}
            detailItems={[
              { label: "未提交", value: statistics?.unsubmittedBatchCount, unit: "批", tone: "warning" },
              { label: "暂存", value: statistics?.draftBatchCount, unit: "批" },
              { label: "对账任务", value: statistics?.reconciliationTaskCount, unit: "个" },
              { label: "源文件", value: statistics?.sourceFileCount, unit: "个" },
              { label: "成功导入发票", value: statistics?.importedInvoiceCount, unit: "张", tone: "success" },
              { label: "已关联统一发票", value: statistics?.linkedCanonicalInvoiceCount, unit: "张" },
              { label: "OA 草稿批次", value: statistics?.oaDraftBatchCount, unit: "批" },
            ]}
          />
        }
        actions={
          <>
            <PageBusinessAuditIcon
              ariaLabel="Audit ETC票据管理"
              label="ETC票据管理"
              pageKey="etc-tickets"
            />
            <Button
              className="etc-secondary-action"
              isDisabled={loading || taskLoading}
              isPending={loading}
              onPress={() => {
                void loadBatches();
                setDetailReloadKey((current) => current + 1);
              }}
              size="sm"
              variant="secondary"
            >
              <RefreshCw aria-hidden="true" size={16} />
              刷新
            </Button>
            <RouterLink className="button button--sm button--outline etc-page-action-link" to="/imports/etc-invoices">
              导入发票
              <ArrowRight aria-hidden="true" size={16} />
            </RouterLink>
          </>
        }
      >
        <div className="etc-page-content">
          {actionError ? <StatePanel tone="error">{actionError}</StatePanel> : null}
          {!canMutateData ? (
            <StatePanel tone="warning" compact>
              当前账号仅支持查看和导出，不能创建审批草稿、人工确认、上传、删除或新建批次。
            </StatePanel>
          ) : null}

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
                if (next === "submitted" || next === "staged" || next === "unsubmitted") {
                  handleStatusChange(next);
                }
              }}
            >
              <ToggleButton id="unsubmitted" className="etc-status-segmented__button">
                未提交 {counts.unsubmitted}
              </ToggleButton>
              <ToggleButton id="staged" className="etc-status-segmented__button">
                <ToggleButtonGroup.Separator />
                暂存 {counts.staged}
              </ToggleButton>
              <ToggleButton id="submitted" className="etc-status-segmented__button">
                <ToggleButtonGroup.Separator />
                已提交 {counts.submitted}
              </ToggleButton>
            </ToggleButtonGroup>
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
                placeholder="批次、审批或发票"
                onChange={(event) => setKeyword(event.target.value)}
              />
            </label>
            {activeStatus === "unsubmitted" ? (
              <Button
                className="etc-primary-action"
                isDisabled={!canSubmitCurrentBatch || draftCreating}
                isPending={draftCreating}
                aria-label={canSubmitCurrentBatch ? "提交审批" : submitDisabledReason}
                onPress={() => setCreateDialogOpen(true)}
                size="sm"
                variant="primary"
              >
                提交审批
              </Button>
            ) : null}
            {activeStatus === "unsubmitted" && currentBusinessBatch && !canSubmitCurrentBatch ? (
              <span className="etc-action-disabled-reason" role="status">{submitDisabledReason}</span>
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
                    isDisabled={!canMutateData || taskActionLoading}
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
                  const deletable = canDeleteBatch(batch);
                  const selected = selectedBatchId === batch.businessBatchId;
                  const rowCountText = `发票 ${batch.invoiceSummary.count}`;
                  const rowAmountText = `${batch.invoiceSummary.count} 张 / ${formatMoney(batch.invoiceSummary.amount)} 元`;
                  const displayTitle = batchDisplayTitle(batch);
                  const rowExternalBatchId = batch.externalEtcBatchId;
                  const titleEditable = Boolean(canMutateData && activeStatus === "unsubmitted");
                  const titleEditing = editingBatchTitleId === batch.businessBatchId;
                  const titleSaving = titleSavingBatchId === batch.businessBatchId;
                  const selectRow = () => {
                    setBusinessBatchDetail(null);
                    setSelectedTask(null);
                    setTaskListError(null);
                    setTaskLoading(true);
                    selectedBatchIdRef.current = batch.businessBatchId;
                    setSelectedBatchId(batch.businessBatchId);
                  };
                  return (
                    <li
                      key={batch.businessBatchId}
                      className={`etc-batch-row ${batch.status}`}
                      data-testid={`etc-batch-row-${batch.businessBatchId}`}
                    >
                      <div
                        role="button"
                        tabIndex={0}
                        className="etc-list-row-button"
                        aria-label={`查看批次 ${displayTitle}`}
                        aria-current={selected ? "true" : undefined}
                        data-selected={selected ? "true" : undefined}
                        onClick={selectRow}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            selectRow();
                          }
                        }}
                      >
                        <span className="etc-row-title">
                          {titleEditing ? (
                            <input
                              className="etc-batch-title-input"
                              aria-label={`批次标题 ${displayTitle}`}
                              value={editingBatchTitle}
                              disabled={titleSaving}
                              autoFocus
                              onChange={(event) => setEditingBatchTitle(event.target.value)}
                              onClick={(event) => event.stopPropagation()}
                              onKeyDown={(event) => {
                                event.stopPropagation();
                                if (event.key === "Escape") {
                                  event.preventDefault();
                                  cancelBusinessBatchTitleEdit();
                                  return;
                                }
                                if (event.key === "Enter") {
                                  event.preventDefault();
                                  event.currentTarget.blur();
                                }
                              }}
                              onBlur={() => {
                                if (titleEditCancelRef.current) {
                                  titleEditCancelRef.current = false;
                                  return;
                                }
                                void saveBusinessBatchTitle(batch);
                              }}
                            />
                          ) : titleEditable ? (
                            <button
                              type="button"
                              className="etc-batch-title-button"
                              aria-label={`编辑批次标题 ${displayTitle}`}
                              onKeyDown={(event) => {
                                event.stopPropagation();
                              }}
                              onClick={(event) => {
                                event.stopPropagation();
                                startBusinessBatchTitleEdit(batch);
                              }}
                            >
                              <strong>{displayTitle}</strong>
                            </button>
                          ) : (
                            <strong>{displayTitle}</strong>
                          )}
                          <StatusChip tone={businessBatchTone(batch.status)}>
                            {businessBatchStatusLabel(batch.status)}
                          </StatusChip>
                        </span>
                        <span className="etc-batch-fields">
                          {rowExternalBatchId ? <span>批次号 {rowExternalBatchId}</span> : null}
                          <span>{rowCountText}</span>
                          <span>{rowAmountText}</span>
                          {batch.oaRowId ? <span>OA {batch.oaRowId}</span> : null}
                        </span>
                      </div>
                      <button
                        type="button"
                        className="etc-icon-action etc-icon-action--danger"
                        aria-label={deletable ? `删除批次 ${displayTitle}` : deleteBatchDisabledReason(batch)}
                        title={deletable ? "删除批次" : deleteBatchDisabledReason(batch)}
                        disabled={!deletable || deleteSubmitting}
                        onClick={(event) => {
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
                        <Button className="etc-secondary-action" isDisabled={!taskMutationTarget || taskActionLoading} onPress={handleReopenReconciliationTask} size="sm" variant="secondary">
                          重新打开
                        </Button>
                      ) : null}
                      <Button
                        className="etc-primary-action"
                        isDisabled={!taskMutationTarget || !canConfirmSelectedTask || taskActionLoading}
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

                        <section className="etc-oa-amount-summary" aria-label="OA草稿金额口径">
                          <div>
                            <span>OA 草稿金额</span>
                            <strong>{formatMoney(oaDraftAmount)} 元</strong>
                            <small>来自已完成的对账任务</small>
                          </div>
                          <div>
                            <span>已导入 ETC 发票</span>
                            <strong>{importedInvoiceCount} 张 / {formatMoney(importedInvoiceAmount)} 元</strong>
                            <small>来自当前业务批次的实际发票</small>
                          </div>
                          {hasOaInvoiceAmountDifference ? (
                            <p role="status">
                              两者相差 {oaInvoiceAmountDifference} 元；OA 草稿仍按对账任务金额创建。
                            </p>
                          ) : (
                            <p>两项金额一致。</p>
                          )}
                        </section>

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
                                  disabled={!taskMutationTarget || taskActionLoading}
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
                                {renderEtcInvoiceTable(
                                  businessBatchDetail?.invoiceItems ?? [],
                                  {
                                    ariaLabel: "已导入ETC发票明细",
                                    emptyText: "暂无明细。",
                                    loadingText: detailLoading ? "加载中。" : "",
                                    tableKey: selectedBusinessBatch?.businessBatchId ?? "",
                                  },
                                )}
                              </section>
                            </EtcDisclosureSection>
                          ) : null}
                        </DisclosureGroup>

                        {selectedBusinessBatch && isOaConfirmationPendingStatus(selectedBusinessBatch.status)
                          ? renderOaStatusPanel(selectedBusinessBatch)
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
                      <p>{selectedBatch ? batchDisplayTitle(selectedBatch) : "选择左侧批次。"}</p>
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
                        <h2>{batchDisplayTitle(selectedBatch)}</h2>
                        <StatusChip tone={businessBatchTone(selectedBatch.status)}>
                          {businessBatchStatusLabel(selectedBatch.status)}
                        </StatusChip>
                      </div>
                      {selectedBatch.oaRowId ? <p>OA {selectedBatch.oaRowId}</p> : null}
                    </div>
                  </div>

                  {selectedBusinessBatch
                    && isOaConfirmationPendingStatus(selectedBusinessBatch.status)
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
                      summary={`${selectedBatch.invoiceSummary.count} 张 / ${formatMoney(selectedBatch.invoiceSummary.amount)}`}
                      meta={<StatusChip tone={businessBatchTone(selectedBatch.status)}>{businessBatchStatusLabel(selectedBatch.status)}</StatusChip>}
                    >
                      <div className="etc-detail-metrics" aria-label="批次指标">
                        <div>
                          <span>总金额</span>
                          <strong>{formatMoney(selectedBatch.invoiceSummary.amount)}</strong>
                        </div>
                        <div>
                          <span>发票数</span>
                          <strong>{selectedBatch.invoiceSummary.count} 张</strong>
                        </div>
                        <div>
                          <span>开票日期</span>
                          <strong>{formatDateRange(selectedBatchMetrics?.issueStartDate ?? null, selectedBatchMetrics?.issueEndDate ?? null)}</strong>
                        </div>
                        <div>
                          <span>通行日期</span>
                          <strong>{formatDateRange(selectedBatchMetrics?.passageStartDate ?? null, selectedBatchMetrics?.passageEndDate ?? null)}</strong>
                        </div>
                      </div>

                      <div className="etc-plate-summary" aria-label="车牌汇总">
                        {(selectedBatchMetrics?.plateSummary ?? []).map((item) => (
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
                      headerAction={isSubmittedBusinessStatus(selectedBatch.status) ? (
                        <button
                          type="button"
                          className="etc-secondary-action etc-disclosure-download-action"
                          aria-busy={invoicePdfDownloadingBatchId === selectedBatch.businessBatchId}
                          disabled={invoicePdfDownloadingBatchId === selectedBatch.businessBatchId}
                          onClick={() => void handleDownloadInvoicePdf(selectedBatch)}
                        >
                          <Download aria-hidden="true" size={16} />
                          {invoicePdfDownloadingBatchId === selectedBatch.businessBatchId ? "正在合并..." : "下载 PDF"}
                        </button>
                      ) : null}
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

                    {businessBatchDetail?.importAttempts.length ? (
                      <EtcDisclosureSection
                        id="attempts"
                        title="导入记录"
                        summary={`${businessBatchDetail.importAttempts.length} 次`}
                        meta={<CountChip>{businessBatchDetail.importAttempts.length} 次</CountChip>}
                      >
                        <section className="etc-import-attempts" aria-label="导入记录">
                          <div className="etc-import-attempt-list">
                            {businessBatchDetail.importAttempts.map((attempt, index) => (
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
          description="补充凭证会直接覆盖当前信用卡项；金额不一致或无法识别时，差异说明会进入审计和审批提交口径。"
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
          title={deleteTarget?.kind === "sourceFile" ? "删除源文件" : "删除批次"}
          description={deleteTarget?.kind === "sourceFile"
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
          {deleteTarget?.kind === "sourceFile" ? (
            <div className="etc-dialog-detail-list">
              <p>文件：{deleteTarget.item.originalName || deleteTarget.item.fileId}</p>
              <p>类型：{sourceKindLabel(deleteTarget.item.sourceKind)}</p>
              <p>批次：{formatTaskTitle(deleteTarget.task)}</p>
              <p>版本：v{deleteTarget.task.version}</p>
            </div>
          ) : deleteTarget?.kind === "batch" ? (
            <div className="etc-dialog-detail-list">
              <p>批次：{batchDisplayTitle(deleteTarget.item)}</p>
              <p>数量：发票 {deleteTarget.item.invoiceSummary.count}</p>
              <p>金额：{formatMoney(deleteTarget.item.invoiceSummary.amount)} 元</p>
            </div>
          ) : null}
        </AppDialog>

        <AppDialog
          open={createDialogOpen}
          title={draftResult ? "确认 OA 草稿处理结果" : "创建审批草稿"}
          onClose={() => setCreateDialogOpen(false)}
          disableEscapeClose={oaActionLoading}
          actions={
            draftResult ? (
              renderOaDecisionActions()
            ) : (
              <>
                <button type="button" className="etc-secondary-action" onClick={() => setCreateDialogOpen(false)}>取消</button>
                <button type="button" className="etc-primary-action" onClick={handleCreateDraft} disabled={!canMutateData || draftCreating}>
                  {draftCreating ? "正在创建..." : "创建草稿"}
                </button>
              </>
            )
          }
        >
          {draftResult ? (
            <div className="etc-oa-result-summary">
              <p>OA 草稿已创建。请根据你在 OA 系统中的实际操作选择结果。</p>
              <p>批次：{currentOaActionBatch ? batchDisplayTitle(currentOaActionBatch) : currentOaDraftBatchLabel || "-"}</p>
              <p>OA 草稿金额：<strong>{formatMoney(displayedOaDraftAmount)} 元</strong></p>
            </div>
          ) : (
            <div className="etc-dialog-detail-list etc-oa-create-summary">
              <p>OA 草稿金额：<strong>{formatMoney(oaDraftAmount)} 元</strong>（来自已完成的对账任务）</p>
              <p>已导入 ETC 发票：{importedInvoiceCount} 张 / {formatMoney(importedInvoiceAmount)} 元</p>
              {hasOaInvoiceAmountDifference ? (
                <p className="etc-dialog-warning">两者相差 {oaInvoiceAmountDifference} 元；OA 草稿仍按对账任务金额创建。</p>
              ) : null}
              <p>批次：{currentOaDraftBatchLabel || "-"}</p>
            </div>
          )}
        </AppDialog>
      </PageScaffold>
    </div>
  );
}
