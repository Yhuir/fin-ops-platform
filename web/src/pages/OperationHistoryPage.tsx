import { Button, Chip, ComboBox, Input, ListBox, SearchField, Select } from "@heroui/react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { appPageDefinitions, pageLabelForKey } from "../app/pageRegistry";
import { FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTableRow } from "../components/common/FinanceTable";
import PageScaffold from "../components/common/PageScaffold";
import SegmentedControl from "../components/common/SegmentedControl";
import StatePanel from "../components/common/StatePanel";
import OperationHistoryDetailDrawer from "../components/operations/OperationHistoryDetailDrawer";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { formatDateTimeText } from "../features/dateTime";
import { fetchOperationHistory, fetchOperationHistoryActors, fetchOperationHistoryDetail, type OperationHistoryActor, type OperationHistoryFilters, type OperationHistoryOperation } from "../features/operationHistory/api";
import { actorLabel, operationCategories, operationDateRange, operationOutcomes, outcomeView } from "../features/operationHistory/presentation";
import "../features/operationHistory/operationHistory.css";

const pageOptions = [
  { key: "all", label: "全部页面" },
  ...appPageDefinitions.filter(page => page.sidebar && page.pageKey !== "cash").map(page => ({ key: page.pageKey, label: pageLabelForKey(page.pageKey) })),
  { key: "application", label: "系统操作" },
  { key: "database", label: "数据保护" },
];
const timeOptions = [{ key: "all", label: "全部时间" }, { key: "today", label: "今天" }, { key: "7", label: "近 7 天" }, { key: "30", label: "近 30 天" }, { key: "custom", label: "自定义" }];

