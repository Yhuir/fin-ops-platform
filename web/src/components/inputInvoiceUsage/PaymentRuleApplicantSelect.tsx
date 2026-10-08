import { Autocomplete, Button, ListBox, SearchField, Select } from "@heroui/react";
import type { PaymentRuleApplicantOption } from "../../features/inputInvoiceUsage/types";

export default function PaymentRuleApplicantSelect({ label, options, names, onChange }: {
  label: string;
  options: PaymentRuleApplicantOption[];
  names: string[];
  onChange: (names: string[]) => void;
}) {
  const selectedIds = options.filter((option) => names.includes(option.matchName)).map((option) => option.userId);
  const directoryNames = new Set(options.map((option) => option.matchName));
  const missingNames = names.filter((name) => !directoryNames.has(name));
  return <>
    <Select selectionMode="multiple" aria-label={label} placeholder="选择申请人" value={selectedIds}
      onChange={(keys) => {
        const nextIds = new Set(keys.map(String));
        const nextNames = new Set(names);
        // Account selection changes the shared name condition, including keyboard bulk selection.
        for (const option of options) {
          if (nextIds.has(option.userId) === selectedIds.includes(option.userId)) continue;
          if (nextIds.has(option.userId)) nextNames.add(option.matchName);
          else nextNames.delete(option.matchName);
        }
        onChange([...nextNames]);
      }}>
      <Select.Trigger><Select.Value>{names.length ? names.join("、") : "选择申请人"}</Select.Value><Select.Indicator /></Select.Trigger>
      <Select.Popover className="payment-rule-applicants-popover">
        <Autocomplete.Filter filter={(text, input) => text.toLocaleLowerCase().includes(input.trim().toLocaleLowerCase())}>
          <SearchField aria-label="搜索申请人姓名或账号" className="payment-rule-applicants-search">
            <SearchField.Group><SearchField.SearchIcon /><SearchField.Input placeholder="搜索姓名或账号" /><SearchField.ClearButton /></SearchField.Group>
          </SearchField>
          <ListBox aria-label="OA 申请人账号" className="payment-rule-applicants-list" renderEmptyState={() => "没有匹配的用户"}>
            {options.map((option) => <ListBox.Item key={option.userId} id={option.userId}
              textValue={`${option.name} ${option.account} ${option.matchName}`} aria-label={`${option.name} ${option.account}`}>
              <span className="payment-rule-applicant-identity" title={`${option.name} ${option.account}`}>
                <span>{option.name}</span><small>{option.account}</small>
              </span>
              <span className="payment-rule-applicant-status" data-enabled={option.enabled} role="img"
                aria-label={option.enabled ? "账号已启用" : "账号已停用"} title={option.enabled ? "账号已启用" : "账号已停用"} />
              <ListBox.ItemIndicator />
            </ListBox.Item>)}
          </ListBox>
        </Autocomplete.Filter>
      </Select.Popover>
    </Select>
    {missingNames.map((name) => <span key={name} className="input-invoice-usage-payment-rule-applicant-hint">{name}（不在 OA 目录）<Button size="sm" variant="ghost" onPress={() => onChange(names.filter((item) => item !== name))}>移除</Button></span>)}
  </>;
}
