import { Button } from "@heroui/react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useCashQuery } from "../../features/cash/hooks";
import { FinanceTablePagination } from "../common/FinanceTable";
import { CashItemPicker } from "./CashItems";
import { cashAmount, cashMoneyInput, cashToday, itemTypeLabels, settlementLabels, settlementVersions,
  type CashItem, type CashPageRows, type CashSettlement, type CashSettlementKind } from "./CashItems.types";
import { CashInput, CashNotice, CashSelect, CashTabs } from "./CashUi";
import { CashConfigurationSelect } from "./CashFlowSelectors";

type Version = { id: string; version: number };
type Versions = { items: Version[]; flows: Version[]; occurrences: Version[] };
export type CashFlowCorrectionValue = {
  source_corrections: unknown[]; settlement_changes: unknown[]; item_reference_changes: unknown[];
  expected_related_versions: Versions;
};
type Change = { key: string; label: string; payload: Record<string, unknown>; versions: Versions };
type FlowChoice = Version & { occurred_on: string; content: string; amount: string; kind: string;
  task: { occurrence_id: string; occurrence_version: number } | null };
const emptyVersions = (): Versions => ({ items: [], flows: [], occurrences: [] });

export function mergeCashCorrectionVersions(values: Versions[]): Versions {
  const merged = emptyVersions();
  for (const group of ["items", "flows", "occurrences"] as const) {
    const entries = new Map<string, number>();
    for (const value of values) for (const row of value[group]) {
      if (entries.has(row.id) && entries.get(row.id) !== row.version) throw new Error("关联记录在选择期间发生变化，请清除本次纠错并重新读取。");
      entries.set(row.id, row.version);
    }
    merged[group] = Array.from(entries, ([id, version]) => ({ id, version }));
  }
  return merged;
}

function flowVersions(flow: FlowChoice): Versions {
  return { items: [], flows: [{ id: flow.id, version: flow.version }],
    occurrences: flow.task ? [{ id: flow.task.occurrence_id, version: flow.task.occurrence_version }] : [] };
}

function CorrectionFlowPicker({ excludeId, onSelect, onClose }: {
  excludeId?: string; onSelect: (row: FlowChoice) => void; onClose: () => void;
}) {
  const [month, setMonth] = useState(cashToday().slice(0, 7));
  const [search, setSearch] = useState(""); const [keyword, setKeyword] = useState(""); const [page, setPage] = useState(1);
  const validMonth = /^\d{4}-(0[1-9]|1[0-2])$/.test(month);
  const [year, number] = month.split("-").map(Number);
  const end = validMonth ? `${month}-${new Date(Date.UTC(year, number, 0)).getUTCDate()}` : "";
  const query = useCashQuery<CashPageRows<FlowChoice>>(validMonth ? "/flows" : null,
    { date_from: `${month}-01`, date_to: end, keyword, page, page_size: 20 });
  return <section className="cash-picker" aria-label="选择正确现金流水">
    <div className="cash-toolbar"><CashInput label="流水月份" type="month" value={month} onChange={value => { setMonth(value); setPage(1); }} />
      <CashInput label="搜索正确流水" value={search} onChange={setSearch} />
      <Button type="button" size="sm" variant="secondary" onPress={() => { setKeyword(search); setPage(1); }}>查询流水</Button>
      <Button type="button" size="sm" variant="tertiary" onPress={onClose}>取消选择</Button></div>
    <CashNotice error={query.error?.message} />{query.loading && <p role="status">正在读取现金流水…</p>}
    {query.data && <><ul className="cash-choice-list">{query.data.rows.map(row => <li key={row.id}>
      <Button type="button" size="sm" variant="tertiary" isDisabled={row.id === excludeId || row.kind === "transfer"} onPress={() => onSelect(row)}>
        {row.occurred_on} · {row.content} · {cashAmount(row.amount)}</Button></li>)}</ul>
      {!query.data.rows.length && <p>本月没有匹配流水，可切换月份查询。不会自动新增现金。</p>}
      <FinanceTablePagination {...query.data.pagination} pageSize={20} onPageChange={setPage} /></>}
    {query.error && <Button type="button" size="sm" onPress={query.reload}>重新读取</Button>}
  </section>;
}

