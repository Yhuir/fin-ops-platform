import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type FocusEvent, type FormEvent, type MouseEvent } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Popover from "@mui/material/Popover";
import Paper from "@mui/material/Paper";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import {
  DataGrid,
  GridToolbarColumnsButton,
  GridToolbarContainer,
  GridToolbarExport,
  GridToolbarFilterButton,
  type GridColDef,
  type GridLocaleText,
  type GridPaginationModel,
} from "@mui/x-data-grid";
import { zhCN } from "@mui/x-data-grid/locales";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";

import StatePanel from "../components/common/StatePanel";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import BankCategoryTag from "../features/bankDetails/BankCategoryTag";
import BankCategoryPicker from "../features/bankDetails/BankCategoryPicker";
import { fetchBankDetailAccounts, fetchBankDetailTransactions, saveBankTransactionCategories } from "../features/bankDetails/api";
import {
  FINANCE_DOMAIN_EVENTS,
  emitFinanceDomainEvent,
  eventAffectedMonths,
  subscribeFinanceDomainEvent,
} from "../features/domainEvents";
import type {
  BankDateFilter,
  BankDetailAccount,
  BankDetailTransaction,
  BankTransactionCategoryCode,
  BankTransactionCategoryCounts,
} from "../features/bankDetails/types";
import type { BankTransactionTagDefinition } from "../features/pendingInvoices/types";

const TODAY = new Date(2026, 4, 2);
const DEFAULT_PAGE_SIZE = 100;
const ALL_ACCOUNTS_KEY = "__all_bank_accounts__";
const TAG_SYNC_EVENT = "finops:bank-transaction-tags-updated";
const TAG_VERSION_STORAGE_KEY = "finops.bankTransactionTags.version";
const FEATURED_CATEGORY_CODES: BankTransactionCategoryCode[] = [
  "fee",
  "salary",
  "internal_transfer",
];
const EMPTY_CATEGORY_COUNTS: BankTransactionCategoryCounts = { uncategorized: 0 };

const DATA_GRID_LOCALE_TEXT: Partial<GridLocaleText> = {
  ...zhCN.components.MuiDataGrid.defaultProps.localeText,
  toolbarQuickFilterPlaceholder: "搜索流水",
  filterPanelOperator: "条件",
  filterPanelInputLabel: "值",
  filterPanelInputPlaceholder: "输入筛选值",
  paginationRowsPerPage: "每页行数",
  paginationDisplayedRows: ({ from, to, count }) => `${from}-${to} / ${count === -1 ? `超过 ${to}` : count}`,
};

type SavedCategoryState = {
  categoryCode: BankTransactionCategoryCode | null;
  categoryLabel: string | null;
  categoryPath: string[];
  categorySource: string;
  categoryVersion: number | null;
  effectiveCategoryCode: BankTransactionCategoryCode | null;
  effectiveCategoryLabel: string | null;
  effectiveCategoryPath: string[];
  effectiveCategorySource: string;
};

type PendingNavigation = {
  run: () => void;
};

type CategorySummaryItem = {
  code: BankTransactionCategoryCode;
  label: string;
};

type BankDetailsGridToolbarProps = {
  effectiveCategoryCounts: BankTransactionCategoryCounts;
  dirtyCount: number;
  visibleCategorySummary: CategorySummaryItem[];
  searchKeyword: string;
  onSearchKeywordChange: (value: string) => void;
};

declare module "@mui/x-data-grid" {
  interface ToolbarPropsOverrides {
    effectiveCategoryCounts?: BankTransactionCategoryCounts;
    dirtyCount?: number;
    visibleCategorySummary?: CategorySummaryItem[];
    searchKeyword?: string;
    onSearchKeywordChange?: (value: string) => void;
  }
}

function formatDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function daysAgo(days: number) {
  const date = new Date(TODAY);
  date.setDate(date.getDate() - days);
  return date;
}

function endOfMonth(year: number, monthIndex: number) {
  return new Date(year, monthIndex + 1, 0);
}

function createDateFilter(preset: BankDateFilter["preset"], monthValue = "2026-05"): BankDateFilter {
  if (preset === "previous_month") {
    return { preset, dateFrom: "2026-04-01", dateTo: "2026-04-30" };
  }
  if (preset === "last_7_days") {
    return { preset, dateFrom: formatDate(daysAgo(6)), dateTo: formatDate(TODAY) };
  }
  if (preset === "last_30_days") {
    return { preset, dateFrom: formatDate(daysAgo(29)), dateTo: formatDate(TODAY) };
  }
  if (preset === "current_year") {
    return { preset, dateFrom: "2026-01-01", dateTo: "2026-12-31" };
  }
  if (preset === "month") {
    const [year, month] = monthValue.split("-").map(Number);
    return {
      preset,
      dateFrom: `${year}-${String(month).padStart(2, "0")}-01`,
      dateTo: formatDate(endOfMonth(year, month - 1)),
    };
  }
  return { preset: "current_month", dateFrom: "2026-05-01", dateTo: "2026-05-31" };
}

function displayBalance(value: string | null) {
  return value && value.trim() ? formatMoney(value) : "余额为空";
}

