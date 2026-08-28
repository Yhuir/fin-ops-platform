import {
  Button,
  Checkbox,
  Chip,
  Disclosure,
  DisclosureGroup,
  Input,
  TextArea,
  ToggleButton,
  ToggleButtonGroup,
} from "@heroui/react";
import type { Key } from "@heroui/react";
import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import {
  fetchCostStatisticsManualAllocations,
  saveCostStatisticsManualAllocation,
} from "../../features/cost-statistics/api";
import { formatDateTimeText } from "../../features/dateTime";
import type {
  CostStatisticsManualAllocationLine,
  CostStatisticsManualAllocationTask,
  CostStatisticsManualAllocationUnit,
} from "../../features/cost-statistics/types";

const MONEY_PATTERN = /^(?:0|[1-9]\d{0,14})\.\d{2}$/;

type AllocationStatus = "pending" | "allocated";

type Props = {
  canSave: boolean;
  onSaved: () => void;
};

type TaskDraft = {
  allocations: Record<string, string>;
  hasNonCostAmount: boolean;
  nonCostAmount: string;
  nonCostReason: string;
};

type DraftSummary = {
  allocatedCents: bigint;
  valid: boolean;
  message: string;
};

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
  if (projects.length > 1) return `${projects[0]} 等 ${projects.length} 个项目`;
  if (projects.length === 1) return projects[0];
  const counterparty = task.bankEvents.find((event) => event.counterpartyName)?.counterpartyName;
  return counterparty || "未填写业务名称";
}

function taskStatusLabel(task: CostStatisticsManualAllocationTask) {
  if (task.status === "allocated") return "人工已分配";
  if (task.status === "stale") return "待重新分配";
  return "待分配";
}

function buildTaskDraft(task: CostStatisticsManualAllocationTask): TaskDraft {
  const saved = new Map(task.allocations.map((line) => [line.unitId, line.amount]));
  const allocated = task.status === "allocated";
  const nonCostAmount = allocated ? task.nonCostAmount : "";
  return {
    allocations: Object.fromEntries(task.units.map((unit) => [
      unit.unitId,
      allocated ? saved.get(unit.unitId) ?? "" : "",
    ])),
    hasNonCostAmount: allocated && MONEY_PATTERN.test(nonCostAmount) && moneyToCents(nonCostAmount) > 0n,
    nonCostAmount,
    nonCostReason: allocated ? task.nonCostReason : "",
  };
}

function taskDrafts(tasks: CostStatisticsManualAllocationTask[]) {
  return Object.fromEntries(tasks.map((task) => [task.relationCaseId, buildTaskDraft(task)]));
}

function draftsEqual(left: TaskDraft | undefined, right: TaskDraft) {
  if (!left) return true;
  const leftKeys = Object.keys(left.allocations);
  const rightKeys = Object.keys(right.allocations);
  return left.hasNonCostAmount === right.hasNonCostAmount
    && left.nonCostAmount === right.nonCostAmount
    && left.nonCostReason === right.nonCostReason
    && leftKeys.length === rightKeys.length
    && leftKeys.every((key) => left.allocations[key] === right.allocations[key]);
}

function summarizeDraft(task: CostStatisticsManualAllocationTask, draft: TaskDraft): DraftSummary {
  const values = task.units.map((unit) => draft.allocations[unit.unitId] ?? "");
  const allocatedCents = values
    .filter((value) => MONEY_PATTERN.test(value))
    .reduce((total, value) => total + moneyToCents(value), 0n);
  const netOutflowCents = moneyToCents(task.netOutflowTotal);
  if (values.some((value) => !MONEY_PATTERN.test(value))) {
    return {
      allocatedCents,
      valid: false,
      message: "每项分配金额均需填写为非负数，并保留两位小数。",
    };
  }
  let nonCostCents = 0n;
  if (draft.hasNonCostAmount) {
    if (!MONEY_PATTERN.test(draft.nonCostAmount) || moneyToCents(draft.nonCostAmount) <= 0n) {
      return { allocatedCents, valid: false, message: "不计入成本金额必须大于 0.00，并保留两位小数。" };
    }
    if (!draft.nonCostReason.trim()) {
      return { allocatedCents, valid: false, message: "请填写不计入成本说明。" };
    }
    nonCostCents = moneyToCents(draft.nonCostAmount);
  }
  const totalCents = allocatedCents + nonCostCents;
  return {
    allocatedCents,
    valid: totalCents === netOutflowCents,
    message: totalCents === netOutflowCents
      ? `已分配 ${formatCents(allocatedCents)} / 净支出 ${task.netOutflowTotal}`
      : `分配金额${draft.hasNonCostAmount ? "与不计入成本金额合计" : "合计"} ${formatCents(totalCents)}，需等于净支出 ${task.netOutflowTotal}。`,
  };
}

