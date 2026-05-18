import AddOutlinedIcon from "@mui/icons-material/AddOutlined";
import ArrowForwardOutlinedIcon from "@mui/icons-material/ArrowForwardOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import ExpandLessOutlinedIcon from "@mui/icons-material/ExpandLessOutlined";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import UndoOutlinedIcon from "@mui/icons-material/UndoOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent } from "react";
import { Link as RouterLink } from "react-router-dom";

import AppDialog from "../components/common/AppDialog";
import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import { useBackgroundJobProgress } from "../features/backgroundJobs/BackgroundJobProgressProvider";
import {
  confirmEtcBatchSubmitted,
  confirmEtcReconciliationTask,
  createEtcReconciliationTask,
  createEtcOaDraftForBatch,
  deleteEtcBatch,
  deleteEtcReconciliationTask,
  deleteEtcReconciliationTaskImportedInvoices,
  deleteEtcReconciliationSourceFile,
  fetchEtcBatchDetail,
  fetchEtcBatches,
  fetchEtcReconciliationTasks,
  markEtcBatchNotSubmitted,
  patchEtcReconciliationItem,
  refreshEtcReconciliationMatches,
  reopenEtcReconciliationTask,
  uploadEtcCreditCardStatement,
  uploadEtcSupplementEvidences,
  uploadEtcTicketRootFiles,
  uploadEtcTicketRootTexts,
} from "../features/etc/api";
import { buildEtcOaDraftReviewUrl } from "../features/etc/oaNavigation";
import type {
  EtcBatchCounts,
  EtcBatchDetail,
  EtcBatchStatus,
  EtcBatchSummary,
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
  return task.title || `对账任务 ${task.taskId}`;
}

function taskCountText(task: Pick<EtcReconciliationTask, "etcInvoiceCount" | "supplementCount">) {
  return `ETC票 ${task.etcInvoiceCount} + 补充凭证 ${task.supplementCount}`;
}

type UploadBlockProps = {
  label: string;
  accept: string;
  disabled: boolean;
  multiple?: boolean;
  onFiles: (files: File[]) => void;
};

function UploadBlock({ label, accept, disabled, multiple = false, onFiles }: UploadBlockProps) {
  return (
    <Button
      component="label"
      variant="outlined"
      startIcon={<UploadFileOutlinedIcon />}
      disabled={disabled}
      className="etc-upload-button"
    >
      {label}
      <input
        hidden
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          event.target.value = "";
          if (files.length > 0) {
            onFiles(files);
          }
        }}
      />
    </Button>
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

type TicketRootImportMode = "clipboard" | "textFile" | "file";

type TicketRootPasteBlock = {
  clientId: string;
  text: string;
  sourceFileId?: string;
  originalName?: string;
};

type TicketRootTextDialogState = {
  clientId: string;
  text: string;
} | null;

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

