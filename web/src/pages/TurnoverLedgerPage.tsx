import { useCallback, useEffect, useMemo, useState, type SyntheticEvent } from "react";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import TurnoverLedgerExportDialog from "../components/turnoverLedger/TurnoverLedgerExportDialog";
import TurnoverLedgerExtraDrawer from "../components/turnoverLedger/TurnoverLedgerExtraDrawer";
import TurnoverLedgerGroupedTable, { formatMoney, formatNullable } from "../components/turnoverLedger/TurnoverLedgerGroupedTable";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  FINANCE_DOMAIN_EVENTS,
  emitFinanceDomainEvent,
} from "../features/domainEvents";
import { useActiveFinanceDomainEvent } from "../hooks/useActiveFinanceDomainEvent";
import { usePageScrollSession } from "../hooks/usePageScrollSession";
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
    <Paper data-testid={testId} variant="outlined" sx={{ p: 1.25, minHeight: 112, borderRadius: 1 }}>
      <Typography variant="body2" color="text.secondary" fontWeight={800}>
        {label}
      </Typography>
      <Typography variant="h6" fontWeight={900} sx={{ mt: 0.5 }}>
        {value}
      </Typography>
      <Stack spacing={0.25} sx={{ mt: 0.75 }}>
        {breakdown.map((item) => (
          <Stack key={item.label} direction="row" justifyContent="space-between" spacing={1}>
            <Typography variant="caption" color="text.secondary">{item.label}</Typography>
            <Typography variant="caption" fontWeight={800}>{item.value}</Typography>
          </Stack>
        ))}
      </Stack>
    </Paper>
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

