import { useEffect, useState } from 'react';
import SourceDetailDrawer from '../SourceDetailDrawer';
import { type EntityDetailSection } from '../../components/common/EntityDetailContent';
import { apiRequestJson } from '../apiClient';

type SourceDetail = { detail_available: boolean; unavailable_reason?: string; sections: EntityDetailSection[] };
type Props = { transactionId: string | null; onClose: () => void; onSaved?: () => void | Promise<void> };

export default function BankTransactionDrawer({ transactionId, onClose, onSaved }: Props) {
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
  return <SourceDetailDrawer open={Boolean(transactionId)} target={transactionId ? { kind: 'bank', id: transactionId } : null}
    sections={current?.detail?.sections ?? []} loading={Boolean(transactionId) && !current}
    error={current?.error} detailAvailable={current?.detail?.detail_available}
    unavailableReason={current?.detail?.unavailable_reason} onClose={onClose} onBankSplitSaved={onSaved} />;
}
