import { useCallback, useEffect, useMemo, useRef, useState, type FocusEvent, type FormEvent, type MouseEvent } from "react";
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
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListSubheader from "@mui/material/ListSubheader";
import ListItemText from "@mui/material/ListItemText";
import Select from "@mui/material/Select";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { DataGrid, type GridColDef, type GridPaginationModel } from "@mui/x-data-grid";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";

import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { fetchBankDetailAccounts, fetchBankDetailTransactions, saveBankTransactionCategories } from "../features/bankDetails/api";
import type {
  BankDateFilter,
  BankDetailAccount,
  BankDetailTransaction,
  BankTransactionCategoryCode,
  BankTransactionCategoryCounts,
} from "../features/bankDetails/types";

const TODAY = new Date(2026, 4, 2);
const DEFAULT_PAGE_SIZE = 100;

type BankTransactionCategoryOption = {
  code: BankTransactionCategoryCode;
  root: string;
  group: string;
  status: string;
  label: string;
  menuLabel: string;
};

const CATEGORY_TREE: Array<{
  root: string;
  groups: Array<{
    name: string;
    displayName: string;
    items: Array<{ code: BankTransactionCategoryCode; status: string }>;
  }>;
}> = [
  {
    root: "借入",
    groups: [
      {
        name: "个人往来款",
        displayName: "个人暂借款",
        items: [
          { code: "borrow_in_personal_pending_repayment", status: "待还款" },
          { code: "borrow_in_personal_repaid", status: "已还款" },
        ],
      },
      {
        name: "公司往来款",
        displayName: "公司暂借款",
        items: [
          { code: "borrow_in_company_pending_repayment", status: "待还款" },
          { code: "borrow_in_company_repaid", status: "已还款" },
        ],
      },
      {
        name: "银行往来款",
        displayName: "银行往来款",
        items: [
          { code: "borrow_in_bank_pending_repayment", status: "待还款" },
          { code: "borrow_in_bank_repaid", status: "已还款" },
        ],
      },
    ],
  },
  {
    root: "借出",
    groups: [
      {
        name: "个人往来款",
        displayName: "个人往来款",
        items: [
          { code: "borrow_out_personal_lent", status: "已借款" },
          { code: "borrow_out_personal_pending_collection", status: "待收款" },
        ],
      },
      {
        name: "公司往来款",
        displayName: "公司往来款",
        items: [
          { code: "borrow_out_company_lent", status: "已借款" },
          { code: "borrow_out_company_pending_collection", status: "待收款" },
        ],
      },
      {
        name: "货款往来款",
        displayName: "货款往来款",
        items: [
          { code: "borrow_out_goods_lent", status: "已借款" },
          { code: "borrow_out_goods_pending_collection", status: "待收款" },
        ],
      },
    ],
  },
  {
    root: "业务往来",
    groups: [
      {
        name: "质保金",
        displayName: "质保金",
        items: [{ code: "business_warranty_pending_collection", status: "待收款" }],
      },
      {
        name: "投标保证金",
        displayName: "投标保证金",
        items: [{ code: "business_bid_bond_pending_collection", status: "待收款" }],
      },
      {
        name: "履约保证金",
        displayName: "履约保证金",
        items: [{ code: "business_performance_bond_pending_collection", status: "待收款" }],
      },
      {
        name: "已开发票未收款",
        displayName: "已开发票未收款",
        items: [{ code: "business_invoiced_pending_collection", status: "待收款" }],
      },
    ],
  },
];

const SELECTABLE_CATEGORY_OPTIONS: BankTransactionCategoryOption[] = CATEGORY_TREE.flatMap((rootNode) => (
  rootNode.groups.flatMap((group) => (
    group.items.map((item) => ({
      code: item.code,
      root: rootNode.root,
      group: group.name,
      status: item.status,
      label: `${group.displayName}：${item.status}`,
      menuLabel: `${rootNode.root} / ${group.name} / ${item.status}`,
    }))
  ))
));

const CATEGORY_LABEL_BY_CODE: Partial<Record<BankTransactionCategoryCode, string>> = {
  ...Object.fromEntries(SELECTABLE_CATEGORY_OPTIONS.map((option) => [option.code, option.label])),
  external_turnover: "外部往来款",
  internal_transfer: "内部往来款",
  offset: "冲",
  cash_turnover: "现金往来",
};
const EMPTY_CATEGORY_COUNTS: BankTransactionCategoryCounts = {
  uncategorized: 0,
  ...Object.fromEntries(SELECTABLE_CATEGORY_OPTIONS.map((option) => [option.code, 0])),
};

type SavedCategoryState = {
  categoryCode: BankTransactionCategoryCode | null;
  categoryLabel: string | null;
  categoryPath: string[];
  categoryVersion: number | null;
};

