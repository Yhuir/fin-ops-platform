import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { useAppChrome } from "../../contexts/AppChromeContext";
import { formatMoney } from "../../features/money";
import {
  importManualOaRows,
  refreshManualOaImportAttachments,
  searchManualOaImports,
} from "../../features/workbench/api";
import type { OaManualSearchFilters, OaManualSearchRow } from "../../features/workbench/types";

const formTypeOptions = [
  { value: "payment_request", label: "支付申请" },
  { value: "expense_claim", label: "日常报销" },
];

const statusOptions = [
  { value: "completed", label: "已完成" },
  { value: "in_progress", label: "进行中" },
];

const oaImportCompletionStatusMs = 1200;
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
          <input value={query} type="search" onChange={(event) => setQuery(event.currentTarget.value)} />
        </label>
        <label className="settings-field settings-field--date">
          <span>开始日期</span>
          <input value={dateFrom} type="date" onChange={(event) => setDateFrom(event.currentTarget.value)} />
        </label>
        <label className="settings-field settings-field--date">
          <span>结束日期</span>
          <input value={dateTo} type="date" onChange={(event) => setDateTo(event.currentTarget.value)} />
        </label>
      </div>

      <div className="oa-manual-import__filter-groups">
        <fieldset className="settings-checkbox-group">
          <legend>搜索表单类型</legend>
          <div className="settings-checkbox-list settings-checkbox-list--inline">
            {formTypeOptions.map((option) => (
              <label className="settings-checkbox-row" key={option.value}>
                <input
                  checked={formTypes.includes(option.value)}
                  type="checkbox"
                  onChange={() => setFormTypes((current) => nextToggledList(option.value, current))}
                />
                <span>搜索{option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="settings-checkbox-group">
          <legend>搜索流程状态</legend>
          <div className="settings-checkbox-list settings-checkbox-list--inline">
            {statusOptions.map((option) => (
              <label className="settings-checkbox-row" key={option.value}>
                <input
                  checked={statuses.includes(option.value)}
                  type="checkbox"
                  onChange={() => setStatuses((current) => nextToggledList(option.value, current))}
                />
                <span>搜索{option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      <div className="oa-manual-import__actions">
        <button className="settings-primary-button" disabled={isLoading} type="button" onClick={() => void runSearch(0, pageSize)}>
          搜索
        </button>
        <button
          className="settings-secondary-button"
          type="button"
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
        </button>
        <button className="settings-secondary-button" type="button" onClick={() => setSelectedRows({})}>
          清空选择
        </button>
        <button
          className="settings-primary-button"
          disabled={selectedImportableRows.length === 0 || isImporting}
          type="button"
          onClick={() => void handleImportSelected()}
        >
          {isImporting ? "正在导入" : "导入已选OA项"}
        </button>
      </div>

      {error ? <div className="settings-inline-alert settings-inline-alert--error" role="alert">{error}</div> : null}

      <div className="settings-native-table-shell settings-native-table-shell--scroll">
        <table className="settings-native-table oa-manual-import__table" aria-label="OA全量搜索导入结果">
          <thead>
            <tr>
              <th scope="col">
                <input
                  aria-label="选择当前页可导入OA"
                  checked={allCurrentPageImportableSelected}
                  disabled={importablePageRows.length === 0}
                  type="checkbox"
                  ref={(element) => {
                    if (element) {
                      element.indeterminate = someCurrentPageImportableSelected;
                    }
                  }}
                  onChange={toggleCurrentPageImportable}
                />
              </th>
              <th scope="col" aria-label="展开明细" />
              <th scope="col">OA编号</th>
              <th scope="col">申请人</th>
              <th scope="col">申请日期</th>
              <th scope="col">表单类型</th>
              <th scope="col">流程状态</th>
              <th scope="col">项目摘要</th>
              <th scope="col">整单金额</th>
              <th scope="col">附件总数</th>
              <th scope="col">可导入发票</th>
              <th scope="col">未识别附件</th>
              <th scope="col">导入状态</th>
              <th scope="col">禁用原因</th>
              <th scope="col">操作</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td className="settings-table-empty" colSpan={15}>正在搜索OA</td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td className="settings-table-empty" colSpan={15}>
                  {hasSearched ? "没有符合条件的 OA" : "输入条件后点击搜索"}
                </td>
              </tr>
            ) : rows.map((row) => {
              const expanded = expandedRows[row.rowId] === true;
              return (
                <Fragment key={row.rowId}>
                  <tr className={selectedRows[row.rowId] ? "settings-native-table-row--selected" : undefined}>
                    <td>
                      <input
                        aria-label={`选择 OA ${row.rowId}`}
                        checked={Boolean(selectedRows[row.rowId])}
                        disabled={!row.canImport}
                        title={row.canImport ? undefined : row.disabledReason || "不可导入"}
                        type="checkbox"
                        onChange={() => toggleRow(row)}
                      />
                    </td>
                    <td>
                      <button
                        aria-label={`${expanded ? "收起" : "展开"} OA ${row.rowId} 明细`}
                        className="settings-icon-button"
                        type="button"
                        onClick={() => setExpandedRows((current) => ({ ...current, [row.rowId]: !expanded }))}
                      >
                        {expanded ? <ChevronDown aria-hidden="true" size={16} /> : <ChevronRight aria-hidden="true" size={16} />}
                      </button>
                    </td>
                    <td>{row.oaNo || row.rowId}</td>
                    <td>{row.applicant}</td>
                    <td>{row.applicationDate}</td>
                    <td>{row.formTypeLabel}</td>
                    <td>
                      <span className={`settings-selected-tag settings-selected-tag--${row.status === "completed" ? "success" : "warning"}`}>
                        {row.statusLabel}
                      </span>
                    </td>
                    <td className="oa-manual-import__project">
                      <strong>{row.projectName}</strong>
                      <small>{row.reason}</small>
                    </td>
                    <td className="settings-table-amount">{formatMoney(row.amount)}</td>
                    <td className="settings-table-amount">{row.attachmentFileCount}</td>
                    <td className="settings-table-amount">{row.importableInvoiceCount}</td>
                    <td className="settings-table-amount">{row.unrecognizedAttachmentCount}</td>
                    <td>
                      <span className={`settings-selected-tag settings-selected-tag--${importStatusTone(row)}`}>
                        {importStatusLabel(row)}
                      </span>
                    </td>
                    <td>{row.canImport ? "" : row.disabledReason || "不可导入"}</td>
                    <td>
                      <button
                        aria-label={`刷新 OA ${row.rowId} 附件解析`}
                        className="settings-icon-button"
                        disabled={busyRowId === row.rowId}
                        title="刷新附件解析"
                        type="button"
                        onClick={() => void handleRefresh(row)}
                      >
                        <RefreshCw aria-hidden="true" size={16} />
                      </button>
                    </td>
                  </tr>
                  {expanded ? (
                    <tr>
                      <td className="oa-manual-import__detail-cell" colSpan={15}>
                        <table className="settings-native-table oa-manual-import__detail-table" aria-label={`OA ${row.rowId} 明细`}>
                          <thead>
                            <tr>
                              <th scope="col">明细日期</th>
                              <th scope="col">金额</th>
                              <th scope="col">费用/付款内容</th>
                              <th scope="col">项目名称</th>
                              <th scope="col">申请事由</th>
                              <th scope="col">明细附件数量</th>
                              <th scope="col">明细可识别发票</th>
                            </tr>
                          </thead>
                          <tbody>
                            {row.items.length === 0 ? (
                              <tr>
                                <td className="settings-table-empty" colSpan={7}>暂无明细</td>
                              </tr>
                            ) : row.items.map((item, index) => (
                              <tr key={`${row.rowId}-item-${index}`}>
                                <td>{item.date}</td>
                                <td className="settings-table-amount">{formatMoney(item.amount)}</td>
                                <td>{item.content}</td>
                                <td>{item.projectName}</td>
                                <td>{item.reason}</td>
                                <td className="settings-table-amount">{item.attachmentFileCount}</td>
                                <td className="settings-table-amount">{item.importableInvoiceCount}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="settings-table-pagination">
        <span>{currentFrom}-{currentTo} / {total}</span>
        <label>
          每页行数
          <select
            value={pageSize}
            onChange={(event) => {
              const nextPageSize = Number.parseInt(event.currentTarget.value, 10);
              if (hasSearched) {
                void runSearch(0, nextPageSize);
              } else {
                setPage(0);
                setPageSize(nextPageSize);
              }
            }}
          >
            {[10, 20, 50, 100].map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        </label>
        <div className="settings-table-pagination__actions">
          <button
            className="settings-secondary-button"
            disabled={page <= 0}
            type="button"
            onClick={() => {
              const nextPage = Math.max(0, page - 1);
              if (hasSearched) {
                void runSearch(nextPage, pageSize);
              } else {
                setPage(nextPage);
              }
            }}
          >
            上一页
          </button>
          <button
            className="settings-secondary-button"
            disabled={page + 1 >= totalPages}
            type="button"
            onClick={() => {
              const nextPage = Math.min(totalPages - 1, page + 1);
              if (hasSearched) {
                void runSearch(nextPage, pageSize);
              } else {
                setPage(nextPage);
              }
            }}
          >
            下一页
          </button>
        </div>
      </div>
    </section>
  );
}
