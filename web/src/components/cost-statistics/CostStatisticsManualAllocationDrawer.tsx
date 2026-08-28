import { Button, Chip, Input, ToggleButton, ToggleButtonGroup } from "@heroui/react";
import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import {
  fetchCostStatisticsManualAllocations,
  saveCostStatisticsManualAllocation,
} from "../../features/cost-statistics/api";
import type {
  CostStatisticsManualAllocationLine,
  CostStatisticsManualAllocationTask,
} from "../../features/cost-statistics/types";

const MONEY_PATTERN = /^(?:0|[1-9]\d{0,14})\.\d{2}$/;

type AllocationStatus = "pending" | "allocated";

type Props = {
  canSave: boolean;
  onSaved: () => void;
};

function cellKey(unitId: string, sourceKind: string, sourceId: string) {
  return `${unitId}\u001f${sourceKind}\u001f${sourceId}`;
}

function sourceKey(sourceKind: string, sourceId: string) {
  return `${sourceKind}\u001f${sourceId}`;
}

function moneyToCents(value: string) {
  const [whole, fraction] = value.split(".");
  return (BigInt(whole) * 100n) + BigInt(fraction);
}

function formatCents(value: bigint) {
  const sign = value < 0n ? "-" : "";
  const absolute = value < 0n ? -value : value;
  return `${sign}${absolute / 100n}.${(absolute % 100n).toString().padStart(2, "0")}`;
}

function taskLabel(task: CostStatisticsManualAllocationTask) {
  const projects = [...new Set(task.units.map((unit) => unit.projectName).filter(Boolean))];
  const counterparties = [...new Set(task.sources.map((source) => source.counterpartyName).filter(Boolean))];
  return projects[0] || counterparties[0] || "未命名成本关系";
}

function taskMeta(task: CostStatisticsManualAllocationTask) {
  const extraUnits = Math.max(0, task.units.length - 1);
  const extraSources = Math.max(0, task.sources.length - 1);
  const parts = [`净支出 ${task.netCashCost}`];
  if (extraUnits > 0) parts.push(`${task.units.length} 个子付款项`);
  if (extraSources > 0) parts.push(`${task.sources.length} 条流水`);
  return parts.join(" · ");
}

function buildTaskDrafts(task: CostStatisticsManualAllocationTask | undefined) {
  if (!task) return {};
  const saved = new Map(task.allocations.map((line) => [
    cellKey(line.unitId, line.sourceKind, line.sourceId),
    line.amount,
  ]));
  return Object.fromEntries(task.units.flatMap((unit) => (
    task.sources.map((source) => {
      const key = cellKey(unit.unitId, source.sourceKind, source.sourceId);
      return [key, task.status === "allocated" ? saved.get(key) ?? "" : ""];
    })
  )));
}

function draftsEqual(left: Record<string, string>, right: Record<string, string>) {
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  return leftKeys.length === rightKeys.length
    && leftKeys.every((key) => left[key] === right[key]);
}

