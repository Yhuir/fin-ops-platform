import { memo, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

type WorkbenchColumnFilterMenuProps = {
  label: string;
  open: boolean;
  options: string[];
  selectedValues: string[];
  onToggle: () => void;
  onClose: () => void;
  onChange: (selectedValues: string[]) => void;
};

function WorkbenchColumnFilterMenu({
  label,
  open,
  options,
  selectedValues,
  onToggle,
  onClose,
  onChange,
}: WorkbenchColumnFilterMenuProps) {
  const popoverWidth = 188;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const [popoverStyle, setPopoverStyle] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    if (!open || !buttonRef.current) {
      return;
    }

    const updatePosition = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) {
        return;
      }
      setPopoverStyle({
        top: rect.bottom + 8,
        left: Math.min(Math.max(8, rect.right - popoverWidth), window.innerWidth - popoverWidth - 8),
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (containerRef.current?.contains(target) || popoverRef.current?.contains(target)) {
        return;
      }
      if (!containerRef.current?.contains(target)) {
        onClose();
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  const handleToggleValue = (value: string) => {
    if (selectedValues.includes(value)) {
      onChange(selectedValues.filter((candidate) => candidate !== value));
      return;
    }
    onChange([...selectedValues, value]);
  };

  return (
    <div ref={containerRef} className="column-filter-menu">
      <button
        ref={buttonRef}
        aria-label={`筛选 ${label}`}
        className={`column-filter-btn${selectedValues.length > 0 ? " active" : ""}`}
        type="button"
        onClick={onToggle}
      >
        <svg aria-hidden="true" className="column-filter-icon" viewBox="0 0 16 16">
          <path d="M4 6.5 8 10.5 12 6.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
        </svg>
      </button>
      {open && popoverStyle ? createPortal(
        <div
          ref={popoverRef}
          aria-label={`筛选 ${label}`}
          className="column-filter-popover"
          role="dialog"
          style={{ top: `${popoverStyle.top}px`, left: `${popoverStyle.left}px` }}
        >
          <div className="column-filter-actions">
            <button
              className="column-filter-action-btn"
              type="button"
              onClick={() => onChange(options)}
            >
              全选
            </button>
            <button
              className="column-filter-action-btn"
              type="button"
              onClick={() => onChange([])}
            >
              清空
            </button>
          </div>
          <div className="column-filter-option-list">
            {options.length === 0 ? <div className="column-filter-empty">暂无可选项</div> : null}
            {options.map((option) => (
              <label key={option} className="column-filter-option">
                <input
                  checked={selectedValues.includes(option)}
                  type="checkbox"
                  onChange={() => handleToggleValue(option)}
                />
                <span>{option}</span>
              </label>
            ))}
          </div>
        </div>,
        document.body,
      ) : null}
    </div>
  );
}

export default memo(WorkbenchColumnFilterMenu);
