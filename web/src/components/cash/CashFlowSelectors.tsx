import { Button } from "@heroui/react";
import { useState } from "react";
import { useCashQuery } from "../../features/cash/hooks";
import { FinanceTablePagination } from "../common/FinanceTable";
import { CashInput, CashNotice, CashSelect } from "./CashUi";
import type { CashPageRows } from "./CashItems.types";
import type { CashProjectsPage } from "./CashSettingsTypes";

export function CashConfigurationSelect({ name, label, value, onChange, selected, group, required, disabled }: {
  name: "accounts" | "categories" | "bill-labels"; label: string; value: string; onChange: (value: string) => void;
  selected?: { id: string; name: string } | null; group?: string; required?: boolean; disabled?: boolean;
}) {
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState("");
  const query = useCashQuery<CashPageRows<{ id: string; name?: string; label?: string; bank_name?: string; group?: string }>>(`/settings/${name}`, {
    enabled: true, page, page_size: 100, keyword,
  });
  const options = query.data ? query.data.rows.filter(row => !group || row.group === group || row.group === "turnover")
    .map(row => ({ value: row.id, label: name === "bill-labels" ? `${row.bank_name} · ${row.label}` : row.name! })) : [];
  if (selected && !options.some(option => option.value === selected.id)) options.unshift({ value: selected.id, label: `${selected.name}（原值）` });
  return <div className="cash-config-select">
    <CashSelect label={label} value={value} onChange={onChange} options={options} required={required} disabled={disabled || query.loading} />
    <CashNotice error={query.error?.message} />
    {query.error && <Button size="sm" variant="tertiary" onPress={query.reload}>重新读取{label}</Button>}
    {query.data && query.data.pagination.total === 0 && <small>暂无启用的{label}，请在基础设置中添加。</small>}
    {query.data && (query.data.pagination.total > 100 || keyword) && <>
      <CashInput label={`搜索${label}`} value={keyword} onChange={value => { setKeyword(value); setPage(1); }} />
      <FinanceTablePagination page={page} pageSize={100} total={query.data.pagination.total} onPageChange={setPage} compact />
    </>}
  </div>;
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