function formatMoney(value: string | null) {
  if (!value || !value.trim()) {
    return "";
  }
  const parsed = Number(value.replace(/,/g, ""));
  if (!Number.isFinite(parsed)) {
    return value;
  }
  return parsed.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function dateValue(value: string) {
  return value ? dayjs(value) : null;
}

function formatPickerDate(value: Dayjs | null) {
  return value?.isValid() ? value.format("YYYY-MM-DD") : null;
}

function relationTagTone(tag: string) {
  return tag.startsWith("有") ? "has" : "none";
}

function monthIndex(value: string) {
  if (!/^\d{4}-\d{2}$/.test(value)) {
    return null;
  }
  const [year, month] = value.split("-").map(Number);
  return year * 12 + month;
}

function eventTagVersion(event: Event) {
  if (!(event instanceof CustomEvent) || !event.detail || typeof event.detail !== "object") {
    return null;
  }
  const version = Number((event.detail as { version?: unknown }).version);
  return Number.isFinite(version) ? version : null;
}

function readPersistedTagVersion() {
  try {
    const version = Number(window.localStorage.getItem(TAG_VERSION_STORAGE_KEY));
    return Number.isFinite(version) && version > 0 ? version : null;
  } catch {
    return null;
  }
}

function persistTagVersion(version: number | null | undefined) {
  if (typeof version !== "number" || !Number.isFinite(version) || version <= 0) {
    return;
  }
  try {
    window.localStorage.setItem(TAG_VERSION_STORAGE_KEY, String(version));
  } catch {
    // localStorage may be unavailable in restrictive embedded shells.
  }
}

function affectedMonthsHitDateFilter(affectedMonths: string[] | null, dateFilter: BankDateFilter) {
  if (!affectedMonths || affectedMonths.length === 0 || affectedMonths.includes("all")) {
    return true;
  }
  const startMonth = monthIndex(dateFilter.dateFrom.slice(0, 7));
  const endMonth = monthIndex(dateFilter.dateTo.slice(0, 7));
  if (startMonth === null || endMonth === null) {
    return true;
  }
  return affectedMonths.some((month) => {
    const index = monthIndex(month);
    return index === null || (index >= startMonth && index <= endMonth);
  });
}

function isAbortLikeError(caught: unknown) {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return true;
  }
  if (caught instanceof Error) {
    return caught.name === "AbortError" || /aborted|abort/i.test(caught.message);
  }
  return false;
}

function isBankDateFilter(value: unknown): value is BankDateFilter {
  if (!value || typeof value !== "object") {
    return false;
  }
  const filter = value as Record<string, unknown>;
  return (
    typeof filter.preset === "string"
    && typeof filter.dateFrom === "string"
    && typeof filter.dateTo === "string"
  );
}

function EmptyTransactionOverlay() {
  return (
    <Stack alignItems="center" justifyContent="center" sx={{ height: "100%", px: 2, textAlign: "center" }}>
      <Typography color="text.secondary">当前时间范围内没有流水。</Typography>
    </Stack>
  );
}

function BankDetailsGridToolbar({
  effectiveCategoryCounts = EMPTY_CATEGORY_COUNTS,
  dirtyCount = 0,
  visibleCategorySummary = [],
  searchKeyword = "",
  onSearchKeywordChange = () => undefined,
}: Partial<BankDetailsGridToolbarProps>) {
  return (
    <GridToolbarContainer className="bank-grid-toolbar">
      <Stack className="bank-grid-toolbar-content" spacing={1}>
        <Stack className="bank-grid-category-summary" direction="row" gap={0.4}>
          <BankCategoryTag categoryCode={null} compact label="未分类" count={effectiveCategoryCounts.uncategorized} />
          <Chip className="bank-dirty-count-chip bank-chip-auto-size" label={`未保存 ${dirtyCount}`} size="small" color={dirtyCount > 0 ? "warning" : "default"} variant="outlined" />
          {visibleCategorySummary.map((option) => (
            <BankCategoryTag
              key={option.code}
              categoryCode={option.code}
              compact
              label={option.label}
              count={effectiveCategoryCounts[option.code] ?? 0}
            />
          ))}
        </Stack>
        <Stack className="bank-grid-toolbar-actions" direction="row" spacing={0.5} alignItems="center">
          <GridToolbarColumnsButton />
          <GridToolbarFilterButton />
          <GridToolbarExport printOptions={{ disableToolbarButton: true }} />
          <TextField
            className="bank-grid-search-field"
            size="small"
            placeholder="搜索流水"
            value={searchKeyword}
            onChange={(event) => onSearchKeywordChange(event.target.value)}
            inputProps={{ "aria-label": "搜索流水" }}
          />
        </Stack>
      </Stack>
    </GridToolbarContainer>
  );
}

function hasOwnDraft(
  drafts: Partial<Record<string, BankTransactionCategoryCode | null>>,
  rowId: string,
) {
  return Object.prototype.hasOwnProperty.call(drafts, rowId);
}

function categoryCountKey(categoryCode: BankTransactionCategoryCode | null) {
  return categoryCode ?? "uncategorized";
}

function baseCategoryCodeForCounts(savedCategory: SavedCategoryState | undefined) {
  if (!savedCategory) {
    return null;
  }
  return savedCategory.categorySource === "manual"
    ? savedCategory.categoryCode
    : savedCategory.effectiveCategoryCode;
}

