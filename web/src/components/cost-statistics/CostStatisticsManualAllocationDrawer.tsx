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
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../common/FinanceTable";
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
  valid: boolean;
  message: string | null;
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
  const hasAllocationInput = values.some((value) => value.trim());
  const allocatedCents = values
    .filter((value) => MONEY_PATTERN.test(value))
    .reduce((total, value) => total + moneyToCents(value), 0n);
  const netOutflowCents = moneyToCents(task.netOutflowTotal);
  if (values.some((value) => value && !MONEY_PATTERN.test(value))) {
    return { valid: false, message: "请输入非负金额（两位小数）" };
  }
  let nonCostCents = 0n;
  if (draft.hasNonCostAmount) {
    if (!MONEY_PATTERN.test(draft.nonCostAmount) || moneyToCents(draft.nonCostAmount) <= 0n) {
      return { valid: false, message: "请输入不计入成本金额（两位小数）" };
    }
    if (!draft.nonCostReason.trim()) {
      return { valid: false, message: "请填写不计入成本说明" };
    }
    nonCostCents = moneyToCents(draft.nonCostAmount);
  }
  const totalCents = allocatedCents + nonCostCents;
  const differenceCents = netOutflowCents - totalCents;
  if (values.some((value) => !value)) {
    if (!hasAllocationInput && !draft.hasNonCostAmount && task.status !== "allocated") {
      return { valid: false, message: null };
    }
    if (differenceCents === 0n) {
      return { valid: false, message: "请填写每项分配金额" };
    }
    return {
      valid: false,
      message: differenceCents > 0n
        ? `待分配 ${formatCents(differenceCents)}`
        : `超出 ${formatCents(-differenceCents)}`,
    };
  }
  if (differenceCents === 0n) {
    return { valid: true, message: null };
  }
  return {
    valid: false,
    message: differenceCents > 0n
      ? `待分配 ${formatCents(differenceCents)}`
      : `超出 ${formatCents(-differenceCents)}`,
  };
}

function unitTitle(unit: CostStatisticsManualAllocationUnit) {
  return unit.projectName || unit.expenseContent || unit.expenseType || "未填写 OA 项";
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
                const hasMultipleProjects = new Set(
                  task.units.map((unit) => unit.projectName).filter(Boolean),
                ).size > 1;
                const hasRefund = moneyToCents(task.wrongPaymentRefundTotal) > 0n;
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
                          {task.status === "stale" ? (
                            <Chip color="warning" size="sm" variant="soft">待重新分配</Chip>
                          ) : null}
                          <Disclosure.Indicator className="cost-manual-allocation-indicator" />
                        </span>
                      </Button>
                    </Disclosure.Heading>
                    <Disclosure.Content>
                      <Disclosure.Body className="cost-manual-allocation-detail">
                        {expanded ? (
                          <>
                            <section className="cost-manual-allocation-sources" aria-label="流水明细">
                              <header>
                                <h3>流水</h3>
                                {hasRefund ? (
                                  <span>支出 {task.grossOutflowTotal} · 退款 {task.wrongPaymentRefundTotal}</span>
                                ) : null}
                              </header>
                              <div>
                                {task.bankEvents.map((event, index) => (
                                  <article key={`${event.eventKind}:${event.transactionId}`}>
                                    <div className="cost-manual-allocation-event-heading">
                                      <Chip color={event.eventKind === "wrong_payment_refund" ? "warning" : "default"} size="sm" variant="soft">
                                        {event.eventKind === "wrong_payment_refund" ? "付错退款" : `流水${index + 1}`}
                                      </Chip>
                                      <strong>{event.amount}</strong>
                                    </div>
                                    {event.counterpartyName ? <span>{event.counterpartyName}</span> : null}
                                    <Chip className="cost-manual-allocation-meta-chip" color="default" size="sm" variant="soft">
                                      <Chip.Label>{formatDateTimeText(event.tradeTime)}</Chip.Label>
                                    </Chip>
                                    {event.tags.length > 0 ? (
                                      <Chip className="cost-manual-allocation-tag-chip" color="default" size="sm" variant="soft">
                                        <Chip.Label>{event.tags.join(" / ")}</Chip.Label>
                                      </Chip>
                                    ) : null}
                                  </article>
                                ))}
                              </div>
                            </section>
                            <div className="cost-manual-allocation-table-wrap">
                              <FinanceTable
                                ariaLabel={`${taskLabel(task)}人工分配明细`}
                                className="cost-manual-allocation-table"
                                minWidth={560}
                                selectableText
                              >
                                <FinanceTableHeader>
                                  <FinanceTableColumn columnRole="description" id="oa-unit" isRowHeader>OA 项</FinanceTableColumn>
                                  <FinanceTableColumn columnRole="amount" id="amount">分配金额</FinanceTableColumn>
                                </FinanceTableHeader>
                                <FinanceTableBody>
                                  {task.units.map((unit) => (
                                    <FinanceTableRow id={unit.unitId} key={unit.unitId} textValue={unitTitle(unit)}>
                                      <FinanceTableCell columnRole="description" textValue={unitTitle(unit)}>
                                        {hasMultipleProjects ? <strong>{unit.projectName}</strong> : null}
                                        <div className="cost-manual-allocation-oa-tags">
                                          {unit.oaApplyType ? (
                                            <Chip color="default" size="sm" variant="soft">{unit.oaApplyType}</Chip>
                                          ) : null}
                                          {unit.expenseType ? (
                                            <Chip color="default" size="sm" variant="soft">{unit.expenseType}</Chip>
                                          ) : null}
                                        </div>
                                        <small>
                                          {unit.oaApplicant ? `${unit.oaApplicant} · ` : ""}
                                          {`OA 金额 ${unit.oaOriginalAmount}`}
                                        </small>
                                      </FinanceTableCell>
                                      <FinanceTableCell columnRole="amount" textValue={draft.allocations[unit.unitId] ?? ""}>
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
                                      </FinanceTableCell>
                                    </FinanceTableRow>
                                  ))}
                                </FinanceTableBody>
                              </FinanceTable>
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
                                <span>不计入成本</span>
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
                              {summary.message ? <span>{summary.message}</span> : null}
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