export default function OperationHistoryPage() {
  const { active, activationGeneration } = useOptionalPageActivation("operation-history");
  const { canAdminAccess } = useSessionPermissions();
  const [draft, setDraft] = useState<OperationHistoryFilters>({});
  const [timeRange, setTimeRange] = useState("all");
  const [query, setQuery] = useState({ filters: {} as OperationHistoryFilters, cursors: [null] as (string | null)[], page: 0, limit: 50, revision: 0 });
  const [actors, setActors] = useState<OperationHistoryActor[]>([]);
  const [actorsRevision, setActorsRevision] = useState(0);
  const [actorsError, setActorsError] = useState<string | null>(null);
  const [rows, setRows] = useState<OperationHistoryOperation[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<OperationHistoryOperation | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const listRequest = useRef<AbortController | null>(null);
  const detailRequest = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    if (!active || !canAdminAccess) return;
    listRequest.current?.abort();
    const controller = new AbortController();
    listRequest.current = controller;
    setLoading(true);
    setRows([]);
    setNextCursor(null);
    setError(null);
    try {
      const result = await fetchOperationHistory(query.filters, query.cursors[query.page], controller.signal, query.limit);
      if (listRequest.current !== controller || controller.signal.aborted) return;
      setRows(result.rows);
      setNextCursor(result.next_cursor);
      scrollRef.current?.scrollTo({ top: 0 });
    } catch (loadError) {
      if (controller.signal.aborted || listRequest.current !== controller) return;
      setError(loadError instanceof Error ? loadError.message : "操作历史加载失败。");
    } finally {
      if (listRequest.current === controller && !controller.signal.aborted) setLoading(false);
    }
  }, [active, canAdminAccess, query]);

  useEffect(() => {
    void load();
    return () => listRequest.current?.abort();
  }, [activationGeneration, load]);

  const loadActors = useCallback(async (signal: AbortSignal) => {
    setActorsError(null);
    try {
      const result = await fetchOperationHistoryActors(signal);
      if (!signal.aborted) setActors(result.rows);
    } catch (actorError) {
      if (!signal.aborted) setActorsError(actorError instanceof Error ? actorError.message : "操作人选项加载失败。");
    }
  }, []);
  useEffect(() => {
    if (!active || !canAdminAccess) return undefined;
    const controller = new AbortController();
    void loadActors(controller.signal);
    return () => controller.abort();
  }, [activationGeneration, active, canAdminAccess, loadActors, actorsRevision]);
  useEffect(() => () => detailRequest.current?.abort(), []);

  const submitFilters = (event: FormEvent) => {
    event.preventDefault();
    setQuery(current => ({ ...current, filters: { ...draft, search: draft.search?.trim() || undefined }, cursors: [null], page: 0, revision: current.revision + 1 }));
  };
  const setDates = (key: string) => {
    setTimeRange(key);
    if (key === "custom") return;
    setDraft(current => ({ ...current, ...(key === "all" ? { dateFrom: undefined, dateTo: undefined } : operationDateRange(key === "today" ? 1 : Number(key))) }));
  };
  const openDetail = async (operation: OperationHistoryOperation) => {
    detailRequest.current?.abort();
    const controller = new AbortController();
    detailRequest.current = controller;
    setSelected(operation);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const result = await fetchOperationHistoryDetail(operation.operation_key, controller.signal);
      if (detailRequest.current === controller && !controller.signal.aborted) setSelected(result.operation);
    } catch (detailLoadError) {
      if (!controller.signal.aborted && detailRequest.current === controller) setDetailError(detailLoadError instanceof Error ? detailLoadError.message : "操作证据加载失败。");
    } finally {
      if (detailRequest.current === controller && !controller.signal.aborted) setDetailLoading(false);
    }
  };
  const closeDetail = () => {
    detailRequest.current?.abort();
    setSelected(null);
    setDetailLoading(false);
    setDetailError(null);
  };

  return (
    <PageScaffold fillViewport className="operation-history-page" title="操作历史">
      <form className="operation-history-query" onSubmit={submitFilters}>
        <SegmentedControl label="操作分类" className="operation-history-categories" value={draft.category || "all"} options={operationCategories}
          onChange={category => setDraft(current => ({ ...current, category: category === "all" ? undefined : category }))} />
        <Select className="operation-history-compact-category" aria-label="操作分类" selectedKey={draft.category || "all"} onSelectionChange={key => setDraft(current => ({ ...current, category: key === "all" ? undefined : String(key) }))}>
          <Select.Trigger className="w-full"><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox>{operationCategories.map(item => <ListBox.Item id={item.key} key={item.key} textValue={item.key === "all" ? "全部分类" : item.label}>{item.key === "all" ? "全部分类" : item.label}</ListBox.Item>)}</ListBox></Select.Popover>
        </Select>
        <div className="operation-history-filters">
          <SearchField aria-label="搜索操作历史" onChange={search => setDraft(current => ({ ...current, search }))} value={draft.search ?? ""}>
            <SearchField.Group><SearchField.SearchIcon /><SearchField.Input placeholder="搜索操作、对象或内容" />
              {draft.search ? <SearchField.ClearButton aria-label="清除操作历史查询" onPress={() => setDraft(current => ({ ...current, search: undefined }))} /> : null}
            </SearchField.Group>
          </SearchField>
          <ComboBox aria-label="页面" selectedKey={draft.pageKey || "all"} onSelectionChange={key => setDraft(current => ({ ...current, pageKey: key === null || key === "all" ? undefined : String(key) }))} menuTrigger="focus">
            <ComboBox.InputGroup><Input aria-label="页面" placeholder="全部页面" /><ComboBox.Trigger /></ComboBox.InputGroup>
            <ComboBox.Popover><ListBox items={pageOptions} renderEmptyState={() => "无匹配页面"}>{page => <ListBox.Item id={page.key} textValue={page.label}>{page.label}</ListBox.Item>}</ListBox></ComboBox.Popover>
          </ComboBox>
          <Select aria-label="操作人" selectedKey={draft.actorId || "all"} onSelectionChange={key => setDraft(current => ({ ...current, actorId: key === "all" ? undefined : String(key) }))}>
            <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox>
              <ListBox.Item id="all" textValue="全部操作人">全部操作人</ListBox.Item>
              {actors.map(actor => <ListBox.Item id={actor.actor_id} key={actor.actor_id} textValue={actorLabel(actor)}>{actorLabel(actor)}</ListBox.Item>)}
            </ListBox></Select.Popover>
          </Select>
          <Select aria-label="操作结果" selectedKey={draft.outcome || "all"} onSelectionChange={key => setDraft(current => ({ ...current, outcome: key === "all" ? undefined : String(key) }))}>
            <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox>
              <ListBox.Item id="all" textValue="全部结果">全部结果</ListBox.Item>
              {operationOutcomes.map(item => <ListBox.Item id={item.key} key={item.key} textValue={item.label}>{item.label}</ListBox.Item>)}
            </ListBox></Select.Popover>
          </Select>
        </div>
        <div className="operation-history-time" data-custom-range={timeRange === "custom"}>
          <SegmentedControl label="时间范围" value={timeRange} options={timeOptions} onChange={setDates} />
          <Select className="operation-history-compact-time" aria-label="时间范围" selectedKey={timeRange} onSelectionChange={key => setDates(String(key))}>
            <Select.Trigger className="w-full"><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox>{timeOptions.map(item => <ListBox.Item id={item.key} key={item.key} textValue={item.label}>{item.label}</ListBox.Item>)}</ListBox></Select.Popover>
          </Select>
          <div className="operation-history-date-inputs">
            <label className="operation-history-date-field"><span>开始日期</span><Input aria-label="开始日期" type="date" value={draft.dateFrom ?? ""} onChange={event => { setTimeRange("custom"); setDraft(current => ({ ...current, dateFrom: event.target.value || undefined })); }} /></label>
            <span aria-hidden="true">—</span>
            <label className="operation-history-date-field"><span>结束日期</span><Input aria-label="结束日期" type="date" min={draft.dateFrom} value={draft.dateTo ?? ""} onChange={event => { setTimeRange("custom"); setDraft(current => ({ ...current, dateTo: event.target.value || undefined })); }} /></label>
          </div>
          <div className="operation-history-query-actions">
            <Button type="button" variant="tertiary" onPress={() => { setDraft({}); setTimeRange("all"); setQuery(current => ({ ...current, filters: {}, cursors: [null], page: 0, revision: current.revision + 1 })); }}>重置</Button>
            <Button type="submit" variant="primary"><Search aria-hidden="true" size={16} />查询</Button>
          </div>
        </div>
      </form>
      {actorsError ? <div role="alert" className="operation-history-option-error">{actorsError}<Button size="sm" variant="tertiary" onPress={() => setActorsRevision(current => current + 1)}>重试操作人</Button></div> : null}
      <div className="finance-page-table-frame operation-history-table-frame" aria-busy={loading}>
        <FinanceTable ariaLabel="操作历史" minWidth={960} scrollMode="contained" scrollRef={scrollRef} selectableText
          footer={<div className="operation-history-pagination">
            <Select className="operation-history-limit" aria-label="每页显示条数" selectedKey={String(query.limit)} onSelectionChange={key => setQuery(current => ({ ...current, limit: Number(key), cursors: [null], page: 0 }))}>
              <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox>{[50, 100, 200].map(limit => <ListBox.Item id={String(limit)} key={limit} textValue={`${limit} 条/页`}>{limit} 条/页</ListBox.Item>)}</ListBox></Select.Popover>
            </Select>
            <span role="status">{loading ? "读取中" : `第 ${query.page + 1} 页 · 本页 ${rows.length} 条`}</span>
            <div className="operation-history-page-actions">
              <Button size="sm" variant="tertiary" isDisabled={loading || query.page === 0} onPress={() => setQuery(current => ({ ...current, page: current.page - 1 }))}><ChevronLeft size={16} aria-hidden="true" />上一页</Button>
              <Button size="sm" variant="tertiary" isDisabled={loading || !nextCursor} onPress={() => setQuery(current => ({ ...current, page: current.page + 1, cursors: [...current.cursors.slice(0, current.page + 1), nextCursor] }))}>下一页<ChevronRight size={16} aria-hidden="true" /></Button>
            </div>
          </div>}>
          <FinanceTableHeader>
            <FinanceTableColumn id="time" columnRole="date" isRowHeader>时间</FinanceTableColumn>
            <FinanceTableColumn id="actor" columnRole="identity">操作人</FinanceTableColumn>
            <FinanceTableColumn id="page" columnRole="account">页面</FinanceTableColumn>
            <FinanceTableColumn id="action" columnRole="description">操作与对象</FinanceTableColumn>
            <FinanceTableColumn id="outcome" columnRole="status">结果</FinanceTableColumn>
            <FinanceTableColumn id="detail" columnRole="action">详情</FinanceTableColumn>
          </FinanceTableHeader>
          <FinanceTableBody items={rows} renderEmptyState={() => error ? <StatePanel tone="error" title="操作历史加载失败">{error}<Button variant="secondary" onPress={() => void load()}>重试读取</Button></StatePanel> : loading ? <span role="status">正在加载操作历史</span> : "暂无操作记录"}>
            {row => {
              const outcome = outcomeView(row.outcome);
              return <FinanceTableRow id={row.operation_key} textValue={row.action_label}>
                <FinanceTableCell columnRole="date">{formatDateTimeText(row.started_at)}</FinanceTableCell>
                <FinanceTableCell columnRole="identity">{actorLabel(row)}</FinanceTableCell>
                <FinanceTableCell columnRole="account">{pageLabelForKey(row.page_key)}</FinanceTableCell>
                <FinanceTableCell columnRole="description"><div className="operation-history-action"><strong>{row.action_label}</strong><span>{row.object_title || row.object_label}</span></div></FinanceTableCell>
                <FinanceTableCell columnRole="status"><Chip color={outcome.color} size="sm">{outcome.label}</Chip></FinanceTableCell>
                <FinanceTableCell columnRole="action"><Button aria-label={`查看${row.action_label}详情`} size="sm" variant="tertiary" onPress={() => void openDetail(row)}>详情</Button></FinanceTableCell>
              </FinanceTableRow>;
            }}
          </FinanceTableBody>
        </FinanceTable>
      </div>
      <OperationHistoryDetailDrawer error={detailError} loading={detailLoading} operation={selected} onClose={closeDetail} onRetry={() => { if (selected) void openDetail(selected); }} />
    </PageScaffold>
  );
}
