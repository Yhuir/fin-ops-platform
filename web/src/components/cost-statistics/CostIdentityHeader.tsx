import { Button, Checkbox, PopoverContent, PopoverDialog, PopoverRoot, PopoverTrigger, SearchField } from "@heroui/react";
import { useState } from "react";

type Props = {
  label: string;
  options: string[];
  selected: string[];
  order: "asc" | "desc";
  onApply: (names: string[]) => void;
  onSort: (order: "asc" | "desc") => void;
};

/** Controlled presentation only; the page owns queries and pagination. */
export default function CostIdentityHeader({ label, options, selected, order, onApply, onSort }: Props) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const visible = options.filter(name => (name || "未填写").toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  return <span className="cost-identity-header">
    <PopoverRoot isOpen={open} onOpenChange={next => {
      if (next) { setDraft(selected); setSearch(""); }
      setOpen(next);
    }}>
      <PopoverTrigger className={`cost-identity-filter${selected.length ? " is-active" : ""}`} aria-label={`筛选${label}${selected.length ? `，已选${selected.length}项` : ""}`}>
        {label}<span aria-hidden="true">▾</span>{selected.length > 0 ? <span>{selected.length}</span> : null}
      </PopoverTrigger>
      <PopoverContent className="column-filter-popover" containerPadding={12} maxHeight={380} offset={8} placement="bottom start">
        <PopoverDialog aria-label={`筛选${label}`} className="column-filter-dialog">
          <SearchField aria-label={`搜索${label}选项`} onChange={setSearch} value={search}>
            <SearchField.Group className="column-filter-search-group">
              <SearchField.SearchIcon /><SearchField.Input placeholder="搜索选项" /><SearchField.ClearButton aria-label="清空选项搜索" />
            </SearchField.Group>
          </SearchField>
          <div className="column-filter-option-list" role="group" aria-label={`${label}选项`}>
            {visible.length === 0 ? <span className="column-filter-state">暂无可选项</span> : null}
            {visible.map(name => <Checkbox key={name} className="column-filter-option" slot={null} isSelected={draft.includes(name)} onChange={checked => setDraft(current => checked ? [...current, name] : current.filter(value => value !== name))}>
              <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><span>{name || "未填写"}</span>
            </Checkbox>)}
          </div>
          <div className="column-filter-actions">
            <Button size="sm" variant="tertiary" onPress={() => setDraft([])}>清空</Button>
            <Button size="sm" onPress={() => { onApply([...new Set(draft)].sort()); setOpen(false); }}>应用</Button>
          </div>
        </PopoverDialog>
      </PopoverContent>
    </PopoverRoot>
    <span aria-hidden="true">/</span>
    <span className="cost-identity-time">时间<button type="button" aria-label={`时间${order === "desc" ? "倒序" : "正序"}，点击切换${order === "desc" ? "正序" : "倒序"}`} title={order === "desc" ? "最新在前" : "最早在前"} onClick={() => onSort(order === "desc" ? "asc" : "desc")}>{order === "desc" ? "↓" : "↑"}</button></span>
  </span>;
}
