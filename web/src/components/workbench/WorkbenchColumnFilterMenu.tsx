import {
  Button,
  Checkbox,
  PopoverContent,
  PopoverDialog,
  PopoverRoot,
  PopoverTrigger,
  SearchField,
  Spinner,
} from "@heroui/react";
import { memo, useEffect, useRef, useState } from "react";

import type {
  WorkbenchFilterOption,
  WorkbenchFilterOptionsLoader,
  WorkbenchRecordType,
  WorkbenchZoneId,
} from "../../features/workbench/types";

type WorkbenchColumnFilterMenuProps = {
  label: string;
  open: boolean;
  options?: string[];
  selectedValues: string[];
  loadFilterOptions?: WorkbenchFilterOptionsLoader;
  zoneId?: WorkbenchZoneId;
  paneId?: WorkbenchRecordType;
  columnKey?: string;
  onOpen?: () => void;
  onToggle?: () => void;
  onClose: () => void;
  onChange: (selectedValues: string[]) => void;
};

function WorkbenchColumnFilterMenu({
  label,
  open,
  options: staticOptions,
  selectedValues,
  loadFilterOptions,
  zoneId,
  paneId,
  columnKey,
  onOpen,
  onToggle,
  onClose,
  onChange,
}: WorkbenchColumnFilterMenuProps) {
  const requestIdRef = useRef(0);
  const [optionSearch, setOptionSearch] = useState("");
  const [options, setOptions] = useState<WorkbenchFilterOption[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    const requestId = ++requestIdRef.current;
    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      if (!loadFilterOptions || !zoneId || !paneId || !columnKey) {
        setOptions((staticOptions ?? [])
          .filter((option) => !optionSearch || option.toLocaleLowerCase("zh-CN").includes(optionSearch.toLocaleLowerCase("zh-CN")))
          .map((option) => ({ value: option, label: option, missing: false })));
        setHasMore(false);
        setError(staticOptions ? null : "筛选选项暂不可用");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const result = await loadFilterOptions(zoneId, {
          pane: paneId,
          facet: "column",
          column: columnKey,
          optionSearch,
          page: 1,
        }, controller.signal);
        if (requestId !== requestIdRef.current) return;
        if (result.readModelStatus !== "fresh") {
          setOptions([]);
          setHasMore(false);
          setError("数据正在刷新，请稍后重试");
          return;
        }
        setOptions(result.options);
        setPage(1);
        setHasMore(result.hasMore);
      } catch (reason) {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return;
        setOptions([]);
        setHasMore(false);
        setError(reason instanceof Error ? reason.message : "筛选选项加载失败");
      } finally {
        if (requestId === requestIdRef.current) setLoading(false);
      }
    }, optionSearch ? 160 : 0);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [columnKey, loadFilterOptions, open, optionSearch, paneId, staticOptions, zoneId]);

  const handleLoadMore = async () => {
    if (!loadFilterOptions || !zoneId || !paneId || !columnKey || loading || !hasMore) return;
    const nextPage = page + 1;
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const result = await loadFilterOptions(zoneId, {
        pane: paneId,
        facet: "column",
        column: columnKey,
        optionSearch,
        page: nextPage,
      });
      if (requestId !== requestIdRef.current) return;
      setOptions((current) => {
        const byValue = new Map(current.map((option) => [option.value, option]));
        result.options.forEach((option) => byValue.set(option.value, option));
        return Array.from(byValue.values());
      });
      setPage(nextPage);
      setHasMore(result.hasMore);
    } catch (reason) {
      if (requestId === requestIdRef.current) {
        setError(reason instanceof Error ? reason.message : "筛选选项加载失败");
      }
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  };

  const handleToggleValue = (value: string, selected: boolean) => {
    onChange(selected
      ? Array.from(new Set([...selectedValues, value]))
      : selectedValues.filter((candidate) => candidate !== value));
  };

  return (
    <PopoverRoot
      isOpen={open}
      onOpenChange={(nextOpen) => {
        if (nextOpen) {
          setOptionSearch("");
          (onOpen ?? onToggle)?.();
        } else {
          onClose();
        }
      }}
    >
      <PopoverTrigger
        aria-label={`筛选 ${label}`}
        className={`column-filter-btn${selectedValues.length > 0 ? " active" : ""}`}
      >
        <svg aria-hidden="true" className="column-filter-icon" viewBox="0 0 16 16">
          <path d="M4 6.5 8 10.5 12 6.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
        </svg>
      </PopoverTrigger>
      <PopoverContent
        className="column-filter-popover"
        containerPadding={12}
        maxHeight={380}
        offset={8}
        placement="bottom end"
      >
        <PopoverDialog aria-label={`筛选 ${label}`} className="column-filter-dialog">
          <SearchField aria-label={`搜索${label}选项`} onChange={setOptionSearch} value={optionSearch}>
            <SearchField.Group className="column-filter-search-group">
              <SearchField.SearchIcon />
              <SearchField.Input placeholder="搜索选项" />
              <SearchField.ClearButton aria-label="清空选项搜索" />
            </SearchField.Group>
          </SearchField>
          <div className="column-filter-option-list" role="group" aria-label={`${label}选项`}>
            {loading && options.length === 0 ? (
              <div className="column-filter-state" role="status"><Spinner size="sm" /><span>加载中</span></div>
            ) : null}
            {!loading && error ? <div className="column-filter-state error" role="alert">{error}</div> : null}
            {!loading && !error && options.length === 0 ? <div className="column-filter-state">暂无可选项</div> : null}
            {options.map((option) => (
              <Checkbox
                className="column-filter-option"
                isSelected={selectedValues.includes(option.value)}
                key={option.value}
                onChange={(selected) => handleToggleValue(option.value, selected)}
                slot={null}
              >
                <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                <span>{option.label}</span>
              </Checkbox>
            ))}
            {hasMore ? (
              <Button isDisabled={loading} onPress={() => void handleLoadMore()} size="sm" variant="tertiary">
                {loading ? "加载中" : "加载更多"}
              </Button>
            ) : null}
          </div>
          <div className="column-filter-actions">
            <Button
              isDisabled={selectedValues.length === 0}
              onPress={() => {
                onChange([]);
                onClose();
              }}
              size="sm"
              variant="tertiary"
            >
              清空
            </Button>
          </div>
        </PopoverDialog>
      </PopoverContent>
    </PopoverRoot>
  );
}

export default memo(WorkbenchColumnFilterMenu);
