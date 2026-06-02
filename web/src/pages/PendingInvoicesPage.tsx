import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TablePagination from "@mui/material/TablePagination";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";

import ManualInvoiceDialog from "../components/pendingInvoices/ManualInvoiceDialog";
import PendingInvoiceDetailDrawer from "../components/pendingInvoices/PendingInvoiceDetailDrawer";
import PendingInvoiceExportDrawer from "../components/pendingInvoices/PendingInvoiceExportDrawer";
import PendingInvoiceInvoicePickerDrawer from "../components/pendingInvoices/PendingInvoiceInvoicePickerDrawer";
import PendingInvoiceRelationDrawer from "../components/pendingInvoices/PendingInvoiceRelationDrawer";
import PendingInvoiceRulesDrawer from "../components/pendingInvoices/PendingInvoiceRulesDrawer";
import PendingInvoicesTable from "../components/pendingInvoices/PendingInvoicesTable";
import {
  confirmAttachExistingInvoice,
  downloadPendingInvoiceExport,
  fetchPendingInvoiceCandidates,
  fetchPendingInvoiceExportPreview,
  fetchPendingInvoiceObjectDetail,
  fetchPendingInvoiceRelationDetail,
  fetchPendingInvoiceRows,
  fetchPendingInvoiceRules,
  previewAttachExistingInvoice,
  savePendingInvoiceRules,
  savePendingInvoiceIncomeStatus,
} from "../features/pendingInvoices/api";
import { FINANCE_DOMAIN_EVENTS, emitFinanceDomainEvent } from "../features/domainEvents";
import type {
  AttachExistingInvoiceResult,
  FetchPendingInvoiceRowsRequest,
  ManualPendingInvoiceResult,
  PendingInvoiceDirection,
  PendingInvoiceFilter,
  PendingInvoiceObjectDetailTarget,
  PendingInvoiceRow,
  PendingInvoiceSortDirection,
  PendingInvoiceSortField,
  PendingInvoiceSourceSummary,
} from "../features/pendingInvoices/types";

const DEFAULT_PAGE_SIZE = 50;
const TAG_SYNC_EVENT = "finops:bank-transaction-tags-updated";
const TAG_VERSION_STORAGE_KEY = "finops.bankTransactionTags.version";

type ActiveDrawer = "rules" | "relation" | "invoicePicker" | "detail" | "export" | null;
type RelationTarget = { transactionId: string } | null;
type RulesDirection = Exclude<PendingInvoiceDirection, "all">;

const EXPENSE_FILTER_LABELS: Record<PendingInvoiceFilter, string> = {
  all: "全部",
  requires_invoice: "需要开票",
  bank_statement_as_invoice: "流水代替发票",
  no_invoice_required: "无需开票",
  cash_income: "现金收入",
};

const INCOME_FILTER_LABELS: Record<PendingInvoiceFilter, string> = {
  all: "全部",
  requires_invoice: "待开发票",
  bank_statement_as_invoice: "流水代替发票",
  no_invoice_required: "无需开票",
  cash_income: "现金收入",
};

function filterLabel(direction: PendingInvoiceDirection, filter: PendingInvoiceFilter) {
  return (direction === "income" ? INCOME_FILTER_LABELS : EXPENSE_FILTER_LABELS)[filter];
}

function isAbortLikeError(caught: unknown) {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return true;
  }
  return caught instanceof Error && (caught.name === "AbortError" || /aborted|abort/i.test(caught.message));
}

function eventVersion(event: Event) {
  if (!(event instanceof CustomEvent) || !event.detail || typeof event.detail !== "object") {
    return null;
  }
  const version = Number((event.detail as { version?: unknown }).version);
  return Number.isFinite(version) ? version : null;
}

function persistTagVersion(version: number | null | undefined) {
  if (typeof version !== "number" || !Number.isFinite(version)) {
    return;
  }
  try {
    window.localStorage.setItem(TAG_VERSION_STORAGE_KEY, String(version));
  } catch {
    // localStorage can be unavailable in embedded contexts.
  }
}

