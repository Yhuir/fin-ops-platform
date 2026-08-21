import { Alert, Button, Checkbox } from "@heroui/react";
import { useEffect, useMemo, useRef, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import {
  assignWorkbenchInvoiceExpenseItems,
  resolveWorkbenchActionErrorMessage,
} from "../../features/workbench/api";
import type {
  WorkbenchInvoiceExpenseItemAssignmentTarget,
  WorkbenchInvoiceExpenseItemCandidate,
} from "../../features/workbench/types";

type WorkbenchInvoiceAssignmentDrawerProps = {
  open: boolean;
  target: WorkbenchInvoiceExpenseItemAssignmentTarget | null;
  disabled?: boolean;
  onClose: () => void;
  onCompleted: () => Promise<void> | void;
};

export default function WorkbenchInvoiceAssignmentDrawer({
  open,
  target,
  disabled = false,
  onClose,
  onCompleted,
}: WorkbenchInvoiceAssignmentDrawerProps) {
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set());
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [committedSignature, setCommittedSignature] = useState<string | null>(null);
  const idempotencyKeysBySignatureRef = useRef(new Map<string, string>());
  const candidateGroups = useMemo(() => groupCandidatesByOa(target?.candidates ?? []), [target?.candidates]);

  useEffect(() => {
    if (!open) {
      return;
    }
    setSelectedKeys(new Set());
    setErrorMessage(null);
    setSubmitting(false);
    setCommittedSignature(null);
    idempotencyKeysBySignatureRef.current.clear();
  }, [open, target?.idempotencyKey]);

  async function submit() {
    if (!target || disabled || submitting || selectedKeys.size === 0) {
      return;
    }
    const targets = normalizedSelectedTargets(target, selectedKeys);
    const signature = assignmentPayloadSignature(target, targets);
    let idempotencyKey = idempotencyKeysBySignatureRef.current.get(signature);
    if (!idempotencyKey) {
      idempotencyKey = idempotencyKeysBySignatureRef.current.size === 0
        ? target.idempotencyKey
        : crypto.randomUUID();
      idempotencyKeysBySignatureRef.current.set(signature, idempotencyKey);
    }
    setSubmitting(true);
    setErrorMessage(null);
    let postSucceeded = committedSignature === signature;
    try {
      if (!postSucceeded) {
        await assignWorkbenchInvoiceExpenseItems({
          caseId: target.caseId,
          invoiceRowId: target.invoiceRowId,
          targets,
          anomalyFingerprint: target.anomalyFingerprint,
          idempotencyKey,
        });
        postSucceeded = true;
        setCommittedSignature(signature);
      }
      await onCompleted();
      onClose();
    } catch (error) {
      setErrorMessage(resolveWorkbenchActionErrorMessage(
        error,
        postSucceeded
          ? "归属已保存，但刷新结果失败，请重试。"
          : "发票归属保存失败，请稍后重试。",
      ));
    } finally {
      setSubmitting(false);
    }
  }

  const selectedCount = selectedKeys.size;
  const hasCandidates = (target?.candidates.length ?? 0) > 0;
  const selectionLocked = committedSignature !== null;

  return (
    <AppDrawer
      ariaBusy={submitting}
      className="workbench-invoice-assignment-drawer"
      closeDisabled={submitting}
      closeLabel="关闭选择 OA 明细"
      footer={(
        <>
          <span className="workbench-invoice-assignment-drawer__footer-status">
            {selectionLocked
              ? "归属已保存，等待刷新"
              : selectedCount > 0 ? `已选 ${selectedCount} 项` : "尚未选择"}
          </span>
          <Button isDisabled={submitting} size="sm" variant="secondary" onPress={onClose}>
            取消
          </Button>
          <Button
            isDisabled={disabled || submitting || selectedCount === 0 || !hasCandidates}
            size="sm"
            variant="primary"
            onPress={() => { void submit(); }}
          >
            {submitting
              ? selectionLocked ? "正在刷新…" : "正在确认…"
              : selectionLocked ? "重试刷新结果" : "确认归属"}
          </Button>
        </>
      )}
      onClose={onClose}
      open={open}
      title="选择 OA 明细"
      width="min(640px, 100vw)"
    >
      {target ? (
        <div className="workbench-invoice-assignment-drawer__content">
          <section aria-label="待归属发票" className="workbench-invoice-assignment-drawer__invoice-summary">
            <div>
              <span>发票号码</span>
              <strong>{target.invoiceNo || "—"}</strong>
            </div>
            <div>
              <span>销方名称</span>
              <strong>{target.sellerName || "—"}</strong>
            </div>
            <div>
              <span>价税合计</span>
              <strong>{target.amount || "—"}</strong>
            </div>
          </section>

          <p className="workbench-invoice-assignment-drawer__guidance">
            请选择这张发票实际对应的 OA 付款明细。系统不会按金额自动推荐，可同时选择多个明细。
          </p>

          {errorMessage ? (
            <Alert className="workbench-invoice-assignment-drawer__alert" color="danger" role="alert">
              {errorMessage}
            </Alert>
          ) : null}

          {!hasCandidates ? (
            <Alert className="workbench-invoice-assignment-drawer__alert" color="warning" role="status">
              当前关联组没有可选的 OA 付款明细，请刷新后重试。
            </Alert>
          ) : (
            <div aria-label="OA 付款明细" className="workbench-invoice-assignment-drawer__groups">
              {candidateGroups.map((group) => (
                <section className="workbench-invoice-assignment-drawer__group" key={group.oaRowId}>
                  <header>
                    <strong>{group.oaLabel}</strong>
                    <span>{group.candidates.length} 项</span>
                  </header>
                  <div className="workbench-invoice-assignment-drawer__candidates">
                    {group.candidates.map((candidate) => {
                      const detailParts = [
                        candidate.expenseType,
                        candidate.feeContent,
                        candidate.feeDescription,
                      ]
                        .map((value) => value?.trim())
                        .filter((value): value is string => Boolean(value) && value !== "--" && value !== "—");
                      const rowIndex = candidate.rowIndex.trim();
                      if (rowIndex && rowIndex !== "--" && rowIndex !== "—") {
                        detailParts.push(`明细 ${rowIndex}`);
                      }
                      const detailLabel = Array.from(new Set(detailParts)).join(" · ") || "未提供费用说明";
                      const projectName = candidate.projectName.trim() || "未命名项目";
                      const amount = candidate.amount.trim() || "—";
                      return (
                        <Checkbox
                          aria-label={`${projectName}，${amount}，${detailLabel}`}
                          className="workbench-invoice-assignment-drawer__candidate"
                          isDisabled={disabled || submitting || selectionLocked}
                          isSelected={selectedKeys.has(candidate.key)}
                          key={candidate.key}
                          onChange={(selected) => {
                            setSelectedKeys((current) => {
                              const next = new Set(current);
                              if (selected) {
                                next.add(candidate.key);
                              } else {
                                next.delete(candidate.key);
                              }
                              return next;
                            });
                          }}
                        >
                          <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                          <span className="workbench-invoice-assignment-drawer__candidate-main">
                            <strong>{projectName}</strong>
                            <span>{detailLabel}</span>
                          </span>
                          <span className="workbench-invoice-assignment-drawer__candidate-amount">{amount}</span>
                        </Checkbox>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </AppDrawer>
  );
}

function groupCandidatesByOa(candidates: WorkbenchInvoiceExpenseItemCandidate[]) {
  const groups = new Map<string, {
    oaRowId: string;
    oaLabel: string;
    candidates: WorkbenchInvoiceExpenseItemCandidate[];
  }>();
  candidates.forEach((candidate) => {
    const group = groups.get(candidate.oaRowId) ?? {
      oaRowId: candidate.oaRowId,
      oaLabel: candidate.oaLabel,
      candidates: [],
    };
    group.candidates.push(candidate);
    groups.set(candidate.oaRowId, group);
  });
  return Array.from(groups.values());
}

function normalizedSelectedTargets(
  target: WorkbenchInvoiceExpenseItemAssignmentTarget,
  selectedKeys: Set<string>,
) {
  return target.candidates
    .filter((candidate) => selectedKeys.has(candidate.key))
    .map((candidate) => ({
      oaRowId: candidate.oaRowId,
      expenseItemId: candidate.expenseItemId,
    }))
    .sort((left, right) => (
      left.oaRowId.localeCompare(right.oaRowId)
      || left.expenseItemId.localeCompare(right.expenseItemId)
    ));
}

function assignmentPayloadSignature(
  target: WorkbenchInvoiceExpenseItemAssignmentTarget,
  targets: ReturnType<typeof normalizedSelectedTargets>,
) {
  return JSON.stringify({
    caseId: target.caseId,
    invoiceRowId: target.invoiceRowId,
    anomalyFingerprint: target.anomalyFingerprint,
    targets,
  });
}

export type { WorkbenchInvoiceAssignmentDrawerProps };
