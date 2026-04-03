import { useEffect, useMemo, useRef, useState } from "react";

type MonthPickerProps = {
  value: string;
  onChange: (month: string) => void;
  ariaLabel?: string;
  caption?: string | null;
};

function parseMonthValue(value: string) {
  const [yearText, monthText] = value.split("-");
  const year = Number.parseInt(yearText, 10);
  const month = Number.parseInt(monthText, 10);
  return {
    year: Number.isFinite(year) ? year : 2026,
    month: Number.isFinite(month) ? month : 1,
  };
}

export function formatMonthLabel(value: string) {
  const { year, month } = parseMonthValue(value);
  return `${year}年${month}月`;
}

export default function MonthPicker({
  value,
  onChange,
  ariaLabel = "年月选择",
  caption = "月份",
}: MonthPickerProps) {
  const { year: selectedYear, month: selectedMonth } = parseMonthValue(value);
  const [isOpen, setIsOpen] = useState(false);
  const [activeYear, setActiveYear] = useState(selectedYear);
  const [popoverOffsetX, setPopoverOffsetX] = useState(0);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setActiveYear(selectedYear);
  }, [selectedYear]);

  useEffect(() => {
    if (!isOpen) {
      return;
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

  useEffect(() => {
    if (!isOpen || !containerRef.current || !popoverRef.current || typeof window === "undefined") {
      return undefined;
    }

    const viewportPadding = 16;

    const updatePopoverOffset = () => {
      if (!containerRef.current || !popoverRef.current) {
        return;
      }
      const containerRect = containerRef.current.getBoundingClientRect();
      const popoverRect = popoverRef.current.getBoundingClientRect();
      const overflowRight = containerRect.left + popoverRect.width - (window.innerWidth - viewportPadding);
      setPopoverOffsetX(overflowRight > 0 ? -overflowRight : 0);
    };

    updatePopoverOffset();
    window.addEventListener("resize", updatePopoverOffset);
    return () => window.removeEventListener("resize", updatePopoverOffset);
  }, [isOpen]);

  const years = useMemo(() => [selectedYear - 1, selectedYear, selectedYear + 1], [selectedYear]);

  const handlePickMonth = (monthNumber: number) => {
    onChange(`${activeYear}-${String(monthNumber).padStart(2, "0")}`);
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className="month-picker">
      <button
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        aria-label={ariaLabel}
        className="month-picker-trigger"
        type="button"
        onClick={() => setIsOpen((current) => !current)}
      >
        {caption ? <span className="month-picker-caption">{caption}</span> : null}
        <strong>{formatMonthLabel(value)}</strong>
      </button>

      {isOpen ? (
        <div
          ref={popoverRef}
          aria-label="年月面板"
          className="month-picker-popover"
          role="dialog"
          style={popoverOffsetX !== 0 ? { left: `${popoverOffsetX}px` } : undefined}
        >
          <div className="month-picker-section">
            <div className="month-picker-section-title">年份</div>
            <div className="month-picker-chip-grid years">
              {years.map((year) => (
                <button
                  key={year}
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
                const isCurrentSelection = activeYear === selectedYear && monthNumber === selectedMonth;
                return (
                  <button
                    key={monthNumber}
                    aria-pressed={isCurrentSelection}
                    className={`month-picker-chip${isCurrentSelection ? " active" : ""}`}
                    type="button"
                    onClick={() => handlePickMonth(monthNumber)}
                  >
                    {monthNumber}月
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
