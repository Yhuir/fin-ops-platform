import { useMemo, useState } from "react";

type MonthPickerProps = {
  value: string;
  onChange: (month: string) => void;
  ariaLabel?: string;
  caption?: string | null;
  inline?: boolean;
};

const monthLabels = [
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

function parseMonthValue(value: string) {
  const [yearText, monthText] = value.split("-");
  const year = Number.parseInt(yearText, 10);
  const month = Number.parseInt(monthText, 10);
  return {
    year: Number.isFinite(year) ? year : 2026,
    month: Number.isFinite(month) && month >= 1 && month <= 12 ? month : 1,
  };
}

function formatMonthValue(year: number, month: number) {
  return `${year}-${String(month).padStart(2, "0")}`;
}

export function formatMonthLabel(value: string) {
  const { year, month } = parseMonthValue(value);
  return `${year}年${month}月`;
}

function createYearOptions(activeYear: number) {
  const start = activeYear - 1;
  return Array.from({ length: 6 }, (_, index) => start + index);
}

export default function MonthPicker({
  value,
  onChange,
  ariaLabel = "年月选择",
  caption = "月份",
  inline = false,
}: MonthPickerProps) {
  const { year, month } = parseMonthValue(value);
  const [open, setOpen] = useState(false);
  const [activeYear, setActiveYear] = useState(year);
  const yearOptions = useMemo(() => createYearOptions(activeYear), [activeYear]);
  const label = caption ?? ariaLabel;

  const selectMonth = (nextMonth: number) => {
    onChange(formatMonthValue(activeYear, nextMonth));
    setOpen(false);
  };

  const pickerPanel = (
    <div className={inline ? "month-picker-inline-panel" : "month-picker-popover"} role="dialog" aria-label={`${ariaLabel}面板`}>
      <div className="month-picker-section">
        <div className="month-picker-section-title">年份</div>
        <div className="month-picker-chip-grid years" role="radiogroup" aria-label="年份">
          {yearOptions.map((option) => (
            <button
              key={option}
              aria-checked={option === activeYear}
              className={`month-picker-chip${option === activeYear ? " active" : ""}`}
              role="radio"
              type="button"
              onClick={() => setActiveYear(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      <div className="month-picker-section">
        <div className="month-picker-section-title">月份</div>
        <div className="month-picker-chip-grid months" role="radiogroup" aria-label="月份">
          {monthLabels.map((monthLabel, index) => {
            const monthNumber = index + 1;
            const isActive = activeYear === year && monthNumber === month;
            return (
              <button
                key={monthLabel}
                aria-checked={isActive}
                className={`month-picker-chip${isActive ? " active" : ""}`}
                role="radio"
                type="button"
                onClick={() => selectMonth(monthNumber)}
              >
                {monthLabel}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );

  if (inline) {
    return (
      <div className="month-picker" role="group" aria-label={label}>
        <span role="spinbutton" aria-label="年份" aria-valuenow={year} aria-valuemin={1900} aria-valuemax={2100} />
        <span role="spinbutton" aria-label="月份" aria-valuenow={month} aria-valuemin={1} aria-valuemax={12} />
        {pickerPanel}
      </div>
    );
  }

  return (
    <div className="month-picker" role="group" aria-label={label}>
      <span role="spinbutton" aria-label="年份" aria-valuenow={year} aria-valuemin={1900} aria-valuemax={2100} />
      <span role="spinbutton" aria-label="月份" aria-valuenow={month} aria-valuemin={1} aria-valuemax={12} />
      <button
        aria-expanded={open}
        aria-label={ariaLabel}
        className="month-picker-trigger"
        type="button"
        onClick={() => {
          setActiveYear(year);
          setOpen((current) => !current);
        }}
      >
        {caption ? <span className="month-picker-caption">{caption}</span> : null}
        <strong>{formatMonthLabel(value)}</strong>
      </button>
      {open ? pickerPanel : null}
    </div>
  );
}
