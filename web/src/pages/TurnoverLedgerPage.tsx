import { useCallback, useEffect, useMemo, useState, type SyntheticEvent } from "react";
import { Download } from "lucide-react";

import AppDrawer from "../components/common/AppDrawer";
import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import TurnoverLedgerExportDialog from "../components/turnoverLedger/TurnoverLedgerExportDialog";
import TurnoverLedgerExtraDrawer from "../components/turnoverLedger/TurnoverLedgerExtraDrawer";
import TurnoverLedgerGroupedTable, { formatMoney, formatNullable } from "../components/turnoverLedger/TurnoverLedgerGroupedTable";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  FINANCE_DOMAIN_EVENTS,
  emitFinanceDomainEvent,
} from "../features/domainEvents";
import { operationBarrierTargetsFromMonths, waitForOperationFreshness } from "../features/operationBarrier/api";
import { useActiveFinanceDomainEvent } from "../hooks/useActiveFinanceDomainEvent";
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

const DEFAULT_PAGE_SIZE = 100;

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

function SummaryCard({
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
    <div className="turnover-ledger-summary-card" data-testid={testId}>
      <span className="turnover-ledger-summary-card__label">
        {label}
      </span>
      <span className="turnover-ledger-summary-card__value">
        {value}
      </span>
      <span className="turnover-ledger-summary-card__breakdown">
        {breakdown.map((item) => (
          <span className="turnover-ledger-summary-card__breakdown-row" key={item.label}>
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

function closureExpectedVersions(rows: TurnoverLedgerGroupedRow[]) {
  const expectedVersions: Record<string, unknown> = {};
  rows.forEach((row) => {
    const bankRowId = flowBankRowId(row);
    if (!bankRowId || !Number.isFinite(row.categoryVersion)) {
      return;
    }
    expectedVersions[`turnover_bank_row:${bankRowId}`] = row.categoryVersion;
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
  const { runOperation } = useGlobalOperationOverlay();
  const { canMutateData } = useSessionPermissions();
  const [family, setFamily] = useState<TurnoverLedgerFamily>("all");
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
  const [closureSelection, setClosureSelection] = useState<{
    groupId: string;
    groupLabel: string;
    rows: TurnoverLedgerGroupedRow[];
  } | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportFamily, setExportFamily] = useState<TurnoverLedgerFamily>("all");
  const [exportPreview, setExportPreview] = useState<TurnoverLedgerExportPreview | null>(null);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportDownloading, setExportDownloading] = useState(false);
  const [toast, setToast] = useState<{ severity: "success" | "error"; message: string } | null>(null);

  const summary = ledger?.summary ?? DEFAULT_SUMMARY;
  const groups = ledger?.groups ?? [];
  const readModelStatus = cleanText(ledger?.readModelStatus) || "fresh";
  const readModelNeedsRefresh = readModelStatus !== "fresh";
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

  const fetchLedger = useCallback((signal?: AbortSignal) => fetchTurnoverLedgerGrouped({
    family,
    direction: "all",
    page: 1,
    pageSize: DEFAULT_PAGE_SIZE,
    signal,
  }), [family]);

  const reloadLedgerAfterMutation = useCallback(async () => {
    const nextLedger = await fetchLedger();
    setLedger(nextLedger);
    return nextLedger;
  }, [fetchLedger]);

  const loadLedger = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    fetchLedger(signal)
      .then(setLedger)
      .catch((caught: unknown) => {
        if (isAbortLikeError(caught)) {
          return;
        }
        setError(caught instanceof Error ? caught.message : "往来款台账加载失败");
      })
      .finally(() => setLoading(false));
  }, [fetchLedger]);

  useEffect(() => {
    const controller = new AbortController();
    loadLedger(controller.signal);
    return () => controller.abort();
  }, [loadLedger]);

  useEffect(() => {
    const controller = new AbortController();
    loadTagSelection(controller.signal);
    return () => controller.abort();
  }, [loadTagSelection]);

  useEffect(() => {
    if (!toast) {
      return undefined;
    }
    const timer = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const handleCategoryUpdated = useCallback(() => {
    loadTagSelection();
    loadLedger();
  }, [loadLedger, loadTagSelection]);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, handleCategoryUpdated);

  useEffect(() => {
    if (!exportOpen) {
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
  }, [exportFamily, exportOpen]);

  const handleFamilyChange = (_event: SyntheticEvent, nextFamily: TurnoverLedgerFamily) => {
    if (!nextFamily) {
      return;
    }
    setClosureSelection(null);
    setClosureDrawerOpen(false);
    setFamily(nextFamily);
  };

  const handleToggleClosureRow = (group: { groupId: string; counterpartyName: string; familyLabel: string }, row: TurnoverLedgerGroupedRow) => {
    const rowId = flowBankRowId(row);
    if (!rowId) {
      setToast({ severity: "error", message: "这条流水缺少银行流水 ID，无法选择" });
      return;
    }
    setClosureSelection((current) => {
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
      return { ...current, rows: [...current.rows, row] };
    });
  };

  const handleConfirmClosure = async () => {
    if (!closurePreview.canConfirm || closureSubmitting) {
      return;
    }
    const bankRowIds = selectedClosureRows.map(flowBankRowId).filter(Boolean);
    if (bankRowIds.length < 2) {
      return;
    }
    const selectedRows = selectedClosureRows;
    const result = await runOperation({
      loadingMessage: "正在确认外部往来闭环...",
      action: async ({ setMessage }) => {
        setClosureSubmitting(true);
        try {
          const closureResult = await confirmTurnoverClosure({
            bankRowIds,
            expectedVersions: closureExpectedVersions(selectedRows),
            idempotencyKey: closureIdempotencyKey(bankRowIds),
          });
          setClosureSelection(null);
          setClosureDrawerOpen(false);
          setMessage("正在等待往来款台账和关联台读模型同步...");
          await waitForOperationFreshness(
            closureResult.freshnessTargets.length > 0
              ? closureResult.freshnessTargets
              : operationBarrierTargetsFromMonths("turnover_ledger", [], "all"),
          );
          setMessage("正在刷新往来款台账...");
          await reloadLedgerAfterMutation();
          return closureResult;
        } finally {
          setClosureSubmitting(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "外部往来闭环确认失败",
    });
    if (result.status === "success") {
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.turnoverRelationUpdated, {
        relationId: result.value.relationId,
        affectedRowIds: bankRowIds,
        affectedMonths: result.value.affectedMonths,
        action: "manual_closure",
        source: "turnover_manual_closure",
      });
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
        relationId: result.value.workbenchPairRelationId,
        affectedRowIds: bankRowIds,
        affectedMonths: result.value.affectedMonths,
        action: "turnover_manual_closure",
        source: "turnover_manual_closure",
      });
      setToast({ severity: "success", message: "外部往来闭环已确认" });
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
    if (!isFlowRow(row)) {
      return;
    }
    const normalizedRow = { ...row, relationId: relationIdForRow(row) };
    if (!normalizedRow.relationId) {
      setToast({ severity: "error", message: "这条流水缺少可编辑关系，无法打开补充信息" });
      return;
    }
    setSelectedRow(normalizedRow);
    setDetail(null);
    setDetailError(null);
    setExtraDirty(false);
    setExtraForm(extraFromRow(normalizedRow));
    setDetailLoading(true);
    const controller = new AbortController();
    Promise.all([
      fetchTurnoverRelationDetail(normalizedRow.relationId, controller.signal),
      fetchTurnoverRelationExtra(normalizedRow.relationId, controller.signal),
    ])
      .then(([nextDetail, nextExtra]) => {
        setDetail(nextDetail);
        setExtraForm(nextExtra);
      })
      .catch((caught: unknown) => {
        if (isAbortLikeError(caught)) {
          return;
        }
        setDetailError(relationDetailErrorMessage(caught));
      })
      .finally(() => setDetailLoading(false));
  };

  const handleExtraChange = (next: TurnoverLedgerExtra) => {
    setExtraForm(next);
    setExtraDirty(true);
  };

  const handleSaveExtra = async () => {
    if (!selectedRow || savingExtra) {
      return;
    }
    const targetRow = selectedRow;
    const nextExtra = extraForm;
    const result = await runOperation({
      loadingMessage: "正在保存往来关系补充信息...",
      action: async ({ setMessage }) => {
        setSavingExtra(true);
        try {
          const saved = await saveTurnoverRelationExtra(targetRow.relationId, nextExtra);
          setExtraForm(saved.extra);
          setExtraDirty(false);
          setMessage("正在等待往来款台账读模型同步...");
          await waitForOperationFreshness(operationBarrierTargetsFromMonths("turnover_ledger", [], "all"));
          setMessage("正在刷新往来款台账...");
          await reloadLedgerAfterMutation();
          return saved;
        } finally {
          setSavingExtra(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "补充信息保存失败",
    });
    if (result.status === "success") {
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.turnoverLedgerExtraUpdated, {
        relationId: targetRow.relationId,
        source: "turnover_extra_save",
      });
      setToast({ severity: "success", message: "补充信息已保存" });
    } else {
      setToast({ severity: "error", message: result.error instanceof Error ? result.error.message : "补充信息保存失败" });
    }
  };

  const handleRelationMutation = async (kind: "confirm" | "withdraw") => {
    if (!selectedRow || mutatingRelation) {
      return;
    }
    const targetRow = selectedRow;
    const result = await runOperation({
      loadingMessage: kind === "confirm" ? "正在确认往来归并..." : "正在撤销往来归并...",
      action: async ({ setMessage }) => {
        setMutatingRelation(true);
        try {
          const mutationResult = kind === "confirm"
            ? await confirmTurnoverRelation({ bankRowIds: targetRow.bankRowIds })
            : await withdrawTurnoverRelation({ relationId: targetRow.relationId });
          setMessage("正在等待往来款台账读模型同步...");
          await waitForOperationFreshness(
            operationBarrierTargetsFromMonths("turnover_ledger", mutationResult.affectedMonths, "all"),
          );
          setMessage("正在刷新往来款台账...");
          await reloadLedgerAfterMutation();
          return mutationResult;
        } finally {
          setMutatingRelation(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "往来关系操作失败",
    });
    if (result.status === "success") {
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.turnoverRelationUpdated, {
        relationId: result.value.relationId || targetRow.relationId,
        action: kind,
        source: "turnover_relation_mutation",
      });
      if (kind === "withdraw") {
        emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
          relationId: result.value.relationId || targetRow.relationId,
          affectedRowIds: targetRow.bankRowIds,
          action: "turnover_relation_withdraw",
          source: "turnover_relation_mutation",
        });
      }
      setToast({ severity: "success", message: kind === "confirm" ? "往来关系已确认归并" : "往来归并已撤销" });
    } else {
      setToast({ severity: "error", message: result.error instanceof Error ? result.error.message : "往来关系操作失败" });
    }
  };

  const handleOpenExport = () => {
    setExportFamily(family);
    setExportPreview(null);
    setExportError(null);
    setExportOpen(true);
  };

  const handleSaveTagSelection = async () => {
    if (tagSaving) {
      return;
    }
    const selectedTagCodes = Array.from(draftSelectedTagCodes);
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
          setMessage("正在等待往来款台账读模型同步...");
          await waitForOperationFreshness(operationBarrierTargetsFromMonths("turnover_ledger", [], "all"));
          setMessage("正在刷新往来款台账...");
          await reloadLedgerAfterMutation();
          return saved;
        } finally {
          setTagSaving(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "外部往来款标签设置保存失败",
    });
    if (result.status === "success") {
      setToast({ severity: "success", message: "外部往来款标签设置已保存" });
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

  return (
    <div className="turnover-ledger-page" data-testid="turnover-ledger-page">
      <PageScaffold
        title="外部往来款管理"
        actions={(
          <button
            className="turnover-ledger-button"
            disabled={tagLoading}
            onClick={() => setTagDrawerOpen(true)}
            type="button"
          >
            外部往来款标签设置
          </button>
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
        {readModelNeedsRefresh ? (
          <div className="turnover-ledger-page-notice turnover-ledger-page-notice--warning" role="alert">
            往来款台账正在刷新，当前展示的是非最新数据。
          </div>
        ) : null}

        <div className="turnover-ledger-summary-grid">
          <SummaryCard
            label="当前待还款金额"
            value={formatMoney(summary.pendingRepaymentAmount)}
            breakdown={summaryBreakdown("pendingRepaymentAmount")}
            testId="turnover-summary-pending-repayment"
          />
          <SummaryCard
            label="累计已还款金额"
            value={formatMoney(summary.repaidAmount)}
            breakdown={summaryBreakdown("repaidAmount")}
            testId="turnover-summary-repaid"
          />
          <SummaryCard
            label="当前待收款金额"
            value={formatMoney(summary.pendingCollectionAmount)}
            breakdown={summaryBreakdown("pendingCollectionAmount")}
            testId="turnover-summary-pending-collection"
          />
          <SummaryCard
            label="累计已收款金额"
            value={formatMoney(summary.collectedAmount)}
            breakdown={summaryBreakdown("collectedAmount")}
            testId="turnover-summary-collected"
          />
        </div>

        <section className="turnover-ledger-table-panel">
          <div className="turnover-ledger-table-panel__inner">
            <div className="turnover-ledger-table-panel__toolbar">
              <div aria-label="往来款账单范围" className="turnover-ledger-tabs" role="tablist">
                {FAMILY_TABS.map((tab) => (
                  <button
                    aria-selected={family === tab.value}
                    className={`turnover-ledger-tabs__tab${family === tab.value ? " turnover-ledger-tabs__tab--active" : ""}`}
                    key={tab.value}
                    onClick={(event) => handleFamilyChange(event, tab.value)}
                    role="tab"
                    type="button"
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              <div className="turnover-ledger-actions">
                <button
                  className="turnover-ledger-button"
                  disabled={!canMutateData || selectedClosureRows.length < 2}
                  onClick={() => setClosureDrawerOpen(true)}
                  type="button"
                >
                  确认闭环
                </button>
                <button className="turnover-ledger-button turnover-ledger-button--primary" onClick={handleOpenExport} type="button">
                  <Download aria-hidden="true" size={16} strokeWidth={2.2} />
                  下载表格
                </button>
              </div>
            </div>
            <div className="turnover-ledger-table-panel__divider" />
            <TurnoverLedgerGroupedTable
              groups={groups}
              loading={loading}
              onEdit={handleOpenEditor}
              selectedFlowRowIds={selectedFlowRowIds}
              onToggleFlowSelection={handleToggleClosureRow}
              actionsDisabled={false}
            />
          </div>
        </section>
      </PageScaffold>

      <AppDrawer
        className="turnover-ledger-drawer"
        closeLabel="关闭外部往来款标签设置"
        open={tagDrawerOpen}
        onClose={() => setTagDrawerOpen(false)}
        subtitle={`版本 ${tagSelection.version}`}
        title="外部往来款标签设置"
        width={520}
      >
        <div className="turnover-ledger-drawer__content">
          <div className="turnover-ledger-drawer__actions">
            <button className="turnover-ledger-button" disabled={tagSaving} onClick={() => setDraftSelectedTagCodes(new Set(tagSelection.activeTags.map((tag) => tag.code)))} type="button">全选</button>
            <button className="turnover-ledger-button" disabled={tagSaving} onClick={() => setDraftSelectedTagCodes(new Set())} type="button">清空</button>
            <button className="turnover-ledger-button turnover-ledger-button--primary" disabled={tagSaving} onClick={() => void handleSaveTagSelection()} type="button">保存</button>
          </div>
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
                  <label className="turnover-ledger-checkbox-row turnover-ledger-checkbox-row--primary">
                    <input
                      aria-checked={checkedCount > 0 && !allChecked ? "mixed" : allChecked}
                      checked={allChecked}
                      className="turnover-ledger-checkbox"
                      type="checkbox"
                        onChange={(event) => {
                          setDraftSelectedTagCodes((current) => {
                            const next = new Set(current);
                            codes.forEach((code) => {
                              if (event.target.checked) {
                                next.add(code);
                              } else {
                                next.delete(code);
                              }
                            });
                            return next;
                          });
                        }}
                    />
                    <span>{group.primaryLabel}</span>
                  </label>
                  <div className="turnover-ledger-tag-group__children">
                    {group.tags.map((tag) => {
                      const label = tagSubLabel(tag) || SELF_SUB_LABEL;
                      return (
                        <label className="turnover-ledger-checkbox-row" key={tag.code}>
                          <input
                            checked={draftSelectedTagCodes.has(tag.code)}
                            className="turnover-ledger-checkbox"
                            type="checkbox"
                              onChange={(event) => {
                                setDraftSelectedTagCodes((current) => {
                                  const next = new Set(current);
                                  if (event.target.checked) {
                                    next.add(tag.code);
                                  } else {
                                    next.delete(tag.code);
                                  }
                                  return next;
                                });
                              }}
                          />
                          <span>{label}</span>
                        </label>
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
        subtitle={closureSelection?.groupLabel || "未选择往来组"}
        title="确认外部往来闭环"
        width={520}
      >
        <div className="turnover-ledger-drawer__content">
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
                  <span className="turnover-ledger-closure-card__muted">{item.bankRowId}</span>
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
            <button className="turnover-ledger-button" disabled={closureSubmitting} onClick={() => setClosureDrawerOpen(false)} type="button">取消</button>
            <button
              className="turnover-ledger-button turnover-ledger-button--primary"
              disabled={!closurePreview.canConfirm || closureSubmitting}
              onClick={() => void handleConfirmClosure()}
              type="button"
            >
              确定
            </button>
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
          setSelectedRow(null);
          setDetail(null);
          setDetailError(null);
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
