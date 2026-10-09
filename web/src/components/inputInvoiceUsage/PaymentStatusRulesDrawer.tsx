import { Button, Checkbox, Input, ListBox, Select, Table, TextField } from "@heroui/react";
import { closestCenter, DndContext, DragOverlay, KeyboardSensor, MeasuringStrategy, PointerSensor, pointerWithin, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { type CSSProperties, type ReactNode, useState } from "react";
import SortablePaymentRuleRow from "./SortablePaymentRuleRow";
import PaymentRuleApplicantSelect from "./PaymentRuleApplicantSelect";
import AppDrawer from "../common/AppDrawer";
import AppDialog from "../common/AppDialog";
import type { FinanceTableColumnRole } from "../common/FinanceTable";
import { usePaymentStatusRules, type PaymentStatusRulesPorts } from "../../features/inputInvoiceUsage/usePaymentStatusRules";
import type { InputInvoiceUsagePaymentStatusRule, InvoiceNetSignOperator, PaymentComparisonOperator } from "../../features/inputInvoiceUsage/types";
import "./paymentStatusRules.css";
export type PaymentStatusRule = InputInvoiceUsagePaymentStatusRule;
export type { PaymentStatusRulesPayload } from "../../features/inputInvoiceUsage/usePaymentStatusRules";

const booleanOptions = [{ id: "true", label: "✓" }, { id: "false", label: "✕" }];
function RuleSelect({ label, value, options, disabled, onChange }: { label: string; value: string; options: { id: string; label: string }[]; disabled: boolean; onChange: (value: string) => void }) {
  const [open, setOpen] = useState(false);
  return <Select isOpen={open} onOpenChange={setOpen} className="payment-rule-cell-select" aria-label={label} selectedKey={value} isDisabled={disabled} onSelectionChange={key => { if (key != null) { onChange(String(key)); setOpen(false); } }}>
    <Select.Trigger><Select.Value /></Select.Trigger><Select.Popover><ListBox>
      {options.map(option => <ListBox.Item id={option.id} key={option.id} textValue={option.label}>{option.label}</ListBox.Item>)}
    </ListBox></Select.Popover>
  </Select>;
}
// A native table keeps form controls and dnd-kit in charge of their keyboard events.
// The shared finance grid intentionally owns arrow navigation and remains unchanged.
function RuleCell({ children, columnRole, className = "" }: { children: ReactNode; columnRole: FinanceTableColumnRole; className?: string }) {
  return <td data-column-role={columnRole} className={`table__cell finance-table__cell ${className}`}>{children}</td>;
}
export default function PaymentStatusRulesDrawer(props: PaymentStatusRulesPorts & { onClose: () => void }) {
  const state = usePaymentStatusRules(props);
  const [confirm, setConfirm] = useState<"close" | "reload" | null>(null);
  const [adding, setAdding] = useState(false);
  const [newGroup, setNewGroup] = useState("true");
  const [newLabel, setNewLabel] = useState("new");
  const [activeId, setActiveId] = useState<string | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const groupedRules = [true, false].flatMap(hasBank => {
    const members = state.rules.map((rule, index) => ({ rule, index })).filter(({ rule }) => rule.conditions?.hasBank === hasBank);
    return members.map((member, groupIndex) => ({ ...member, hasBank, groupIndex, groupCount: members.length }));
  });
  const labels = [...new Map(state.rules.map(rule => [rule.statusCode!, { id: rule.statusCode!, label: rule.label }])).values()];
  const sortingDisabled = !state.canSave || state.saving || state.loading;
  const disabled = sortingDisabled || activeId !== null;
  const activeRule = state.rules.find(rule => rule.id === activeId);
  const close = () => { if (state.dirty) setConfirm("close"); else { setAdding(false); props.onClose(); } };
  return <>
    <AppDrawer open={props.open} title="发票与支付状态规则设置" className="input-invoice-usage-rules-drawer" width="min(1480px, 100vw)"
      onClose={close} closeLabel="关闭支付状态规则抽屉" closeDisabled={state.saving || activeId !== null}
      footer={<><Button variant="secondary" onPress={close} isDisabled={state.saving || activeId !== null}>取消</Button>{state.canSave ? <><Button variant="secondary" onPress={state.restore} isDisabled={disabled || !state.dirty}>还原</Button>
        <Button variant="primary" onPress={() => void state.save()} isPending={state.saving} isDisabled={disabled || !state.dirty || state.invalid}>保存</Button></> : null}</>}>
      <div className="payment-rules-body">
        <div className="payment-rules-toolbar"><span>{state.rules.length} 条规则{state.dirty ? " · 未保存" : ""}</span><span className="payment-rules-order-hint">同组内从上到下匹配，采用第一条满足条件的启用规则</span></div>
        {state.loading ? <div role="status">正在读取规则</div> : null}
        {state.error ? <div role="alert">{state.error}<Button size="sm" variant="ghost" onPress={() => state.dirty ? setConfirm("reload") : state.reload()}>重试读取</Button></div> : null}
        {state.feedback ? <div role="status">{state.feedback}</div> : null}
        {state.refreshError ? <div role="alert">{state.refreshError}<Button size="sm" variant="ghost" onPress={() => void state.refresh()}>重试刷新</Button></div> : null}
        {state.payload && !state.canSave ? <div role="status">只读</div> : null}
        {state.conditionErrors.map((error, index) => error ? <div role="alert" key={state.rules[index].id}>{state.rules[index].label || `规则 ${index + 1}`}：{error}</div> : null)}
        {state.payload ? <DndContext sensors={sensors} measuring={{ droppable: { strategy: MeasuringStrategy.Always } }} collisionDetection={args => args.pointerCoordinates ? pointerWithin(args) : closestCenter(args)}
          onDragStart={({ active }) => setActiveId(String(active.id))}
          onDragCancel={() => setActiveId(null)}
          onDragEnd={({ active, over }) => { setActiveId(null); if (over) state.reorder(String(active.id), String(over.id)); }}
          accessibility={{ screenReaderInstructions: { draggable: "按空格拿起规则，上下箭头调整组内顺序，再按空格放下，按 Escape 取消。" }, announcements: {
            onDragStart: ({ active }) => `已拿起规则 ${state.rules.find(rule => rule.id === active.id)?.label}，上下箭头调整顺序。`,
            onDragOver: ({ active, over }) => {
              if (!over) return "未选择放置位置。";
              const source = state.rules.find(rule => rule.id === active.id);
              const target = state.rules.find(rule => rule.id === over.id);
              if (source?.conditions?.hasBank !== target?.conditions?.hasBank) return "不能跨付款分组移动。";
              const position = state.rules.filter(rule => rule.conditions?.hasBank === target?.conditions?.hasBank).findIndex(rule => rule.id === over.id) + 1;
              return `将规则放到组内第 ${position} 条。`;
            },
            onDragEnd: ({ active, over }) => over && state.rules.find(rule => rule.id === active.id)?.conditions?.hasBank === state.rules.find(rule => rule.id === over.id)?.conditions?.hasBank ? "顺序已调整，保存后生效。" : "顺序未改变。",
            onDragCancel: () => "已取消移动，顺序未改变。",
          } }}>
          <Table className="finance-table payment-rules-grid">
            <Table.ScrollContainer className="finance-table__scroll">
              <table aria-label="支付状态规则" className="table__content finance-table__content" style={{ "--finance-table-min-width": "1100px" } as CSSProperties}>
                <thead className="table__header"><tr>{["付款状态", "顺序", "启用", "规则", "OA 申请人", "是否有流水", "发票 VS 流水", "发票净额（正数票+负数票）", "操作"].map(label => <th scope="col" data-column-role="description" className="table__column finance-table__column" key={label}>{label}</th>)}</tr></thead>
                <tbody className="table__body">
                  {groupedRules.length === 0 ? <tr><td colSpan={9}>暂无规则</td></tr> : null}
                  {[true, false].map(hasBank => <SortableContext key={String(hasBank)} items={groupedRules.filter(item => item.hasBank === hasBank).map(item => item.rule.id!)} strategy={verticalListSortingStrategy}>
                  {groupedRules.filter(item => item.hasBank === hasBank).map(({ rule, index, groupIndex, groupCount }) => {
                    const name = rule.label || `规则 ${index + 1}`;
                    const conditions = rule.conditions ?? {};
                    const names = Array.isArray(conditions.applicantNames) ? conditions.applicantNames as string[] : [];
                    const oaMode = conditions.hasOa === false ? "none" : Array.isArray(conditions.applicantNames) ? "named" : conditions.hasOa === true ? "anyOa" : "any";
                    return <SortablePaymentRuleRow key={rule.id} id={rule.id!} name={name} order={groupIndex + 1} disabled={sortingDisabled}>{handle => <>
                      <RuleCell columnRole="status" className={`payment-rule-group payment-rule-group--${hasBank ? "paid" : "unpaid"}${groupIndex === groupCount - 1 ? " payment-rule-group--last" : ""}`}>
                        {groupIndex === 0 ? <div className="payment-rule-group-label" style={{ "--group-rows": groupCount } as CSSProperties}><strong>{hasBank ? "已付款" : "未付款"}</strong><span>{groupCount} 条规则</span></div> : null}
                      </RuleCell>
                      <RuleCell columnRole="action">{handle}</RuleCell>
                      <RuleCell columnRole="selection"><Checkbox aria-label={`启用规则 ${name}`} isSelected={rule.enabled !== false} isDisabled={disabled} onChange={enabled => state.update(index, { enabled })}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control></Checkbox></RuleCell>
                      <RuleCell columnRole="description"><TextField aria-label={`标签 ${index + 1}`} isDisabled={disabled}><Input aria-label={`标签 ${index + 1}`} value={rule.label} onChange={event => state.setRules(current => current.map(item => item.statusCode === rule.statusCode ? { ...item, label: event.target.value } : item))} /></TextField></RuleCell>
                      <RuleCell columnRole="description"><PaymentRuleApplicantSelect label={`${name} OA 申请人条件`} options={state.payload!.applicantOptions} names={names} mode={oaMode} disabled={disabled}
                        onModeChange={mode => state.condition(index, { hasOa: mode === "any" ? undefined : mode !== "none", applicantNames: mode === "named" ? names : undefined })}
                        onChange={value => state.condition(index, { applicantNames: value, hasOa: true })} /></RuleCell>
                      <RuleCell columnRole="description"><RuleSelect label={`${name} 流水条件`} disabled={disabled} value={String(conditions.hasBank)} options={booleanOptions} onChange={value => state.condition(index, { hasBank: value === "true", ...(value === "false" ? { paymentComparison: undefined } : {}) })} /></RuleCell>
                      <RuleCell columnRole="description">{conditions.hasBank === false ? <span className="payment-rule-unavailable" aria-label={`${name} 金额比较不可用`}>—</span> : <RuleSelect label={`${name} 金额比较条件`} disabled={disabled} value={String(conditions.paymentComparison ?? "any")} options={[{ id: "any", label: "不限" }, { id: "equal", label: "＝" }, { id: "less", label: "＜" }, { id: "less_equal", label: "≤" }, { id: "greater", label: "＞" }, { id: "greater_equal", label: "≥" }]} onChange={value => state.condition(index, { paymentComparison: value === "any" ? undefined : value as PaymentComparisonOperator })} />}</RuleCell>
                      <RuleCell columnRole="description"><RuleSelect label={`${name} 发票净额条件`} disabled={disabled} value={String(conditions.invoiceNetSign ?? "any")} options={[{ id: "any", label: "不限" }, { id: "negative", label: "＜0" }, { id: "nonpositive", label: "≤0" }, { id: "zero", label: "＝0" }, { id: "nonnegative", label: "≥0" }, { id: "positive", label: "＞0" }]} onChange={value => state.condition(index, { invoiceNetSign: value === "any" ? undefined : value as InvoiceNetSignOperator })} /></RuleCell>
                      <RuleCell columnRole="description"><div className="payment-rules-row-actions"><Button aria-label={`删除规则 ${name}`} variant="ghost" size="sm" isDisabled={disabled} onPress={() => state.setRules(current => current.filter((_, i) => i !== index))}>删除</Button></div></RuleCell>
                    </>}</SortablePaymentRuleRow>;
                  })}</SortableContext>)}
                </tbody>
              </table>
            </Table.ScrollContainer>
            <Table.Footer className="finance-table__footer">{state.canSave ? adding ?
              <div role="group" aria-label="新增规则" className="payment-rule-add-form">
                <RuleSelect label="新增规则付款状态" value={newGroup} disabled={disabled} options={[{ id: "true", label: "已付款" }, { id: "false", label: "未付款" }]} onChange={setNewGroup} />
                <RuleSelect label="新增规则标签" value={newLabel} disabled={disabled} options={[{ id: "new", label: "新标签" }, ...labels]} onChange={setNewLabel} />
                <Button size="sm" variant="primary" isDisabled={disabled} onPress={() => { state.add(newGroup === "true", newLabel === "new" ? undefined : newLabel); setAdding(false); setNewLabel("new"); }}>添加</Button>
                <Button size="sm" variant="ghost" isDisabled={disabled} onPress={() => setAdding(false)}>取消新增</Button>
              </div> : <Button variant="ghost" aria-label="新增规则" className="payment-rules-add" isDisabled={disabled} onPress={() => setAdding(true)}>＋ 新增规则</Button> : null}</Table.Footer>
          </Table>
          <DragOverlay dropAnimation={null}>{activeRule ? <div className="payment-rule-drag-preview">{activeRule.label}</div> : null}</DragOverlay>
        </DndContext> : null}
      </div>
    </AppDrawer>
    <AppDialog open={confirm !== null} title="放弃未保存的规则？" onClose={() => setConfirm(null)} actions={<><Button variant="secondary" onPress={() => setConfirm(null)}>继续编辑</Button><Button variant="danger" onPress={() => { const action = confirm; setConfirm(null); if (action === "reload") state.reload(); else { setAdding(false); props.onClose(); } }}>放弃修改</Button></>} />
  </>;
}
