import { memo, useEffect, useRef } from "react";
import ClearIcon from "@mui/icons-material/Clear";
import SearchIcon from "@mui/icons-material/Search";
import Grow from "@mui/material/Grow";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import TextField from "@mui/material/TextField";

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
  const inputRef = useRef<HTMLInputElement | null>(null);
  const normalizedDraftValue = draftValue.trim();
  const normalizedAppliedValue = appliedValue.trim();
  const hasAppliedValue = normalizedAppliedValue.length > 0;
  const showAppliedSummary = hasAppliedValue && !open;
  const buttonAriaLabel = open
    ? `收起搜索 ${paneTitle}`
    : hasAppliedValue
      ? `搜索 ${paneTitle}，当前关键词 ${normalizedAppliedValue}`
      : `搜索 ${paneTitle}`;

  useEffect(() => {
    if (!open) {
      return;
    }
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [open]);

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
        <Grow in timeout={140} style={{ transformOrigin: "right top" }}>
          <div className={`pane-search-popover${hasAppliedValue ? " active" : ""}`}>
            <TextField
              inputRef={inputRef}
              className="pane-search-field"
              hiddenLabel
              placeholder={`搜索${paneTitle}`}
              size="small"
              type="search"
              value={draftValue}
              variant="outlined"
              onChange={(event) => onChange(event.target.value)}
              slotProps={{
                htmlInput: {
                  "aria-label": `搜索 ${paneTitle}`,
                  autoComplete: "off",
                },
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon fontSize="small" />
                    </InputAdornment>
                  ),
                  endAdornment: draftValue ? (
                    <InputAdornment position="end">
                      <IconButton
                        aria-label={`清空搜索 ${paneTitle}`}
                        edge="end"
                        size="small"
                        onClick={onClear}
                        onMouseDown={(event) => event.preventDefault()}
                      >
                        <ClearIcon fontSize="small" />
                      </IconButton>
                    </InputAdornment>
                  ) : null,
                },
              }}
            />
          </div>
        </Grow>
      ) : null}
      <button
        aria-label={buttonAriaLabel}
        className={`pane-tool-btn pane-search-toggle-btn fixed${open || hasAppliedValue ? " active" : ""}${showAppliedSummary ? " summary" : ""}`}
        type="button"
        onClick={onToggle}
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
