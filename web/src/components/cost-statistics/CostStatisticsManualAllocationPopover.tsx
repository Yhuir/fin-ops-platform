import {
  Button,
  Chip,
  Input,
  ListBox,
  PopoverContent,
  PopoverDialog,
  PopoverRoot,
  PopoverTrigger,
  Select,
} from "@heroui/react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  fetchCostStatisticsManualAllocations,
  saveCostStatisticsManualAllocation,
} from "../../features/cost-statistics/api";
import type { CostStatisticsManualAllocationTask } from "../../features/cost-statistics/types";

const MONEY_PATTERN = /^(?:0|[1-9]\d*)\.\d{2}$/;

function moneyToCents(value: string) {
  const [whole, fraction] = value.split(".");
  return (BigInt(whole) * 100n) + BigInt(fraction);
}

function formatCents(value: bigint) {
  const whole = value / 100n;
  const fraction = (value % 100n).toString().padStart(2, "0");
  return `${whole}.${fraction}`;
}

type Props = {
  canSave: boolean;
  knownPendingCount?: number;
  onSaved: () => void;
};

export default function CostStatisticsManualAllocationPopover({
  canSave,
  knownPendingCount,
  onSaved,
}: Props) {
  const [open, setOpen] = useState(false);
  const [tasks, setTasks] = useState<CostStatisticsManualAllocationTask[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const selectedTask = tasks.find((task) => task.relationCaseId === selectedCaseId) ?? tasks[0];

  const load = async (cursor?: string) => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    if (cursor) setLoadingMore(true);
    else setLoading(true);
    setError(null);
    try {
      const page = await fetchCostStatisticsManualAllocations(controller.signal, cursor);
      if (requestRef.current !== controller) return;
      setTasks((current) => cursor
        ? [...current, ...page.items.filter((item) => !current.some((task) => task.relationCaseId === item.relationCaseId))]
        : page.items);
      setNextCursor(page.nextCursor);
      setSelectedCaseId((current) => (
        cursor || page.items.some((task) => task.relationCaseId === current)
          ? current
          : page.items[0]?.relationCaseId ?? ""
      ));
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : "待分配关系加载失败。" );
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
    if (!selectedTask) {
      setDrafts({});
      return;
    }
    if (selectedTask.status !== "allocated") {
      setDrafts(Object.fromEntries(selectedTask.units.map((unit) => [unit.unitId, ""])));
      return;
    }
    const saved = new Map(selectedTask.allocations.map((line) => [line.unitId, line.amount]));
    setDrafts(Object.fromEntries(selectedTask.units.map((unit) => [unit.unitId, saved.get(unit.unitId) ?? ""])));
  }, [selectedTask?.relationCaseId, selectedTask?.sourceFingerprint, selectedTask?.version]);

  const draftSummary = useMemo(() => {
    if (!selectedTask) return { complete: false, total: "0.00", matches: false };
    const values = selectedTask.units.map((unit) => drafts[unit.unitId] ?? "");
    const complete = values.every((value) => MONEY_PATTERN.test(value));
    const cents = complete
      ? values.reduce((total, value) => total + moneyToCents(value), 0n)
      : 0n;
    const targetCents = moneyToCents(selectedTask.netCashCost);
    return {
      complete,
      total: formatCents(cents),
      matches: complete && cents === targetCents,
    };
  }, [drafts, selectedTask]);

  const handleSave = async () => {
    if (!selectedTask || !draftSummary.matches) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await saveCostStatisticsManualAllocation({
        relationCaseId: selectedTask.relationCaseId,
        expectedVersion: selectedTask.version,
        sourceFingerprint: selectedTask.sourceFingerprint,
        allocations: selectedTask.units.map((unit) => ({
          unitId: unit.unitId,
          amount: drafts[unit.unitId],
        })),
      });
      setTasks((current) => current.map((task) => (
        task.relationCaseId === saved.relationCaseId ? saved : task
      )));
      onSaved();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "人工分配保存失败。" );
    } finally {
      setSaving(false);
    }
  };

  const unresolvedCount = tasks.filter((task) => task.status !== "allocated").length;
  const triggerCount = tasks.length > 0 ? unresolvedCount : knownPendingCount;

  return (
    <PopoverRoot
      isOpen={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (nextOpen) void load();
      }}
    >
      <PopoverTrigger aria-label="待分配" className="button button--sm button--secondary cost-page-action cost-manual-allocation-trigger">
        <span>待分配</span>
        {typeof triggerCount === "number" && triggerCount > 0 ? (
          <Chip color="warning" size="sm" variant="soft">{triggerCount}</Chip>
        ) : null}
      </PopoverTrigger>
      {open ? (
        <PopoverContent
          className="cost-manual-allocation-popover"
          containerPadding={16}
          offset={8}
          placement="bottom end"
        >
          <PopoverDialog aria-label="成本统计待分配" className="cost-manual-allocation-dialog">
            <div className="cost-manual-allocation-heading">
              <div>
                <strong>配对金额人工分配</strong>
                <p>仅处理 OA 合计与流水净支出不一致的关联关系。</p>
              </div>
              {selectedTask ? (
                <Chip color={selectedTask.status === "stale" ? "warning" : selectedTask.status === "allocated" ? "success" : "default"} size="sm" variant="soft">
                  {selectedTask.status === "stale" ? "来源已变化" : selectedTask.status === "allocated" ? "已分配" : "待分配"}
                </Chip>
              ) : null}
            </div>
            {loading ? <p className="cost-manual-allocation-state">正在读取当前配对事实…</p> : null}
            {!loading && tasks.length === 0 ? <p className="cost-manual-allocation-state">当前没有待人工分配的关联关系。</p> : null}
            {!loading && tasks.length > 0 ? (
              <>
                <Select
                  aria-label="选择待分配关联关系"
                  onSelectionChange={(key) => setSelectedCaseId(String(key))}
                  selectedKey={selectedTask?.relationCaseId}
                >
                  <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
                  <Select.Popover>
                    <ListBox>
                      {tasks.map((task) => (
                        <ListBox.Item id={task.relationCaseId} key={task.relationCaseId} textValue={`${task.relationCaseId} 净支出 ${task.netCashCost}`}>
                          {task.relationCaseId} · 净支出 {task.netCashCost}
                        </ListBox.Item>
                      ))}
                    </ListBox>
                  </Select.Popover>
                </Select>
                {nextCursor ? (
                  <Button
                    isPending={loadingMore}
                    onPress={() => void load(nextCursor)}
                    size="sm"
                    variant="secondary"
                  >
                    加载更多待分配关系
                  </Button>
                ) : null}
                {selectedTask ? (
                  <>
                    <div className="cost-manual-allocation-facts">
                      <span>OA 合计 <strong>{selectedTask.oaAllocationTotal}</strong></span>
                      <span>支出 <strong>{selectedTask.bankOutflowTotal}</strong></span>
                      <span>付错退款 <strong>{selectedTask.paidWrongRefundTotal}</strong></span>
                      <span>净支出 <strong>{selectedTask.netCashCost}</strong></span>
                    </div>
                    <div className="cost-manual-allocation-units">
                      {selectedTask.units.map((unit) => (
                        <label className="cost-manual-allocation-unit" key={unit.unitId}>
                          <span>
                            <strong>{unit.projectName}</strong>
                            <small>{unit.expenseType} · OA 原金额 {unit.oaOriginalAmount}</small>
                          </span>
                          <Input
                            aria-label={`${unit.projectName}实际分配金额`}
                            disabled={!canSave || !selectedTask.canSave}
                            inputMode="decimal"
                            maxLength={18}
                            onChange={(event) => setDrafts((current) => ({ ...current, [unit.unitId]: event.target.value }))}
                            placeholder="请输入金额"
                            value={drafts[unit.unitId] ?? ""}
                          />
                        </label>
                      ))}
                    </div>
                    <div className="cost-manual-allocation-footer">
                      <span className={draftSummary.matches ? "is-balanced" : ""}>
                        已填 {draftSummary.total} / 净支出 {selectedTask.netCashCost}
                      </span>
                      <Button
                        isDisabled={!canSave || !selectedTask.canSave || !draftSummary.matches}
                        isPending={saving}
                        onPress={() => void handleSave()}
                        size="sm"
                        variant="primary"
                      >
                        保存分配
                      </Button>
                    </div>
                  </>
                ) : null}
              </>
            ) : null}
            {error ? <p className="cost-manual-allocation-error" role="alert">{error}</p> : null}
          </PopoverDialog>
        </PopoverContent>
      ) : null}
    </PopoverRoot>
  );
}
