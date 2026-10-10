import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Alert, Button, Spinner } from "@heroui/react";
import { ArrowLeft, History, RefreshCw, Search } from "lucide-react";

import AppDialog from "../components/common/AppDialog";
import AppDrawer from "../components/common/AppDrawer";
import { FinanceStatusTag, FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTableRow } from "../components/common/FinanceTable";
import ImportJobDiagnostics from "../components/imports/ImportJobDiagnostics";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSession, useSessionPermissions } from "../contexts/SessionContext";
import { fetchAppHealthDashboard, fetchImportHistory, fetchImportHistoryDetail, withdrawBankTransactionImport } from "../features/appHealth/api";
import type { ImportHistoryQuery, OperationsDashboardImportEvent, OperationsDashboardInventoryBlock, OperationsDashboardPayload, OperationsImportHistoryPayload } from "../features/appHealth/types";

const REFRESH_INTERVAL_MS = 10_000;
const initialQuery: ImportHistoryQuery = { page: 1, page_size: 50, batch_type: "", status: "", search: "", start_date: "", end_date: "" };
const numberFormat = new Intl.NumberFormat("zh-CN");
const timeFormat = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Shanghai" });
const eventStates = {
  awaiting_confirmation: { label: "待确认", tone: "warning" }, queued: { label: "排队中", tone: "warning" },
  processing: { label: "导入中", tone: "warning" }, succeeded: { label: "已完成", tone: "success" },
  partial_success: { label: "部分完成", tone: "warning" }, withdrawn: { label: "已撤回", tone: "neutral" },
  failed: { label: "导入失败", tone: "danger" }, discarded: { label: "已放弃", tone: "neutral" },
  preview_failed: { label: "预览失败", tone: "danger" }, inconsistent: { label: "状态异常", tone: "danger" },
  unknown: { label: "未记录", tone: "neutral" },
} as const;
function count(value: number | null | undefined) { return value == null ? "—" : numberFormat.format(value); }
function timestamp(value: string | null | undefined) { return value ? timeFormat.format(new Date(value)) : "—"; }
function source(block: OperationsDashboardInventoryBlock, key: string) { return block.sources.find(row => row.key === key); }
function Notice({ children, danger = false }: { children: ReactNode; danger?: boolean }) {
  return <Alert className="app-health-notice" status={danger ? "danger" : "accent"} role={danger ? "alert" : "status"}>
    <Alert.Indicator /><Alert.Content><Alert.Description>{children}</Alert.Description></Alert.Content>
  </Alert>;
}
function EventStatus({ status }: { status: string }) {
  const state = eventStates[status as keyof typeof eventStates];
  return <FinanceStatusTag tone={state?.tone ?? "neutral"}>{state?.label ?? "状态未识别"}</FinanceStatusTag>;
}
function Section({ title, id, actions, children }: { title: string; id: string; actions?: ReactNode; children: ReactNode }) {
  return <section className="app-health-section" data-testid={id}>
    <header className="app-health-section__header"><h2 className="app-health-section__title">{title}</h2>{actions}</header>
    <div className="app-health-section__body">{children}</div>
  </section>;
}
function Partition({ title, total, rows }: { title: string; total: number | null; rows: Array<{ label: string; value: number | null | undefined }> }) {
  const known = total !== null && rows.every(row => row.value != null);
  const sum = known ? rows.reduce((value, row) => value + row.value!, 0) : null;
  const difference = sum === null ? null : Math.abs(sum - total!);
  return <div className="app-health-partition" aria-label={title}>
    <div className="app-health-partition__heading"><h4>{title}</h4>
      {difference === 0 ? <span className="app-health-partition__total">合计 {count(sum)} 张</span> : null}
    </div>
    <dl>{rows.map(row => <div key={row.label}><dt>{row.label}</dt><dd>{count(row.value)} <small>张</small></dd></div>)}</dl>
    {difference !== null && difference > 0 ? <p role="alert" className="app-health-partition__warning">统计未闭合 · 差异 {count(difference)} 张</p> : null}
  </div>;
}
function Inventory({ payload }: { payload: OperationsDashboardPayload }) {
  const { bank, invoice, oa } = payload.data_inventory;
  return <div className="app-health-inventory-grid">
    <div className="app-health-invoice" aria-label="发票统计">
      <div className="app-health-invoice__heading"><h3>发票</h3><span>最近同步 {timestamp(invoice.latest_synced_at)}</span></div>
      <div className="app-health-total"><strong>{count(invoice.total_count)}</strong><span>张</span></div>
      <div className="app-health-partitions">
        <Partition title="按类型" total={invoice.total_count} rows={[{ label: "进项发票", value: source(invoice, "input_invoice")?.count }, { label: "销项发票", value: source(invoice, "output_invoice")?.count }]} />
        <Partition title="按导入方式" total={invoice.total_count} rows={[{ label: "手工导入", value: source(invoice, "manual")?.count }, { label: "OA 解析新增", value: source(invoice, "oa_attachment")?.supplementary_count }]} />
      </div>
    </div>
    <div className="app-health-other-inventory">
      <div className="app-health-bank"><h3>银行流水</h3><div className="app-health-total app-health-total--small"><strong>{count(bank.total_count)}</strong><span>笔</span></div><p>最近同步 {timestamp(bank.latest_synced_at)}</p></div>
      <div className="app-health-oa" aria-label="OA 状态"><h3>OA</h3><dl>
        <div><dt>已完成</dt><dd>{count(source(oa, "oa_records_completed")?.count)} <small>条</small></dd></div>
        <div><dt>进行中</dt><dd>{count(source(oa, "oa_records_in_progress")?.count)} <small>条</small></dd></div>
      </dl><p>最近同步 {timestamp(oa.latest_synced_at)}</p></div>
    </div>
  </div>;
}
function EventsTable({ rows, label, loading = false, onDetail }: { rows: OperationsDashboardImportEvent[]; label: string; loading?: boolean; onDetail: (id: string) => void }) {
  return <FinanceTable ariaLabel={label} className="app-health-import-history-table" minWidth={660}>
    <FinanceTableHeader>
      <FinanceTableColumn columnRole="status">类型</FinanceTableColumn><FinanceTableColumn columnRole="description" isRowHeader>文件 / 来源</FinanceTableColumn>
      <FinanceTableColumn columnRole="amount">数量</FinanceTableColumn><FinanceTableColumn columnRole="date">时间</FinanceTableColumn>
      <FinanceTableColumn columnRole="status">状态</FinanceTableColumn><FinanceTableColumn columnRole="action">操作</FinanceTableColumn>
    </FinanceTableHeader>
    <FinanceTableBody renderEmptyState={() => loading ? "正在加载…" : "暂无导入记录"}>
      {rows.map(row => <FinanceTableRow key={row.key} id={row.key}>
        <FinanceTableCell columnRole="status">{row.batch_type === "input_invoice" ? "进项发票" : row.batch_type === "output_invoice" ? "销项发票" : row.label}</FinanceTableCell>
        <FinanceTableCell columnRole="description"><span className="app-health-file-name" title={row.source_name}>{row.source_name || "未记录文件名"}</span><small className="app-health-file-actor">{row.imported_by || "未记录操作人"}</small></FinanceTableCell>
        <FinanceTableCell columnRole="amount">{count(row.count)}</FinanceTableCell><FinanceTableCell columnRole="date">{timestamp(row.imported_at)}</FinanceTableCell>
        <FinanceTableCell columnRole="status"><EventStatus status={row.status} /></FinanceTableCell>
        <FinanceTableCell columnRole="action"><Button size="sm" variant="tertiary" aria-label={`查看 ${row.source_name}`} onPress={() => onDetail(row.batch_id)}>详情</Button></FinanceTableCell>
      </FinanceTableRow>)}
    </FinanceTableBody>
  </FinanceTable>;
}
function EventDetail({ row, onTask, onWithdraw }: { row: OperationsDashboardImportEvent; onTask: (jobId: string) => void; onWithdraw: () => void }) {
  const accountName = row.selected_bank_name || row.detected_bank_name;
  const accountLast4 = row.selected_bank_last4 || row.detected_last4;
  return <div className="app-health-history-detail">
    <div className="app-health-detail-heading"><h3>{row.source_name || "未记录文件名"}</h3><EventStatus status={row.status} /></div>
    <dl className="app-health-detail-facts">
      <div><dt>类型</dt><dd>{row.batch_type === "input_invoice" ? "进项发票" : row.batch_type === "output_invoice" ? "销项发票" : row.label}</dd></div>
      <div><dt>导入数量</dt><dd>{count(row.count)}</dd></div><div><dt>操作人</dt><dd>{row.imported_by || "未记录"}</dd></div>
      <div><dt>导入时间</dt><dd>{timestamp(row.imported_at)}</dd></div>
      {row.batch_type === "bank_transaction" ? <div><dt>银行账户</dt><dd>{[accountName, accountLast4].filter(Boolean).join(" · ") || "未记录"}</dd></div> : null}
      <div><dt>批次编号</dt><dd>{row.batch_id}</dd></div>
    </dl>
    {row.error ? <Notice danger>{row.error}</Notice> : null}
    {row.withdrawal ? <Notice>已撤回 {count(row.withdrawal.withdrawn_count)} 笔 · {row.withdrawal.withdrawn_by} · {timestamp(row.withdrawal.withdrawn_at)}</Notice> : null}
    <div className="app-health-detail-actions">
      {row.job_id ? <Button variant="secondary" onPress={() => onTask(row.job_id!)}>查看任务</Button> : <span>未关联导入任务</span>}
      {row.withdrawal_allowed ? <Button variant="danger" onPress={onWithdraw}>撤回本次流水导入</Button> : null}
    </div>
  </div>;
}
export default function AppHealthOperationsPage() {
  const session = useSession();
  const { canAdminAccess } = useSessionPermissions();
  const { active, activationGeneration } = useOptionalPageActivation("app-health-operations");
  const [payload, setPayload] = useState<OperationsDashboardPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<OperationsImportHistoryPayload | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [query, setQuery] = useState(initialQuery);
  const [draft, setDraft] = useState(initialQuery);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<OperationsDashboardImportEvent | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [task, setTask] = useState<{ jobId?: string; sequence: number } | null>(null);
  const [withdrawTarget, setWithdrawTarget] = useState<OperationsDashboardImportEvent | null>(null);
  const [withdrawing, setWithdrawing] = useState(false);
  const [withdrawError, setWithdrawError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const dashboardRequest = useRef<AbortController | null>(null);
  const historyRequest = useRef<AbortController | null>(null);
  const detailRequest = useRef<AbortController | null>(null);
  const withdrawalBusy = useRef(false);
  const listRef = useRef<HTMLDivElement | null>(null);
  const historyButtonRef = useRef<HTMLButtonElement | null>(null);
  const scrollPosition = useRef(0);

  const loadDashboard = useCallback(async () => {
    if (!canAdminAccess) return;
    dashboardRequest.current?.abort();
    const request = new AbortController(); dashboardRequest.current = request; setLoading(true);
    try {
      const result = await fetchAppHealthDashboard(request.signal);
      if (!request.signal.aborted) { setPayload(result); setLoadError(null); }
    } catch (error) {
      if (!request.signal.aborted) setLoadError(error instanceof Error ? error.message : "数据读取失败。");
    } finally {
      if (dashboardRequest.current === request) { dashboardRequest.current = null; setLoading(false); }
    }
  }, [canAdminAccess]);
  const loadHistory = useCallback(async () => {
    if (!canAdminAccess) return;
    historyRequest.current?.abort();
    const request = new AbortController(); historyRequest.current = request; setHistoryLoading(true);
    try {
      const result = await fetchImportHistory(query, request.signal);
      if (request.signal.aborted) return;
      if (!result.rows.length && query.page > Math.max(result.pagination.total_pages, 1)) {
        setQuery(current => ({ ...current, page: Math.max(result.pagination.total_pages, 1) })); return;
      }
      setHistory(result); setHistoryError(null);
    } catch (error) {
      if (!request.signal.aborted) setHistoryError(error instanceof Error ? error.message : "导入历史读取失败。");
    } finally {
      if (historyRequest.current === request) { historyRequest.current = null; setHistoryLoading(false); }
    }
  }, [canAdminAccess, query]);
  const loadDetail = useCallback(async (id: string) => {
    detailRequest.current?.abort();
    const request = new AbortController(); detailRequest.current = request; setDetailLoading(true);
    try {
      const result = await fetchImportHistoryDetail(id, request.signal);
      if (!request.signal.aborted) { setDetail(result.row); setDetailError(null); }
    } catch (error) {
      if (!request.signal.aborted) setDetailError(error instanceof Error ? error.message : "导入详情读取失败。");
    } finally {
      if (detailRequest.current === request) { detailRequest.current = null; setDetailLoading(false); }
    }
  }, []);
  const refreshAll = useCallback(async () => {
    await Promise.all([loadDashboard(), historyOpen ? loadHistory() : Promise.resolve(), historyOpen && selectedId ? loadDetail(selectedId) : Promise.resolve()]);
  }, [historyOpen, loadDashboard, loadHistory, loadDetail, selectedId]);

  useEffect(() => {
    if (!canAdminAccess || !active) return;
    let stopped = false;
    let timer: number | undefined;
    let generation = 0;
    const poll = async () => {
      if (stopped || document.hidden) return;
      const currentGeneration = generation;
      if (!dashboardRequest.current || dashboardRequest.current.signal.aborted) await loadDashboard();
      if (!stopped && !document.hidden && currentGeneration === generation) timer = window.setTimeout(() => void poll(), REFRESH_INTERVAL_MS);
    };
    const visibility = () => {
      generation++;
      window.clearTimeout(timer);
      if (document.hidden) dashboardRequest.current?.abort(); else void poll();
    };
    void poll(); document.addEventListener("visibilitychange", visibility);
    return () => { stopped = true; window.clearTimeout(timer); document.removeEventListener("visibilitychange", visibility); dashboardRequest.current?.abort(); };
  }, [active, activationGeneration, canAdminAccess, loadDashboard]);
  useEffect(() => {
    if (!historyOpen || task || !active) return;
    if (selectedId) void loadDetail(selectedId); else void loadHistory();
    return () => { historyRequest.current?.abort(); detailRequest.current?.abort(); };
  }, [historyOpen, task, selectedId, active, loadHistory, loadDetail]);
  useLayoutEffect(() => { if (historyOpen && !selectedId && listRef.current) listRef.current.scrollTop = scrollPosition.current; }, [historyOpen, selectedId, task]);
  useEffect(() => () => { dashboardRequest.current?.abort(); historyRequest.current?.abort(); detailRequest.current?.abort(); }, []);

  const openHistory = (id: string | null = null) => {
    // The entry survives table refreshes, so native drawer focus restoration has a stable target.
    historyButtonRef.current?.focus();
    setSelectedId(id); setDetail(null); setDetailError(null); setFeedback(null); setHistoryOpen(true);
  };
  const confirmWithdrawal = async () => {
    if (!withdrawTarget || withdrawalBusy.current) return;
    withdrawalBusy.current = true; setWithdrawing(true); setFeedback(null); setWithdrawError(null);
    try {
      const result = await withdrawBankTransactionImport(withdrawTarget.batch_id, "从导入历史撤回误导入的银行流水");
      setFeedback(`已撤回 ${result.withdrawn_count} 笔银行流水。`); setWithdrawTarget(null);
      await refreshAll();
    } catch (error) { setWithdrawError(error instanceof Error ? error.message : "撤回失败，请核实结果。"); }
    finally { withdrawalBusy.current = false; setWithdrawing(false); }
  };
  if (session.status === "loading") return <div className="app-health-page"><Notice>正在加载。</Notice></div>;
  if (!canAdminAccess) return <div className="app-health-page"><Notice>当前账号没有管理员权限，不能查看 AppHealth 运维状态。</Notice></div>;
  return <div className="app-health-page" data-testid="app-health-page">
    <header className="app-health-header" data-testid="app-health-header"><div className="app-health-heading"><h1 className="app-health-title">数据与导入</h1><p className="app-health-generated-at">最近更新 {timestamp(payload?.generated_at)}</p></div>
      <Button aria-label="刷新" className="app-health-refresh-button" isIconOnly isDisabled={loading} variant="secondary" onPress={() => void refreshAll()}>{loading ? <Spinner size="sm" /> : <RefreshCw size={17} />}</Button>
    </header>
    {loadError ? <Notice danger>{loadError}</Notice> : null}
    {payload ? <div className="app-health-content" aria-busy={loading}>
      <Section title="数据" id="app-health-data"><Inventory payload={payload} /></Section>
      <Section title="最近导入记录" id="app-health-recent-imports" actions={<div className="app-health-section-actions">
        <Button size="sm" variant="tertiary" onPress={() => setTask({ sequence: Date.now() })}>导入任务</Button>
        <Button ref={historyButtonRef} size="sm" variant="secondary" onPress={() => openHistory()}><History size={15} />导入历史</Button>
      </div>}><EventsTable rows={payload.data_inventory.import_events} label="最近导入记录" onDetail={openHistory} /></Section>
    </div> : !loadError ? <Notice>正在加载。</Notice> : null}
    <AppDrawer className="app-health-import-history-drawer" title="导入历史" width="min(960px, calc(100vw - 24px))" open={historyOpen && !task} closeLabel="关闭导入历史" onClose={() => setHistoryOpen(false)} headerActions={selectedId ? <Button size="sm" variant="tertiary" onPress={() => { setSelectedId(null); setDetailError(null); }}><ArrowLeft size={15} />返回列表</Button> : undefined}>
      {feedback ? <Notice>{feedback}</Notice> : null}
      {selectedId ? <div className="app-health-history-view" key={selectedId}>
        {detailLoading ? <Spinner aria-label="正在读取导入详情" size="sm" /> : null}
        {detailError ? <Notice danger>{detailError}<Button variant="tertiary" onPress={() => void loadDetail(selectedId)}>重试</Button></Notice> : null}
        {detail?.batch_id === selectedId && !detailError ? <EventDetail row={detail} onTask={jobId => setTask({ jobId, sequence: Date.now() })} onWithdraw={() => { setWithdrawError(null); setWithdrawTarget(detail); }} /> : null}
      </div> : <>
        <form className="app-health-history-filters" onSubmit={event => { event.preventDefault(); scrollPosition.current = 0; setHistory(null); setQuery({ ...draft, page: 1, page_size: query.page_size }); }}>
          <label>类型<select value={draft.batch_type} onChange={event => setDraft({ ...draft, batch_type: event.target.value })}><option value="">全部类型</option><option value="bank_transaction">银行流水</option><option value="input_invoice">进项发票</option><option value="output_invoice">销项发票</option></select></label>
          <label>状态<select value={draft.status} onChange={event => setDraft({ ...draft, status: event.target.value })}><option value="">全部状态</option>{Object.entries(eventStates).map(([value, state]) => <option value={value} key={value}>{state.label}</option>)}</select></label>
          <label>开始日期<input type="date" value={draft.start_date} onChange={event => setDraft({ ...draft, start_date: event.target.value })} /></label>
          <label>结束日期<input type="date" value={draft.end_date} min={draft.start_date} onChange={event => setDraft({ ...draft, end_date: event.target.value })} /></label>
          <label className="app-health-history-search">文件名<input type="search" maxLength={200} placeholder="搜索文件名" value={draft.search} onChange={event => setDraft({ ...draft, search: event.target.value })} /></label>
          <Button type="submit" variant="primary" isDisabled={historyLoading}><Search size={15} />查询</Button>
        </form>
        {historyError ? <Notice danger>{historyError}<Button variant="tertiary" onPress={() => void loadHistory()}>重试</Button></Notice> : null}
        <div ref={listRef} className="app-health-history-list" onScroll={event => { scrollPosition.current = event.currentTarget.scrollTop; }} aria-busy={historyLoading}>
          <EventsTable rows={history?.rows ?? []} label="导入历史记录" loading={historyLoading} onDetail={id => { setSelectedId(id); setDetail(null); setDetailError(null); }} />
        </div>
        <div className="app-health-history-pagination"><label>每页<select value={query.page_size} onChange={event => { scrollPosition.current = 0; setHistory(null); setQuery({ ...query, page: 1, page_size: Number(event.target.value) }); }}><option value={50}>50 条</option><option value={100}>100 条</option></select></label>
          <span>共 {count(history?.pagination.total)} 条</span><div><Button size="sm" variant="tertiary" isDisabled={historyLoading || query.page <= 1} onPress={() => setQuery({ ...query, page: query.page - 1 })}>上一页</Button>
          <span>{query.page} / {Math.max(history?.pagination.total_pages ?? 1, 1)}</span><Button size="sm" variant="tertiary" isDisabled={historyLoading || !history || query.page >= history.pagination.total_pages} onPress={() => setQuery({ ...query, page: query.page + 1 })}>下一页</Button></div>
        </div>
      </>}
    </AppDrawer>
    {task ? <ImportJobDiagnostics key={task.sequence} initialJobId={task.jobId} refreshToken={payload?.generated_at} onHandled={refreshAll} drawer={{ open: true, onClose: () => { setTask(null); void refreshAll(); } }} /> : null}
    <AppDialog title="撤回流水导入" open={Boolean(withdrawTarget)} isDismissable={!withdrawing} disableEscapeClose={withdrawing} onClose={() => setWithdrawTarget(null)} actions={<><Button variant="secondary" isDisabled={withdrawing} onPress={() => setWithdrawTarget(null)}>取消</Button><Button variant="danger" isDisabled={withdrawing} onPress={() => void confirmWithdrawal()}>{withdrawing ? "正在撤回…" : "确认撤回"}</Button></>}>
      <div className="app-health-import-withdrawal-confirmation">{withdrawError ? <Notice danger>{withdrawError}</Notice> : null}<p>{withdrawTarget?.source_name}</p><p>撤回 {count(withdrawTarget?.count)} 笔本次导入独占创建的银行流水，并解除其关联。</p><Notice>OA、发票及导入/操作审计记录不会删除；需要恢复时请重新导入原文件。</Notice></div>
    </AppDialog>
  </div>;
}
