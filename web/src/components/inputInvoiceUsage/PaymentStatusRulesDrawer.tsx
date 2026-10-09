import { Button, Input, ListBox, Select, TextField } from "@heroui/react";
import { useState } from "react";
import PaymentRuleApplicantSelect from "./PaymentRuleApplicantSelect";
import AppDrawer from "../common/AppDrawer";
import AppDialog from "../common/AppDialog";
import { FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTableRow } from "../common/FinanceTable";
import { usePaymentStatusRules, type PaymentStatusRulesPorts } from "../../features/inputInvoiceUsage/usePaymentStatusRules";
import type { InputInvoiceUsagePaymentStatusRule, InvoiceNetSignOperator, PaymentComparisonOperator } from "../../features/inputInvoiceUsage/types";
import "./paymentStatusRules.css";
export type PaymentStatusRule = InputInvoiceUsagePaymentStatusRule;
export type { PaymentStatusRulesPayload } from "../../features/inputInvoiceUsage/usePaymentStatusRules";

const booleanOptions = [{ id: "any", label: "不限" }, { id: "true", label: "✓" }, { id: "false", label: "✕" }];
function RuleSelect({ label, value, options, disabled, onChange }: { label: string; value: string; options: { id: string; label: string }[]; disabled: boolean; onChange: (value: string) => void }) {
  return <Select className="payment-rule-cell-select" aria-label={label} selectedKey={value} isDisabled={disabled} onSelectionChange={key => { if (key != null) onChange(String(key)); }}>
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
          <Button variant="ghost" size="sm" isDisabled={state.loading || state.saving} onPress={() => state.dirty ? setConfirm("reload") : state.reload()}>重新加载</Button></div>
        {state.loading ? <div role="status">正在读取规则</div> : null}
        {state.error ? <div role="alert">{state.error}</div> : null}
        {state.feedback ? <div role="status">{state.feedback}</div> : null}
        {state.refreshError ? <div role="alert">{state.refreshError}<Button size="sm" variant="ghost" onPress={() => void state.refresh()}>重试刷新</Button></div> : null}
        {state.payload && !state.canSave ? <div role="status">只读</div> : null}
        {state.conditionErrors.map((error, index) => error ? <div role="alert" key={state.rules[index].id}>{state.rules[index].label || `规则 ${index + 1}`}：{error}</div> : null)}
        {state.payload ? <FinanceTable ariaLabel="支付状态规则" minWidth={1360} className="payment-rules-grid"
          footer={state.canSave ? <Button className="payment-rules-add" aria-label="新增规则" variant="ghost" size="sm" isDisabled={disabled} onPress={() => state.add()}>＋</Button> : null}>
          <FinanceTableHeader>{["启用", "顺序", "规则", "OA 申请人", "流水", "发票与付款比较", "发票净额", "完全匹配", "发票/OA 金额匹配", "操作"].map(label => <FinanceTableColumn columnRole="description" id={label} key={label} isRowHeader={label === "规则"}>{label}</FinanceTableColumn>)}</FinanceTableHeader>
          <FinanceTableBody renderEmptyState={() => "暂无规则"}>
            {state.rules.map((rule, index) => {
              const name = rule.label || `规则 ${index + 1}`;
              const conditions = rule.conditions ?? {};
              const names = Array.isArray(conditions.applicantNames) ? conditions.applicantNames as string[] : [];
              const oaMode = conditions.hasOa === false ? "none" : Array.isArray(conditions.applicantNames) ? "named" : conditions.hasOa === true ? "anyOa" : "any";
              return <FinanceTableRow key={rule.id}>
                <FinanceTableCell columnRole="description"><RuleSelect label={`启用规则 ${name}`} value={String(rule.enabled !== false)} options={booleanOptions.slice(1)} disabled={disabled} onChange={value => state.update(index, { enabled: value === "true" })} /></FinanceTableCell>
                <FinanceTableCell columnRole="description"><div className="payment-rules-order"><span>{rule.priority}</span><Button size="sm" variant="ghost" isIconOnly aria-label={`上移规则 ${name}`} isDisabled={disabled || index === 0} onPress={() => state.move(index, -1)}>↑</Button><Button size="sm" variant="ghost" isIconOnly aria-label={`下移规则 ${name}`} isDisabled={disabled || index === state.rules.length - 1} onPress={() => state.move(index, 1)}>↓</Button></div></FinanceTableCell>
                <FinanceTableCell columnRole="description"><TextField aria-label={`标签 ${index + 1}`} isDisabled={disabled}><Input aria-label={`标签 ${index + 1}`} value={rule.label} onChange={event => state.setRules(current => current.map(item => item.statusCode === rule.statusCode ? { ...item, label: event.target.value } : item))} /></TextField></FinanceTableCell>
                <FinanceTableCell columnRole="description"><PaymentRuleApplicantSelect label={`${name} OA 申请人条件`} options={state.payload!.applicantOptions} names={names} mode={oaMode} disabled={disabled}
                  onModeChange={mode => state.condition(index, { hasOa: mode === "any" ? undefined : mode !== "none", applicantNames: mode === "named" ? names : undefined, ...(mode === "none" ? { invoiceOaAmountMatched: undefined } : {}) })}
                  onChange={value => state.condition(index, { applicantNames: value, hasOa: true })} /></FinanceTableCell>
                <FinanceTableCell columnRole="description"><RuleSelect label={`${name} 流水条件`} disabled={disabled} value={conditions.hasBank == null ? "any" : String(conditions.hasBank)} options={booleanOptions} onChange={value => state.condition(index, { hasBank: value === "any" ? undefined : value === "true", ...(value === "false" ? { paymentComparison: undefined } : {}) })} /></FinanceTableCell>
                <FinanceTableCell columnRole="description">{conditions.hasBank === false ? <span className="payment-rule-unavailable" aria-label={`${name} 金额比较不可用`}>—</span> : <RuleSelect label={`${name} 金额比较条件`} disabled={disabled} value={String(conditions.paymentComparison ?? "any")} options={[{ id: "any", label: "不限" }, { id: "equal", label: "＝" }, { id: "less", label: "＜" }, { id: "less_equal", label: "≤" }, { id: "greater", label: "＞" }, { id: "greater_equal", label: "≥" }]} onChange={value => state.condition(index, { paymentComparison: value === "any" ? undefined : value as PaymentComparisonOperator })} />}</FinanceTableCell>
                <FinanceTableCell columnRole="description"><RuleSelect label={`${name} 发票净额条件`} disabled={disabled} value={String(conditions.invoiceNetSign ?? "any")} options={[{ id: "any", label: "不限" }, { id: "negative", label: "＜0" }, { id: "nonpositive", label: "≤0" }, { id: "zero", label: "＝0" }, { id: "nonnegative", label: "≥0" }, { id: "positive", label: "＞0" }]} onChange={value => state.condition(index, { invoiceNetSign: value === "any" ? undefined : value as InvoiceNetSignOperator })} /></FinanceTableCell>
                <FinanceTableCell columnRole="description"><RuleSelect label={`${name} 完全匹配条件`} disabled={disabled} value={conditions.fullyMatched == null ? "any" : String(conditions.fullyMatched)} options={booleanOptions} onChange={value => state.condition(index, { fullyMatched: value === "any" ? undefined : value === "true" })} /></FinanceTableCell>
                <FinanceTableCell columnRole="description">{conditions.hasOa === false && conditions.invoiceOaAmountMatched == null ? <span className="payment-rule-unavailable" aria-label={`${name} OA 金额匹配不可用`}>—</span> : <RuleSelect label={`${name} 发票/OA 金额条件`} disabled={disabled} value={conditions.invoiceOaAmountMatched == null ? "any" : String(conditions.invoiceOaAmountMatched)} options={booleanOptions} onChange={value => state.condition(index, { invoiceOaAmountMatched: value === "any" ? undefined : value === "true" })} />}</FinanceTableCell>
                <FinanceTableCell columnRole="description"><div className="payment-rules-row-actions"><Button aria-label={`复制规则 ${name}`} variant="ghost" size="sm" isDisabled={disabled} onPress={() => state.add(rule)}>复制</Button><Button aria-label={`删除规则 ${name}`} variant="ghost" size="sm" isDisabled={disabled} onPress={() => state.setRules(current => current.filter((_, i) => i !== index))}>删除</Button></div></FinanceTableCell>
              </FinanceTableRow>;
            })}
          </FinanceTableBody>
        </FinanceTable> : null}
      </div>
    </AppDrawer>
    <AppDialog open={confirm !== null} title="放弃未保存的规则？" onClose={() => setConfirm(null)} actions={<><Button variant="secondary" onPress={() => setConfirm(null)}>继续编辑</Button><Button variant="danger" onPress={() => { const action = confirm; setConfirm(null); if (action === "reload") state.reload(); else props.onClose(); }}>放弃修改</Button></>} />
  </>;
}