function cleanText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function moneyNumber(value: string | null | undefined) {
  const parsed = Number(String(value ?? "").replace(/,/g, "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function flowBankRowId(row: TurnoverLedgerGroupedRow) {
  return cleanText(row.sourceBankRowId) || cleanText(row.bankRowIds[0]) || cleanText(row.flowId);
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
  const incomeAmount = incomeItems.reduce((sum, item) => sum + item.amount, 0);
  const expenseAmount = expenseItems.reduce((sum, item) => sum + item.amount, 0);
  const delta = Math.abs(incomeAmount - expenseAmount);
  return {
    items,
    incomeAmount,
    expenseAmount,
    delta,
    canConfirm: rows.length === 2 && incomeItems.length === 1 && expenseItems.length === 1 && delta === 0,
  };
}

function tagPrimaryLabel(tag: TurnoverLedgerTagDefinition) {
  return cleanText(tag.outputPrimaryLabel) || cleanText(tag.label) || cleanText(tag.code);
}

function tagSubLabel(tag: TurnoverLedgerTagDefinition) {
  return cleanText(tag.outputSubLabel);
}

export default function TurnoverLedgerPage() {
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
  const [snackbar, setSnackbar] = useState<{ severity: "success" | "error"; message: string } | null>(null);
  const tableWrapRef = usePageScrollSession<HTMLDivElement>({
    pageKey: "turnover-ledger",
    scrollKey: "grouped-table",
  });

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

  const loadTagSelection = useCallback((signal?: AbortSignal) => {
    setTagLoading(true);
    fetchTurnoverLedgerTagSelection(signal)
      .then((nextSelection) => {
        setTagSelection(nextSelection);
        setDraftSelectedTagCodes(new Set(nextSelection.selectedTagCodes));
      })
      .catch((caught: unknown) => {
        if (!isAbortLikeError(caught)) {
          setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "外部往来款标签设置加载失败" });
        }
      })
      .finally(() => setTagLoading(false));
  }, []);

  const loadLedger = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    fetchTurnoverLedgerGrouped({
      family,
      direction: "all",
      page: 1,
      pageSize: DEFAULT_PAGE_SIZE,
      signal,
    })
      .then(setLedger)
      .catch((caught: unknown) => {
        if (isAbortLikeError(caught)) {
          return;
        }
        setError(caught instanceof Error ? caught.message : "往来款台账加载失败");
      })
      .finally(() => setLoading(false));
  }, [family]);

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
      setSnackbar({ severity: "error", message: "这条流水缺少银行流水 ID，无法选择" });
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
        setSnackbar({ severity: "error", message: "一次只能选择同一往来组内的两条流水" });
        return current;
      }
      const exists = current.rows.some((item) => flowBankRowId(item) === rowId);
      if (exists) {
        const rows = current.rows.filter((item) => flowBankRowId(item) !== rowId);
        return rows.length > 0 ? { ...current, rows } : null;
      }
      if (current.rows.length >= 2) {
        setSnackbar({ severity: "error", message: "一次最多选择两条流水" });
        return current;
      }
      return { ...current, rows: [...current.rows, row] };
    });
  };

  const handleConfirmClosure = async () => {
    if (!closurePreview.canConfirm || closureSubmitting) {
      return;
    }
    const bankRowIds = selectedClosureRows.map(flowBankRowId).filter(Boolean);
    if (bankRowIds.length !== 2) {
      return;
    }
    setClosureSubmitting(true);
    try {
      const result = await confirmTurnoverClosure({ bankRowIds });
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.turnoverRelationUpdated, {
        relationId: result.relationId,
        affectedRowIds: bankRowIds,
        affectedMonths: result.affectedMonths,
        action: "manual_closure",
        source: "turnover_manual_closure",
      });
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
        relationId: result.workbenchPairRelationId,
        affectedRowIds: bankRowIds,
        affectedMonths: result.affectedMonths,
        action: "turnover_manual_closure",
        source: "turnover_manual_closure",
      });
      setClosureSelection(null);
      setClosureDrawerOpen(false);
      setSnackbar({ severity: "success", message: "外部往来闭环已确认" });
      loadLedger();
    } catch (caught) {
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "外部往来闭环确认失败" });
    } finally {
      setClosureSubmitting(false);
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
    const normalizedRow = { ...row, relationId: relationIdForRow(row) };
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
        setDetailError(caught instanceof Error ? caught.message : "往来关系详情加载失败");
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
    setSavingExtra(true);
    try {
      const saved = await saveTurnoverRelationExtra(selectedRow.relationId, extraForm);
      setExtraForm(saved.extra);
      setExtraDirty(false);
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.turnoverLedgerExtraUpdated, {
        relationId: selectedRow.relationId,
        source: "turnover_extra_save",
      });
      setSnackbar({ severity: "success", message: "补充信息已保存" });
      loadLedger();
    } catch (caught) {
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "补充信息保存失败" });
    } finally {
      setSavingExtra(false);
    }
  };

  const handleRelationMutation = async (kind: "confirm" | "withdraw") => {
    if (!selectedRow || mutatingRelation) {
      return;
    }
    setMutatingRelation(true);
    try {
      const result = kind === "confirm"
        ? await confirmTurnoverRelation({ bankRowIds: selectedRow.bankRowIds })
        : await withdrawTurnoverRelation({ relationId: selectedRow.relationId });
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.turnoverRelationUpdated, {
        relationId: result.relationId || selectedRow.relationId,
        action: kind,
        source: "turnover_relation_mutation",
      });
      setSnackbar({ severity: "success", message: kind === "confirm" ? "往来关系已确认归并" : "往来归并已撤销" });
      loadLedger();
    } catch (caught) {
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "往来关系操作失败" });
    } finally {
      setMutatingRelation(false);
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
    setTagSaving(true);
    try {
      const saved = await saveTurnoverLedgerTagSelection({
        expectedVersion: tagSelection.version,
        selectedTagCodes: Array.from(draftSelectedTagCodes),
      });
      setTagSelection(saved);
      setDraftSelectedTagCodes(new Set(saved.selectedTagCodes));
      setTagDrawerOpen(false);
      setSnackbar({ severity: "success", message: "外部往来款标签设置已保存" });
      loadLedger();
    } catch (caught) {
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "外部往来款标签设置保存失败" });
    } finally {
      setTagSaving(false);
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
      setSnackbar({ severity: "success", message: "往来款台账下载已开始" });
      setExportOpen(false);
    } catch (caught) {
      setExportError(caught instanceof Error ? caught.message : "往来款台账下载失败");
    } finally {
      setExportDownloading(false);
    }
  };

  return (
    <Box data-testid="turnover-ledger-page">
      <PageScaffold
        title="外部往来款管理"
        description="基于银行明细标签实时汇总外部往来关系，并把已确认关系同步到关联台。"
        actions={(
          <Button disabled={tagLoading} onClick={() => setTagDrawerOpen(true)} variant="outlined">
            外部往来款标签设置
          </Button>
        )}
      >
        {!canMutateData ? (
          <Alert severity="info">当前账号为只读权限，可查看台账与详情，不能确认或撤销归并。</Alert>
        ) : null}

        {error ? (
          <StatePanel tone="error" title="往来款台账加载失败">
            {error}
          </StatePanel>
        ) : null}

        <Stack
          direction="row"
          spacing={1.5}
          useFlexGap
          flexWrap="wrap"
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", lg: "repeat(4, minmax(0, 1fr))" },
          }}
        >
          <SummaryCard
            label="待还款金额"
            value={formatMoney(summary.pendingRepaymentAmount)}
            breakdown={summaryBreakdown("pendingRepaymentAmount")}
            testId="turnover-summary-pending-repayment"
          />
          <SummaryCard
            label="已还款金额"
            value={formatMoney(summary.repaidAmount)}
            breakdown={summaryBreakdown("repaidAmount")}
            testId="turnover-summary-repaid"
          />
          <SummaryCard
            label="待收款金额"
            value={formatMoney(summary.pendingCollectionAmount)}
            breakdown={summaryBreakdown("pendingCollectionAmount")}
            testId="turnover-summary-pending-collection"
          />
          <SummaryCard
            label="已收款金额"
            value={formatMoney(summary.collectedAmount)}
            breakdown={summaryBreakdown("collectedAmount")}
            testId="turnover-summary-collected"
          />
        </Stack>

        <Paper variant="outlined" sx={{ borderRadius: 1, overflow: "hidden" }}>
          <Stack spacing={1.5} sx={{ p: 1.5 }}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }} justifyContent="space-between">
              <Tabs value={family} onChange={handleFamilyChange} aria-label="往来款账单范围" variant="scrollable" allowScrollButtonsMobile>
                {FAMILY_TABS.map((tab) => (
                  <Tab key={tab.value} value={tab.value} label={tab.label} />
                ))}
              </Tabs>
              <Stack direction="row" spacing={1}>
                <Button
                  disabled={!canMutateData || selectedClosureRows.length !== 2}
                  onClick={() => setClosureDrawerOpen(true)}
                  variant="outlined"
                >
                  确认闭环
                </Button>
                <Button variant="contained" startIcon={<DownloadOutlinedIcon />} onClick={handleOpenExport}>
                  下载表格
                </Button>
              </Stack>
            </Stack>
            <Divider />
            <TurnoverLedgerGroupedTable
              groups={groups}
              loading={loading}
              onEdit={handleOpenEditor}
              selectedFlowRowIds={selectedFlowRowIds}
              onToggleFlowSelection={handleToggleClosureRow}
              tableWrapRef={tableWrapRef}
            />
          </Stack>
        </Paper>
      </PageScaffold>

      <Drawer
        anchor="right"
        open={tagDrawerOpen}
        onClose={() => setTagDrawerOpen(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: "520px" }, maxWidth: "100vw" }, role: "dialog", "aria-label": "外部往来款标签设置" }}
      >
        <Stack spacing={0} sx={{ height: "100%" }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 1.5 }}>
            <Box>
              <Typography component="h2" variant="h6" fontWeight={900}>外部往来款标签设置</Typography>
              <Typography color="text.secondary" variant="caption">版本 {tagSelection.version}</Typography>
            </Box>
            <IconButton aria-label="关闭外部往来款标签设置" onClick={() => setTagDrawerOpen(false)}>
              <CloseIcon />
            </IconButton>
          </Stack>
          <Divider />
          <Stack direction="row" spacing={1} sx={{ p: 2 }}>
            <Button disabled={tagSaving} onClick={() => setDraftSelectedTagCodes(new Set(tagSelection.activeTags.map((tag) => tag.code)))} size="small" variant="outlined">全选</Button>
            <Button disabled={tagSaving} onClick={() => setDraftSelectedTagCodes(new Set())} size="small" variant="outlined">清空</Button>
            <Button disabled={tagSaving} onClick={() => void handleSaveTagSelection()} size="small" variant="contained">保存</Button>
          </Stack>
          {tagSelection.inactiveSelectedTagCodes.length > 0 ? (
            <Alert severity="warning" sx={{ mx: 2, mb: 1 }}>
              已停用或不再属于外部往来款的标签不再生效：{tagSelection.inactiveSelectedTagCodes.join("、")}。保存后会清理这些引用。
            </Alert>
          ) : null}
          <Stack divider={<Divider flexItem />} sx={{ overflow: "auto" }}>
            {tagLoading ? <StatePanel compact tone="loading" title="标签加载中" /> : null}
            {!tagLoading && drawerGroups.length === 0 ? <StatePanel compact tone="empty" title="暂无可用外部往来款标签" /> : null}
            {!tagLoading ? drawerGroups.map((group) => {
              const codes = group.tags.map((tag) => tag.code);
              const checkedCount = codes.filter((code) => draftSelectedTagCodes.has(code)).length;
              const allChecked = checkedCount === codes.length && codes.length > 0;
              return (
                <Box key={group.primaryLabel} sx={{ p: 2 }}>
                  <FormControlLabel
                    control={(
                      <Checkbox
                        checked={allChecked}
                        indeterminate={checkedCount > 0 && !allChecked}
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
                    )}
                    label={<Typography fontWeight={900}>{group.primaryLabel}</Typography>}
                  />
                  <Stack sx={{ pl: 4 }}>
                    {group.tags.map((tag) => {
                      const label = tagSubLabel(tag) || SELF_SUB_LABEL;
                      return (
                        <FormControlLabel
                          key={tag.code}
                          control={(
                            <Checkbox
                              checked={draftSelectedTagCodes.has(tag.code)}
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
                          )}
                          label={label}
                        />
                      );
                    })}
                  </Stack>
                </Box>
              );
            }) : null}
          </Stack>
        </Stack>
      </Drawer>

      <Drawer
        anchor="right"
        open={closureDrawerOpen}
        onClose={() => setClosureDrawerOpen(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: "520px" }, maxWidth: "100vw" }, role: "dialog", "aria-label": "确认外部往来闭环" }}
      >
        <Stack spacing={0} sx={{ height: "100%" }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 1.5 }}>
            <Box>
              <Typography component="h2" variant="h6" fontWeight={900}>确认外部往来闭环</Typography>
              <Typography color="text.secondary" variant="caption">{closureSelection?.groupLabel || "未选择往来组"}</Typography>
            </Box>
            <IconButton aria-label="关闭确认外部往来闭环" onClick={() => setClosureDrawerOpen(false)}>
              <CloseIcon />
            </IconButton>
          </Stack>
          <Divider />
          <Stack spacing={1.5} sx={{ p: 2, overflow: "auto", flex: 1 }}>
            {closurePreview.items.map((item) => {
              const { row } = item;
              return (
                <Paper key={item.bankRowId} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                  <Stack spacing={0.75}>
                    <Stack direction="row" justifyContent="space-between" spacing={1}>
                      <Typography fontWeight={900}>{item.directionLabel}</Typography>
                      <Typography fontWeight={900}>{formatMoney(String(item.amount.toFixed(2)))}</Typography>
                    </Stack>
                    <Typography variant="body2">{formatNullable(row.transactionAt || row.borrowDate || row.repaymentDate)}</Typography>
                    <Typography variant="body2" color="text.secondary">{item.bankRowId}</Typography>
                    <Typography variant="body2" color="text.secondary">{formatNullable(row.repaymentRemark || row.summaryText)}</Typography>
                  </Stack>
                </Paper>
              );
            })}
            <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
              <Stack spacing={0.75}>
                <Stack direction="row" justifyContent="space-between">
                  <Typography color="text.secondary">收入合计</Typography>
                  <Typography fontWeight={800}>{formatMoney(closurePreview.incomeAmount.toFixed(2))}</Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography color="text.secondary">支出合计</Typography>
                  <Typography fontWeight={800}>{formatMoney(closurePreview.expenseAmount.toFixed(2))}</Typography>
                </Stack>
                <Divider />
                <Stack direction="row" justifyContent="space-between">
                  <Typography fontWeight={900}>差额</Typography>
                  <Typography data-testid="turnover-closure-delta" fontWeight={900}>{formatMoney(closurePreview.delta.toFixed(2))}</Typography>
                </Stack>
              </Stack>
            </Paper>
            {!closurePreview.canConfirm ? (
              <Alert severity="info">只有一收一支且差额为 0.00 的两条流水可以确认闭环。</Alert>
            ) : null}
          </Stack>
          <Divider />
          <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ p: 2 }}>
            <Button disabled={closureSubmitting} onClick={() => setClosureDrawerOpen(false)} variant="outlined">取消</Button>
            <Button
              disabled={!closurePreview.canConfirm || closureSubmitting}
              onClick={() => void handleConfirmClosure()}
              variant="contained"
            >
              确定
            </Button>
          </Stack>
        </Stack>
      </Drawer>

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

      <Snackbar
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        autoHideDuration={4000}
        open={snackbar !== null}
        onClose={() => setSnackbar(null)}
      >
        {snackbar ? (
          <Alert severity={snackbar.severity} variant="filled" onClose={() => setSnackbar(null)} sx={{ width: "100%" }}>
            {snackbar.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </Box>
  );
}
