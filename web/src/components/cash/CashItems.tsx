import { Button, Checkbox } from "@heroui/react";
import { useState, type FormEvent } from "react";

import { useCashMutation, useCashQuery } from "../../features/cash/hooks";
import AppDrawer from "../common/AppDrawer";
import {
  FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader,
  FinanceTablePagination, FinanceTableRow,
} from "../common/FinanceTable";
import { CashInput, CashNotice, CashSelect, CashTabs } from "./CashUi";
import {
  cashAmount, cashMoneyInput, cashToday, itemTypeLabels, settlementLabels, settlementVersions,
  type CashItem, type CashItemDetailData, type CashItemType, type CashPageRows,
  type CashSettlement, type CashSettlementKind,
} from "./CashItems.types";

type QueryParams = Record<string, string | number | boolean | null | undefined>;
type RefItem = { id: string; version: number; content: string };

function useItemWrite() {
  const mutation = useCashMutation();
  const [error, setError] = useState<string | null>(null);
  async function write(path: string, method: string, body: unknown, onSuccess: () => void) {
    setError(null);
    const result = await mutation.run(path, body, method);
    if (result !== null) onSuccess();
  }
  return { busy: mutation.busy, error: error ?? mutation.error?.message, setError, write };
}

export function CashItemPicker({ label, params = {}, onSelect, onCancel }: {
  label: string; params?: QueryParams; onSelect: (item: CashItem) => void; onCancel?: () => void;
}) {
  const [search, setSearch] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const query = useCashQuery<CashPageRows<CashItem>>("/items", { ...params, keyword: keyword || undefined, page, page_size: 20 });
  return <section className="cash-picker" aria-label={label}>
    <div className="cash-toolbar" onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); setKeyword(search); setPage(1); } }}>
      <CashInput label={label} value={search} onChange={setSearch} placeholder="搜索对象、项目或事项内容" />
      <Button size="sm" variant="secondary" onPress={() => { setKeyword(search); setPage(1); }}>查询</Button>
      {onCancel && <Button size="sm" variant="tertiary" onPress={onCancel}>收起选择</Button>}
    </div>
    <CashNotice error={query.error?.message} />
    {query.loading && <p role="status">正在读取事项…</p>}
    {query.data && !query.loading && <>
      <FinanceTable ariaLabel={label} minWidth={560}>
        <FinanceTableHeader><FinanceTableColumn isRowHeader>事项 / 对象</FinanceTableColumn><FinanceTableColumn>项目</FinanceTableColumn><FinanceTableColumn>金额</FinanceTableColumn><FinanceTableColumn>操作</FinanceTableColumn></FinanceTableHeader>
        <FinanceTableBody>{query.data.rows.map(item => <FinanceTableRow key={item.id} id={item.id} textValue={item.content}>
          <FinanceTableCell columnRole="identity"><div>{item.content}</div><small>{item.counterparty ?? item.ticket_provider ?? itemTypeLabels[item.type]}</small></FinanceTableCell>
          <FinanceTableCell columnRole="description">{item.project === null ? "无项目" : item.project!.name_snapshot}</FinanceTableCell>
          <FinanceTableCell columnRole="amount">{cashAmount(item.selectable === false ? null : params.purpose === "settlement_source" ? item.available_source_amount! : params.purpose === "settlement_target" && (item.type === "loan" || item.type === "company_receivable") ? item.remaining_obligation_amount! : item.original_amount)}<small>{params.purpose === "settlement_source" ? "来源可用" : params.purpose === "settlement_target" && (item.type === "loan" || item.type === "company_receivable") ? "目标未结" : "原始金额"}</small></FinanceTableCell>
          <FinanceTableCell columnRole="action"><Button size="sm" variant="tertiary" isDisabled={item.selectable === false} onPress={() => onSelect(item)}>选择</Button>{item.selectable === false && <small>不符合本次处理条件</small>}</FinanceTableCell>
        </FinanceTableRow>)}</FinanceTableBody>
      </FinanceTable>
      {query.data.rows.length === 0 && <p>没有符合条件的事项。</p>}
      <FinanceTablePagination {...query.data.pagination} pageSize={query.data.pagination.page_size} onPageChange={setPage} />
    </>}
    {query.error && <Button size="sm" variant="tertiary" onPress={query.reload}>重新读取</Button>}
  </section>;
}

