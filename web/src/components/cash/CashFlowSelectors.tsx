import { Button } from "@heroui/react";
import { useEffect, useState } from "react";
import { useCashQuery } from "../../features/cash/hooks";
import { FinanceTablePagination } from "../common/FinanceTable";
import { CashInput, CashNotice, CashSelect } from "./CashUi";
import type { CashPageRows } from "./CashItems.types";
import { cashCategoryGroupLabels, type CashCategorySetting, type CashProjectsPage } from "./CashSettingsTypes";
import { CashFilterPopover, type CashFilterOption, type CashFilterValue } from "./CashFilters";
import type { CashQueryParams } from "../../features/cash/api";

type ConfigurationReference = { id: string; name: string; group?: string; enabled?: boolean };
type ConfigurationRow = ConfigurationReference & { label?: string; bank_name?: string };

type ConfigurationSelectProps = {
  name: "accounts" | "categories" | "bill-labels"; label: string; value: string; onChange: (value: string, selected: ConfigurationReference | null) => void;
  selected?: ConfigurationReference | null; group?: string; groups?: string[]; required?: boolean; disabled?: boolean;
};
export function CashConfigurationSelect(props: ConfigurationSelectProps) {
  return <CashConfigurationSelectInput key={JSON.stringify([props.name, props.group, props.groups])} {...props} />;
}

function CashConfigurationSelectInput({ name, label, value, onChange, selected, group, groups, required, disabled }: ConfigurationSelectProps) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [keyword, setKeyword] = useState("");
  const [remembered, setRemembered] = useState<ConfigurationReference | null>(null);
  const allowedGroups = groups ?? (name === "categories" && group ? group === "turnover" ? [group] : [group, "turnover"] : undefined);
  useEffect(() => {
    if (search.trim() === keyword) return;
    const timer = window.setTimeout(() => { setKeyword(search.trim()); setPage(1); }, 250);
    return () => window.clearTimeout(timer);
  }, [search, keyword]);
  const query = useCashQuery<CashPageRows<ConfigurationRow>>(`/settings/${name}`, {
    enabled: true, page, page_size: 100, keyword, groups: allowedGroups,
  });
  const rows = query.data?.rows ?? [];
  const currentRow = rows.find(row => row.id === value);
  const original = selected?.id === value ? selected : null;
  const known = currentRow ?? (remembered?.id === value ? remembered : null) ?? original;
  const needsExact = name === "categories" && Boolean(value) && !known?.group && !query.loading;
  const exact = useCashQuery<CashPageRows<CashCategorySetting>>(needsExact ? "/settings/categories" : null, { category_id: value || undefined });
  const exactRow = exact.data?.rows.find(row => row.id === value);
  const chosen = known?.group || name !== "categories" ? known : exactRow;
  useEffect(() => {
    const row: ConfigurationRow | undefined = currentRow ?? exactRow;
    if (row) {
      const next = { id: row.id, name: name === "bill-labels" ? `${row.bank_name} · ${row.label}` : row.name, group: row.group, enabled: row.enabled };
      setRemembered(previous => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
    }
  }, [currentRow, exactRow, name]);
  const reference = (row: ConfigurationRow): ConfigurationReference => ({ id: row.id, name: name === "bill-labels" ? `${row.bank_name} · ${row.label}` : row.name, group: row.group, enabled: row.enabled });
  const candidates: ConfigurationReference[] = rows.map(reference);
  if (chosen && !candidates.some(row => row.id === chosen.id)) candidates.unshift(chosen);
  const categoryError = name !== "categories" || !value ? undefined
    : exact.error ? exact.error.message
    : !chosen?.group ? needsExact && !exact.loading && exact.data ? "所选费用类型不存在，请重新选择。" : "正在读取所选费用类型…"
    : !original && chosen.enabled === false ? "所选费用类型已停用，请重新选择。"
    : !original && allowedGroups && !allowedGroups.includes(chosen.group) ? "所选费用类型不适用于当前收付方向，请重新选择。" : undefined;
  const options = candidates.map(row => ({ value: row.id, label: row.name + (original?.id === row.id && !rows.some(candidate => candidate.id === row.id) ? "（原值）" : ""),
    disabled: !original && row.enabled === false,
    group: name === "categories" && row.group ? { id: row.group, label: cashCategoryGroupLabels[row.group as keyof typeof cashCategoryGroupLabels] } : undefined,
  }));
  if (name === "categories") options.sort((a, b) => Object.keys(cashCategoryGroupLabels).indexOf(a.group?.id ?? "") - Object.keys(cashCategoryGroupLabels).indexOf(b.group?.id ?? ""));
  return <div className="cash-config-select">
    <CashSelect label={label} value={value} onChange={next => {
      const row = candidates.find(candidate => candidate.id === next) ?? null;
      setRemembered(row); onChange(next, row);
    }} options={options} required={required} disabled={disabled} validationError={categoryError}>
      <CashInput label={`搜索${label}`} value={search} onChange={setSearch} />
      {(query.loading || search.trim() !== keyword) && <p role="status">正在读取{label}…</p>}
      {query.data && query.data.pagination.total > 100 &&
        <FinanceTablePagination page={page} pageSize={100} total={query.data.pagination.total} onPageChange={setPage} compact isDisabled={query.loading} />}
    </CashSelect>
    <CashNotice error={query.error?.message} />
    {categoryError && <CashNotice error={exact.loading || query.loading ? undefined : categoryError}>{categoryError}</CashNotice>}
    {query.error && <Button size="sm" variant="tertiary" onPress={query.reload}>重新读取{label}</Button>}
    {exact.error && <Button size="sm" variant="tertiary" onPress={exact.reload}>重新读取所选费用类型</Button>}
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
