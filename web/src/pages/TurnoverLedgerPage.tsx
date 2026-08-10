import { Button, Checkbox, ToggleButton, ToggleButtonGroup } from "@heroui/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, RefreshCw } from "lucide-react";

import AppDrawer from "../components/common/AppDrawer";
import { FinanceTablePagination } from "../components/common/FinanceTable";
import PageScaffold from "../components/common/PageScaffold";
import PageBusinessAuditIcon from "../components/common/PageBusinessAuditIcon";
import PageStatisticsPopover from "../components/common/PageStatisticsPopover";
import StatePanel from "../components/common/StatePanel";
import TurnoverLedgerExportDialog from "../components/turnoverLedger/TurnoverLedgerExportDialog";
import TurnoverLedgerExtraDrawer from "../components/turnoverLedger/TurnoverLedgerExtraDrawer";
import TurnoverLedgerGroupedTable, { formatMoney, formatNullable } from "../components/turnoverLedger/TurnoverLedgerGroupedTable";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { ApiClientError } from "../features/apiClient";
import {
  confirmTurnoverClosure,
  confirmTurnoverRelation,
  downloadTurnoverLedgerExport,
  fetchTurnoverLedgerExportPreview,
  fetchTurnoverLedgerGrouped,
  fetchTurnoverLedgerTagSelection,
  fetchTurnoverRelationDetail,
  fetchTurnoverRelationExtra,
  saveTurnoverLedgerTagSelection,
  saveTurnoverRelationExtra,
  withdrawTurnoverClosure,
  withdrawTurnoverRelation,
} from "../features/turnoverLedger/api";
import type {
  TurnoverLedgerExportPreview,
  TurnoverLedgerExtra,
  TurnoverLedgerFamily,
  TurnoverLedgerFamilySummary,
  TurnoverLedgerGroupedResponse,
  TurnoverLedgerGroupedRow,
  TurnoverLedgerSummary,
  TurnoverLedgerTagDefinition,
  TurnoverLedgerTagSelection,
  TurnoverRelationDetail,
} from "../features/turnoverLedger/types";

const DEFAULT_PAGE_SIZE = 50;

const FAMILY_TABS: Array<{ value: TurnoverLedgerFamily; label: string }> = [
  { value: "all", label: "全部" },
  { value: "personal", label: "个人往来" },
  { value: "company", label: "公司往来" },
  { value: "bank", label: "银行往来" },
  { value: "business", label: "业务往来" },
];

const FAMILY_BREAKDOWN_ORDER = FAMILY_TABS.filter((tab) => tab.value !== "all") as Array<{
  value: Exclude<TurnoverLedgerFamily, "all">;
  label: string;
}>;

const DEFAULT_SUMMARY: TurnoverLedgerSummary = {
  pendingRepaymentAmount: "0.00",
  repaidAmount: "0.00",
  pendingCollectionAmount: "0.00",
  collectedAmount: "0.00",
  closedAmount: "0.00",
  suggestedCount: 0,
  conflictCount: 0,
  rowCount: 0,
};

const DEFAULT_EXTRA: TurnoverLedgerExtra = {
  relationId: "",
  interestRateType: "none",
  interestRateValue: "0.000000",
  interestPaidAmount: "0.00",
  interestPaidDate: null,
  interestPaymentMethod: "",
  note: "",
  updatedAt: null,
  updatedBy: "",
};

const EMPTY_TAG_SELECTION: TurnoverLedgerTagSelection = {
  version: 1,
  selectedTagCodes: [],
  inactiveSelectedTagCodes: [],
  activeTags: [],
};

const SELF_SUB_LABEL = "主标签本身";
const POST_MUTATION_RELOAD_WARNING_MESSAGE = "操作已成功，但页面重新加载失败，请刷新页面重试。";

type TurnoverLedgerToastSeverity = "success" | "warning" | "error";

type ClosureSelection = {
  groupId: string;
  groupLabel: string;
  rows: TurnoverLedgerGroupedRow[];
};

function isAbortLikeError(caught: unknown) {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return true;
  }
  return caught instanceof Error && (caught.name === "AbortError" || /aborted|abort/i.test(caught.message));
}

type SummaryBreakdownMetric =
  | "pendingRepaymentAmount"
  | "repaidAmount"
  | "pendingCollectionAmount"
  | "collectedAmount";

function familySummaryAmount(summary: TurnoverLedgerFamilySummary | undefined, metric: SummaryBreakdownMetric) {
  return formatMoney(summary?.[metric] ?? "0.00");
}

function SummaryMetric({
  label,
  value,
  breakdown,
  testId,
}: {
  label: string;
  value: string | number;
  breakdown: Array<{ label: string; value: string }>;
  testId: string;
}) {
  return (
    <div className="turnover-ledger-summary-metric" data-testid={testId}>
      <span className="turnover-ledger-summary-metric__label">
        {label}
      </span>
      <span className="turnover-ledger-summary-metric__value">
        {value}
      </span>
      <span className="turnover-ledger-summary-metric__breakdown">
        {breakdown.map((item) => (
          <span className="turnover-ledger-summary-metric__breakdown-row" key={item.label}>
            <span>{item.label}</span>
            <span>{item.value}</span>
          </span>
        ))}
      </span>
    </div>
  );
}

function extraFromRow(row: TurnoverLedgerGroupedRow): TurnoverLedgerExtra {
  return {
    relationId: relationIdForRow(row),
    interestRateType: row.interestRateType,
    interestRateValue: row.interestRateValue,
    interestPaidAmount: row.interestPaidAmount,
    interestPaidDate: row.interestPaidDate,
    interestPaymentMethod: row.interestPaymentMethod,
    note: row.note,
    updatedAt: null,
    updatedBy: "",
  };
}

function relationIdForRow(row: TurnoverLedgerGroupedRow) {
  return row.relationId || row.parentRelationId || "";
}

function isFlowRow(row: TurnoverLedgerGroupedRow) {
  return row.rowKind === "flow";
}

