import { useEffect, useRef, useState, type ComponentProps } from 'react';
import EntityDetailContent from '../../components/common/EntityDetailContent';
import BankSplitEditor from './BankSplitEditor';
import type { BankSplitDetail } from './api';

type Props = ComponentProps<typeof EntityDetailContent> & {
  bankTransactionId?: string;
  onBankSplitSaved?: (detail: BankSplitDetail) => void | Promise<void>;
  onSplitSavingChange?: (saving: boolean) => void;
  onSplitDirtyChange?: (dirty: boolean, source?: string) => void;
};
export default function BankTransactionDetailContent({ bankTransactionId, onBankSplitSaved, onSplitDirtyChange, onSplitSavingChange, ...props }: Props) {
  const dirtyIds = useRef(new Set<string>());
  const savingIds = useRef(new Set<string>());
  const changeDirty = (id: string, dirty: boolean) => {
    if (dirty) dirtyIds.current.add(id); else dirtyIds.current.delete(id);
    onSplitDirtyChange?.(dirty, id);
  };
  const changeSaving = (id: string, saving: boolean) => {
    if (saving) savingIds.current.add(id); else savingIds.current.delete(id);
    onSplitSavingChange?.(savingIds.current.size > 0);
  };
  const ids = props.sections.map((section, index) => section.bank_transaction_id ?? (index === 0 ? bankTransactionId : undefined));
  const operationIds = ids.map((id, index) => id && ids.lastIndexOf(id) === index ? id : undefined);
  return <><EntityDetailContent {...props} extraFields={(_section, index) => {
    const id = operationIds[index];
    return id ? [{ label: '流水操作', content: <SplitOperation key={id} transactionId={id}
      onSaved={onBankSplitSaved} onDirtyChange={dirty => changeDirty(id, dirty)} onSavingChange={saving => changeSaving(id, saving)} /> }] : [];
  }} />
    {!props.loading && !props.error && props.detailAvailable !== false && props.sections.length === 0 && bankTransactionId &&
      <div className="entity-detail-actions"><h4>流水操作</h4><SplitOperation transactionId={bankTransactionId}
        onSaved={onBankSplitSaved} onDirtyChange={dirty => changeDirty(bankTransactionId, dirty)} onSavingChange={saving => changeSaving(bankTransactionId, saving)} /></div>}
  </>;
}

function SplitOperation(props: ComponentProps<typeof BankSplitEditor>) {
  const latest = useRef(props);
  latest.current = props;
  useEffect(() => () => { latest.current.onDirtyChange?.(false); latest.current.onSavingChange?.(false); }, []);
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  return <div>
    <button type="button" className="entity-detail-operation" aria-expanded={open}
      onClick={() => { setMounted(true); setOpen(value => !value); }}>流水子项拆分</button>
    <div hidden={!open}>{mounted && <BankSplitEditor {...props} />}</div>
  </div>;
}
