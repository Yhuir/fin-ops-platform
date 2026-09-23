import { useEffect, useRef, useState } from 'react';
import TwoColumnTagPicker from '../../components/common/TwoColumnTagPicker';
import { ApiClientError } from '../apiClient';
import { amountCents, centsText } from './amount';
import { fetchBankSplits, saveBankSplits, type BankSplitDetail } from './api';
import './bankSplits.css';

type DraftPart = { key: string; id?: string; category_code: string; amount: string };
type Props = { transactionId: string; initialDetail?: BankSplitDetail; onSaved?: () => void | Promise<void>; onDirtyChange?: (dirty: boolean) => void };
export default function BankSplitEditor({ transactionId, initialDetail, onSaved, onDirtyChange }: Props) {
  const [detail, setDetail] = useState<BankSplitDetail | null>(null);
  const [parts, setParts] = useState<DraftPart[]>([]);
  const [category, setCategory] = useState('');
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [conflict, setConflict] = useState(false);
  const [reload, setReload] = useState(0);
  const nextKey = useRef(0);
  const apply = (data: BankSplitDetail) => {
    setDetail(data); setParts(data.parts.map(part => ({ ...part, key: part.id })));
    setCategory(data.category_code ?? ''); setDirty(false); setConflict(false);
  };
  useEffect(() => {
    if (initialDetail && reload === 0) { apply(initialDetail); setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true); setError(''); setNotice(''); setDetail(null);
    fetchBankSplits(transactionId, controller.signal).then(data => {
      if (!controller.signal.aborted) apply(data);
    }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '读取拆分失败');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [transactionId, reload, initialDetail]);
  useEffect(() => { onDirtyChange?.(dirty || saving); }, [dirty, saving, onDirtyChange]);
  const changed = (next: DraftPart[]) => { setParts(next); setDirty(true); setNotice(''); setError(''); };
  const total = parts.reduce((sum, part) => sum + (amountCents(part.amount) ?? 0n), 0n);
  const parentAmount = detail ? amountCents(detail.amount) : null;
  const difference = parentAmount === null ? null : parentAmount - total;
  const disabled = saving || conflict || !detail?.can_edit;
  const tags = detail?.tag_definitions.filter(tag => tag.status === 'active') ?? [];
  const save = async () => {
    if (!detail || disabled) return;
    if (parts.length === 1) { setError('拆分至少需要两个子项'); return; }
    if (parts.some(part => !tags.some(tag => tag.code === part.category_code) || amountCents(part.amount) === null || amountCents(part.amount)! <= 0n)) {
      setError('请填写有效标签和大于零的两位小数金额'); return;
    }
    if (parts.length && difference !== 0n) { setError('子项合计必须等于流水金额'); return; }
    if (!parts.length && !tags.some(tag => tag.code === category)) { setError('请选择整笔流水标签'); return; }
    setSaving(true); setError(''); setNotice('');
    try {
      const response = await saveBankSplits(transactionId, {
        version: detail.version,
        parts: parts.map(part => ({ ...(part.id ? { id: part.id } : {}), category_code: part.category_code, amount: centsText(amountCents(part.amount)!) })),
        ...(!parts.length ? { category_code: category } : {}),
      });
      apply(response); setNotice('已保存');
      await onSaved?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存拆分失败');
      if (reason instanceof ApiClientError && reason.status === 409) setConflict(true);
    } finally { setSaving(false); }
  };
  if (loading) return <span role="status">正在读取拆分…</span>;
  if (!detail) return <div role="alert">{error}<button type="button" onClick={() => setReload(value => value + 1)}>重试</button></div>;
  return <div className="bank-split-editor">
    <div className="bank-split-toolbar"><button type="button" aria-label="新增流水子项" disabled={disabled} onClick={() => changed([...parts, { key: `new-${nextKey.current++}`, category_code: '', amount: '' }])}>＋</button></div>
    {parts.map((part, index) => <div className="bank-split-line" key={part.key}>
      <TwoColumnTagPicker value={part.category_code} savedLabel={tags.find(tag => tag.code === part.category_code)?.label ?? detail.parts.find(item => item.id === part.id)?.category_label ?? ''}
        tags={tags} loading={false} disabled={disabled} onLoad={() => undefined} label={`子项 ${index + 1} 标签`} placeholder="选择标签"
        onChange={tag => changed(parts.map(item => item.key === part.key ? { ...item, category_code: tag.code } : item))} />
      <input aria-label={`子项 ${index + 1} 金额`} inputMode="decimal" value={part.amount} disabled={disabled}
        onChange={event => changed(parts.map(item => item.key === part.key ? { ...item, amount: event.target.value } : item))} />
      <button type="button" aria-label={`删除子项 ${index + 1}`} disabled={disabled} onClick={() => changed(parts.filter(item => item.key !== part.key))}>删除</button>
    </div>)}
    {!parts.length && dirty ? <TwoColumnTagPicker value={category} savedLabel="" tags={tags} loading={false} disabled={disabled} onLoad={() => undefined}
      label="整笔流水标签" placeholder="选择整笔流水标签" onChange={tag => { setCategory(tag.code); setDirty(true); }} /> : null}
    {parts.length ? <div className="bank-split-total">合计 {centsText(total)}{difference !== null && difference !== 0n ? <span>差额 {centsText(difference)}</span> : null}</div> : null}
    {error ? <div role="alert">{error}</div> : null}
    {notice ? <div role="status">{notice}</div> : null}
    {conflict ? <button type="button" onClick={() => setReload(value => value + 1)}>重新读取</button> : null}
    {dirty ? <div className="bank-split-actions">
      <button type="button" disabled={saving} onClick={() => { apply(detail); setError(''); }}>取消</button>
      <button type="button" disabled={disabled} onClick={() => void save()}>{saving ? '保存中…' : '保存'}</button>
    </div> : null}
  </div>;
}
