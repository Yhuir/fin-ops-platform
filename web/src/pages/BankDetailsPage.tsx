import { Fragment, useEffect, useMemo, useRef, useState, type FocusEvent, type FormEvent, type MouseEvent } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Popover from "@mui/material/Popover";
import Paper from "@mui/material/Paper";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import RuleIcon from "@mui/icons-material/Rule";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";

import StatePanel from "../components/common/StatePanel";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import BankCategoryTag from "../features/bankDetails/BankCategoryTag";
import AutoTagRulesDrawer from "../features/bankDetails/AutoTagRulesDrawer";
import { downloadBankDetailTransactionsExport, fetchBankDetailAccounts, fetchBankDetailTransactions } from "../features/bankDetails/api";
import {
  FINANCE_DOMAIN_EVENTS,
  eventAffectedMonths,
  subscribeFinanceDomainEvent,
} from "../features/domainEvents";
import type {
  BankDateFilter,
  BankDetailAccount,
  BankDetailExportMode,
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
];
const EMPTY_CATEGORY_COUNTS: BankTransactionCategoryCounts = { uncategorized: 0 };

type CategorySummaryItem = {
  code: BankTransactionCategoryCode;
  label: string;
};

type BankDetailsTableToolbarProps = {
  effectiveCategoryCounts: BankTransactionCategoryCounts;
  visibleCategorySummary: CategorySummaryItem[];
  searchKeyword: string;
  onSearchKeywordChange: (value: string) => void;
  exportMenuAnchorEl: HTMLElement | null;
  exportFeedback: string | null;
  isExporting: boolean;
  canExportCurrentAccount: boolean;
  onOpenExportMenu: (event: MouseEvent<HTMLElement>) => void;
  onCloseExportMenu: () => void;
  onExport: (mode: BankDetailExportMode) => void;
};

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
    <Stack alignItems="center" justifyContent="center" sx={{ minHeight: 240, px: 2, textAlign: "center" }}>
      <Typography color="text.secondary">当前时间范围内没有流水。</Typography>
    </Stack>
  );
}

