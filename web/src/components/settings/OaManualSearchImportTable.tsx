import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import RefreshIcon from "@mui/icons-material/Refresh";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormGroup from "@mui/material/FormGroup";
import FormLabel from "@mui/material/FormLabel";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { useAppChrome } from "../../contexts/AppChromeContext";
import {
  importManualOaRows,
  refreshManualOaImportAttachments,
  searchManualOaImports,
} from "../../features/workbench/api";
import type { OaManualSearchFilters, OaManualSearchRow } from "../../features/workbench/types";
import { settingsButtonSx, settingsTokens } from "./settingsDesign";

const formTypeOptions = [
  { value: "payment_request", label: "支付申请" },
  { value: "expense_claim", label: "日常报销" },
];

const statusOptions = [
  { value: "completed", label: "已完成" },
  { value: "in_progress", label: "进行中" },
];

const compactTextFieldSx = {
  minWidth: { xs: "100%", sm: 180 },
  "& .MuiInputLabel-root": { color: settingsTokens.textSecondary },
  "& .MuiOutlinedInput-root": {
    "&.Mui-focused fieldset": { borderColor: settingsTokens.primary },
  },
};

const oaImportCompletionStatusMs = 1200;
const oaImportPendingStages = [
  { delayMs: 250, percent: 35, label: "解析 OA 附件发票" },
  { delayMs: 900, percent: 70, label: "同步到关联台" },
];

const checkboxSx = {
  color: settingsTokens.textSecondary,
  "&.Mui-checked": { color: settingsTokens.primary },
};

