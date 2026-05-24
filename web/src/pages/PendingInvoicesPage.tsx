import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";

import ManualInvoiceDialog from "../components/pendingInvoices/ManualInvoiceDialog";
import PendingInvoicesTable from "../components/pendingInvoices/PendingInvoicesTable";
import {
  fetchPendingInvoiceRows,
} from "../features/pendingInvoices/api";
import { FINANCE_DOMAIN_EVENTS, emitFinanceDomainEvent } from "../features/domainEvents";
import type {
  ManualPendingInvoiceResult,
  PendingInvoiceDirection,
  PendingInvoiceFilter,
  PendingInvoiceRow,
} from "../features/pendingInvoices/types";

const DEFAULT_PAGE_SIZE = 50;
const TAG_SYNC_EVENT = "finops:bank-transaction-tags-updated";
const TAG_VERSION_STORAGE_KEY = "finops.bankTransactionTags.version";

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
  const [direction, setDirection] = useState<PendingInvoiceDirection>("expense");
  const [filter, setFilter] = useState<PendingInvoiceFilter>("all");
  const [rows, setRows] = useState<PendingInvoiceRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterAnchorEl, setFilterAnchorEl] = useState<HTMLElement | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [dialogRow, setDialogRow] = useState<PendingInvoiceRow | null>(null);
  const tagVersionRef = useRef<number | null>(readPersistedTagVersion());

  const activeFilter = direction === "expense" ? filter : "all";
  const filterOpen = Boolean(filterAnchorEl);

  const loadRows = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    fetchPendingInvoiceRows({
      direction,
      filter: activeFilter,
      keyword,
      page,
      pageSize,
      signal,
    })
      .then((payload) => {
        setRows(payload.rows);
        setTotal(payload.pagination.total);
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
  }, [activeFilter, direction, keyword, page, pageSize]);

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

  function handleDirectionChange(_event: MouseEvent<HTMLElement>, value: PendingInvoiceDirection | null) {
    if (!value) {
      return;
    }
    setDirection(value);
    setPage(1);
    if (value === "income") {
      setFilter("all");
    }
  }

  const filterOptions = useMemo<PendingInvoiceFilter[]>(() => [
    "all",
    "requires_invoice",
    "bank_statement_as_invoice",
    "no_invoice_required",
  ], []);

  function handleConfirmed(result: ManualPendingInvoiceResult) {
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

  return (
    <Box data-testid="pending-invoices-page" sx={{ px: { xs: 2, md: 3 }, py: 2 }}>
      <Stack spacing={2}>
        <Paper elevation={0} sx={{ p: 2, border: "1px solid", borderColor: "divider" }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ xs: "stretch", md: "center" }} justifyContent="space-between">
            <Stack direction="row" spacing={1} alignItems="center">
              <ToggleButtonGroup exclusive size="small" value={direction} onChange={handleDirectionChange} aria-label="流水方向">
                <ToggleButton value="expense">支出流水</ToggleButton>
                <ToggleButton value="income">收入流水</ToggleButton>
              </ToggleButtonGroup>
              {direction === "expense" ? (
                <>
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
                </>
              ) : null}
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
        <PendingInvoicesTable
          direction={direction}
          rows={rows}
          page={page}
          pageSize={pageSize}
          total={total}
          onPageChange={setPage}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(nextPageSize);
            setPage(1);
          }}
          onCreateInvoice={setDialogRow}
        />
      </Stack>
      <ManualInvoiceDialog
        open={dialogRow !== null}
        row={dialogRow}
        direction={direction}
        onClose={() => setDialogRow(null)}
        onConfirmed={handleConfirmed}
      />
    </Box>
  );
}
