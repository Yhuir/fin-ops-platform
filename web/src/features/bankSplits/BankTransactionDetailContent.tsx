import { useEffect, useState, type ComponentProps } from 'react';
import EntityDetailContent from '../../components/common/EntityDetailContent';
import BankSplitEditor, { type BankSplitPartAction } from './BankSplitEditor';
import { getBankTransactionSplitsBatch, type BankSplitDetail } from './api';

type Props = ComponentProps<typeof EntityDetailContent> & {
  bankTransactionId?: string;
  onBankSplitSaved?: (detail: BankSplitDetail) => void | Promise<void>;
  renderPartAction?: BankSplitPartAction;
  onSplitDirtyChange?: (dirty: boolean, source?: string) => void;
};
export default function BankTransactionDetailContent({ bankTransactionId, onBankSplitSaved, onSplitDirtyChange, renderPartAction, ...props }: Props) {
  const ids = [...new Set(props.sections.flatMap((section, index) => {
    const id = section.bank_transaction_id ?? (index === 0 ? bankTransactionId : undefined);
    return id ? [id] : [];
  }))];
  const batchKey = ids.length > 1 && !props.loading && !props.error && props.detailAvailable !== false ? JSON.stringify(ids) : '';
  const [batch, setBatch] = useState<{ key: string; rows: BankSplitDetail[] } | null>(null);
  const [batchError, setBatchError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!batchKey) return;
    const controller = new AbortController();
    setBatchError('');
    getBankTransactionSplitsBatch(JSON.parse(batchKey) as string[], controller.signal).then(rows => {
      if (!controller.signal.aborted) setBatch({ key: batchKey, rows });
    }).catch(reason => {
      if (!controller.signal.aborted) setBatchError(reason instanceof Error ? reason.message : '读取拆分失败');
    });
    return () => controller.abort();
  }, [batchKey, reload]);
  return <EntityDetailContent {...props} extraFields={(section, index) => {
    const id = section.bank_transaction_id ?? (index === 0 ? bankTransactionId : undefined);
    if (!id) return [];
    const initialDetail = batchKey && batch?.key === batchKey ? batch.rows[ids.indexOf(id)] : undefined;
    return [{ label: '流水子项拆分', content: batchKey && !initialDetail
      ? batchError ? <div role="alert">{batchError}<button type="button" onClick={() => setReload(value => value + 1)}>重试</button></div> : <span role="status">正在读取拆分…</span>
      : <BankSplitEditor key={id} transactionId={id} initialDetail={initialDetail} onSaved={onBankSplitSaved} renderPartAction={renderPartAction} onDirtyChange={dirty => onSplitDirtyChange?.(dirty, id)} /> }];
  }} />;
}
