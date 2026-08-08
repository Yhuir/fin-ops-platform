import { Button, Chip, Input } from "@heroui/react";
import { RefreshCw, Search } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import AppDrawer from "../components/common/AppDrawer";
import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../components/common/FinanceTable";
import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { pageKeyForLabel, pageLabelForKey } from "../app/pageRegistry";
import {
  fetchOperationHistory,
  fetchOperationHistoryEvent,
  type OperationHistoryEvent,
  type OperationHistoryFilters,
} from "../features/operationHistory/api";

const EMPTY_FILTERS: OperationHistoryFilters = {};

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function eventSummary(event: OperationHistoryEvent) {
  const summary = String(event.payload?.summary || event.action || event.event_type || "操作");
  return /^(GET|POST|PUT|PATCH|DELETE) \/api\//.test(summary)
    ? `${pageLabelForKey(event.page_key)}操作`
    : summary;
}

function actorLabel(event: OperationHistoryEvent) {
  if (event.actor_name) return event.actor_name;
  const actorId = String(event.actor_id ?? "");
  return !actorId || actorId === "system" || actorId === "database" || actorId.includes("-persistence") || actorId.includes("-repair")
    ? "系统"
    : actorId;
}

function objectLabel(objectType?: string | null) {
  const labels: Record<string, string> = {
    bank_transactions: "银行流水",
    financial_fact_corrections: "事实修正",
    http_request: "页面操作",
    invoices: "发票",
    workbench_pair_relations: "关联关系",
  };
  return labels[String(objectType ?? "")] ?? "业务数据";
}

function locationLabel(event: OperationHistoryEvent) {
  const location = String(event.operation_location ?? "");
  if (location === "database_trigger") return "数据保护";
  if (location === "service") return "后台处理";
  return pageLabelForKey(event.page_key);
}

function displayJson(value: unknown) {
  if (value === null || value === undefined) return "—";
  return JSON.stringify(value, (key, item) => (
    /(^id$|_id$|fingerprint|raw_payload|source_links|legacy_mongo_id)/i.test(key) ? undefined : item
  ), 2);
}

