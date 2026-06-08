import { memo, useCallback, useEffect, useRef, useState, type CSSProperties } from "react";

type WorkbenchPaneSearchProps = {
  paneTitle: string;
  open: boolean;
  draftValue: string;
  appliedValue: string;
  onChange: (value: string) => void;
  onClear: () => void;
  onClose: () => void;
  onToggle: () => void;
};

function WorkbenchPaneSearch({
  paneTitle,
  open,
  draftValue,
  appliedValue,
  onChange,
  onClear,
  onClose,
  onToggle,
}: WorkbenchPaneSearchProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [popoverStyle, setPopoverStyle] = useState<CSSProperties>({});
  const normalizedDraftValue = draftValue.trim();
  const normalizedAppliedValue = appliedValue.trim();
  const hasAppliedValue = normalizedAppliedValue.length > 0;
  const showAppliedSummary = hasAppliedValue && !open;
  const buttonAriaLabel = open
    ? `收起搜索 ${paneTitle}`
    : hasAppliedValue
      ? `搜索 ${paneTitle}，当前关键词 ${normalizedAppliedValue}`
      : `搜索 ${paneTitle}`;

  const syncPopoverPosition = useCallback(() => {
    const button = buttonRef.current;
    if (!button) {
      return;
    }
    const rect = button.getBoundingClientRect();
    const popoverWidth = Math.min(244, Math.max(180, window.innerWidth - 24));
    const left = Math.max(12, Math.min(rect.right - popoverWidth, window.innerWidth - popoverWidth - 12));
    const top = Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - 52));
    setPopoverStyle({
      "--pane-search-popover-left": `${left}px`,
      "--pane-search-popover-top": `${top}px`,
      "--pane-search-popover-width": `${popoverWidth}px`,
    } as CSSProperties);
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }
    syncPopoverPosition();
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [open, syncPopoverPosition]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handleViewportChange = () => syncPopoverPosition();
    window.addEventListener("resize", handleViewportChange);
    window.addEventListener("scroll", handleViewportChange, true);
    return () => {
      window.removeEventListener("resize", handleViewportChange);
      window.removeEventListener("scroll", handleViewportChange, true);
    };
  }, [open, syncPopoverPosition]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (rootRef.current?.contains(event.target as Node)) {
        return;
      }
      onClose();
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [onClose, open]);

  return (
    <div ref={rootRef} className={`pane-search${open ? " open" : ""}${hasAppliedValue ? " has-applied" : ""}`}>
      {open ? (
        <div className={`pane-search-popover${hasAppliedValue ? " active" : ""}`} style={popoverStyle}>
          <div className="pane-search-input-wrap">
            <svg aria-hidden="true" className="pane-search-input-icon" viewBox="0 0 20 20">
              <circle cx="9" cy="9" r="5.6" fill="none" stroke="currentColor" strokeWidth="1.8" />
              <path d="M13.4 13.4 17 17" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
            </svg>
            <input
              ref={inputRef}
              aria-label={`搜索 ${paneTitle}`}
              autoComplete="off"
              className="pane-search-field"
              placeholder={`搜索${paneTitle}`}
              type="search"
              value={draftValue}
              onChange={(event) => onChange(event.target.value)}
            />
            {draftValue ? (
              <button
                aria-label={`清空搜索 ${paneTitle}`}
                className="pane-search-clear-btn"
                type="button"
                onClick={onClear}
                onMouseDown={(event) => event.preventDefault()}
              >
                <span aria-hidden="true">×</span>
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
      <button
        ref={buttonRef}
        aria-label={buttonAriaLabel}
        className={`pane-tool-btn pane-search-toggle-btn pane-search-toggle-btn--header-control${open || hasAppliedValue ? " active" : ""}${showAppliedSummary ? " summary" : ""}`}
        type="button"
        onClick={() => {
          syncPopoverPosition();
          onToggle();
        }}
      >
        {showAppliedSummary ? (
          <span className="pane-search-summary">{normalizedAppliedValue}</span>
        ) : (
          <svg aria-hidden="true" className="pane-tool-icon" viewBox="0 0 20 20">
            <circle cx="9" cy="9" r="5.6" fill="none" stroke="currentColor" strokeWidth="1.8" />
            <path d="M13.4 13.4 17 17" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
          </svg>
        )}
      </button>
    </div>
  );
}

export default memo(WorkbenchPaneSearch);
