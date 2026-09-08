import { Button } from "@heroui/react";
import { useState } from "react";
import { CashItemPicker } from "./CashItems";
import { CashInput, CashSelect } from "./CashUi";
import { CashConfigurationSelect } from "./CashFlowSelectors";
import { cashMoneyInput, itemTypeLabels, settlementLabels, type CashItem, type CashSettlementKind } from "./CashItems.types";
import type { CashFlowKind } from "./CashFlows.types";

export type FlowPart = {
  id: string; mode: "loan" | "expense" | "settlement" | "origin";
  amount: string; content: string; counterparty: string; group: string; direction: string;
  billLabel: string; billMonth: string; category: string; relatedLoanId: string; item: CashItem | null; kind: CashSettlementKind;
};
export function newFlowPart(mode: FlowPart["mode"], kind: CashFlowKind, item: CashItem | null = null, settlementKind?: CashSettlementKind): FlowPart {
  return { id: crypto.randomUUID(), mode, amount: "", content: "", counterparty: "", group: "", direction: "", billLabel: "", billMonth: "", category: "", relatedLoanId: "", item,
    kind: settlementKind ?? (item?.type === "company_receivable" ? "company_collection" : item?.type === "expense" ? kind === "receipt" ? "expense_refund" : "expense_payment" : "cash_repayment") };
}

export function flowCompositionPayload(parts: FlowPart[], date: string, projectId: string | null, kind: CashFlowKind) {
  const related_items: Record<string, unknown>[] = []; const origin_items: Record<string, unknown>[] = []; const allocations: Record<string, unknown>[] = [];
  for (const part of parts) {
    if (part.mode === "loan" || part.mode === "expense") {
      const amount = cashMoneyInput(part.amount);
      if (!part.content.trim()) throw new Error("请填写新增事项的内容。");
      if (part.mode === "loan" && (!part.counterparty.trim() || !part.group || !part.direction)) throw new Error("请填写往来对象、账簿分类及借款方向。");
      if (part.mode === "loan" && part.group === "personal" && part.direction !== "receivable") throw new Error("个人借款 / 代付只能登记对方应归还。");
      if (Boolean(part.billLabel) !== Boolean(part.billMonth)) throw new Error("账单标识和账单月份须同时填写。");
      if (part.mode === "expense" && part.relatedLoanId && !parts.some(row => row.mode === "loan" && row.id === part.relatedLoanId)) throw new Error("费用归属的借款已被移除，请重新选择或明确取消关联。");
      if (part.mode === "expense" && kind !== "payment") throw new Error("新增费用付款须使用支出；费用退款请选择已有费用。");
      if (part.mode === "expense" && !part.category) throw new Error("请选择新增事项的费用类型。");
      related_items.push({ id: part.id, type: part.mode, origin_date: date, original_amount: amount, content: part.content.trim(), oa_project_id: projectId,
        category_id: part.mode === "expense" ? part.category : null,
        ...(part.mode === "loan" ? { counterparty: part.counterparty.trim(), ledger_group: part.group, obligation_direction: part.direction } : {}),
        ...(part.billLabel ? { bill_label_id: part.billLabel, bill_month: part.billMonth } : {}),
        ...(part.mode === "expense" && part.relatedLoanId ? { related_obligation_id: part.relatedLoanId } : {}),
      });
      // The source flow itself pays a newly-created expense. A second allocation would double-count it.
    } else {
      if (!part.item) throw new Error("请选择要关联的已有事项。");
      if (part.mode === "origin") origin_items.push({ item_id: part.item.id, expected_item_version: part.item.version });
      else allocations.push({ id: part.id, item_id: part.item.id, target_is_new: false, expected_item_version: part.item.version, kind: part.kind, amount: cashMoneyInput(part.amount) });
    }
  }
  return { related_items, origin_items, allocations };
}

