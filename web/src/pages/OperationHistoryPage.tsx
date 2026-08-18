import { Button, Chip, Input, ListBox, SearchField, Select } from "@heroui/react";
import { RefreshCw, Search } from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

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
import OperationHistoryDetailDrawer from "../components/operations/OperationHistoryDetailDrawer";
import { pageKeyForLabel, pageLabelForKey } from "../app/pageRegistry";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  fetchOperationHistory,
  fetchOperationHistoryActors,
  fetchOperationHistoryDetail,
  type OperationHistoryActor,
  type OperationHistoryFilters,
  type OperationHistoryOperation,
} from "../features/operationHistory/api";
import { formatDateTimeText } from "../features/dateTime";

const EMPTY_FILTERS: OperationHistoryFilters = {};

function formatTime(value?: string | null) {
  return formatDateTimeText(value);
}

function actorLabel(actor: Pick<OperationHistoryOperation, "actor_id" | "actor_name" | "actor_account">) {
  const actorId = String(actor.actor_id ?? "");
  if (!actorId || actorId === "system" || actorId === "database" || actorId.includes("-persistence") || actorId.includes("-repair")) {
    return "系统";
  }
  const name = String(actor.actor_name || "").trim();
  const account = String(actor.actor_account || "").trim();
  return name && account ? `${name} · ${account}` : name || account || actorId;
}

function outcomeView(outcome: string) {
  if (outcome === "success") return { color: "success" as const, label: "成功" };
  if (outcome === "failed") return { color: "danger" as const, label: "失败" };
  if (outcome === "incomplete") return { color: "danger" as const, label: "执行未完成" };
  return { color: "warning" as const, label: "进行中" };
}

