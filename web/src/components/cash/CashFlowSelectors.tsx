import { Button } from "@heroui/react";
import { useEffect, useState } from "react";
import { useCashQuery } from "../../features/cash/hooks";
import { FinanceTablePagination } from "../common/FinanceTable";
import { CashInput, CashNotice, CashSelect } from "./CashUi";
import type { CashPageRows } from "./CashItems.types";
import type { CashProjectsPage } from "./CashSettingsTypes";
import { CashFilterPopover, type CashFilterOption, type CashFilterValue } from "./CashFilters";
import type { CashQueryParams } from "../../features/cash/api";

export function CashConfigurationSelect({ name, label, value, onChange, selected, group, required, disabled }: {
  name: "accounts" | "categories" | "bill-labels"; label: string; value: string; onChange: (value: string, selected: { id: string; name: string } | null) => void;
  selected?: { id: string; name: string } | null; group?: string; required?: boolean; disabled?: boolean;
}) {
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState("");
  const query = useCashQuery<CashPageRows<{ id: string; name?: string; label?: string; bank_name?: string; group?: string }>>(`/settings/${name}`, {
    enabled: true, page, page_size: 100, keyword,
    groups: name === "categories" && group ? group === "turnover" ? [group] : [group, "turnover"] : undefined,
  });
  const options = query.data ? query.data.rows.map(row => ({ value: row.id, label: name === "bill-labels" ? `${row.bank_name} · ${row.label}` : row.name! })) : [];
  if (selected && !options.some(option => option.value === selected.id)) options.unshift({ value: selected.id, label: `${selected.name}（原值）` });
  return <div className="cash-config-select">
    <CashSelect label={label} value={value} onChange={value => onChange(value, value ? { id: value, name: options.find(option => option.value === value)!.label } : null)} options={options} required={required} disabled={disabled}>
      <CashInput label={`搜索${label}`} value={keyword} onChange={value => { setKeyword(value); setPage(1); }} />
      {query.loading && <p role="status">正在读取{label}…</p>}
      {query.data && query.data.pagination.total > 100 &&
      <FinanceTablePagination page={page} pageSize={100} total={query.data.pagination.total} onPageChange={setPage} compact />
      }
    </CashSelect>
    <CashNotice error={query.error?.message} />
    {query.error && <Button size="sm" variant="tertiary" onPress={query.reload}>重新读取{label}</Button>}
    {query.data && query.data.pagination.total === 0 && <small>暂无启用的{label}，请在基础设置中添加。</small>}
  </div>;
}

function useCandidateSearch() {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState(""); const [keyword, setKeyword] = useState(""); const [page, setPage] = useState(1);
  useEffect(() => {
    if (!open || search.trim() === keyword) return;
    const timer = window.setTimeout(() => { setKeyword(search.trim()); setPage(1); }, 250);
    return () => window.clearTimeout(timer);
  }, [open, search, keyword]);
  return { open, onOpenChange: (next: boolean) => { setOpen(next); if (next) { setSearch(""); setKeyword(""); setPage(1); } },
    onSearch: setSearch, keyword, page, onPageChange: setPage, searching: search.trim() !== keyword };
}

type CashResourceFilterProps = {
  label: string; value: CashFilterValue[]; selected?: CashFilterOption[]; column?: boolean;
  onApply: (value: CashFilterValue[], selected: CashFilterOption[]) => string | null | void;
};

export function CashConfigurationFilter({ name, ...props }: CashResourceFilterProps & { name: "accounts" | "categories" | "bill-labels" }) {
  const search = useCandidateSearch();
  const pageSize = name === "accounts" ? 50 : 49;
  const query = useCashQuery<CashPageRows<{ id: string; name?: string; label?: string; bank_name?: string }>>(search.open ? `/settings/${name}` : null,
    { page: search.page, page_size: pageSize, keyword: search.keyword });
  const options: CashFilterOption[] = query.data?.rows.map(row => ({ value: row.id, label: name === "bill-labels" ? `${row.bank_name} · ${row.label}` : row.name! })) ?? [];
  if (name !== "accounts") options.unshift({ value: null, label: name === "categories" ? "未分类" : "无账单" });
  return <CashFilterPopover {...props} options={options} loading={query.loading || search.searching} error={query.error?.message} onReload={query.reload}
    onOpenChange={search.onOpenChange} onSearch={search.onSearch} page={search.page} pageSize={pageSize} total={query.data?.pagination.total} onPageChange={search.onPageChange} />;
}

export function CashHistoricalProjectFilter({ scope, ...props }: CashResourceFilterProps & { scope: CashQueryParams }) {
  const search = useCandidateSearch();
  const query = useCashQuery<CashPageRows<{ id: string; name: string }>>(search.open ? "/reports/project-options" : null,
    { ...scope, page: search.page, page_size: 49, keyword: search.keyword });
  return <CashFilterPopover {...props} options={[{ value: null, label: "无项目" }, ...(query.data?.rows.map(row => ({ value: row.id, label: row.name })) ?? [])]}
    loading={query.loading || search.searching} error={query.error?.message} onReload={query.reload} onOpenChange={search.onOpenChange}
    onSearch={search.onSearch} page={search.page} pageSize={49} total={query.data?.pagination.total} onPageChange={search.onPageChange} />;
}

export function CashProjectPicker({ onSelect, onClose }: {
  onSelect: (project: { id: string; name_snapshot: string }) => void; onClose: () => void;
}) {
  const [search, setSearch] = useState(""); const [keyword, setKeyword] = useState(""); const [page, setPage] = useState(1);
  const query = useCashQuery<CashProjectsPage>("/projects", { purpose: "selection", keyword, page, page_size: 20 });
  return <section className="cash-picker" aria-label="选择现金项目">
    <form className="cash-toolbar" onSubmit={event => { event.preventDefault(); setKeyword(search); setPage(1); }}>
      <CashInput label="项目名称或编号" value={search} onChange={setSearch} />
      <Button type="submit" variant="secondary" size="sm">查询</Button><Button size="sm" variant="tertiary" onPress={onClose}>取消</Button>
    </form>
    <CashNotice error={query.error?.message} />
    {query.loading && <p role="status">正在读取 OA 项目…</p>}
    {query.error && <Button size="sm" variant="tertiary" onPress={query.reload}>重新读取</Button>}
    {query.data && <><ul className="cash-choice-list">{query.data.rows.map(row => <li key={row.id}>
      <Button size="sm" variant="tertiary" isDisabled={!row.selectable} onPress={() => onSelect({ id: row.id, name_snapshot: row.name })}>{row.name}</Button>
      <small>{row.stage_name === null ? "未提供状态" : row.stage_name}</small>
    </li>)}</ul>{query.data.rows.length === 0 && <p>没有符合条件的项目。请检查基础设置中勾选的项目阶段。</p>}
      <FinanceTablePagination page={page} pageSize={20} total={query.data.total} onPageChange={setPage} compact /></>}
  </section>;
}