function ItemProjectPicker({ historical, onSelect, onCancel }: {
  historical: boolean; onSelect: (row: { id: string; name: string }) => void; onCancel: () => void;
}) {
  const [search, setSearch] = useState(""); const [keyword, setKeyword] = useState(""); const [page, setPage] = useState(1);
  const query = useCashQuery<{ rows: { id: string; name: string; stage_name: string | null }[]; total: number; page: number; page_size: number }>("/projects", { purpose: historical ? "all" : "selection", keyword: keyword || undefined, page, page_size: 20 });
  return <section className="cash-picker">
    <div className="cash-toolbar" onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); setKeyword(search); setPage(1); } }}>
      <CashInput label={historical ? "期初历史项目" : "可选项目"} value={search} onChange={setSearch} />
      <Button size="sm" variant="secondary" onPress={() => { setKeyword(search); setPage(1); }}>查询项目</Button><Button size="sm" variant="tertiary" onPress={onCancel}>取消选择</Button>
    </div>
    <CashNotice error={query.error?.message} />
    {query.loading && <p role="status">正在读取项目…</p>}
    {query.data && !query.loading && <><ul className="cash-choice-list">{query.data.rows.map(row => <li key={row.id}><Button size="sm" variant="tertiary" onPress={() => onSelect(row)}>{row.name} · {row.stage_name ?? "状态未提供"}</Button></li>)}</ul>{query.data.rows.length === 0 && <p>没有可选项目。可以保留无项目，或在基础设置调整允许阶段。</p>}<FinanceTablePagination page={page} pageSize={20} total={query.data.total} onPageChange={setPage} /></>}
  </section>;
}