export default function OperationHistoryPage() {
  const { active, activationGeneration } = useOptionalPageActivation("operation-history");
  const { canAdminAccess } = useSessionPermissions();
  const [draft, setDraft] = useState<OperationHistoryFilters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<OperationHistoryFilters>(EMPTY_FILTERS);
  const [rows, setRows] = useState<OperationHistoryEvent[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<OperationHistoryEvent | null>(null);

  const load = useCallback(async (cursor?: string | null) => {
    if (!active || !canAdminAccess) return;
    cursor ? setLoadingMore(true) : setLoading(true);
    setError(null);
    try {
      const result = await fetchOperationHistory(filters, cursor);
      setRows((current) => cursor ? [...current, ...result.rows] : result.rows);
      setNextCursor(result.next_cursor);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "操作历史加载失败。");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [active, canAdminAccess, filters]);

  useEffect(() => {
    void load();
  }, [activationGeneration, load]);

  const submitFilters = (event: FormEvent) => {
    event.preventDefault();
    setFilters({
      search: draft.search?.trim() || undefined,
      actorId: draft.actorId?.trim() || undefined,
      pageKey: pageKeyForLabel(draft.pageKey) || undefined,
      dateFrom: draft.dateFrom || undefined,
      dateTo: draft.dateTo || undefined,
    });
  };

  const openDetail = async (event: OperationHistoryEvent) => {
    setSelected(event);
    try {
      const detail = await fetchOperationHistoryEvent(event.id);
      setSelected(detail.event);
    } catch {
      // The list payload already contains the safe detail fields.
    }
  };

  return (
    <PageScaffold
      className="operation-history-page"
      title="操作历史"
      actions={(
        <Button variant="secondary" onPress={() => void load()}>
          <RefreshCw aria-hidden="true" size={16} />
          刷新
        </Button>
      )}
    >
      <form className="operation-history-filters" onSubmit={submitFilters}>
        <Input
          aria-label="搜索操作历史"
          placeholder="搜索操作、对象或内容"
          value={draft.search ?? ""}
          onChange={(event) => setDraft((value) => ({ ...value, search: event.target.value }))}
        />
        <Input
          aria-label="操作人"
          placeholder="操作人"
          value={draft.actorId ?? ""}
          onChange={(event) => setDraft((value) => ({ ...value, actorId: event.target.value }))}
        />
        <Input
          aria-label="页面"
          placeholder="页面名称"
          value={draft.pageKey ?? ""}
          onChange={(event) => setDraft((value) => ({ ...value, pageKey: event.target.value }))}
        />
        <Input
          aria-label="开始日期"
          type="date"
          value={draft.dateFrom ?? ""}
          onChange={(event) => setDraft((value) => ({ ...value, dateFrom: event.target.value }))}
        />
        <Input
          aria-label="结束日期"
          type="date"
          value={draft.dateTo ?? ""}
          onChange={(event) => setDraft((value) => ({ ...value, dateTo: event.target.value }))}
        />
        <Button type="submit" variant="primary">
          <Search aria-hidden="true" size={16} />
          查询
        </Button>
      </form>

      {error ? <StatePanel tone="error" title="操作历史加载失败">{error}</StatePanel> : null}
      {!error && loading ? <StatePanel tone="loading" title="正在加载操作历史" /> : null}
      {!error && !loading && rows.length === 0 ? <StatePanel tone="empty" title="暂无操作记录" /> : null}
      {!error && !loading && rows.length > 0 ? (
        <FinanceTable ariaLabel="操作历史" minWidth={980}>
          <FinanceTableHeader>
            <FinanceTableColumn id="time" columnRole="date" isRowHeader>时间</FinanceTableColumn>
            <FinanceTableColumn id="actor" columnRole="identity">操作人</FinanceTableColumn>
            <FinanceTableColumn id="page" columnRole="account">页面</FinanceTableColumn>
            <FinanceTableColumn id="action" columnRole="description">操作内容</FinanceTableColumn>
            <FinanceTableColumn id="object" columnRole="identity">对象</FinanceTableColumn>
            <FinanceTableColumn id="outcome" columnRole="status">结果</FinanceTableColumn>
          </FinanceTableHeader>
          <FinanceTableBody items={rows}>
            {(row) => (
              <FinanceTableRow id={row.id} textValue={eventSummary(row)}>
                <FinanceTableCell columnRole="date">{formatTime(row.occurred_at)}</FinanceTableCell>
                <FinanceTableCell columnRole="identity">{actorLabel(row)}</FinanceTableCell>
                <FinanceTableCell columnRole="account">{pageLabelForKey(row.page_key)}</FinanceTableCell>
                <FinanceTableCell columnRole="description">
                  <Button
                    aria-label={`查看${eventSummary(row)}`}
                    className="operation-history-action"
                    onPress={() => void openDetail(row)}
                    variant="tertiary"
                  >
                    {eventSummary(row)}
                  </Button>
                </FinanceTableCell>
                <FinanceTableCell columnRole="identity">{objectLabel(row.object_type)}</FinanceTableCell>
                <FinanceTableCell columnRole="status">
                  <Chip color={row.outcome === "success" ? "success" : row.outcome === "failed" ? "danger" : "warning"} size="sm">
                    {row.outcome === "success" ? "成功" : row.outcome === "failed" ? "失败" : "进行中"}
                  </Chip>
                </FinanceTableCell>
              </FinanceTableRow>
            )}
          </FinanceTableBody>
        </FinanceTable>
      ) : null}

      {nextCursor ? (
        <div className="operation-history-more">
          <Button isPending={loadingMore} variant="secondary" onPress={() => void load(nextCursor)}>加载更多</Button>
        </div>
      ) : null}

      <AppDrawer open={selected !== null} title="操作详情" width={560} onClose={() => setSelected(null)}>
        {selected ? (
          <div className="operation-history-detail">
            <dl>
              <div><dt>时间</dt><dd>{formatTime(selected.occurred_at)}</dd></div>
              <div><dt>操作人</dt><dd>{actorLabel(selected)}</dd></div>
              <div><dt>页面</dt><dd>{pageLabelForKey(selected.page_key)}</dd></div>
              <div><dt>位置</dt><dd>{locationLabel(selected)}</dd></div>
              <div><dt>内容</dt><dd>{eventSummary(selected)}</dd></div>
              <div><dt>原因</dt><dd>{selected.reason || "—"}</dd></div>
            </dl>
            <section><h3>操作前</h3><pre>{displayJson(selected.payload?.before)}</pre></section>
            <section><h3>操作后</h3><pre>{displayJson(selected.payload?.after)}</pre></section>
          </div>
        ) : null}
      </AppDrawer>
    </PageScaffold>
  );
}
