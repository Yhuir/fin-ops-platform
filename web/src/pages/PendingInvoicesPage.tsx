import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TablePagination from "@mui/material/TablePagination";
import TextField from "@mui/material/TextField";
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
} from "../features/pendingInvoices/types";

const DEFAULT_PAGE_SIZE = 50;
const TAG_SYNC_EVENT = "finops:bank-transaction-tags-updated";
const TAG_VERSION_STORAGE_KEY = "finops.bankTransactionTags.version";

type ActiveDrawer = "rules" | "relation" | "invoicePicker" | "detail" | "export" | null;
type RelationTarget = { transactionId: string } | null;

const FILTER_LABELS: Record<PendingInvoiceFilter, string> = {
  all: "全部",
  requires_invoice: "需要开票",
  bank_statement_as_invoice: "流水代替发票",
  no_invoice_required: "无需开票",
};

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
  const direction: PendingInvoiceDirection = "expense";
  const [filter, setFilter] = useState<PendingInvoiceFilter>("all");
  const [rows, setRows] = useState<PendingInvoiceRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [keyword, setKeyword] = useState("");
  const [sortField, setSortField] = useState<PendingInvoiceSortField>("trade_date");
  const [sortDirection, setSortDirection] = useState<PendingInvoiceSortDirection>("desc");
  const [expandedCellIds, setExpandedCellIds] = useState<Set<string>>(() => new Set());
  const [activeDrawer, setActiveDrawer] = useState<ActiveDrawer>(null);
  const [detailTarget, setDetailTarget] = useState<PendingInvoiceObjectDetailTarget | null>(null);
  const [relationTarget, setRelationTarget] = useState<RelationTarget>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [readModelStatus, setReadModelStatus] = useState("");
  const [filterAnchorEl, setFilterAnchorEl] = useState<HTMLElement | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
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
        setReadModelStatus(payload.readModelStatus);
        const version = payload.tagDictionary?.version;
        if (typeof version === "number" && version > 0) {
          tagVersionRef.current = version;
          persistTagVersion(version);
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

  const filterOptions = useMemo<PendingInvoiceFilter[]>(() => [
    "all",
    "requires_invoice",
    "bank_statement_as_invoice",
    "no_invoice_required",
  ], []);

  const tableConfig = useMemo(() => ({
    sortField,
    sortDirection,
    expandedCellIds,
  }), [expandedCellIds, sortDirection, sortField]);

  const handleSortChange = useCallback((field: PendingInvoiceSortField) => {
    setPage(1);
    if (field === sortField) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortField(field);
    setSortDirection("asc");
  }, [sortField]);

  const handleToggleCellExpand = useCallback((cellId: string) => {
    setExpandedCellIds((current) => {
      const next = new Set(current);
      if (next.has(cellId)) {
        next.delete(cellId);
      } else {
        next.add(cellId);
      }
      return next;
    });
  }, []);

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

  const loadRelation = useCallback((transactionId: string) => fetchPendingInvoiceRelationDetail(transactionId), []);
  const loadObjectDetail = useCallback((target: PendingInvoiceObjectDetailTarget) => fetchPendingInvoiceObjectDetail(target), []);
  const loadRules = useCallback(() => fetchPendingInvoiceRules(), []);
  const saveRules = useCallback((payload: Parameters<typeof savePendingInvoiceRules>[0]) => savePendingInvoiceRules(payload), []);
  const loadCandidates = useCallback((transactionId: string) => fetchPendingInvoiceCandidates({
    transactionId,
    sortField: "amount_difference_abs",
    sortDirection: "asc",
    page: 1,
    pageSize: 20,
  }), []);
  const loadExportPreview = useCallback(() => fetchPendingInvoiceExportPreview(query), [query]);
  const handleDownloadExport = useCallback(() => downloadPendingInvoiceExport(query), [query]);

  return (
    <Box data-testid="pending-invoices-page" sx={{ px: { xs: 2, md: 3 }, py: 2 }}>
      <Stack spacing={2}>
        <Paper elevation={0} sx={{ p: 2, border: "1px solid", borderColor: "divider" }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ xs: "stretch", md: "center" }} justifyContent="space-between">
            <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
              <Typography variant="h6" fontWeight={900}>待找发票</Typography>
              <Button
                variant="outlined"
                size="small"
                aria-haspopup="menu"
                onClick={(event) => setFilterAnchorEl(event.currentTarget)}
              >
                {FILTER_LABELS[filter]}
              </Button>
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
                    {FILTER_LABELS[option]}
                  </MenuItem>
                ))}
              </Menu>
            </Stack>
            <Stack direction="row" spacing={1} alignItems="center">
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
        </Paper>

        {error ? <Typography color="error">{error}</Typography> : null}
        {loading ? <Typography color="text.secondary">正在加载待找发票。</Typography> : null}
        {readModelStatus === "refreshing" ? <Typography color="text.secondary">待找发票数据正在刷新。</Typography> : null}
        <PendingInvoicesTable
          rows={rows}
          config={tableConfig}
          onSortChange={handleSortChange}
          onOpenRelation={handleOpenRelation}
          onOpenInvoicePicker={handleOpenInvoicePicker}
          onOpenManualInvoice={setDialogRow}
          onOpenObjectDetail={handleOpenDetail}
          onOpenRules={() => setActiveDrawer("rules")}
          onOpenExport={() => setActiveDrawer("export")}
          onToggleCellExpand={handleToggleCellExpand}
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