function amountToNumber(value: string) {
  const parsed = Number.parseFloat(value.replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatCurrency(value: number) {
  return `¥${value.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function importStatusLabel(row: OaManualSearchRow) {
  if (row.importStatus === "imported") {
    return "已导入";
  }
  if (row.importStatus === "already_imported") {
    return "已存在";
  }
  return "未导入";
}

function importStatusColor(row: OaManualSearchRow): "default" | "success" | "warning" {
  if (row.importStatus === "imported" || row.importStatus === "already_imported") {
    return "success";
  }
  if (!row.canImport) {
    return "warning";
  }
  return "default";
}

function nextToggledList(value: string, current: string[]) {
  return current.includes(value)
    ? current.filter((item) => item !== value)
    : [...current, value];
}

function mergeUpdatedRows(rows: OaManualSearchRow[], updates: OaManualSearchRow[]) {
  const updateMap = new Map(updates.map((row) => [row.rowId, row]));
  return rows.map((row) => updateMap.get(row.rowId) ?? row);
}

export default function OaManualSearchImportTable() {
  const { setWorkbenchStatus } = useAppChrome();
  const [query, setQuery] = useState("");
  const [formTypes, setFormTypes] = useState(formTypeOptions.map((option) => option.value));
  const [statuses, setStatuses] = useState(statusOptions.map((option) => option.value));
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [rows, setRows] = useState<OaManualSearchRow[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedRows, setSelectedRows] = useState<Record<string, OaManualSearchRow>>({});
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const [hasSearched, setHasSearched] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [busyRowId, setBusyRowId] = useState<string | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState("");
  const pendingStatusTimeoutsRef = useRef<Array<ReturnType<typeof window.setTimeout>>>([]);
  const completionStatusTimeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);

  const selectedList = useMemo(() => Object.values(selectedRows), [selectedRows]);
  const importablePageRows = rows.filter((row) => row.canImport);
  const selectedImportableRows = selectedList.filter((row) => row.canImport && row.importStatus !== "imported");
  const selectedAmount = selectedList.reduce((sum, row) => sum + amountToNumber(row.amount), 0);
  const selectedInvoiceCount = selectedList.reduce((sum, row) => sum + row.importableInvoiceCount, 0);
  const allCurrentPageImportableSelected =
    importablePageRows.length > 0 && importablePageRows.every((row) => selectedRows[row.rowId]);
  const someCurrentPageImportableSelected =
    importablePageRows.some((row) => selectedRows[row.rowId]) && !allCurrentPageImportableSelected;

  const buildFilters = (targetPage = page, targetPageSize = pageSize): OaManualSearchFilters => ({
    query,
    formTypes,
    statuses,
    dateFrom,
    dateTo,
    page: targetPage,
    pageSize: targetPageSize,
  });

  function clearOaImportStatusTimers() {
    pendingStatusTimeoutsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
    pendingStatusTimeoutsRef.current = [];
    if (completionStatusTimeoutRef.current !== null) {
      window.clearTimeout(completionStatusTimeoutRef.current);
      completionStatusTimeoutRef.current = null;
    }
  }

  function publishOaImportStatus(percent: number, label: string) {
    setWorkbenchStatus({
      level: "pending",
      percent,
      reason: `OA导入 ${percent}%：${label}`,
    });
  }

  function scheduleOaImportPendingStages() {
    pendingStatusTimeoutsRef.current = oaImportPendingStages.map((stage) =>
      window.setTimeout(() => {
        publishOaImportStatus(stage.percent, stage.label);
      }, stage.delayMs)
    );
  }

  function publishOaImportError(reason: string) {
    clearOaImportStatusTimers();
    setWorkbenchStatus({ level: "error", reason });
  }

  function publishOaImportComplete() {
    clearOaImportStatusTimers();
    publishOaImportStatus(100, "导入完成");
    completionStatusTimeoutRef.current = window.setTimeout(() => {
      setWorkbenchStatus(null);
      completionStatusTimeoutRef.current = null;
    }, oaImportCompletionStatusMs);
  }

  useEffect(() => () => {
    clearOaImportStatusTimers();
    setWorkbenchStatus(null);
  }, [setWorkbenchStatus]);

  async function runSearch(targetPage = 0, targetPageSize = pageSize) {
    if (formTypes.length === 0 || statuses.length === 0) {
      setRows([]);
      setTotal(0);
      setPage(targetPage);
      setPageSize(targetPageSize);
      setHasSearched(true);
      setError("至少选择一个表单类型和一个流程状态");
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const result = await searchManualOaImports(buildFilters(targetPage, targetPageSize));
      setRows(result.rows);
      setTotal(result.total);
      setPage(result.page);
      setPageSize(result.pageSize || targetPageSize);
      setHasSearched(true);
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : "搜索失败");
    } finally {
      setIsLoading(false);
    }
  }

  function toggleRow(row: OaManualSearchRow) {
    if (!row.canImport) {
      return;
    }
    setSelectedRows((current) => {
      const next = { ...current };
      if (next[row.rowId]) {
        delete next[row.rowId];
      } else {
        next[row.rowId] = row;
      }
      return next;
    });
  }

  function toggleCurrentPageImportable() {
    setSelectedRows((current) => {
      const next = { ...current };
      if (allCurrentPageImportableSelected) {
        importablePageRows.forEach((row) => {
          delete next[row.rowId];
        });
      } else {
        importablePageRows.forEach((row) => {
          next[row.rowId] = row;
        });
      }
      return next;
    });
  }

  async function handleRefresh(row: OaManualSearchRow) {
    setBusyRowId(row.rowId);
    setError("");
    try {
      const result = await refreshManualOaImportAttachments([row.rowId]);
      const updatedCounts = result.rows[0];
      if (updatedCounts) {
        const updateRow = (candidate: OaManualSearchRow) =>
          candidate.rowId === updatedCounts.rowId
            ? {
              ...candidate,
              attachmentFileCount: updatedCounts.attachmentFileCount,
              importableInvoiceCount: updatedCounts.importableInvoiceCount,
              unrecognizedAttachmentCount: updatedCounts.unrecognizedAttachmentCount,
            }
            : candidate;
        setRows((current) => current.map(updateRow));
        setSelectedRows((current) => Object.fromEntries(
          Object.entries(current).map(([rowId, selectedRow]) => [rowId, updateRow(selectedRow)]),
        ));
      }
      if (result.errors.length > 0) {
        setError("部分附件刷新失败");
      }
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "附件刷新失败");
    } finally {
      setBusyRowId(null);
    }
  }

  async function handleImportSelected() {
    if (selectedImportableRows.length === 0) {
      return;
    }
    clearOaImportStatusTimers();
    publishOaImportStatus(10, "准备导入已选 OA");
    scheduleOaImportPendingStages();
    setIsImporting(true);
    setError("");
    try {
      const result = await importManualOaRows(selectedImportableRows.map((row) => row.rowId));
      publishOaImportStatus(90, "刷新搜索结果");
      setRows((current) => mergeUpdatedRows(current, result.rows));
      setSelectedRows((current) => {
        const updatedMap = new Map(result.rows.map((row) => [row.rowId, row]));
        return Object.fromEntries(
          Object.entries(current).map(([rowId, row]) => [rowId, updatedMap.get(rowId) ?? row]),
        );
      });
      if (result.failed.length > 0) {
        setError("部分 OA 导入失败");
        publishOaImportError("OA导入失败：部分 OA 导入失败");
      } else {
        publishOaImportComplete();
      }
    } catch (importError) {
      const reason = importError instanceof Error ? importError.message : "导入失败";
      setError(reason);
      publishOaImportError(`OA导入失败：${reason}`);
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <Box
      component="section"
      aria-labelledby="oa-manual-search-import-title"
      sx={{
        mt: 2,
        pt: 3,
        borderTop: `1px solid ${settingsTokens.borderSubtle}`,
      }}
    >
      <Stack spacing={2.5}>
        <Stack direction={{ xs: "column", md: "row" }} alignItems={{ xs: "stretch", md: "center" }} justifyContent="space-between" spacing={2}>
          <Box>
            <Typography id="oa-manual-search-import-title" component="h4" variant="h6" sx={{ color: settingsTokens.textPrimary, fontWeight: 400, fontSize: "16px" }}>
              OA全量搜索导入
            </Typography>
            <Typography component="p" variant="body2" sx={{ color: settingsTokens.textSecondary, mt: 0.5 }}>
              可按独立条件搜索全量 OA，并手动导入已完成 OA 项。
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip label={`已选 ${selectedList.length} 个OA`} size="small" />
            <Chip label={`金额合计 ${formatCurrency(selectedAmount)}`} size="small" />
            <Chip label={`预计发票 ${selectedInvoiceCount} 张`} size="small" />
          </Stack>
        </Stack>

        <Stack spacing={2}>
          <Stack direction={{ xs: "column", lg: "row" }} spacing={2} alignItems={{ xs: "stretch", lg: "flex-start" }}>
            <TextField
              label="搜索关键字"
              size="small"
              value={query}
              onChange={(event) => setQuery(event.currentTarget.value)}
              sx={{ ...compactTextFieldSx, flex: 1, minWidth: { xs: "100%", lg: 260 } }}
            />
            <TextField
              label="开始日期"
              type="date"
              size="small"
              value={dateFrom}
              onChange={(event) => setDateFrom(event.currentTarget.value)}
              slotProps={{ inputLabel: { shrink: true } }}
              sx={compactTextFieldSx}
            />
            <TextField
              label="结束日期"
              type="date"
              size="small"
              value={dateTo}
              onChange={(event) => setDateTo(event.currentTarget.value)}
              slotProps={{ inputLabel: { shrink: true } }}
              sx={compactTextFieldSx}
            />
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
            <FormControl component="fieldset">
              <FormLabel component="legend" sx={{ color: settingsTokens.textSecondary, fontSize: "14px", mb: 1 }}>搜索表单类型</FormLabel>
              <FormGroup row>
                {formTypeOptions.map((option) => (
                  <FormControlLabel
                    key={option.value}
                    control={(
                      <Checkbox
                        size="small"
                        checked={formTypes.includes(option.value)}
                        onChange={() => setFormTypes((current) => nextToggledList(option.value, current))}
                        sx={checkboxSx}
                      />
                    )}
                    label={`搜索${option.label}`}
                  />
                ))}
              </FormGroup>
            </FormControl>
            <FormControl component="fieldset">
              <FormLabel component="legend" sx={{ color: settingsTokens.textSecondary, fontSize: "14px", mb: 1 }}>搜索流程状态</FormLabel>
              <FormGroup row>
                {statusOptions.map((option) => (
                  <FormControlLabel
                    key={option.value}
                    control={(
                      <Checkbox
                        size="small"
                        checked={statuses.includes(option.value)}
                        onChange={() => setStatuses((current) => nextToggledList(option.value, current))}
                        sx={checkboxSx}
                      />
                    )}
                    label={`搜索${option.label}`}
                  />
                ))}
              </FormGroup>
            </FormControl>
          </Stack>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button variant="contained" onClick={() => void runSearch(0, pageSize)} disabled={isLoading} sx={settingsButtonSx}>
              搜索
            </Button>
            <Button
              variant="outlined"
              onClick={() => {
                setQuery("");
                setDateFrom("");
                setDateTo("");
                setFormTypes(formTypeOptions.map((option) => option.value));
                setStatuses(statusOptions.map((option) => option.value));
                setRows([]);
                setTotal(0);
                setPage(0);
                setSelectedRows({});
                setExpandedRows({});
                setHasSearched(false);
                setError("");
              }}
            >
              清空
            </Button>
            <Button variant="outlined" onClick={() => setSelectedRows({})}>
              清空选择
            </Button>
            <Button
              variant="contained"
              onClick={() => void handleImportSelected()}
              disabled={selectedImportableRows.length === 0 || isImporting}
              sx={settingsButtonSx}
            >
              {isImporting ? "正在导入" : "导入已选OA项"}
            </Button>
          </Stack>
        </Stack>

        {error ? <Alert severity="error">{error}</Alert> : null}

        <TableContainer sx={{ border: `1px solid ${settingsTokens.borderSubtle}` }}>
          <Table aria-label="OA全量搜索导入结果" size="small">
            <TableHead sx={{ bgcolor: settingsTokens.layer01 }}>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    size="small"
                    checked={allCurrentPageImportableSelected}
                    indeterminate={someCurrentPageImportableSelected}
                    disabled={importablePageRows.length === 0}
                    onChange={toggleCurrentPageImportable}
                    slotProps={{ input: { "aria-label": "选择当前页可导入OA" } }}
                    sx={checkboxSx}
                  />
                </TableCell>
                <TableCell />
                <TableCell>OA编号</TableCell>
                <TableCell>申请人</TableCell>
                <TableCell>申请日期</TableCell>
                <TableCell>表单类型</TableCell>
                <TableCell>流程状态</TableCell>
                <TableCell>项目摘要</TableCell>
                <TableCell align="right">整单金额</TableCell>
                <TableCell align="right">附件总数</TableCell>
                <TableCell align="right">可导入发票</TableCell>
                <TableCell align="right">未识别附件</TableCell>
                <TableCell>导入状态</TableCell>
                <TableCell>禁用原因</TableCell>
                <TableCell align="right">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={15} align="center" sx={{ py: 4 }}>
                    <CircularProgress size={24} aria-label="正在搜索OA" />
                  </TableCell>
                </TableRow>
              ) : rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={15} align="center" sx={{ color: settingsTokens.textSecondary, py: 4 }}>
                    {hasSearched ? "没有符合条件的 OA" : "输入条件后点击搜索"}
                  </TableCell>
                </TableRow>
              ) : rows.map((row) => {
                const expanded = expandedRows[row.rowId] === true;
                return (
                  <Fragment key={row.rowId}>
                    <TableRow key={row.rowId} hover selected={Boolean(selectedRows[row.rowId])}>
                      <TableCell padding="checkbox">
                        <Tooltip title={row.canImport ? "" : row.disabledReason || "不可导入"}>
                          <span>
                            <Checkbox
                              size="small"
                              checked={Boolean(selectedRows[row.rowId])}
                              disabled={!row.canImport}
                              onChange={() => toggleRow(row)}
                              slotProps={{ input: { "aria-label": `选择 OA ${row.rowId}` } }}
                              sx={checkboxSx}
                            />
                          </span>
                        </Tooltip>
                      </TableCell>
                      <TableCell padding="checkbox">
                        <IconButton
                          size="small"
                          aria-label={`${expanded ? "收起" : "展开"} OA ${row.rowId} 明细`}
                          onClick={() => setExpandedRows((current) => ({ ...current, [row.rowId]: !expanded }))}
                        >
                          {expanded ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                        </IconButton>
                      </TableCell>
                      <TableCell>{row.oaNo || row.rowId}</TableCell>
                      <TableCell>{row.applicant}</TableCell>
                      <TableCell>{row.applicationDate}</TableCell>
                      <TableCell>{row.formTypeLabel}</TableCell>
                      <TableCell>
                        <Chip label={row.statusLabel} size="small" color={row.status === "completed" ? "success" : "warning"} variant="outlined" />
                      </TableCell>
                      <TableCell sx={{ maxWidth: 260 }}>
                        <Typography variant="body2" sx={{ color: settingsTokens.textPrimary }}>{row.projectName}</Typography>
                        <Typography variant="caption" sx={{ color: settingsTokens.textSecondary }}>{row.reason}</Typography>
                      </TableCell>
                      <TableCell align="right">{row.amount}</TableCell>
                      <TableCell align="right">{row.attachmentFileCount}</TableCell>
                      <TableCell align="right">{row.importableInvoiceCount}</TableCell>
                      <TableCell align="right">{row.unrecognizedAttachmentCount}</TableCell>
                      <TableCell>
                        <Chip label={importStatusLabel(row)} size="small" color={importStatusColor(row)} variant="outlined" />
                      </TableCell>
                      <TableCell>{row.canImport ? "" : row.disabledReason || "不可导入"}</TableCell>
                      <TableCell align="right">
                        <Tooltip title="刷新附件解析">
                          <span>
                            <IconButton
                              size="small"
                              aria-label={`刷新 OA ${row.rowId} 附件解析`}
                              disabled={busyRowId === row.rowId}
                              onClick={() => void handleRefresh(row)}
                            >
                              <RefreshIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                    <TableRow key={`${row.rowId}-details`}>
                      <TableCell colSpan={15} sx={{ py: 0, bgcolor: settingsTokens.layer01 }}>
                        <Collapse in={expanded} timeout="auto" unmountOnExit>
                          <Box sx={{ py: 2 }}>
                            <Table size="small" aria-label={`OA ${row.rowId} 明细`}>
                              <TableHead>
                                <TableRow>
                                  <TableCell>明细日期</TableCell>
                                  <TableCell align="right">金额</TableCell>
                                  <TableCell>费用/付款内容</TableCell>
                                  <TableCell>项目名称</TableCell>
                                  <TableCell>申请事由</TableCell>
                                  <TableCell align="right">明细附件数量</TableCell>
                                  <TableCell align="right">明细可识别发票</TableCell>
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                {row.items.length === 0 ? (
                                  <TableRow>
                                    <TableCell colSpan={7} align="center" sx={{ color: settingsTokens.textSecondary }}>
                                      暂无明细
                                    </TableCell>
                                  </TableRow>
                                ) : row.items.map((item, index) => (
                                  <TableRow key={`${row.rowId}-item-${index}`}>
                                    <TableCell>{item.date}</TableCell>
                                    <TableCell align="right">{item.amount}</TableCell>
                                    <TableCell>{item.content}</TableCell>
                                    <TableCell>{item.projectName}</TableCell>
                                    <TableCell>{item.reason}</TableCell>
                                    <TableCell align="right">{item.attachmentFileCount}</TableCell>
                                    <TableCell align="right">{item.importableInvoiceCount}</TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </Box>
                        </Collapse>
                      </TableCell>
                    </TableRow>
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
        <TablePagination
          component="div"
          count={total}
          page={page}
          rowsPerPage={pageSize}
          rowsPerPageOptions={[10, 20, 50, 100]}
          labelRowsPerPage="每页行数"
          labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count}`}
          onPageChange={(_, nextPage) => {
            if (hasSearched) {
              void runSearch(nextPage, pageSize);
            } else {
              setPage(nextPage);
            }
          }}
          onRowsPerPageChange={(event) => {
            const nextPageSize = Number.parseInt(event.target.value, 10);
            if (hasSearched) {
              void runSearch(0, nextPageSize);
            } else {
              setPage(0);
              setPageSize(nextPageSize);
            }
          }}
        />
      </Stack>
    </Box>
  );
}
