import { Button, Checkbox, Input, ListBox, Select } from "@heroui/react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useAppChrome } from "../../contexts/AppChromeContext";
import { formatMoney } from "../../features/money";
import {
  getManualOaImportAttachmentRefreshStatus,
  importManualOaRows,
  refreshManualOaImportAttachments,
  searchManualOaImports,
} from "../../features/workbench/api";
import type { OaManualSearchFilters, OaManualSearchRow } from "../../features/workbench/types";
import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../common/FinanceTable";

const formTypeOptions = [
  { value: "payment_request", label: "支付申请" },
  { value: "expense_claim", label: "日常报销" },
];

const statusOptions = [
  { value: "completed", label: "已完成" },
  { value: "in_progress", label: "进行中" },
];

const oaImportCompletionStatusMs = 1200;
const oaAttachmentRefreshPollIntervalMs = 1_000;
const oaAttachmentRefreshObservationTimeoutMs = 120_000;
const oaAttachmentRefreshDetailRequestTimeoutMs = 15_000;
const oaImportPendingStages = [
  { delayMs: 250, percent: 35, label: "解析 OA 附件发票" },
  { delayMs: 900, percent: 70, label: "同步到关联台" },
];

function amountToNumber(value: string) {
  const parsed = Number.parseFloat(value.replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatCurrency(value: number) {
  return `¥${formatMoney(value)}`;
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

function importStatusTone(row: OaManualSearchRow) {
  if (row.importStatus === "imported" || row.importStatus === "already_imported") {
    return "success";
  }
  if (!row.canImport) {
    return "warning";
  }
  return "neutral";
}

function oaDisplayLabel(row: OaManualSearchRow) {
  return row.oaNo || [row.applicant, row.applicationDate].filter(Boolean).join(" ") || "未命名 OA";
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

function pageCount(total: number, pageSize: number) {
  return Math.max(1, Math.ceil(total / pageSize));
}

function waitForAttachmentRefreshPoll(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("OA attachment refresh polling aborted", "AbortError"));
      return;
    }
    const onAbort = () => {
      window.clearTimeout(timeoutId);
      reject(new DOMException("OA attachment refresh polling aborted", "AbortError"));
    };
    const timeoutId = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, oaAttachmentRefreshPollIntervalMs);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}

function attachmentRefreshErrorMessage(errors: Array<{ message: string }>) {
  const suffix = errors.length > 1 ? `（另有 ${errors.length - 1} 条错误）` : "";
  return `${errors[0].message}${suffix}`;
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
  const [refreshMessage, setRefreshMessage] = useState("");
  const pendingStatusTimeoutsRef = useRef<Array<ReturnType<typeof window.setTimeout>>>([]);
  const completionStatusTimeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const attachmentRefreshAbortRef = useRef<AbortController | null>(null);
  const attachmentRefreshObservationTimeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const importInFlightRef = useRef(false);
  const mountedRef = useRef(true);

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

  function clearAttachmentRefreshObservationTimeout() {
    if (attachmentRefreshObservationTimeoutRef.current !== null) {
      window.clearTimeout(attachmentRefreshObservationTimeoutRef.current);
      attachmentRefreshObservationTimeoutRef.current = null;
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

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearAttachmentRefreshObservationTimeout();
      attachmentRefreshAbortRef.current?.abort();
      attachmentRefreshAbortRef.current = null;
      clearOaImportStatusTimers();
      setWorkbenchStatus(null);
    };
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
    if (attachmentRefreshAbortRef.current || importInFlightRef.current || row.status !== "completed") {
      return;
    }
    const controller = new AbortController();
    let observationTimedOut = false;
    attachmentRefreshAbortRef.current = controller;
    setBusyRowId(row.rowId);
    setError("");
    setRefreshMessage("已进入 OA 附件解析队列");
    try {
      const request = await refreshManualOaImportAttachments([row.rowId], controller.signal);
      attachmentRefreshObservationTimeoutRef.current = window.setTimeout(() => {
        observationTimedOut = true;
        attachmentRefreshObservationTimeoutRef.current = null;
        controller.abort();
      }, oaAttachmentRefreshObservationTimeoutMs);
      let status = await getManualOaImportAttachmentRefreshStatus(
        request.eventId,
        request.rowIds,
        controller.signal,
      );
      while (status.status === "pending" || status.status === "processing") {
        setRefreshMessage(status.status === "processing" ? "正在重新解析 OA 附件" : "等待 OA 附件解析");
        await waitForAttachmentRefreshPoll(controller.signal);
        status = await getManualOaImportAttachmentRefreshStatus(
          request.eventId,
          request.rowIds,
          controller.signal,
        );
      }
      clearAttachmentRefreshObservationTimeout();
      if (status.status !== "done") {
        throw new Error(status.error || "OA 附件刷新失败");
      }
      if (!status.result || status.result.rows.length === 0) {
        throw new Error("OA 附件刷新完成，但结果缺少附件计数");
      }
      if (status.result.errors.length > 0) {
        throw new Error(attachmentRefreshErrorMessage(status.result.errors));
      }
      const refreshed = await searchManualOaImports({
        query: row.rowId,
        formTypes: [row.formType],
        statuses: ["completed"],
        dateFrom: "",
        dateTo: "",
        page: 0,
        pageSize: 1,
      }, controller.signal, {
        timeoutMs: oaAttachmentRefreshDetailRequestTimeoutMs,
        timeoutMessage: "OA 附件刷新已完成，但最新 OA 明细查询超时。",
      });
      const refreshedRow = refreshed.rows.find((candidate) => candidate.rowId === row.rowId);
      const refreshSummary = status.result.rows.find((candidate) => candidate.rowId === row.rowId);
      if (!refreshedRow || !refreshSummary) {
        throw new Error("OA 附件刷新完成，但无法读取最新 OA 明细");
      }
      if (
        refreshedRow.attachmentFileCount !== refreshSummary.attachmentFileCount
        || refreshedRow.importableInvoiceCount !== refreshSummary.importableInvoiceCount
        || refreshedRow.unrecognizedAttachmentCount !== refreshSummary.unrecognizedAttachmentCount
      ) {
        throw new Error("OA 附件刷新结果与最新 OA 投影不一致");
      }
      if (controller.signal.aborted || !mountedRef.current) {
        return;
      }
      setRows((current) => mergeUpdatedRows(current, [refreshedRow]));
      setSelectedRows((current) => Object.fromEntries(
        Object.entries(current).map(([rowId, selectedRow]) => [
          rowId,
          rowId === refreshedRow.rowId ? refreshedRow : selectedRow,
        ]),
      ));
      setRefreshMessage("OA 附件刷新完成");
    } catch (refreshError) {
      if (observationTimedOut) {
        if (mountedRef.current) {
          setError("");
          setRefreshMessage("OA 附件解析仍在后台进行，请稍后重新搜索查看结果");
        }
        return;
      }
      if (isAbortError(refreshError)) {
        return;
      }
      if (mountedRef.current) {
        setRefreshMessage("");
        setError(refreshError instanceof Error ? refreshError.message : "附件刷新失败");
      }
    } finally {
      clearAttachmentRefreshObservationTimeout();
      if (attachmentRefreshAbortRef.current === controller) {
        attachmentRefreshAbortRef.current = null;
        if (mountedRef.current) {
          setBusyRowId(null);
        }
      }
    }
  }

  async function handleImportSelected() {
    if (
      selectedImportableRows.length === 0
      || importInFlightRef.current
      || attachmentRefreshAbortRef.current
    ) {
      return;
    }
    importInFlightRef.current = true;
    clearOaImportStatusTimers();
    publishOaImportStatus(10, "准备导入已选 OA");
    scheduleOaImportPendingStages();
    setIsImporting(true);
    setError("");
    setRefreshMessage("");
    try {
      const result = await importManualOaRows(selectedImportableRows.map((row) => row.rowId));
      publishOaImportStatus(95, "更新搜索结果");
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
      importInFlightRef.current = false;
      setIsImporting(false);
    }
  }

  const currentFrom = total === 0 ? 0 : page * pageSize + 1;
  const currentTo = Math.min(total, (page + 1) * pageSize);
  const totalPages = pageCount(total, pageSize);

  return (
    <section aria-labelledby="oa-manual-search-import-title" className="oa-manual-import">
      <div className="oa-manual-import__header">
        <div>
          <h4 id="oa-manual-search-import-title">OA全量搜索导入</h4>
          <p>可按独立条件搜索全量 OA，并手动导入已完成 OA 项。</p>
        </div>
        <div className="oa-manual-import__metrics">
          <span>已选 {selectedList.length} 个OA</span>
          <span>金额合计 {formatCurrency(selectedAmount)}</span>
          <span>预计发票 {selectedInvoiceCount} 张</span>
        </div>
      </div>

      <div className="oa-manual-import__filters">
        <label className="settings-field">
          <span>搜索关键字</span>
          <Input value={query} type="search" onChange={(event) => setQuery(event.currentTarget.value)} />
        </label>
        <label className="settings-field settings-field--date">
          <span>开始日期</span>
          <Input value={dateFrom} type="date" onChange={(event) => setDateFrom(event.currentTarget.value)} />
        </label>
        <label className="settings-field settings-field--date">
          <span>结束日期</span>
          <Input value={dateTo} type="date" onChange={(event) => setDateTo(event.currentTarget.value)} />
        </label>
      </div>

      <div className="oa-manual-import__filter-groups">
        <fieldset className="settings-checkbox-group">
          <legend>搜索表单类型</legend>
          <div className="settings-checkbox-list settings-checkbox-list--inline">
            {formTypeOptions.map((option) => (
              <Checkbox
                className="settings-checkbox-row"
                isSelected={formTypes.includes(option.value)}
                key={option.value}
                onChange={() => setFormTypes((current) => nextToggledList(option.value, current))}
              >
                <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                <span>搜索{option.label}</span>
              </Checkbox>
            ))}
          </div>
        </fieldset>
        <fieldset className="settings-checkbox-group">
          <legend>搜索流程状态</legend>
          <div className="settings-checkbox-list settings-checkbox-list--inline">
            {statusOptions.map((option) => (
              <Checkbox
                className="settings-checkbox-row"
                isSelected={statuses.includes(option.value)}
                key={option.value}
                onChange={() => setStatuses((current) => nextToggledList(option.value, current))}
              >
                <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                <span>搜索{option.label}</span>
              </Checkbox>
            ))}
          </div>
        </fieldset>
      </div>

      <div className="oa-manual-import__actions">
        <Button className="settings-primary-button" isDisabled={isLoading} onPress={() => void runSearch(0, pageSize)} size="sm" variant="primary">
          搜索
        </Button>
        <Button
          className="settings-secondary-button"
          onPress={() => {
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
          size="sm"
          variant="secondary"
        >
          清空
        </Button>
        <Button className="settings-secondary-button" onPress={() => setSelectedRows({})} size="sm" variant="secondary">
          清空选择
        </Button>
        <Button
          className="settings-primary-button"
          isDisabled={selectedImportableRows.length === 0 || isImporting || busyRowId !== null}
          onPress={() => void handleImportSelected()}
          size="sm"
          variant="primary"
        >
          {isImporting ? "正在导入" : "导入已选OA项"}
        </Button>
      </div>

      {error ? <div className="settings-inline-alert settings-inline-alert--error" role="alert">{error}</div> : null}
      {refreshMessage ? <div className="settings-inline-alert" role="status">{refreshMessage}</div> : null}

      <div className="settings-native-table-shell settings-native-table-shell--scroll">
        <FinanceTable ariaLabel="OA全量搜索导入结果" className="settings-native-table oa-manual-import__table" minWidth={1680} scrollMode="contained">
          <FinanceTableHeader>
              <FinanceTableColumn id="selection" columnRole="selection">
                <Checkbox
                  aria-label="选择当前页可导入OA"
                  isDisabled={importablePageRows.length === 0}
                  isIndeterminate={someCurrentPageImportableSelected}
                  isSelected={allCurrentPageImportableSelected}
                  slot="selection"
                  onChange={toggleCurrentPageImportable}
                >
                  <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                </Checkbox>
              </FinanceTableColumn>
              <FinanceTableColumn id="expand" columnRole="action">明细</FinanceTableColumn>
              <FinanceTableColumn id="oa" isRowHeader columnRole="identity">OA编号</FinanceTableColumn>
              <FinanceTableColumn id="applicant" columnRole="identity">申请人</FinanceTableColumn>
              <FinanceTableColumn id="date" columnRole="date">申请日期</FinanceTableColumn>
              <FinanceTableColumn id="type" columnRole="description">表单类型</FinanceTableColumn>
              <FinanceTableColumn id="status" columnRole="status">流程状态</FinanceTableColumn>
              <FinanceTableColumn id="project" columnRole="description">项目摘要</FinanceTableColumn>
              <FinanceTableColumn id="amount" columnRole="amount">整单金额</FinanceTableColumn>
              <FinanceTableColumn id="attachments" columnRole="quantity">附件总数</FinanceTableColumn>
              <FinanceTableColumn id="invoices" columnRole="quantity">可导入发票</FinanceTableColumn>
              <FinanceTableColumn id="unrecognized" columnRole="quantity">未识别附件</FinanceTableColumn>
              <FinanceTableColumn id="importStatus" columnRole="status">导入状态</FinanceTableColumn>
              <FinanceTableColumn id="reason" columnRole="description">禁用原因</FinanceTableColumn>
              <FinanceTableColumn id="action" columnRole="action">操作</FinanceTableColumn>
          </FinanceTableHeader>
          <FinanceTableBody>
            {isLoading ? (
              <OaStateRow label="正在搜索OA" />
            ) : rows.length === 0 ? (
              <OaStateRow label={hasSearched ? "没有符合条件的 OA" : "输入条件后点击搜索"} />
            ) : rows.map((row) => {
              const expanded = expandedRows[row.rowId] === true;
              return (
                  <FinanceTableRow id={row.rowId} key={row.rowId} className={selectedRows[row.rowId] ? "settings-native-table-row--selected" : undefined}>
                    <FinanceTableCell columnRole="selection">
                      <Checkbox
                        aria-label={`选择 OA ${oaDisplayLabel(row)}`}
                        isSelected={Boolean(selectedRows[row.rowId])}
                        isDisabled={!row.canImport}
                        onChange={() => toggleRow(row)}
                      >
                        <Checkbox.Control>
                          <Checkbox.Indicator />
                        </Checkbox.Control>
                      </Checkbox>
                    </FinanceTableCell>
                    <FinanceTableCell columnRole="action">
                      <Button
                        aria-label={`${expanded ? "收起" : "展开"} OA ${oaDisplayLabel(row)} 明细`}
                        className="settings-icon-button"
                        isIconOnly
                        onPress={() => setExpandedRows((current) => ({ ...current, [row.rowId]: !expanded }))}
                        size="sm"
                        variant="tertiary"
                      >
                        {expanded ? <ChevronDown aria-hidden="true" size={16} /> : <ChevronRight aria-hidden="true" size={16} />}
                      </Button>
                    </FinanceTableCell>
                    <FinanceTableCell columnRole="identity">{row.oaNo || "-"}</FinanceTableCell>
                    <FinanceTableCell columnRole="identity">{row.applicant}</FinanceTableCell>
                    <FinanceTableCell columnRole="date">{row.applicationDate}</FinanceTableCell>
                    <FinanceTableCell columnRole="description">{row.formTypeLabel}</FinanceTableCell>
                    <FinanceTableCell columnRole="status">
                      <span className={`settings-selected-tag settings-selected-tag--${row.status === "completed" ? "success" : "warning"}`}>
                        {row.statusLabel}
                      </span>
                    </FinanceTableCell>
                    <FinanceTableCell columnRole="description" className="oa-manual-import__project">
                      <strong>{row.projectName}</strong>
                      <small>{row.reason}</small>
                      {expanded ? <OaDetailTable row={row} /> : null}
                    </FinanceTableCell>
                    <FinanceTableCell columnRole="amount" className="settings-table-amount">{formatMoney(row.amount)}</FinanceTableCell>
                    <FinanceTableCell columnRole="quantity" className="settings-table-amount">{row.attachmentFileCount}</FinanceTableCell>
                    <FinanceTableCell columnRole="quantity" className="settings-table-amount">{row.importableInvoiceCount}</FinanceTableCell>
                    <FinanceTableCell columnRole="quantity" className="settings-table-amount">{row.unrecognizedAttachmentCount}</FinanceTableCell>
                    <FinanceTableCell columnRole="status">
                      <span className={`settings-selected-tag settings-selected-tag--${importStatusTone(row)}`}>
                        {importStatusLabel(row)}
                      </span>
                    </FinanceTableCell>
                    <FinanceTableCell columnRole="description">{row.canImport ? "" : row.disabledReason || "不可导入"}</FinanceTableCell>
                    <FinanceTableCell columnRole="action">
                      <Button
                        aria-label={`刷新 OA ${oaDisplayLabel(row)} 附件解析`}
                        className="settings-icon-button"
                        isDisabled={busyRowId !== null || isImporting || row.status !== "completed"}
                        isIconOnly
                        onPress={() => void handleRefresh(row)}
                        size="sm"
                        variant="tertiary"
                      >
                        <RefreshCw aria-hidden="true" size={16} />
                      </Button>
                    </FinanceTableCell>
                  </FinanceTableRow>
              );
            })}
          </FinanceTableBody>
        </FinanceTable>
      </div>

      <div className="settings-table-pagination">
        <span>{currentFrom}-{currentTo} / {total}</span>
        <div>
          <span>每页行数</span>
          <Select
            aria-label="每页行数"
            selectedKey={String(pageSize)}
            onSelectionChange={(key) => {
              const nextPageSize = Number.parseInt(String(key), 10);
              if (hasSearched) {
                void runSearch(0, nextPageSize);
              } else {
                setPage(0);
                setPageSize(nextPageSize);
              }
            }}
          >
            <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
            <Select.Popover>
              <ListBox>
                {[10, 20, 50, 100].map((option) => <ListBox.Item id={String(option)} key={option} textValue={String(option)}>{option}</ListBox.Item>)}
              </ListBox>
            </Select.Popover>
          </Select>
        </div>
        <div className="settings-table-pagination__actions">
          <Button
            className="settings-secondary-button"
            isDisabled={page <= 0}
            onPress={() => {
              const nextPage = Math.max(0, page - 1);
              if (hasSearched) {
                void runSearch(nextPage, pageSize);
              } else {
                setPage(nextPage);
              }
            }}
            size="sm"
            variant="secondary"
          >
            上一页
          </Button>
          <Button
            className="settings-secondary-button"
            isDisabled={page + 1 >= totalPages}
            onPress={() => {
              const nextPage = Math.min(totalPages - 1, page + 1);
              if (hasSearched) {
                void runSearch(nextPage, pageSize);
              } else {
                setPage(nextPage);
              }
            }}
            size="sm"
            variant="secondary"
          >
            下一页
          </Button>
        </div>
      </div>
    </section>
  );
}

function OaStateRow({ label }: { label: string }) {
  const roles = ["selection", "action", "identity", "identity", "date", "description", "status", "description", "amount", "quantity", "quantity", "quantity", "status", "description", "action"] as const;
  return (
    <FinanceTableRow id="oa-state">
      {roles.map((role, index) => <FinanceTableCell className={index === 2 ? "settings-table-empty" : undefined} columnRole={role} key={`${role}-${index}`}>{index === 2 ? label : "-"}</FinanceTableCell>)}
    </FinanceTableRow>
  );
}

function OaDetailTable({ row }: { row: OaManualSearchRow }) {
  return (
    <div className="oa-manual-import__detail-cell">
      <FinanceTable ariaLabel={`OA ${oaDisplayLabel(row)} 明细`} className="settings-native-table oa-manual-import__detail-table" minWidth={900}>
        <FinanceTableHeader>
          <FinanceTableColumn id="date" isRowHeader columnRole="date">明细日期</FinanceTableColumn>
          <FinanceTableColumn id="amount" columnRole="amount">金额</FinanceTableColumn>
          <FinanceTableColumn id="content" columnRole="description">费用/付款内容</FinanceTableColumn>
          <FinanceTableColumn id="project" columnRole="description">项目名称</FinanceTableColumn>
          <FinanceTableColumn id="reason" columnRole="description">申请事由</FinanceTableColumn>
          <FinanceTableColumn id="attachments" columnRole="quantity">明细附件数量</FinanceTableColumn>
          <FinanceTableColumn id="invoices" columnRole="quantity">明细可识别发票</FinanceTableColumn>
        </FinanceTableHeader>
        <FinanceTableBody>
          {row.items.length === 0 ? (
            <FinanceTableRow id="empty"><FinanceTableCell columnRole="date">暂无明细</FinanceTableCell><FinanceTableCell columnRole="amount">-</FinanceTableCell><FinanceTableCell columnRole="description">-</FinanceTableCell><FinanceTableCell columnRole="description">-</FinanceTableCell><FinanceTableCell columnRole="description">-</FinanceTableCell><FinanceTableCell columnRole="quantity">-</FinanceTableCell><FinanceTableCell columnRole="quantity">-</FinanceTableCell></FinanceTableRow>
          ) : row.items.map((item, index) => (
            <FinanceTableRow id={`${row.rowId}-item-${index}`} key={`${row.rowId}-item-${index}`}>
              <FinanceTableCell columnRole="date">{item.date}</FinanceTableCell>
              <FinanceTableCell className="settings-table-amount" columnRole="amount">{formatMoney(item.amount)}</FinanceTableCell>
              <FinanceTableCell columnRole="description">{item.content}</FinanceTableCell>
              <FinanceTableCell columnRole="description">{item.projectName}</FinanceTableCell>
              <FinanceTableCell columnRole="description">{item.reason}</FinanceTableCell>
              <FinanceTableCell className="settings-table-amount" columnRole="quantity">{item.attachmentFileCount}</FinanceTableCell>
              <FinanceTableCell className="settings-table-amount" columnRole="quantity">{item.importableInvoiceCount}</FinanceTableCell>
            </FinanceTableRow>
          ))}
        </FinanceTableBody>
      </FinanceTable>
    </div>
  );
}
