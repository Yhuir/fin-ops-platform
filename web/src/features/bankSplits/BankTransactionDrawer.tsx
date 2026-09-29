import { useEffect, useState } from 'react';
import AppDrawer from '../../components/common/AppDrawer';
import { preparePublicDetailSections, type EntityDetailSection } from '../../components/common/EntityDetailContent';
import { apiRequestJson } from '../apiClient';
import BankTransactionDetailContent from './BankTransactionDetailContent';
import { useBankSplitClose } from './useBankSplitClose';

type SourceDetail = { detail_available: boolean; unavailable_reason?: string; sections: EntityDetailSection[] };
type Props = { transactionId: string | null; onClose: () => void; onSaved?: () => void | Promise<void> };

export default function BankTransactionDrawer({ transactionId, onClose, onSaved }: Props) {
  const { close, setDirty } = useBankSplitClose(onClose);
  const [result, setResult] = useState<{ id: string; detail?: SourceDetail; error?: string } | null>(null);

  useEffect(() => {
    if (!transactionId) {
      setResult(null);
      return;
    }
    const controller = new AbortController();
    setResult(null);
    apiRequestJson<SourceDetail>(`/api/bank-transactions/${encodeURIComponent(transactionId)}/source-detail`,
      { method: 'GET', signal: controller.signal }, { allowHtmlFallback: false })
      .then(detail => {
        if (!controller.signal.aborted) setResult({ id: transactionId, detail });
      })
      .catch(reason => {
        if (!controller.signal.aborted) setResult({ id: transactionId, error: reason instanceof Error ? reason.message : '流水来源详情加载失败' });
      });
    return () => controller.abort();
  }, [transactionId]);

  const current = result?.id === transactionId ? result : null;
  return <AppDrawer className="source-detail-drawer" open={Boolean(transactionId)} title="银行流水详情" width="min(800px, 100vw)" onClose={close}>
    {transactionId ? <BankTransactionDetailContent key={transactionId} bankTransactionId={transactionId}
      sections={current?.detail ? preparePublicDetailSections(current.detail.sections) : []}
      loading={!current} error={current?.error} detailAvailable={current?.detail?.detail_available}
      unavailableReason={current?.detail?.unavailable_reason}
      onBankSplitSaved={onSaved} onSplitDirtyChange={setDirty} /> : null}
  </AppDrawer>;
}