type DeleteTarget =
  | { kind: "batch"; item: EtcBatchSummary }
  | { kind: "task"; item: EtcReconciliationTask }
  | { kind: "sourceFile"; task: EtcReconciliationTask; item: EtcSourceFile };

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
    <Stack className="etc-reconciliation-description-cell" direction="row" spacing={0.5} alignItems="center">
      <Tooltip title={text} describeChild placement="top">
        <Typography
          ref={textRef}
          component="span"
          data-testid={`etc-reconciliation-description-${cardId}`}
          className={`etc-reconciliation-description ${expanded ? "etc-reconciliation-description--expanded" : "etc-reconciliation-description--collapsed"}`}
        >
          {text}
        </Typography>
      </Tooltip>
      {canExpand ? (
        <Button
          type="button"
          size="small"
          variant="text"
          className="etc-reconciliation-description-toggle"
          aria-label={`${expanded ? "收起" : "展开"}交易描述 ${cardId}`}
          onClick={(event) => {
            event.stopPropagation();
            onToggle();
          }}
        >
          {expanded ? "收起" : "展开"}
        </Button>
      ) : null}
    </Stack>
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
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [batchDetail, setBatchDetail] = useState<EtcBatchDetail | null>(null);
  const [taskImportBatchDetail, setTaskImportBatchDetail] = useState<EtcBatchDetail | null>(null);
  const [reconciliationTasks, setReconciliationTasks] = useState<EtcReconciliationTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [selectedCardItemId, setSelectedCardItemId] = useState("");
  const [selectedEvidenceRowId, setSelectedEvidenceRowId] = useState("");
  const [selectedReconciliationRowIds, setSelectedReconciliationRowIds] = useState<Set<string>>(() => new Set());
  const [expandedDescriptionRowIds, setExpandedDescriptionRowIds] = useState<Set<string>>(() => new Set());
  const [reviewNote, setReviewNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [taskLoading, setTaskLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [taskImportDetailLoading, setTaskImportDetailLoading] = useState(false);
  const [taskImportDetailError, setTaskImportDetailError] = useState<string | null>(null);
  const [taskActionLoading, setTaskActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [taskPanelExpanded, setTaskPanelExpanded] = useState(true);
  const [batchDetailPanelExpanded, setBatchDetailPanelExpanded] = useState(true);
  const [revokeDialogOpen, setRevokeDialogOpen] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [removeImportedInvoicesDialogOpen, setRemoveImportedInvoicesDialogOpen] = useState(false);
  const [removeImportedInvoicesSubmitting, setRemoveImportedInvoicesSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [draftCreating, setDraftCreating] = useState(false);
  const [draftResult, setDraftResult] = useState<EtcOaDraftPayload | null>(null);
  const [ticketRootImportMode, setTicketRootImportMode] = useState<TicketRootImportMode>("file");
  const [ticketRootPasteBlocks, setTicketRootPasteBlocks] = useState<TicketRootPasteBlock[]>([{ clientId: "paste-1", text: "" }]);
  const [ticketRootTextDialog, setTicketRootTextDialog] = useState<TicketRootTextDialogState>(null);
  const refreshedImportJobIdsRef = useRef<Set<string>>(new Set());

  const loadBatches = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setActionError(null);
    try {
      const payload = await fetchEtcBatches({
        status: activeStatus,
        month,
        plate: plate.trim(),
        keyword: keyword.trim(),
        signal,
      });
      setCounts(payload.counts);
      setBatches(payload.items);
      setSelectedBatchId((current) => {
        if (payload.items.some((batch) => batch.id === current)) {
          return current;
        }
        return payload.items[0]?.id ?? "";
      });
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setActionError(caught instanceof Error ? caught.message : "ETC批次加载失败。");
      }
    } finally {
      setLoading(false);
    }
  }, [activeStatus, keyword, month, plate]);

  const loadReconciliationTasks = useCallback(async (signal?: AbortSignal) => {
    setTaskLoading(true);
    try {
      const payload = await fetchEtcReconciliationTasks(signal);
      setReconciliationTasks(payload.items);
      setSelectedTaskId((current) => {
        if (payload.items.some((task) => task.taskId === current)) {
          return current;
        }
        return payload.items[0]?.taskId ?? "";
      });
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setActionError(caught instanceof Error ? caught.message : "ETC对账任务加载失败。");
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
      return undefined;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setActionError(null);
    void fetchEtcBatchDetail(selectedBatchId, controller.signal)
      .then((detail) => {
        if (!controller.signal.aborted) {
          setBatchDetail(detail);
        }
      })
      .catch((caught) => {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setActionError(caught instanceof Error ? caught.message : "ETC批次明细加载失败。");
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
    void loadBatches();
  }, [jobs, loadBatches]);

  const selectedBatch = useMemo(
    () => batchDetail ?? batches.find((batch) => batch.id === selectedBatchId) ?? null,
    [batchDetail, batches, selectedBatchId],
  );
  const selectedTask = useMemo(
    () => reconciliationTasks.find((task) => task.taskId === selectedTaskId) ?? null,
    [reconciliationTasks, selectedTaskId],
  );
  const taskImportBatchIds = useMemo(() => {
    const ids = new Set<string>();
    reconciliationTasks.forEach((task) => {
      if (task.etcBatchId) {
        ids.add(task.etcBatchId);
      }
      if (task.importBatchId) {
        ids.add(task.importBatchId);
      }
    });
    return ids;
  }, [reconciliationTasks]);
  const visibleBatches = useMemo(
    () => batches.filter((batch) =>
      !taskImportBatchIds.has(batch.id)
      && !taskImportBatchIds.has(batch.etcBatchId)
      && !taskImportBatchIds.has(batch.externalBatchId)
    ),
    [batches, taskImportBatchIds],
  );
  const selectedTaskImportBatchId = selectedTask?.importBatchId || "";
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
    && importedInvoiceCount > 0
    && !selectedTask.submittedConfirmedAt,
  );

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
    void fetchEtcBatchDetail(selectedTaskImportBatchId, controller.signal)
      .then((detail) => {
        if (!controller.signal.aborted) {
          setTaskImportBatchDetail(detail);
        }
      })
      .catch((caught) => {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setTaskImportDetailError(caught instanceof Error ? caught.message : "已导入ETC发票加载失败。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setTaskImportDetailLoading(false);
        }
      });
    return () => controller.abort();
  }, [selectedTaskImportBatchId]);

  useEffect(() => {
    if (batches.length === 0) {
      return;
    }
    if (visibleBatches.some((batch) => batch.id === selectedBatchId)) {
      return;
    }
    setBatchDetail(null);
    setSelectedBatchId(visibleBatches[0]?.id ?? "");
  }, [batches.length, selectedBatchId, visibleBatches]);
  const ticketRootManualSources = useMemo(
    () => (selectedTask?.sourceFiles ?? []).filter(isManualTicketRootSource),
    [selectedTask],
  );
  const ticketRootTextFileSources = useMemo(
    () => (selectedTask?.sourceFiles ?? []).filter(isTextFileTicketRootSource),
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
  const hasTicketRootTextFileSource = ticketRootTextFileSources.length > 0;
  const hasTicketRootDocumentSource = ticketRootDocumentSources.length > 0;

  useEffect(() => {
    setSelectedCardItemId("");
    setSelectedEvidenceRowId("");
    setSelectedReconciliationRowIds(new Set());
    setExpandedDescriptionRowIds(new Set());
    setReviewNote("");
  }, [selectedTaskId]);

  useEffect(() => {
    if (!selectedTask) {
      setTicketRootImportMode("file");
      setTicketRootPasteBlocks([{ clientId: "paste-1", text: "" }]);
      return;
    }
    if (ticketRootManualSources.length > 0) {
      setTicketRootImportMode("clipboard");
      setTicketRootPasteBlocks(
        ticketRootManualSources.map((sourceFile, index) => ({
          clientId: `paste-${index + 1}`,
          text: "",
          sourceFileId: sourceFile.fileId,
          originalName: sourceFile.originalName,
        })),
      );
      return;
    }
    if (ticketRootTextFileSources.length > 0) {
      setTicketRootImportMode("textFile");
      setTicketRootPasteBlocks([{ clientId: "paste-1", text: "" }]);
      return;
    }
    if (ticketRootDocumentSources.length > 0) {
      setTicketRootImportMode("file");
      setTicketRootPasteBlocks([{ clientId: "paste-1", text: "" }]);
      return;
    }
    setTicketRootPasteBlocks((current) => (current.length > 0 ? current : [{ clientId: "paste-1", text: "" }]));
  }, [selectedTask?.taskId, ticketRootManualSources, ticketRootTextFileSources, ticketRootDocumentSources, selectedTask]);

  const invoiceRows = batchDetail?.invoiceItems ?? [];
  const taskHasSubmittedLink = (task: EtcReconciliationTask) =>
    Boolean(task.submittedConfirmedAt?.trim());
  const canDeleteTask = (task: EtcReconciliationTask) =>
    ["draft", "reviewing", "ready_for_import", "imported"].includes(task.status) && !taskHasSubmittedLink(task);
  const deleteTaskDisabledReason = (task: EtcReconciliationTask) => {
    if (taskHasSubmittedLink(task)) {
      return "已确认提交OA，不能删除";
    }
    if (task.status === "importing") {
      return "导入中，不能删除";
    }
    if (task.status === "closed") {
      return "已关闭任务不能删除";
    }
    return "当前状态不能删除";
  };
  const deleteTaskDescription = (task: EtcReconciliationTask) => {
    if (task.status === "imported") {
      return "将删除该对账任务及其未进入 OA 链路的数据，并一并删除已导入 ETC 发票。用户需要重新导入时只能重新建/导。";
    }
    if (task.status === "ready_for_import") {
      return "将删除该对账任务及其未进入 OA 链路的数据。请确认相关上传文件、核对结果和待导入数据不再需要。";
    }
    return "将删除该对账任务、上传源文件和核对结果。已进入 OA/提交链路的数据不会被允许删除。";
  };
  const canDeleteBatch = (batch: EtcBatchSummary) => batch.status !== "submitted";
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
    const consumedEvidenceIds = new Set<string>();
    const rows: ReconciliationRow[] = [];

    selectedTask.creditCardItems.forEach((card) => {
      const linkedTicket = selectedTask.ticketRootItems.find((ticket) =>
        ticket.linkedCreditCardItemIds.includes(card.itemId)
      );
      const matchedEvidence = linkedTicket ? evidenceById.get(linkedTicket.itemId) ?? null : null;
      if (matchedEvidence) {
        consumedEvidenceIds.add(matchedEvidence.id);
      }

      const manual = manualHighlight(card.manualResolution);
      const rowHighlight = matchedEvidence ? "matched" : manual || "missing";
      rows.push({
        id: card.itemId,
        card,
        evidence: matchedEvidence,
        highlight: rowHighlight,
        cardHighlight: matchedEvidence ? "matched" : rowHighlight,
        evidenceHighlight: matchedEvidence ? "matched" : "",
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
    && taskImportBatchDetail
    && taskImportBatchDetail.status === "unsubmitted"
    && importedInvoiceCount > 0
    && !taskImportDetailLoading,
  );
  const currentOaDraftBatchId = selectedTaskImportBatchSelected ? selectedTaskImportBatchId : selectedBatchId;
  const currentOaDraftBatchLabel = selectedTaskImportBatchSelected
    ? (taskImportBatchDetail?.externalBatchId || taskImportBatchDetail?.etcBatchId || selectedTaskImportBatchId)
    : (selectedBatch?.externalBatchId || selectedBatch?.etcBatchId || "");
  const currentOaDraftDescription = selectedTaskImportBatchSelected
    ? `将为当前 ETC 对账任务下已导入的 ${importedInvoiceCount} 张发票创建 OA 支付申请草稿，发票合计 ${importedInvoiceAmount}。`
    : "将为当前 ETC 批次创建 OA 支付申请草稿。";
  const canSubmitCurrentBatch = activeStatus === "unsubmitted"
    && (selectedTaskImportBatchSelected
      ? selectedTaskImportBatchCanSubmit
      : Boolean(currentOaDraftBatchId) && selectedBatch?.status === "unsubmitted" && !detailLoading);
  const canRevokeCurrentBatch = activeStatus === "submitted" && Boolean(selectedBatchId) && !detailLoading;
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

  const handleStatusChange = (_event: MouseEvent<HTMLElement>, nextStatus: EtcBatchStatus | null) => {
    if (!nextStatus || nextStatus === activeStatus) {
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
      setActionError(caught instanceof Error ? caught.message : "ETC对账任务操作失败。");
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

  const handleTicketRootImportModeChange = (_event: MouseEvent<HTMLElement>, nextMode: TicketRootImportMode | null) => {
    if (!nextMode) {
      return;
    }
    setTicketRootImportMode(nextMode);
    if (nextMode === "clipboard") {
      setTicketRootPasteBlocks((current) => (current.length > 0 ? current : [{ clientId: "paste-1", text: "" }]));
    }
  };

  const openTicketRootTextDialog = (block: TicketRootPasteBlock) => {
    if (!taskIsMutable || hasTicketRootTextFileSource || hasTicketRootDocumentSource) {
      return;
    }
    setTicketRootTextDialog({ clientId: block.clientId, text: block.text });
  };

  const handleAddTicketRootPasteBlock = () => {
    setTicketRootPasteBlocks((current) => [
      ...current,
      { clientId: `paste-${current.length + 1}`, text: "" },
    ]);
  };

  const handleRemoveTicketRootPasteBlock = async (block: TicketRootPasteBlock) => {
    if (block.sourceFileId && selectedTask) {
      await runTaskAction(() => deleteEtcReconciliationSourceFile(selectedTask.taskId, block.sourceFileId ?? "", selectedTask.version));
      return;
    }
    setTicketRootPasteBlocks((current) => {
      const nextBlocks = current.filter((item) => item.clientId !== block.clientId);
      return nextBlocks.length > 0 ? nextBlocks : [{ clientId: "paste-1", text: "" }];
    });
  };

  const handleSubmitTicketRootText = async () => {
    if (!selectedTask || !ticketRootTextDialog) {
      return;
    }
    const text = ticketRootTextDialog.text.trim();
    if (!text) {
      setActionError("票根网文本不能为空。");
      return;
    }
    const entry = { clientId: ticketRootTextDialog.clientId, text };
    setTicketRootTextDialog(null);
    setTicketRootPasteBlocks((current) =>
      current.map((block) => (block.clientId === entry.clientId ? { ...block, text: entry.text } : block))
    );
    await runTaskAction(() => uploadEtcTicketRootTexts(selectedTask.taskId, [entry], selectedTask.version));
  };

  const handleUploadSupplementEvidences = async (files: File[]) => {
    if (!selectedTask || files.length === 0) {
      return;
    }
    await runTaskAction(() => uploadEtcSupplementEvidences(selectedTask.taskId, files, selectedTask.version, { evidenceKind: "non_etc_invoice" }));
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
      const task = await deleteEtcReconciliationTaskImportedInvoices(selectedTask.taskId, selectedTask.version);
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
      setActionError(caught instanceof Error ? caught.message : "已导入ETC发票移除失败。");
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
    setDeleteTarget({ kind: "batch", item: batch });
  };

  const openDeleteSourceFileDialog = (sourceFile: EtcSourceFile, event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!selectedTask || !taskIsMutable) {
      return;
    }
    setActionError(null);
    setDeleteTarget({ kind: "sourceFile", task: selectedTask, item: sourceFile });
  };

  const handleDeleteConfirmed = async () => {
    if (!deleteTarget) {
      return;
    }
    setDeleteSubmitting(true);
    setActionError(null);
    try {
      if (deleteTarget.kind === "task") {
        const taskId = deleteTarget.item.taskId;
        const wasSelectedTask = selectedTaskId === taskId;
        const removedBatchId = deleteTarget.item.etcBatchId || deleteTarget.item.importBatchId || "";
        await deleteEtcReconciliationTask(taskId, deleteTarget.item.version);
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
        const task = await deleteEtcReconciliationSourceFile(
          deleteTarget.task.taskId,
          deleteTarget.item.fileId,
          deleteTarget.task.version,
        );
        mergeReconciliationTask(task);
      } else {
        const batchId = deleteTarget.item.id;
        await deleteEtcBatch(batchId);
        setSelectedBatchId((current) => (current === batchId ? "" : current));
        if (selectedBatchId === batchId) {
          setBatchDetail(null);
        }
        await loadBatches();
      }
      setDeleteTarget(null);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "删除失败。");
    } finally {
      setDeleteSubmitting(false);
    }
  };

  const handleCreateDraft = async () => {
    if (!currentOaDraftBatchId) {
      return;
    }
    setActionError(null);
    setDraftCreating(true);
    const draftWindow = window.open("about:blank", "_blank");
    if (draftWindow) {
      draftWindow.opener = null;
    }
    try {
      const result = await createEtcOaDraftForBatch(currentOaDraftBatchId);
      setDraftResult(result);
      if (!result.oaDraftUrl) {
        throw new Error("OA 草稿地址为空，请在 OA 系统中手动查找刚创建的草稿。");
      }
      const reviewUrl = buildEtcOaDraftReviewUrl(result.oaDraftUrl);
      if (draftWindow && !draftWindow.closed) {
        draftWindow.location.href = reviewUrl;
      } else {
        window.location.assign(reviewUrl);
      }
    } catch (caught) {
      if (draftWindow && !draftWindow.closed) {
        draftWindow.close();
      }
      setActionError(caught instanceof Error ? caught.message : "OA 草稿创建失败。");
    } finally {
      setDraftCreating(false);
    }
  };

  const handleResultConfirmation = async (submitted: boolean) => {
    if (!draftResult?.batchId) {
      return;
    }
    setActionError(null);
    if (submitted) {
      await confirmEtcBatchSubmitted(draftResult.batchId);
    } else {
      await markEtcBatchNotSubmitted(draftResult.batchId);
    }
    setCreateDialogOpen(false);
    setDraftResult(null);
    await loadBatches();
    await loadReconciliationTasks();
  };

  const handleRevoke = async () => {
    if (!selectedBatchId) {
      return;
    }
    setActionError(null);
    await markEtcBatchNotSubmitted(selectedBatchId);
    setRevokeDialogOpen(false);
    await loadBatches();
  };

  const renderCardDateCell = (card: EtcCreditCardItem | null) => {
    if (!card) {
      return <span className="etc-reconciliation-empty">-</span>;
    }
    const transactionDate = splitDateParts(card.transactionDate);
    return (
      <Box className="etc-reconciliation-date-pair" data-testid={`etc-card-date-transaction-${card.itemId}`}>
        <span>{transactionDate}</span>
      </Box>
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
      <Stack className="etc-reconciliation-amount-cell" spacing={0.65} alignItems="center">
        <Typography component="span" className="etc-reconciliation-money">
          {formatMoney(card.settlementAmount)}
        </Typography>
      </Stack>
    );
  };

  const renderEvidenceTimeCell = (evidence: EvidenceRow | null) => {
    if (!evidence) {
      return <span className="etc-reconciliation-empty">未找到票根/凭证</span>;
    }
    const parts = splitDateTimeParts(evidence.transactionTime);
    const showFallback = parts.date === "-" && evidence.fallbackTimeLabel;
    return (
      <Stack className="etc-reconciliation-time-cell" spacing={0.35}>
        <span>{showFallback ? evidence.fallbackTimeLabel : parts.date}</span>
        {parts.time ? <span>{parts.time}</span> : null}
      </Stack>
    );
  };

  const renderEvidenceSummaryCell = (evidence: EvidenceRow | null) => {
    if (!evidence) {
      return <span className="etc-reconciliation-empty">-</span>;
    }
    return (
      <Stack className="etc-reconciliation-evidence-cell" spacing={0.7}>
        <Stack className="etc-reconciliation-chip-line" direction="row" spacing={0.75} flexWrap="wrap" useFlexGap alignItems="center" justifyContent="center">
          <Typography component="span" className="etc-reconciliation-money">
            {formatMoney(evidence.amount)}
          </Typography>
          <Chip label={evidence.plateOrMerchant || (evidence.source === "ticket" ? "未记录车牌" : "补充凭证")} size="small" variant="outlined" />
        </Stack>
        {evidence.source === "supplement" && evidence.tags.length > 0 ? (
          <Stack className="etc-reconciliation-chip-line" direction="row" spacing={0.5} flexWrap="wrap" useFlexGap justifyContent="center">
            {evidence.tags.map((tag) => <Chip key={tag} label={tag} size="small" color="warning" variant="outlined" />)}
          </Stack>
        ) : null}
      </Stack>
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
    <TableContainer className="etc-invoice-table-container">
      <Table
        key={tableKey}
        aria-label={ariaLabel}
        size="small"
        stickyHeader
        sx={{
          tableLayout: "fixed",
          width: "100%",
          "& .MuiTableCell-root": {
            borderColor: "#e2e8f0",
            color: "#243b53",
            overflowWrap: "anywhere",
          },
          "& .MuiTableCell-head": {
            backgroundColor: "#f4f7fb",
            fontWeight: 800,
          },
        }}
      >
        <TableHead>
          <TableRow>
            <TableCell sx={{ width: "17%" }}>发票号码</TableCell>
            <TableCell sx={{ width: "12%" }}>开票日期</TableCell>
            <TableCell sx={{ width: "15%" }}>通行日期</TableCell>
            <TableCell sx={{ width: "12%" }}>车牌</TableCell>
            <TableCell sx={{ width: "18%" }}>销方</TableCell>
            <TableCell sx={{ width: "9%" }} align="right">金额</TableCell>
            <TableCell sx={{ width: "8%" }} align="right">税额</TableCell>
            <TableCell sx={{ width: "9%" }}>附件状态</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={8} align="center">
                <Typography color="text.secondary" variant="body2">
                  {loadingText || emptyText}
                </Typography>
              </TableCell>
            </TableRow>
          ) : (
            rows.map((invoice) => (
              <TableRow key={invoice.id}>
                <TableCell>{invoice.invoiceNumber}</TableCell>
                <TableCell>{invoice.issueDate}</TableCell>
                <TableCell>{formatDateRange(invoice.passageStartDate, invoice.passageEndDate)}</TableCell>
                <TableCell>{invoice.plateNumber || "-"}</TableCell>
                <TableCell>{invoice.sellerName || "-"}</TableCell>
                <TableCell align="right">{formatMoney(invoice.totalAmount)}</TableCell>
                <TableCell align="right">{formatMoney(invoice.taxAmount)}</TableCell>
                <TableCell>{attachmentLabel(invoice)}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );

  return (
    <Box data-testid="etc-ticket-management-page">
      <PageScaffold
        className="etc-page"
        title="ETC票据管理"
        actions={
          <Button
            component={RouterLink}
            to="/imports/etc-invoices"
            variant="outlined"
            endIcon={<ArrowForwardOutlinedIcon />}
          >
            导入 ETC 发票
          </Button>
        }
      >
        <Stack spacing={2}>
          {actionError ? <StatePanel tone="error">{actionError}</StatePanel> : null}

          <Paper className="etc-filter-bar" variant="outlined" aria-label="ETC筛选">
            <ToggleButtonGroup
              color="primary"
              size="small"
              exclusive
              value={activeStatus}
              onChange={handleStatusChange}
              aria-label="ETC批次状态"
            >
              <ToggleButton value="unsubmitted">
                未提交 {counts.unsubmitted}
              </ToggleButton>
              <ToggleButton value="submitted">
                已提交 {counts.submitted}
              </ToggleButton>
            </ToggleButtonGroup>
            <TextField
              label="月份"
              size="small"
              type="month"
              value={month}
              InputLabelProps={{ shrink: true }}
              onChange={(event) => setMonth(event.target.value)}
            />
            <TextField
              label="车牌"
              size="small"
              value={plate}
              placeholder="云ADA0381"
              onChange={(event) => setPlate(event.target.value)}
            />
            <TextField
              label="关键词"
              size="small"
              value={keyword}
              placeholder="批次号/OA/发票号"
              onChange={(event) => setKeyword(event.target.value)}
            />
            {activeStatus === "unsubmitted" ? (
              <Button
                type="button"
                variant="contained"
                disabled={!canSubmitCurrentBatch || draftCreating}
                onClick={() => setCreateDialogOpen(true)}
              >
                提交OA支付申请
              </Button>
            ) : null}
          </Paper>

          <Box className="etc-layout">
            <Paper className="etc-batch-list-panel" variant="outlined" component="section" aria-label="ETC批次列表区">
              <Stack className="etc-panel-heading" direction="row" alignItems="center" spacing={1.5}>
                <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
                  <Typography component="h2" variant="h6" fontWeight={800}>
                    批次列表
                  </Typography>
                  <Chip label={`${visibleBatches.length} 批`} size="small" variant="outlined" />
                </Stack>
                {activeStatus === "unsubmitted" ? (
                  <Button
                    type="button"
                    size="small"
                    variant="contained"
                    startIcon={<AddOutlinedIcon />}
                    disabled={taskActionLoading}
                    onClick={handleCreateReconciliationTask}
                  >
                    新建批次
                  </Button>
                ) : null}
              </Stack>
              {activeStatus === "unsubmitted" ? (
                <Box className="etc-reconciliation-task-list" aria-label="ETC对账任务列表">
                  <Typography variant="caption" color="text.secondary" fontWeight={800}>
                    对账任务
                  </Typography>
                  {taskLoading ? <StatePanel tone="loading" compact>正在加载对账任务。</StatePanel> : null}
                  {!taskLoading && reconciliationTasks.length === 0 ? (
                    <StatePanel tone="empty" compact>暂无对账任务。</StatePanel>
                  ) : null}
                  <List disablePadding aria-label="ETC对账任务">
                    {reconciliationTasks.map((task) => {
                      const deletable = canDeleteTask(task);
                      const taskTitle = formatTaskTitle(task);
                      return (
                        <ListItem
                          key={task.taskId}
                          className="etc-reconciliation-task-row"
                          data-testid={`etc-reconciliation-task-row-${task.taskId}`}
                          disablePadding
                          secondaryAction={
                            <Tooltip title={deletable ? "删除对账任务" : deleteTaskDisabledReason(task)}>
                              <span>
                                <IconButton
                                  edge="end"
                                  size="small"
                                  color="error"
                                  aria-label={deletable ? `删除对账任务 ${taskTitle}` : deleteTaskDisabledReason(task)}
                                  disabled={!deletable || deleteSubmitting}
                                  onClick={(event) => openDeleteTaskDialog(task, event)}
                                >
                                  <DeleteOutlineOutlinedIcon fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
                          }
                        >
                          <ListItemButton
                            aria-label={`查看对账任务 ${taskTitle}`}
                            selected={selectedTaskId === task.taskId}
                            onClick={() => setSelectedTaskId(task.taskId)}
                          >
                            <ListItemText
                              primaryTypographyProps={{ component: "div" }}
                              secondaryTypographyProps={{ component: "div" }}
                              primary={
                                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                  <Typography component="strong" fontWeight={800}>
                                    {formatShortDateRange(task.periodStart, task.periodEnd)}
                                  </Typography>
                                  <Chip label={reconciliationStatusLabel(task.status)} size="small" variant="outlined" />
                                </Stack>
                              }
                              secondary={
                                <Box className="etc-batch-fields">
                                  <span>{taskTitle}</span>
                                  <span>{taskCountText(task)}</span>
                                  <span>{task.vehiclePlates.join("、") || "未记录车牌"}</span>
                                </Box>
                              }
                            />
                          </ListItemButton>
                        </ListItem>
                      );
                    })}
                  </List>
                </Box>
              ) : null}
              {loading ? <StatePanel tone="loading" compact>正在加载ETC批次。</StatePanel> : null}
              {!loading && visibleBatches.length === 0 ? <StatePanel tone="empty" compact>当前筛选下没有ETC批次。</StatePanel> : null}
              <List className="etc-batch-list" aria-label="ETC批次列表" disablePadding>
                {visibleBatches.map((batch) => {
                  const deletable = canDeleteBatch(batch);
                  const batchTitle = batch.externalBatchId || batch.etcBatchId;
                  return (
                    <ListItem
                      key={batch.id}
                      className={`etc-batch-row ${batch.status}`}
                      data-testid={`etc-batch-row-${batch.id}`}
                      disablePadding
                      secondaryAction={
                        <Tooltip title={deletable ? "删除ETC批次" : "已提交批次不能删除"}>
                          <span>
                            <IconButton
                              edge="end"
                              size="small"
                              color="error"
                              aria-label={deletable ? `删除ETC批次 ${batchTitle}` : "已提交批次不能删除"}
                              disabled={!deletable || deleteSubmitting}
                              onClick={(event) => openDeleteBatchDialog(batch, event)}
                            >
                              <DeleteOutlineOutlinedIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      }
                    >
                      <ListItemButton
                        aria-label={`查看ETC批次 ${batchTitle}`}
                        selected={selectedBatchId === batch.id}
                        onClick={() => {
                          setBatchDetail(null);
                          setSelectedBatchId(batch.id);
                        }}
                      >
                        <ListItemText
                          primaryTypographyProps={{ component: "div" }}
                          secondaryTypographyProps={{ component: "div" }}
                          primary={
                            <Stack className="etc-row-title" direction="row" alignItems="center" spacing={1} flexWrap="wrap">
                              <Typography component="strong" fontWeight={800}>
                                {formatShortDateRange(batch.passageStartDate, batch.passageEndDate)}
                              </Typography>
                              <Chip
                                label={batchStatusLabel(batch.status)}
                                size="small"
                                color={batch.status === "submitted" ? "success" : "primary"}
                                variant="outlined"
                              />
                            </Stack>
                          }
                          secondary={
                            <Box className="etc-batch-fields">
                              <span>{batchTitle}</span>
                              <span>{batch.displayCountText || taskCountText({ etcInvoiceCount: batch.etcInvoiceCount, supplementCount: batch.supplementCount })}</span>
                              <span>{batch.invoiceCount} 张 / {formatMoney(batch.totalAmount)} 元</span>
                              <span>{batch.plateCount} 个车牌</span>
                              {batch.status === "submitted" && batchOaLabel(batch) ? <span>{batchOaLabel(batch)}</span> : null}
                            </Box>
                          }
                        />
                      </ListItemButton>
                    </ListItem>
                  );
                })}
              </List>
            </Paper>

            <Stack className="etc-right-column" spacing={2}>
              <Paper className="etc-reconciliation-workspace" variant="outlined" component="section" aria-label="ETC对账工作区">
                <Stack spacing={2}>
                  <Stack className="etc-detail-heading" direction={{ xs: "column", md: "row" }} alignItems={{ xs: "stretch", md: "flex-start" }} spacing={1.5}>
                    <Box>
                      <Typography component="h2" variant="h6" fontWeight={800}>
                        ETC对账任务
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        {selectedTask ? `${formatTaskTitle(selectedTask)} / v${selectedTask.version}` : "请选择左侧对账任务或新建批次。"}
                      </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      {selectedTask && selectedTask.status === "ready_for_import" ? (
                        <Button type="button" variant="outlined" disabled={taskActionLoading} onClick={handleReopenReconciliationTask}>
                          重新打开
                        </Button>
                      ) : null}
                      <Button
                        type="button"
                        variant="contained"
                        disabled={!selectedTask || !canConfirmSelectedTask || taskActionLoading}
                        onClick={handleConfirmReconciliationTask}
                      >
                        确认对账
                      </Button>
                      <Button
                        type="button"
                        variant="outlined"
                        aria-expanded={taskPanelExpanded}
                        aria-controls="etc-reconciliation-task-content"
                        startIcon={taskPanelExpanded ? <ExpandLessOutlinedIcon /> : <ExpandMoreOutlinedIcon />}
                        onClick={() => setTaskPanelExpanded((current) => !current)}
                      >
                        {taskPanelExpanded ? "折叠ETC对账任务" : "展开ETC对账任务"}
                      </Button>
                    </Stack>
                  </Stack>

                  <Collapse in={taskPanelExpanded} timeout="auto" unmountOnExit>
                    <Box id="etc-reconciliation-task-content">
                      {selectedTask ? (
                        <Stack spacing={2}>
                      <Box className="etc-upload-blocks" aria-label="ETC对账文件上传">
                        <Box className="etc-ticket-root-import-panel">
                          <Stack spacing={1}>
                            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                              <Typography component="h3" variant="subtitle2" fontWeight={800}>
                                票根网导入方式
                              </Typography>
                              <ToggleButtonGroup
                                size="small"
                                exclusive
                                value={ticketRootImportMode}
                                onChange={handleTicketRootImportModeChange}
                                aria-label="票根网导入方式"
                              >
                                <ToggleButton value="clipboard" disabled={!taskIsMutable || hasTicketRootTextFileSource || hasTicketRootDocumentSource}>
                                  手工输入
                                </ToggleButton>
                                <ToggleButton value="textFile" disabled={!taskIsMutable || hasTicketRootManualSource || hasTicketRootDocumentSource}>
                                  TXT文件
                                </ToggleButton>
                                <ToggleButton value="file" disabled={!taskIsMutable || hasTicketRootManualSource || hasTicketRootTextFileSource}>
                                  PDF/JPG
                                </ToggleButton>
                              </ToggleButtonGroup>
                            </Stack>
                            {hasTicketRootDocumentSource ? (
                              <Typography variant="caption" color="text.secondary">已有 PDF/JPG 源文件，删除后可切换。</Typography>
                            ) : null}
                            {hasTicketRootTextFileSource ? (
                              <Typography variant="caption" color="text.secondary">已有 TXT 源文件，删除后可切换。</Typography>
                            ) : null}
                            {hasTicketRootManualSource ? (
                              <Typography variant="caption" color="text.secondary">已有手工粘贴源，删除后可切换。</Typography>
                            ) : null}
                            {ticketRootImportMode === "clipboard" ? (
                              <Stack spacing={1}>
                                <Box className="etc-ticket-root-paste-grid">
                                  {ticketRootPasteBlocks.map((block, index) => {
                                    const sourceItems = block.sourceFileId ? ticketRootItemsBySourceFileId.get(block.sourceFileId) ?? [] : [];
                                    const sourceSummary = block.sourceFileId ? ticketRootSourceSummary(sourceItems) : null;
                                    const summary = block.sourceFileId
                                      ? `${sourceSummary?.plateLabel ?? "未识别车牌"} / 已解析 ${sourceSummary?.parsedCount ?? 0} 条`
                                      : block.text.trim()
                                        ? "待提交"
                                        : "点击粘贴票根网文本";
                                    return (
                                      <Paper key={block.clientId} className="etc-ticket-root-paste-card" variant="outlined">
                                        <Button
                                          type="button"
                                          className="etc-ticket-root-paste-open"
                                          aria-label={block.sourceFileId || block.text.trim() ? `编辑票根网文本 ${index + 1}` : "点击粘贴票根网文本"}
                                          disabled={!taskIsMutable || taskActionLoading || hasTicketRootTextFileSource || hasTicketRootDocumentSource}
                                          onClick={() => openTicketRootTextDialog(block)}
                                        >
                                          <Stack className="etc-ticket-root-paste-main" spacing={0.25} alignItems="stretch">
                                            <Stack className="etc-ticket-root-paste-summary" direction="row" spacing={0.75} alignItems="center">
                                              <Typography component="span" variant="caption" color="text.secondary" className="etc-ticket-root-paste-index">
                                                #{index + 1}
                                              </Typography>
                                              {sourceSummary ? (
                                                <>
                                                  <Typography component="span" fontWeight={800} className="etc-ticket-root-paste-plate" title={sourceSummary.plateLabel}>
                                                    {sourceSummary.plateLabel}
                                                  </Typography>
                                                  <Chip component="span" label={`已解析 ${sourceSummary.parsedCount} 条`} size="small" variant="outlined" />
                                                  <Typography component="span" variant="caption" color="text.secondary" className="etc-ticket-root-paste-meta">
                                                    金额合计 {sourceSummary.totalAmount}
                                                  </Typography>
                                                  <Typography component="span" variant="caption" color="text.secondary" className="etc-ticket-root-paste-meta" title={sourceSummary.dateRange}>
                                                    日期 {sourceSummary.dateRange}
                                                  </Typography>
                                                </>
                                              ) : (
                                                <Typography component="span" fontWeight={800} className="etc-ticket-root-paste-plate">
                                                  {summary}
                                                </Typography>
                                              )}
                                            </Stack>
                                            {block.originalName ? (
                                              <Tooltip title={block.originalName}>
                                                <Typography component="span" variant="caption" color="text.secondary" className="etc-ticket-root-paste-filename">
                                                  {block.originalName}
                                                </Typography>
                                              </Tooltip>
                                            ) : null}
                                          </Stack>
                                        </Button>
                                        <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                                          <Tooltip title="编辑">
                                            <span>
                                              <IconButton
                                                size="small"
                                                aria-label={`编辑票根网文本 ${index + 1}`}
                                                disabled={!taskIsMutable || taskActionLoading || hasTicketRootTextFileSource || hasTicketRootDocumentSource}
                                                onClick={() => openTicketRootTextDialog(block)}
                                              >
                                                <EditOutlinedIcon fontSize="small" />
                                              </IconButton>
                                            </span>
                                          </Tooltip>
                                          <Tooltip title="删除">
                                            <span>
                                              <IconButton
                                                size="small"
                                                color="error"
                                                aria-label={`删除票根网文本 ${index + 1}`}
                                                disabled={!taskIsMutable || taskActionLoading || ticketRootPasteBlocks.length === 1 && !block.sourceFileId}
                                                onClick={() => void handleRemoveTicketRootPasteBlock(block)}
                                              >
                                                <DeleteOutlineOutlinedIcon fontSize="small" />
                                              </IconButton>
                                            </span>
                                          </Tooltip>
                                        </Stack>
                                      </Paper>
                                    );
                                  })}
                                </Box>
                                <Button
                                  type="button"
                                  variant="outlined"
                                  size="small"
                                  startIcon={<AddOutlinedIcon />}
                                  disabled={!taskIsMutable || taskActionLoading || hasTicketRootTextFileSource || hasTicketRootDocumentSource}
                                  onClick={handleAddTicketRootPasteBlock}
                                >
                                  增加粘贴框
                                </Button>
                              </Stack>
                            ) : null}
                          </Stack>
                        </Box>
                        <Box className="etc-upload-actions" aria-label="ETC导入动作">
                          <UploadBlock
                            label="信用卡账单 PDF"
                            accept=".pdf,application/pdf"
                            disabled={!taskIsMutable || taskActionLoading}
                            onFiles={handleUploadCreditCardStatement}
                          />
                          <UploadBlock
                            label="补充凭证"
                            accept=".pdf,.jpg,.jpeg,image/jpeg,application/pdf"
                            multiple
                            disabled={!taskIsMutable || taskActionLoading}
                            onFiles={handleUploadSupplementEvidences}
                          />
                          <UploadBlock
                            label="票根网 TXT"
                            accept=".txt,text/plain"
                            multiple
                            disabled={!taskIsMutable || taskActionLoading || ticketRootImportMode !== "textFile" || hasTicketRootManualSource || hasTicketRootDocumentSource}
                            onFiles={handleUploadTicketRootFiles}
                          />
                          <UploadBlock
                            label="票根网 PDF/JPG"
                            accept=".pdf,.jpg,.jpeg,image/jpeg,application/pdf"
                            multiple
                            disabled={!taskIsMutable || taskActionLoading || ticketRootImportMode !== "file" || hasTicketRootManualSource || hasTicketRootTextFileSource}
                            onFiles={handleUploadTicketRootFiles}
                          />
                        </Box>
                      </Box>

                      <Box className="etc-reconciliation-metrics" aria-label="本次确认预览">
                        <Box>
                          <Typography variant="caption" color="text.secondary">金额</Typography>
                          <Typography fontWeight={800}>{formatMoney(selectedReconciliationSummary.oaTotalAmount)}</Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.secondary">任务范围</Typography>
                          <Typography fontWeight={800}>{formatDateRange(selectedReconciliationSummary.periodStart, selectedReconciliationSummary.periodEnd)}</Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.secondary">数量</Typography>
                          <Typography fontWeight={800}>{taskCountText(selectedReconciliationSummary)}</Typography>
                        </Box>
                      </Box>

                      <Box component="section" aria-label="已上传文件">
                        <Stack spacing={1}>
                          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                            <Typography component="h3" variant="subtitle1" fontWeight={800}>
                              已上传文件
                            </Typography>
                            <Chip label={`${selectedTask.sourceFiles.length} 个文件`} size="small" variant="outlined" />
                          </Stack>
                          {selectedTask.sourceFiles.length === 0 ? (
                            <StatePanel tone="empty" compact>暂无上传文件。</StatePanel>
                          ) : (
                            <List disablePadding aria-label="已上传文件列表">
                              {selectedTask.sourceFiles.map((sourceFile) => {
                                const sourceSummary = ticketRootSourceSummaryBySourceFileId.get(sourceFile.fileId);
                                return (
                                  <ListItem
                                    key={sourceFile.fileId}
                                    disablePadding
                                    secondaryAction={
                                      <Tooltip title={taskIsMutable ? "删除源文件" : "已确认/已导入任务不能删除源文件"}>
                                        <span>
                                          <IconButton
                                            edge="end"
                                            size="small"
                                            color="error"
                                            aria-label={taskIsMutable ? `删除源文件 ${sourceFile.originalName}` : "已确认/已导入任务不能删除源文件"}
                                            disabled={!taskIsMutable || taskActionLoading || deleteSubmitting}
                                            onClick={(event) => openDeleteSourceFileDialog(sourceFile, event)}
                                          >
                                            <DeleteOutlineOutlinedIcon fontSize="small" />
                                          </IconButton>
                                        </span>
                                      </Tooltip>
                                    }
                                  >
                                    <ListItemText
                                      primaryTypographyProps={{ component: "div" }}
                                      secondaryTypographyProps={{ component: "div" }}
                                      primary={
                                        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                          <Typography component="span" fontWeight={800}>
                                            {sourceFile.originalName || sourceFile.fileId}
                                          </Typography>
                                          <Chip label={sourceKindLabel(sourceFile.sourceKind)} size="small" variant="outlined" />
                                          {sourceSummary ? (
                                            <>
                                              <Chip label={`${sourceSummary.plateLabel} / 已解析 ${sourceSummary.parsedCount} 条`} size="small" variant="outlined" />
                                              <Chip label={`金额合计 ${sourceSummary.totalAmount}`} size="small" variant="outlined" />
                                              <Chip label={`日期 ${sourceSummary.dateRange}`} size="small" variant="outlined" />
                                            </>
                                          ) : null}
                                          {sourceFile.hasBlockingIssue ? <Chip label="blocking" size="small" color="error" /> : null}
                                        </Stack>
                                      }
                                      secondary={sourceFile.fileId}
                                    />
                                  </ListItem>
                                );
                              })}
                            </List>
                          )}
                        </Stack>
                      </Box>

                      <Paper className="etc-manual-review-panel" variant="outlined" component="section" aria-label="人工核对处理">
                        <Stack spacing={1.5}>
                          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ xs: "stretch", md: "center" }}>
                            <Box className="etc-manual-review-card">
                              <Typography variant="caption" color="text.secondary">当前信用卡项</Typography>
                              <Typography fontWeight={800}>
                                {selectedCardItem ? `${selectedCardItem.transactionDate} / ${formatMoney(selectedCardItem.settlementAmount)}` : "未选择"}
                              </Typography>
                              <Typography variant="body2" color="text.secondary">
                                {selectedCardItem?.description ?? "点击信用卡侧明细行后处理。"}
                              </Typography>
                            </Box>
                            <Box className="etc-manual-review-card">
                              <Typography variant="caption" color="text.secondary">推荐票根</Typography>
                              <Typography fontWeight={800}>
                                {suggestedTicket ? `${suggestedTicket.vehiclePlate} / ${formatMoney(suggestedTicket.amount)}` : "无可接受建议"}
                              </Typography>
                              <Typography variant="body2" color="text.secondary">
                                {suggestedTicket ? "金额与信用卡项一致，可人工确认后接受。" : "仅在推荐候选命中时可直接接受。"}
                              </Typography>
                            </Box>
                            <TextField
                              select
                              SelectProps={{ native: true }}
                              label="关联票根/补充凭证"
                              size="small"
                              value={selectedEvidenceRowId}
                              onChange={(event) => setSelectedEvidenceRowId(event.target.value)}
                              sx={{ minWidth: 240, flex: 1 }}
                              disabled={!taskIsMutable || taskActionLoading}
                            >
                              <option value="">选择一条记录</option>
                              {evidenceRows.map((item) => (
                                <option key={item.id} value={item.id}>
                                  {item.source === "ticket" ? "票根" : "补充"} / {formatMoney(item.amount)} / {item.plateOrMerchant}
                                </option>
                              ))}
                            </TextField>
                          </Stack>
                          <TextField
                            label="处理说明"
                            size="small"
                            value={reviewNote}
                            onChange={(event) => setReviewNote(event.target.value)}
                            placeholder="排除、异常或手工确认时必填"
                            disabled={!taskIsMutable || taskActionLoading}
                          />
                          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Button
                              type="button"
                              size="small"
                              variant="contained"
                              disabled={!taskIsMutable || taskActionLoading || !selectedCardItem || !suggestedTicket}
                              onClick={handleAcceptSuggestedTicket}
                            >
                              接受推荐票根
                            </Button>
                            <Button
                              type="button"
                              size="small"
                              variant="outlined"
                              disabled={!taskIsMutable || taskActionLoading || !selectedCardItem || !selectedEvidenceRow}
                              onClick={handleLinkSelectedEvidence}
                            >
                              关联所选记录
                            </Button>
                            <Button
                              type="button"
                              size="small"
                              variant="outlined"
                              color="warning"
                              disabled={!taskIsMutable || taskActionLoading || !selectedCardItem}
                              onClick={() => handleExcludeCard("excluded_non_etc")}
                            >
                              排除非ETC
                            </Button>
                            <Button
                              type="button"
                              size="small"
                              variant="outlined"
                              color="warning"
                              disabled={!taskIsMutable || taskActionLoading || !selectedCardItem}
                              onClick={() => handleExcludeCard("excluded_error")}
                            >
                              标记异常
                            </Button>
                            <Button
                              type="button"
                              size="small"
                              variant="outlined"
                              disabled={!taskIsMutable || taskActionLoading || !selectedCardItem}
                              onClick={handleManualConfirmCard}
                            >
                              手工确认
                            </Button>
                          </Stack>
                        </Stack>
                      </Paper>

                      {selectedTask.parseIssues.length > 0 ? (
                        <Stack spacing={1}>
                          {selectedTask.parseIssues.map((issue) => (
                            <Alert
                              key={issue.issueId || `${issue.fileId}-${issue.sourcePage ?? ""}-${issue.sourceLine ?? ""}-${issue.message}`}
                              severity={issue.severity === "blocking" ? "error" : "warning"}
                            >
                              <Stack spacing={0.5}>
                                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                  <Typography component="span" fontWeight={800}>
                                    {issue.originalName || issue.fileId || "未知文件"}
                                  </Typography>
                                  <Chip label={sourceKindLabel(issue.sourceKind)} size="small" variant="outlined" />
                                  {parseIssueContextLabel(issue) ? (
                                    <Typography component="span" variant="caption" color="text.secondary">
                                      {parseIssueContextLabel(issue)}
                                    </Typography>
                                  ) : null}
                                </Stack>
                                <Typography component="span" variant="body2">
                                  {issue.message}
                                </Typography>
                              </Stack>
                            </Alert>
                          ))}
                        </Stack>
                      ) : null}

                      <Box
                        className="etc-reconciliation-table-block"
                        style={{ "--etc-reconciliation-row-height": "32px" } as CSSProperties}
                      >
                        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
                          <Typography component="h3" variant="subtitle1" fontWeight={800}>
                            双侧核对
                          </Typography>
                          <Chip label={`${reconciliationRows.length} 行`} size="small" variant="outlined" />
                          <Button
                            type="button"
                            size="small"
                            variant="outlined"
                            disabled={reconciliationRows.length === 0}
                            onClick={handleSelectAllReconciliationRows}
                          >
                            全选
                          </Button>
                          <Button
                            type="button"
                            size="small"
                            variant="outlined"
                            disabled={pairedReconciliationRowIds.length === 0}
                            onClick={handleSelectPairedReconciliationRows}
                          >
                            全选配对项
                          </Button>
                          <Button
                            type="button"
                            size="small"
                            variant="outlined"
                            disabled={selectedReconciliationRowIds.size === 0}
                            onClick={handleClearReconciliationSelection}
                          >
                            清空
                          </Button>
                          <Tooltip title="重新计算匹配">
                            <span>
                              <Button
                                type="button"
                                size="small"
                                variant="outlined"
                                startIcon={<RefreshOutlinedIcon />}
                                disabled={!selectedTask || taskActionLoading}
                                onClick={handleRefreshReconciliationMatches}
                              >
                                刷新匹配
                              </Button>
                            </span>
                          </Tooltip>
                        </Stack>
                        <TableContainer className="etc-reconciliation-table-container">
                          <Table
                            aria-label="ETC双侧核对明细"
                            className="etc-reconciliation-table"
                            size="small"
                          >
                            <TableHead>
                              <TableRow>
                                <TableCell className="etc-reconciliation-select-column" aria-label="选择列" />
                                <TableCell className="etc-reconciliation-table-side-heading" colSpan={3} align="center">
                                  信用卡侧
                                </TableCell>
                                <TableCell className="etc-reconciliation-table-side-heading etc-reconciliation-divider" colSpan={2} align="center">
                                  票根/补充凭证侧
                                </TableCell>
                              </TableRow>
                              <TableRow>
                                <TableCell className="etc-reconciliation-select-column" align="center">选择</TableCell>
                                <TableCell className="etc-reconciliation-date-column">交易日</TableCell>
                                <TableCell className="etc-reconciliation-description-column">交易描述</TableCell>
                                <TableCell className="etc-reconciliation-amount-column" align="center">金额</TableCell>
                                <TableCell className="etc-reconciliation-time-column etc-reconciliation-divider">交易时间</TableCell>
                                <TableCell className="etc-reconciliation-evidence-column" align="center">金额 / 车牌</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {reconciliationRows.map((row) => (
                                <TableRow
                                  key={row.id}
                                  className="etc-reconciliation-table-row"
                                  data-testid={`etc-reconciliation-row-${row.id}`}
                                  data-highlight={row.highlight || undefined}
                                >
                                  <TableCell className="etc-reconciliation-select-column" align="center">
                                    <Checkbox
                                      size="small"
                                      checked={selectedReconciliationRowIds.has(row.id)}
                                      onChange={() => handleToggleReconciliationRow(row.id)}
                                      onClick={(event) => event.stopPropagation()}
                                      slotProps={{ input: { "aria-label": `选择核对行 ${row.id}` } }}
                                    />
                                  </TableCell>
                                  <TableCell
                                    className="etc-reconciliation-card-cell etc-reconciliation-date-column"
                                    data-highlight={row.cardHighlight || undefined}
                                    onClick={() => row.card && setSelectedCardItemId(row.card.itemId)}
                                  >
                                    {renderCardDateCell(row.card)}
                                  </TableCell>
                                  <TableCell
                                    className="etc-reconciliation-card-cell etc-reconciliation-description-column"
                                    data-testid={row.card ? `etc-reconciliation-card-cell-${row.card.itemId}` : undefined}
                                    data-highlight={row.cardHighlight || undefined}
                                    onClick={() => row.card && setSelectedCardItemId(row.card.itemId)}
                                  >
                                    {renderCardDescriptionCell(row.card)}
                                  </TableCell>
                                  <TableCell
                                    className="etc-reconciliation-card-cell etc-reconciliation-amount-column"
                                    data-highlight={row.cardHighlight || undefined}
                                    align="center"
                                    onClick={() => row.card && setSelectedCardItemId(row.card.itemId)}
                                  >
                                    {renderCardAmountCell(row.card)}
                                  </TableCell>
                                  <TableCell
                                    className="etc-reconciliation-evidence-side-cell etc-reconciliation-time-column etc-reconciliation-divider"
                                    data-highlight={row.evidenceHighlight || undefined}
                                    onClick={() => row.evidence && setSelectedEvidenceRowId(row.evidence.id)}
                                  >
                                    {renderEvidenceTimeCell(row.evidence)}
                                  </TableCell>
                                  <TableCell
                                    className="etc-reconciliation-evidence-side-cell etc-reconciliation-evidence-column"
                                    data-testid={row.evidence ? `etc-reconciliation-evidence-cell-${row.evidence.id}` : undefined}
                                    data-highlight={row.evidenceHighlight || undefined}
                                    align="center"
                                    onClick={() => row.evidence && setSelectedEvidenceRowId(row.evidence.id)}
                                  >
                                    {renderEvidenceSummaryCell(row.evidence)}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </Box>
                      <Box component="section" className="etc-task-imported-invoices" aria-label="已导入ETC发票">
                        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                          <Typography component="h3" variant="subtitle1" fontWeight={800}>
                            已导入ETC发票
                          </Typography>
                          {taskImportBatchDetail ? (
                            <Chip label={`${importedInvoiceCount} 张`} size="small" variant="outlined" />
                          ) : null}
                          {taskImportBatchDetail ? (
                            <Chip label={`合计 ${importedInvoiceAmount}`} size="small" color="success" variant="outlined" />
                          ) : null}
                          {canRemoveImportedInvoices ? (
                            <Button
                              type="button"
                              size="small"
                              variant="outlined"
                              color="warning"
                              startIcon={<DeleteOutlineOutlinedIcon />}
                              disabled={removeImportedInvoicesSubmitting || taskActionLoading}
                              onClick={() => setRemoveImportedInvoicesDialogOpen(true)}
                            >
                              移除已导入的发票
                            </Button>
                          ) : null}
                        </Stack>
                        {!selectedTaskImportBatchId ? (
                          <StatePanel tone="info" compact>确认对账后，请到 ETC 发票导入页导入 zip。</StatePanel>
                        ) : taskImportDetailError ? (
                          <StatePanel tone="error" compact>{taskImportDetailError}</StatePanel>
                        ) : (
                          renderEtcInvoiceTable(
                            taskImportBatchDetail?.invoiceItems ?? [],
                            {
                              ariaLabel: "已导入ETC发票明细",
                              emptyText: "暂无已导入ETC发票明细。",
                              loadingText: taskImportDetailLoading ? "正在加载已导入ETC发票。" : "",
                              tableKey: selectedTaskImportBatchId,
                            },
                          )
                        )}
                      </Box>
                    </Stack>
                  ) : (
                    <StatePanel tone="empty">暂无可展示的ETC对账任务。</StatePanel>
                  )}
                    </Box>
                  </Collapse>
                </Stack>
              </Paper>

              <Paper className="etc-batch-detail-panel" variant="outlined" component="section" aria-label="ETC批次详情">
                <Stack spacing={2}>
                  <Stack className="etc-detail-heading" direction="row" alignItems="center" justifyContent="space-between" spacing={1.5}>
                    <Box>
                      <Typography component="h2" variant="h6" fontWeight={800}>
                        ETC批次详情
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        {selectedBatch ? selectedBatch.externalBatchId || selectedBatch.etcBatchId : "请选择左侧批次。"}
                      </Typography>
                    </Box>
                    <Button
                      type="button"
                      variant="outlined"
                      aria-expanded={batchDetailPanelExpanded}
                      aria-controls="etc-batch-detail-content"
                      startIcon={batchDetailPanelExpanded ? <ExpandLessOutlinedIcon /> : <ExpandMoreOutlinedIcon />}
                      onClick={() => setBatchDetailPanelExpanded((current) => !current)}
                    >
                      {batchDetailPanelExpanded ? "折叠ETC批次详情" : "展开ETC批次详情"}
                    </Button>
                  </Stack>
                  <Collapse in={batchDetailPanelExpanded} timeout="auto" unmountOnExit>
                    <Box id="etc-batch-detail-content">
                      {!selectedBatch ? (
                        <StatePanel tone="empty">请选择左侧批次。</StatePanel>
                      ) : (
                        <Stack spacing={2}>
                  <Stack className="etc-detail-heading" direction={{ xs: "column", md: "row" }} alignItems={{ xs: "stretch", md: "flex-start" }} spacing={1.5}>
                    <Box>
                      <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap">
                        <Typography component="h2" variant="h6" fontWeight={800}>
                          {selectedBatch.externalBatchId || selectedBatch.etcBatchId}
                        </Typography>
                        <Chip
                          label={batchStatusLabel(selectedBatch.status)}
                          size="small"
                          color={selectedBatch.status === "submitted" ? "success" : "primary"}
                          variant="outlined"
                        />
                      </Stack>
                      {selectedBatch.status === "submitted" && batchOaLabel(selectedBatch) ? (
                        <Typography color="text.secondary" variant="body2" fontWeight={700} sx={{ mt: 0.75 }}>
                          {batchOaLabel(selectedBatch)}
                        </Typography>
                      ) : null}
                    </Box>
                    {activeStatus === "submitted" ? (
                      <Button
                        type="button"
                        variant="outlined"
                        color="warning"
                        startIcon={<UndoOutlinedIcon />}
                        disabled={!canRevokeCurrentBatch}
                        onClick={() => setRevokeDialogOpen(true)}
                      >
                        撤销提交状态
                      </Button>
                    ) : null}
                  </Stack>

                  <Box className="etc-detail-metrics" aria-label="批次指标">
                    <Box>
                      <Typography variant="caption" color="text.secondary">总金额</Typography>
                      <Typography fontWeight={800}>{formatMoney(selectedBatch.totalAmount)}</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary">发票数</Typography>
                      <Typography fontWeight={800}>{selectedBatch.invoiceCount} 张</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary">开票日期</Typography>
                      <Typography fontWeight={800}>{formatDateRange(selectedBatch.issueStartDate, selectedBatch.issueEndDate)}</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary">通行日期</Typography>
                      <Typography fontWeight={800}>{formatDateRange(selectedBatch.passageStartDate, selectedBatch.passageEndDate)}</Typography>
                    </Box>
                  </Box>

                  <Box className="etc-plate-summary" aria-label="车牌汇总">
                    {selectedBatch.plateSummary.map((item) => (
                      <Box key={item.plateNumber} className="etc-plate-summary-item">
                        <Typography fontWeight={800}>{item.plateNumber || "未记录车牌"}</Typography>
                        <Typography color="text.secondary" variant="body2">{item.invoiceCount} 张</Typography>
                        <Typography fontWeight={800}>{formatMoney(item.totalAmount)}</Typography>
                      </Box>
                    ))}
                  </Box>

                  <Divider />

                          {detailLoading ? <StatePanel tone="loading" compact>正在加载批次明细。</StatePanel> : null}
                          {renderEtcInvoiceTable(
                            invoiceRows,
                            {
                              ariaLabel: "ETC发票明细",
                              emptyText: "暂无发票明细。",
                              loadingText: detailLoading ? "正在加载批次明细。" : "",
                              tableKey: selectedBatchId,
                            },
                          )}
                        </Stack>
                      )}
                    </Box>
                  </Collapse>
                </Stack>
              </Paper>
            </Stack>
          </Box>
        </Stack>

        <AppDialog
          open={Boolean(ticketRootTextDialog)}
          title="粘贴票根网文本"
          maxWidth="md"
          onClose={() => setTicketRootTextDialog(null)}
          actions={
            <>
              <Button type="button" onClick={() => setTicketRootTextDialog(null)}>取消</Button>
              <Button type="button" variant="contained" onClick={() => void handleSubmitTicketRootText()} disabled={taskActionLoading}>
                确定
              </Button>
            </>
          }
        >
          <TextField
            label="票根网文本"
            value={ticketRootTextDialog?.text ?? ""}
            onChange={(event) => {
              const nextText = event.target.value;
              setTicketRootTextDialog((current) => current ? { ...current, text: nextText } : current);
            }}
            multiline
            minRows={10}
            fullWidth
            autoFocus
          />
        </AppDialog>

        <AppDialog
          open={Boolean(deleteTarget)}
          title={deleteTarget?.kind === "task" ? "删除对账任务" : deleteTarget?.kind === "sourceFile" ? "删除源文件" : "删除ETC批次"}
          description={deleteTarget?.kind === "task"
            ? deleteTaskDescription(deleteTarget.item)
            : deleteTarget?.kind === "sourceFile"
              ? "将删除该上传源文件及其解析结果、解析错误和解析产物。"
              : "将删除该未提交 ETC 批次。已提交或已关联 OA 的批次不会被允许删除。"}
          onClose={() => {
            if (!deleteSubmitting) {
              setDeleteTarget(null);
            }
          }}
          actions={
            <>
              <Button type="button" onClick={() => setDeleteTarget(null)} disabled={deleteSubmitting}>取消</Button>
              <Button type="button" variant="contained" color="error" onClick={handleDeleteConfirmed} disabled={deleteSubmitting}>
                {deleteSubmitting ? "正在删除..." : "确认删除"}
              </Button>
            </>
          }
        >
          {deleteTarget?.kind === "task" ? (
            <Stack spacing={1}>
              <Typography>任务：{formatTaskTitle(deleteTarget.item)}</Typography>
              <Typography>期间：{formatDateRange(deleteTarget.item.periodStart, deleteTarget.item.periodEnd)}</Typography>
              <Typography>数量：{taskCountText(deleteTarget.item)}</Typography>
              {deleteTarget.item.status === "imported" || deleteTarget.item.hasImportedInvoices ? (
                <Typography color="warning.main">
                  将一并删除该任务下已导入的 ETC 发票；如需恢复，需要重新创建/确认任务并重新导入 zip。
                </Typography>
              ) : null}
              <Typography>版本：v{deleteTarget.item.version}</Typography>
            </Stack>
          ) : deleteTarget?.kind === "sourceFile" ? (
            <Stack spacing={1}>
              <Typography>文件：{deleteTarget.item.originalName || deleteTarget.item.fileId}</Typography>
              <Typography>类型：{sourceKindLabel(deleteTarget.item.sourceKind)}</Typography>
              <Typography>任务：{formatTaskTitle(deleteTarget.task)}</Typography>
              <Typography>版本：v{deleteTarget.task.version}</Typography>
            </Stack>
          ) : deleteTarget?.kind === "batch" ? (
            <Stack spacing={1}>
              <Typography>批次：{deleteTarget.item.externalBatchId || deleteTarget.item.etcBatchId}</Typography>
              <Typography>通行期间：{formatDateRange(deleteTarget.item.passageStartDate, deleteTarget.item.passageEndDate)}</Typography>
              <Typography>数量：{deleteTarget.item.displayCountText || taskCountText({ etcInvoiceCount: deleteTarget.item.etcInvoiceCount, supplementCount: deleteTarget.item.supplementCount })}</Typography>
              <Typography>金额：{formatMoney(deleteTarget.item.totalAmount)} 元</Typography>
            </Stack>
          ) : null}
        </AppDialog>

        <AppDialog
          open={removeImportedInvoicesDialogOpen}
          title="移除已导入发票"
          description="将清空该对账任务下已导入的 ETC 发票关联，任务可重新进入 ETC 发票导入流程。"
          onClose={() => {
            if (!removeImportedInvoicesSubmitting) {
              setRemoveImportedInvoicesDialogOpen(false);
            }
          }}
          actions={
            <>
              <Button
                type="button"
                onClick={() => setRemoveImportedInvoicesDialogOpen(false)}
                disabled={removeImportedInvoicesSubmitting}
              >
                取消
              </Button>
              <Button
                type="button"
                variant="contained"
                color="warning"
                onClick={() => void handleRemoveImportedInvoices()}
                disabled={removeImportedInvoicesSubmitting}
              >
                {removeImportedInvoicesSubmitting ? "正在移除..." : "确认移除"}
              </Button>
            </>
          }
        >
          {selectedTask ? (
            <Stack spacing={1}>
              <Typography>任务：{formatTaskTitle(selectedTask)}</Typography>
              <Typography>期间：{formatDateRange(selectedTask.periodStart, selectedTask.periodEnd)}</Typography>
              <Typography>已导入发票：{importedInvoiceCount} 张</Typography>
              <Typography>版本：v{selectedTask.version}</Typography>
            </Stack>
          ) : null}
        </AppDialog>

        <AppDialog
          open={revokeDialogOpen}
          title="撤销提交状态"
          description="只修改 fin-ops 内部 ETC 批次状态，不撤回 OA 流程，不修改 OA 数据。"
          onClose={() => setRevokeDialogOpen(false)}
          actions={
            <>
              <Button type="button" onClick={() => setRevokeDialogOpen(false)}>取消</Button>
              <Button type="button" variant="contained" color="warning" onClick={handleRevoke}>确认撤销</Button>
            </>
          }
        />

        <AppDialog
          open={createDialogOpen}
          title={draftResult ? "OA提交结果确认" : "创建OA支付申请草稿"}
          onClose={() => setCreateDialogOpen(false)}
          actions={
            draftResult ? (
              <>
                <Button type="button" variant="contained" onClick={() => handleResultConfirmation(true)}>确认已提交OA</Button>
                <Button type="button" onClick={() => handleResultConfirmation(false)}>未提交OA</Button>
              </>
            ) : (
              <>
                <Button type="button" onClick={() => setCreateDialogOpen(false)}>取消</Button>
                <Button type="button" variant="contained" onClick={handleCreateDraft} disabled={draftCreating}>
                  {draftCreating ? "正在创建..." : "确认创建草稿"}
                </Button>
              </>
            )
          }
        >
          {draftResult ? (
            <Stack spacing={1}>
              <Typography>OA 草稿已创建，并已打开支付申请列表。</Typography>
              <Typography>批次号：{draftResult.etcBatchId}</Typography>
            </Stack>
          ) : (
            <Stack spacing={1}>
              <Typography>{currentOaDraftDescription}</Typography>
              <Typography>当前批次：{currentOaDraftBatchLabel || "-"}</Typography>
            </Stack>
          )}
        </AppDialog>
      </PageScaffold>
    </Box>
  );
}