function applyDirtyCategoryCounts(
  counts: BankTransactionCategoryCounts,
  savedCategoryByRowId: Record<string, SavedCategoryState>,
  draftCategoryByRowId: Partial<Record<string, BankTransactionCategoryCode | null>>,
): BankTransactionCategoryCounts {
  const next = { ...counts };
  Object.entries(draftCategoryByRowId).forEach(([rowId, draftCategoryCode]) => {
    const savedCategoryCode = baseCategoryCodeForCounts(savedCategoryByRowId[rowId]);
    if (savedCategoryCode === draftCategoryCode) {
      return;
    }
    const savedKey = categoryCountKey(savedCategoryCode);
    const draftKey = categoryCountKey(draftCategoryCode ?? null);
    next[savedKey] = Math.max(0, (next[savedKey] ?? 0) - 1);
    next[draftKey] = (next[draftKey] ?? 0) + 1;
  });
  return next;
}

function categoryLabelForCode(
  categoryCode: BankTransactionCategoryCode | null,
  categoryOptions: BankTransactionTagDefinition[],
  fallback?: string | null,
) {
  if (!categoryCode) {
    return null;
  }
  return fallback?.trim() || categoryOptions.find((option) => option.code === categoryCode)?.label || categoryCode;
}

function counterpartyNameDensity(name: string) {
  const length = name.trim().length;
  if (length >= 28) {
    return "dense";
  }
  if (length >= 20) {
    return "compact";
  }
  return "regular";
}

const baseTransactionColumns: GridColDef<BankDetailTransaction>[] = [
  {
    field: "counterpartyName",
    headerName: "对方户名",
    width: 260,
    minWidth: 230,
    renderCell: ({ row }) => (
      <Stack className="bank-counterparty-cell" justifyContent="center" spacing={0.5} sx={{ minWidth: 0, width: "100%" }}>
        <Typography
          className={`bank-counterparty-name ${counterpartyNameDensity(row.counterpartyName)}`}
          component="span"
          variant="body2"
          fontWeight={750}
        >
          {row.counterpartyName}
        </Typography>
        <Stack className="bank-relation-chip-row" direction="row" spacing={0.5} sx={{ minWidth: 0, maxWidth: "100%" }}>
          <Chip className="bank-trade-time-chip bank-trade-time-chip-full bank-chip-auto-size" label={row.tradeTime} size="small" variant="outlined" />
          {row.relationTags.map((tag) => (
            <Chip
              key={`${row.id}-${tag}`}
              className={`bank-relation-tag bank-relation-tag-${relationTagTone(tag)} bank-chip-auto-size`}
              label={tag}
              size="small"
              variant="outlined"
            />
          ))}
        </Stack>
      </Stack>
    ),
  },
  {
    field: "amount",
    headerName: "金额",
    width: 148,
    minWidth: 140,
    align: "right",
    headerAlign: "right",
    renderCell: ({ row }) => (
      <Stack className="bank-amount-cell" alignItems="stretch" justifyContent="center" spacing={0.5} sx={{ width: "100%" }}>
        <Stack className="bank-amount-line" direction="row" alignItems="center" spacing={0.75}>
          <Chip
            className={`direction-tag bank-direction-tag-centered bank-chip-auto-size ${row.direction}`}
            label={row.directionLabel}
            size="small"
            variant="filled"
          />
          <Typography component="span" variant="body2" fontWeight={800} sx={{ fontVariantNumeric: "tabular-nums" }}>
            {formatMoney(row.amount)}
          </Typography>
        </Stack>
        <Chip className="bank-source-chip bank-chip-auto-size" label={`${row.bankName} ${row.accountLast4}`} size="small" variant="outlined" />
      </Stack>
    ),
  },
  {
    field: "balance",
    headerName: "余额",
    width: 112,
    minWidth: 96,
    align: "right",
    headerAlign: "right",
    valueFormatter: (value) => formatMoney(value as string | null),
  },
  {
    field: "summaryPurpose",
    headerName: "摘要/用途",
    minWidth: 210,
    flex: 1,
    valueGetter: (_value, row) => [row.summary, row.purpose].map((value) => value.trim()).filter(Boolean).join(" "),
    renderCell: ({ row }) => (
      <Stack className="bank-summary-purpose-cell" justifyContent="center" spacing={0.5} sx={{ minWidth: 0, width: "100%" }}>
        {row.summary.trim() ? (
          <Typography component="span" variant="body2">
            {row.summary}
          </Typography>
        ) : null}
        {row.purpose.trim() ? (
          <Typography component="span" variant="caption" color="text.secondary">
            {row.purpose}
          </Typography>
        ) : null}
      </Stack>
    ),
  },
  {
    field: "actions",
    headerName: "操作",
    width: 68,
    minWidth: 64,
    sortable: false,
    filterable: false,
    align: "center",
    headerAlign: "center",
    renderCell: () => (
      <Button size="small" variant="text">详情</Button>
    ),
  },
];