function cleanText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function moneyNumber(value: string | null | undefined) {
  const parsed = Number(String(value ?? "").replace(/,/g, "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function moneyCents(value: number) {
  return Math.round(value * 100);
}

function flowBankRowId(row: TurnoverLedgerGroupedRow) {
  return cleanText(row.sourceBankRowId) || cleanText(row.bankRowIds[0]) || cleanText(row.flowId);
}

function cashClosureCaseIdForRow(row: TurnoverLedgerGroupedRow) {
  return cleanText(row.cashClosureCaseId);
}

function cashClosureRelationIdForRow(row: TurnoverLedgerGroupedRow) {
  return cleanText(row.cashClosureRelationId);
}

function isCashClosureLinkedRow(row: TurnoverLedgerGroupedRow) {
  return Boolean(row.cashClosureLinked);
}

function closureExpectedVersions(rows: TurnoverLedgerGroupedRow[]) {
  const expectedVersions: Record<string, unknown> = {};
  rows.forEach((row) => {
    const bankRowId = flowBankRowId(row);
    if (!bankRowId) {
      return;
    }
    if (row.selectionVersion) {
      expectedVersions[`turnover_bank_row_selection:${bankRowId}`] = row.selectionVersion;
    }
    if (typeof row.categoryVersion === "number" && Number.isFinite(row.categoryVersion)) {
      expectedVersions[`turnover_bank_row:${bankRowId}`] = row.categoryVersion;
    }
  });
  return Object.keys(expectedVersions).length > 0 ? expectedVersions : undefined;
}

function closureIdempotencyKey(bankRowIds: string[]) {
  return `turnover-manual-closure:${Date.now()}:${bankRowIds.join(",")}`;
}

function relationDetailErrorMessage(caught: unknown) {
  if (caught instanceof ApiClientError && (caught.status === 404 || caught.code === "unknown_relation_id")) {
    return "该流水所属往来关系已刷新或不存在，请刷新台账后再编辑。";
  }
  if (caught instanceof Error && /往来款关系不存在|unknown_relation_id/i.test(caught.message)) {
    return "该流水所属往来关系已刷新或不存在，请刷新台账后再编辑。";
  }
  return caught instanceof Error ? caught.message : "往来关系详情加载失败";
}

async function reloadLedgerAfterWrite(
  reloadLedger: () => Promise<TurnoverLedgerGroupedResponse>,
  markReloading: () => void,
) {
  markReloading();
  try {
    await reloadLedger();
    return "";
  } catch {
    return POST_MUTATION_RELOAD_WARNING_MESSAGE;
  }
}

type ClosureCashDirection = "income" | "expense" | "unknown";

type ClosurePreviewItem = {
  bankRowId: string;
  direction: ClosureCashDirection;
  directionLabel: string;
  amount: number;
  row: TurnoverLedgerGroupedRow;
};

function normalizeCashDirection(value: string | null | undefined): ClosureCashDirection {
  if (value === "income" || value === "expense") {
    return value;
  }
  return "unknown";
}

function closureCashDirection(row: TurnoverLedgerGroupedRow): ClosureCashDirection {
  const flowDirection = normalizeCashDirection(row.flowDirection);
  if (flowDirection !== "unknown") {
    return flowDirection;
  }
  const borrowAmount = moneyNumber(row.borrowAmount);
  const repaymentAmount = moneyNumber(row.repaymentAmount);
  if (borrowAmount > 0 && repaymentAmount <= 0) {
    return normalizeCashDirection(row.borrowDirection);
  }
  if (repaymentAmount > 0 && borrowAmount <= 0) {
    return normalizeCashDirection(row.repaymentDirection);
  }
  return "unknown";
}

function closureAmount(row: TurnoverLedgerGroupedRow) {
  const flowAmount = moneyNumber(row.flowAmount);
  if (flowAmount > 0) {
    return flowAmount;
  }
  const borrowAmount = moneyNumber(row.borrowAmount);
  const repaymentAmount = moneyNumber(row.repaymentAmount);
  if (borrowAmount > 0 && repaymentAmount <= 0) {
    return borrowAmount;
  }
  if (repaymentAmount > 0 && borrowAmount <= 0) {
    return repaymentAmount;
  }
  return Math.max(borrowAmount, repaymentAmount);
}

function buildClosurePreview(rows: TurnoverLedgerGroupedRow[]) {
  const items: ClosurePreviewItem[] = rows.map((row) => {
    const direction = closureCashDirection(row);
    return {
      bankRowId: flowBankRowId(row),
      direction,
      directionLabel: direction === "income" ? "收入" : direction === "expense" ? "支出" : "未知方向",
      amount: closureAmount(row),
      row,
    };
  });
  const incomeItems = items.filter((item) => item.direction === "income");
  const expenseItems = items.filter((item) => item.direction === "expense");
  const incomeCents = incomeItems.reduce((sum, item) => sum + moneyCents(item.amount), 0);
  const expenseCents = expenseItems.reduce((sum, item) => sum + moneyCents(item.amount), 0);
  const incomeAmount = incomeCents / 100;
  const expenseAmount = expenseCents / 100;
  const delta = Math.abs(incomeCents - expenseCents) / 100;
  return {
    items,
    incomeAmount,
    expenseAmount,
    delta,
    canConfirm: rows.length >= 2 && incomeItems.length >= 1 && expenseItems.length >= 1 && incomeCents === expenseCents,
  };
}

function tagPrimaryLabel(tag: TurnoverLedgerTagDefinition) {
  return cleanText(tag.outputPrimaryLabel) || cleanText(tag.label) || cleanText(tag.code);
}

function tagSubLabel(tag: TurnoverLedgerTagDefinition) {
  return cleanText(tag.outputSubLabel);
}

export default function TurnoverLedgerPage() {
  const { active, activationGeneration } = useOptionalPageActivation("turnover-ledger");
  const { runOperation } = useGlobalOperationOverlay();
  const { canAdminAccess, canMutateData } = useSessionPermissions();
  const [family, setFamily] = useState<TurnoverLedgerFamily>("all");
  const [page, setPage] = useState(1);
  const [ledger, setLedger] = useState<TurnoverLedgerGroupedResponse | null>(null);
  const [tagSelection, setTagSelection] = useState<TurnoverLedgerTagSelection>(EMPTY_TAG_SELECTION);
  const [tagDrawerOpen, setTagDrawerOpen] = useState(false);
  const [draftSelectedTagCodes, setDraftSelectedTagCodes] = useState<Set<string>>(() => new Set());
  const [tagLoading, setTagLoading] = useState(false);
  const [tagSaving, setTagSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedRow, setSelectedRow] = useState<TurnoverLedgerGroupedRow | null>(null);
  const [detail, setDetail] = useState<TurnoverRelationDetail | null>(null);
  const [extraForm, setExtraForm] = useState<TurnoverLedgerExtra>(DEFAULT_EXTRA);
  const [extraDirty, setExtraDirty] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [savingExtra, setSavingExtra] = useState(false);
  const [mutatingRelation, setMutatingRelation] = useState(false);
  const [closureDrawerOpen, setClosureDrawerOpen] = useState(false);
  const [closureSubmitting, setClosureSubmitting] = useState(false);
  const [closureSelection, setClosureSelection] = useState<ClosureSelection | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportFamily, setExportFamily] = useState<TurnoverLedgerFamily>("all");
  const [exportPreview, setExportPreview] = useState<TurnoverLedgerExportPreview | null>(null);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportDownloading, setExportDownloading] = useState(false);
  const [toast, setToast] = useState<{ severity: TurnoverLedgerToastSeverity; message: string } | null>(null);
  const activeLedgerRequestRef = useRef<{
    family: TurnoverLedgerFamily;
    page: number;
    controller: AbortController;
  } | null>(null);
  const activeExtraEditorRef = useRef<{ relationId: string; controller: AbortController } | null>(null);

  const summary = ledger?.summary ?? DEFAULT_SUMMARY;
  const groups = ledger?.groups ?? [];
  const familySummaryMap = useMemo(() => new Map((ledger?.familySummaries ?? []).map((item) => [item.family, item])), [
    ledger?.familySummaries,
  ]);
  const summaryBreakdown = useCallback((metric: SummaryBreakdownMetric) => (
    FAMILY_BREAKDOWN_ORDER.map((item) => ({
      label: item.label,
      value: familySummaryAmount(familySummaryMap.get(item.value), metric),
    }))
  ), [familySummaryMap]);
  const selectedClosureRows = closureSelection?.rows ?? [];
  const selectedFlowRowIds = useMemo(
    () => new Set(selectedClosureRows.map(flowBankRowId).filter(Boolean)),
    [selectedClosureRows],
  );
  const closurePreview = useMemo(() => buildClosurePreview(selectedClosureRows), [selectedClosureRows]);
  const selectedRowsContainCashClosure = selectedClosureRows.some(isCashClosureLinkedRow);
  const selectedRowsContainOpenClosureCandidate = selectedClosureRows.some((row) => !isCashClosureLinkedRow(row));
  const selectedRowsAllCashClosure = selectedClosureRows.length > 0
    && selectedRowsContainCashClosure
    && !selectedRowsContainOpenClosureCandidate;
  const selectedCashClosureCaseId = useMemo(() => {
    if (!selectedRowsAllCashClosure) {
      return "";
    }
    const caseIds = new Set(selectedClosureRows.map(cashClosureCaseIdForRow).filter(Boolean));
    return caseIds.size === 1 ? Array.from(caseIds)[0] : "";
  }, [selectedClosureRows, selectedRowsAllCashClosure]);
  const selectedCashClosureRelationId = useMemo(() => {
    if (!selectedRowsAllCashClosure) {
      return "";
    }
    const relationIds = new Set(selectedClosureRows.map(cashClosureRelationIdForRow).filter(Boolean));
    return relationIds.size === 1 ? Array.from(relationIds)[0] : "";
  }, [selectedClosureRows, selectedRowsAllCashClosure]);
  const canWithdrawSelectedCashClosure = Boolean(
    canMutateData
      && selectedRowsAllCashClosure
      && selectedCashClosureCaseId
      && !closureSubmitting
      && !mutatingRelation,
  );
  const canOpenClosureDrawer = canMutateData
    && selectedClosureRows.length >= 2
    && !selectedRowsContainCashClosure;
  const closureActionLabel = selectedRowsAllCashClosure ? "撤回闭环" : "确认闭环";
  const canRunClosurePrimaryAction = selectedRowsAllCashClosure ? canWithdrawSelectedCashClosure : canOpenClosureDrawer;
  const ledgerNavigationDisabled = loading
    || tagSaving
    || savingExtra
    || mutatingRelation
    || closureSubmitting
    || selectedRow !== null;

  const loadTagSelection = useCallback((signal?: AbortSignal) => {
    setTagLoading(true);
    fetchTurnoverLedgerTagSelection(signal)
      .then((nextSelection) => {
        setTagSelection(nextSelection);
        setDraftSelectedTagCodes(new Set(nextSelection.selectedTagCodes));
      })
      .catch((caught: unknown) => {
        if (!isAbortLikeError(caught)) {
          setToast({ severity: "error", message: caught instanceof Error ? caught.message : "外部往来款标签设置加载失败" });
        }
      })
      .finally(() => setTagLoading(false));
  }, []);

  const requestLedger = useCallback(async ({
    surfaceError = true,
    throwOnError = false,
  }: { surfaceError?: boolean; throwOnError?: boolean } = {}) => {
    activeLedgerRequestRef.current?.controller.abort();
    const requestContext = { family, page, controller: new AbortController() };
    activeLedgerRequestRef.current = requestContext;
    setLoading(true);
    if (surfaceError) {
      setError(null);
    }
    try {
      let requestedPage = page;
      let nextLedger = await fetchTurnoverLedgerGrouped({
        family,
        direction: "all",
        page: requestedPage,
        pageSize: DEFAULT_PAGE_SIZE,
        signal: requestContext.controller.signal,
      });
      if (activeLedgerRequestRef.current !== requestContext || requestContext.controller.signal.aborted) {
        return null;
      }
      const totalPages = Math.max(1, Math.ceil(nextLedger.pagination.total / DEFAULT_PAGE_SIZE));
      if (requestedPage > totalPages) {
        requestedPage = totalPages;
        nextLedger = await fetchTurnoverLedgerGrouped({
          family,
          direction: "all",
          page: requestedPage,
          pageSize: DEFAULT_PAGE_SIZE,
          signal: requestContext.controller.signal,
        });
        if (activeLedgerRequestRef.current !== requestContext || requestContext.controller.signal.aborted) {
          return null;
        }
      }
      setLedger(nextLedger);
      if (requestedPage !== page) {
        setPage(requestedPage);
      }
      return nextLedger;
    } catch (caught: unknown) {
      if (
        activeLedgerRequestRef.current !== requestContext
        || requestContext.controller.signal.aborted
        || isAbortLikeError(caught)
      ) {
        return null;
      }
      if (surfaceError) {
        setError(caught instanceof Error ? caught.message : "往来款台账加载失败");
      }
      if (throwOnError) {
        throw caught;
      }
      return null;
    } finally {
      if (activeLedgerRequestRef.current === requestContext) {
        activeLedgerRequestRef.current = null;
        setLoading(false);
      }
    }
  }, [family, page]);

  const reloadLedgerAfterMutation = useCallback(async () => {
    const nextLedger = await requestLedger({ surfaceError: false, throwOnError: true });
    if (!nextLedger) {
      throw new Error("往来款台账刷新请求已失效");
    }
    return nextLedger;
  }, [requestLedger]);

  const loadLedger = useCallback(() => {
    void requestLedger();
  }, [requestLedger]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    loadLedger();
    return () => activeLedgerRequestRef.current?.controller.abort();
  }, [active, activationGeneration, loadLedger]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    loadTagSelection(controller.signal);
    return () => controller.abort();
  }, [active, activationGeneration, loadTagSelection]);

  useEffect(() => {
    if (!toast || toast.severity !== "success") {
      return undefined;
    }
    const timer = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (active) {
      return;
    }
    const activeEditor = activeExtraEditorRef.current;
    activeExtraEditorRef.current = null;
    activeEditor?.controller.abort();
    const activeLedgerRequest = activeLedgerRequestRef.current;
    activeLedgerRequestRef.current = null;
    activeLedgerRequest?.controller.abort();
    setLoading(false);
    setSelectedRow(null);
    setDetail(null);
    setExtraForm(DEFAULT_EXTRA);
    setExtraDirty(false);
    setDetailLoading(false);
    setDetailError(null);
  }, [active]);

  useEffect(() => () => {
    const activeEditor = activeExtraEditorRef.current;
    activeExtraEditorRef.current = null;
    activeEditor?.controller.abort();
    const activeLedgerRequest = activeLedgerRequestRef.current;
    activeLedgerRequestRef.current = null;
    activeLedgerRequest?.controller.abort();
  }, []);

  useEffect(() => {
    if (!active || !exportOpen) {
      return undefined;
    }
    const controller = new AbortController();
    setExportLoading(true);
    setExportError(null);
    fetchTurnoverLedgerExportPreview({ family: exportFamily, signal: controller.signal })
      .then(setExportPreview)
      .catch((caught: unknown) => {
        if (isAbortLikeError(caught)) {
          return;
        }
        setExportError(caught instanceof Error ? caught.message : "导出预览加载失败");
      })
      .finally(() => setExportLoading(false));
    return () => controller.abort();
  }, [active, exportFamily, exportOpen]);

  const handleFamilyChange = (nextFamily: TurnoverLedgerFamily) => {
    if (!nextFamily || nextFamily === family || ledgerNavigationDisabled) {
      return;
    }
    setClosureSelection(null);
    setClosureDrawerOpen(false);
    setPage(1);
    setFamily(nextFamily);
  };

  const handlePageChange = (nextPage: number) => {
    if (ledgerNavigationDisabled || nextPage === page) {
      return;
    }
    setClosureSelection(null);
    setClosureDrawerOpen(false);
    setPage(nextPage);
  };

  const handleToggleClosureRow = (group: { groupId: string; counterpartyName: string; familyLabel: string }, row: TurnoverLedgerGroupedRow) => {
    const rowId = flowBankRowId(row);
    if (!rowId) {
      setToast({ severity: "error", message: "这条流水缺少必要数据，无法选择。" });
      return;
    }
    setClosureSelection((current) => {
      const nextIsCashClosure = isCashClosureLinkedRow(row);
      const nextCashClosureCaseId = cashClosureCaseIdForRow(row);
      if (nextIsCashClosure && !nextCashClosureCaseId) {
        setToast({ severity: "error", message: "这组闭环缺少必要数据，请刷新后重试。" });
        return current;
      }
      if (!current) {
        return {
          groupId: group.groupId,
          groupLabel: [group.counterpartyName, group.familyLabel].filter(Boolean).join(" / "),
          rows: [row],
        };
      }
      if (current.groupId !== group.groupId) {
        setToast({ severity: "error", message: "一次只能选择同一往来组内的流水" });
        return current;
      }
      const exists = current.rows.some((item) => flowBankRowId(item) === rowId);
      if (exists) {
        const rows = current.rows.filter((item) => flowBankRowId(item) !== rowId);
        return rows.length > 0 ? { ...current, rows } : null;
      }
      const currentHasCashClosure = current.rows.some(isCashClosureLinkedRow);
      const currentHasOpenClosureCandidate = current.rows.some((item) => !isCashClosureLinkedRow(item));
      if ((currentHasCashClosure && !nextIsCashClosure) || (currentHasOpenClosureCandidate && nextIsCashClosure)) {
        setToast({ severity: "error", message: "不能同时选择已闭环和未闭环流水" });
        return current;
      }
      if (currentHasCashClosure && nextIsCashClosure) {
        const currentCaseIds = new Set(current.rows.map(cashClosureCaseIdForRow).filter(Boolean));
        if (currentCaseIds.size !== 1 || !currentCaseIds.has(nextCashClosureCaseId)) {
          setToast({ severity: "error", message: "一次只能撤回一组收支闭环流水" });
          return current;
        }
      }
      return { ...current, rows: [...current.rows, row] };
    });
  };

  const handleConfirmClosure = async () => {
    const currentSelection = closureSelection;
    if (!currentSelection || !closurePreview.canConfirm || closureSubmitting) {
      return;
    }
    const bankRowIds = currentSelection.rows.map(flowBankRowId).filter(Boolean);
    if (bankRowIds.length < 2) {
      return;
    }
    let postMutationSyncWarning = "";
    const result = await runOperation({
      loadingMessage: "正在确认外部往来闭环...",
      action: async ({ setMessage }) => {
        setClosureSubmitting(true);
        try {
          setMessage("正在确认外部往来闭环...");
          const closureResult = await confirmTurnoverClosure({
            bankRowIds,
            expectedVersions: closureExpectedVersions(currentSelection.rows),
            idempotencyKey: closureIdempotencyKey(bankRowIds),
          });
          setClosureSelection(null);
          setClosureDrawerOpen(false);
          setMessage("正在刷新往来款台账...");
          postMutationSyncWarning = await reloadLedgerAfterWrite(
            reloadLedgerAfterMutation,
            () => setMessage("正在刷新往来款台账..."),
          );
          return closureResult;
        } finally {
          setClosureSubmitting(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "外部往来闭环确认失败",
    });
    if (result.status === "success") {
      setToast({
        severity: postMutationSyncWarning ? "warning" : "success",
        message: postMutationSyncWarning || "外部往来闭环已确认",
      });
    } else {
      setToast({ severity: "error", message: result.error instanceof Error ? result.error.message : "外部往来闭环确认失败" });
    }
  };

  const drawerGroups = useMemo(() => {
    const grouped = new Map<string, TurnoverLedgerTagDefinition[]>();
    tagSelection.activeTags.forEach((tag) => {
      const primary = tagPrimaryLabel(tag) || tag.label || tag.code;
      grouped.set(primary, [...(grouped.get(primary) ?? []), tag]);
    });
    return Array.from(grouped.entries()).map(([primaryLabel, tags]) => ({ primaryLabel, tags }));
  }, [tagSelection.activeTags]);

  const handleOpenEditor = (row: TurnoverLedgerGroupedRow) => {
    if (!isFlowRow(row) || savingExtra || mutatingRelation) {
      return;
    }
    const normalizedRow = { ...row, relationId: relationIdForRow(row) };
    if (!normalizedRow.relationId) {
      setToast({ severity: "error", message: "这条流水缺少可编辑关系，无法打开补充信息" });
      return;
    }
    activeExtraEditorRef.current?.controller.abort();
    const editorContext = {
      relationId: normalizedRow.relationId,
      controller: new AbortController(),
    };
    activeExtraEditorRef.current = editorContext;
    setSelectedRow(normalizedRow);
    setDetail(null);
    setDetailError(null);
    setExtraDirty(false);
    setExtraForm(extraFromRow(normalizedRow));
    setDetailLoading(true);
    Promise.all([
      fetchTurnoverRelationDetail(normalizedRow.relationId, editorContext.controller.signal),
      fetchTurnoverRelationExtra(normalizedRow.relationId, editorContext.controller.signal),
    ])
      .then(([nextDetail, nextExtra]) => {
        if (activeExtraEditorRef.current !== editorContext || editorContext.controller.signal.aborted) {
          return;
        }
        setDetail(nextDetail);
        setExtraForm(nextExtra);
      })
      .catch((caught: unknown) => {
        if (
          activeExtraEditorRef.current !== editorContext
          || editorContext.controller.signal.aborted
          || isAbortLikeError(caught)
        ) {
          return;
        }
        setDetailError(relationDetailErrorMessage(caught));
      })
      .finally(() => {
        if (activeExtraEditorRef.current === editorContext) {
          setDetailLoading(false);
        }
      });
  };

  const handleExtraChange = (next: TurnoverLedgerExtra) => {
    const activeEditor = activeExtraEditorRef.current;
    if (
      !activeEditor
      || activeEditor.relationId !== next.relationId
      || !canMutateData
      || detailLoading
      || detailError
      || savingExtra
      || mutatingRelation
    ) {
      return;
    }
    setExtraForm(next);
    setExtraDirty(true);
  };

  const handleSaveExtra = async () => {
    const editorContext = activeExtraEditorRef.current;
    if (
      !editorContext
      || !selectedRow
      || detailLoading
      || detailError
      || !extraDirty
      || savingExtra
      || mutatingRelation
      || editorContext.relationId !== selectedRow.relationId
      || editorContext.relationId !== extraForm.relationId
    ) {
      if (
        selectedRow
        && editorContext
        && (
          editorContext.relationId !== selectedRow.relationId
          || editorContext.relationId !== extraForm.relationId
        )
      ) {
        setDetailError("当前编辑关系已发生变化，请关闭后重新打开。");
      }
      return;
    }
    const targetRow = selectedRow;
    const nextExtra = extraForm;
    let postMutationSyncWarning = "";
    const result = await runOperation({
      loadingMessage: "正在保存往来关系补充信息...",
      action: async ({ setMessage }) => {
        setSavingExtra(true);
        try {
          const saved = await saveTurnoverRelationExtra(targetRow.relationId, {
            ...nextExtra,
            expectedVersions: {
              [`turnover_relation_extra:${targetRow.relationId}`]: nextExtra.updatedAt ?? "",
            },
          });
          if (activeExtraEditorRef.current === editorContext) {
            setExtraForm(saved.extra);
            setExtraDirty(false);
          }
          setMessage("正在刷新往来款台账...");
          postMutationSyncWarning = await reloadLedgerAfterWrite(
            reloadLedgerAfterMutation,
            () => setMessage("正在刷新往来款台账..."),
          );
          return saved;
        } finally {
          setSavingExtra(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "补充信息保存失败",
    });
    if (result.status === "success") {
      setToast({
        severity: postMutationSyncWarning ? "warning" : "success",
        message: postMutationSyncWarning || "补充信息已保存",
      });
    } else {
      setToast({ severity: "error", message: result.error instanceof Error ? result.error.message : "补充信息保存失败" });
    }
  };

  const handleRelationMutation = async (kind: "confirm" | "withdraw") => {
    const editorContext = activeExtraEditorRef.current;
    if (
      !editorContext
      || !selectedRow
      || detailLoading
      || detailError
      || savingExtra
      || mutatingRelation
      || editorContext.relationId !== selectedRow.relationId
    ) {
      return;
    }
    const targetRow = selectedRow;
    let postMutationSyncWarning = "";
    const result = await runOperation({
      loadingMessage: kind === "confirm" ? "正在确认往来归并..." : "正在撤销往来归并...",
      action: async ({ setMessage }) => {
        setMutatingRelation(true);
        try {
          const mutationResult = kind === "confirm"
            ? await confirmTurnoverRelation({ bankRowIds: targetRow.bankRowIds })
            : await withdrawTurnoverRelation({ relationId: targetRow.relationId });
          setMessage("正在刷新往来款台账...");
          postMutationSyncWarning = await reloadLedgerAfterWrite(
            reloadLedgerAfterMutation,
            () => setMessage("正在刷新往来款台账..."),
          );
          return mutationResult;
        } finally {
          setMutatingRelation(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "往来关系操作失败",
    });
    if (result.status === "success") {
      setToast({
        severity: postMutationSyncWarning ? "warning" : "success",
        message: postMutationSyncWarning || (kind === "confirm" ? "往来关系已确认归并" : "往来归并已撤销"),
      });
    } else {
      setToast({ severity: "error", message: result.error instanceof Error ? result.error.message : "往来关系操作失败" });
    }
  };

  const handleWithdrawSelectedCashClosure = async () => {
    if (!selectedCashClosureCaseId || !canWithdrawSelectedCashClosure) {
      return;
    }
    const relationId = selectedCashClosureRelationId;
    const cashClosureCaseId = selectedCashClosureCaseId;
    const affectedRowIds = selectedClosureRows.map(flowBankRowId).filter(Boolean);
    let postMutationSyncWarning = "";
    const result = await runOperation({
      loadingMessage: "正在撤回外部往来闭环...",
      action: async ({ setMessage }) => {
        setMutatingRelation(true);
        try {
          const mutationResult = relationId
            ? await withdrawTurnoverRelation({ relationId })
            : await withdrawTurnoverClosure({ cashClosureCaseId });
          setClosureSelection(null);
          setClosureDrawerOpen(false);
          setMessage("正在刷新往来款台账...");
          postMutationSyncWarning = await reloadLedgerAfterWrite(
            reloadLedgerAfterMutation,
            () => setMessage("正在刷新往来款台账..."),
          );
          return mutationResult;
        } finally {
          setMutatingRelation(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "外部往来闭环撤回失败",
    });
    if (result.status === "success") {
      setToast({
        severity: postMutationSyncWarning ? "warning" : "success",
        message: postMutationSyncWarning || "外部往来闭环已撤回",
      });
    } else {
      setToast({ severity: "error", message: result.error instanceof Error ? result.error.message : "外部往来闭环撤回失败" });
    }
  };

  const handleOpenExport = () => {
    setExportFamily(family);
    setExportPreview(null);
    setExportError(null);
    setExportOpen(true);
  };

  const handleSaveTagSelection = async () => {
    if (!canMutateData || tagSaving) {
      return;
    }
    const selectedTagCodes = Array.from(draftSelectedTagCodes);
    let postMutationSyncWarning = "";
    const result = await runOperation({
      loadingMessage: "正在保存外部往来款标签设置...",
      action: async ({ setMessage }) => {
        setTagSaving(true);
        try {
          const saved = await saveTurnoverLedgerTagSelection({
            expectedVersion: tagSelection.version,
            selectedTagCodes,
          });
          setTagSelection(saved);
          setDraftSelectedTagCodes(new Set(saved.selectedTagCodes));
          setTagDrawerOpen(false);
          setMessage("正在刷新往来款台账...");
          postMutationSyncWarning = await reloadLedgerAfterWrite(
            reloadLedgerAfterMutation,
            () => setMessage("正在刷新往来款台账..."),
          );
          return saved;
        } finally {
          setTagSaving(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "外部往来款标签设置保存失败",
    });
    if (result.status === "success") {
      setToast({
        severity: postMutationSyncWarning ? "warning" : "success",
        message: postMutationSyncWarning || "外部往来款标签设置已保存",
      });
    } else {
      setToast({ severity: "error", message: result.error instanceof Error ? result.error.message : "外部往来款标签设置保存失败" });
    }
  };

  const handleDownloadExport = async () => {
    setExportDownloading(true);
    try {
      const download = await downloadTurnoverLedgerExport({ family: exportFamily });
      const blob = download.blob;
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = download.fileName;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(href);
      setToast({ severity: "success", message: "往来款台账下载已开始" });
      setExportOpen(false);
    } catch (caught) {
      setExportError(caught instanceof Error ? caught.message : "往来款台账下载失败");
    } finally {
      setExportDownloading(false);
    }
  };

  const visibleStatistics = ledger?.statistics;
  const titleAccessory = (
    <div className="page-title-accessory-group">
      <PageStatisticsPopover
        ariaLabel="外部往来款管理数据统计"
        loading={loading && !ledger}
        coreItems={[
          { label: "往来流水", value: visibleStatistics?.transactionCount, unit: "笔" },
          { label: "支出", value: visibleStatistics?.expenseTransactionCount, unit: "笔", tone: "expense" },
          { label: "收入", value: visibleStatistics?.incomeTransactionCount, unit: "笔", tone: "income" },
        ]}
        detailItems={[
          { label: "已闭环组", value: visibleStatistics?.closedGroupCount, unit: "组", tone: "success" },
          { label: "台账组", value: visibleStatistics?.ledgerGroupCount, unit: "组" },
          { label: "未闭环组", value: visibleStatistics?.unclosedGroupCount, unit: "组", tone: "warning" },
          { label: "已关联 OA 的流水", value: visibleStatistics?.linkedOaTransactionCount, unit: "笔" },
          { label: "已关联发票的流水", value: visibleStatistics?.linkedInvoiceTransactionCount, unit: "笔" },
        ]}
      />
      {canAdminAccess ? (
        <PageBusinessAuditIcon
          ariaLabel="Audit 外部往来款管理"
          pageKey="turnover-ledger"
          label="外部往来款管理"
        />
      ) : null}
    </div>
  );

  return (
    <div className="turnover-ledger-page" data-testid="turnover-ledger-page">
      <PageScaffold
        title="外部往来款管理"
        titleAccessory={titleAccessory}
        actions={(
          <>
            <Button
              className="turnover-ledger-button"
              isDisabled={ledgerNavigationDisabled}
              onPress={() => loadLedger()}
              size="sm"
              variant="secondary"
            >
              <RefreshCw aria-hidden="true" size={16} strokeWidth={2.2} />
              刷新台账
            </Button>
            <Button
              className="turnover-ledger-button"
              isDisabled={tagLoading}
              onPress={() => setTagDrawerOpen(true)}
              size="sm"
              variant="secondary"
            >
              外部往来款标签设置
            </Button>
          </>
        )}
      >
        {!canMutateData ? (
          <div className="turnover-ledger-page-notice turnover-ledger-page-notice--info" role="status">
            当前账号为只读权限，可查看台账与详情，不能确认或撤销归并。
          </div>
        ) : null}

        {error ? (
          <StatePanel tone="error" title="往来款台账加载失败">
            {error}
          </StatePanel>
        ) : null}
        <div className="turnover-ledger-summary-band">
          <SummaryMetric
            label="当前待还款金额"
            value={formatMoney(summary.pendingRepaymentAmount)}
            breakdown={summaryBreakdown("pendingRepaymentAmount")}
            testId="turnover-summary-pending-repayment"
          />
          <SummaryMetric
            label="累计已还款金额"
            value={formatMoney(summary.repaidAmount)}
            breakdown={summaryBreakdown("repaidAmount")}
            testId="turnover-summary-repaid"
          />
          <SummaryMetric
            label="当前待收款金额"
            value={formatMoney(summary.pendingCollectionAmount)}
            breakdown={summaryBreakdown("pendingCollectionAmount")}
            testId="turnover-summary-pending-collection"
          />
          <SummaryMetric
            label="累计已收款金额"
            value={formatMoney(summary.collectedAmount)}
            breakdown={summaryBreakdown("collectedAmount")}
            testId="turnover-summary-collected"
          />
        </div>

        <section className="turnover-ledger-table-panel">
          <div className="turnover-ledger-table-panel__inner">
            <div className="turnover-ledger-table-panel__toolbar">
              <ToggleButtonGroup
                aria-label="往来款账单范围"
                className="turnover-ledger-tabs"
                disallowEmptySelection
                isDisabled={ledgerNavigationDisabled}
                onSelectionChange={(keys) => {
                  const [next] = Array.from(keys);
                  const tab = FAMILY_TABS.find((candidate) => candidate.value === next);
                  if (tab) handleFamilyChange(tab.value);
                }}
                selectedKeys={new Set([family])}
                selectionMode="single"
                size="sm"
              >
                {FAMILY_TABS.map((tab, index) => (
                  <ToggleButton id={tab.value} key={tab.value}>
                    {index > 0 ? <ToggleButtonGroup.Separator /> : null}
                    {tab.label}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
              <div className="turnover-ledger-actions">
                {selectedClosureRows.length > 0 ? (
                  <span className="turnover-ledger-selection-summary" role="status">
                    已选 {selectedClosureRows.length} 笔
                  </span>
                ) : null}
                <Button
                  className={`turnover-ledger-button${selectedRowsAllCashClosure ? " turnover-ledger-button--warning" : ""}`}
                  isDisabled={!canRunClosurePrimaryAction}
                  onPress={() => {
                    if (selectedRowsAllCashClosure) {
                      void handleWithdrawSelectedCashClosure();
                      return;
                    }
                    setClosureDrawerOpen(true);
                  }}
                  size="sm"
                  variant={selectedRowsAllCashClosure ? "danger" : "secondary"}
                >
                  {closureActionLabel}
                </Button>
                <Button className="turnover-ledger-button turnover-ledger-button--primary" onPress={handleOpenExport} size="sm" variant="primary">
                  <Download aria-hidden="true" size={16} strokeWidth={2.2} />
                  下载表格
                </Button>
              </div>
            </div>
            <div className="turnover-ledger-table-panel__divider" />
            <TurnoverLedgerGroupedTable
              groups={groups}
              loading={loading}
              showEmptyState={!error}
              onEdit={handleOpenEditor}
              selectedFlowRowIds={selectedFlowRowIds}
              onToggleFlowSelection={handleToggleClosureRow}
              actionsDisabled={!canMutateData}
            />
            <FinanceTablePagination
              page={ledger?.pagination.page ?? page}
              pageSize={ledger?.pagination.pageSize ?? DEFAULT_PAGE_SIZE}
              total={ledger?.pagination.total ?? 0}
              isDisabled={ledgerNavigationDisabled}
              onPageChange={handlePageChange}
            />
          </div>
        </section>
      </PageScaffold>

      <AppDrawer
        className="turnover-ledger-drawer"
        closeLabel="关闭外部往来款标签设置"
        open={tagDrawerOpen}
        onClose={() => setTagDrawerOpen(false)}
        title="外部往来款标签设置"
        width={520}
      >
        <div className="turnover-ledger-drawer__content">
          <div className="turnover-ledger-drawer__actions">
            <Button className="turnover-ledger-button" isDisabled={!canMutateData || tagSaving} onPress={() => setDraftSelectedTagCodes(new Set(tagSelection.activeTags.map((tag) => tag.code)))} size="sm" variant="secondary">全选</Button>
            <Button className="turnover-ledger-button" isDisabled={!canMutateData || tagSaving} onPress={() => setDraftSelectedTagCodes(new Set())} size="sm" variant="secondary">清空</Button>
            <Button className="turnover-ledger-button turnover-ledger-button--primary" isDisabled={!canMutateData || tagSaving} isPending={tagSaving} onPress={() => void handleSaveTagSelection()} size="sm" variant="primary">保存</Button>
          </div>
          {!canMutateData ? (
            <div className="turnover-ledger-drawer__notice" role="status">
              当前账号仅支持查看和导出，不能保存外部往来款标签设置。
            </div>
          ) : null}
          {tagSelection.inactiveSelectedTagCodes.length > 0 ? (
            <div className="turnover-ledger-drawer__notice" role="alert">
              已停用或不再属于外部往来款的标签不再生效：{tagSelection.inactiveSelectedTagCodes.join("、")}。保存后会清理这些引用。
            </div>
          ) : null}
          <div className="turnover-ledger-tag-list">
            {tagLoading ? <StatePanel compact tone="loading" title="标签加载中" /> : null}
            {!tagLoading && drawerGroups.length === 0 ? <StatePanel compact tone="empty" title="暂无可用外部往来款标签" /> : null}
            {!tagLoading ? drawerGroups.map((group) => {
              const codes = group.tags.map((tag) => tag.code);
              const checkedCount = codes.filter((code) => draftSelectedTagCodes.has(code)).length;
              const allChecked = checkedCount === codes.length && codes.length > 0;
              return (
                <fieldset className="turnover-ledger-tag-group" key={group.primaryLabel}>
                  <Checkbox
                    className="turnover-ledger-checkbox-row turnover-ledger-checkbox-row--primary"
                    isIndeterminate={checkedCount > 0 && !allChecked}
                    isSelected={allChecked}
                    isDisabled={!canMutateData || tagSaving}
                    onChange={(selected) => {
                      setDraftSelectedTagCodes((current) => {
                        const next = new Set(current);
                        codes.forEach((code) => {
                          if (selected) {
                            next.add(code);
                          } else {
                            next.delete(code);
                          }
                        });
                        return next;
                      });
                    }}
                  >
                    <Checkbox.Control
                      className="turnover-ledger-checkbox"
                    ><Checkbox.Indicator /></Checkbox.Control>
                    <span>{group.primaryLabel}</span>
                  </Checkbox>
                  <div className="turnover-ledger-tag-group__children">
                    {group.tags.map((tag) => {
                      const label = tagSubLabel(tag) || SELF_SUB_LABEL;
                      return (
                        <Checkbox
                          className="turnover-ledger-checkbox-row"
                          isDisabled={!canMutateData || tagSaving}
                          isSelected={draftSelectedTagCodes.has(tag.code)}
                          key={tag.code}
                          onChange={(selected) => {
                            setDraftSelectedTagCodes((current) => {
                              const next = new Set(current);
                              if (selected) {
                                next.add(tag.code);
                              } else {
                                next.delete(tag.code);
                              }
                              return next;
                            });
                          }}
                        >
                          <Checkbox.Control
                            className="turnover-ledger-checkbox"
                          ><Checkbox.Indicator /></Checkbox.Control>
                          <span>{label}</span>
                        </Checkbox>
                      );
                    })}
                  </div>
                </fieldset>
              );
            }) : null}
          </div>
        </div>
      </AppDrawer>

      <AppDrawer
        className="turnover-ledger-drawer"
        closeLabel="关闭确认外部往来闭环"
        open={closureDrawerOpen}
        onClose={() => setClosureDrawerOpen(false)}
        title="确认外部往来闭环"
        width={520}
      >
        <div className="turnover-ledger-drawer__content">
          {closureSelection?.groupLabel ? (
            <div className="turnover-ledger-drawer__notice" role="status">{closureSelection.groupLabel}</div>
          ) : null}
          <div className="turnover-ledger-closure-list">
            {closurePreview.items.map((item) => {
              const { row } = item;
              return (
                <div className="turnover-ledger-closure-card" key={item.bankRowId}>
                  <div className="turnover-ledger-closure-card__main">
                    <span>{item.directionLabel}</span>
                    <span>{formatMoney(String(item.amount.toFixed(2)))}</span>
                  </div>
                  <span>{formatNullable(row.transactionAt || row.borrowDate || row.repaymentDate)}</span>
                  <span className="turnover-ledger-closure-card__muted">{formatNullable(row.repaymentRemark || row.summaryText)}</span>
                </div>
              );
            })}
            <div className="turnover-ledger-closure-card">
              <div className="turnover-ledger-closure-card__row">
                <span>收入合计</span>
                <span>{formatMoney(closurePreview.incomeAmount.toFixed(2))}</span>
              </div>
              <div className="turnover-ledger-closure-card__row">
                <span>支出合计</span>
                <span>{formatMoney(closurePreview.expenseAmount.toFixed(2))}</span>
              </div>
              <div className="turnover-ledger-closure-card__delta">
                <span>差额</span>
                <span data-testid="turnover-closure-delta">{formatMoney(closurePreview.delta.toFixed(2))}</span>
              </div>
            </div>
            {!closurePreview.canConfirm ? (
              <div className="turnover-ledger-drawer__notice" role="alert">需选择同一往来组内至少一笔收入和一笔支出，且收支合计差额为 0.00。</div>
            ) : null}
          </div>
          <div className="turnover-ledger-drawer__footer">
            <Button className="turnover-ledger-button" isDisabled={closureSubmitting} onPress={() => setClosureDrawerOpen(false)} size="sm" variant="secondary">取消</Button>
            <Button
              className="turnover-ledger-button turnover-ledger-button--primary"
              isDisabled={!closurePreview.canConfirm || closureSubmitting}
              isPending={closureSubmitting}
              onPress={() => void handleConfirmClosure()}
              size="sm"
              variant="primary"
            >
              确定
            </Button>
          </div>
        </div>
      </AppDrawer>

      <TurnoverLedgerExtraDrawer
        open={selectedRow !== null}
        row={selectedRow}
        detail={detail}
        extra={extraForm}
        dirty={extraDirty}
        canMutateData={canMutateData}
        loading={detailLoading}
        saving={savingExtra}
        mutating={mutatingRelation}
        error={detailError}
        onClose={() => {
          if (savingExtra || mutatingRelation) {
            return;
          }
          const activeEditor = activeExtraEditorRef.current;
          activeExtraEditorRef.current = null;
          activeEditor?.controller.abort();
          setSelectedRow(null);
          setDetail(null);
          setExtraForm(DEFAULT_EXTRA);
          setDetailError(null);
          setDetailLoading(false);
          setExtraDirty(false);
        }}
        onExtraChange={handleExtraChange}
        onSave={() => void handleSaveExtra()}
        onConfirm={() => void handleRelationMutation("confirm")}
        onWithdraw={() => void handleRelationMutation("withdraw")}
      />

      <TurnoverLedgerExportDialog
        open={exportOpen}
        family={exportFamily}
        preview={exportPreview}
        loading={exportLoading}
        downloading={exportDownloading}
        error={exportError}
        onClose={() => setExportOpen(false)}
        onFamilyChange={setExportFamily}
        onDownload={() => void handleDownloadExport()}
      />

      {toast ? (
        <div className={`turnover-ledger-toast turnover-ledger-toast--${toast.severity}`} role={toast.severity === "error" ? "alert" : "status"}>
          <span>{toast.message}</span>
          <button aria-label="关闭提示" onClick={() => setToast(null)} type="button">×</button>
        </div>
      ) : null}
    </div>
  );
}
