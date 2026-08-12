import { memo, useEffect, useMemo, useState } from "react";

import BusinessPeriodPicker from "../common/BusinessPeriodPicker";
import type { WorkbenchPaneTimeFilter } from "../../features/workbench/groupDisplayModel";
import type { WorkbenchFilterOptionsPage } from "../../features/workbench/types";

type WorkbenchPaneTimeFilterProps = {
  paneTitle: string;
  filter: WorkbenchPaneTimeFilter;
  loadYears?: (cursor: string | null, signal?: AbortSignal) => Promise<WorkbenchFilterOptionsPage>;
  onChange: (filter: WorkbenchPaneTimeFilter) => void;
};

function WorkbenchPaneTimeFilter({ paneTitle, filter, loadYears, onChange }: WorkbenchPaneTimeFilterProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [years, setYears] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resolvedYears = useMemo(() => {
    const values = new Set(years);
    if (filter.mode === "year") values.add(filter.year);
    if (filter.mode === "month") values.add(filter.month.slice(0, 4));
    return Array.from(values).sort((left, right) => right.localeCompare(left, "zh-CN"));
  }, [filter, years]);
  useEffect(() => {
    if (!isOpen) return undefined;
    const controller = new AbortController();
    const load = async () => {
      if (!loadYears) {
        setError("时间选项暂不可用");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const nextYears: string[] = [];
        let cursor: string | null = null;
        let hasMore = true;
        while (hasMore) {
          const result = await loadYears(cursor, controller.signal);
          nextYears.push(...result.options.map((option) => option.value));
          hasMore = result.hasMore;
          cursor = result.nextCursor;
        }
        const uniqueYears = Array.from(new Set(nextYears)).sort((left, right) => right.localeCompare(left, "zh-CN"));
        setYears(uniqueYears);
      } catch (reason) {
        if (!controller.signal.aborted) {
          setYears([]);
          setError(reason instanceof Error ? reason.message : "时间选项加载失败");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, [isOpen, loadYears]);

  const fallbackYear = resolvedYears[0] ?? String(new Date().getFullYear());
  const selection = filter.mode === "year"
    ? { mode: "year" as const, year: filter.year, month: `${filter.year}-01` }
    : filter.mode === "month"
      ? { mode: "month" as const, year: filter.month.slice(0, 4), month: filter.month }
      : { mode: "all" as const, year: fallbackYear, month: `${fallbackYear}-01` };

  return (
    <BusinessPeriodPicker
      ariaLabel={`${paneTitle}时间筛选`}
      className="pane-time-filter"
      error={error}
      loading={loading}
      onChange={(nextSelection) => {
        if (nextSelection.mode === "all") onChange({ mode: "none" });
        if (nextSelection.mode === "year") onChange({ mode: "year", year: nextSelection.year });
        if (nextSelection.mode === "month") onChange({ mode: "month", month: nextSelection.month });
      }}
      onOpenChange={setIsOpen}
      selection={selection}
      years={resolvedYears}
    />
  );
}

export default memo(WorkbenchPaneTimeFilter);