export function CashItemEditor({ item, initialType = "loan", opening: initialOpening = false, ticketSource, onClose, onSaved }: {
  item?: CashItem; initialType?: CashItemType; opening?: boolean; ticketSource?: RefItem; onClose: () => void; onSaved?: (id: string) => void;
}) {
  const [id] = useState(() => item?.id ?? crypto.randomUUID());
  const [expectedVersion] = useState(item?.version);
  const [type, setType] = useState<CashItemType>(item?.type ?? initialType);
  const [date, setDate] = useState(item?.origin_date ?? cashToday());
  const [amount, setAmount] = useState(item?.original_amount ?? "");
  const [content, setContent] = useState(item?.content ?? ""); const [remark, setRemark] = useState(item?.remark ?? "");
  const [counterparty, setCounterparty] = useState(item?.counterparty ?? "");
  const [group, setGroup] = useState<string>(item?.ledger_group ?? "company");
  const [direction, setDirection] = useState<string>(item?.obligation_direction ?? "receivable");
  const [opening, setOpening] = useState(item?.is_opening ?? initialOpening);
  const [project, setProject] = useState<{ id: string; name: string } | null>(item?.oa_project_id ? { id: item.oa_project_id, name: item.project_name_snapshot! } : null);
  const [projectPicker, setProjectPicker] = useState(false);
  const [provider, setProvider] = useState(item?.ticket_provider ?? "");
  const [description, setDescription] = useState(item?.ticket_description ?? "");
  const [billLabel, setBillLabel] = useState(item?.bill_label_id ?? ""); const [billMonth, setBillMonth] = useState(item?.bill_month ?? "");
  const [billPage, setBillPage] = useState(1); const [showBill, setShowBill] = useState(Boolean(item?.bill_label_id));
  const bills = useCashQuery<CashPageRows<{ id: string; label: string; bank_name: string; enabled: boolean }>>(showBill ? "/settings/bill-labels" : null, { page: billPage, page_size: 50 });
  const [ref, setRef] = useState<RefItem | null>(ticketSource ?? null);
  const [refCleared, setRefCleared] = useState(false); const [refPicker, setRefPicker] = useState(false);
  const originalRefId = item?.related_obligation_id ?? item?.ticket_source_id;
  const originalRef = useCashQuery<CashItemDetailData>(originalRefId && !refCleared && !ref ? `/items/${originalRefId}` : null);
  const linked = ref ?? (!refCleared && originalRef.data ? originalRef.data.item : null);
  const [closing, setClosing] = useState(false);
  const action = useItemWrite();
  const obligation = type === "loan" || type === "company_receivable";
  const protectedSource = Boolean(item?.origin_flow_id);
  const dirty = type !== (item?.type ?? initialType) || date !== (item?.origin_date ?? cashToday()) || amount !== (item?.original_amount ?? "")
    || content !== (item?.content ?? "") || remark !== (item?.remark ?? "") || counterparty !== (item?.counterparty ?? "")
    || group !== (item?.ledger_group ?? "company") || direction !== (item?.obligation_direction ?? "receivable")
    || opening !== (item?.is_opening ?? initialOpening) || (project?.id ?? null) !== (item?.oa_project_id ?? null)
    || provider !== (item?.ticket_provider ?? "") || description !== (item?.ticket_description ?? "")
    || billLabel !== (item?.bill_label_id ?? "") || billMonth !== (item?.bill_month ?? "")
    || showBill !== Boolean(item?.bill_label_id) || (refCleared && Boolean(originalRefId || ticketSource))
    || Boolean(ref && ref.id !== (originalRefId ?? ticketSource?.id));
  const requestClose = () => { if (dirty) setClosing(true); else onClose(); };
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const body = {
        ...(item ? { expected_version: expectedVersion } : { id }), type,
        origin_date: date, original_amount: cashMoneyInput(amount), content: content.trim(), remark: remark.trim() || null,
        is_opening: obligation && opening,
        obligation_direction: obligation ? (type === "company_receivable" || group === "personal" ? "receivable" : direction) : null,
        ledger_group: obligation ? (type === "company_receivable" ? "company" : group) : null,
        counterparty: obligation ? counterparty.trim() : null,
        oa_project_id: project?.id ?? null,
        bill_label_id: (type === "loan" || type === "expense") && showBill ? billLabel || null : null,
        bill_month: (type === "loan" || type === "expense") && showBill ? billMonth || null : null,
        ticket_provider: type === "ticket_source" ? provider.trim() : null,
        ticket_provided_on: type === "ticket_source" ? date : null,
        ticket_description: type === "ticket_source" ? description.trim() : null,
        related_obligation_id: type === "expense" ? linked?.id ?? null : null,
        ticket_source_id: type === "company_receivable" ? linked?.id ?? null : null,
        expected_related_versions: { items: linked ? [{ id: linked.id, version: linked.version }] : [], flows: [], occurrences: [] },
      };
      await action.write(item ? `/items/${id}` : "/items", item ? "PUT" : "POST", body, () => { onSaved?.(id); onClose(); });
    } catch (error) { if (!(error instanceof Error)) throw error; action.setError(error.message); }
  }
  return <AppDrawer open title={item ? "更正事项" : "新建事项"} width={620} className="cash-module cash-drawer" closeDisabled={action.busy} onClose={requestClose}>
    {closing && <div role="alert" className="cash-confirm"><p>未保存的事项内容将被丢弃。</p><Button size="sm" variant="secondary" onPress={() => setClosing(false)}>继续填写</Button><Button size="sm" variant="danger" onPress={onClose}>放弃并关闭</Button></div>}
    <form className="cash-form" onSubmit={submit}>
      <CashNotice error={action.error} />
      <CashSelect label="事项类型" value={type} disabled={Boolean(item)} onChange={value => { setType(value as CashItemType); setRef(null); setRefCleared(true); setOpening(false); }} options={Object.entries(itemTypeLabels).map(([value, label]) => ({ value, label }))} />
      <div className="cash-form-grid"><CashInput label={opening ? "起算日期" : "实际日期"} type="date" value={date} onChange={setDate} required disabled={protectedSource} /><CashInput label={opening ? "期初未结金额" : "原始金额"} value={amount} onChange={setAmount} required disabled={protectedSource} /></div>
      {obligation && <><CashInput label="往来对象" value={counterparty} onChange={setCounterparty} required /><div className="cash-form-grid"><CashSelect label="往来类别" value={type === "company_receivable" ? "company" : group} onChange={setGroup} disabled={type === "company_receivable"} options={[{ value: "company", label: "公司往来" }, { value: "external_person", label: "外部人员" }, { value: "personal", label: "个人专账" }]} /><CashSelect label="义务方向" value={type === "company_receivable" || group === "personal" ? "receivable" : direction} onChange={setDirection} disabled={protectedSource || type === "company_receivable" || group === "personal"} options={[{ value: "receivable", label: "应收 / 对方应还" }, { value: "payable", label: "应付 / 我方应还" }]} /></div><Checkbox isSelected={opening} isDisabled={protectedSource} onChange={setOpening}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><Checkbox.Content>登记期初未结，不计本期新增</Checkbox.Content></Checkbox></>}
      <div className="cash-toolbar"><span>项目：{project?.name ?? "无项目"}</span><Button size="sm" variant="tertiary" isDisabled={protectedSource} onPress={() => setProjectPicker(!projectPicker)}>选择项目</Button>{project && <Button size="sm" variant="tertiary" isDisabled={protectedSource} onPress={() => setProject(null)}>清除</Button>}</div>
      {projectPicker && <ItemProjectPicker historical={opening} onSelect={row => { setProject(row); setProjectPicker(false); }} onCancel={() => setProjectPicker(false)} />}
      <CashInput label="事项内容" value={content} onChange={setContent} required />
      {type === "ticket_source" && <><CashInput label="提供人" value={provider} onChange={setProvider} required /><CashInput label="票据 / 用途说明" value={description} onChange={setDescription} required /></>}
      {(type === "loan" || type === "expense") && <><Checkbox isSelected={showBill} onChange={setShowBill}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><Checkbox.Content>归属银行 / 卡片账单</Checkbox.Content></Checkbox>{showBill && <><CashNotice error={bills.error?.message} /><CashSelect label="账单别名" value={billLabel} onChange={setBillLabel} required options={[{ value: "", label: "请选择账单" }, ...(bills.data?.rows.map(row => ({ value: row.id, label: `${row.bank_name} · ${row.label}`, disabled: !row.enabled && row.id !== billLabel })) ?? [])]} />{bills.data && <FinanceTablePagination {...bills.data.pagination} pageSize={bills.data.pagination.page_size} onPageChange={setBillPage} />}<CashInput label="账单月份" type="month" value={billMonth} onChange={setBillMonth} required /></>}</>}
      {(type === "expense" || type === "company_receivable") && <><div className="cash-toolbar"><span>{type === "expense" ? "往来展示归属" : "对应票据来源"}：{linked?.content ?? "未关联"}</span><Button size="sm" variant="tertiary" onPress={() => setRefPicker(!refPicker)}>选择事项</Button>{(linked || originalRefId) && <Button size="sm" variant="tertiary" onPress={() => { setRef(null); setRefCleared(true); }}>解除引用</Button>}</div><CashNotice error={originalRef.error?.message} />{refPicker && <CashItemPicker label={type === "expense" ? "选择往来义务" : "选择票据来源"} params={{ type: type === "company_receivable" ? "ticket_source" : undefined, purpose: type === "expense" ? "settlement_target" : "list", settlement_kind: type === "expense" ? "non_ticket_offset" : undefined }} onSelect={row => { setRef(row); setRefCleared(false); setRefPicker(false); }} onCancel={() => setRefPicker(false)} />}</>}
      <CashInput label="备注" value={remark} onChange={setRemark} />
      {protectedSource && <p className="cash-muted">金额、日期、项目和期初由来源流水管理，请在该流水详情更正。</p>}
      <div className="cash-form-actions"><Button variant="secondary" onPress={requestClose} isDisabled={action.busy}>取消</Button><Button type="submit" isDisabled={action.busy || Boolean(originalRefId && !refCleared && !linked)}>保存事项</Button></div>
    </form>
  </AppDrawer>;
}