type PendingNavigation = {
  run: () => void;
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

function hasOwnDraft(
  drafts: Partial<Record<string, BankTransactionCategoryCode | null>>,
  rowId: string,
) {
  return Object.prototype.hasOwnProperty.call(drafts, rowId);
}

function categoryCountKey(categoryCode: BankTransactionCategoryCode | null) {
  return categoryCode ?? "uncategorized";
}

function applyDirtyCategoryCounts(
  counts: BankTransactionCategoryCounts,
  savedCategoryByRowId: Record<string, SavedCategoryState>,
  draftCategoryByRowId: Partial<Record<string, BankTransactionCategoryCode | null>>,
): BankTransactionCategoryCounts {
  const next = { ...counts };
  Object.entries(draftCategoryByRowId).forEach(([rowId, draftCategoryCode]) => {
    const savedCategoryCode = savedCategoryByRowId[rowId]?.categoryCode ?? null;
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

const baseTransactionColumns: GridColDef<BankDetailTransaction>[] = [
  {
    field: "tradeTime",
    headerName: "交易时间",
    minWidth: 160,
    flex: 1,
  },
  {
    field: "counterpartyName",
    headerName: "对方户名",
    minWidth: 200,
    flex: 1.35,
  },
  {
    field: "amount",
    headerName: "金额",
    minWidth: 170,
    flex: 0.95,
    align: "right",
    headerAlign: "right",
    renderCell: ({ row }) => (
      <Stack direction="row" alignItems="center" justifyContent="flex-end" spacing={0.75} sx={{ width: "100%" }}>
        <Chip
          className={`direction-tag ${row.direction}`}
          label={row.directionLabel}
          size="small"
          variant="filled"
        />
        <Typography component="span" variant="body2" fontWeight={700}>
          {formatMoney(row.amount)}
        </Typography>
      </Stack>
    ),
  },
  {
    field: "balance",
    headerName: "余额",
    minWidth: 140,
    flex: 0.85,
    align: "right",
    headerAlign: "right",
    valueFormatter: (value) => formatMoney(value as string | null),
  },
  {
    field: "summary",
    headerName: "摘要",
    minWidth: 150,
    flex: 1,
  },
  {
    field: "purpose",
    headerName: "用途",
    minWidth: 130,
    flex: 0.8,
  },
];

export default function BankDetailsPage() {
  const selectedAccountSession = usePageSessionState<string | null>({
    pageKey: "bank-details",
    stateKey: "selectedAccountKey",
    version: 1,
    initialValue: null,
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
  const [loading, setLoading] = useState(true);
  const [rowLoading, setRowLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [categoryCounts, setCategoryCounts] = useState<BankTransactionCategoryCounts>(EMPTY_CATEGORY_COUNTS);
  const [savedCategoryByRowId, setSavedCategoryByRowId] = useState<Record<string, SavedCategoryState>>({});
  const [draftCategoryByRowId, setDraftCategoryByRowId] = useState<Partial<Record<string, BankTransactionCategoryCode | null>>>({});
  const draftCategoryByRowIdRef = useRef(draftCategoryByRowId);
  const [savingCategories, setSavingCategories] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<PendingNavigation | null>(null);
  const [snackbar, setSnackbar] = useState<{ severity: "success" | "error"; message: string } | null>(null);

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
        setSelectedAccountKey((current) => (
          current && payload.accounts.some((account) => account.accountKey === current)
            ? current
            : payload.accounts[0]?.accountKey ?? null
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
  }, [dateFilter.dateFrom, dateFilter.dateTo, setSelectedAccountKey]);

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
    fetchBankDetailTransactions({
      accountKey: selectedAccountKey,
      dateFrom: dateFilter.dateFrom,
      dateTo: dateFilter.dateTo,
      page: paginationModel.page + 1,
      pageSize: paginationModel.pageSize,
      signal: controller.signal,
    })
      .then((payload) => {
        setRows(payload.rows);
        setRowCount(payload.pagination.total);
        setCategoryCounts(payload.categoryCounts);
        setSavedCategoryByRowId((current) => {
          const next = { ...current };
          payload.rows.forEach((row) => {
            if (!hasOwnDraft(draftCategoryByRowIdRef.current, row.id)) {
              next[row.id] = {
                categoryCode: row.categoryCode,
                categoryLabel: row.categoryLabel,
                categoryPath: row.categoryPath,
                categoryVersion: row.categoryVersion,
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
  }, [dateFilter.dateFrom, dateFilter.dateTo, paginationModel.page, paginationModel.pageSize, selectedAccountKey]);

  const dirtyEntries = useMemo(
    () => Object.entries(draftCategoryByRowId).filter((entry): entry is [string, BankTransactionCategoryCode | null] => entry[1] !== undefined),
    [draftCategoryByRowId],
  );
  const dirtyCount = dirtyEntries.length;
  const effectiveCategoryCounts = useMemo(
    () => applyDirtyCategoryCounts(categoryCounts, savedCategoryByRowId, draftCategoryByRowId),
    [categoryCounts, draftCategoryByRowId, savedCategoryByRowId],
  );

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

  const applyPreset = (preset: BankDateFilter["preset"]) => {
    applyDateFilter(createDateFilter(preset, monthValue));
  };

  const handlePresetChange = (_event: MouseEvent<HTMLElement>, preset: BankDateFilter["preset"] | null) => {
    if (preset) {
      applyPreset(preset);
    }
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
      return draftCategoryByRowId[row.id] ?? null;
    }
    return savedCategoryByRowId[row.id]?.categoryCode ?? row.categoryCode ?? null;
  }, [draftCategoryByRowId, savedCategoryByRowId]);

  const handleCategoryChange = useCallback((row: BankDetailTransaction, categoryCode: BankTransactionCategoryCode | null) => {
    const savedCategoryCode = savedCategoryByRowId[row.id]?.categoryCode ?? row.categoryCode ?? null;
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

  const transactionColumns = useMemo<GridColDef<BankDetailTransaction>[]>(() => [
    ...baseTransactionColumns,
    {
      field: "categoryCode",
      headerName: "类别",
      minWidth: 190,
      flex: 0.95,
      sortable: false,
      filterable: false,
      renderCell: ({ row }) => {
        const currentCategoryCode = displayCategoryForRow(row);
        return (
          <Select
            fullWidth
            inputProps={{ "aria-label": `${row.id} 类别` }}
            size="small"
            displayEmpty
            value={currentCategoryCode ?? ""}
            onChange={(event) => {
              const nextValue = event.target.value;
              handleCategoryChange(row, nextValue ? nextValue as BankTransactionCategoryCode : null);
            }}
            renderValue={(selected) => {
              const selectedCode = selected ? selected as BankTransactionCategoryCode : null;
              return selectedCode ? (
                <Chip label={CATEGORY_LABEL_BY_CODE[selectedCode] ?? selectedCode} size="small" />
              ) : "无";
            }}
          >
            {[
              <MenuItem key="none" value="">无</MenuItem>,
              ...CATEGORY_TREE.flatMap((rootNode) => [
                <ListSubheader key={`${rootNode.root}:root`}>{rootNode.root}</ListSubheader>,
                ...rootNode.groups.flatMap((group) => [
                  <ListSubheader key={`${rootNode.root}:${group.name}`} sx={{ pl: 4, typography: "caption" }}>
                    {group.name}
                  </ListSubheader>,
                  ...group.items.map((item) => {
                    const label = `${rootNode.root} / ${group.name} / ${item.status}`;
                    return (
                      <MenuItem key={item.code} value={item.code} sx={{ pl: 6 }}>
                        {label}
                      </MenuItem>
                    );
                  }),
                ]),
              ]),
            ]}
          </Select>
        );
      },
    },
  ], [displayCategoryForRow, handleCategoryChange]);

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
            categoryVersion: category.version,
          };
        });
        return next;
      });
      setCategoryCounts(nextCounts);
      setDraftCategoryByRowId({});
      window.dispatchEvent(new CustomEvent("bankTransactionCategoryUpdated", {
        detail: { affectedMonths: response.affectedMonths },
      }));
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
    <Box data-testid="bank-details-page">
      <PageScaffold
        className="bank-details-page"
        title="银行明细"
        actions={(
          <Stack direction="row" flexWrap="wrap" alignItems="center" justifyContent="flex-end" gap={1}>
            <Box sx={{ minWidth: 0, textAlign: { xs: "left", sm: "right" } }}>
              <Typography color="text.secondary" variant="caption">总余额</Typography>
              <Typography component="strong" variant="subtitle1" fontWeight={800} sx={{ display: "block" }}>
                {displayBalance(accountsData.totalBalance)}
              </Typography>
            </Box>
            {accountsData.missingBalanceAccountCount > 0 ? (
              <Chip label={`${accountsData.missingBalanceAccountCount} 个账户无余额`} size="small" color="warning" variant="outlined" />
            ) : null}
          </Stack>
        )}
      >
        <Stack spacing={2}>
          {error ? <StatePanel tone="error">{error}</StatePanel> : null}
          {loading ? <StatePanel tone="loading" compact>正在加载银行明细。</StatePanel> : null}
          {!loading && accountsData.accounts.length === 0 ? (
            <StatePanel tone="empty">暂无银行流水，请先在银行流水导入页面导入。</StatePanel>
          ) : null}

          <Box className="bank-details-layout">
            <Paper component="aside" className="bank-account-tree" elevation={0}>
              <Stack className="bank-account-heading" direction="row" alignItems="center" justifyContent="space-between">
                <Typography className="bank-section-title" component="h2" variant="subtitle2">银行账户</Typography>
                <Chip className="bank-account-total-chip" label={`${accountsData.accounts.length} 个`} size="small" variant="outlined" />
              </Stack>
              <List aria-label="银行账户" dense disablePadding>
                {accountsData.accounts.map((account) => {
                  const selected = account.accountKey === selectedAccountKey;
                  return (
                    <ListItem key={account.accountKey} disablePadding>
                      <ListItemButton
                        aria-current={selected ? "true" : undefined}
                        aria-label={`${account.displayName} 余额 ${displayBalance(account.latestBalance)}`}
                        className={`bank-account-node${selected ? " active" : ""}`}
                        component="button"
                        onClick={() => handleAccountSelect(account.accountKey)}
                      >
                        <ListItemText
                          disableTypography
                          primary={(
                            <Stack direction="row" alignItems="center" spacing={0.75} minWidth={0}>
                              <Typography className="bank-account-name" component="span">{account.bankName}</Typography>
                              <Typography className="bank-account-last4" component="span">{account.accountLast4}</Typography>
                            </Stack>
                          )}
                          secondary={(
                            <Stack direction="row" alignItems="center" spacing={0.75} minWidth={0}>
                              <Chip className="bank-account-count-chip" label={`${account.transactionCount} 条`} size="small" variant="outlined" />
                              {!account.hasBalance ? (
                                <Chip className="bank-account-empty-chip" label="余额为空" size="small" variant="outlined" />
                              ) : null}
                            </Stack>
                          )}
                        />
                        <Box className="bank-account-balance">
                          <Typography component="strong">{displayBalance(account.latestBalance)}</Typography>
                        </Box>
                      </ListItemButton>
                    </ListItem>
                  );
                })}
              </List>
            </Paper>

            <Paper component="section" className="bank-transaction-panel" elevation={0}>
              <Stack className="bank-transaction-toolbar" spacing={1.5}>
                <Stack direction={{ xs: "column", lg: "row" }} alignItems={{ xs: "flex-start", lg: "center" }} justifyContent="space-between" spacing={1.5}>
                  <Box>
                    <Typography component="h2" variant="h6" fontWeight={800}>
                      {selectedAccount?.displayName ?? "账户流水"}
                    </Typography>
                    <Typography color="text.secondary" variant="body2">
                      {dateFilter.dateFrom} 至 {dateFilter.dateTo}
                    </Typography>
                  </Box>
                  <Stack direction="row" flexWrap="wrap" gap={1}>
                    <Chip label={`共 ${rowCount} 条流水`} size="small" variant="outlined" />
                    <Chip label={`当前页 ${paginationModel.page + 1} / ${totalPages}`} size="small" variant="outlined" />
                    {SELECTABLE_CATEGORY_OPTIONS.map((option) => (
                      <Chip
                        key={option.code}
                        label={`${option.label} ${effectiveCategoryCounts[option.code] ?? 0}`}
                        size="small"
                        variant="outlined"
                      />
                    ))}
                    <Chip label={`无 ${effectiveCategoryCounts.uncategorized}`} size="small" variant="outlined" />
                    <Chip label={`未保存 ${dirtyCount}`} size="small" color={dirtyCount > 0 ? "warning" : "default"} variant="outlined" />
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
                </Stack>

                <Stack className="bank-date-filter" direction={{ xs: "column", md: "row" }} spacing={1}>
                  <TextField
                    label="年月筛选"
                    type="month"
                    size="small"
                    value={monthValue}
                    onChange={(event) => handleMonthChange(event.target.value)}
                    InputLabelProps={{ shrink: true }}
                  />
                  <DatePicker
                    enableAccessibleFieldDOMStructure={false}
                    label="开始日期"
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
                    label="结束日期"
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
              </Stack>

              <Divider />

              <Box className="bank-transaction-grid" sx={{ height: { xs: 520, lg: 560 }, minHeight: 420, width: "100%" }}>
                <DataGrid
                  aria-label="交易流水"
                  columns={transactionColumns}
                  rows={rows}
                  loading={rowLoading}
                  disableRowSelectionOnClick
                  paginationMode="server"
                  rowCount={rowCount}
                  paginationModel={paginationModel}
                  onPaginationModelChange={setPaginationModel}
                  pageSizeOptions={[100, 200, 500]}
                  showToolbar
                  getRowClassName={(params) => (params.indexRelativeToCurrentPage % 2 === 0 ? "bank-grid-row-even" : "bank-grid-row-odd")}
                  localeText={{ toolbarQuickFilterPlaceholder: "搜索流水" }}
                  slotProps={{
                    toolbar: {
                      quickFilterProps: {
                        debounceMs: 200,
                      },
                    },
                  }}
                  slots={{ noRowsOverlay: EmptyTransactionOverlay }}
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
      </PageScaffold>
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
