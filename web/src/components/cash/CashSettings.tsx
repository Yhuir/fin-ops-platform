import { Button, Checkbox } from "@heroui/react";
import { useEffect, useState } from "react";

import { useCashMutation, useCashQuery, useCashScope } from "../../features/cash/hooks";
import { cashAmount, type CashPersonalSetting } from "./CashItems.types";
import AppDrawer from "../common/AppDrawer";
import { FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTablePagination, FinanceTableRow } from "../common/FinanceTable";
import { CashInput, CashNotice, CashSelect, CashTabs } from "./CashUi";
import { CashColumnHeader, CashFilterPopover } from "./CashFilters";
import type { CashTasksPage } from "./CashTasksTypes";
import type { CashAccountSetting, CashBillLabelSetting, CashCategorySetting, CashProjectSelection, CashProjectsPage } from "./CashSettingsTypes";
import { cashCategoryGroupLabels, cashProjectUnavailableLabels } from "./CashSettingsTypes";
import { CashItemEditor } from "./CashItems";
import { useCashTaskSettingsCloseGuard } from "./CashTaskSettingsCloseGuard";

const settingTabs = [
  { id: "accounts", label: "现金账户与期初" },
  { id: "categories", label: "费用类型" },
  { id: "projects", label: "OA 项目与可选阶段" },
  { id: "guide", label: "支付办理说明" },
];

type AccountCriteria = { page: number; keyword: string; enabled: string; order: "asc" | "desc" };
type CategoryCriteria = AccountCriteria & { groups: string[] };
type ProjectCriteria = { page: number; keyword: string; stages: (string | null)[]; selectable: string };
export type CashSettingsCriteria = { tab: string; accounts: AccountCriteria; categories: CategoryCriteria; projects: ProjectCriteria; guide: string };
export function initialCashSettingsCriteria(): CashSettingsCriteria {
  return { tab: "accounts", accounts: { page: 1, keyword: "", enabled: "", order: "asc" },
    categories: { page: 1, keyword: "", enabled: "", groups: [], order: "asc" },
    projects: { page: 1, keyword: "", stages: [], selectable: "" }, guide: "" };
}
export default function CashSettings({ initialCriteria, onCriteriaChange }: { initialCriteria?: CashSettingsCriteria; onCriteriaChange?: (value: CashSettingsCriteria) => void }) {
  const [initial] = useState(() => initialCriteria ?? initialCashSettingsCriteria());
  const [tab, setTab] = useState(initial.tab); const [accounts, setAccounts] = useState(initial.accounts);
  const [categories, setCategories] = useState(initial.categories); const [projects, setProjects] = useState(initial.projects); const [guide, setGuide] = useState(initial.guide);
  useEffect(() => { onCriteriaChange?.({ tab, accounts, categories, projects, guide }); }, [tab, accounts, categories, projects, guide, onCriteriaChange]);
  return <>
    <CashTabs value={tab} onChange={setTab} tabs={settingTabs} />
    <div className="cash-scroll-content">{tab === "accounts" && <><CashAccounts initial={accounts} onChange={setAccounts} /><CashPersonalOpening /></>}
    {tab === "categories" && <CashCategories initial={categories} onChange={setCategories} />}
    {tab === "projects" && <CashProjectSettings initial={projects} onChange={setProjects} />}
    {tab === "guide" && <CashPaymentGuide keyword={guide} onChange={setGuide} />}</div>
  </>;
}

