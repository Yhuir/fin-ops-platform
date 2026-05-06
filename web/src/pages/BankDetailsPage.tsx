import { useEffect, useMemo, useState, type FocusEvent, type FormEvent, type MouseEvent } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";

import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { fetchBankDetailAccounts, fetchBankDetailTransactions } from "../features/bankDetails/api";
import type { BankDateFilter, BankDetailAccount, BankDetailTransaction } from "../features/bankDetails/types";

const TODAY = new Date(2026, 4, 2);

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

const transactionColumns: GridColDef<BankDetailTransaction>[] = [
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
    version: 1,
    initialValue: createDateFilter("current_month"),
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
  const [loading, setLoading] = useState(true);
  const [rowLoading, setRowLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchBankDetailAccounts(controller.signal)
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
  }, []);

  useEffect(() => {
    if (!selectedAccountKey) {
      setRows([]);
      return;
    }
    const controller = new AbortController();
    setRowLoading(true);
    setError(null);
    fetchBankDetailTransactions({
      accountKey: selectedAccountKey,
      dateFrom: dateFilter.dateFrom,
      dateTo: dateFilter.dateTo,
      signal: controller.signal,
    })
      .then((payload) => setRows(payload.rows))
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
  }, [dateFilter.dateFrom, dateFilter.dateTo, selectedAccountKey]);

  const selectedAccount = useMemo(
    () => accountsData.accounts.find((account) => account.accountKey === selectedAccountKey) ?? null,
    [accountsData.accounts, selectedAccountKey],
  );

  const applyPreset = (preset: BankDateFilter["preset"]) => {
    setDateFilter(createDateFilter(preset, monthValue));
  };

  const handlePresetChange = (_event: MouseEvent<HTMLElement>, preset: BankDateFilter["preset"] | null) => {
    if (preset) {
      applyPreset(preset);
    }
  };

  const handleMonthChange = (value: string) => {
    setMonthValue(value);
    if (value) {
      setDateFilter(createDateFilter("month", value));
    }
  };

  const handleCustomDateChange = (key: "dateFrom" | "dateTo", value: string) => {
    setDateFilter((current) => ({
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
                        onClick={() => setSelectedAccountKey(account.accountKey)}
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
                  hideFooter
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
    </Box>
  );
}