function readPersistedTagVersion() {
  try {
    const value = Number(window.localStorage.getItem(TAG_VERSION_STORAGE_KEY));
    return Number.isFinite(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

export default function PendingInvoicesPage() {
  const [direction, setDirection] = useState<PendingInvoiceDirection>("expense");
  const [filter, setFilter] = useState<PendingInvoiceFilter>("all");
  const [rows, setRows] = useState<PendingInvoiceRow[]>([]);
  const [total, setTotal] = useState(0);
  const [sourceSummary, setSourceSummary] = useState<PendingInvoiceSourceSummary | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [keyword, setKeyword] = useState("");
  const [sortField, setSortField] = useState<PendingInvoiceSortField>("trade_date");
  const [sortDirection, setSortDirection] = useState<PendingInvoiceSortDirection>("desc");
  const [activeDrawer, setActiveDrawer] = useState<ActiveDrawer>(null);
  const [rulesDirection, setRulesDirection] = useState<RulesDirection>("expense");
  const [detailTarget, setDetailTarget] = useState<PendingInvoiceObjectDetailTarget | null>(null);
  const [relationTarget, setRelationTarget] = useState<RelationTarget>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [readModelStatus, setReadModelStatus] = useState("");
  const [filterAnchorEl, setFilterAnchorEl] = useState<HTMLElement | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [rulesTagRefreshToken, setRulesTagRefreshToken] = useState(0);
  const [dialogRow, setDialogRow] = useState<PendingInvoiceRow | null>(null);
  const tagVersionRef = useRef<number | null>(readPersistedTagVersion());

  const filterOpen = Boolean(filterAnchorEl);

  const query = useMemo<FetchPendingInvoiceRowsRequest>(() => ({
    direction,
    filter,
    keyword,
    page,
    pageSize,
    sortField,
    sortDirection,
  }), [direction, filter, keyword, page, pageSize, sortDirection, sortField]);

  const loadRows = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    fetchPendingInvoiceRows({ ...query, signal })
      .then((payload) => {
        setRows(payload.rows);
        setTotal(payload.pagination.total);
        setSourceSummary(payload.summary.sourceSummary ?? null);
        setReadModelStatus(payload.readModelStatus);
        const version = payload.tagDictionary?.version;
        if (typeof version === "number" && version > 0) {
          const previousVersion = tagVersionRef.current;
          tagVersionRef.current = version;
          persistTagVersion(version);
          if (previousVersion !== null && previousVersion !== version) {
            setRulesTagRefreshToken((current) => current + 1);
          }
        }
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setError(caught instanceof Error ? caught.message : "待找发票加载失败。");
        }
      })
      .finally(() => {
        if (!signal?.aborted) {
          setLoading(false);
        }
      });
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();
    loadRows(controller.signal);
    return () => controller.abort();
  }, [loadRows, refreshToken]);

  useEffect(() => {
    const handleTagUpdate = (event: Event) => {
      const version = eventVersion(event);
      if (version !== null) {
        tagVersionRef.current = version;
        persistTagVersion(version);
      }
      setRulesTagRefreshToken((current) => current + 1);
      setRefreshToken((current) => current + 1);
    };
    window.addEventListener(TAG_SYNC_EVENT, handleTagUpdate);

    let channel: BroadcastChannel | null = null;
    if (typeof BroadcastChannel !== "undefined") {
      channel = new BroadcastChannel(TAG_SYNC_EVENT);
      channel.onmessage = (message) => {
        const version = Number((message.data as { version?: unknown } | undefined)?.version);
        window.dispatchEvent(new CustomEvent(TAG_SYNC_EVENT, { detail: { version: Number.isFinite(version) ? version : undefined } }));
      };
    }

    const handleFocus = () => {
      const persistedVersion = readPersistedTagVersion();
      if (persistedVersion !== null && persistedVersion !== tagVersionRef.current) {
        tagVersionRef.current = persistedVersion;
        setRulesTagRefreshToken((current) => current + 1);
      }
      setRefreshToken((current) => current + 1);
    };
    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener(TAG_SYNC_EVENT, handleTagUpdate);
      window.removeEventListener("focus", handleFocus);
      channel?.close();
    };
  }, []);

  const filterOptions = useMemo<PendingInvoiceFilter[]>(() => (
    direction === "expense" ? [
    "all",
    "requires_invoice",
    "bank_statement_as_invoice",
    "no_invoice_required",
  ] : direction === "income" ? [
    "all",
    "requires_invoice",
    "no_invoice_required",
    "cash_income",
  ] : ["all"]
  ), [direction]);

  const tableConfig = useMemo(() => ({
    sortField,
    sortDirection,
  }), [sortDirection, sortField]);
  const actionsDisabled = Boolean(readModelStatus && readModelStatus !== "fresh");

  const handleSortChange = useCallback((field: PendingInvoiceSortField) => {
    setPage(1);
    if (field === sortField) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortField(field);
    setSortDirection("asc");
  }, [sortField]);

  const handleOpenRelation = useCallback((row: PendingInvoiceRow) => {
    setRelationTarget({ transactionId: row.bankTransaction.id || row.id });
    setActiveDrawer("relation");
  }, []);

  const handleOpenInvoicePicker = useCallback((row: PendingInvoiceRow) => {
    setRelationTarget({ transactionId: row.bankTransaction.id || row.id });
    setActiveDrawer("invoicePicker");
  }, []);

  const handleOpenInvoicePickerById = useCallback((transactionId: string) => {
    setRelationTarget({ transactionId });
    setActiveDrawer("invoicePicker");
  }, []);

  const handleOpenDetail = useCallback((target: PendingInvoiceObjectDetailTarget) => {
    setDetailTarget(target);
    setActiveDrawer("detail");
  }, []);

  function closeDrawer() {
    setActiveDrawer(null);
    setDetailTarget(null);
    setRelationTarget(null);
  }

  function handleManualConfirmed(result: ManualPendingInvoiceResult) {
    setDialogRow(null);
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.invoiceFactUpdated, {
      affectedMonths: result.affectedMonths,
      affectedRowIds: [...result.affectedTransactionIds, ...result.affectedInvoiceIds],
      source: "pending_invoice_manual_invoice",
    });
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
      affectedMonths: result.affectedMonths,
      affectedRowIds: result.affectedTransactionIds,
      source: "pending_invoice_manual_invoice",
    });
    const updatedRow = result.row;
    if (updatedRow) {
      setRows((current) => current.map((row) => (row.id === updatedRow.id ? updatedRow : row)));
      return;
    }
    setRefreshToken((current) => current + 1);
  }

  function handleAttachConfirmed(result: AttachExistingInvoiceResult) {
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.invoiceFactUpdated, {
      affectedMonths: result.affectedMonths,
      affectedRowIds: [...result.affectedTransactionIds, ...result.affectedInvoiceIds],
      source: "pending_invoice_attach_existing_invoice",
    });
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
      affectedMonths: result.affectedMonths,
      affectedRowIds: result.affectedTransactionIds,
      source: "pending_invoice_attach_existing_invoice",
    });
    if (result.row) {
      setRows((current) => current.map((row) => (row.id === result.row?.id ? result.row : row)));
    } else {
      setRefreshToken((current) => current + 1);
    }
    closeDrawer();
  }

  const loadRelation = useCallback((transactionId: string) => fetchPendingInvoiceRelationDetail(transactionId, direction), [direction]);
  const loadObjectDetail = useCallback((target: PendingInvoiceObjectDetailTarget) => fetchPendingInvoiceObjectDetail(target), []);
  const loadRules = useCallback(() => fetchPendingInvoiceRules(rulesDirection), [rulesDirection]);
  const saveRules = useCallback((payload: Parameters<typeof savePendingInvoiceRules>[0]) => savePendingInvoiceRules(payload, rulesDirection), [rulesDirection]);
  const loadCandidates = useCallback(fetchPendingInvoiceCandidates, []);
  const loadExportPreview = useCallback(() => fetchPendingInvoiceExportPreview(query), [query]);
  const handleDownloadExport = useCallback(() => downloadPendingInvoiceExport(query), [query]);

  const handleDirectionChange = useCallback((nextDirection: PendingInvoiceDirection) => {
    setDirection(nextDirection);
    setFilter("all");
    setPage(1);
  }, []);

  const handleOpenRules = useCallback((nextRulesDirection: RulesDirection) => {
    setRulesDirection(nextRulesDirection);
    setActiveDrawer("rules");
  }, []);

  const handleMarkIncomeStatus = useCallback((row: PendingInvoiceRow, statusCode: "income_no_invoice_required" | "cash_income") => {
    savePendingInvoiceIncomeStatus(row.id, statusCode)
      .then((result) => {
        if (result.row) {
          setRows((current) => current.map((item) => (item.id === result.row?.id ? result.row : item)));
        }
        setRefreshToken((current) => current + 1);
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "收入流水状态保存失败。");
      });
  }, []);

  const compactStatusText = error
    ? error
    : readModelStatus === "refreshing"
      ? "数据刷新中"
      : readModelStatus && !["fresh", "refreshing"].includes(readModelStatus)
        ? `读模型 ${readModelStatus}，写入和导出已暂停`
        : "";

  const summaryCounts = {
    all: sourceSummary?.bankTransactionRows ?? 0,
    expense: sourceSummary?.expenseRows ?? 0,
    income: sourceSummary?.incomeRows ?? 0,
  };

  const statusFilterControl = (
    <Button
      variant="outlined"
      size="small"
      aria-haspopup="menu"
      aria-label={`筛选发票获取状态：${filterLabel(direction, filter)}`}
      onClick={(event) => setFilterAnchorEl(event.currentTarget)}
      sx={{
        minHeight: 24,
        height: 24,
        px: 0.8,
        py: 0,
        fontSize: 11,
        lineHeight: 1,
        borderRadius: 1,
        whiteSpace: "nowrap",
      }}
    >
      {filterLabel(direction, filter)}
    </Button>
  );

  return (
    <Box data-testid="pending-invoices-page" sx={{ px: { xs: 2, md: 3 }, py: 2 }}>
      <Stack spacing={1}>
        <Box sx={{ borderBottom: "1px solid", borderColor: "divider", pb: 1 }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ xs: "stretch", md: "center" }} justifyContent="space-between">
            <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
              <Typography component="h1" fontWeight={900} sx={{ fontSize: 18, lineHeight: 1.3 }}>待找发票</Typography>
              <ToggleButtonGroup
                exclusive
                size="small"
                value={direction}
                onChange={(_event, nextDirection: PendingInvoiceDirection | null) => {
                  if (nextDirection) {
                    handleDirectionChange(nextDirection);
                  }
                }}
                aria-label="待找发票流水范围"
                sx={{
                  "& .MuiToggleButton-root": {
                    minHeight: 30,
                    px: 1.2,
                    py: 0.25,
                    fontSize: 12,
                    fontWeight: 800,
                    lineHeight: 1.2,
                    whiteSpace: "nowrap",
                  },
                }}
              >
                <ToggleButton value="all">全部 {summaryCounts.all}</ToggleButton>
                <ToggleButton value="expense">支出 {summaryCounts.expense}</ToggleButton>
                <ToggleButton value="income">收入 {summaryCounts.income}</ToggleButton>
              </ToggleButtonGroup>
              <Menu anchorEl={filterAnchorEl} open={filterOpen} onClose={() => setFilterAnchorEl(null)}>
                {filterOptions.map((option) => (
                  <MenuItem
                    key={option}
                    selected={option === filter}
                    onClick={() => {
                      setFilter(option);
                      setPage(1);
                      setFilterAnchorEl(null);
                    }}
                  >
                    {filterLabel(direction, option)}
                  </MenuItem>
                ))}
              </Menu>
            </Stack>
            <Stack direction="row" spacing={1} alignItems="center" justifyContent={{ xs: "space-between", md: "flex-end" }}>
              <Typography
                color={error ? "error" : readModelStatus && !["fresh", "refreshing"].includes(readModelStatus) ? "warning.main" : "text.secondary"}
                sx={{ minWidth: 74, fontSize: 12, lineHeight: 1.25 }}
              >
                {compactStatusText}
              </Typography>
              <Button size="small" variant="outlined" onClick={() => handleOpenRules("expense")} sx={{ whiteSpace: "nowrap" }}>
                支出待找发票规则设置
              </Button>
              <Button size="small" variant="outlined" onClick={() => handleOpenRules("income")} sx={{ whiteSpace: "nowrap" }}>
                收入待找发票规则设置
              </Button>
              <Button size="small" variant="contained" disabled={actionsDisabled} onClick={() => setActiveDrawer("export")} sx={{ whiteSpace: "nowrap" }}>
                筛选内容导出
              </Button>
              <TextField
                size="small"
                placeholder="搜索流水"
                value={keyword}
                onChange={(event) => {
                  setKeyword(event.target.value);
                  setPage(1);
                }}
                inputProps={{ "aria-label": "搜索流水" }}
              />
              <Button size="small" variant="outlined" onClick={() => setRefreshToken((current) => current + 1)}>
                刷新
              </Button>
            </Stack>
          </Stack>
        </Box>
        <Box sx={{ height: 2 }}>{loading ? <LinearProgress aria-label="待找发票加载中" sx={{ height: 2 }} /> : null}</Box>
        <PendingInvoicesTable
          rows={rows}
          config={tableConfig}
          onSortChange={handleSortChange}
          onOpenRelation={handleOpenRelation}
          onOpenInvoicePicker={handleOpenInvoicePicker}
          onOpenManualInvoice={setDialogRow}
          onOpenObjectDetail={handleOpenDetail}
          onMarkIncomeStatus={handleMarkIncomeStatus}
          direction={direction}
          statusFilterControl={statusFilterControl}
          actionsDisabled={actionsDisabled}
        />
        <TablePagination
          component="div"
          count={total}
          page={Math.max(0, page - 1)}
          rowsPerPage={pageSize}
          rowsPerPageOptions={[25, 50, 100]}
          labelRowsPerPage="每页行数"
          labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count}`}
          onPageChange={(_event, nextPage) => setPage(nextPage + 1)}
          onRowsPerPageChange={(event) => {
            setPageSize(Number(event.target.value));
            setPage(1);
          }}
        />
      </Stack>
      <PendingInvoiceRulesDrawer
        open={activeDrawer === "rules"}
        loadRules={loadRules}
        saveRules={saveRules}
        refreshToken={rulesTagRefreshToken}
        onSaved={() => setRefreshToken((current) => current + 1)}
        onClose={closeDrawer}
      />
      <PendingInvoiceRelationDrawer
        open={activeDrawer === "relation"}
        transactionId={relationTarget?.transactionId ?? null}
        loadDetail={loadRelation}
        onOpenInvoicePicker={handleOpenInvoicePickerById}
        onClose={closeDrawer}
      />
      <PendingInvoiceInvoicePickerDrawer
        open={activeDrawer === "invoicePicker"}
        transactionId={relationTarget?.transactionId ?? null}
        loadCandidates={loadCandidates}
        previewAttach={(transactionId, invoiceId, requestId) => previewAttachExistingInvoice({ transactionId, invoiceId, requestId })}
        confirmAttach={(transactionId, invoiceId, previewId, requestId) => confirmAttachExistingInvoice({ transactionId, invoiceId, previewId, requestId })}
        onConfirmed={handleAttachConfirmed}
        onClose={closeDrawer}
      />
      <PendingInvoiceDetailDrawer
        open={activeDrawer === "detail"}
        target={detailTarget}
        loadDetail={loadObjectDetail}
        onClose={closeDrawer}
      />
      <PendingInvoiceExportDrawer
        open={activeDrawer === "export"}
        loadPreview={loadExportPreview}
        downloadExport={handleDownloadExport}
        onClose={closeDrawer}
      />
      <ManualInvoiceDialog
        open={dialogRow !== null}
        row={dialogRow}
        direction={direction}
        onClose={() => setDialogRow(null)}
        onConfirmed={handleManualConfirmed}
      />
    </Box>
  );
}