export default function CostStatisticsManualAllocationDrawer({ canSave, onSaved }: Props) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<AllocationStatus>("pending");
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [tasks, setTasks] = useState<CostStatisticsManualAllocationTask[]>([]);
  const [counts, setCounts] = useState({ pending: 0, allocated: 0 });
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const selectedTask = tasks.find((task) => task.relationCaseId === selectedCaseId) ?? tasks[0];
  const initialDrafts = useMemo(() => buildTaskDrafts(selectedTask), [
    selectedTask?.relationCaseId,
    selectedTask?.sourceFingerprint,
    selectedTask?.status,
    selectedTask?.version,
  ]);
  const hasUnsavedChanges = useMemo(
    () => !draftsEqual(drafts, initialDrafts),
    [drafts, initialDrafts],
  );

  const load = async ({
    targetStatus = status,
    targetQuery = query,
    cursor,
  }: {
    targetStatus?: AllocationStatus;
    targetQuery?: string;
    cursor?: string;
  } = {}) => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    if (cursor) setLoadingMore(true);
    else setLoading(true);
    setError(null);
    try {
      const page = await fetchCostStatisticsManualAllocations({
        status: targetStatus,
        query: targetQuery || undefined,
        cursor,
        pageSize: 50,
        signal: controller.signal,
      });
      if (requestRef.current !== controller) return;
      setTasks((current) => cursor
        ? [...current, ...page.items.filter((item) => !current.some((task) => task.relationCaseId === item.relationCaseId))]
        : page.items);
      setCounts(page.counts);
      setNextCursor(page.nextCursor);
      setSelectedCaseId((current) => (
        cursor || page.items.some((task) => task.relationCaseId === current)
          ? current
          : page.items[0]?.relationCaseId ?? ""
      ));
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : "人工分配任务加载失败。");
      }
    } finally {
      if (requestRef.current === controller) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  };

  useEffect(() => () => requestRef.current?.abort(), []);

  useEffect(() => {
    setDrafts(initialDrafts);
  }, [initialDrafts]);

  const draftSummary = useMemo(() => {
    if (!selectedTask) return { complete: false, valid: false, sourceTotals: new Map<string, bigint>(), unitNets: new Map<string, bigint>() };
    const sourceTotals = new Map<string, bigint>();
    const unitNets = new Map<string, bigint>();
    let complete = true;
    selectedTask.units.forEach((unit) => {
      let unitNet = 0n;
      selectedTask.sources.forEach((source) => {
        const draftKey = cellKey(unit.unitId, source.sourceKind, source.sourceId);
        const value = drafts[draftKey] ?? "";
        if (!MONEY_PATTERN.test(value)) {
          complete = false;
          return;
        }
        const cents = moneyToCents(value);
        const totalKey = sourceKey(source.sourceKind, source.sourceId);
        sourceTotals.set(totalKey, (sourceTotals.get(totalKey) ?? 0n) + cents);
        unitNet += source.sourceKind === "paid_wrong_refund" ? -cents : cents;
      });
      unitNets.set(unit.unitId, unitNet);
    });
    const sourcesClose = selectedTask.sources.every((source) => (
      sourceTotals.get(sourceKey(source.sourceKind, source.sourceId)) === moneyToCents(source.amount)
    ));
    const unitsNonnegative = [...unitNets.values()].every((amount) => amount >= 0n);
    return { complete, valid: complete && sourcesClose && unitsNonnegative, sourceTotals, unitNets };
  }, [drafts, selectedTask]);

  const allocations = useMemo<CostStatisticsManualAllocationLine[]>(() => (
    selectedTask?.units.flatMap((unit) => selectedTask.sources.map((source) => ({
      unitId: unit.unitId,
      sourceId: source.sourceId,
      sourceKind: source.sourceKind,
      amount: drafts[cellKey(unit.unitId, source.sourceKind, source.sourceId)] ?? "",
    }))) ?? []
  ), [drafts, selectedTask]);

  const handleSave = async () => {
    if (!selectedTask || !draftSummary.valid) return;
    setSaving(true);
    setError(null);
    try {
      await saveCostStatisticsManualAllocation({
        relationCaseId: selectedTask.relationCaseId,
        expectedVersion: selectedTask.version,
        sourceFingerprint: selectedTask.sourceFingerprint,
        allocations,
      });
      onSaved();
      await load({ targetStatus: status, targetQuery: query });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "人工分配保存失败。");
    } finally {
      setSaving(false);
    }
  };

  const confirmDiscardDrafts = () => {
    if (!hasUnsavedChanges) return true;
    if (!window.confirm("当前分配尚未保存，继续操作将丢失输入。")) return false;
    setDrafts(initialDrafts);
    return true;
  };

  const applySearch = () => {
    if (saving || !confirmDiscardDrafts()) return;
    const normalized = queryDraft.trim().replace(/\s+/g, " ");
    setQuery(normalized);
    void load({ targetQuery: normalized });
  };

  return (
    <>
      <Button
        aria-label="打开成本人工分配"
        className="cost-page-action cost-manual-allocation-trigger"
        onPress={() => {
          setOpen(true);
          void load();
        }}
        size="sm"
        variant="secondary"
      >
        待分配
        {counts.pending > 0 ? <Chip color="warning" size="sm" variant="soft">{counts.pending}</Chip> : null}
      </Button>
      <AppDrawer
        ariaBusy={loading || saving}
        className="cost-manual-allocation-drawer"
        closeDisabled={saving}
        onClose={() => {
          if (confirmDiscardDrafts()) setOpen(false);
        }}
        open={open}
        title="成本人工分配"
        width="min(780px, 100vw)"
      >
        <div className="cost-manual-allocation-body">
          <p className="cost-manual-allocation-intro">单 OA 单流水自动按流水金额计入；其余关系必须逐条流水、逐个子付款项明确分配。</p>
          <ToggleButtonGroup
            aria-label="成本人工分配状态"
            className="cost-manual-allocation-tabs"
            disallowEmptySelection
            onSelectionChange={(keys) => {
              const next = String([...keys][0] ?? "pending") as AllocationStatus;
              if (next === status || saving || !confirmDiscardDrafts()) return;
              setStatus(next);
              setTasks([]);
              setSelectedCaseId("");
              void load({ targetStatus: next });
            }}
            selectedKeys={new Set([status])}
            selectionMode="single"
          >
            <ToggleButton id="pending">待分配 {counts.pending}</ToggleButton>
            <ToggleButton id="allocated"><ToggleButtonGroup.Separator />人工已分配 {counts.allocated}</ToggleButton>
          </ToggleButtonGroup>
          <div className="cost-manual-allocation-search">
            <Input
              aria-label="搜索人工分配任务"
              onChange={(event) => setQueryDraft(event.currentTarget.value)}
              onKeyDown={(event) => { if (event.key === "Enter") applySearch(); }}
              placeholder="搜索项目、费用、申请人或流水"
              value={queryDraft}
            />
            <Button aria-label="查询人工分配任务" isIconOnly onPress={applySearch} size="sm" variant="secondary">
              <Search aria-hidden="true" size={16} />
            </Button>
          </div>
          {loading ? <div className="cost-manual-allocation-state">正在读取全量配对事实…</div> : null}
          {!loading && tasks.length === 0 ? (
            <div className="cost-manual-allocation-state">{query ? "没有命中当前搜索条件的任务。" : status === "pending" ? "当前没有待人工分配的关系。" : "当前没有人工已分配的关系。"}</div>
          ) : null}
          {tasks.length > 0 ? (
            <div aria-label="人工分配任务" className="cost-manual-allocation-task-strip">
              {tasks.map((task) => (
                <button
                  aria-current={task.relationCaseId === selectedTask?.relationCaseId ? "true" : undefined}
                  className={task.relationCaseId === selectedTask?.relationCaseId ? "is-selected" : ""}
                  disabled={saving}
                  key={task.relationCaseId}
                  onClick={() => {
                    if (task.relationCaseId === selectedTask?.relationCaseId || !confirmDiscardDrafts()) return;
                    setSelectedCaseId(task.relationCaseId);
                  }}
                  type="button"
                >
                  <span><strong>{taskLabel(task)}</strong>{task.status === "stale" ? <Chip color="warning" size="sm" variant="soft">来源已变化</Chip> : null}</span>
                  <small>{taskMeta(task)}</small>
                </button>
              ))}
              {nextCursor ? <Button isPending={loadingMore} onPress={() => void load({ cursor: nextCursor })} size="sm" variant="secondary">加载更多</Button> : null}
            </div>
          ) : null}
          {selectedTask ? (
            <section className="cost-manual-allocation-detail">
              <header>
                <div>
                  <strong>{taskLabel(selectedTask)}</strong>
                  <span>{selectedTask.units.length} 个子付款项 · {selectedTask.sources.length} 条金额来源</span>
                </div>
                <Chip color={selectedTask.status === "allocated" ? "success" : selectedTask.status === "stale" ? "warning" : "default"} size="sm" variant="soft">
                  {selectedTask.status === "allocated" ? "人工已分配" : selectedTask.status === "stale" ? "待重新分配" : "待分配"}
                </Chip>
              </header>
              <div className="cost-manual-allocation-facts">
                <span>OA 子付款项合计<strong>{selectedTask.oaAllocationTotal}</strong></span>
                <span>流水支出<strong>{selectedTask.bankOutflowTotal}</strong></span>
                <span>付错退款<strong>{selectedTask.paidWrongRefundTotal}</strong></span>
                <span>净支出<strong>{selectedTask.netCashCost}</strong></span>
              </div>
              <div className="cost-manual-allocation-matrix-wrap">
                <table className="cost-manual-allocation-matrix">
                  <thead>
                    <tr>
                      <th>OA 子付款项</th>
                      {selectedTask.sources.map((source, index) => (
                        <th key={`${source.sourceKind}-${source.sourceId}`}>
                          <span>{source.sourceKind === "paid_wrong_refund" ? "付错退款" : `流水 ${index + 1}`}</span>
                          <strong>{source.amount}</strong>
                          <small>{source.counterpartyName || "未填写对方户名"} · {source.tradeTime || "时间未知"}</small>
                        </th>
                      ))}
                      <th>净成本</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedTask.units.map((unit) => (
                      <tr key={unit.unitId}>
                        <th scope="row">
                          <strong>{unit.projectName || "未填写项目"}</strong>
                          <span>{unit.expenseType || "未填写费用类型"}</span>
                          <small>{unit.oaApplicant ? `${unit.oaApplicant} · ` : ""}OA 金额 {unit.oaOriginalAmount}</small>
                        </th>
                        {selectedTask.sources.map((source) => {
                          const key = cellKey(unit.unitId, source.sourceKind, source.sourceId);
                          return (
                            <td key={key}>
                              <Input
                                aria-label={`${unit.projectName || "OA 子付款项"}分配至${source.counterpartyName || "流水"}的金额`}
                                disabled={!canSave || !selectedTask.canSave}
                                inputMode="decimal"
                                maxLength={18}
                                onChange={(event) => {
                                  const value = event.currentTarget.value;
                                  setDrafts((current) => ({ ...current, [key]: value }));
                                }}
                                placeholder="0.00"
                                value={drafts[key] ?? ""}
                              />
                            </td>
                          );
                        })}
                        <td className={(draftSummary.unitNets.get(unit.unitId) ?? 0n) < 0n ? "is-invalid" : ""}>
                          {formatCents(draftSummary.unitNets.get(unit.unitId) ?? 0n)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {selectedTask.status === "stale" ? <p className="cost-manual-allocation-warning">关系事实已变化，旧分配不再生效；请按当前子付款项和流水重新填写。</p> : null}
              <div className="cost-manual-allocation-actions">
                <div>
                  {selectedTask.sources.map((source) => (
                    <span className={draftSummary.sourceTotals.get(sourceKey(source.sourceKind, source.sourceId)) === moneyToCents(source.amount) ? "is-balanced" : ""} key={sourceKey(source.sourceKind, source.sourceId)}>
                      {source.sourceKind === "paid_wrong_refund" ? "退款" : "流水"}已填 {formatCents(draftSummary.sourceTotals.get(sourceKey(source.sourceKind, source.sourceId)) ?? 0n)} / {source.amount}
                    </span>
                  ))}
                </div>
                <Button
                  isDisabled={!canSave || !selectedTask.canSave || !draftSummary.valid}
                  isPending={saving}
                  onPress={() => void handleSave()}
                  size="sm"
                  variant="primary"
                >
                  {status === "allocated" ? "保存修改" : "保存分配"}
                </Button>
              </div>
            </section>
          ) : null}
          {error ? <p className="cost-manual-allocation-error" role="alert">{error}</p> : null}
        </div>
      </AppDrawer>
    </>
  );
}
