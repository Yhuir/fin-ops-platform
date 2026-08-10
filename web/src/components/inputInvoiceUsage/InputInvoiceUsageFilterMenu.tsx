import { PopoverContent, PopoverDialog, PopoverRoot, PopoverTrigger } from "@heroui/react";
import { ArrowDown, ArrowUp, Filter } from "lucide-react";
import type { ReactNode } from "react";
import { useId, useMemo, useState } from "react";

export type InputInvoiceUsageFilterMode = "text" | "enum_single" | "enum_multi" | "date" | "money";

export type InputInvoiceUsageFieldConfig = {
  field: string;
  label: string;
  mode: InputInvoiceUsageFilterMode;
  sortable?: boolean;
};

export type InputInvoiceUsageFilterOption = {
  value: string;
  label: string;
  count?: number;
};

export type InputInvoiceUsageFilterValue =
  | { field: string; operator: "in"; values: string[] }
  | { field: string; operator: "equals"; value: string }
  | { field: string; operator: string; value?: string; values?: string[] };

type InputInvoiceUsageFilterMenuProps = {
  fieldConfig: InputInvoiceUsageFieldConfig;
  currentFilter?: InputInvoiceUsageFilterValue | null;
  options: InputInvoiceUsageFilterOption[];
  onApply: (filter: InputInvoiceUsageFilterValue) => void;
  onClear: (field: string) => void;
  onSort: (direction: "asc" | "desc") => void;
};

export default function InputInvoiceUsageFilterMenu({
  fieldConfig,
  currentFilter,
  options,
  onApply,
  onClear,
  onSort,
}: InputInvoiceUsageFilterMenuProps) {
  const menuId = useId();
  const [open, setOpen] = useState(false);
  const selectedValues = useMemo(() => resolveSelectedValues(currentFilter), [currentFilter]);
  const selectedSet = useMemo(() => new Set(selectedValues), [selectedValues]);

  const optionLabel = (option: InputInvoiceUsageFilterOption) => (
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

  return (
    <PopoverRoot isOpen={open} onOpenChange={setOpen}>
      <PopoverTrigger
        aria-controls={open ? menuId : undefined}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`筛选 ${fieldConfig.label}`}
        className={selectedValues.length > 0 ? "input-invoice-usage-filter-menu__trigger input-invoice-usage-filter-menu__trigger--active" : "input-invoice-usage-filter-menu__trigger"}
      >
        <Filter aria-hidden="true" size={14} />
        <span>{fieldConfig.label}</span>
      </PopoverTrigger>
      {open ? (
        <PopoverContent
          className="input-invoice-usage-filter-menu__popover"
          containerPadding={12}
          offset={4}
          placement="bottom start"
        >
          <PopoverDialog aria-label={`${fieldConfig.label}筛选与排序`} className="input-invoice-usage-filter-menu__dialog">
            <div
              aria-label={`${fieldConfig.label}筛选与排序`}
              className="input-invoice-usage-filter-menu__panel"
              id={menuId}
              onKeyDown={(event) => {
                if (event.key === "Escape") setOpen(false);
              }}
              role="menu"
            >
              <div className="input-invoice-usage-filter-menu__header">
                <div className="input-invoice-usage-filter-menu__title">{fieldConfig.label}</div>
              </div>
              <MenuAction onClick={() => onSort("asc")}>
                <ArrowUp aria-hidden="true" size={14} />
                <span>升序排序</span>
              </MenuAction>
              <MenuAction onClick={() => onSort("desc")}>
                <ArrowDown aria-hidden="true" size={14} />
                <span>降序排序</span>
              </MenuAction>
              <div className="input-invoice-usage-filter-menu__divider" role="separator" />
              {fieldConfig.mode === "enum_multi" ? (
                <>
                  <MenuAction onClick={() => applyMulti(options.map((option) => option.value))}>全选</MenuAction>
                  <MenuAction onClick={() => onClear(fieldConfig.field)}>清空</MenuAction>
                  <div className="input-invoice-usage-filter-menu__divider" role="separator" />
                  {options.length === 0 ? <DisabledChoice>暂无可选项</DisabledChoice> : null}
                  {options.map((option) => (
                    <button
                      key={option.value}
                      aria-checked={selectedSet.has(option.value)}
                      className="input-invoice-usage-filter-menu__item"
                      onClick={() => toggleMulti(option.value)}
                      role="menuitemcheckbox"
                      type="button"
                    >
                      <span aria-hidden="true" className="input-invoice-usage-filter-menu__checkmark">
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
                  <div className="input-invoice-usage-filter-menu__divider" role="separator" />
                  {options.length === 0 ? <DisabledChoice>暂无可选项</DisabledChoice> : null}
                  {options.map((option) => (
                    <button
                      key={option.value}
                      aria-checked={selectedSet.has(option.value)}
                      className="input-invoice-usage-filter-menu__item"
                      onClick={() => applySingle(option.value)}
                      role="menuitemradio"
                      type="button"
                    >
                      <span aria-hidden="true" className="input-invoice-usage-filter-menu__radio">
                        {selectedSet.has(option.value) ? "●" : ""}
                      </span>
                      <span>{optionLabel(option)}</span>
                    </button>
                  ))}
                </>
              ) : null}
              {fieldConfig.mode !== "enum_multi" && fieldConfig.mode !== "enum_single" ? (
                <>
                  <MenuAction onClick={() => onClear(fieldConfig.field)}>清空</MenuAction>
                  <DisabledChoice>该字段的输入控件由页面查询区提供</DisabledChoice>
                </>
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
    <button className="input-invoice-usage-filter-menu__item" onClick={onClick} role="menuitem" type="button">
      {children}
    </button>
  );
}

function DisabledChoice({ children }: { children: ReactNode }) {
  return (
    <div aria-disabled="true" className="input-invoice-usage-filter-menu__item input-invoice-usage-filter-menu__item--disabled" role="menuitem">
      {children}
    </div>
  );
}

function resolveSelectedValues(currentFilter?: InputInvoiceUsageFilterValue | null) {
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
