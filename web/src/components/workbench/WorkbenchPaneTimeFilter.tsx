import {
  Button,
  PopoverContent,
  PopoverDialog,
  PopoverRoot,
  PopoverTrigger,
  Spinner,
} from "@heroui/react";
import { memo, useEffect, useMemo, useState } from "react";

import { formatMonthLabel } from "../MonthPicker";
import type { WorkbenchPaneTimeFilter } from "../../features/workbench/groupDisplayModel";
import type { WorkbenchFilterOptionsPage } from "../../features/workbench/types";

type WorkbenchPaneTimeFilterProps = {
  paneTitle: string;
  filter: WorkbenchPaneTimeFilter;
  loadYears?: (page: number, signal?: AbortSignal) => Promise<WorkbenchFilterOptionsPage>;
  onChange: (filter: WorkbenchPaneTimeFilter) => void;
};

function WorkbenchPaneTimeFilter({ paneTitle, filter, loadYears, onChange }: WorkbenchPaneTimeFilterProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [pickerMode, setPickerMode] = useState<"year" | "month">(filter.mode === "year" ? "year" : "month");
  const [years, setYears] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resolvedYears = useMemo(() => {
    const values = new Set(years);
    if (filter.mode === "year") values.add(filter.year);
    if (filter.mode === "month") values.add(filter.month.slice(0, 4));
    return Array.from(values).sort((left, right) => right.localeCompare(left, "zh-CN"));
  }, [filter, years]);
  const [activeYear, setActiveYear] = useState(
    filter.mode === "year" ? filter.year : filter.mode === "month" ? filter.month.slice(0, 4) : "",
  );

  useEffect(() => {
    setPickerMode(filter.mode === "year" ? "year" : "month");
    setActiveYear(filter.mode === "year" ? filter.year : filter.mode === "month" ? filter.month.slice(0, 4) : "");
  }, [filter]);

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
        let page = 1;
        let hasMore = true;
        while (hasMore) {
          const result = await loadYears(page, controller.signal);
          if (result.readModelStatus !== "fresh") throw new Error("数据正在刷新，请稍后重试");
          nextYears.push(...result.options.map((option) => option.value));
          hasMore = result.hasMore;
          page += 1;
        }
        const uniqueYears = Array.from(new Set(nextYears)).sort((left, right) => right.localeCompare(left, "zh-CN"));
        setYears(uniqueYears);
        setActiveYear((current) => current || uniqueYears[0] || "");
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

  const buttonLabel = filter.mode === "year" ? `${filter.year}年` : filter.mode === "month" ? formatMonthLabel(filter.month) : "时间筛选";
  const buttonAriaLabel = filter.mode === "none" ? `${paneTitle}时间筛选` : `清除${paneTitle}时间筛选 ${buttonLabel}`;

  return (
    <PopoverRoot
      isOpen={isOpen}
      onOpenChange={(nextOpen) => {
        if (filter.mode !== "none" && nextOpen) {
          onChange({ mode: "none" });
          setIsOpen(false);
          return;
        }
        setIsOpen(nextOpen);
      }}
    >
      <PopoverTrigger
        aria-label={buttonAriaLabel}
        className={`pane-tool-btn pane-time-filter-btn${filter.mode !== "none" ? " active" : ""}`}
      >
        <span className="pane-time-filter-label">{buttonLabel}</span>
      </PopoverTrigger>
      <PopoverContent className="pane-time-filter-popover" containerPadding={12} maxHeight={420} offset={8} placement="bottom end">
        <PopoverDialog aria-label={`${paneTitle}时间筛选面板`} className="pane-time-filter-dialog">
          <div className="pane-time-filter-mode-row" role="group" aria-label={`${paneTitle}时间筛选模式`}>
            <Button aria-pressed={pickerMode === "year"} onPress={() => setPickerMode("year")} size="sm" variant={pickerMode === "year" ? "primary" : "tertiary"}>按年</Button>
            <Button aria-pressed={pickerMode === "month"} onPress={() => setPickerMode("month")} size="sm" variant={pickerMode === "month" ? "primary" : "tertiary"}>按月</Button>
          </div>
          {loading ? <div className="pane-time-filter-state" role="status"><Spinner size="sm" /><span>加载中</span></div> : null}
          {!loading && error ? <div className="pane-time-filter-state error" role="alert">{error}</div> : null}
          {!loading && !error && resolvedYears.length === 0 ? <div className="pane-time-filter-state">暂无可选时间</div> : null}
          {!loading && !error && pickerMode === "year" ? (
            <div className="month-picker-chip-grid years">
              {resolvedYears.map((year) => (
                <Button key={year} aria-pressed={filter.mode === "year" && filter.year === year} onPress={() => { onChange({ mode: "year", year }); setIsOpen(false); }} size="sm" variant={filter.mode === "year" && filter.year === year ? "primary" : "tertiary"}>{year}年</Button>
              ))}
            </div>
          ) : null}
          {!loading && !error && pickerMode === "month" && activeYear ? (
            <>
              <div className="month-picker-chip-grid years">
                {resolvedYears.map((year) => (
                  <Button key={year} aria-pressed={activeYear === year} onPress={() => setActiveYear(year)} size="sm" variant={activeYear === year ? "primary" : "tertiary"}>{year}年</Button>
                ))}
              </div>
              <div className="month-picker-chip-grid months">
                {Array.from({ length: 12 }, (_, index) => {
                  const monthNumber = index + 1;
                  const monthValue = `${activeYear}-${String(monthNumber).padStart(2, "0")}`;
                  return (
                    <Button key={monthValue} aria-pressed={filter.mode === "month" && filter.month === monthValue} onPress={() => { onChange({ mode: "month", month: monthValue }); setIsOpen(false); }} size="sm" variant={filter.mode === "month" && filter.month === monthValue ? "primary" : "tertiary"}>{monthNumber}月</Button>
                  );
                })}
              </div>
            </>
          ) : null}
        </PopoverDialog>
      </PopoverContent>
    </PopoverRoot>
  );
}

export default memo(WorkbenchPaneTimeFilter);