function CashAccounts({ initial, onChange }: { initial: AccountCriteria; onChange: (value: AccountCriteria) => void }) {
  const { revision } = useCashScope();
  const [page, setPage] = useState(initial.page);
  const [keyword, setKeyword] = useState(initial.keyword);
  const [search, setSearch] = useState(initial.keyword);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [order, setOrder] = useState(initial.order);
  const [editing, setEditing] = useState<CashAccountSetting | "new" | null>(null);
  useEffect(() => { onChange({ page, keyword, enabled, order }); }, [page, keyword, enabled, order, onChange]);
  const query = useCashQuery<CashTasksPage<CashAccountSetting>>("/settings/accounts", { page, page_size: 50, sort: "name", order, keyword: keyword || undefined, enabled: enabled || undefined }, revision);
  return <section className="cash-section" aria-label="现金账户">
    <form className="cash-toolbar" onSubmit={(event) => { event.preventDefault(); setKeyword(search.trim()); setPage(1); }}>
      <CashInput label="账户名称" value={search} onChange={setSearch} placeholder="搜索账户" />
      <Button type="submit" variant="secondary">查询</Button>
      <Button variant="tertiary" onPress={() => { setKeyword(""); setSearch(""); setEnabled(""); setOrder("asc"); setPage(1); }}>重置</Button>
      <Button variant="tertiary" onPress={query.reload} isDisabled={query.loading}>刷新</Button>
      <Button onPress={() => setEditing("new")}>新增账户</Button>
    </form>
    <CashNotice error={query.error?.message} />
    <FinanceTable ariaLabel="现金账户" minWidth={900} sortDescriptor={{ column: "name", direction: order === "asc" ? "ascending" : "descending" }} onSortChange={value => { setOrder(value.direction === "ascending" ? "asc" : "desc"); setPage(1); }} footer={<FinanceTablePagination page={page} pageSize={50} total={query.data?.pagination.total ?? 0} onPageChange={setPage} isDisabled={query.loading || Boolean(query.error)} />}>
      <FinanceTableHeader>
        <FinanceTableColumn id="name" isRowHeader allowsSorting>账户名称</FinanceTableColumn><FinanceTableColumn id="kind">类型</FinanceTableColumn><FinanceTableColumn id="opening_date">起算日期</FinanceTableColumn><FinanceTableColumn id="opening_amount">确认期初</FinanceTableColumn>
        <FinanceTableColumn id="enabled"><CashColumnHeader label="状态"><CashFilterPopover label="账户状态" column value={enabled ? [enabled] : []} options={[{ value: "true", label: "启用" }, { value: "false", label: "停用" }]} onApply={value => { setEnabled(value.length === 1 ? value[0] : ""); setPage(1); }} /></CashColumnHeader></FinanceTableColumn>
        <FinanceTableColumn id="remark">说明</FinanceTableColumn><FinanceTableColumn id="actions">操作</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody renderEmptyState={() => query.loading ? "正在读取账户…" : query.error ? "账户读取失败，请刷新。" : "尚无匹配账户。新增现金账户并确认期初后，即可逐笔录入。"}>{(query.data?.rows ?? []).map((row) => <FinanceTableRow key={row.id} id={row.id}>
        <FinanceTableCell columnRole="identity">{row.name}</FinanceTableCell>
        <FinanceTableCell columnRole="status">{row.kind === "cash" ? "现金" : "储蓄"}</FinanceTableCell>
        <FinanceTableCell columnRole="date">{row.opening_date}</FinanceTableCell>
        <FinanceTableCell columnRole="amount">{cashAmount(row.opening_amount)}</FinanceTableCell>
        <FinanceTableCell columnRole="status">{row.enabled ? "启用" : "停用"}</FinanceTableCell>
        <FinanceTableCell columnRole="description">{row.remark ?? "—"}</FinanceTableCell>
        <FinanceTableCell columnRole="action"><Button variant="tertiary" size="sm" onPress={() => setEditing(row)}>编辑</Button></FinanceTableCell>
      </FinanceTableRow>)}</FinanceTableBody>
    </FinanceTable>
    {editing && <CashAccountEditor account={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
  </section>;
}

function CashAccountEditor({ account, onClose }: { account: CashAccountSetting | null; onClose: () => void }) {
  const [id] = useState(() => crypto.randomUUID());
  const [name, setName] = useState(account?.name ?? "");
  const [kind, setKind] = useState<string>(account?.kind ?? "");
  const [openingDate, setOpeningDate] = useState(account?.opening_date ?? "");
  const [amount, setAmount] = useState(account?.opening_amount ?? "");
  const [enabled, setEnabled] = useState(account?.enabled ?? true);
  const [remark, setRemark] = useState(account?.remark ?? "");
  const mutation = useCashMutation();
  const close = useCashTaskSettingsCloseGuard([name, kind, openingDate, amount, enabled, remark], onClose, mutation.busy);
  const openingChanged = Boolean(account && (openingDate !== account.opening_date || amount !== account.opening_amount));
  const [confirmed, setConfirmed] = useState(false);
  const save = async () => {
    const result = await mutation.run(account ? `/settings/accounts/${account.id}` : "/settings/accounts",
      { ...(account ? { expected_version: account.version } : { id }), name, kind, opening_date: openingDate, opening_amount: amount, enabled, remark: remark || null }, account ? "PUT" : "POST");
    if (result !== null) onClose();
  };
  return <AppDrawer open title={account ? "编辑现金账户" : "新增现金账户"} className="cash-drawer" width={520} onClose={close.requestClose} closeDisabled={mutation.busy} footer={<><Button variant="tertiary" isDisabled={mutation.busy} onPress={close.requestClose}>取消</Button><Button type="submit" form="cash-account-form" isDisabled={mutation.busy || (openingChanged && !confirmed)}>保存账户</Button></>}>
    <form id="cash-account-form" className="cash-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <CashNotice error={mutation.error?.message} />
      <CashInput label="账户名称" value={name} onChange={setName} required disabled={mutation.busy} />
      <CashSelect label="账户类型" value={kind} onChange={setKind} required disabled={mutation.busy} options={[{ value: "", label: "请选择类型" }, { value: "cash", label: "现金" }, { value: "savings", label: "储蓄账户" }]} />
      <CashInput label="起算日期" type="date" value={openingDate} onChange={(value) => { setOpeningDate(value); setConfirmed(false); }} required disabled={mutation.busy} />
      <CashInput label="确认期初金额" value={amount} onChange={(value) => { setAmount(value); setConfirmed(false); }} required disabled={mutation.busy} placeholder="明确填写金额，可为 0" />
      {amount.startsWith("-") && <p className="cash-hint">期初为负数，请核对是否符合实际。</p>}
      <CashInput label="说明" value={remark} onChange={setRemark} disabled={mutation.busy} />
      <Checkbox isSelected={enabled} onChange={setEnabled} isDisabled={mutation.busy}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><span>启用账户</span></Checkbox>
      {account && <p className="cash-hint">停用只影响新录入，已有流水保留；已引用账户不能改资金性质。</p>}
      {openingChanged && <Checkbox isSelected={confirmed} onChange={setConfirmed} isDisabled={mutation.busy}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><span>确认更正期初，后续余额将重新计算</span></Checkbox>}
    </form>
    {close.confirmation}
  </AppDrawer>;
}

function CashCategories({ initial, onChange }: { initial: CategoryCriteria; onChange: (value: CategoryCriteria) => void }) {
  const { revision } = useCashScope();
  const [page, setPage] = useState(initial.page);
  const [keyword, setKeyword] = useState(initial.keyword);
  const [search, setSearch] = useState(initial.keyword);
  const [groups, setGroups] = useState(initial.groups);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [order, setOrder] = useState(initial.order);
  const [editing, setEditing] = useState<CashCategorySetting | "new" | null>(null);
  useEffect(() => { onChange({ page, keyword, enabled, groups, order }); }, [page, keyword, enabled, groups, order, onChange]);
  const query = useCashQuery<CashTasksPage<CashCategorySetting>>("/settings/categories", { page, page_size: 50, sort: "name", order, keyword: keyword || undefined, groups: groups.length ? groups : undefined, enabled: enabled || undefined }, revision);
  return <section className="cash-section" aria-label="费用类型">
    <form className="cash-toolbar" onSubmit={(event) => { event.preventDefault(); setKeyword(search.trim()); setPage(1); }}>
      <CashInput label="费用类型名称" value={search} onChange={setSearch} placeholder="搜索费用类型" />
      <Button type="submit" variant="secondary">查询</Button>
      <Button variant="tertiary" onPress={() => { setKeyword(""); setSearch(""); setGroups([]); setEnabled(""); setOrder("asc"); setPage(1); }}>重置</Button>
      <Button variant="tertiary" onPress={query.reload} isDisabled={query.loading}>刷新</Button><Button onPress={() => setEditing("new")}>新增费用类型</Button>
    </form>
    <CashNotice error={query.error?.message} />
    <FinanceTable ariaLabel="费用类型" minWidth={760} sortDescriptor={{ column: "name", direction: order === "asc" ? "ascending" : "descending" }} onSortChange={value => { setOrder(value.direction === "ascending" ? "asc" : "desc"); setPage(1); }} footer={<FinanceTablePagination page={page} pageSize={50} total={query.data?.pagination.total ?? 0} onPageChange={setPage} isDisabled={query.loading || Boolean(query.error)} />}>
      <FinanceTableHeader>
        <FinanceTableColumn id="name" isRowHeader allowsSorting>名称</FinanceTableColumn>
        <FinanceTableColumn id="group"><CashColumnHeader label="适用范围"><CashFilterPopover label="适用范围" column value={groups} options={Object.entries(cashCategoryGroupLabels).map(([value, label]) => ({ value, label }))} onApply={value => { setGroups(value); setPage(1); }} /></CashColumnHeader></FinanceTableColumn>
        <FinanceTableColumn id="enabled"><CashColumnHeader label="状态"><CashFilterPopover label="费用类型状态" column value={enabled ? [enabled] : []} options={[{ value: "true", label: "启用" }, { value: "false", label: "停用" }]} onApply={value => { setEnabled(value.length === 1 ? value[0] : ""); setPage(1); }} /></CashColumnHeader></FinanceTableColumn>
        <FinanceTableColumn id="remark">说明</FinanceTableColumn><FinanceTableColumn id="actions">操作</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody renderEmptyState={() => query.loading ? "正在读取费用类型…" : query.error ? "费用类型读取失败，请刷新。" : "暂无匹配费用类型。请按实际收付或往来用途新增。"}>{(query.data?.rows ?? []).map((row) => <FinanceTableRow key={row.id} id={row.id}>
        <FinanceTableCell columnRole="identity">{row.name}</FinanceTableCell><FinanceTableCell columnRole="direction">{cashCategoryGroupLabels[row.group]}</FinanceTableCell>
        <FinanceTableCell columnRole="status">{row.enabled ? "启用" : "停用"}</FinanceTableCell><FinanceTableCell columnRole="description">{row.remark ?? "—"}</FinanceTableCell>
        <FinanceTableCell columnRole="action"><Button variant="tertiary" size="sm" onPress={() => setEditing(row)}>编辑</Button></FinanceTableCell>
      </FinanceTableRow>)}</FinanceTableBody>
    </FinanceTable>
    {editing && <CashCategoryEditor category={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
  </section>;
}

function CashCategoryEditor({ category, onClose }: { category: CashCategorySetting | null; onClose: () => void }) {
  const [id] = useState(() => crypto.randomUUID());
  const [name, setName] = useState(category?.name ?? "");
  const [group, setGroup] = useState<string>(category?.group ?? "");
  const [enabled, setEnabled] = useState(category?.enabled ?? true);
  const [remark, setRemark] = useState(category?.remark ?? "");
  const mutation = useCashMutation();
  const close = useCashTaskSettingsCloseGuard([name, group, enabled, remark], onClose, mutation.busy);
  return <AppDrawer open title={category ? "编辑费用类型" : "新增费用类型"} width={480} className="cash-drawer" onClose={close.requestClose} closeDisabled={mutation.busy} footer={<><Button variant="tertiary" onPress={close.requestClose} isDisabled={mutation.busy}>取消</Button><Button type="submit" form="cash-category-form" isDisabled={mutation.busy}>保存费用类型</Button></>}>
    <form id="cash-category-form" className="cash-form" onSubmit={(event) => { event.preventDefault(); void (async () => {
      const result = await mutation.run(category ? `/settings/categories/${category.id}` : "/settings/categories", { ...(category ? { expected_version: category.version } : { id }), name, group, enabled, remark: remark || null }, category ? "PUT" : "POST");
      if (result !== null) onClose();
    })(); }}>
      <CashNotice error={mutation.error?.message} />
      <CashInput label="费用类型名称" value={name} onChange={setName} required disabled={mutation.busy} />
      <CashSelect label="适用范围" value={group} onChange={setGroup} required disabled={mutation.busy} options={[{ value: "", label: "请选择范围" }, ...Object.entries(cashCategoryGroupLabels).map(([value, label]) => ({ value, label }))]} />
      <CashInput label="说明" value={remark} onChange={setRemark} disabled={mutation.busy} />
      <Checkbox isSelected={enabled} onChange={setEnabled} isDisabled={mutation.busy}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><span>启用费用类型</span></Checkbox>
      <p className="cash-hint">已引用类型只能更名或停用；改变业务含义请新增类型。</p>
    </form>
    {close.confirmation}
  </AppDrawer>;
}

function CashPersonalOpening() {
  const { revision } = useCashScope();
  const query = useCashQuery<CashPersonalSetting>("/settings/personal-opening", undefined, revision);
  const [editing, setEditing] = useState<CashPersonalSetting | null>(null);
  const [openingItem, setOpeningItem] = useState(false);
  const [billLabels, setBillLabels] = useState(false);
  return <section className="cash-section cash-settings-subsection" aria-label="个人账起算">
    <div className="cash-toolbar"><h3>个人账起算</h3><span>{query.data ? `${query.data.counterparty ?? "归属人未设置"} · ${query.data.opening_date ?? "起算未设置"}` : "正在读取…"}</span><Button variant="tertiary" onPress={() => setEditing(query.data)} isDisabled={!query.data || query.loading}>设置起算日期</Button><Button variant="tertiary" isDisabled={!query.data?.opening_date || !query.data.counterparty || query.loading} onPress={() => setOpeningItem(true)}>登记期初未结</Button><Button variant="tertiary" onPress={() => setBillLabels(true)}>管理账单分组</Button></div>
    <CashNotice error={query.error?.message} />
    <p className="cash-hint">声明个人账的记账范围，不改变现金账户期初；旧欠款需逐项登记，不会自动生成现金流水。</p>
    {editing && <CashOpeningDateEditor setting={editing} onClose={() => setEditing(null)} />}
    {openingItem && query.data?.counterparty && query.data.opening_date && <CashItemEditor opening initialType="loan" personalContext={{ counterparty: query.data.counterparty, opening_date: query.data.opening_date }} onClose={() => setOpeningItem(false)} />}
    {billLabels && <AppDrawer open title="账单分组" width={760} className="cash-drawer" onClose={() => setBillLabels(false)}><CashBillLabels /></AppDrawer>}
  </section>;
}

function CashOpeningDateEditor({ setting, onClose }: { setting: CashPersonalSetting; onClose: () => void }) {
  const [date, setDate] = useState(setting.opening_date ?? "");
  const [counterparty, setCounterparty] = useState(setting.counterparty ?? "");
  const [confirmed, setConfirmed] = useState(false);
  const mutation = useCashMutation();
  const close = useCashTaskSettingsCloseGuard([date, counterparty], onClose, mutation.busy);
  return <AppDrawer open title="设置个人账起算" width={480} className="cash-drawer" onClose={close.requestClose} closeDisabled={mutation.busy} footer={<><Button variant="tertiary" onPress={close.requestClose} isDisabled={mutation.busy}>取消</Button><Button type="submit" form="cash-personal-opening-form" isDisabled={mutation.busy || Boolean(setting.opening_date && !confirmed)}>保存起算</Button></>}>
    <form id="cash-personal-opening-form" className="cash-form" onSubmit={(event) => { event.preventDefault(); void (async () => {
      const result = await mutation.run("/settings/personal-opening", { expected_version: setting.version, opening_date: date || null, counterparty: counterparty.trim() || null }, "PUT");
      if (result !== null) onClose();
    })(); }}>
      <CashNotice error={mutation.error?.message} /><CashInput label="个人账起算日期" type="date" value={date} onChange={(value) => { setDate(value); setConfirmed(false); }} disabled={mutation.busy} />
      <CashInput label="个人专账归属人" value={counterparty} onChange={value => { setCounterparty(value); setConfirmed(false); }} disabled={mutation.busy} required={Boolean(date)} />
      <p className="cash-hint">起算前不显示已知零余额；已登记的期初事项随日期更正，不自动改金额。</p>
      {setting.opening_date && <Checkbox isSelected={confirmed} onChange={setConfirmed} isDisabled={mutation.busy}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><span>确认更正记账范围及已有期初事项日期</span></Checkbox>}
    </form>
    {close.confirmation}
  </AppDrawer>;
}

export function CashProjectSettings({ initial = initialCashSettingsCriteria().projects, onChange }: { initial?: ProjectCriteria; onChange?: (value: ProjectCriteria) => void } = {}) {
  const { revision } = useCashScope();
  const [page, setPage] = useState(initial.page);
  const [keyword, setKeyword] = useState(initial.keyword);
  const [search, setSearch] = useState(initial.keyword);
  const [stages, setStages] = useState(initial.stages);
  const [selectable, setSelectable] = useState(initial.selectable);
  const [draft, setDraft] = useState<{ codes: string[]; version: number } | null>(null);
  const [stageOptions, setStageOptions] = useState<CashProjectsPage["stages"] | null>(null);
  const [savedSelection, setSavedSelection] = useState<CashProjectSelection | null>(null);
  useEffect(() => { onChange?.({ page, keyword, stages, selectable }); }, [page, keyword, stages, selectable, onChange]);
  const selection = useCashQuery<CashProjectSelection>("/settings/project-selection", undefined, revision);
  const projects = useCashQuery<CashProjectsPage>("/projects", { purpose: "all", page, page_size: 50, keyword: keyword || undefined, stage_codes: stages.length ? stages : undefined, selectable: selectable || undefined }, revision);
  useEffect(() => { if (projects.data) setStageOptions(projects.data.stages); }, [projects.data]);
  useEffect(() => { if (selection.data) setSavedSelection(selection.data); }, [selection.data]);
  const mutation = useCashMutation();
  const displayedSelection = selection.data ?? savedSelection;
  const selected = draft?.codes ?? displayedSelection?.allowed_stage_codes ?? [];
  const configurationUnavailable = mutation.busy || selection.loading || projects.loading || !selection.data || Boolean(projects.error);
  const save = async () => {
    if (!selection.data) return;
    const result = await mutation.run<CashProjectSelection>("/settings/project-selection", { expected_version: draft?.version ?? selection.data.version, allowed_stage_codes: selected }, "PUT");
    if (result !== null) setDraft(null);
  };
  return <section className="cash-section" aria-label="OA 项目与可选阶段">
    <div className="cash-toolbar"><h3>新增流水可选项目状态</h3><Button variant="tertiary" isDisabled={projects.loading || selection.loading || mutation.busy} onPress={() => { projects.reload(); selection.reload(); }}>刷新 OA 资料</Button></div>
    <p className="cash-hint">仅影响新增流水的项目选择，不修改 OA 状态。</p>
    <CashNotice error={selection.error?.message ?? projects.error?.message ?? mutation.error?.message} />
    {displayedSelection && stageOptions && <>
      <fieldset className="cash-checkbox-grid" disabled={configurationUnavailable}>
        <legend className="sr-only">允许进入新增流水的 OA 阶段</legend>
        {stageOptions.map((item) => <Checkbox key={item.code} isSelected={item.code !== "end" && selected.includes(item.code)} isDisabled={configurationUnavailable || item.code === "end"} onChange={(checked) => {
          const next = checked ? [...selected, item.code] : selected.filter((code) => code !== item.code);
          setDraft({ codes: next, version: draft?.version ?? selection.data!.version });
        }}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><span>{item.name}{item.code === "end" ? "（不允许新增）" : ""}</span></Checkbox>)}
      </fieldset>
      <div className="cash-toolbar">
        <span role="status">{draft ? "未保存" : !displayedSelection.configured ? "尚未设置，请明确保存允许范围" : displayedSelection.allowed_stage_codes.length === 0 ? "当前不允许任何项目" : "已保存"}</span>
        <Button isDisabled={configurationUnavailable || (!draft && displayedSelection.configured)} onPress={() => { void save(); }}>保存选择</Button>
        <Button variant="tertiary" isDisabled={!draft || mutation.busy} onPress={() => setDraft(null)}>撤销更改</Button>
      </div>
    </>}
    <form className="cash-toolbar" onSubmit={(event) => { event.preventDefault(); setKeyword(search.trim()); setPage(1); }}>
      <CashInput label="项目关键词" value={search} onChange={setSearch} placeholder="项目名称或编号" />
      <Button type="submit" variant="secondary">查询项目</Button>
      <Button variant="tertiary" onPress={() => { setKeyword(""); setSearch(""); setStages([]); setSelectable(""); setPage(1); }}>重置</Button>
      {projects.data && <span className="cash-hint">本次读取：{new Date(projects.data.read_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</span>}
    </form>
    <FinanceTable ariaLabel="OA 项目列表" minWidth={900} footer={<FinanceTablePagination page={page} pageSize={50} total={projects.data?.total ?? 0} onPageChange={setPage} isDisabled={projects.loading || Boolean(projects.error) || mutation.busy} />}>
      <FinanceTableHeader>
        <FinanceTableColumn id="code">项目编号</FinanceTableColumn><FinanceTableColumn id="name" isRowHeader>项目名称</FinanceTableColumn>
        <FinanceTableColumn id="stage"><CashColumnHeader label="真实阶段"><CashFilterPopover<string | null> label="项目阶段" column value={stages} options={[...(stageOptions?.map(item => ({ value: item.code, label: item.name })) ?? []), { value: null, label: "阶段缺失" }]} loading={projects.loading} error={projects.error?.message} onReload={projects.reload} onApply={value => { setStages(value); setPage(1); }} /></CashColumnHeader></FinanceTableColumn>
        <FinanceTableColumn id="selectable"><CashColumnHeader label="新增可选"><CashFilterPopover label="新增资格" column value={selectable ? [selectable] : []} options={[{ value: "true", label: "可选" }, { value: "false", label: "不可选" }]} onApply={value => { setSelectable(value.length === 1 ? value[0] : ""); setPage(1); }} /></CashColumnHeader></FinanceTableColumn>
        <FinanceTableColumn id="reason">不可选原因</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody renderEmptyState={() => projects.loading ? "正在读取 OA 项目…" : projects.error ? "OA 项目读取失败，请刷新。" : "没有匹配项目。历史现金记录不受本页选择范围影响。"}>{(projects.data?.rows ?? []).map((row) => <FinanceTableRow key={row.id} id={row.id}>
        <FinanceTableCell columnRole="identity">{row.code ?? "—"}</FinanceTableCell><FinanceTableCell columnRole="identity">{row.name}</FinanceTableCell>
        <FinanceTableCell columnRole="status">{row.stage_name ?? (row.stage_code ? "未知阶段" : "阶段缺失")}</FinanceTableCell><FinanceTableCell columnRole="status">{row.selectable ? "可选" : "不可选"}</FinanceTableCell>
        <FinanceTableCell columnRole="description">{row.unavailable_reason ? cashProjectUnavailableLabels[row.unavailable_reason] : "—"}</FinanceTableCell>
      </FinanceTableRow>)}</FinanceTableBody>
    </FinanceTable>
  </section>;
}

export function CashBillLabels() {
  const { revision } = useCashScope();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState("");
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<CashBillLabelSetting | "new" | null>(null);
  const query = useCashQuery<CashTasksPage<CashBillLabelSetting>>("/settings/bill-labels", { page, page_size: 50, keyword: keyword || undefined, order: "asc" }, revision);
  return <section className="cash-section" aria-label="账单分组">
    <form className="cash-toolbar" onSubmit={(event) => { event.preventDefault(); setKeyword(search.trim()); setPage(1); }}><CashInput label="账单分组关键词" value={search} onChange={setSearch} /><Button type="submit" variant="secondary">查询分组</Button><Button onPress={() => setEditing("new")}>新增账单分组</Button></form>
    <CashNotice error={query.error?.message} />
    <FinanceTable ariaLabel="账单分组" minWidth={480} footer={<FinanceTablePagination page={page} pageSize={50} total={query.data?.pagination.total ?? 0} onPageChange={setPage} isDisabled={query.loading || Boolean(query.error)} />}>
      <FinanceTableHeader>{["银行", "账单别名", "状态", "操作"].map((name, i) => <FinanceTableColumn key={name} id={name} isRowHeader={i === 1}>{name}</FinanceTableColumn>)}</FinanceTableHeader>
      <FinanceTableBody renderEmptyState={() => query.loading ? "正在读取账单分组…" : query.error ? "账单分组读取失败，请刷新。" : "尚无账单分组。分组只标明用途，不是现金账户。"}>{(query.data?.rows ?? []).map((row) => <FinanceTableRow id={row.id} key={row.id}><FinanceTableCell columnRole="identity">{row.bank_name}</FinanceTableCell><FinanceTableCell columnRole="identity">{row.label}</FinanceTableCell><FinanceTableCell columnRole="status">{row.enabled ? "启用" : "停用"}</FinanceTableCell><FinanceTableCell columnRole="action"><Button variant="tertiary" onPress={() => setEditing(row)}>编辑</Button></FinanceTableCell></FinanceTableRow>)}</FinanceTableBody>
    </FinanceTable>
    {editing && <CashBillEditor row={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
  </section>;
}

function CashBillEditor({ row, onClose }: { row: CashBillLabelSetting | null; onClose: () => void }) {
  const [id] = useState(() => crypto.randomUUID());
  const [bank, setBank] = useState(row?.bank_name ?? "");
  const [label, setLabel] = useState(row?.label ?? "");
  const [enabled, setEnabled] = useState(row?.enabled ?? true);
  const mutation = useCashMutation();
  const close = useCashTaskSettingsCloseGuard([bank, label, enabled], onClose, mutation.busy);
  return <AppDrawer open title={row ? "编辑账单分组" : "新增账单分组"} width={480} className="cash-drawer" onClose={close.requestClose} closeDisabled={mutation.busy} footer={<Button type="submit" form="cash-bill-form" isDisabled={mutation.busy}>保存分组</Button>}>
    <form id="cash-bill-form" className="cash-form" onSubmit={(event) => { event.preventDefault(); void (async () => { const result = await mutation.run(row ? `/settings/bill-labels/${row.id}` : "/settings/bill-labels", { ...(row ? { expected_version: row.version } : { id }), bank_name: bank, label, enabled }, row ? "PUT" : "POST"); if (result !== null) onClose(); })(); }}>
      <CashNotice error={mutation.error?.message} /><CashInput label="银行名称" value={bank} onChange={setBank} required disabled={mutation.busy} /><CashInput label="账单别名" value={label} onChange={setLabel} required disabled={mutation.busy} />
      <Checkbox isSelected={enabled} onChange={setEnabled} isDisabled={mutation.busy}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><span>启用分组</span></Checkbox>
    </form>
    {close.confirmation}
  </AppDrawer>;
}

const paymentGuideRows = [
  { category: "员工无发票报销", summary: "材料、交通、修理、打印复印、餐费、资料费等", applicant: "员工", document: "无票报销单", recipient: "员工", current: "按实际报销资料审核后支付", proposed: "下载申请单 → 填写补票资料 → 纸质或 PDF 审核 → 交财务支付" },
  { category: "招投标费用", summary: "配合费、保证金", applicant: "商务", document: "支付申请", recipient: "第三方", current: "审核支付申请后，按确认的银行卡或微信渠道办理", proposed: "未明确调整" },
  { category: "挂靠费用", summary: "非本公司中标、履约等相关费用", applicant: "商务或经办人", document: "支付申请", recipient: "第三方", current: "核对申请及收款资料后办理", proposed: "未明确调整" },
  { category: "房租水电", summary: "租金、水电等", applicant: "经办人", document: "无票报销单", recipient: "第三方", current: "核对费用归属和实际收款方后办理", proposed: "未明确调整" },
  { category: "无发票项目成本", summary: "项目相关成本", applicant: "经办人", document: "支付申请", recipient: "第三方", current: "核对项目及费用用途后办理", proposed: "未明确调整" },
  { category: "无票货款、劳务", summary: "货款与劳务费用", applicant: "项目负责人或采购", document: "支付申请", recipient: "第三方", current: "按实际审核结果办理", proposed: "未明确调整" },
  { category: "代开票税费", summary: "代开票相关税费", applicant: "经办人", document: "报销单", recipient: "第三方", current: "核对税费资料后办理", proposed: "未明确调整" },
  { category: "个人借款、利息", summary: "个人借款或利息支付", applicant: "经办人", document: "支付申请", recipient: "第三方", current: "核对真实义务及审批金额后办理", proposed: "未明确调整" },
  { category: "个人信用卡还款", summary: "实际信用卡账单还款", applicant: "经办人", document: "领款单", recipient: "个人银行卡", current: "按本次真实账单和实际采用日期办理；不是受管现金账户互转", proposed: "原资料的日期有差异，以本次确认日期为准" },
  { category: "员工施工预领", summary: "施工前预领费用", applicant: "员工", document: "负责人同意后填写领款单", recipient: "员工", current: "申请经负责人同意后，交财务办理", proposed: "未明确调整" },
];

function CashPaymentGuide({ keyword, onChange }: { keyword: string; onChange: (value: string) => void }) {
  const [detail, setDetail] = useState<(typeof paymentGuideRows)[number] | null>(null);
  const needle = keyword.trim();
  const rows = paymentGuideRows.filter((row) => !needle || Object.values(row).some((value) => value.includes(needle)));
  return <section className="cash-section" aria-label="支付办理说明">
    <p className="cash-hint">参考说明，不会提交 OA 或执行付款。现行与拟调整方式不自动成为任务规则。</p>
    <div className="cash-toolbar"><CashInput label="办理说明关键词" value={keyword} onChange={onChange} placeholder="类别、申请人或所需单据" /></div>
    <FinanceTable ariaLabel="支付办理参考" minWidth={1050}>
      <FinanceTableHeader>{["类别", "概要", "申请人", "所需单据", "收款方", "办理说明"].map((name, index) => <FinanceTableColumn key={name} id={name} isRowHeader={index === 0}>{name}</FinanceTableColumn>)}</FinanceTableHeader>
      <FinanceTableBody renderEmptyState={() => "没有匹配的办理说明。"}>{rows.map((row) => <FinanceTableRow key={row.category} id={row.category}><FinanceTableCell columnRole="identity">{row.category}</FinanceTableCell><FinanceTableCell columnRole="description">{row.summary}</FinanceTableCell><FinanceTableCell columnRole="identity">{row.applicant}</FinanceTableCell><FinanceTableCell columnRole="description">{row.document}</FinanceTableCell><FinanceTableCell columnRole="identity">{row.recipient}</FinanceTableCell><FinanceTableCell columnRole="action"><Button variant="tertiary" size="sm" onPress={() => setDetail(row)}>查看说明</Button></FinanceTableCell></FinanceTableRow>)}</FinanceTableBody>
    </FinanceTable>
    {detail && <AppDrawer open title={detail.category} width={520} className="cash-drawer" onClose={() => setDetail(null)}><div className="cash-form"><p>{detail.summary}</p><p>申请人：{detail.applicant}</p><p>所需单据：{detail.document}</p><p>收款方：{detail.recipient}</p><p>现行参考：{detail.current}</p><p>调整参考：{detail.proposed}</p></div></AppDrawer>}
  </section>;
}
