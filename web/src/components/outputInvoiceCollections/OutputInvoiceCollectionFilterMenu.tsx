import { PopoverContent, PopoverDialog, PopoverRoot, PopoverTrigger } from "@heroui/react";
import { ArrowDown, ArrowUp, Filter } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";
import { useEffect, useId, useMemo, useState } from "react";

export type OutputInvoiceCollectionFilterMode = "text" | "enum_single" | "enum_multi" | "date" | "money";

export type OutputInvoiceCollectionFieldConfig = {
  field: string;
  label: string;
  mode: OutputInvoiceCollectionFilterMode;
  sortable?: boolean;
  operators?: string[];
};

export type OutputInvoiceCollectionFilterOption = {
  value: string;
  label: string;
  count?: number;
};

export type OutputInvoiceCollectionFilterValue =
  | { field: string; operator: "in"; values: string[] }
  | { field: string; operator: "equals"; value: string }
  | { field: string; operator: "contains"; value: string }
  | { field: string; operator: "between"; value: { min?: string; max?: string } | [string, string] | null }
  | { field: string; operator: string; value?: string; values?: string[] };

type OutputInvoiceCollectionFilterMenuProps = {
  fieldConfig: OutputInvoiceCollectionFieldConfig;
  currentFilter?: OutputInvoiceCollectionFilterValue | null;
  options: OutputInvoiceCollectionFilterOption[];
  onApply: (filter: OutputInvoiceCollectionFilterValue) => void;
  onClear: (field: string) => void;
  onSort: (direction: "asc" | "desc") => void;
};

