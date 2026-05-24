import { useCallback, useEffect, useMemo, useState, type SyntheticEvent } from "react";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";

import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import TurnoverLedgerExportDialog from "../components/turnoverLedger/TurnoverLedgerExportDialog";
import TurnoverLedgerExtraDrawer from "../components/turnoverLedger/TurnoverLedgerExtraDrawer";
import TurnoverLedgerGroupedTable, { formatMoney } from "../components/turnoverLedger/TurnoverLedgerGroupedTable";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  FINANCE_DOMAIN_EVENTS,
  emitFinanceDomainEvent,
  subscribeFinanceDomainEvent,
} from "../features/domainEvents";
import {
  confirmTurnoverRelation,
  downloadTurnoverLedgerExport,
  fetchTurnoverLedgerExportPreview,
  fetchTurnoverLedgerGrouped,
  fetchTurnoverRelationDetail,
  fetchTurnoverRelationExtra,
  saveTurnoverRelationExtra,
  withdrawTurnoverRelation,
} from "../features/turnoverLedger/api";
import type {
  TurnoverLedgerExportPreview,
  TurnoverLedgerExtra,
  TurnoverLedgerFamily,
  TurnoverLedgerGroupedResponse,
  TurnoverLedgerGroupedRow,
  TurnoverLedgerSummary,
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

function isAbortLikeError(caught: unknown) {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return true;
  }
  return caught instanceof Error && (caught.name === "AbortError" || /aborted|abort/i.test(caught.message));
}

function SummaryCard({ label, value, helper }: { label: string; value: string | number; helper?: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, minHeight: 92, borderRadius: 1 }}>
      <Typography variant="body2" color="text.secondary" fontWeight={800}>
        {label}
      </Typography>
      <Typography variant="h6" fontWeight={900} sx={{ mt: 0.75 }}>
        {value}
      </Typography>
      {helper ? (
        <Typography variant="caption" color="text.secondary">
          {helper}
        </Typography>
      ) : null}
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

export default function TurnoverLedgerPage() {
  const { canMutateData } = useSessionPermissions();
  const [family, setFamily] = useState<TurnoverLedgerFamily>("all");
  const [ledger, setLedger] = useState<TurnoverLedgerGroupedResponse | null>(null);
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
  const [exportOpen, setExportOpen] = useState(false);
  const [exportFamily, setExportFamily] = useState<TurnoverLedgerFamily>("all");
  const [exportPreview, setExportPreview] = useState<TurnoverLedgerExportPreview | null>(null);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportDownloading, setExportDownloading] = useState(false);
  const [snackbar, setSnackbar] = useState<{ severity: "success" | "error"; message: string } | null>(null);

  const selectedFamilyLabel = FAMILY_TABS.find((tab) => tab.value === family)?.label ?? "全部";
  const summary = ledger?.summary ?? DEFAULT_SUMMARY;
  const groups = ledger?.groups ?? [];

  const loadLedger = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    fetchTurnoverLedgerGrouped({
      family,
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
    const handleCategoryUpdated = () => {
      loadLedger();
    };
    return subscribeFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, handleCategoryUpdated);
  }, [loadLedger]);

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
    setFamily(nextFamily);
  };

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

  const familySummaries = useMemo(() => ledger?.familySummaries ?? [], [ledger?.familySummaries]);

  return (
    <Box data-testid="turnover-ledger-page">
      <PageScaffold
        title="往来款管理"
        description="基于银行明细标签实时汇总外部往来关系，并把已确认关系同步到关联台。"
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
          <SummaryCard label="待还款金额" value={formatMoney(summary.pendingRepaymentAmount)} />
          <SummaryCard label="已还款金额" value={formatMoney(summary.repaidAmount)} />
          <SummaryCard label="待收款金额" value={formatMoney(summary.pendingCollectionAmount)} />
          <SummaryCard label="已收款金额" value={formatMoney(summary.collectedAmount)} />
          <SummaryCard label="已闭合金额" value={formatMoney(summary.closedAmount)} />
          <SummaryCard label="待人工确认数量" value={summary.suggestedCount} helper={`当前：${selectedFamilyLabel}`} />
          <SummaryCard label="冲突/异常数量" value={summary.conflictCount} />
          <SummaryCard label="账单行数" value={summary.rowCount} />
        </Stack>

        <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
          <Typography variant="subtitle2" fontWeight={900} sx={{ mb: 1 }}>
            分组余额
          </Typography>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            {familySummaries.map((summaryItem) => (
              <Chip
                key={summaryItem.family}
                label={`${summaryItem.label} 余额 ${formatMoney(summaryItem.pendingAmount)} / ${summaryItem.rowCount} 条`}
                variant="outlined"
              />
            ))}
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ borderRadius: 1, overflow: "hidden" }}>
          <Stack spacing={1.5} sx={{ p: 1.5 }}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }} justifyContent="space-between">
              <Tabs value={family} onChange={handleFamilyChange} aria-label="往来款账单范围" variant="scrollable" allowScrollButtonsMobile>
                {FAMILY_TABS.map((tab) => (
                  <Tab key={tab.value} value={tab.value} label={tab.label} />
                ))}
              </Tabs>
              <Button variant="contained" startIcon={<DownloadOutlinedIcon />} onClick={handleOpenExport}>
                下载表格
              </Button>
            </Stack>
            <Divider />
            <TurnoverLedgerGroupedTable groups={groups} loading={loading} onEdit={handleOpenEditor} />
          </Stack>
        </Paper>
      </PageScaffold>

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