export function CashFlowComposition({ parts, onChange, kind, existingItem, personalEntry = false, disabled }: {
  parts: FlowPart[]; onChange: (parts: FlowPart[]) => void; kind: CashFlowKind; existingItem?: CashItem; personalEntry?: boolean; disabled: boolean;
}) {
  const [picking, setPicking] = useState<string | null>(null);
  function update(id: string, patch: Partial<FlowPart>) { onChange(parts.map(part => part.id === id ? { ...part, ...patch } : part)); }
  if (kind === "transfer") return null;
  return <section className="cash-composition">
    <div className="cash-toolbar"><h3>资金用途与事项</h3>
      {!existingItem && <><Button size="sm" variant="secondary" isDisabled={disabled} onPress={() => onChange([...parts, newFlowPart("loan", kind)])}>新增借款 / 代付</Button>
        {kind === "payment" && <Button size="sm" variant="secondary" isDisabled={disabled} onPress={() => onChange([...parts, newFlowPart("expense", kind)])}>新增真实费用</Button>}
        <Button size="sm" variant="tertiary" isDisabled={disabled} onPress={() => onChange([...parts, newFlowPart("origin", kind)])}>补记借款现金来源</Button></>}
      <Button size="sm" variant="secondary" isDisabled={disabled} onPress={() => onChange([...parts, newFlowPart("settlement", kind)])}>关联已有事项</Button>
    </div>
    {parts.length === 0 && <p className="cash-hint">普通收付可直接保存。涉及借款、真实费用或归还时，在此明确登记；不会按分类自动猜账。</p>}
    {parts.map((part, index) => <div className="cash-composition-row" key={part.id}>
      <div className="cash-toolbar"><h4>{index + 1}. {part.mode === "loan" ? "新增借款 / 代付" : part.mode === "expense" ? "新增真实费用" : part.mode === "origin" ? "补记现金来源" : "已有事项结算"}</h4>
        {!(existingItem && index === 0) && <Button size="sm" variant="tertiary" isDisabled={disabled} onPress={() => onChange(parts.filter(row => row.id !== part.id))}>移除</Button>}</div>
      {part.mode === "loan" || part.mode === "expense" ? <div className="cash-form-grid">
        <CashInput label="事项金额" value={part.amount} onChange={amount => update(part.id, { amount })} required disabled={disabled} />
        <CashInput label="事项内容" value={part.content} onChange={content => update(part.id, { content })} required disabled={disabled} />
        {part.mode === "loan" && <>
          <CashInput label="往来对象" value={part.counterparty} onChange={counterparty => update(part.id, { counterparty })} required disabled={disabled || personalEntry && index === 0} />
          <CashSelect label="账簿分类" value={part.group} onChange={group => update(part.id, { group, direction: group === "personal" && part.direction === "payable" ? "" : part.direction })} required disabled={disabled || personalEntry && index === 0} options={[{ value: "company", label: "公司" }, { value: "external_person", label: "外部人员" }, { value: "personal", label: "个人借款 / 代付" }]} />
          <CashSelect label="借款方向" value={part.direction} onChange={direction => update(part.id, { direction })} required disabled={disabled} options={[{ value: "receivable", label: "对方应归还" }, { value: "payable", label: "我方应归还", disabled: part.group === "personal" }]} />
        </>}
        {part.mode === "expense" && <><CashConfigurationSelect name="categories" label="事项费用类型" value={part.category} groups={["payment"]} onChange={category => update(part.id, { category })} required disabled={disabled} /><CashSelect label="费用归属本次借款（可选）" value={part.relatedLoanId} onChange={relatedLoanId => update(part.id, { relatedLoanId })} disabled={disabled}
          options={[{ value: "", label: "不关联借款" }, ...parts.filter(row => row.mode === "loan").map((row, loanIndex) => ({ value: row.id, label: `${loanIndex + 1}. ${row.content || "未填写内容的借款"}` }))]} /></>}
        <CashConfigurationSelect name="bill-labels" label="账单标识（可选）" value={part.billLabel} onChange={billLabel => update(part.id, { billLabel })} disabled={disabled} />
        <CashInput label="账单月份（可选）" type="month" value={part.billMonth} onChange={billMonth => update(part.id, { billMonth })} disabled={disabled} />
      </div> : <>
        {part.mode === "settlement" && <CashSelect label="处理类型" value={part.kind} onChange={value => update(part.id, { kind: value as CashSettlementKind, item: null })}
          disabled={disabled || Boolean(existingItem && index === 0)} options={(kind === "receipt" ? ["cash_repayment", "company_collection", "expense_refund"] : ["cash_repayment", "expense_payment"]).map(value => ({ value, label: settlementLabels[value as CashSettlementKind] }))} />}
        <p>{part.item ? `${itemTypeLabels[part.item.type]} · ${part.item.content} · ${part.item.project_name_snapshot === null ? "无项目" : part.item.project_name_snapshot}` : "尚未选择事项"}</p>
        {!(existingItem && index === 0) && <Button size="sm" variant="secondary" isDisabled={disabled} onPress={() => setPicking(part.id)}>选择事项</Button>}
        {picking === part.id && <CashItemPicker label="选择要关联的事项" params={part.mode === "origin" ? { type: "loan" } : { purpose: "settlement_target", settlement_kind: part.kind }} onCancel={() => setPicking(null)} onSelect={item => { update(part.id, { item }); setPicking(null); }} />}
        {part.mode === "settlement" && <CashInput label="本次处理金额" value={part.amount} onChange={amount => update(part.id, { amount })} required disabled={disabled} />}
      </>}
    </div>)}
    {parts.length > 0 && <p className="cash-hint">现金只登记一次。借款资金与费用处理按各自口径校验，保存时全部一起成功或一起撤回。</p>}
  </section>;
}