function BankDetailsTableToolbar({
  effectiveCategoryCounts = EMPTY_CATEGORY_COUNTS,
  visibleCategorySummary = [],
  searchKeyword = "",
  onSearchKeywordChange = () => undefined,
  exportMenuAnchorEl = null,
  exportFeedback = null,
  isExporting = false,
  canExportCurrentAccount = false,
  onOpenExportMenu = () => undefined,
  onCloseExportMenu = () => undefined,
  onExport = () => undefined,
}: Partial<BankDetailsTableToolbarProps>) {
  const exportMenuOpen = Boolean(exportMenuAnchorEl);
  return (
    <Box className="bank-grid-toolbar">
      <Stack className="bank-grid-toolbar-content" spacing={1}>
        <Stack className="bank-grid-category-summary" direction="row" gap={0.4}>
          <BankCategoryTag categoryCode={null} compact label="未分类" count={effectiveCategoryCounts.uncategorized} />
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
          {exportFeedback ? (
            <Typography className="bank-export-feedback" color="text.secondary" variant="caption">
              {exportFeedback}
            </Typography>
          ) : null}
          <Button
            aria-controls={exportMenuOpen ? "bank-detail-export-menu" : undefined}
            aria-expanded={exportMenuOpen ? "true" : undefined}
            aria-haspopup="menu"
            className="bank-export-button"
            disabled={isExporting}
            onClick={onOpenExportMenu}
            size="small"
            variant="outlined"
          >
            {isExporting ? "导出中" : "导出"}
          </Button>
          <Menu
            id="bank-detail-export-menu"
            anchorEl={exportMenuAnchorEl}
            open={exportMenuOpen}
            onClose={onCloseExportMenu}
            MenuListProps={{ "aria-label": "导出银行明细" }}
          >
            <MenuItem onClick={() => onExport("all")} disabled={isExporting}>导出全部银行</MenuItem>
            <MenuItem onClick={() => onExport("account")} disabled={isExporting || !canExportCurrentAccount}>导出当前账户</MenuItem>
          </Menu>
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
    </Box>
  );
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

function TypeCell({ row }: { row: BankDetailTransaction }) {
  if (!row.autoCategoryCode || !row.autoCategoryLabel) {
    return <Typography className="bank-auto-type-empty" component="span">-</Typography>;
  }
  return (
    <BankCategoryTag
      categoryCode={row.autoCategoryCode}
      compact
      label={row.autoCategoryLabel}
    />
  );
}

function BankTextCell({ value }: { value: string }) {
  return (
    <Typography className="bank-table-text-cell" component="span" variant="body2">
      {value.trim() || "-"}
    </Typography>
  );
}

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
  const [paginationModel, setPaginationModel] = useState({
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
  const tagVersionRef = useRef<number | null>(readPersistedTagVersion());
  const [dateFilterAnchorEl, setDateFilterAnchorEl] = useState<HTMLElement | null>(null);
  const [exportMenuAnchorEl, setExportMenuAnchorEl] = useState<HTMLElement | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [exportFeedback, setExportFeedback] = useState<string | null>(null);
  const [rulesDrawerOpen, setRulesDrawerOpen] = useState(false);
  const [rulesFeedback, setRulesFeedback] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

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

  const effectiveCategoryCounts = categoryCounts;
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

  const resetToFirstPage = () => {
    setPaginationModel((current) => (
      current.page === 0 ? current : { ...current, page: 0 }
    ));
  };

  const applyDateFilter = (nextFilter: BankDateFilter | ((current: BankDateFilter) => BankDateFilter)) => {
    resetToFirstPage();
    setDateFilter(nextFilter);
  };

  const handleAccountSelect = (accountKey: string) => {
    if (accountKey === selectedAccountKey) {
      return;
    }
    resetToFirstPage();
    setSelectedAccountKey(accountKey);
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

  const openExportMenu = (event: MouseEvent<HTMLElement>) => {
    setExportMenuAnchorEl(event.currentTarget);
  };

  const closeExportMenu = () => {
    setExportMenuAnchorEl(null);
  };

  const handleExport = (mode: BankDetailExportMode) => {
    closeExportMenu();
    const accountKey = selectedAccountKey === ALL_ACCOUNTS_KEY ? null : selectedAccountKey;
    if (mode === "account" && !accountKey) {
      setExportFeedback("请选择具体银行账户");
      return;
    }
    setIsExporting(true);
    setExportFeedback(null);
    downloadBankDetailTransactionsExport({
      mode,
      accountKey,
      dateFrom: dateFilter.dateFrom,
      dateTo: dateFilter.dateTo,
      keyword: searchKeyword,
    })
      .then(({ blob, fileName }) => {
        const objectUrl = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = fileName;
        link.rel = "noopener";
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(objectUrl);
        setExportFeedback("已开始下载");
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setExportFeedback(caught instanceof Error ? caught.message : "银行明细导出失败。");
        }
      })
      .finally(() => {
        setIsExporting(false);
      });
  };

  const handleAutoTagRulesSaved = (payload: { version: number }) => {
    persistTagVersion(payload.version);
    tagVersionRef.current = payload.version;
    window.dispatchEvent(new CustomEvent(TAG_SYNC_EVENT, { detail: { version: payload.version } }));
    if (typeof BroadcastChannel !== "undefined") {
      const channel = new BroadcastChannel(TAG_SYNC_EVENT);
      channel.postMessage({ version: payload.version });
      channel.close();
    }
    setRulesFeedback("规则已保存，银行明细正在刷新。");
    setRefreshToken((current) => current + 1);
  };

  const handleMonthChange = (value: string) => {
    if (!value) {
      setMonthValue(value);
      return;
    }
    setMonthValue(value);
    resetToFirstPage();
    setDateFilter(createDateFilter("month", value));
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

  return (
    <Box className="bank-details-page" data-testid="bank-details-page">
      <Stack className="bank-details-workbench" spacing={1}>
        {error ? <StatePanel tone="error">{error}</StatePanel> : null}
        {loading ? <StatePanel tone="loading" compact>正在加载银行明细。</StatePanel> : null}
        {readModelStatus === "refreshing" && !error ? (
          <StatePanel tone="loading" compact>银行明细读模型正在刷新。</StatePanel>
        ) : null}
        {rulesFeedback ? <StatePanel tone="success" compact>{rulesFeedback}</StatePanel> : null}
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
                  <Button
                    startIcon={<RuleIcon />}
                    size="small"
                    variant="outlined"
                    onClick={() => setRulesDrawerOpen(true)}
                  >
                    自动标签规则
                  </Button>
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
                </Stack>
              </Stack>
            </Stack>

            <Divider />

            <Box className="bank-transaction-grid bank-transaction-grid-readable">
              <BankDetailsTableToolbar
                effectiveCategoryCounts={effectiveCategoryCounts}
                visibleCategorySummary={visibleCategorySummary}
                searchKeyword={searchInput}
                onSearchKeywordChange={handleSearchKeywordChange}
                exportMenuAnchorEl={exportMenuAnchorEl}
                exportFeedback={exportFeedback}
                isExporting={isExporting}
                canExportCurrentAccount={!isAllAccountsSelected}
                onOpenExportMenu={openExportMenu}
                onCloseExportMenu={closeExportMenu}
                onExport={handleExport}
              />
              <TableContainer className="bank-transaction-table-container">
                <Table aria-label="交易流水" className="bank-transaction-table" size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell className="bank-col-counterparty">对方户名</TableCell>
                      <TableCell align="center" className="bank-col-type">类型</TableCell>
                      <TableCell align="right" className="bank-col-amount">金额</TableCell>
                      <TableCell align="right" className="bank-col-balance">余额</TableCell>
                      <TableCell className="bank-col-purpose">用途/交易用途</TableCell>
                      <TableCell className="bank-col-summary">摘要</TableCell>
                      <TableCell className="bank-col-note">备注/附言/客户附言</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rowLoading ? (
                      <TableRow>
                        <TableCell colSpan={7}>
                          <Stack alignItems="center" justifyContent="center" sx={{ minHeight: 220 }}>
                            <Typography color="text.secondary">正在加载流水。</Typography>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    ) : null}
                    {!rowLoading && rows.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7}>
                          <EmptyTransactionOverlay />
                        </TableCell>
                      </TableRow>
                    ) : null}
                    {!rowLoading && rows.map((row, index) => (
                      <TableRow
                        className={index % 2 === 0 ? "bank-grid-row-even" : "bank-grid-row-odd"}
                        hover
                        key={row.id}
                      >
                        <TableCell className="bank-col-counterparty">
                          <Stack className="bank-counterparty-cell" justifyContent="center" spacing={0.5} sx={{ minWidth: 0, width: "100%" }}>
                            <Typography
                              className={`bank-counterparty-name ${counterpartyNameDensity(row.counterpartyName)}`}
                              component="span"
                              variant="body2"
                              fontWeight={750}
                            >
                              {row.counterpartyName}
                            </Typography>
                            <Stack className="bank-relation-time-row" direction="row" spacing={0.5} sx={{ minWidth: 0, maxWidth: "100%" }}>
                              <Chip className="bank-trade-time-chip bank-trade-time-chip-full bank-chip-auto-size" label={row.tradeTime} size="small" variant="outlined" />
                            </Stack>
                            <Stack className="bank-relation-chip-row" direction="row" spacing={0.5} sx={{ minWidth: 0, maxWidth: "100%" }}>
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
                        </TableCell>
                        <TableCell align="center" className="bank-col-type">
                          <TypeCell row={row} />
                        </TableCell>
                        <TableCell align="right" className="bank-col-amount">
                          <Stack className="bank-amount-cell" alignItems="stretch" justifyContent="center" spacing={0.5} sx={{ width: "100%" }}>
                            <Stack className="bank-amount-line" direction="row" alignItems="center" justifyContent="flex-end" spacing={0.75}>
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
                        </TableCell>
                        <TableCell align="right" className="bank-col-balance">
                          <Typography component="span" variant="body2" sx={{ fontVariantNumeric: "tabular-nums" }}>
                            {formatMoney(row.balance)}
                          </Typography>
                        </TableCell>
                        <TableCell className="bank-col-purpose"><BankTextCell value={row.purposeText} /></TableCell>
                        <TableCell className="bank-col-summary"><BankTextCell value={row.summaryText} /></TableCell>
                        <TableCell className="bank-col-note"><BankTextCell value={row.noteText} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <TablePagination
                className="bank-transaction-pagination"
                component="div"
                count={rowCount}
                labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count === -1 ? `超过 ${to}` : count}`}
                labelRowsPerPage="每页行数"
                onPageChange={(_event, page) => setPaginationModel((current) => ({ ...current, page }))}
                onRowsPerPageChange={(event) => {
                  setPaginationModel({ page: 0, pageSize: Number(event.target.value) });
                }}
                page={paginationModel.page}
                rowsPerPage={paginationModel.pageSize}
                rowsPerPageOptions={[25, 50, 100]}
              />
            </Box>
          </Paper>
        </Box>
      </Stack>
      <AutoTagRulesDrawer
        open={rulesDrawerOpen}
        onClose={() => setRulesDrawerOpen(false)}
        onSaved={handleAutoTagRulesSaved}
      />
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
    </Box>
  );
}
