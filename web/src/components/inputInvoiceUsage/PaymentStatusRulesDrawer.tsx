import { Accordion, Button, Checkbox, Input, ListBox, Select, TextField } from "@heroui/react";
import { useState } from "react";
import PaymentRuleApplicantSelect from "./PaymentRuleApplicantSelect";
import AppDrawer from "../common/AppDrawer";
import AppDialog from "../common/AppDialog";
import { FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTableRow } from "../common/FinanceTable";
import { usePaymentStatusRules, type PaymentStatusRulesPorts } from "../../features/inputInvoiceUsage/usePaymentStatusRules";
import type { InputInvoiceUsagePaymentStatusRule } from "../../features/inputInvoiceUsage/types";
import "./paymentStatusRules.css";
export type PaymentStatusRule = InputInvoiceUsagePaymentStatusRule;
export type { PaymentStatusRulesPayload } from "../../features/inputInvoiceUsage/usePaymentStatusRules";

const booleanOptions = [{ id: "any", label: "不限" }, { id: "true", label: "是" }, { id: "false", label: "否" }];
function RuleSelect({ label, value, options, disabled, onChange }: { label: string; value: string; options: { id: string; label: string }[]; disabled: boolean; onChange: (value: string) => void }) {
  return <Select aria-label={label} selectedKey={value} isDisabled={disabled} onSelectionChange={key => { if (key != null) onChange(String(key)); }}>
    <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox>
      {options.map(option => <ListBox.Item id={option.id} key={option.id} textValue={option.label}>{option.label}</ListBox.Item>)}
    </ListBox></Select.Popover>
  </Select>;
}
export default function PaymentStatusRulesDrawer(props: PaymentStatusRulesPorts & { onClose: () => void }) {
  const state = usePaymentStatusRules(props);
  const [confirm, setConfirm] = useState<"close" | "reload" | null>(null);
  const disabled = !state.canSave || state.saving || state.loading;
  const close = () => state.dirty ? setConfirm("close") : props.onClose();
  return <>
    <AppDrawer open={props.open} title="发票与支付状态规则设置" className="input-invoice-usage-rules-drawer" width="min(1480px, 100vw)"
      onClose={close} closeLabel="关闭支付状态规则抽屉" closeDisabled={state.saving}
      footer={<><Button variant="secondary" onPress={close} isDisabled={state.saving}>取消</Button>{state.canSave ? <><Button variant="secondary" onPress={state.restore} isDisabled={disabled || !state.dirty}>还原</Button>
        <Button variant="primary" onPress={() => void state.save()} isPending={state.saving} isDisabled={disabled || !state.dirty || state.invalid}>保存</Button></> : null}</>}>
      <div className="payment-rules-body">
        <div className="payment-rules-toolbar"><span>{state.rules.length} 条规则{state.dirty ? " · 未保存" : ""}</span>
          <div><Button variant="ghost" size="sm" isDisabled={state.loading || state.saving} onPress={() => state.dirty ? setConfirm("reload") : state.reload()}>重新加载</Button>
            {state.canSave ? <Button variant="secondary" size="sm" isDisabled={disabled} onPress={() => state.add()}>新增规则</Button> : null}</div></div>
        {state.loading ? <div role="status">正在读取规则</div> : null}
        {state.error ? <div role="alert">{state.error}</div> : null}
        {state.feedback ? <div role="status">{state.feedback}</div> : null}
        {state.refreshError ? <div role="alert">{state.refreshError}<Button size="sm" variant="ghost" onPress={() => void state.refresh()}>重试刷新</Button></div> : null}
        {state.payload && !state.canSave ? <div role="status">只读</div> : null}
        {state.payload ? <FinanceTable ariaLabel="支付状态规则" minWidth={1260}>
          <FinanceTableHeader>{["启用", "优先级", "标签", "OA 申请人", "流水", "发票净额", "发票付款比较", "更多条件", "操作"].map(label => <FinanceTableColumn columnRole="description" id={label} key={label} isRowHeader={label === "标签"}>{label}</FinanceTableColumn>)}</FinanceTableHeader>
          <FinanceTableBody renderEmptyState={() => "暂无规则"}>
            {state.rules.map((rule, index) => {
              const name = rule.label || `规则 ${index + 1}`;
              const conditions = rule.conditions ?? {};
              const names = Array.isArray(conditions.applicantNames) ? conditions.applicantNames as string[] : [];
              const oaMode = conditions.hasOa === false ? "none" : Array.isArray(conditions.applicantNames) ? "named" : conditions.hasOa === true ? "anyOa" : "any";
              return <FinanceTableRow key={rule.id}>
                <FinanceTableCell columnRole="description"><Checkbox aria-label={`启用规则 ${name}`} isSelected={rule.enabled !== false} isDisabled={disabled} onChange={enabled => state.update(index, { enabled })}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control></Checkbox></FinanceTableCell>
                <FinanceTableCell columnRole="description"><TextField aria-label={`${name} 优先级`} isDisabled={disabled}><Input aria-label={`${name} 优先级`} type="number" min={1} value={rule.priority} onChange={event => state.update(index, { priority: Number(event.target.value) })} /></TextField></FinanceTableCell>
                <FinanceTableCell columnRole="description"><TextField aria-label={`标签 ${index + 1}`} isDisabled={disabled}><Input aria-label={`标签 ${index + 1}`} value={rule.label} onChange={event => state.setRules(current => current.map(item => item.statusCode === rule.statusCode ? { ...item, label: event.target.value } : item))} /></TextField></FinanceTableCell>
                <FinanceTableCell columnRole="description"><div className="payment-rules-oa"><RuleSelect label={`${name} OA 条件`} value={oaMode} disabled={disabled}
                  options={[{ id: "any", label: "不限" }, { id: "none", label: "无 OA" }, { id: "anyOa", label: "有 OA · 任意申请人" }, { id: "named", label: "指定申请人" }]}
                  onChange={mode => state.condition(index, { hasOa: mode === "any" ? undefined : mode !== "none", applicantNames: mode === "named" ? names : undefined })} />
                  {oaMode === "named" ? disabled ? <span>{names.join("、")}</span> : <PaymentRuleApplicantSelect label={`${name} OA 申请人条件`} options={state.payload!.applicantOptions} names={names} onChange={value => state.condition(index, { applicantNames: value, hasOa: true })} /> : null}
                </div></FinanceTableCell>
                <FinanceTableCell columnRole="description"><RuleSelect label={`${name} 流水条件`} disabled={disabled} value={conditions.hasBank == null ? "any" : String(conditions.hasBank)} options={[{ id: "any", label: "不限" }, { id: "true", label: "有流水" }, { id: "false", label: "无流水" }]} onChange={value => state.condition(index, { hasBank: value === "any" ? undefined : value === "true" })} /></FinanceTableCell>
                <FinanceTableCell columnRole="description"><RuleSelect label={`${name} 发票净额条件`} disabled={disabled} value={String(conditions.invoiceNetSign ?? "any")} options={[{ id: "any", label: "不限" }, { id: "positive", label: "大于 0" }, { id: "zero", label: "等于 0" }, { id: "negative", label: "小于 0" }]} onChange={value => state.condition(index, { invoiceNetSign: value === "any" ? undefined : value })} /></FinanceTableCell>
                <FinanceTableCell columnRole="description"><RuleSelect label={`${name} 金额比较条件`} disabled={disabled || conditions.hasBank === false} value={String(conditions.paymentComparison ?? "any")} options={[{ id: "any", label: "不限" }, { id: "equal", label: "发票＝付款" }, { id: "less", label: "发票＜付款" }, { id: "greater", label: "发票＞付款" }]} onChange={value => state.condition(index, { paymentComparison: value === "any" ? undefined : value })} />{rule.label && state.conditionErrors[index] ? <span role="alert" className="payment-rules-condition-error">{state.conditionErrors[index]}</span> : null}</FinanceTableCell>
                <FinanceTableCell columnRole="description"><Accordion><Accordion.Item id={`more-${rule.id}`}><Accordion.Heading><Accordion.Trigger>更多条件<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel>
                  <span>完全匹配</span><RuleSelect label={`${name} 完全匹配条件`} disabled={disabled} value={conditions.fullyMatched == null ? "any" : String(conditions.fullyMatched)} options={booleanOptions} onChange={value => state.condition(index, { fullyMatched: value === "any" ? undefined : value === "true" })} />
                  <span>发票/OA 金额匹配</span><RuleSelect label={`${name} 发票/OA 金额条件`} disabled={disabled} value={conditions.invoiceOaAmountMatched == null ? "any" : String(conditions.invoiceOaAmountMatched)} options={booleanOptions} onChange={value => state.condition(index, { invoiceOaAmountMatched: value === "any" ? undefined : value === "true" })} />
                </Accordion.Panel></Accordion.Item></Accordion></FinanceTableCell>
                <FinanceTableCell columnRole="description"><div className="payment-rules-row-actions"><Button aria-label={`复制规则 ${name}`} variant="ghost" size="sm" isDisabled={disabled} onPress={() => state.add(rule)}>复制</Button><Button aria-label={`删除规则 ${name}`} variant="danger-soft" size="sm" isDisabled={disabled} onPress={() => state.setRules(current => current.filter((_, i) => i !== index))}>删除</Button></div></FinanceTableCell>
              </FinanceTableRow>;
            })}
          </FinanceTableBody>
        </FinanceTable> : null}
      </div>
    </AppDrawer>
    <AppDialog open={confirm !== null} title="放弃未保存的规则？" onClose={() => setConfirm(null)} actions={<><Button variant="secondary" onPress={() => setConfirm(null)}>继续编辑</Button><Button variant="danger" onPress={() => { const action = confirm; setConfirm(null); if (action === "reload") state.reload(); else props.onClose(); }}>放弃修改</Button></>} />
  </>;
}