function SourceEditor({ item, flowId, mode, onSave, onClose }: {
  item: CashItem; flowId: string; mode: "edit" | "delete"; onSave: (change: Change) => void; onClose: () => void;
}) {
  const [action, setAction] = useState(""); const [amount, setAmount] = useState(item.original_amount);
  const [flow, setFlow] = useState<FlowChoice | null>(null); const [picking, setPicking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  function adopt() {
    try {
      if (!action) throw new Error("请明确选择此来源事项的处理方式。");
      const payload: Record<string, unknown> = { action, item_id: item.id, expected_version: item.version };
      let versions: Versions = { items: [{ id: item.id, version: item.version }], flows: [], occurrences: [] };
      if (action === "correct_amount") payload.original_amount = cashMoneyInput(amount);
      if (action === "rebind_flow") {
        if (!flow) throw new Error("请从已录现金中选择正确来源。");
        payload.new_flow_id = flow.id; payload.expected_new_flow_version = flow.version;
        versions = mergeCashCorrectionVersions([versions, flowVersions(flow)]);
      }
      onSave({ key: item.id, label: `${item.content}：${sourceLabel(action)}`, payload, versions });
    } catch (cause) { if (cause instanceof Error) setError(cause.message); else throw cause; }
  }
  return <section className="cash-form" aria-label="来源事项纠错">
    <h4>{item.content} · {cashAmount(item.original_amount)}</h4><CashNotice error={error} />
    <CashSelect label="来源处理方式" value={action} onChange={value => { setAction(value); setError(null); setFlow(null); }} options={[
      { value: "keep_independent", label: sourceLabel("keep_independent") },
      { value: "delete_false_item", label: sourceLabel("delete_false_item") },
      { value: "rebind_flow", label: sourceLabel("rebind_flow") },
      ...(mode === "edit" ? [{ value: "correct_amount", label: sourceLabel("correct_amount") }] : []),
    ]} />
    {action === "correct_amount" && <CashInput label="正确原始金额" value={amount} onChange={setAmount} required />}
    {action === "rebind_flow" && <><p>正确来源：{flow ? `${flow.occurred_on} · ${flow.content} · ${cashAmount(flow.amount)}` : "尚未选择"}</p>
      <Button type="button" size="sm" variant="secondary" onPress={() => setPicking(true)}>选择正确流水</Button>
      {picking && <CorrectionFlowPicker excludeId={flowId} onSelect={row => { setFlow(row); setPicking(false); }} onClose={() => setPicking(false)} />}</>}
    {action === "delete_false_item" && <p>只删除错误事项及其错误分配；真实其他流水保留。非现金处理和子事项引用须在下面明确更正。</p>}
    {action === "keep_independent" && <p>事项真实但来源错误：解除此来源，保留原义务和后续真实处理。</p>}
    <div className="cash-form-actions"><Button type="button" size="sm" variant="secondary" onPress={onClose}>取消本项</Button>
      <Button type="button" size="sm" onPress={adopt}>采用来源纠错</Button></div>
  </section>;
}

function sourceLabel(action: string): string {
  const labels: Record<string, string> = { keep_independent: "保留真实事项，解除错误来源", delete_false_item: "删除误录事项，保留真实其他现金", rebind_flow: "改绑另一笔正确现金", correct_amount: "更正来源事项金额" };
  return labels[action];
}

function SettlementCorrection({ row, onSave, onClose }: { row: CashSettlement; onSave: (change: Change) => void; onClose: () => void }) {
  const [action, setAction] = useState(""); const [kind, setKind] = useState(row.kind);
  const [amount, setAmount] = useState(row.amount); const [date, setDate] = useState(row.occurred_on); const [remark, setRemark] = useState(row.remark ?? "");
  const [category, setCategory] = useState(row.category_id ?? "");
  const [target, setTarget] = useState<(Version & { content: string }) | null>(row.item_id ? { id: row.item_id, version: row.item_version!, content: row.item_content! } : null);
  const [source, setSource] = useState<(Version & { content: string }) | null>(row.source_item_id ? { id: row.source_item_id, version: row.source_item_version!, content: row.source_item_content! } : null);
  const [flow, setFlow] = useState<FlowChoice | null>(null); const [picker, setPicker] = useState<"target" | "source" | "flow" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isCash = ["cash_repayment", "company_collection", "expense_payment", "expense_refund"].includes(kind);
  function adopt() {
    try {
      if (!action) throw new Error("请选择移除或更正此处理记录。");
      let versions = settlementVersions(row);
      const payload: Record<string, unknown> = { id: row.id, expected_version: row.version, action };
      if (action === "update") {
        if (kind !== "ticket_use" && !target) throw new Error("请选择真实目标事项。");
        if (["ticket_use", "ticket_offset"].includes(kind) && !source) throw new Error("请选择票据来源。");
        if (kind === "non_ticket_offset" && !source && !category) throw new Error("请选择无来源调整分类。");
        const proposed = { kind, amount: cashMoneyInput(amount), occurred_on: isCash ? flow?.occurred_on ?? row.occurred_on : date,
          category_id: kind === "non_ticket_offset" && !source ? category : null,
          remark: remark.trim() || null, item_id: kind === "ticket_use" ? null : target?.id ?? null,
          source_item_id: isCash ? null : source?.id ?? null, flow_id: isCash ? flow?.id ?? row.flow_id : null };
        const fields = Object.fromEntries(Object.entries(proposed).filter(([key, value]) => row[key as keyof CashSettlement] !== value));
        if (!Object.keys(fields).length) throw new Error("尚未修改此处理记录。");
        if (!proposed.occurred_on) throw new Error("请选择实际处理日期。");
        if ((kind === "ticket_use" || kind === "non_ticket_offset" && !source) && !proposed.remark) throw new Error("请输入本次处理说明。");
        payload.fields = fields;
        versions = mergeCashCorrectionVersions([versions, { items: [kind === "ticket_use" ? null : target, isCash ? null : source].filter((item): item is Version & { content: string } => item !== null).map(({ id, version }) => ({ id, version })), flows: [], occurrences: [] }, ...(flow ? [flowVersions(flow)] : [])]);
      }
      onSave({ key: row.id, label: `${row.occurred_on} ${settlementLabels[row.kind]}：${action === "remove" ? "移除错误处理" : "更正处理"}`, payload, versions });
    } catch (cause) { if (cause instanceof Error) setError(cause.message); else throw cause; }
  }
  const targetType = kind === "cash_repayment" ? "loan" : kind === "company_collection" ? "company_receivable" : kind.startsWith("expense_") ? "expense" : undefined;
  return <section className="cash-form" aria-label="关联处理纠错"><h4>{settlementLabels[row.kind]} · {cashAmount(row.amount)}</h4><CashNotice error={error} />
    <CashSelect label="处理记录纠错方式" value={action} onChange={value => { setAction(value); setError(null); }} options={[{ value: "remove", label: "移除误录的处理 / 分配" }, { value: "update", label: "更正真实处理" }]} />
    {action === "remove" && <p>仅移除此关联，不删除其他真实现金。票仍真实使用时，应改为票据使用而非移除。</p>}
    {action === "update" && <><CashSelect label="更正后处理类型" value={kind} onChange={value => setKind(value as CashSettlementKind)} options={(["ticket_use", "ticket_offset"].includes(row.kind) ? ["ticket_use", "ticket_offset"] : [row.kind]).map(value => ({ value, label: settlementLabels[value as CashSettlementKind] }))} />
      {kind !== "ticket_use" && <div className="cash-toolbar"><span>目标：{target?.content ?? "未选择"}</span><Button type="button" size="sm" variant="tertiary" onPress={() => setPicker("target")}>更正目标事项</Button></div>}
      {!isCash && <div className="cash-toolbar"><span>来源：{source?.content ?? "无来源事项"}</span><Button type="button" size="sm" variant="tertiary" onPress={() => setPicker("source")}>更正来源事项</Button>{kind === "non_ticket_offset" && source && <Button type="button" size="sm" variant="tertiary" onPress={() => setSource(null)}>解除费用来源</Button>}</div>}
      {isCash && <div className="cash-toolbar"><span>现金：{flow?.content ?? "原关联现金"}</span><Button type="button" size="sm" variant="tertiary" onPress={() => setPicker("flow")}>更正关联流水</Button></div>}
      {(picker === "target" || picker === "source") && <CashItemPicker label={picker === "target" ? "选择正确目标" : "选择正确来源"} params={{ type: picker === "target" ? targetType : kind === "non_ticket_offset" ? "expense" : "ticket_source" }} onSelect={item => { if (picker === "target") setTarget(item); else setSource(item); setPicker(null); }} onCancel={() => setPicker(null)} />}
      {picker === "flow" && <CorrectionFlowPicker onSelect={item => { setFlow(item); setPicker(null); }} onClose={() => setPicker(null)} />}
      <div className="cash-form-grid"><CashInput label="更正处理金额" value={amount} onChange={setAmount} required /><CashInput label="更正处理日期" type="date" value={flow?.occurred_on ?? date} onChange={setDate} disabled={isCash} required /></div>
      <CashInput label="更正处理说明" value={remark} onChange={setRemark} />
      {kind === "non_ticket_offset" && !source && <CashConfigurationSelect name="categories" label="无来源调整分类" value={category} selected={row.category} groups={["turnover"]} onChange={setCategory} required />}</>}
    <div className="cash-form-actions"><Button type="button" size="sm" variant="secondary" onPress={onClose}>取消本项</Button><Button type="button" size="sm" onPress={adopt}>采用处理纠错</Button></div>
  </section>;
}

function ReferenceCorrection({ row, onSave, onClose }: { row: CashItem; onSave: (change: Change) => void; onClose: () => void }) {
  const field = row.type === "expense" ? "related_obligation_id" : "ticket_source_id";
  const [action, setAction] = useState(""); const [target, setTarget] = useState<CashItem | null>(null);
  const [picking, setPicking] = useState(false); const [error, setError] = useState<string | null>(null);
  function adopt() {
    if (!action || action === "rebind" && !target) { setError("请选择解除引用或明确的正确引用事项。"); return; }
    const nextId = action === "detach" ? null : target!.id;
    if (nextId === row[field]) { setError("新引用与原引用相同。"); return; }
    onSave({ key: row.id, label: `${row.content}：${action === "detach" ? "解除错误引用，保留真实事项" : "更正引用"}`,
      payload: { item_id: row.id, expected_version: row.version, [field]: nextId },
      versions: { items: [{ id: row.id, version: row.version }, ...(action === "rebind" ? [{ id: target!.id, version: target!.version }] : [])], flows: [], occurrences: [] } });
  }
  return <section className="cash-form" aria-label="子事项引用纠错"><h4>{row.content}</h4><CashNotice error={error} />
    <CashSelect label="引用处理方式" value={action} onChange={setAction} options={[{ value: "detach", label: "解除错误引用，保留真实子事项" }, { value: "rebind", label: "引用另一正确事项" }]} />
    {action === "rebind" && <><p>正确事项：{target?.content ?? "尚未选择"}</p><Button type="button" size="sm" onPress={() => setPicking(true)}>选择正确引用</Button>
      {picking && <CashItemPicker label="选择正确引用事项" params={row.type === "company_receivable" ? { type: "ticket_source" } : {}} onSelect={item => { setTarget(item); setPicking(false); }} onCancel={() => setPicking(false)} />}</>}
    <div className="cash-form-actions"><Button type="button" size="sm" variant="secondary" onPress={onClose}>取消本项</Button><Button type="button" size="sm" onPress={adopt}>采用引用纠错</Button></div>
  </section>;
}

type Props = { flowId: string; mode: "edit" | "delete"; onChange: (value: CashFlowCorrectionValue) => void;
  onValidityChange?: (valid: boolean) => void };
export function CashFlowCorrections(props: Props) {
  return <CorrectionsPanel key={`${props.flowId}:${props.mode}`} {...props} />;
}

function CorrectionsPanel({ flowId, mode, onChange, onValidityChange }: Props) {
  const [view, setView] = useState("sources"); const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<CashItem | null>(null); const [detailView, setDetailView] = useState("target"); const [detailPage, setDetailPage] = useState(1);
  const [editor, setEditor] = useState<{ type: "source"; row: CashItem } | { type: "settlement"; row: CashSettlement } | { type: "reference"; row: CashItem } | null>(null);
  const [sources, setSources] = useState<Change[]>([]); const [settlements, setSettlements] = useState<Change[]>([]); const [references, setReferences] = useState<Change[]>([]);
  const sourcesQuery = useCashQuery<CashPageRows<CashItem>>(view === "sources" ? "/items" : null, { origin_flow_id: flowId, page, page_size: 20 });
  const flowsQuery = useCashQuery<CashPageRows<CashSettlement>>(view === "allocations" ? "/settlements" : null, { flow_id: flowId, page, page_size: 20 });
  const details = useCashQuery<CashPageRows<CashSettlement>>(selected && detailView !== "references" ? "/settlements" : null,
    { [detailView === "source" ? "source_item_id" : "item_id"]: selected?.id, page: detailPage, page_size: 20 });
  const children = useCashQuery<CashPageRows<CashItem>>(selected && detailView === "references" ? "/items" : null,
    { [selected?.type === "ticket_source" ? "ticket_source_id" : "related_obligation_id"]: selected?.id, page: detailPage, page_size: 20 });
  const result = useMemo(() => {
    try {
      if (sources.length + settlements.length + references.length > 100) throw new Error("一次最多 100 项纠错，请取消超出项并分批处理。");
      return { value: { source_corrections: sources.map(row => row.payload), settlement_changes: settlements.map(row => row.payload), item_reference_changes: references.map(row => row.payload),
        expected_related_versions: mergeCashCorrectionVersions([...sources, ...settlements, ...references].map(row => row.versions)) }, error: null };
    } catch (cause) { if (cause instanceof Error) return { value: null, error: cause.message }; throw cause; }
  }, [sources, settlements, references]);
  const callbacks = useRef({ onChange, onValidityChange }); callbacks.current = { onChange, onValidityChange };
  useEffect(() => { if (result.value) callbacks.current.onChange(result.value); }, [result]);
  useEffect(() => { callbacks.current.onValidityChange?.(!editor && !result.error); }, [editor, result.error]);
  function adopt(change: Change, group: "source" | "settlement" | "reference") {
    const setter = group === "source" ? setSources : group === "settlement" ? setSettlements : setReferences;
    setter(rows => [...rows.filter(row => row.key !== change.key), change]); setEditor(null);
  }
  function rowsView(rows: CashSettlement[]) {
    return <ul className="cash-choice-list">{rows.map(row => <li key={row.id}><span>{row.occurred_on} · {settlementLabels[row.kind]} · {cashAmount(row.amount)} · {row.item_content ?? row.source_item_content}</span>
      <Button type="button" size="sm" variant="tertiary" onPress={() => setEditor({ type: "settlement", row })}>更正此处理</Button></li>)}</ul>;
  }
  return <section className="cash-section" aria-label="现金来源与关联纠错">
    <h3>来源与关联纠错</h3><p className="cash-muted">仅选择确实错误的项目。这里不立即写入，最终随本笔现金{mode === "edit" ? "保存" : "删除"}在同一事务提交。</p>
    <CashNotice error={result.error} />
    {!!(sources.length + settlements.length + references.length) && <section aria-label="待提交纠错"><h4>已采用 {sources.length + settlements.length + references.length} 项纠错</h4>
      {([ ["source", sources, setSources], ["settlement", settlements, setSettlements], ["reference", references, setReferences] ] as const).map(([group, rows, setter]) => <ul key={group}>{rows.map(row => <li key={row.key}>{row.label}<Button type="button" size="sm" variant="tertiary" onPress={() => setter(values => values.filter(value => value.key !== row.key))}>取消此纠错</Button></li>)}</ul>)}
      <Button type="button" size="sm" variant="secondary" onPress={() => { setSources([]); setSettlements([]); setReferences([]); setEditor(null); sourcesQuery.reload(); flowsQuery.reload(); details.reload(); children.reload(); }}>清除纠错并重新读取</Button>
    </section>}
    {editor?.type === "source" && <SourceEditor key={`source:${editor.row.id}`} item={editor.row} flowId={flowId} mode={mode} onSave={row => adopt(row, "source")} onClose={() => setEditor(null)} />}
    {editor?.type === "settlement" && <SettlementCorrection key={`settlement:${editor.row.id}`} row={editor.row} onSave={row => adopt(row, "settlement")} onClose={() => setEditor(null)} />}
    {editor?.type === "reference" && <ReferenceCorrection key={`reference:${editor.row.id}`} row={editor.row} onSave={row => adopt(row, "reference")} onClose={() => setEditor(null)} />}
    {!editor && <><CashTabs value={view} onChange={value => { setView(value); setPage(1); setSelected(null); }} tabs={[{ id: "sources", label: "本笔来源事项" }, { id: "allocations", label: "本笔现金分配" }]} />
      <CashNotice error={sourcesQuery.error?.message ?? flowsQuery.error?.message} />{(sourcesQuery.loading || flowsQuery.loading) && <p role="status">正在读取关联记录…</p>}
      {view === "sources" && sourcesQuery.data && <><ul className="cash-choice-list">{sourcesQuery.data.rows.map(row => <li key={row.id}>
        <span>{row.content} · {itemTypeLabels[row.type]} · {cashAmount(row.original_amount)}</span><Button type="button" size="sm" variant="tertiary" onPress={() => setEditor({ type: "source", row })}>更正来源</Button>
        <Button type="button" size="sm" variant="tertiary" onPress={() => { setSelected(row); setDetailView("target"); setDetailPage(1); }}>后续处理与引用</Button></li>)}</ul>
        {!sourcesQuery.data.rows.length && <p>本笔现金没有来源事项。</p>}<FinanceTablePagination {...sourcesQuery.data.pagination} pageSize={20} onPageChange={setPage} /></>}
      {view === "allocations" && flowsQuery.data && <>{rowsView(flowsQuery.data.rows)}{!flowsQuery.data.rows.length && <p>本笔现金没有分配记录。</p>}<FinanceTablePagination {...flowsQuery.data.pagination} pageSize={20} onPageChange={setPage} /></>}
      {(sourcesQuery.error || flowsQuery.error) && <Button type="button" size="sm" onPress={() => { sourcesQuery.reload(); flowsQuery.reload(); }}>重新读取关联</Button>}
      {selected && <section aria-label="来源事项后续关联"><h4>{selected.content} · 后续关联</h4>
        <CashTabs value={detailView} onChange={value => { setDetailView(value); setDetailPage(1); }} tabs={[{ id: "target", label: "作为目标的处理" }, { id: "source", label: "作为来源的处理" }, { id: "references", label: "子事项引用" }]} />
        <CashNotice error={details.error?.message ?? children.error?.message} />{(details.loading || children.loading) && <p role="status">正在读取后续关联…</p>}
        {details.data && <>{rowsView(details.data.rows)}{!details.data.rows.length && <p>没有此类处理记录。</p>}<FinanceTablePagination {...details.data.pagination} pageSize={20} onPageChange={setDetailPage} /></>}
        {children.data && <><ul className="cash-choice-list">{children.data.rows.map(row => <li key={row.id}><span>{row.content} · {cashAmount(row.original_amount)}</span><Button type="button" size="sm" variant="tertiary" onPress={() => setEditor({ type: "reference", row })}>更正引用</Button></li>)}</ul>{!children.data.rows.length && <p>没有引用此事项的子事项。</p>}<FinanceTablePagination {...children.data.pagination} pageSize={20} onPageChange={setDetailPage} /></>}
        {(details.error || children.error) && <Button type="button" size="sm" onPress={() => { details.reload(); children.reload(); }}>重新读取后续关联</Button>}
      </section>}
    </>}
  </section>;
}
