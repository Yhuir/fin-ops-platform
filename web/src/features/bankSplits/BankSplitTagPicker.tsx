import { ListBox, Popover } from '@heroui/react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { BankSplitDetail, BankSplitTag } from './api';

type Selection = { category_code: string; category_label_path: string[] };
type Props = {
  value: Selection;
  tags: BankSplitTag[];
  familyOptions: BankSplitDetail['turnover_third_label_options'];
  label: string;
  disabled: boolean;
  onChange: (selection: Selection) => void;
};

export default function BankSplitTagPicker({ value, tags, familyOptions, label, disabled, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [prefix, setPrefix] = useState<string[]>([]);
  const choices = useMemo(() => tags.flatMap(tag => tag.turnover_role === 'external_turnover'
    ? familyOptions.map(option => ({ category_code: tag.code, category_label_path: [...tag.path.slice(0, 2), option.value] }))
    : [{ category_code: tag.code, category_label_path: tag.path }]), [tags, familyOptions]);
  const branches = choices.filter(choice => !prefix.length || choice.category_label_path[0] === prefix[0]);
  const depth = Math.max(1, ...branches.map(choice => choice.category_label_path.length));
  const changeOpen = (next: boolean) => {
    if (disabled) return;
    if (next) setPrefix(value.category_label_path);
    setOpen(next);
  };
  return <Popover isOpen={open} onOpenChange={changeOpen}>
    <Popover.Trigger className="bank-split-tag-picker" role="combobox" aria-label={label} aria-haspopup="dialog"
      aria-expanded={open} aria-disabled={disabled} tabIndex={disabled ? -1 : 0}
      onKeyDown={event => { if (!disabled && event.key === 'ArrowDown') { event.preventDefault(); changeOpen(true); } }}>
      <span>{value.category_label_path.length ? value.category_label_path.join(' / ') : '选择标签'}</span><ChevronDown size={14} />
    </Popover.Trigger>
    <Popover.Content className="bank-split-tag-popover" placement="bottom end" offset={4}>
      <Popover.Dialog aria-label={label}>
        {open ? <div className="bank-split-tag-columns" style={{ gridTemplateColumns: `repeat(${depth}, minmax(0, 1fr))` }}
          onKeyDownCapture={event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setOpen(false); } }}>
          {Array.from({ length: depth }, (_, level) => {
            const candidates = choices.filter(choice => prefix.length >= level && prefix.slice(0, level).every((part, index) => choice.category_label_path[index] === part));
            const options = [...new Set(candidates.map(choice => choice.category_label_path[level]).filter(Boolean))];
            const columnLabel = ['主标签', '子标签', '往来归属'][level];
            return <ListBox key={level} aria-label={columnLabel} selectionMode="single" selectedKeys={prefix[level] ? [prefix[level]] : []}
              onSelectionChange={keys => {
                if (keys === 'all') return;
                // Clicking the selected option completes it again, rather than clearing the saved classification.
                const path = keys.size ? [...prefix.slice(0, level), String([...keys][0])] : prefix.slice(0, level + 1);
                setPrefix(path);
                const matches = candidates.filter(choice => choice.category_label_path[level] === path[level]);
                if (matches.length === 1 && matches[0].category_label_path.length === path.length) {
                  onChange(matches[0]); setOpen(false);
                }
              }}>
              {options.map(option => <ListBox.Item id={option} key={option} textValue={option} className="bank-split-tag-option">
                <span>{option}</span>{candidates.some(choice => choice.category_label_path[level] === option && choice.category_label_path.length > level + 1) ? <ChevronRight size={14} /> : null}
              </ListBox.Item>)}
            </ListBox>;
          })}
          {!choices.length ? <p role="status">暂无可选标签</p> : null}
        </div> : null}
      </Popover.Dialog>
    </Popover.Content>
  </Popover>;
}