export default function OperationHistoryPage() {
  const { active, activationGeneration } = useOptionalPageActivation("operation-history");
  const { canAdminAccess } = useSessionPermissions();
  const [draft, setDraft] = useState<OperationHistoryFilters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<OperationHistoryFilters>(EMPTY_FILTERS);
  const [actors, setActors] = useState<OperationHistoryActor[]>([]);
  const [rows, setRows] = useState<OperationHistoryOperation[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<OperationHistoryOperation | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const listRequest = useRef<AbortController | null>(null);
  const detailRequest = useRef<AbortController | null>(null);

  const load = useCallback(async (cursor?: string | null) => {
    if (!active || !canAdminAccess) return;
    listRequest.current?.abort();
    const controller = new AbortController();
    listRequest.current = controller;
    cursor ? setLoadingMore(true) : setLoading(true);
    setError(null);
    try {
      const result = await fetchOperationHistory(filters, cursor, controller.signal);
      if (listRequest.current !== controller) return;
      setRows((current) => cursor ? [...current, ...result.rows] : result.rows);
      setNextCursor(result.next_cursor);
    } catch (loadError) {
      if (controller.signal.aborted || listRequest.current !== controller) return;
      setError(loadError instanceof Error ? loadError.message : "操作历史加载失败。");
    } finally {
      if (listRequest.current === controller) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [active, canAdminAccess, filters]);

  useEffect(() => {
    void load();
    return () => listRequest.current?.abort();
  }, [activationGeneration, load]);

  useEffect(() => {
    if (!active || !canAdminAccess) return undefined;
    const controller = new AbortController();
    void fetchOperationHistoryActors(controller.signal)
      .then((result) => setActors(result.rows))
      .catch(() => {
        if (!controller.signal.aborted) setActors([]);
      });
    return () => controller.abort();
  }, [activationGeneration, active, canAdminAccess]);

  const submitFilters = (event: FormEvent) => {
    event.preventDefault();
    setFilters({
      search: draft.search?.trim() || undefined,
      actorId: draft.actorId || undefined,
      pageKey: pageKeyForLabel(draft.pageKey) || undefined,
      dateFrom: draft.dateFrom || undefined,
      dateTo: draft.dateTo || undefined,
    });
  };

  const openDetail = async (operation: OperationHistoryOperation) => {
    detailRequest.current?.abort();
    const controller = new AbortController();
    detailRequest.current = controller;
    setSelected(operation);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const detail = await fetchOperationHistoryDetail(operation.operation_key, controller.signal);
      if (detailRequest.current === controller) setSelected(detail.operation);
    } catch (detailLoadError) {
      if (!controller.signal.aborted && detailRequest.current === controller) {
        setDetailError(detailLoadError instanceof Error ? detailLoadError.message : "操作证据加载失败。");
      }
    } finally {
      if (detailRequest.current === controller) setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    detailRequest.current?.abort();
    setSelected(null);
    setDetailLoading(false);
    setDetailError(null);
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
        <SearchField
          aria-label="搜索操作历史"
          onChange={(search) => setDraft((value) => ({ ...value, search }))}
          value={draft.search ?? ""}
        >
          <SearchField.Group>
            <SearchField.SearchIcon />
            <SearchField.Input placeholder="搜索操作、对象或内容" />
            {draft.search ? (
              <SearchField.ClearButton
                aria-label="清除操作历史查询"
                onPress={() => setDraft((value) => ({ ...value, search: undefined }))}
              />
            ) : null}
          </SearchField.Group>
        </SearchField>
        <Select
          aria-label="操作人"
          selectedKey={draft.actorId || "all"}
          onSelectionChange={(key) => setDraft((value) => ({ ...value, actorId: String(key) === "all" ? undefined : String(key) }))}
        >
          <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
          <Select.Popover>
            <ListBox>
              <ListBox.Item id="all" textValue="全部操作人">全部操作人</ListBox.Item>
              {actors.map((actor) => (
                <ListBox.Item id={actor.actor_id} key={actor.actor_id} textValue={actorLabel(actor)}>
                  {actorLabel(actor)}
                </ListBox.Item>
              ))}
            </ListBox>
          </Select.Popover>
        </Select>
        <Input
          aria-label="页面"
          placeholder="页面名称"
          value={draft.pageKey ?? ""}
          onChange={(event) => setDraft((value) => ({ ...value, pageKey: event.target.value }))}
        />
        <Input aria-label="开始日期" type="date" value={draft.dateFrom ?? ""} onChange={(event) => setDraft((value) => ({ ...value, dateFrom: event.target.value }))} />
        <Input aria-label="结束日期" type="date" value={draft.dateTo ?? ""} onChange={(event) => setDraft((value) => ({ ...value, dateTo: event.target.value }))} />
        <Button type="submit" variant="primary"><Search aria-hidden="true" size={16} />查询</Button>
      </form>

      {error ? <StatePanel tone="error" title="操作历史加载失败">{error}</StatePanel> : null}
      {!error && loading ? <StatePanel tone="loading" title="正在加载操作历史" /> : null}
      {!error && !loading && rows.length === 0 ? <StatePanel tone="empty" title="暂无操作记录" /> : null}
      {!error && !loading && rows.length > 0 ? (
        <FinanceTable ariaLabel="操作历史" minWidth={1040}>
          <FinanceTableHeader>
            <FinanceTableColumn id="time" columnRole="date" isRowHeader>时间</FinanceTableColumn>
            <FinanceTableColumn id="actor" columnRole="identity">操作人</FinanceTableColumn>
            <FinanceTableColumn id="page" columnRole="account">页面</FinanceTableColumn>
            <FinanceTableColumn id="action" columnRole="description">操作内容</FinanceTableColumn>
            <FinanceTableColumn id="object" columnRole="identity">对象</FinanceTableColumn>
            <FinanceTableColumn id="outcome" columnRole="status">结果</FinanceTableColumn>
            <FinanceTableColumn id="detail" columnRole="action">详情</FinanceTableColumn>
          </FinanceTableHeader>
          <FinanceTableBody items={rows}>
            {(row) => {
              const outcome = outcomeView(row.outcome);
              return (
                <FinanceTableRow id={row.operation_key} textValue={row.action_label}>
                  <FinanceTableCell columnRole="date">{formatTime(row.started_at)}</FinanceTableCell>
                  <FinanceTableCell columnRole="identity">{actorLabel(row)}</FinanceTableCell>
                  <FinanceTableCell columnRole="account">{pageLabelForKey(row.page_key)}</FinanceTableCell>
                  <FinanceTableCell columnRole="description">{row.action_label}</FinanceTableCell>
                  <FinanceTableCell columnRole="identity">{row.object_label || "业务记录"}</FinanceTableCell>
                  <FinanceTableCell columnRole="status"><Chip color={outcome.color} size="sm">{outcome.label}</Chip></FinanceTableCell>
                  <FinanceTableCell columnRole="action">
                    <Button aria-label={`查看${row.action_label}详情`} size="sm" variant="tertiary" onPress={() => void openDetail(row)}>详情</Button>
                  </FinanceTableCell>
                </FinanceTableRow>
              );
            }}
          </FinanceTableBody>
        </FinanceTable>
      ) : null}

      {nextCursor ? <div className="operation-history-more"><Button isPending={loadingMore} variant="secondary" onPress={() => void load(nextCursor)}>加载更多</Button></div> : null}

      <OperationHistoryDetailDrawer
        error={detailError}
        loading={detailLoading}
        operation={selected}
        onClose={closeDetail}
      />
    </PageScaffold>
  );
}
