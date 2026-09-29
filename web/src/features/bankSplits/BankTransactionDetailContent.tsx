import { useState, type ComponentProps } from 'react';
import EntityDetailContent from '../../components/common/EntityDetailContent';
import BankSplitEditor from './BankSplitEditor';
import type { BankSplitDetail } from './api';

type Props = ComponentProps<typeof EntityDetailContent> & {
  bankTransactionId?: string;
  onBankSplitSaved?: (detail: BankSplitDetail) => void | Promise<void>;
  onSplitDirtyChange?: (dirty: boolean, source?: string) => void;
};
export default function BankTransactionDetailContent({ bankTransactionId, onBankSplitSaved, onSplitDirtyChange, ...props }: Props) {
  const ids = props.sections.map((section, index) => section.bank_transaction_id ?? (index === 0 ? bankTransactionId : undefined));
  const operationIds = ids.map((id, index) => id && ids.lastIndexOf(id) === index ? id : undefined);
  return <><EntityDetailContent {...props} extraFields={(_section, index) => {
    const id = operationIds[index];
    return id ? [{ label: '流水操作', content: <SplitOperation key={id} transactionId={id}
      onSaved={onBankSplitSaved} onDirtyChange={dirty => onSplitDirtyChange?.(dirty, id)} /> }] : [];
  }} />
    {!props.loading && !props.error && props.detailAvailable !== false && props.sections.length === 0 && bankTransactionId &&
      <div className="entity-detail-actions"><h4>流水操作</h4><SplitOperation transactionId={bankTransactionId}
        onSaved={onBankSplitSaved} onDirtyChange={dirty => onSplitDirtyChange?.(dirty, bankTransactionId)} /></div>}
  </>;
}

function SplitOperation(props: ComponentProps<typeof BankSplitEditor>) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  return <div>
    <button type="button" className="entity-detail-operation" aria-expanded={open}
      onClick={() => { setMounted(true); setOpen(value => !value); }}>流水子项拆分</button>
    <div hidden={!open}>{mounted && <BankSplitEditor {...props} />}</div>
  </div>;
}