const cashKinds: CashSettlementKind[] = ["cash_repayment", "company_collection", "expense_payment", "expense_refund"];
type FlowCandidate = { id: string; version: number; occurred_on: string; content: string; amount: string; available_amount: string; allocated_amount: string; selectable: boolean; kind: string; from_account: { name: string } | null; to_account: { name: string } | null; source_kind: string };

export function CashSettlementEditor({ target, source, settlement, initialKind, onClose }: {
  target?: RefItem; source?: RefItem; settlement?: CashSettlement; initialKind: CashSettlementKind; onClose: () => void;
}) {
  const [id] = useState(() => crypto.randomUUID()); const [kind, setKind] = useState(initialKind);
  const [amount, setAmount] = useState(settlement?.amount ?? ""); const [date, setDate] = useState(settlement?.occurred_on ?? cashToday()); const [remark, setRemark] = useState(settlement?.remark ?? "");
  const [chosenTarget, setTarget] = useState<RefItem | null>(target ?? (settlement?.item_id ? { id: settlement.item_id, version: settlement.item_version!, content: settlement.item_content! } : null));
  const [chosenSource, setSource] = useState<RefItem | null>(source ?? (settlement?.source_item_id ? { id: settlement.source_item_id, version: settlement.source_item_version!, content: settlement.source_item_content! } : null));
  const [picker, setPicker] = useState<"target" | "source" | null>(null); const [flow, setFlow] = useState<FlowCandidate | null>(null);
  const [flowPage, setFlowPage] = useState(1); const [flowSearch, setFlowSearch] = useState(""); const [flowKeyword, setFlowKeyword] = useState("");
  const isCash = cashKinds.includes(kind);
  const flows = useCashQuery<CashPageRows<FlowCandidate>>(isCash && chosenTarget && !settlement ? "/flows" : null, { purpose: "settlement", item_id: chosenTarget?.id, settlement_kind: kind, keyword: flowKeyword || undefined, page: flowPage, page_size: 20 });
  const action = useItemWrite();
  const targetRef = kind === "ticket_use" ? null : chosenTarget;
  const sourceRef = isCash ? null : chosenSource;
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      if (kind !== "ticket_use" && !targetRef) throw new Error("请选择本次处理的目标事项。");
      if ((kind === "ticket_use" || kind === "ticket_offset") && !sourceRef) throw new Error("请选择票据来源。");
      if (isCash && !settlement && !flow) throw new Error("请选择实际现金流水。");
      const fields = { kind, amount: cashMoneyInput(amount), occurred_on: isCash ? settlement?.occurred_on ?? flow!.occurred_on : date, remark: remark.trim() || null, item_id: targetRef?.id ?? null, source_item_id: sourceRef?.id ?? null, flow_id: isCash ? settlement?.flow_id ?? flow!.id : null };
      let body: Record<string, unknown>;
      if (settlement) {
        const versions = settlementVersions(settlement);
        for (const value of [targetRef, sourceRef]) if (value && !versions.items.some(row => row.id === value.id)) versions.items.push({ id: value.id, version: value.version });
        body = { ...fields, expected_version: settlement.version, expected_related_versions: versions };
      } else body = { id, ...fields, expected_item_version: targetRef?.version ?? null, expected_source_item_version: sourceRef?.version ?? null, expected_flow_version: flow?.version ?? null };
      await action.write(settlement ? `/settlements/${settlement.id}` : "/settlements", settlement ? "PUT" : "POST", body, onClose);
    } catch (error) { if (!(error instanceof Error)) throw error; action.setError(error.message); }
  }
  return <section className="cash-form" aria-label={settlement ? "更正处理记录" : "登记处理"}>
    <h3>{settlement ? "更正处理记录" : "登记处理"}</h3><CashNotice error={action.error} />
    <form className="cash-form" onSubmit={submit}>
      <CashSelect label="处理类型" value={kind} onChange={value => { setKind(value as CashSettlementKind); setFlow(null); }} disabled={Boolean(settlement && !["ticket_use", "ticket_offset"].includes(settlement.kind))} options={(settlement ? (settlement.kind === "ticket_use" || settlement.kind === "ticket_offset" ? ["ticket_use", "ticket_offset"] : [settlement.kind]) : [initialKind]).map(value => ({ value, label: settlementLabels[value as CashSettlementKind] }))} />
      {kind !== "ticket_use" && <div className="cash-toolbar"><span>目标：{chosenTarget?.content ?? "未选择"}</span>{!target && <Button size="sm" variant="tertiary" onPress={() => setPicker("target")}>选择目标</Button>}</div>}
      {!isCash && <div className="cash-toolbar"><span>来源：{chosenSource?.content ?? (kind === "non_ticket_offset" ? "其他明确非现金调整" : "未选择")}</span>{!source && <Button size="sm" variant="tertiary" onPress={() => setPicker("source")}>选择来源</Button>}{kind === "non_ticket_offset" && chosenSource && <Button size="sm" variant="tertiary" onPress={() => setSource(null)}>不关联费用</Button>}</div>}
      {picker && <CashItemPicker label={picker === "target" ? "选择目标事项" : "选择来源事项"} params={{ purpose: picker === "target" ? "settlement_target" : "settlement_source", settlement_kind: kind, source_item_id: picker === "target" ? chosenSource?.id : undefined, item_id: picker === "source" ? chosenTarget?.id : undefined }} onSelect={row => { if (picker === "target") { setTarget(row); setFlow(null); } else setSource(row); setPicker(null); }} onCancel={() => setPicker(null)} />}
      {isCash && !settlement && <><div className="cash-toolbar"><CashInput label="搜索已录现金" value={flowSearch} onChange={setFlowSearch} /><Button size="sm" variant="secondary" onPress={() => { setFlowKeyword(flowSearch); setFlowPage(1); }}>查询流水</Button></div><CashNotice error={flows.error?.message} />{flows.loading && <p role="status">正在读取可关联流水…</p>}{flows.data && !flows.loading && <><ul className="cash-choice-list">{flows.data.rows.map(row => <li key={row.id}><Button size="sm" variant={flow?.id === row.id ? "secondary" : "tertiary"} isDisabled={!row.selectable} onPress={() => { setFlow(row); setDate(row.occurred_on); }}>{row.occurred_on} · {row.content} · {row.from_account?.name ?? row.to_account?.name} · {cashAmount(row.amount)} · 可归属 {cashAmount(row.available_amount)} · {row.source_kind === "manual" ? "手工" : "每月任务"}</Button>{!row.selectable && <small>不符合方向、项目或可用额度</small>}</li>)}</ul>{flows.data.rows.length === 0 && <p>没有可关联现金。请先登记真实收付，不会自动造一笔。</p>}<FinanceTablePagination {...flows.data.pagination} pageSize={20} onPageChange={setFlowPage} /></>}{flow && <p>已选择：{flow.content} · 义务或费用可归属额 {cashAmount(flow.available_amount)}</p>}</>}
      <div className="cash-form-grid"><CashInput label="实际处理日期" type="date" value={date} onChange={setDate} disabled={isCash} required /><CashInput label="本次处理金额" value={amount} onChange={setAmount} required /></div>
      <CashInput label="用途 / 说明" value={remark} onChange={setRemark} required={kind === "ticket_use" || (kind === "non_ticket_offset" && !chosenSource)} />
      <p className="cash-muted">{isCash ? "只关联选中的现金，不生成第二笔流水。" : "此操作不产生现金流水，不改变现金账户余额。"}</p>
      <div className="cash-form-actions"><Button variant="secondary" onPress={onClose} isDisabled={action.busy}>取消处理</Button><Button type="submit" isDisabled={action.busy || flows.loading}>保存处理</Button></div>
    </form>
  </section>;
}

