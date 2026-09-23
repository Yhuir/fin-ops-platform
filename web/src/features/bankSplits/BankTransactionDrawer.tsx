import AppDrawer from '../../components/common/AppDrawer';
import type { EntityDetailSection } from '../../components/common/EntityDetailContent';
import BankTransactionDetailContent from './BankTransactionDetailContent';
import { useBankSplitClose } from './useBankSplitClose';

type Props = { transactionId: string | null; sections: EntityDetailSection[]; onClose: () => void; onSaved?: () => void | Promise<void> };
export default function BankTransactionDrawer({ transactionId, sections, onClose, onSaved }: Props) {
  const { close, setDirty } = useBankSplitClose(onClose);
  return <AppDrawer open={Boolean(transactionId)} title="银行流水详情" width="min(800px, 100vw)" onClose={close}>
    {transactionId ? <BankTransactionDetailContent key={transactionId} bankTransactionId={transactionId} sections={sections} onBankSplitSaved={onSaved} onSplitDirtyChange={setDirty} /> : null}
  </AppDrawer>;
}
