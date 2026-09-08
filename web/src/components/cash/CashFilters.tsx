import { Button, Checkbox, Input, Popover } from "@heroui/react";
import { useCallback, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { FinanceTablePagination } from "../common/FinanceTable";

export type CashFilterValue = string | null;
export type CashFilterOption<T extends CashFilterValue = CashFilterValue> = { value: T; label: string };

// Empty tables have no active cell for the native collection to restore. The
// stable cash trigger owns Escape/explicit-close focus, after the dialog exits.
// Outside dismissal does not request focus and cannot steal another control's.
function useCashPopoverFocus() {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const restoreOnClose = useRef(false);
  const dialogRef = useCallback((node: HTMLElement | null) => {
    if (!node) return;
    return () => {
      if (!restoreOnClose.current) return;
      restoreOnClose.current = false;
      queueMicrotask(() => triggerRef.current?.focus({ preventScroll: true }));
    };
  }, []);
  return {
    triggerRef, dialogRef,
    requestRestore: () => { restoreOnClose.current = true; },
    onKeyDownCapture: (event: KeyboardEvent) => { if (event.key === "Escape" && !event.nativeEvent.isComposing) restoreOnClose.current = true; },
  };
}

/** Presentation only: the owning view supplies candidates and applies one query. */
export function CashFilterPopover<T extends CashFilterValue>({ label, value, onApply, options, column = false,
  loading = false, error, onReload, onOpenChange, onSearch, page, pageSize = 50, total, onPageChange, selected = [],
}: {
  label: string; value: T[]; onApply: (value: T[], selected: CashFilterOption<T>[]) => string | null | void;
  options: CashFilterOption<T>[]; selected?: CashFilterOption<T>[]; column?: boolean;
  loading?: boolean; error?: string | null; onReload?: () => void; onOpenChange?: (open: boolean) => void;
  onSearch?: (search: string) => void; page?: number; pageSize?: number; total?: number; onPageChange?: (page: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<T[]>(value);
  const [search, setSearch] = useState("");
  const [known, setKnown] = useState<CashFilterOption<T>[]>(selected);
  const [applyError, setApplyError] = useState<string | null>(null);
  const focus = useCashPopoverFocus();
  const visible = onSearch ? options : options.filter(option => option.label.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const changeOpen = (next: boolean) => {
    if (next) { setDraft([...value]); setKnown(selected); setSearch(""); setApplyError(null); onSearch?.(""); }
    setOpen(next); onOpenChange?.(next);
  };
  const remember = (items: CashFilterOption<T>[]) => setKnown(previous => [...previous.filter(item => !items.some(next => next.value === item.value)), ...items]);
  const chosen = draft.map(item => options.find(option => option.value === item) ?? known.find(option => option.value === item));
  return <span className="cash-filter-anchor" onClick={event => event.stopPropagation()} onKeyDown={event => event.stopPropagation()} onKeyDownCapture={event => { if (open) focus.onKeyDownCapture(event); }} onFocus={event => event.stopPropagation()}>
    <Popover isOpen={open} onOpenChange={changeOpen}>
      <Button ref={focus.triggerRef} size="sm" variant="tertiary" className={column ? "cash-column-filter" : "cash-filter-button"}
        aria-label={`筛选${label}`} data-active={value.length > 0 || undefined}>
        {column ? <span aria-hidden="true">⌄</span> : label}<span className="cash-filter-count" aria-hidden="true">{value.length || ""}</span>
      </Button>
      <Popover.Content className="cash-filter-popover" placement="bottom start" offset={4}>
        <Popover.Dialog ref={focus.dialogRef} aria-label={`筛选${label}`}>
          <Popover.Heading>{label}</Popover.Heading>
          <Input aria-label={`搜索${label}选项`} placeholder="搜索选项" value={search} onChange={event => { setSearch(event.target.value); onSearch?.(event.target.value); }} />
          <div className="cash-filter-tools"><Button size="sm" variant="ghost" isDisabled={loading || Boolean(error)} onPress={() => {
            setDraft(old => [...new Set([...old, ...visible.map(item => item.value)])]); remember(visible); setApplyError(null);
          }}>{onPageChange ? "全选本页" : search ? "全选匹配项" : "全选"}</Button><Button size="sm" variant="ghost" onPress={() => { setDraft([]); setApplyError(null); }}>清空</Button><span>已选 {draft.length}</span></div>
          <div className="cash-filter-options">
            {loading ? <p role="status">正在读取选项…</p> : error ? <div role="alert"><p>{error}</p>{onReload && <Button size="sm" variant="tertiary" onPress={onReload}>重新读取</Button>}</div> : visible.length ? visible.map(option =>
              <Checkbox slot={null} key={JSON.stringify(option.value)} isSelected={draft.includes(option.value)} onChange={checked => {
                setDraft(old => checked ? [...old, option.value] : old.filter(item => item !== option.value)); remember([option]); setApplyError(null);
              }}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><Checkbox.Content>{option.label}</Checkbox.Content></Checkbox>) : <p>没有匹配选项。</p>}
          </div>
          {onPageChange && page !== undefined && total !== undefined && <FinanceTablePagination page={page} pageSize={pageSize} total={total} onPageChange={onPageChange} compact isDisabled={loading} />}
          {chosen.some(item => item && !visible.some(option => option.value === item.value)) && <details className="cash-filter-selected"><summary>查看已选项</summary>{chosen.map((item, index) => <div key={index}>{item?.label ?? "已选择的历史项"}</div>)}</details>}
          {draft.length > 50 && <p role="alert">每列最多选择 50 项；查看全部请清空此列限制。</p>}
          {applyError && <p role="alert">{applyError}</p>}
          <div className="cash-filter-footer"><Button size="sm" variant="tertiary" onPress={() => { focus.requestRestore(); changeOpen(false); }}>取消</Button><Button size="sm" isDisabled={draft.length > 50} onPress={() => {
            const error = onApply(draft, chosen.filter((item): item is CashFilterOption<T> => item !== undefined));
            if (typeof error === "string") { setApplyError(error); return; }
            focus.requestRestore(); changeOpen(false);
          }}>应用</Button></div>
        </Popover.Dialog>
      </Popover.Content>
    </Popover>
  </span>;
}

export function CashColumnHeader({ label, children }: { label: string; children?: ReactNode }) {
  return <span className="cash-column-heading"><span>{label}</span>{children}</span>;
}

export function CashTextFilter({ label, value, onApply }: { label: string; value: string; onApply: (value: string) => string | null | void }) {
  const [open, setOpen] = useState(false); const [draft, setDraft] = useState(value);
  const [applyError, setApplyError] = useState<string | null>(null);
  const focus = useCashPopoverFocus();
  return <span className="cash-filter-anchor" onClick={event => event.stopPropagation()} onKeyDown={event => event.stopPropagation()} onKeyDownCapture={event => { if (open) focus.onKeyDownCapture(event); }} onFocus={event => event.stopPropagation()}><Popover isOpen={open} onOpenChange={next => { if (next) { setDraft(value); setApplyError(null); } setOpen(next); }}>
    <Button ref={focus.triggerRef} size="sm" variant="tertiary" className="cash-column-filter" aria-label={`筛选${label}`} data-active={Boolean(value) || undefined}>⌄</Button>
    <Popover.Content className="cash-filter-popover" placement="bottom start" offset={4}><Popover.Dialog ref={focus.dialogRef} aria-label={`筛选${label}`}>
      <Popover.Heading>{label}</Popover.Heading><form onSubmit={event => {
        event.preventDefault(); const error = onApply(draft.trim());
        if (typeof error === "string") { setApplyError(error); return; }
        focus.requestRestore(); setOpen(false);
      }}>
        <Input aria-label={`${label}精确名称`} placeholder="输入完整名称" value={draft} onChange={event => { setDraft(event.target.value); setApplyError(null); }} />
        {applyError && <p role="alert">{applyError}</p>}
        <div className="cash-filter-footer"><Button size="sm" variant="tertiary" onPress={() => { setDraft(""); setApplyError(null); }}>清空</Button><Button size="sm" type="submit">应用</Button></div>
      </form></Popover.Dialog></Popover.Content>
  </Popover></span>;
}

/** Only for a supported sort key that has no corresponding visible column. */
export function CashSortMenu({ sort, order, options, onChange }: {
  sort: string; order: string; options: { value: string; label: string }[];
  onChange: (sort: string, order: "asc" | "desc") => void;
}) {
  const [open, setOpen] = useState(false);
  const focus = useCashPopoverFocus();
  return <span className="cash-filter-anchor" onKeyDownCapture={event => { if (open) focus.onKeyDownCapture(event); }}><Popover isOpen={open} onOpenChange={setOpen}><Button ref={focus.triggerRef} size="sm" variant="tertiary" className="cash-filter-button" aria-label="其他排序">排序 ⌄</Button>
    <Popover.Content className="cash-filter-popover cash-sort-popover" placement="bottom start" offset={4}><Popover.Dialog ref={focus.dialogRef} aria-label="其他排序">
      <Popover.Heading>其他排序</Popover.Heading>{options.flatMap(option => (["asc", "desc"] as const).map(direction => <Button key={`${option.value}-${direction}`} size="sm" variant="ghost" aria-pressed={sort === option.value && order === direction} onPress={() => { onChange(option.value, direction); focus.requestRestore(); setOpen(false); }}>{option.label} · {direction === "asc" ? "升序 ↑" : "降序 ↓"}</Button>))}
    </Popover.Dialog></Popover.Content></Popover></span>;
}