export function CashSettlementTable({ params, onItem, onFlow }: { params: QueryParams; onItem?: (id: string) => void; onFlow?: (id: string) => void }) {
  const [page, setPage] = useState(1); const [editing, setEditing] = useState<CashSettlement | null>(null); const [removing, setRemoving] = useState<CashSettlement | null>(null);
  const query = useCashQuery<CashPageRows<CashSettlement>>("/settlements", { ...params, page, page_size: 20 });
  const action = useItemWrite();
  return <section className="cash-section"><CashNotice error={query.error?.message ?? action.error} />{query.loading && <p role="status">正在读取处理明细…</p>}
    {query.data && !query.loading && <><FinanceTable ariaLabel="处理明细" minWidth={780}>
      <FinanceTableHeader><FinanceTableColumn isRowHeader>日期</FinanceTableColumn><FinanceTableColumn>处理类型</FinanceTableColumn><FinanceTableColumn>目标 / 来源</FinanceTableColumn><FinanceTableColumn>金额</FinanceTableColumn><FinanceTableColumn>说明</FinanceTableColumn><FinanceTableColumn>操作</FinanceTableColumn></FinanceTableHeader>
      <FinanceTableBody>{query.data.rows.map(row => <FinanceTableRow key={row.id} id={row.id} textValue={`${row.occurred_on} ${settlementLabels[row.kind]}`}>
        <FinanceTableCell columnRole="date">{row.occurred_on}</FinanceTableCell><FinanceTableCell columnRole="status">{settlementLabels[row.kind]}<small>{row.flow_id ? "实际现金" : "无现金收付"}</small></FinanceTableCell>
        <FinanceTableCell columnRole="description">{row.item_content ?? "无债务目标"}<small>{row.source_item_content ?? "—"}</small></FinanceTableCell><FinanceTableCell columnRole="amount">{cashAmount(row.amount)}</FinanceTableCell><FinanceTableCell columnRole="description">{row.remark ?? "—"}</FinanceTableCell>
        <FinanceTableCell columnRole="action"><div className="cash-actions">{row.flow_id && onFlow && <Button size="sm" variant="tertiary" onPress={() => onFlow(row.flow_id!)}>现金详情</Button>}{row.item_id && onItem && <Button size="sm" variant="tertiary" onPress={() => onItem(row.item_id!)}>事项</Button>}<Button size="sm" variant="tertiary" onPress={() => { setEditing(row); setRemoving(null); }}>更正</Button><Button size="sm" variant="tertiary" onPress={() => { setRemoving(row); setEditing(null); }}>撤销关联</Button></div></FinanceTableCell>
      </FinanceTableRow>)}</FinanceTableBody>
    </FinanceTable>{query.data.rows.length === 0 && <p>暂无处理明细。</p>}<FinanceTablePagination {...query.data.pagination} pageSize={20} onPageChange={setPage} /></>}
    {editing && <CashSettlementEditor key={editing.id} settlement={editing} initialKind={editing.kind} onClose={() => setEditing(null)} />}
    {removing && <div className="cash-confirm" role="alert"><p>撤销 {removing.occurred_on} 的「{settlementLabels[removing.kind]}」{cashAmount(removing.amount)}？实际现金保留。若票仍已使用，请选择“更正”改为票据使用，而不是撤销占用。</p><Button size="sm" variant="secondary" isDisabled={action.busy} onPress={() => setRemoving(null)}>取消</Button><Button size="sm" variant="danger" isDisabled={action.busy} onPress={() => void action.write(`/settlements/${removing.id}/remove`, "POST", { expected_version: removing.version, expected_related_versions: settlementVersions(removing) }, () => setRemoving(null))}>确认撤销错误关联</Button></div>}
  </section>;
}