export default function OutputInvoiceCollectionFilterMenu({
  fieldConfig,
  currentFilter,
  options,
  onApply,
  onClear,
  onSort,
}: OutputInvoiceCollectionFilterMenuProps) {
  const menuId = useId();
  const [open, setOpen] = useState(false);
  const selectedValues = useMemo(() => resolveSelectedValues(currentFilter), [currentFilter]);
  const selectedSet = useMemo(() => new Set(selectedValues), [selectedValues]);
  const [operator, setOperator] = useState<"contains" | "equals" | "between">("contains");
  const [singleValue, setSingleValue] = useState("");
  const [minValue, setMinValue] = useState("");
  const [maxValue, setMaxValue] = useState("");
  const hasActiveFilter = Boolean(currentFilter);

  useEffect(() => {
    if (!open) {
      return;
    }
    const currentOperator = currentFilter?.operator;
    if (currentOperator === "equals" || currentOperator === "contains" || currentOperator === "between") {
      setOperator(currentOperator);
    } else if (fieldConfig.mode === "text") {
      setOperator(fieldConfig.operators?.includes("contains") === false ? "equals" : "contains");
    } else {
      setOperator("between");
    }
    if (currentFilter && "value" in currentFilter) {
      const value = currentFilter.value;
      if (typeof value === "string") {
        setSingleValue(value);
        setMinValue("");
        setMaxValue("");
      } else if (Array.isArray(value)) {
        setSingleValue("");
        setMinValue(String(value[0] ?? ""));
        setMaxValue(String(value[1] ?? ""));
      } else if (value && typeof value === "object") {
        setSingleValue("");
        setMinValue(String(value.min ?? ""));
        setMaxValue(String(value.max ?? ""));
      } else {
        setSingleValue("");
        setMinValue("");
        setMaxValue("");
      }
      return;
    }
    setSingleValue("");
    setMinValue("");
    setMaxValue("");
  }, [currentFilter, fieldConfig, open]);

  const optionLabel = (option: OutputInvoiceCollectionFilterOption) => (
    option.count === undefined ? option.label : `${option.label} ${option.count}`
  );

  const applyMulti = (values: string[]) => {
    onApply({ field: fieldConfig.field, operator: "in", values });
  };

  const toggleMulti = (value: string) => {
    if (selectedSet.has(value)) {
      applyMulti(selectedValues.filter((candidate) => candidate !== value));
      return;
    }
    applyMulti([...selectedValues, value]);
  };

  const applySingle = (value: string) => {
    onApply({ field: fieldConfig.field, operator: "equals", value });
  };

  const applyValueFilter = () => {
    if (operator === "between") {
      const value = { min: minValue.trim(), max: maxValue.trim() };
      if (!value.min && !value.max) {
        onClear(fieldConfig.field);
      } else {
        onApply({ field: fieldConfig.field, operator: "between", value });
      }
    } else {
      const value = singleValue.trim();
      if (!value) {
        onClear(fieldConfig.field);
      } else {
        onApply({ field: fieldConfig.field, operator, value });
      }
    }
    setOpen(false);
  };

  const clearCurrentFilter = () => {
    onClear(fieldConfig.field);
    setOpen(false);
  };

  const handleValueKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      applyValueFilter();
    }
  };

  return (
    <PopoverRoot isOpen={open} onOpenChange={setOpen}>
      <PopoverTrigger
        aria-controls={open ? menuId : undefined}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`筛选 ${fieldConfig.label}`}
        className={hasActiveFilter || selectedValues.length > 0
          ? "output-invoice-collection-filter-menu__trigger output-invoice-collection-filter-menu__trigger--active"
          : "output-invoice-collection-filter-menu__trigger"}
      >
        <Filter aria-hidden="true" size={14} />
        <span>{fieldConfig.label}</span>
      </PopoverTrigger>
      {open ? (
      <PopoverContent className="output-invoice-collection-filter-menu__popover" containerPadding={12} offset={4} placement="bottom start">
        <PopoverDialog aria-label={`${fieldConfig.label}筛选与排序`} className="output-invoice-collection-filter-menu__dialog">
          <div
            aria-label={`${fieldConfig.label}筛选与排序`}
            className="output-invoice-collection-filter-menu__panel"
            id={menuId}
            onKeyDown={(event) => {
              if (event.key === "Escape") setOpen(false);
            }}
            role="menu"
          >
        <div className="output-invoice-collection-filter-menu__header">
          <div className="output-invoice-collection-filter-menu__title">{fieldConfig.label}</div>
          <div className="output-invoice-collection-filter-menu__subtitle">筛选项来自当前后端查询上下文</div>
        </div>
        <MenuAction onClick={() => onSort("asc")}>
          <ArrowUp aria-hidden="true" size={14} />
          <span>升序排序</span>
        </MenuAction>
        <MenuAction onClick={() => onSort("desc")}>
          <ArrowDown aria-hidden="true" size={14} />
          <span>降序排序</span>
        </MenuAction>
        <div className="output-invoice-collection-filter-menu__divider" role="separator" />
        {fieldConfig.mode === "enum_multi" ? (
          <>
            <MenuAction onClick={() => applyMulti(options.map((option) => option.value))}>全选</MenuAction>
            <MenuAction onClick={() => onClear(fieldConfig.field)}>清空</MenuAction>
            <div className="output-invoice-collection-filter-menu__divider" role="separator" />
            {options.length === 0 ? <DisabledChoice>暂无可选项</DisabledChoice> : null}
            {options.map((option) => (
              <button
                key={option.value}
                aria-checked={selectedSet.has(option.value)}
                className="output-invoice-collection-filter-menu__item"
                role="menuitemcheckbox"
                onClick={() => toggleMulti(option.value)}
                type="button"
              >
                <span aria-hidden="true" className="output-invoice-collection-filter-menu__checkmark">
                  {selectedSet.has(option.value) ? "✓" : ""}
                </span>
                <span>{optionLabel(option)}</span>
              </button>
            ))}
          </>
        ) : null}
        {fieldConfig.mode === "enum_single" ? (
          <>
            <MenuAction onClick={() => onClear(fieldConfig.field)}>清空</MenuAction>
            <div className="output-invoice-collection-filter-menu__divider" role="separator" />
            {options.length === 0 ? <DisabledChoice>暂无可选项</DisabledChoice> : null}
            {options.map((option) => (
              <button
                key={option.value}
                aria-checked={selectedSet.has(option.value)}
                className="output-invoice-collection-filter-menu__item"
                role="menuitemradio"
                onClick={() => applySingle(option.value)}
                type="button"
              >
                <span aria-hidden="true" className="output-invoice-collection-filter-menu__choice-dot">
                  {selectedSet.has(option.value) ? "●" : ""}
                </span>
                <span>{optionLabel(option)}</span>
              </button>
            ))}
          </>
        ) : null}
        {fieldConfig.mode !== "enum_multi" && fieldConfig.mode !== "enum_single" ? (
          <div className="output-invoice-collection-filter-menu__fields">
            <button className="output-invoice-collection-filter-menu__clear" onClick={clearCurrentFilter} role="menuitem" type="button">
              清空
            </button>
            {fieldConfig.mode === "text" ? (
              <>
                <label className="output-invoice-collection-filter-menu__field">
                  <span>匹配方式</span>
                  <select
                    value={operator === "equals" ? "equals" : "contains"}
                    onChange={(event) => setOperator(event.target.value as "contains" | "equals")}
                  >
                    <option value="contains">包含</option>
                    <option value="equals">等于</option>
                  </select>
                </label>
                <label className="output-invoice-collection-filter-menu__field">
                  <span>{`${fieldConfig.label}筛选值`}</span>
                  <input
                    autoFocus
                    value={singleValue}
                    onChange={(event) => setSingleValue(event.target.value)}
                    onKeyDown={handleValueKeyDown}
                  />
                </label>
              </>
            ) : null}
            {fieldConfig.mode === "money" || fieldConfig.mode === "date" ? (
              <>
                <label className="output-invoice-collection-filter-menu__field">
                  <span>匹配方式</span>
                  <select
                    value={operator === "equals" ? "equals" : "between"}
                    onChange={(event) => setOperator(event.target.value as "between" | "equals")}
                  >
                    <option value="between">区间</option>
                    <option value="equals">等于</option>
                  </select>
                </label>
                {operator === "equals" ? (
                  <label className="output-invoice-collection-filter-menu__field">
                    <span>{`${fieldConfig.label}筛选值`}</span>
                    <input
                      autoFocus
                      type={fieldConfig.mode === "date" ? "date" : "text"}
                      value={singleValue}
                      onChange={(event) => setSingleValue(event.target.value)}
                      onKeyDown={handleValueKeyDown}
                    />
                  </label>
                ) : (
                  <>
                    <label className="output-invoice-collection-filter-menu__field">
                      <span>{fieldConfig.mode === "date" ? `${fieldConfig.label}开始日期` : `${fieldConfig.label}最小值`}</span>
                      <input
                        autoFocus
                        type={fieldConfig.mode === "date" ? "date" : "text"}
                        value={minValue}
                        onChange={(event) => setMinValue(event.target.value)}
                        onKeyDown={handleValueKeyDown}
                      />
                    </label>
                    <label className="output-invoice-collection-filter-menu__field">
                      <span>{fieldConfig.mode === "date" ? `${fieldConfig.label}结束日期` : `${fieldConfig.label}最大值`}</span>
                      <input
                        type={fieldConfig.mode === "date" ? "date" : "text"}
                        value={maxValue}
                        onChange={(event) => setMaxValue(event.target.value)}
                        onKeyDown={handleValueKeyDown}
                      />
                    </label>
                  </>
                )}
              </>
            ) : null}
            <button className="output-invoice-collection-filter-menu__apply" onClick={applyValueFilter} type="button">
              应用筛选
            </button>
          </div>
        ) : null}
          </div>
        </PopoverDialog>
      </PopoverContent>
      ) : null}
    </PopoverRoot>
  );
}

function MenuAction({
  children,
  onClick,
}: {
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button className="output-invoice-collection-filter-menu__item" onClick={onClick} role="menuitem" type="button">
      {children}
    </button>
  );
}

function DisabledChoice({ children }: { children: ReactNode }) {
  return (
    <div
      aria-disabled="true"
      className="output-invoice-collection-filter-menu__item output-invoice-collection-filter-menu__item--disabled"
      role="menuitem"
    >
      {children}
    </div>
  );
}

function resolveSelectedValues(currentFilter?: OutputInvoiceCollectionFilterValue | null) {
  if (!currentFilter) {
    return [];
  }
  if ("values" in currentFilter && Array.isArray(currentFilter.values)) {
    return currentFilter.values;
  }
  if ("value" in currentFilter && typeof currentFilter.value === "string" && currentFilter.value) {
    return [currentFilter.value];
  }
  return [];
}
