import { Button } from "@heroui/react";
import { useEffect, useRef, useState } from "react";

import { fetchBankFlowRuleBatchDetail } from "../../features/bankFlowRuleBatches/api";
import type { BankFlowRuleBatchDetail } from "../../features/bankFlowRuleBatches/types";
import AppDrawer from "../common/AppDrawer";
import { FinanceTable, FinanceTableHeader, FinanceTableColumn, FinanceTableBody, FinanceTableRow, FinanceTableCell } from "../common/FinanceTable";

/** Reads the complete formal batch; only the parent owns mutation and the post-commit reread. */
export default function BankFlowBatchWithdrawPreview({ batchId, onClose, onSubmit }: {
  batchId: string;
  onClose: () => void;
  onSubmit: (expectedVersion: number, onCommitted: () => void) => Promise<void>;
}) {
  const [detail, setDetail] = useState<BankFlowRuleBatchDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [completed, setCompleted] = useState(false);
  const submitting = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    setDetail(null);
    setError(null);
    void fetchBankFlowRuleBatchDetail(batchId, undefined, "formal", controller.signal).then(result => {
      if (controller.signal.aborted) return;
      if (result.batch.batchId !== batchId || result.batch.version === null
          || !result.batch.canWithdraw || result.batch.status !== "submitted" || result.rows.length === 0) {
        throw new Error("批次已变化或缺少正式成员，请关闭后刷新列表。");
      }
      setDetail(result);
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "读取批次失败。");
    });
    return () => controller.abort();
  }, [batchId]);

  const confirm = async () => {
    if (submitting.current || error || completed || detail?.batch.version == null) return;
    submitting.current = true;
    setBusy(true);
    let committed = false;
    try {
      await onSubmit(detail.batch.version, () => { committed = true; });
      setCompleted(true);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "撤回失败。";
      setError(committed ? `撤回已提交，页面重新读取失败，请勿重复提交。${message}` : `${message} 请关闭后重新预览。`);
    } finally {
      setBusy(false);
      submitting.current = false;
    }
  };

  return (
    <AppDrawer open title="撤回关联" closeLabel="关闭关联预览" width="min(1000px, 100vw)"
      onClose={onClose} closeDisabled={busy} ariaBusy={busy || (!detail && !error)}
      completion={completed ? "关联操作已完成" : undefined}
      footer={<Button variant="danger" size="sm" isPending={busy}
        isDisabled={!detail || Boolean(error) || busy || completed} onPress={confirm}>确认撤回</Button>}>
      {error ? <p role="alert">{error}</p> : null}
      {!detail && !error ? <p role="status">正在读取撤回范围…</p> : null}
      {busy ? <p role="status">正在撤回并重新读取关联台…</p> : null}
      {detail ? <>
        <h3>{detail.batch.batchLabel} · {detail.rows.length} 笔流水</h3>
        <p>批次：{detail.batch.batchId}；合计金额：{detail.batch.totalAmount}</p>
        <p>确认后撤回整个流水规则批次，下列流水恢复为可处理状态。若批次参与过后续合并，服务端按正式关系历史先撤回合并，再撤回原批次，保留其他恢复关系；原始流水不会删除。</p>
        <FinanceTable ariaLabel="待撤回批次流水" minWidth={650}>
          <FinanceTableHeader>
            <FinanceTableColumn id="date" columnRole="date">交易时间</FinanceTableColumn>
            <FinanceTableColumn id="counterparty" isRowHeader>对方户名</FinanceTableColumn>
            <FinanceTableColumn id="direction" columnRole="direction">收支</FinanceTableColumn>
            <FinanceTableColumn id="amount" columnRole="amount">金额</FinanceTableColumn>
            <FinanceTableColumn id="summary" columnRole="description">摘要</FinanceTableColumn>
          </FinanceTableHeader>
          <FinanceTableBody>{detail.rows.map(row => <FinanceTableRow key={row.transactionId} id={row.transactionId}>
            <FinanceTableCell columnRole="date">{row.tradeTime}</FinanceTableCell>
            <FinanceTableCell columnRole="identity">{row.counterpartyName}</FinanceTableCell>
            <FinanceTableCell columnRole="direction">{row.directionLabel}</FinanceTableCell>
            <FinanceTableCell columnRole="amount">{row.amount}</FinanceTableCell>
            <FinanceTableCell columnRole="description">{row.summary}</FinanceTableCell>
          </FinanceTableRow>)}</FinanceTableBody>
        </FinanceTable>
      </> : null}
    </AppDrawer>
  );
}
