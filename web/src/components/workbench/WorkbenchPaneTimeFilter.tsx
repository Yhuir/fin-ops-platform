import { memo, useEffect, useMemo, useRef, useState } from "react";

import { formatMonthLabel } from "../MonthPicker";
import type { WorkbenchPaneTimeFilter } from "../../features/workbench/groupDisplayModel";

type WorkbenchPaneTimeFilterProps = {
  paneTitle: string;
  filter: WorkbenchPaneTimeFilter;
  availableYears: string[];
  onChange: (filter: WorkbenchPaneTimeFilter) => void;
};

function WorkbenchPaneTimeFilter({
  paneTitle,
  filter,
  availableYears,
  onChange,
}: WorkbenchPaneTimeFilterProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [pickerMode, setPickerMode] = useState<"year" | "month">(filter.mode === "year" ? "year" : "month");
  const fallbackYear = String(new Date().getFullYear());
  const resolvedYears = useMemo(() => {
    const yearSet = new Set(availableYears);
    if (filter.mode === "year") {
      yearSet.add(filter.year);
    }
    if (filter.mode === "month") {
      yearSet.add(filter.month.slice(0, 4));
    }
    if (yearSet.size === 0) {
      yearSet.add(fallbackYear);
    }
    return Array.from(yearSet).sort((left, right) => right.localeCompare(left, "zh-CN"));
  }, [availableYears, fallbackYear, filter]);
  const [activeYear, setActiveYear] = useState(
    filter.mode === "year" ? filter.year : filter.mode === "month" ? filter.month.slice(0, 4) : resolvedYears[0] ?? fallbackYear,
  );

  useEffect(() => {
    setPickerMode(filter.mode === "year" ? "year" : "month");
    setActiveYear(
      filter.mode === "year" ? filter.year : filter.mode === "month" ? filter.month.slice(0, 4) : resolvedYears[0] ?? fallbackYear,
    );
  }, [fallbackYear, filter, resolvedYears]);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen]);

  const buttonLabel = filter.mode === "year" ? `${filter.year}年` : filter.mode === "month" ? formatMonthLabel(filter.month) : "时间筛选";
  const buttonAriaLabel =
    filter.mode === "none" ? `${paneTitle}时间筛选` : `清除${paneTitle}时间筛选 ${buttonLabel}`;

  const handleTriggerClick = () => {
    if (filter.mode !== "none") {
      onChange({ mode: "none" });
      setIsOpen(false);
      return;
    }
    setIsOpen((current) => !current);
  };

  const handleYearSelect = (year: string) => {
    onChange({ mode: "year", year });
    setIsOpen(false);
  };

  const handleMonthSelect = (monthNumber: number) => {
    onChange({
      mode: "month",
      month: `${activeYear}-${String(monthNumber).padStart(2, "0")}`,
    });
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className="pane-time-filter">
      <button
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        aria-label={buttonAriaLabel}
        className={`pane-tool-btn pane-time-filter-btn${filter.mode !== "none" ? " active" : ""}`}
        type="button"
        onClick={handleTriggerClick}
      >
        <span className="pane-time-filter-label">{buttonLabel}</span>
      </button>

      {isOpen ? (
        <div
          aria-label={`${paneTitle}时间筛选面板`}
          className="pane-time-filter-popover"
          role="dialog"
        >
          <div className="pane-time-filter-mode-row" role="group" aria-label={`${paneTitle}时间筛选模式`}>
            <button
              aria-pressed={pickerMode === "year"}
              className={`pane-time-filter-mode-btn${pickerMode === "year" ? " active" : ""}`}
              type="button"
              onClick={() => setPickerMode("year")}
            >
              按年
            </button>
            <button
              aria-pressed={pickerMode === "month"}
              className={`pane-time-filter-mode-btn${pickerMode === "month" ? " active" : ""}`}
              type="button"
              onClick={() => setPickerMode("month")}
            >
              按月
            </button>
          </div>

          {pickerMode === "year" ? (
            <div className="month-picker-section">
              <div className="month-picker-section-title">年份</div>
              <div className="month-picker-chip-grid years">
                {resolvedYears.map((year) => (
                  <button
                    key={year}
                    aria-label={`${year}年`}
                    aria-pressed={filter.mode === "year" && filter.year === year}
                    className={`month-picker-chip${filter.mode === "year" && filter.year === year ? " active" : ""}`}
                    type="button"
                    onClick={() => handleYearSelect(year)}
                  >
                    {year}年
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              <div className="month-picker-section">
                <div className="month-picker-section-title">年份</div>
                <div className="month-picker-chip-grid years">
                  {resolvedYears.map((year) => (
                    <button
                      key={year}
                      aria-label={`${year}年`}
                      aria-pressed={activeYear === year}
                      className={`month-picker-chip${activeYear === year ? " active" : ""}`}
                      type="button"
                      onClick={() => setActiveYear(year)}
                    >
                      {year}年
                    </button>
                  ))}
                </div>
              </div>
              <div className="month-picker-section">
                <div className="month-picker-section-title">月份</div>
                <div className="month-picker-chip-grid months">
                  {Array.from({ length: 12 }, (_, index) => {
                    const monthNumber = index + 1;
                    const monthValue = `${activeYear}-${String(monthNumber).padStart(2, "0")}`;
                    const isActive = filter.mode === "month" && filter.month === monthValue;
                    return (
                      <button
                        key={monthValue}
                        aria-label={`${monthNumber}月`}
                        aria-pressed={isActive}
                        className={`month-picker-chip${isActive ? " active" : ""}`}
                        type="button"
                        onClick={() => handleMonthSelect(monthNumber)}
                      >
                        {monthNumber}月
                      </button>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default memo(WorkbenchPaneTimeFilter);