function unitTitle(unit: CostStatisticsManualAllocationUnit) {
  return unit.projectName || unit.expenseContent || unit.expenseType || "未填写 OA 项";
}

function isPaymentApplication(unit: CostStatisticsManualAllocationUnit) {
  return unit.oaApplyType === "支付申请";
}

export default function CostStatisticsManualAllocationDrawer({ canSave, onSaved }: Props) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<AllocationStatus>("pending");
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [tasks, setTasks] = useState<CostStatisticsManualAllocationTask[]>([]);
  const [counts, setCounts] = useState({ pending: 0, allocated: 0 });
  const [draftsByCase, setDraftsByCase] = useState<Record<string, TaskDraft>>({});
  const [expandedKeys, setExpandedKeys] = useState<Set<Key>>(new Set());
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | undefined>();
  const [savingCaseIds, setSavingCaseIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [taskErrors, setTaskErrors] = useState<Record<string, string>>({});
  const requestRef = useRef<AbortController | null>(null);
  const countRequestRef = useRef<AbortController | null>(null);

  const hasUnsavedChanges = useMemo(() => tasks.some((task) => (
    !draftsEqual(draftsByCase[task.relationCaseId], buildTaskDraft(task))
  )), [draftsByCase, tasks]);

  const confirmDiscardDrafts = () => {
    if (!hasUnsavedChanges) return true;
    return window.confirm("当前仍有未保存的分配，继续操作将丢失输入。");
  };

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
    if (cursor) {
      setLoadingMore(true);
      setLoadMoreError(null);
    } else {
      setLoading(true);
      setError(null);
      setLoadMoreError(null);
    }
    try {
      const page = await fetchCostStatisticsManualAllocations({
        status: targetStatus,
        query: targetQuery || undefined,
        cursor,
        pageSize: 50,
        signal: controller.signal,
      });
      if (requestRef.current !== controller) return;
      if (cursor) {
        setTasks((current) => [
          ...current,
          ...page.items.filter((item) => !current.some((task) => task.relationCaseId === item.relationCaseId)),
        ]);
        setDraftsByCase((current) => {
          const next = { ...current };
          page.items.forEach((task) => {
            if (!next[task.relationCaseId]) next[task.relationCaseId] = buildTaskDraft(task);
          });
          return next;
        });
      } else {
        setTasks(page.items);
        setDraftsByCase(taskDrafts(page.items));
        setExpandedKeys(new Set());
        setTaskErrors({});
      }
      setCounts(page.counts);
      setNextCursor(page.nextCursor);
    } catch (caught) {
      if (!controller.signal.aborted) {
        const message = caught instanceof Error ? caught.message : "人工分配任务加载失败。";
        if (cursor) setLoadMoreError(message);
        else setError(message);
      }
    } finally {
      if (requestRef.current === controller) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    countRequestRef.current = controller;
    void fetchCostStatisticsManualAllocations({
      status: "pending",
      pageSize: 1,
      signal: controller.signal,
    }).then((page) => {
      if (countRequestRef.current === controller) setCounts(page.counts);
    }).catch((caught) => {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : "人工分配任务数量加载失败。");
      }
    });
    return () => {
      controller.abort();
      requestRef.current?.abort();
    };
  }, []);

  const applySearch = () => {
    if (savingCaseIds.size > 0 || !confirmDiscardDrafts()) return;
    const normalized = queryDraft.trim().replace(/\s+/g, " ");
    setQuery(normalized);
    void load({ targetQuery: normalized });
  };

  const updateDraft = (relationCaseId: string, updater: (draft: TaskDraft) => TaskDraft) => {
    setDraftsByCase((current) => ({
      ...current,
      [relationCaseId]: updater(current[relationCaseId]),
    }));
    setTaskErrors((current) => {
      if (!current[relationCaseId]) return current;
      const next = { ...current };
      delete next[relationCaseId];
      return next;
    });
  };

  const handleSave = async (task: CostStatisticsManualAllocationTask) => {
    const draft = draftsByCase[task.relationCaseId];
    if (!draft) return;
    const summary = summarizeDraft(task, draft);
    if (!summary.valid) return;
    setSavingCaseIds((current) => new Set(current).add(task.relationCaseId));
    setTaskErrors((current) => {
      const next = { ...current };
      delete next[task.relationCaseId];
      return next;
    });
    try {
      const allocations: CostStatisticsManualAllocationLine[] = task.units.map((unit) => ({
        unitId: unit.unitId,
        amount: draft.allocations[unit.unitId],
      }));
      const saved = await saveCostStatisticsManualAllocation({
        relationCaseId: task.relationCaseId,
        expectedVersion: task.version,
        sourceFingerprint: task.sourceFingerprint,
        allocations,
        nonCostAmount: draft.hasNonCostAmount ? draft.nonCostAmount : "0.00",
        nonCostReason: draft.hasNonCostAmount ? draft.nonCostReason.trim() : "",
      });
      onSaved();
      if (status === "pending") {
        setTasks((current) => current.filter((item) => item.relationCaseId !== task.relationCaseId));
        setDraftsByCase((current) => {
          const next = { ...current };
          delete next[task.relationCaseId];
          return next;
        });
        setExpandedKeys((current) => {
          const next = new Set(current);
          next.delete(task.relationCaseId);
          return next;
        });
        setCounts((current) => ({
          pending: Math.max(0, current.pending - 1),
          allocated: current.allocated + 1,
        }));
      } else {
        setTasks((current) => current.map((item) => (
          item.relationCaseId === saved.relationCaseId ? saved : item
        )));
        setDraftsByCase((current) => ({
          ...current,
          [saved.relationCaseId]: buildTaskDraft(saved),
        }));
      }
    } catch (caught) {
      setTaskErrors((current) => ({
        ...current,
        [task.relationCaseId]: caught instanceof Error ? caught.message : "人工分配保存失败。",
      }));
    } finally {
      setSavingCaseIds((current) => {
        const next = new Set(current);
        next.delete(task.relationCaseId);
        return next;
      });
    }
  };

  const headerActions = (
    <ToggleButtonGroup
      aria-label="成本人工分配状态"
      className="cost-manual-allocation-tabs"
      disallowEmptySelection
      onSelectionChange={(keys) => {
        const next = String([...keys][0] ?? "pending") as AllocationStatus;
        if (next === status || savingCaseIds.size > 0 || !confirmDiscardDrafts()) return;
        setStatus(next);
        setTasks([]);
        setDraftsByCase({});
        void load({ targetStatus: next });
      }}
      selectedKeys={new Set([status])}
      selectionMode="single"
    >
      <ToggleButton id="pending">待分配 {counts.pending}</ToggleButton>
      <ToggleButton id="allocated"><ToggleButtonGroup.Separator />人工已分配 {counts.allocated}</ToggleButton>
    </ToggleButtonGroup>
  );

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
        ariaBusy={loading || savingCaseIds.size > 0}
        className="cost-manual-allocation-drawer"
        closeDisabled={savingCaseIds.size > 0}
        headerActions={headerActions}
        onClose={() => {
          if (confirmDiscardDrafts()) setOpen(false);
        }}
        open={open}
        title="成本人工分配"
        width="min(880px, 100vw)"
      >
        <div className="cost-manual-allocation-body">
          <div className="cost-manual-allocation-search">
            <Input
              aria-label="搜索人工分配任务"
              onChange={(event) => setQueryDraft(event.currentTarget.value)}
              onKeyDown={(event) => { if (event.key === "Enter") applySearch(); }}
              placeholder="搜索项目、费用或申请人"
              value={queryDraft}
            />
            <Button aria-label="查询人工分配任务" isIconOnly onPress={applySearch} size="sm" variant="secondary">
              <Search aria-hidden="true" size={16} />
            </Button>
          </div>
          {error ? <p className="cost-manual-allocation-error" role="alert">{error}</p> : null}
          {loading ? <div className="cost-manual-allocation-state">正在读取配对事实…</div> : null}
          {!loading && !error && tasks.length === 0 ? (
            <div className="cost-manual-allocation-state">
              {query
                ? "没有命中当前搜索条件的任务。"
                : status === "pending"
                  ? "当前没有待人工分配的关系。"
                  : "当前没有人工已分配的关系。"}
            </div>
          ) : null}
          {!loading && !error && tasks.length > 0 ? (
            <DisclosureGroup
              allowsMultipleExpanded
              className="cost-manual-allocation-list"
              expandedKeys={expandedKeys}
              onExpandedChange={setExpandedKeys}
            >
              {tasks.map((task) => {
                const expanded = expandedKeys.has(task.relationCaseId);
                const draft = draftsByCase[task.relationCaseId] ?? buildTaskDraft(task);
                const summary = summarizeDraft(task, draft);
                const saving = savingCaseIds.has(task.relationCaseId);
                return (
                  <Disclosure className="cost-manual-allocation-group" id={task.relationCaseId} key={task.relationCaseId}>
                    <Disclosure.Heading className="cost-manual-allocation-heading">
                      <Button
                        aria-label={`${expanded ? "收起" : "展开"}${taskLabel(task)}人工分配`}
                        className="cost-manual-allocation-group-trigger"
                        fullWidth
                        slot="trigger"
                        variant="tertiary"
                      >
                        <span className="cost-manual-allocation-group-title">
                          <strong title={taskLabel(task)}>{taskLabel(task)}</strong>
                          <span>OA 合计 <b>{task.oaTotal}</b></span>
                          <span>净支出 <b>{task.netOutflowTotal}</b></span>
                          <Chip
                            color={task.status === "allocated" ? "success" : task.status === "stale" ? "warning" : "default"}
                            size="sm"
                            variant="soft"
                          >
                            {taskStatusLabel(task)}
                          </Chip>
                          <Disclosure.Indicator className="cost-manual-allocation-indicator" />
                        </span>
                      </Button>
                    </Disclosure.Heading>
                    <Disclosure.Content>
                      <Disclosure.Body className="cost-manual-allocation-detail">
                        {expanded ? (
                          <>
                            <div className="cost-manual-allocation-facts">
                              <span>OA 合计<strong>{task.oaTotal}</strong></span>
                              <span>
                                净支出<strong>{task.netOutflowTotal}</strong>
                                <small>流水支出 {task.grossOutflowTotal} · 付错退款 {task.wrongPaymentRefundTotal}</small>
                              </span>
                            </div>
                            <section className="cost-manual-allocation-sources" aria-label="流水明细">
                              <h3>流水</h3>
                              <div>
                                {task.bankEvents.map((event, index) => (
                                  <article key={`${event.eventKind}:${event.transactionId}`}>
                                    <strong>{event.eventKind === "wrong_payment_refund" ? `付错退款 ${index + 1}` : `流水 ${index + 1}`} · {event.amount}</strong>
                                    <span>{event.counterpartyName || "未填写对方户名"}</span>
                                    <span>{formatDateTimeText(event.tradeTime)}</span>
                                    {event.summary ? <small>{event.summary}</small> : null}
                                    {event.tags.length > 0 ? <small>{event.tags.join(" · ")}</small> : null}
                                  </article>
                                ))}
                              </div>
                            </section>
                            <div className="cost-manual-allocation-table-wrap">
                              <table className="cost-manual-allocation-table">
                                <thead>
                                  <tr>
                                    <th>OA 项</th>
                                    <th>分配金额</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {task.units.map((unit) => (
                                    <tr key={unit.unitId}>
                                      <th scope="row">
                                        <strong>{unitTitle(unit)}</strong>
                                        <span>{unit.expenseType || "未填写费用类型"}</span>
                                        <small>
                                          {isPaymentApplication(unit) ? "支付申请" : "日常报销子付款项"}
                                          {unit.oaApplicant ? ` · ${unit.oaApplicant}` : ""}
                                          {` · OA 金额 ${unit.oaOriginalAmount}`}
                                        </small>
                                      </th>
                                      <td>
                                        <Input
                                          aria-label={`${unitTitle(unit)}分配金额`}
                                          disabled={!canSave || !task.canSave || saving}
                                          inputMode="decimal"
                                          maxLength={18}
                                          onChange={(event) => {
                                            const value = event.currentTarget.value;
                                            updateDraft(task.relationCaseId, (current) => ({
                                              ...current,
                                              allocations: { ...current.allocations, [unit.unitId]: value },
                                            }));
                                          }}
                                          placeholder="0.00"
                                          value={draft.allocations[unit.unitId] ?? ""}
                                        />
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                            <div className="cost-manual-allocation-non-cost">
                              <Checkbox
                                isDisabled={!canSave || !task.canSave || saving}
                                isSelected={draft.hasNonCostAmount}
                                onChange={(selected) => updateDraft(task.relationCaseId, (current) => ({
                                  ...current,
                                  hasNonCostAmount: selected,
                                  nonCostAmount: selected ? current.nonCostAmount : "",
                                  nonCostReason: selected ? current.nonCostReason : "",
                                }))}
                              >
                                <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                                <span>存在不计入成本金额</span>
                              </Checkbox>
                              {draft.hasNonCostAmount ? (
                                <div>
                                  <Input
                                    aria-label="不计入成本金额"
                                    disabled={!canSave || !task.canSave || saving}
                                    inputMode="decimal"
                                    maxLength={18}
                                    onChange={(event) => {
                                      const value = event.currentTarget.value;
                                      updateDraft(task.relationCaseId, (current) => ({
                                        ...current,
                                        nonCostAmount: value,
                                      }));
                                    }}
                                    placeholder="0.00"
                                    value={draft.nonCostAmount}
                                  />
                                  <TextArea
                                    aria-label="不计入成本说明"
                                    disabled={!canSave || !task.canSave || saving}
                                    maxLength={500}
                                    onChange={(event) => {
                                      const value = event.currentTarget.value;
                                      updateDraft(task.relationCaseId, (current) => ({
                                        ...current,
                                        nonCostReason: value,
                                      }));
                                    }}
                                    placeholder="不计入成本说明（必填）"
                                    rows={2}
                                    value={draft.nonCostReason}
                                  />
                                </div>
                              ) : null}
                            </div>
                            {task.status === "stale" ? (
                              <p className="cost-manual-allocation-warning">关系事实已变化，请按当前 OA 与流水重新分配。</p>
                            ) : null}
                            {taskErrors[task.relationCaseId] ? (
                              <p className="cost-manual-allocation-error" role="alert">{taskErrors[task.relationCaseId]}</p>
                            ) : null}
                            <div className="cost-manual-allocation-actions">
                              <span className={summary.valid ? "is-balanced" : ""}>{summary.message}</span>
                              <Button
                                isDisabled={!canSave || !task.canSave || !summary.valid}
                                isPending={saving}
                                onPress={() => void handleSave(task)}
                                size="sm"
                                variant="primary"
                              >
                                {status === "allocated" ? "保存修改" : "保存分配"}
                              </Button>
                            </div>
                          </>
                        ) : null}
                      </Disclosure.Body>
                    </Disclosure.Content>
                  </Disclosure>
                );
              })}
            </DisclosureGroup>
          ) : null}
          {!loading && tasks.length > 0 && nextCursor ? (
            <div className="cost-manual-allocation-load-more">
              {loadMoreError ? <p className="cost-manual-allocation-error" role="alert">{loadMoreError}</p> : null}
              <Button
                isDisabled={loadingMore || savingCaseIds.size > 0}
                isPending={loadingMore}
                onPress={() => void load({ cursor: nextCursor })}
                size="sm"
                variant="secondary"
              >
                加载更多
              </Button>
            </div>
          ) : null}
        </div>
      </AppDrawer>
    </>
  );
}
