import { memo, useEffect, useRef } from "react";

type WorkbenchPaneSearchProps = {
  paneTitle: string;
  open: boolean;
  value: string;
  onChange: (value: string) => void;
  onToggle: () => void;
};

function WorkbenchPaneSearch({ paneTitle, open, value, onChange, onToggle }: WorkbenchPaneSearchProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [open]);

  return (
    <div className={`pane-search${open ? " open" : ""}`}>
      {open ? (
        <input
          ref={inputRef}
          aria-label={`搜索 ${paneTitle}`}
          className="pane-search-input"
          placeholder={`搜索${paneTitle}`}
          type="search"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : null}
      <button
        aria-label={`搜索 ${paneTitle}`}
        className={`pane-tool-btn${open ? " active" : ""}`}
        type="button"
        onClick={onToggle}
      >
        <svg aria-hidden="true" className="pane-tool-icon" viewBox="0 0 20 20">
          <circle cx="9" cy="9" r="5.6" fill="none" stroke="currentColor" strokeWidth="1.8" />
          <path d="M13.4 13.4 17 17" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
        </svg>
      </button>
    </div>
  );
}

export default memo(WorkbenchPaneSearch);
