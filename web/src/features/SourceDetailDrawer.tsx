import type { ComponentProps } from 'react';
import AppDrawer from '../components/common/AppDrawer';
import { preparePublicDetailSections, type EntityDetailSection } from '../components/common/EntityDetailContent';
import type { SourceDetailTarget } from './relations/types';
import BankTransactionDetailContent from './bankSplits/BankTransactionDetailContent';
import { useBankSplitClose } from './bankSplits/useBankSplitClose';

const titles = { oa: 'OA详情', bank: '银行流水详情', invoice: '发票详情' };
type Props = {
  open: boolean;
  target: SourceDetailTarget | null;
  sections: EntityDetailSection[];
  loading: boolean;
  error?: string | null;
  detailAvailable?: boolean;
  unavailableReason?: string;
  onClose: () => void;
  onBankSplitSaved?: ComponentProps<typeof BankTransactionDetailContent>['onBankSplitSaved'];
};

// Pages own source reads and permissions; the shared drawer owns only presentation and edit protection.
export default function SourceDetailDrawer({ open, target, sections, loading, error, detailAvailable,
  unavailableReason, onClose, onBankSplitSaved }: Props) {
  const { close, setDirty, setSaving } = useBankSplitClose(onClose);
  return <AppDrawer className="source-detail-drawer" closeLabel="关闭详情抽屉" open={open}
    title={target ? titles[target.kind] : '详情'} width="min(800px, 100vw)" onClose={close}>
    <BankTransactionDetailContent key={target ? `${target.kind}:${target.id}` : 'closed'}
      bankTransactionId={target?.kind === 'bank' ? target.id : undefined}
      sections={preparePublicDetailSections(sections)} loading={loading} error={error}
      detailAvailable={detailAvailable} unavailableReason={unavailableReason}
      onBankSplitSaved={onBankSplitSaved} onSplitDirtyChange={setDirty} onSplitSavingChange={setSaving} />
  </AppDrawer>;
}
