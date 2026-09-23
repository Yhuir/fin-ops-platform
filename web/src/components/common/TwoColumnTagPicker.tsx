import { ListBox, Popover } from '@heroui/react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { memo, useMemo, useState } from 'react';
import './TwoColumnTagPicker.css';

export type TwoColumnTag = { code: string; label: string; primary_label: string; sub_label: string };
type Tag = TwoColumnTag;
type Props = { value: string; savedLabel: string; tags: Tag[]; loading: boolean; error?: string;
  label?: string; placeholder?: string;
  disabled: boolean; onLoad: () => void; lineId?: number; onChange: (tag: Tag, lineId?: number) => void };

export default memo(function TwoColumnTagPicker({ value, savedLabel, tags, loading, error, disabled, onLoad, onChange, label = '人工成本标签', placeholder = '选择成本标签', lineId }: Props) {
  const [open, setOpen] = useState(false);
  const [primary, setPrimary] = useState('');
  const selected = tags.find(tag => tag.code === value);
  const groups = useMemo(() => {
    const result = new Map<string, Tag[]>();
    for (const tag of tags) {
      const items = result.get(tag.primary_label) ?? [];
      items.push(tag); result.set(tag.primary_label, items);
    }
    return result;
  }, [tags]);
  const choose = (tag: Tag) => { onChange(tag, lineId); setOpen(false); };
  const changeOpen = (next: boolean) => {
    if (disabled) return;
    setOpen(next);
    if (next) { setPrimary(selected?.primary_label ?? ''); onLoad(); }
  };
  return <Popover isOpen={open} onOpenChange={changeOpen}>
    <Popover.Trigger className="two-column-tag-picker" role="combobox" aria-label={label} aria-haspopup="dialog" aria-expanded={open} aria-disabled={disabled} tabIndex={disabled ? -1 : 0}
      onKeyDown={event => { if (!disabled && event.key === 'ArrowDown') { event.preventDefault(); changeOpen(true); } }}>
      <span>{value ? `${savedLabel || selected?.label || ''}${!selected && !loading && !error ? '（已停用）' : ''}` : placeholder}</span><ChevronDown size={14} />
    </Popover.Trigger>
    <Popover.Content className="two-column-tag-popover" placement="bottom end" offset={4}>
      <Popover.Dialog aria-label={label}>
        {!open ? null : loading ? <p role="status">正在读取标签…</p> : error ? <div role="alert">{error}<button type="button" onClick={onLoad}>重试</button></div> : !tags.length ? <p>暂无可选标签</p> : <div className="two-column-tag-columns" onKeyDownCapture={event => {
          if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setOpen(false); }
        }}>
          <ListBox aria-label="主标签" selectionMode="single" selectedKeys={primary ? [primary] : []} onSelectionChange={keys => {
            if (keys === 'all' || !keys.size) return;
            const key = [...keys][0];
            const items = groups.get(String(key))!;
            if (items.length === 1 && !items[0].sub_label) choose(items[0]);
            else setPrimary(String(key));
          }}>
            {[...groups].map(([label, items]) => <ListBox.Item id={label} key={label} textValue={label} className="two-column-tag-option">
              <span>{label}</span>{items.some(item => item.sub_label) ? <ChevronRight size={14} /> : null}
            </ListBox.Item>)}
          </ListBox>
          {groups.has(primary) ? <ListBox key={primary} aria-label="子标签" selectionMode="single" selectedKeys={value ? [value] : []} onSelectionChange={keys => { if (keys === 'all' || !keys.size) return; choose(groups.get(primary)!.find(tag => tag.code === [...keys][0])!); }}>
            {groups.get(primary)!.map(tag => <ListBox.Item id={tag.code} key={tag.code} textValue={tag.sub_label || tag.primary_label} className="two-column-tag-option">{tag.sub_label || `${tag.primary_label}（主标签本身）`}</ListBox.Item>)}
          </ListBox> : <div className="two-column-tag-empty">选择主标签</div>}
        </div>}
      </Popover.Dialog>
    </Popover.Content>
  </Popover>;
});