const amountLabels: Record<string, string> = { original_amount: "原始金额", cash_settled_amount: "现金已结", ticket_offset_amount: "票抵", non_ticket_offset_amount: "无票 / 其他冲抵", remaining_obligation_amount: "当前未结", paid_amount: "已付款", refund_amount: "已退款", net_expense_amount: "真实花销", available_offset_amount: "可冲抵费用", provided_amount: "提供金额", used_amount: "已使用", offset_amount: "用于抵债", available_source_amount: "来源可用" };

export function CashItemDetail({ itemId, onClose, onFlow, onActualFlow }: { itemId: string; onClose: () => void; onFlow?: (id: string) => void; onActualFlow?: (item: CashItem, kind: CashSettlementKind) => void }) {
  const [currentId, setCurrentId] = useState(itemId);
  const query = useCashQuery<CashItemDetailData>(`/items/${currentId}`);
  const [editing, setEditing] = useState(false); const [actionKind, setActionKind] = useState<CashSettlementKind | null>(null);
  const [view, setView] = useState("target"); const [deleteConfirm, setDeleteConfirm] = useState(false); const [companyCreate, setCompanyCreate] = useState(false);
  const action = useItemWrite(); const item = query.data?.item;
  function openRelated(id: string) { setCurrentId(id); setActionKind(null); setView("target"); setDeleteConfirm(false); }
  if (editing && item) return <CashItemEditor item={item} onClose={() => setEditing(false)} />;
  if (companyCreate && item) return <CashItemEditor initialType="company_receivable" ticketSource={item} onClose={() => setCompanyCreate(false)} onSaved={openRelated} />;
  const cashKind: CashSettlementKind | null = item?.type === "loan" ? "cash_repayment" : item?.type === "company_receivable" ? "company_collection" : item?.type === "expense" ? "expense_payment" : null;
  return <AppDrawer open title="事项详情" width={860} className="cash-module cash-drawer" onClose={onClose} closeDisabled={action.busy}>
    <CashNotice error={query.error?.message ?? action.error} />{query.loading && <p role="status">正在读取事项…</p>}
    {item && query.data && !query.loading && <>
      <div className="cash-detail-heading"><h3>{item.content}</h3><p>{itemTypeLabels[item.type]} · {item.counterparty ?? item.ticket_provider ?? "—"} · {item.project_name_snapshot ?? "无项目"}</p></div>
      <dl className="cash-facts"><div><dt>{item.is_opening ? "起算日期" : "实际日期"}</dt><dd>{item.origin_date}</dd></div>{Object.entries(query.data.amounts).map(([key, value]) => <div key={key}><dt>{amountLabels[key]}</dt><dd>{cashAmount(value)}</dd></div>)}</dl>
      {item.bill_month && <p>账单月份：{item.bill_month}{item.origin_date.slice(0, 7) < item.bill_month ? " · 提前还（计入实际发生月份）" : ""}</p>}
      <p>{item.remark ?? "无备注"}</p>
      <div className="cash-toolbar"><Button size="sm" variant="secondary" onPress={() => setEditing(true)}>更正事项</Button>{item.origin_flow_id && onFlow ? <Button size="sm" variant="tertiary" onPress={() => onFlow(item.origin_flow_id!)}>来源流水 / 纠错</Button> : !item.origin_flow_id && <Button size="sm" variant="tertiary" onPress={() => setDeleteConfirm(true)}>删除错误事项</Button>}
        {cashKind && <><Button size="sm" variant="secondary" onPress={() => setActionKind(cashKind)}>关联已录现金</Button>{onActualFlow && <Button size="sm" onPress={() => onActualFlow(item, cashKind)}>登记实际收付</Button>}</>}
        {item.type === "expense" && <Button size="sm" variant="secondary" onPress={() => setActionKind("expense_refund")}>关联费用退款</Button>}
        {(item.type === "loan" || item.type === "company_receivable") && <><Button size="sm" variant="secondary" onPress={() => setActionKind("ticket_offset")}>票据抵债</Button><Button size="sm" variant="secondary" onPress={() => setActionKind("non_ticket_offset")}>无票 / 其他冲抵</Button></>}
        {item.type === "ticket_source" && <><Button size="sm" variant="secondary" onPress={() => setActionKind("ticket_use")}>登记使用</Button><Button size="sm" variant="secondary" onPress={() => setActionKind("ticket_offset")}>用于抵债</Button><Button size="sm" variant="secondary" onPress={() => setCompanyCreate(true)}>建立明确公司应收</Button></>}
      </div>
      {deleteConfirm && <div role="alert" className="cash-confirm"><p>确认删除此错误事项？这不是删除现金流水；仍有真实使用、结算或引用时，须先在处理明细中明确更正。</p><Button size="sm" variant="secondary" isDisabled={action.busy} onPress={() => setDeleteConfirm(false)}>取消</Button><Button size="sm" variant="danger" isDisabled={action.busy} onPress={() => void action.write(`/items/${item.id}/remove`, "POST", { expected_version: item.version }, onClose)}>确认删除事项</Button></div>}
      {actionKind && <CashSettlementEditor key={actionKind} initialKind={actionKind} target={item.type === "ticket_source" ? undefined : item} source={item.type === "ticket_source" ? item : undefined} onClose={() => setActionKind(null)} />}
      <CashTabs value={view} onChange={setView} tabs={[{ id: "target", label: item.type === "ticket_source" ? "使用 / 抵债明细" : "处理明细" }, ...(item.type === "expense" ? [{ id: "source", label: "作为冲抵来源" }] : []), ...(item.type === "ticket_source" ? [{ id: "receivables", label: "公司应收 / 实际回款" }] : item.type === "loan" || item.type === "company_receivable" ? [{ id: "expenses", label: "关联费用" }] : []), { id: "flows", label: "关联现金" }]} />
      {view === "flows" ? <CashItemFlows itemId={item.id} onFlow={onFlow} /> : view === "receivables" ? <CashItemPicker label="对应公司应收" params={{ type: "company_receivable", ticket_source_id: item.id }} onSelect={row => openRelated(row.id)} /> : view === "expenses" ? <CashItemPicker label="归属该往来的费用" params={{ type: "expense", related_obligation_id: item.id }} onSelect={row => openRelated(row.id)} /> : <CashSettlementTable key={`${item.id}-${view}`} params={item.type === "ticket_source" || view === "source" ? { source_item_id: item.id } : { item_id: item.id }} onFlow={onFlow} onItem={openRelated} />}
    </>}
    {query.error && <Button size="sm" variant="secondary" onPress={query.reload}>重新读取</Button>}
  </AppDrawer>;
}

