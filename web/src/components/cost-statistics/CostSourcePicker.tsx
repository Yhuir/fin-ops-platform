import { ListBox, Popover } from '@heroui/react';
import { ChevronDown } from 'lucide-react';
import { memo, useState } from 'react';
import { CostChips } from './CostSourceEvidence';

export type CostSourceOption = { id: string; label: string; date: string; amount: string; counterparty: string; tags: string[] };
export default memo(function CostSourcePicker({ value, options, label, focusKey, lineId, invalid, disabled, disabledReason, onChange }: {
  value: string; options: CostSourceOption[]; label: string; focusKey: string; lineId: number; invalid: boolean; disabled: boolean; disabledReason: (lineId: number, sourceId: string) => string; onChange: (lineId: number, sourceId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = options.find(option => option.id === value);
  return <Popover isOpen={open} onOpenChange={next => { if (!disabled) setOpen(next); }}>
    <Popover.Trigger className="cost-source-picker" role="combobox" tabIndex={disabled ? -1 : 0} onKeyDown={event => { if (!disabled && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) { event.preventDefault(); setOpen(true); } }} aria-label={label} aria-haspopup="listbox" aria-expanded={open} aria-invalid={invalid} data-focus-key={focusKey} aria-disabled={disabled}>
      <span>{selected ? `${selected.label} · ${selected.date.slice(0, 10)}` : '选择流水'}</span><ChevronDown size={14} />
    </Popover.Trigger>
    <Popover.Content className="cost-source-picker-popover" placement="bottom start" offset={4}>
      <Popover.Dialog aria-label={label}>
        {open ? <ListBox aria-label={label} selectionMode="single" selectedKeys={value ? [value] : []} disabledKeys={options.filter(option => disabledReason(lineId, option.id)).map(option => option.id)} onSelectionChange={keys => { if (keys === 'all') return; const key = [...keys][0]; if (key !== undefined) onChange(lineId, String(key)); setOpen(false); }}>
          {options.map(option => {
            const reason = disabledReason(lineId, option.id);
            return <ListBox.Item id={option.id} key={option.id} textValue={`${option.label} ${option.date} ${option.amount} ${option.counterparty} ${option.tags.join(' ')}`} className="cost-source-option">
              <div><strong>{option.label}</strong><span className="cost-source-money">¥{option.amount}</span></div>
              <span>{option.counterparty}</span><CostChips values={[option.date, ...option.tags]} />
              {reason && reason !== '已用完' ? <span className="cost-source-option-state">{reason}</span> : null}
            </ListBox.Item>;
          })}
        </ListBox> : null}
      </Popover.Dialog>
    </Popover.Content>
  </Popover>;
});
