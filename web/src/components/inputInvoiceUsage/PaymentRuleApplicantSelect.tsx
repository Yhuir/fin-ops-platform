import { Autocomplete, Button, ListBox, Popover, SearchField } from "@heroui/react";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import type { PaymentRuleApplicantOption } from "../../features/inputInvoiceUsage/types";

export type PaymentRuleOaMode = "any" | "none" | "anyOa" | "named";
const modes: { id: PaymentRuleOaMode; label: string }[] = [
  { id: "any", label: "不限" }, { id: "none", label: "无 OA" },
  { id: "anyOa", label: "任意申请人" }, { id: "named", label: "指定申请人" },
];

export default function PaymentRuleApplicantSelect({ label, options, names, mode, disabled, onModeChange, onChange }: {
  label: string; options: PaymentRuleApplicantOption[]; names: string[]; mode: PaymentRuleOaMode;
  disabled: boolean; onModeChange: (mode: PaymentRuleOaMode) => void; onChange: (names: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const selectedIds = options.filter(option => names.includes(option.matchName)).map(option => option.userId);
  const directoryNames = new Set(options.map(option => option.matchName));
  const missingNames = names.filter(name => !directoryNames.has(name));
  const summary = mode === "named" ? names.length ? `${names.slice(0, 2).join("、")}${names.length > 2 ? ` +${names.length - 2}` : ""}` : "选择申请人" : modes.find(item => item.id === mode)!.label;
  return <Popover isOpen={open} onOpenChange={next => { if (!disabled) setOpen(next); }}>
    <Popover.Trigger className="payment-rule-applicant-trigger" role="combobox" aria-label={label} aria-haspopup="dialog"
      aria-expanded={open} aria-disabled={disabled} tabIndex={disabled ? -1 : 0}>
      <span title={mode === "named" ? names.join("、") : summary}>{summary}</span><ChevronDown size={14} />
    </Popover.Trigger>
    <Popover.Content className="payment-rule-applicants-popover" placement="bottom start" offset={4}>
      <Popover.Dialog aria-label={`${label} 选择`}><div className="payment-rule-applicants-content" onKeyDownCapture={event => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setOpen(false); } }}>
        <ListBox aria-label="OA 匹配方式" selectionMode="single" selectedKeys={[mode]} onSelectionChange={keys => {
          if (keys === "all" || !keys.size) return;
          const next = [...keys][0] as PaymentRuleOaMode;
          onModeChange(next);
          if (next !== "named") setOpen(false);
        }}>
          {modes.map(item => <ListBox.Item id={item.id} key={item.id} textValue={item.label}>{item.label}<ListBox.ItemIndicator /></ListBox.Item>)}
        </ListBox>
        {mode === "named" ? <>
          <Autocomplete.Filter filter={(text, input) => text.toLocaleLowerCase().includes(input.trim().toLocaleLowerCase())}>
            <SearchField aria-label="搜索申请人姓名或账号" className="payment-rule-applicants-search">
              <SearchField.Group><SearchField.SearchIcon /><SearchField.Input placeholder="搜索姓名或账号" /><SearchField.ClearButton /></SearchField.Group>
            </SearchField>
            <ListBox aria-label="OA 申请人账号" selectionMode="multiple" selectionBehavior="toggle" selectedKeys={selectedIds}
              className="payment-rule-applicants-list" renderEmptyState={() => "没有匹配的用户"}
              onSelectionChange={keys => {
                const nextIds = new Set(keys === "all" ? options.map(option => option.userId) : [...keys].map(String));
                const nextNames = new Set(names);
                for (const option of options) {
                  if (nextIds.has(option.userId) === selectedIds.includes(option.userId)) continue;
                  if (nextIds.has(option.userId)) nextNames.add(option.matchName);
                  else nextNames.delete(option.matchName);
                }
                onChange([...nextNames]);
              }}>
              {options.map(option => <ListBox.Item key={option.userId} id={option.userId} textValue={`${option.name} ${option.account} ${option.matchName}`} aria-label={`${option.name} ${option.account}`}>
                <span className="payment-rule-applicant-identity" title={`${option.name} ${option.account}`}><span>{option.name}</span><small>{option.account}</small></span>
                <span className="payment-rule-applicant-status" data-enabled={option.enabled} role="img" aria-label={option.enabled ? "账号已启用" : "账号已停用"} />
                <ListBox.ItemIndicator />
              </ListBox.Item>)}
            </ListBox>
          </Autocomplete.Filter>
          {missingNames.map(name => <div key={name} className="payment-rule-missing-name"><span>{name}</span><Button size="sm" variant="ghost" aria-label={`移除申请人 ${name}`} onPress={() => onChange(names.filter(item => item !== name))}>移除</Button></div>)}
        </> : null}
      </div></Popover.Dialog>
    </Popover.Content>
  </Popover>;
}
