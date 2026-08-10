import {
  Button,
  PopoverContent,
  PopoverDialog,
  PopoverRoot,
  PopoverTrigger,
  Spinner,
} from "@heroui/react";
import { useEffect, useMemo, useState } from "react";

export type BusinessPeriodMode = "all" | "year" | "month";

export type BusinessPeriodSelection = {
  mode: BusinessPeriodMode;
  year: string;
  month: string;
};

type BusinessPeriodPickerProps = {
  ariaLabel: string;
  selection: BusinessPeriodSelection;
  years: string[];
  onChange: (selection: BusinessPeriodSelection) => void;
  allowAll?: boolean;
  allowedModes?: Array<Exclude<BusinessPeriodMode, "all">>;
  allLabel?: string;
  className?: string;
  disabled?: boolean;
  error?: string | null;
  inline?: boolean;
  label?: string;
  loading?: boolean;
  onOpenChange?: (open: boolean) => void;
};

const MONTH_LABELS = [
  "一月",
  "二月",
  "三月",
  "四月",
  "五月",
  "六月",
  "七月",
  "八月",
  "九月",
  "十月",
  "十一月",
  "十二月",
];

export function formatMonthLabel(value: string) {
  const [yearText, monthText] = value.split("-");
  const year = /^\d{4}$/.test(yearText) ? yearText : "2026";
  const month = Number.parseInt(monthText, 10);
  return `${year}年${Number.isInteger(month) && month >= 1 && month <= 12 ? month : 1}月`;
}

export function nearbyBusinessYears(value: string) {
  const parsed = Number.parseInt(value.slice(0, 4), 10);
  const year = Number.isInteger(parsed) ? parsed : new Date().getFullYear();
  return Array.from({ length: 6 }, (_, index) => String(year - 1 + index));
}

export default function BusinessPeriodPicker({
  ariaLabel,
  selection,
  years,
  onChange,
  allowAll = true,
  allowedModes = ["year", "month"],
  allLabel = "全部",
  className,
  disabled = false,
  error,
  inline = false,
  label = "时间范围",
  loading = false,
  onOpenChange,
}: BusinessPeriodPickerProps) {
  const [open, setOpen] = useState(false);
  const [activeMode, setActiveMode] = useState<"year" | "month">(
    selection.mode === "year" || selection.mode === "month" ? selection.mode : allowedModes[0] ?? "month",
  );
  const [activeYear, setActiveYear] = useState(selection.month.slice(0, 4) || selection.year);
  const pickerYears = useMemo(() => {
    const values = new Set(years.filter((value) => /^\d{4}$/.test(value)));
    if (/^\d{4}$/.test(selection.year)) values.add(selection.year);
    if (/^\d{4}/.test(selection.month)) values.add(selection.month.slice(0, 4));
    return Array.from(values).sort((left, right) => right.localeCompare(left, "zh-CN"));
  }, [selection.month, selection.year, years]);

  useEffect(() => {
    if (selection.mode === "year" || selection.mode === "month") setActiveMode(selection.mode);
    setActiveYear(selection.mode === "month" ? selection.month.slice(0, 4) : selection.year);
  }, [selection]);

  const close = () => {
    setOpen(false);
    onOpenChange?.(false);
  };
  const select = (nextSelection: BusinessPeriodSelection) => {
    onChange(nextSelection);
    if (!inline) close();
  };
  const triggerLabel = selection.mode === "year"
    ? `${selection.year}年`
    : selection.mode === "month"
      ? formatMonthLabel(selection.month)
      : "年月";

  const panel = (
    <div className={inline ? "business-period-panel business-period-panel--inline" : "business-period-panel"}>
      {allowedModes.length > 1 ? (
        <div className="business-period-modes" aria-label={`${ariaLabel}粒度`} role="group">
          {allowedModes.map((mode) => (
            <Button
              key={mode}
              aria-pressed={activeMode === mode}
              onPress={() => setActiveMode(mode)}
              size="sm"
              variant={activeMode === mode ? "primary" : "tertiary"}
            >
              {mode === "year" ? "按年" : "按月"}
            </Button>
          ))}
        </div>
      ) : null}
      {loading ? <div className="business-period-state" role="status"><Spinner size="sm" /><span>加载中</span></div> : null}
      {!loading && error ? <div className="business-period-state error" role="alert">{error}</div> : null}
      {!loading && !error && pickerYears.length === 0 ? <div className="business-period-state">暂无可选时间</div> : null}
      {!loading && !error ? (
        <>
          <div className="business-period-section">
            <span>年份</span>
            <div className="business-period-grid business-period-grid--years">
              {pickerYears.map((candidateYear) => (
                <Button
                  key={candidateYear}
                  aria-pressed={activeMode === "year" && selection.mode === "year" && selection.year === candidateYear}
                  onPress={() => {
                    setActiveYear(candidateYear);
                    if (activeMode === "year") {
                      select({ ...selection, mode: "year", year: candidateYear });
                    }
                  }}
                  size="sm"
                  variant={activeYear === candidateYear ? "primary" : "tertiary"}
                >
                  {candidateYear}年
                </Button>
              ))}
            </div>
          </div>
          {activeMode === "month" && activeYear ? (
            <div className="business-period-section">
              <span>月份</span>
              <div className="business-period-grid business-period-grid--months">
                {MONTH_LABELS.map((monthLabel, index) => {
                  const month = `${activeYear}-${String(index + 1).padStart(2, "0")}`;
                  return (
                    <Button
                      key={month}
                      aria-pressed={selection.mode === "month" && selection.month === month}
                      onPress={() => select({ mode: "month", year: activeYear, month })}
                      size="sm"
                      variant={selection.mode === "month" && selection.month === month ? "primary" : "tertiary"}
                    >
                      {monthLabel}
                    </Button>
                  );
                })}
              </div>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );

  return (
    <div className={`business-period-picker${inline ? " business-period-picker--inline" : ""}${allowAll && !inline ? " business-period-picker--segmented" : ""}${className ? ` ${className}` : ""}`} role="group" aria-label={ariaLabel}>
      {allowAll ? (
        <Button
          aria-pressed={selection.mode === "all"}
          className="business-period-all"
          isDisabled={disabled}
          onPress={() => select({ ...selection, mode: "all" })}
          size="sm"
          variant={selection.mode === "all" ? "primary" : "secondary"}
        >
          {allLabel}
        </Button>
      ) : null}
      {inline ? panel : (
        <PopoverRoot
          isOpen={open}
          onOpenChange={(nextOpen) => {
            if (disabled) return;
            setOpen(nextOpen);
            onOpenChange?.(nextOpen);
          }}
        >
          <PopoverTrigger
            aria-label={`${ariaLabel}：${triggerLabel}`}
            aria-disabled={disabled}
            className={`business-period-trigger${selection.mode !== "all" ? " is-active" : ""}`}
          >
            <span><small>{label}</small><strong>{triggerLabel}</strong></span>
            <span aria-hidden="true">▾</span>
          </PopoverTrigger>
          <PopoverContent className="business-period-popover" containerPadding={12} maxHeight={440} offset={8} placement="bottom end">
            <PopoverDialog aria-label={`${ariaLabel}选择器`}>{panel}</PopoverDialog>
          </PopoverContent>
        </PopoverRoot>
      )}
    </div>
  );
}
