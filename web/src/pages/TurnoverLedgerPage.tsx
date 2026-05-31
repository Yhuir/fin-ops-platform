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
  fetchTurnoverLedgerTagSelection,
  fetchTurnoverRelationDetail,
  fetchTurnoverRelationExtra,
  saveTurnoverLedgerTagSelection,
  saveTurnoverRelationExtra,
  withdrawTurnoverRelation,
} from "../features/turnoverLedger/api";
import type {
  TurnoverLedgerExportPreview,
  TurnoverLedgerDirectionFilter,
  TurnoverLedgerExtra,
  TurnoverLedgerFamily,
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

const DIRECTION_FILTERS: Array<{ value: TurnoverLedgerDirectionFilter; label: string; ariaLabel: string }> = [
  { value: "all", label: "全部", ariaLabel: "全部方向" },
  { value: "borrow_out", label: "借出", ariaLabel: "借出" },
  { value: "borrow_in", label: "借入", ariaLabel: "借入" },
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

function cleanText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function tagPrimaryLabel(tag: TurnoverLedgerTagDefinition) {
  return cleanText(tag.outputPrimaryLabel) || cleanText(tag.label) || cleanText(tag.code);
}

function tagSubLabel(tag: TurnoverLedgerTagDefinition) {
  return cleanText(tag.outputSubLabel);
}

export default function TurnoverLedgerPage() {
  const { canMutateData } = useSessionPermissions();
  const [direction, setDirection] = useState<TurnoverLedgerDirectionFilter>("all");
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
  const [exportOpen, setExportOpen] = useState(false);
  const [exportFamily, setExportFamily] = useState<TurnoverLedgerFamily>("all");
  const [exportPreview, setExportPreview] = useState<TurnoverLedgerExportPreview | null>(null);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportDownloading, setExportDownloading] = useState(false);
  const [snackbar, setSnackbar] = useState<{ severity: "success" | "error"; message: string } | null>(null);

  const summary = ledger?.summary ?? DEFAULT_SUMMARY;
  const groups = ledger?.groups ?? [];

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
      direction,
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
  }, [direction, family]);

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
    const handleCategoryUpdated = () => {
      loadTagSelection();
      loadLedger();
    };
    return subscribeFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, handleCategoryUpdated);
  }, [loadLedger, loadTagSelection]);

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

  const availableFamilyTabs = useMemo(() => (
    direction === "borrow_in"
      ? FAMILY_TABS.filter((tab) => tab.value !== "business")
      : FAMILY_TABS
  ), [direction]);

  const drawerGroups = useMemo(() => {
    const grouped = new Map<string, TurnoverLedgerTagDefinition[]>();
    tagSelection.activeTags.forEach((tag) => {
      const primary = tagPrimaryLabel(tag) || tag.label || tag.code;
      grouped.set(primary, [...(grouped.get(primary) ?? []), tag]);
    });
    return Array.from(grouped.entries()).map(([primaryLabel, tags]) => ({ primaryLabel, tags }));
  }, [tagSelection.activeTags]);

  const handleDirectionChange = (nextDirection: TurnoverLedgerDirectionFilter) => {
    setDirection(nextDirection);
    if (nextDirection === "borrow_in" && family === "business") {
      setFamily("all");
    }
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
          <SummaryCard label="待还款金额" value={formatMoney(summary.pendingRepaymentAmount)} />
          <SummaryCard label="已还款金额" value={formatMoney(summary.repaidAmount)} />
          <SummaryCard label="待收款金额" value={formatMoney(summary.pendingCollectionAmount)} />
          <SummaryCard label="已收款金额" value={formatMoney(summary.collectedAmount)} />
        </Stack>

        <Paper variant="outlined" sx={{ borderRadius: 1, overflow: "hidden" }}>
          <Stack spacing={1.5} sx={{ p: 1.5 }}>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              {DIRECTION_FILTERS.map((item) => (
                <Button
                  key={item.value}
                  variant={direction === item.value ? "contained" : "outlined"}
                  aria-pressed={direction === item.value}
                  aria-label={item.ariaLabel}
                  onClick={() => handleDirectionChange(item.value)}
                >
                  {item.label}
                </Button>
              ))}
            </Stack>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }} justifyContent="space-between">
              <Tabs value={family} onChange={handleFamilyChange} aria-label="往来款账单范围" variant="scrollable" allowScrollButtonsMobile>
                {availableFamilyTabs.map((tab) => (
                  <Tab key={tab.value} value={tab.value} label={tab.label} />
                ))}
              </Tabs>
              <Stack direction="row" spacing={1}>
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