function CashItemFlows({ itemId, onFlow }: { itemId: string; onFlow?: (id: string) => void }) {
  const [page, setPage] = useState(1);
  const query = useCashQuery<CashPageRows<{ id: string; occurred_on: string; kind: string; amount: string; content: string; source_kind: string }>>("/flows", { item_id: itemId, page, page_size: 20 });
  return <section><CashNotice error={query.error?.message} />{query.loading && <p role="status">正在读取关联现金…</p>}{query.data && !query.loading && <><FinanceTable ariaLabel="事项关联现金" minWidth={620}><FinanceTableHeader><FinanceTableColumn isRowHeader>日期</FinanceTableColumn><FinanceTableColumn>内容</FinanceTableColumn><FinanceTableColumn>方向 / 来源</FinanceTableColumn><FinanceTableColumn>金额</FinanceTableColumn><FinanceTableColumn>操作</FinanceTableColumn></FinanceTableHeader><FinanceTableBody>{query.data.rows.map(row => <FinanceTableRow key={row.id} id={row.id} textValue={row.content}><FinanceTableCell columnRole="date">{row.occurred_on}</FinanceTableCell><FinanceTableCell columnRole="description">{row.content}</FinanceTableCell><FinanceTableCell columnRole="status">{row.kind === "receipt" ? "收入" : row.kind === "payment" ? "支出" : "互转"} · {row.source_kind === "manual" ? "手工" : "每月任务"}</FinanceTableCell><FinanceTableCell columnRole="amount">{cashAmount(row.amount)}</FinanceTableCell><FinanceTableCell columnRole="action">{onFlow && <Button size="sm" variant="tertiary" onPress={() => onFlow(row.id)}>详情</Button>}</FinanceTableCell></FinanceTableRow>)}</FinanceTableBody></FinanceTable>{query.data.rows.length === 0 && <p>暂无关联现金。非现金处理不会生成流水。</p>}<FinanceTablePagination {...query.data.pagination} pageSize={20} onPageChange={setPage} /></>}</section>;
}