export default function BankDetailsPage() {
  const selectedAccountSession = usePageSessionState<string | null>({
    pageKey: "bank-details",
    stateKey: "selectedAccountKey",
    version: 2,
    initialValue: ALL_ACCOUNTS_KEY,
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: (value): value is string | null => value === null || typeof value === "string",
  });
  const dateFilterSession = usePageSessionState<BankDateFilter>({
    pageKey: "bank-details",
    stateKey: "dateFilter",
    version: 2,
    initialValue: createDateFilter("current_year"),
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: isBankDateFilter,
  });
  const monthValueSession = usePageSessionState<string>({
    pageKey: "bank-details",
    stateKey: "monthValue",
    version: 1,
    initialValue: "2026-05",
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: (value): value is string => typeof value === "string" && /^\d{4}-\d{2}$/.test(value),
  });
  const [accountsData, setAccountsData] = useState<{
    accounts: BankDetailAccount[];
    totalBalance: string | null;
    missingBalanceAccountCount: number;
  }>({ accounts: [], totalBalance: null, missingBalanceAccountCount: 0 });
  const selectedAccountKey = selectedAccountSession.value;
  const setSelectedAccountKey = selectedAccountSession.setValue;
  const dateFilter = dateFilterSession.value;
  const setDateFilter = dateFilterSession.setValue;
  const monthValue = monthValueSession.value;
  const setMonthValue = monthValueSession.setValue;
  const [rows, setRows] = useState<BankDetailTransaction[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [paginationModel, setPaginationModel] = useState<GridPaginationModel>({
    page: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  });
  const [searchInput, setSearchInput] = useState("");
  const [searchKeyword, setSearchKeyword] = useState("");
  const [readModelStatus, setReadModelStatus] = useState<"fresh" | "refreshing">("fresh");
  const [loading, setLoading] = useState(true);
  const [rowLoading, setRowLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [categoryCounts, setCategoryCounts] = useState<BankTransactionCategoryCounts>(EMPTY_CATEGORY_COUNTS);
  const [categoryOptions, setCategoryOptions] = useState<BankTransactionTagDefinition[]>([]);
  const [savedCategoryByRowId, setSavedCategoryByRowId] = useState<Record<string, SavedCategoryState>>({});
  const [draftCategoryByRowId, setDraftCategoryByRowId] = useState<Partial<Record<string, BankTransactionCategoryCode | null>>>({});
  const draftCategoryByRowIdRef = useRef(draftCategoryByRowId);
  const tagVersionRef = useRef<number | null>(readPersistedTagVersion());
  const [savingCategories, setSavingCategories] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<PendingNavigation | null>(null);
  const [snackbar, setSnackbar] = useState<{ severity: "success" | "error"; message: string } | null>(null);
  const [dateFilterAnchorEl, setDateFilterAnchorEl] = useState<HTMLElement | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    draftCategoryByRowIdRef.current = draftCategoryByRowId;
  }, [draftCategoryByRowId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchBankDetailAccounts({
      dateFrom: dateFilter.dateFrom,
      dateTo: dateFilter.dateTo,
      signal: controller.signal,
    })
      .then((payload) => {
        setAccountsData({
          accounts: payload.accounts,
          totalBalance: payload.totalBalance,
          missingBalanceAccountCount: payload.missingBalanceAccountCount,
        });
        if (payload.readModelStatus === "refreshing") {
          setReadModelStatus("refreshing");
        }
        setSelectedAccountKey((current) => (
          current && (current === ALL_ACCOUNTS_KEY || payload.accounts.some((account) => account.accountKey === current))
            ? current
            : ALL_ACCOUNTS_KEY
        ));
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setError(caught instanceof Error ? caught.message : "银行明细加载失败。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [dateFilter.dateFrom, dateFilter.dateTo, refreshToken, setSelectedAccountKey]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearchKeyword(searchInput.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    if (!selectedAccountKey) {
      setRows([]);
      setRowCount(0);
      setCategoryCounts(EMPTY_CATEGORY_COUNTS);
      return;
    }
    const controller = new AbortController();
    setRowLoading(true);
    setError(null);
    const accountKey = selectedAccountKey === ALL_ACCOUNTS_KEY ? null : selectedAccountKey;
    fetchBankDetailTransactions({
      accountKey,
      dateFrom: dateFilter.dateFrom,
      dateTo: dateFilter.dateTo,
      keyword: searchKeyword,
      page: paginationModel.page + 1,
      pageSize: paginationModel.pageSize,
      signal: controller.signal,
    })
      .then((payload) => {
        setRows(payload.rows);
        setRowCount(payload.pagination.total);
        setCategoryCounts(payload.categoryCounts);
        setReadModelStatus(payload.readModelStatus === "refreshing" ? "refreshing" : "fresh");
        if (payload.tagDictionary?.tags) {
          setCategoryOptions(payload.tagDictionary.tags.filter((tag) => tag.status === "active"));
        }
        if (typeof payload.tagDictionary?.version === "number" && payload.tagDictionary.version > 0) {
          tagVersionRef.current = payload.tagDictionary.version;
          persistTagVersion(payload.tagDictionary.version);
        }
        setSavedCategoryByRowId((current) => {
          const next = { ...current };
          payload.rows.forEach((row) => {
            if (!hasOwnDraft(draftCategoryByRowIdRef.current, row.id)) {
              next[row.id] = {
                categoryCode: row.categoryCode,
                categoryLabel: row.categoryLabel,
                categoryPath: row.categoryPath,
                categorySource: row.categorySource,
                categoryVersion: row.categoryVersion,
                effectiveCategoryCode: row.effectiveCategoryCode,
                effectiveCategoryLabel: row.effectiveCategoryLabel,
                effectiveCategoryPath: row.effectiveCategoryPath,
                effectiveCategorySource: row.effectiveCategorySource,
              };
            }
          });
          return next;
        });
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setError(caught instanceof Error ? caught.message : "银行流水加载失败。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setRowLoading(false);
        }
      });
    return () => controller.abort();
  }, [dateFilter.dateFrom, dateFilter.dateTo, paginationModel.page, paginationModel.pageSize, refreshToken, searchKeyword, selectedAccountKey]);

  useEffect(() => {
    const handleWorkbenchRelationUpdated = (event: Event) => {
      const affectedMonths = eventAffectedMonths(event);
      if (!affectedMonthsHitDateFilter(affectedMonths, dateFilter)) {
        return;
      }
      setRefreshToken((current) => current + 1);
    };
    return subscribeFinanceDomainEvent(
      FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated,
      handleWorkbenchRelationUpdated,
    );
  }, [dateFilter]);

  useEffect(() => {
    const handleTagUpdate = (event: Event) => {
      const version = eventTagVersion(event);
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

  const dirtyEntries = useMemo(
    () => Object.entries(draftCategoryByRowId).filter((entry): entry is [string, BankTransactionCategoryCode | null] => entry[1] !== undefined),
    [draftCategoryByRowId],
  );
  const dirtyCount = dirtyEntries.length;
  const effectiveCategoryCounts = useMemo(
    () => applyDirtyCategoryCounts(categoryCounts, savedCategoryByRowId, draftCategoryByRowId),
    [categoryCounts, draftCategoryByRowId, savedCategoryByRowId],
  );
  const visibleCategorySummary = useMemo<CategorySummaryItem[]>(() => {
    const labelByCode = new Map(categoryOptions.map((option) => [option.code, option.label]));
    const featured = FEATURED_CATEGORY_CODES.map((code) => ({
      code,
      label: labelByCode.get(code) ?? code,
    }));
    const active = categoryOptions
      .filter((option) => (
        !FEATURED_CATEGORY_CODES.includes(option.code)
        && (effectiveCategoryCounts[option.code] ?? 0) > 0
      ))
      .map((option) => ({
        code: option.code,
        label: option.label,
      }));
    return [...featured, ...active];
  }, [categoryOptions, effectiveCategoryCounts]);

  useEffect(() => {
    if (dirtyCount === 0) {
      return undefined;
    }
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [dirtyCount]);

  const selectedAccount = useMemo(
    () => accountsData.accounts.find((account) => account.accountKey === selectedAccountKey) ?? null,
    [accountsData.accounts, selectedAccountKey],
  );
  const isAllAccountsSelected = selectedAccountKey === ALL_ACCOUNTS_KEY;
  const totalTransactionCount = useMemo(
    () => accountsData.accounts.reduce((sum, account) => sum + account.transactionCount, 0),
    [accountsData.accounts],
  );
  const currentViewTitle = isAllAccountsSelected ? "全部流水" : selectedAccount?.displayName ?? "账户流水";
  const dateFilterOpen = Boolean(dateFilterAnchorEl);

  const totalPages = Math.max(1, Math.ceil(rowCount / paginationModel.pageSize));

  const resetToFirstPage = () => {
    setPaginationModel((current) => (
      current.page === 0 ? current : { ...current, page: 0 }
    ));
  };

  const guardDirtyNavigation = (run: () => void) => {
    if (dirtyCount > 0) {
      setPendingNavigation({ run });
      return;
    }
    run();
  };

  const applyDateFilter = (nextFilter: BankDateFilter | ((current: BankDateFilter) => BankDateFilter)) => {
    guardDirtyNavigation(() => {
      resetToFirstPage();
      setDateFilter(nextFilter);
    });
  };

  const handleAccountSelect = (accountKey: string) => {
    if (accountKey === selectedAccountKey) {
      return;
    }
    guardDirtyNavigation(() => {
      resetToFirstPage();
      setSelectedAccountKey(accountKey);
    });
  };

  const handleSearchKeywordChange = (value: string) => {
    resetToFirstPage();
    setSearchInput(value);
  };

  const applyPreset = (preset: BankDateFilter["preset"]) => {
    applyDateFilter(createDateFilter(preset, monthValue));
  };

  const handlePresetChange = (_event: MouseEvent<HTMLElement>, preset: BankDateFilter["preset"] | null) => {
    if (preset) {
      applyPreset(preset);
    }
  };

  const openDateFilterPopover = (event: MouseEvent<HTMLElement>) => {
    setDateFilterAnchorEl(event.currentTarget);
  };

  const closeDateFilterPopover = () => {
    setDateFilterAnchorEl(null);
  };

  const handleMonthChange = (value: string) => {
    if (!value) {
      setMonthValue(value);
      return;
    }
    guardDirtyNavigation(() => {
      setMonthValue(value);
      resetToFirstPage();
      setDateFilter(createDateFilter("month", value));
    });
  };

  const handleCustomDateChange = (key: "dateFrom" | "dateTo", value: string) => {
    applyDateFilter((current) => ({
      preset: "custom",
      dateFrom: key === "dateFrom" ? value : current.dateFrom,
      dateTo: key === "dateTo" ? value : current.dateTo,
    }));
  };

  const handleCustomDateTextChange = (key: "dateFrom" | "dateTo", value: string) => {
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      handleCustomDateChange(key, value);
    }
  };

  const displayCategoryForRow = useCallback((row: BankDetailTransaction) => {
    if (hasOwnDraft(draftCategoryByRowId, row.id)) {
      const categoryCode = draftCategoryByRowId[row.id] ?? null;
      return {
        categoryCode,
        categoryLabel: categoryLabelForCode(categoryCode, categoryOptions),
        categorySource: "draft",
      };
    }
    const savedCategory = savedCategoryByRowId[row.id];
    if (savedCategory?.categorySource === "manual") {
      return {
        categoryCode: savedCategory.categoryCode,
        categoryLabel: categoryLabelForCode(savedCategory.categoryCode, categoryOptions, savedCategory.categoryLabel),
        categorySource: savedCategory.categorySource,
      };
    }
    return {
      categoryCode: savedCategory?.effectiveCategoryCode ?? row.effectiveCategoryCode ?? null,
      categoryLabel: categoryLabelForCode(
        savedCategory?.effectiveCategoryCode ?? row.effectiveCategoryCode ?? null,
        categoryOptions,
        savedCategory?.effectiveCategoryLabel ?? row.effectiveCategoryLabel,
      ),
      categorySource: savedCategory?.effectiveCategorySource ?? row.effectiveCategorySource,
    };
  }, [categoryOptions, draftCategoryByRowId, savedCategoryByRowId]);

  const handleCategoryChange = useCallback((row: BankDetailTransaction, categoryCode: BankTransactionCategoryCode | null) => {
    const savedCategory = savedCategoryByRowId[row.id];
    const savedCategoryCode = savedCategory?.categorySource === "manual"
      ? savedCategory.categoryCode
      : savedCategory?.effectiveCategoryCode ?? row.effectiveCategoryCode ?? null;
    setDraftCategoryByRowId((current) => {
      const next = { ...current };
      if (categoryCode === savedCategoryCode) {
        delete next[row.id];
      } else {
        next[row.id] = categoryCode;
      }
      return next;
    });
  }, [savedCategoryByRowId]);

  const transactionColumns = useMemo<GridColDef<BankDetailTransaction>[]>(() => {
    const [counterpartyColumn, ...remainingColumns] = baseTransactionColumns;
    return [
      counterpartyColumn,
      {
        field: "categoryCode",
        headerName: "类型",
        width: 176,
        minWidth: 156,
        sortable: false,
        filterable: false,
        renderCell: ({ row }) => {
          const currentCategory = displayCategoryForRow(row);
          return (
            <BankCategoryPicker
              rowId={row.id}
              categoryCode={currentCategory.categoryCode}
              categoryLabel={currentCategory.categoryLabel}
              categorySource={currentCategory.categorySource}
              categoryOptions={categoryOptions}
              onChange={(nextCategoryCode) => handleCategoryChange(row, nextCategoryCode)}
            />
          );
        },
      },
      ...remainingColumns,
    ];
  }, [categoryOptions, displayCategoryForRow, handleCategoryChange]);

  const saveCategoryChanges = useCallback(async () => {
    if (dirtyEntries.length === 0) {
      return true;
    }
    setSavingCategories(true);
    try {
      const response = await saveBankTransactionCategories({
        updates: dirtyEntries.map(([transactionId, categoryCode]) => ({
          transactionId,
          categoryCode,
          expectedVersion: savedCategoryByRowId[transactionId]?.categoryVersion ?? null,
        })),
      });
      const nextCounts = effectiveCategoryCounts;
      setSavedCategoryByRowId((current) => {
        const next = { ...current };
        response.updatedCategories.forEach((category) => {
          next[category.transactionId] = {
            categoryCode: category.categoryCode,
            categoryLabel: category.categoryLabel,
            categoryPath: category.categoryPath,
            categorySource: "manual",
            categoryVersion: category.version,
            effectiveCategoryCode: category.categoryCode,
            effectiveCategoryLabel: category.categoryLabel,
            effectiveCategoryPath: category.categoryPath,
            effectiveCategorySource: category.categoryCode ? "manual" : "",
          };
        });
        return next;
      });
      setCategoryCounts(nextCounts);
      setDraftCategoryByRowId({});
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, {
        affectedMonths: response.affectedMonths,
        source: "bank_details_category_save",
      });
      setSnackbar({ severity: "success", message: "分类已保存" });
      return true;
    } catch (caught) {
      setSnackbar({
        severity: "error",
        message: caught instanceof Error ? caught.message : "分类保存失败",
      });
      return false;
    } finally {
      setSavingCategories(false);
    }
  }, [dirtyEntries, effectiveCategoryCounts, savedCategoryByRowId]);

  const continuePendingNavigation = () => {
    const navigation = pendingNavigation;
    setPendingNavigation(null);
    navigation?.run();
  };

  const handleSaveAndContinue = async () => {
    const saved = await saveCategoryChanges();
    if (saved) {
      continuePendingNavigation();
    }
  };

  const handleDiscardAndContinue = () => {
    setDraftCategoryByRowId({});
    continuePendingNavigation();
  };

  return (
    <Box className="bank-details-page" data-testid="bank-details-page">
      <Stack className="bank-details-workbench" spacing={1}>
        {error ? <StatePanel tone="error">{error}</StatePanel> : null}
        {loading ? <StatePanel tone="loading" compact>正在加载银行明细。</StatePanel> : null}
        {readModelStatus === "refreshing" && !error ? (
          <StatePanel tone="loading" compact>银行明细读模型正在刷新。</StatePanel>
        ) : null}
        {!loading && accountsData.accounts.length === 0 ? (
          <StatePanel tone="empty">暂无银行流水，请先在银行流水导入页面导入。</StatePanel>
        ) : null}

        <Box className="bank-details-layout">
          <Paper component="aside" className="bank-account-tree" elevation={0}>
            <Stack className="bank-account-summary" spacing={0.75}>
              <Typography color="text.secondary" variant="caption">总余额</Typography>
              <Typography className="bank-balance-value bank-total-balance" component="strong" variant="h6" fontWeight={850}>
                {displayBalance(accountsData.totalBalance)}
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={0.75}>
                <Chip className="bank-account-total-chip" label={`${accountsData.accounts.length} 个账户`} size="small" variant="outlined" />
                {accountsData.missingBalanceAccountCount > 0 ? (
                  <Chip label={`${accountsData.missingBalanceAccountCount} 个无余额`} size="small" color="warning" variant="outlined" />
                ) : null}
              </Stack>
            </Stack>
            <List aria-label="银行账户" dense disablePadding>
              <ListItem disablePadding>
                <ListItemButton
                  aria-current={isAllAccountsSelected ? "true" : undefined}
                  aria-label={`全部流水 ${totalTransactionCount} 条`}
                  className={`bank-account-node bank-account-all-node${isAllAccountsSelected ? " active" : ""}`}
                  component="button"
                  onClick={() => handleAccountSelect(ALL_ACCOUNTS_KEY)}
                >
                  <ListItemText
                    disableTypography
                    primary={(
                      <Box className="bank-account-title-row">
                        <Box className="bank-account-identity">
                          <Typography className="bank-account-name" component="span">全部</Typography>
                        </Box>
                        <Chip className="bank-account-count-chip bank-account-title-count" label={`${totalTransactionCount} 条`} size="small" variant="outlined" />
                      </Box>
                    )}
                    secondary={(
                      <Typography className="bank-account-inline-balance bank-account-secondary-balance bank-balance-value" component="span">
                        {displayBalance(accountsData.totalBalance)}
                      </Typography>
                    )}
                  />
                </ListItemButton>
              </ListItem>
              {accountsData.accounts.length > 0 ? (
                <Divider className="bank-account-divider" component="li" aria-hidden="true" />
              ) : null}
              {accountsData.accounts.map((account, index) => {
                const selected = account.accountKey === selectedAccountKey;
                const showDivider = index < accountsData.accounts.length - 1;
                return (
                  <Fragment key={account.accountKey}>
                    <ListItem disablePadding>
                      <ListItemButton
                        aria-current={selected ? "true" : undefined}
                        aria-label={`${account.displayName} 余额 ${displayBalance(account.latestBalance)} ${account.transactionCount} 条`}
                        className={`bank-account-node${selected ? " active" : ""}`}
                        component="button"
                        onClick={() => handleAccountSelect(account.accountKey)}
                      >
                        <ListItemText
                          disableTypography
                          primary={(
                            <Box className="bank-account-title-row">
                              <Box className="bank-account-identity">
                                <Typography className="bank-account-name" component="span">{account.bankName}</Typography>
                                <Typography className="bank-account-last4" component="span">{account.accountLast4}</Typography>
                              </Box>
                              <Chip className="bank-account-count-chip bank-account-title-count" label={`${account.transactionCount} 条`} size="small" variant="outlined" />
                            </Box>
                          )}
                          secondary={(
                            <Stack className="bank-account-metric-row" direction="row" alignItems="center" spacing={0.75} minWidth={0}>
                              {account.hasBalance ? (
                                <Typography className="bank-account-inline-balance bank-account-secondary-balance bank-balance-value" component="span">
                                  {displayBalance(account.latestBalance)}
                                </Typography>
                              ) : null}
                              {!account.hasBalance ? (
                                <Chip className="bank-account-empty-chip" label="余额为空" size="small" variant="outlined" />
                              ) : null}
                            </Stack>
                          )}
                        />
                      </ListItemButton>
                    </ListItem>
                    {showDivider ? <Divider className="bank-account-divider" component="li" aria-hidden="true" /> : null}
                  </Fragment>
                );
              })}
            </List>
          </Paper>

          <Paper component="section" className="bank-transaction-panel" elevation={0}>
            <Stack className="bank-transaction-toolbar" spacing={0.75}>
              <Stack className="bank-transaction-header" direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1}>
                <Stack className="bank-transaction-title-row" direction="row" alignItems="center" spacing={1}>
                  <Typography className="bank-transaction-title" component="h2" variant="subtitle1" fontWeight={850} noWrap>
                    {currentViewTitle}
                  </Typography>
                </Stack>

                <Stack className="bank-header-controls" direction="row" spacing={0.75} alignItems="center">
                  <Stack className="bank-date-toolbar" spacing={0.5} alignItems="flex-end">
                    <ToggleButtonGroup
                      aria-label="日期快捷筛选"
                      className="bank-date-presets"
                      exclusive
                      size="small"
                      value={dateFilter.preset === "custom" || dateFilter.preset === "month" ? null : dateFilter.preset}
                      onChange={handlePresetChange}
                    >
                      <ToggleButton value="current_month">本月</ToggleButton>
                      <ToggleButton value="previous_month">上月</ToggleButton>
                      <ToggleButton value="last_7_days">近7天</ToggleButton>
                      <ToggleButton value="last_30_days">近30天</ToggleButton>
                      <ToggleButton value="current_year">今年</ToggleButton>
                    </ToggleButtonGroup>
                    <Button
                      aria-describedby={dateFilterOpen ? "bank-date-filter-popover" : undefined}
                      className="bank-date-range-button"
                      size="small"
                      variant="outlined"
                      onClick={openDateFilterPopover}
                    >
                      {dateFilter.dateFrom} - {dateFilter.dateTo}
                    </Button>
                  </Stack>
                  <Stack className="bank-category-actions" direction="row" flexWrap="wrap" gap={0.75}>
                    <Button
                      loading={savingCategories}
                      disabled={dirtyCount === 0 || savingCategories}
                      size="small"
                      variant="contained"
                      onClick={() => void saveCategoryChanges()}
                    >
                      保存分类
                    </Button>
                    <Button
                      disabled={dirtyCount === 0 || savingCategories}
                      size="small"
                      variant="outlined"
                      onClick={() => setDraftCategoryByRowId({})}
                    >
                      撤销更改
                    </Button>
                  </Stack>
                </Stack>
              </Stack>
            </Stack>

            <Divider />

            <Box className="bank-transaction-grid bank-transaction-grid-readable">
              <DataGrid
                aria-label="交易流水"
                columns={transactionColumns}
                rows={rows}
                loading={rowLoading}
                disableRowSelectionOnClick
                rowHeight={80}
                columnHeaderHeight={44}
                columnBufferPx={360}
                paginationMode="server"
                rowCount={rowCount}
                paginationModel={paginationModel}
                onPaginationModelChange={setPaginationModel}
                pageSizeOptions={[25, 50, 100]}
                showToolbar
                getRowClassName={(params) => (params.indexRelativeToCurrentPage % 2 === 0 ? "bank-grid-row-even" : "bank-grid-row-odd")}
                localeText={DATA_GRID_LOCALE_TEXT}
                slots={{
                  toolbar: BankDetailsGridToolbar,
                  noRowsOverlay: EmptyTransactionOverlay,
                }}
                slotProps={{
                  toolbar: {
                    effectiveCategoryCounts,
                    dirtyCount,
                    visibleCategorySummary,
                    searchKeyword: searchInput,
                    onSearchKeywordChange: handleSearchKeywordChange,
                  },
                }}
                sx={{
                  height: "100%",
                  borderColor: "#c6c6c6",
                  borderRadius: 0,
                  "--DataGrid-overlayHeight": "320px",
                  "& .MuiDataGrid-columnHeaders": {
                    backgroundColor: "#f4f4f4",
                  },
                }}
              />
            </Box>
          </Paper>
        </Box>
      </Stack>
      <Popover
        id="bank-date-filter-popover"
        open={dateFilterOpen}
        anchorEl={dateFilterAnchorEl}
        onClose={closeDateFilterPopover}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { className: "bank-date-filter-popover" } }}
      >
        <Stack className="bank-date-filter" spacing={1.25}>
          <TextField
            label="年月"
            type="month"
            size="small"
            value={monthValue}
            onChange={(event) => handleMonthChange(event.target.value)}
            InputLabelProps={{ shrink: true }}
            inputProps={{ "aria-label": "年月筛选" }}
          />
          <DatePicker
            enableAccessibleFieldDOMStructure={false}
            label="开始"
            format="YYYY-MM-DD"
            value={dateValue(dateFilter.dateFrom)}
            onChange={(value) => {
              if (!value) {
                handleCustomDateChange("dateFrom", "");
                return;
              }
              const nextValue = formatPickerDate(value);
              if (nextValue) {
                handleCustomDateChange("dateFrom", nextValue);
              }
            }}
            slotProps={{
              textField: {
                size: "small",
                inputProps: {
                  "aria-label": "开始日期",
                  onInput: (event: FormEvent<HTMLInputElement>) => {
                    if (event.currentTarget instanceof HTMLInputElement) {
                      handleCustomDateTextChange("dateFrom", event.currentTarget.value);
                    }
                  },
                },
                onBlur: (event: FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => handleCustomDateTextChange("dateFrom", event.target.value),
              },
            }}
          />
          <DatePicker
            enableAccessibleFieldDOMStructure={false}
            label="结束"
            format="YYYY-MM-DD"
            value={dateValue(dateFilter.dateTo)}
            onChange={(value) => {
              if (!value) {
                handleCustomDateChange("dateTo", "");
                return;
              }
              const nextValue = formatPickerDate(value);
              if (nextValue) {
                handleCustomDateChange("dateTo", nextValue);
              }
            }}
            slotProps={{
              textField: {
                size: "small",
                inputProps: {
                  "aria-label": "结束日期",
                  onInput: (event: FormEvent<HTMLInputElement>) => {
                    if (event.currentTarget instanceof HTMLInputElement) {
                      handleCustomDateTextChange("dateTo", event.currentTarget.value);
                    }
                  },
                },
                onBlur: (event: FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => handleCustomDateTextChange("dateTo", event.target.value),
              },
            }}
          />
        </Stack>
      </Popover>
      <Dialog
        aria-labelledby="bank-category-dirty-dialog-title"
        open={pendingNavigation !== null}
        onClose={() => setPendingNavigation(null)}
      >
        <DialogTitle id="bank-category-dirty-dialog-title">有未保存的分类变动</DialogTitle>
        <DialogContent>
          <DialogContentText>当前有 {dirtyCount} 条未保存分类变动。</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingNavigation(null)}>取消</Button>
          <Button color="warning" onClick={handleDiscardAndContinue}>放弃变动</Button>
          <Button
            loading={savingCategories}
            disabled={savingCategories}
            variant="contained"
            onClick={() => void handleSaveAndContinue()}
          >
            保存并继续
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        autoHideDuration={4000}
        open={snackbar !== null}
        onClose={() => setSnackbar(null)}
      >
        {snackbar ? (
          <Alert
            severity={snackbar.severity}
            variant="filled"
            onClose={() => setSnackbar(null)}
            sx={{ width: "100%" }}
          >
            {snackbar.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </Box>
  );
}
