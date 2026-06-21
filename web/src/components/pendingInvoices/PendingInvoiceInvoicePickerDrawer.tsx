import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import type {
  AttachExistingInvoicesPreview,
  AttachExistingInvoicesResult,
  FetchPendingInvoiceBatchCandidatesRequest,
  PendingInvoiceCandidate,
  PendingInvoiceCandidatesResponse,
} from "../../features/pendingInvoices/types";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceInvoicePickerDrawerProps = {
  open: boolean;
  transactionIds: string[];
  loadCandidates: (request: FetchPendingInvoiceBatchCandidatesRequest) => Promise<PendingInvoiceCandidatesResponse>;
  previewAttach: (transactionIds: string[], invoiceIds: string[], requestId: string) => Promise<AttachExistingInvoicesPreview>;
  confirmAttach: (transactionIds: string[], invoiceIds: string[], previewId: string, requestId: string) => Promise<AttachExistingInvoicesResult>;
  onConfirmed: (result: AttachExistingInvoicesResult) => void | Promise<void>;
  onClose: () => void;
};

function createRequestId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}:${crypto.randomUUID()}`;
  }
  return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}

function formatMoney(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : value || "-";
}

function numericMoney(value: string | null | undefined) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatMoneyNumber(value: number) {
  return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function invoiceNumber(candidate: PendingInvoiceCandidate) {
  return candidate.digitalInvoiceNo || candidate.invoiceNo || candidate.invoiceId || "-";
}

function candidateStatusLabel(status: PendingInvoiceCandidate["candidateStatus"]) {
  const labels: Record<string, string> = {
    available: "可关联",
    already_related: "已关联本流水",
    conflict: "存在冲突",
  };
  return labels[status] ?? status;
}

function candidateStatusTone(status: PendingInvoiceCandidate["candidateStatus"]) {
  if (status === "available") {
    return "success";
  }
  if (status === "conflict") {
    return "warning";
  }
  return "neutral";
}

function bankRelationStatusLabel(status: PendingInvoiceCandidate["bankRelationStatus"]) {
  const labels: Record<string, string> = {
    unlinked: "未关联流水",
    linked: "已关联流水",
    already_selected: "已关联本次流水",
    conflict: "流水关系冲突",
  };
  return labels[status] ?? status;
}

function bankRelationStatusTone(status: PendingInvoiceCandidate["bankRelationStatus"]) {
  if (status === "linked" || status === "already_selected") {
    return "success";
  }
  if (status === "conflict") {
    return "warning";
  }
  return "neutral";
}

function linkedBankTransactionText(candidate: PendingInvoiceCandidate) {
  if (candidate.linkedBankTransactionCount <= 0) {
    return "";
  }
  return `${candidate.linkedBankTransactionCount} 条已关联流水`;
}

export default function PendingInvoiceInvoicePickerDrawer({
  open,
  transactionIds,
  loadCandidates,
  previewAttach,
  confirmAttach,
  onConfirmed,
  onClose,
}: PendingInvoiceInvoicePickerDrawerProps) {
  const [payload, setPayload] = useState<PendingInvoiceCandidatesResponse | null>(null);
  const [selectedInvoiceIds, setSelectedInvoiceIds] = useState<Set<string>>(() => new Set());
  const [preview, setPreview] = useState<AttachExistingInvoicesPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [keyword, setKeyword] = useState("");
  const [sellerName, setSellerName] = useState("");
  const [issueDateFrom, setIssueDateFrom] = useState("");
  const [issueDateTo, setIssueDateTo] = useState("");
  const [amountMin, setAmountMin] = useState("");
  const [amountMax, setAmountMax] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const confirmRequestId = useMemo(() => createRequestId("attach-confirm"), [preview?.previewId]);
  const transactionIdsKey = transactionIds.join("\n");

  const reloadCandidates = useCallback((guard: { active: boolean } = { active: true }) => {
    if (transactionIds.length === 0) {
      return;
    }
    setLoading(true);
    setError(null);
    setPayload(null);
    setPreview(null);
    setSelectedInvoiceIds(new Set());
    loadCandidates({
      transactionIds,
      keyword,
      sellerName,
      issueDateFrom,
      issueDateTo,
      amountMin,
      amountMax,
      sortField: "amount_difference_abs",
      sortDirection: "asc",
      page,
      pageSize,
    })
      .then((nextPayload) => {
        if (guard.active) {
          setPayload(nextPayload);
        }
      })
      .catch((reason: unknown) => {
        if (guard.active) {
          setError(reason instanceof Error ? reason.message : "候选发票加载失败");
        }
      })
      .finally(() => {
        if (guard.active) {
          setLoading(false);
        }
      });
  }, [amountMax, amountMin, issueDateFrom, issueDateTo, keyword, loadCandidates, page, pageSize, sellerName, transactionIds, transactionIdsKey]);

  useEffect(() => {
    if (!open || transactionIds.length === 0) {
      setPayload(null);
      setSelectedInvoiceIds(new Set());
      setPreview(null);
      setLoading(false);
      setBusy(false);
      setError(null);
      setPage(1);
      return undefined;
    }
    const guard = { active: true };
    reloadCandidates(guard);
    return () => {
      guard.active = false;
    };
  }, [open, reloadCandidates, transactionIds.length, transactionIdsKey]);

  const selectedCandidates = useMemo(() => {
    const selected = selectedInvoiceIds;
    return (payload?.rows ?? []).filter((candidate) => selected.has(candidate.invoiceId));
  }, [payload?.rows, selectedInvoiceIds]);
  const selectedInvoiceTotal = useMemo(() => (
    selectedCandidates.reduce((totalAmount, candidate) => totalAmount + numericMoney(candidate.totalWithTax), 0)
  ), [selectedCandidates]);
  const selectedBankTotal = payload?.selectionSummary?.bankTotal || preview?.selectionSummary.bankTotal || "0.00";
  const selectedDifference = selectedInvoiceTotal - numericMoney(selectedBankTotal);
  const selectedInvoiceIdsForSubmit = selectedCandidates.map((candidate) => candidate.invoiceId);

  function toggleCandidate(candidate: PendingInvoiceCandidate) {
    if (candidate.candidateStatus !== "available" || busy) {
      return;
    }
    setPreview(null);
    setSelectedInvoiceIds((current) => {
      const next = new Set(current);
      if (next.has(candidate.invoiceId)) {
        next.delete(candidate.invoiceId);
      } else {
        next.add(candidate.invoiceId);
      }
      return next;
    });
  }

  async function handlePreview() {
    if (transactionIds.length === 0 || selectedInvoiceIdsForSubmit.length === 0 || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setPreview(await previewAttach(transactionIds, selectedInvoiceIdsForSubmit, createRequestId("attach-preview")));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "关联预览失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (transactionIds.length === 0 || selectedInvoiceIdsForSubmit.length === 0 || !preview || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await confirmAttach(transactionIds, selectedInvoiceIdsForSubmit, preview.previewId, confirmRequestId);
      await onConfirmed(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "关系确认失败");
    } finally {
      setBusy(false);
    }
  }

  const pagination = payload?.pagination;
  const total = pagination?.total ?? 0;
  const currentPage = pagination?.page ?? page;
  const currentPageSize = pagination?.pageSize ?? pageSize;
  const from = total === 0 ? 0 : (currentPage - 1) * currentPageSize + 1;
  const to = Math.min(total, currentPage * currentPageSize);
  const subtitle = transactionIds.length > 1 ? `已选 ${transactionIds.length} 条流水` : transactionIds[0];

  return (
    <PendingInvoiceDrawerFrame
      closeLabel="关闭发票选择抽屉"
      footer={(
        <div className="pending-invoice-drawer-actions">
          <button className="pending-invoices-button" disabled={busy} onClick={onClose} type="button">关闭</button>
          <button
            className="pending-invoices-button"
            disabled={selectedInvoiceIdsForSubmit.length === 0 || loading || busy}
            onClick={handlePreview}
            type="button"
          >
            预览关联
          </button>
          <button
            className="pending-invoices-button pending-invoices-button--primary"
            disabled={!preview?.canConfirm || busy}
            onClick={handleConfirm}
            type="button"
          >
            确认建立关系
          </button>
        </div>
      )}
      onClose={onClose}
      open={open}
      subtitle={subtitle}
      title="选择已有进项发票"
      width={900}
    >
      {loading ? <LoadingMessage label="正在加载发票候选" text="正在加载发票候选" /> : null}
      {error ? <StatusMessage tone="danger">{error}</StatusMessage> : null}
      {preview ? (
        <StatusMessage tone={preview.canConfirm ? "info" : "warning"}>
          <div className="pending-invoice-preview-message">
            <span>{preview.requestKey}</span>
            <span>关联后待付 {formatMoney(preview.paymentImpact.remainingAmountAfter)}</span>
            {preview.conflicts.length > 0 ? <PreviewIssueList title="不可确认原因" items={preview.conflicts} /> : null}
            {preview.warnings.length > 0 ? <PreviewIssueList title="提示" items={preview.warnings} /> : null}
          </div>
        </StatusMessage>
      ) : null}
      <section aria-label="选择汇总" className="pending-invoice-metric-grid pending-invoice-picker-summary">
        <Metric label="已选流水金额" value={formatMoney(selectedBankTotal)} />
        <Metric label="已选发票金额" value={formatMoneyNumber(selectedInvoiceTotal)} />
        <Metric label="本次选择差额" value={formatMoneyNumber(selectedDifference)} />
        {preview ? <Metric label="关联后待付" value={formatMoney(preview.paymentImpact.remainingAmountAfter)} /> : null}
      </section>
      <section className="pending-invoice-panel pending-invoice-filter-panel" aria-label="发票候选筛选">
        <Field label="关键词" value={keyword} onChange={(value) => { setKeyword(value); setPage(1); }} />
        <Field label="销方" value={sellerName} onChange={(value) => { setSellerName(value); setPage(1); }} />
        <Field label="开票开始" type="date" value={issueDateFrom} onChange={(value) => { setIssueDateFrom(value); setPage(1); }} />
        <Field label="开票结束" type="date" value={issueDateTo} onChange={(value) => { setIssueDateTo(value); setPage(1); }} />
        <Field inputMode="decimal" label="最小金额" value={amountMin} onChange={(value) => { setAmountMin(value); setPage(1); }} />
        <Field inputMode="decimal" label="最大金额" value={amountMax} onChange={(value) => { setAmountMax(value); setPage(1); }} />
        <button className="pending-invoices-button" disabled={loading || busy} onClick={() => reloadCandidates()} type="button">搜索</button>
      </section>
      <section className="pending-invoice-panel">
        <table aria-label="发票候选" className="pending-invoice-simple-table">
          <thead>
            <tr>
              <th scope="col">选择</th>
              <th scope="col">发票号码</th>
              <th scope="col">销方</th>
              <th className="pending-invoice-simple-table__amount" scope="col">价税合计</th>
              <th scope="col">流水关联</th>
              <th scope="col">状态</th>
            </tr>
          </thead>
          <tbody>
            {payload?.rows.length === 0 ? (
              <tr>
                <td colSpan={6}>暂无候选发票。</td>
              </tr>
            ) : null}
            {payload?.rows.map((candidate) => (
              <tr key={candidate.invoiceId || candidate.id}>
                <td>
                  <input
                    aria-label={`选择发票 ${invoiceNumber(candidate)}`}
                    checked={selectedInvoiceIds.has(candidate.invoiceId)}
                    className="pending-invoice-candidate-select"
                    disabled={candidate.candidateStatus !== "available" || busy}
                    onChange={() => toggleCandidate(candidate)}
                    type="checkbox"
                  />
                </td>
                <td>
                  <span className="pending-invoice-table-stack">
                    <strong>{invoiceNumber(candidate)}</strong>
                    <span>{candidate.issueDate || "-"}</span>
                  </span>
                </td>
                <td>
                  <span className="pending-invoice-table-stack">
                    <span>{candidate.sellerName || "-"}</span>
                    <span>{candidate.sellerTaxNo || "-"}</span>
                  </span>
                </td>
                <td className="pending-invoice-simple-table__amount">{formatMoney(candidate.totalWithTax)}</td>
                <td>
                  <span className="pending-invoice-table-stack">
                    <span className={`pending-invoice-status-tag pending-invoice-status-tag--${bankRelationStatusTone(candidate.bankRelationStatus)}`}>
                      {bankRelationStatusLabel(candidate.bankRelationStatus)}
                    </span>
                    {linkedBankTransactionText(candidate) ? <span>{linkedBankTransactionText(candidate)}</span> : null}
                  </span>
                </td>
                <td>
                  <span className="pending-invoice-table-stack">
                    <span className={`pending-invoice-status-tag pending-invoice-status-tag--${candidateStatusTone(candidate.candidateStatus)}`}>
                      {candidateStatusLabel(candidate.candidateStatus)}
                    </span>
                    {candidate.conflictReason ? <span>{candidate.conflictReason}</span> : null}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="pending-invoice-picker-pagination">
          <label>
            <span>每页发票</span>
            <select
              value={currentPageSize}
              onChange={(event) => {
                setPageSize(Number(event.target.value));
                setPage(1);
              }}
            >
              {[10, 20, 50].map((size) => <option key={size} value={size}>{size}</option>)}
            </select>
          </label>
          <span>{from}-{to} / {total}</span>
          <div className="pending-invoice-picker-pagination__actions">
            <button className="pending-invoices-button" disabled={currentPage <= 1 || loading || busy} onClick={() => setPage(currentPage - 1)} type="button">上一页</button>
            <button
              className="pending-invoices-button"
              disabled={to >= total || loading || busy}
              onClick={() => setPage(currentPage + 1)}
              type="button"
            >
              下一页
            </button>
          </div>
        </div>
      </section>
    </PendingInvoiceDrawerFrame>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="pending-invoice-metric">
      <span className="pending-invoice-metric__label">{label}</span>
      <strong className="pending-invoice-metric__value">{value}</strong>
    </div>
  );
}

function PreviewIssueList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="pending-invoice-preview-issues">
      <span>{title}</span>
      <ul>
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function Field({
  inputMode,
  label,
  type = "text",
  value,
  onChange,
}: {
  inputMode?: "decimal";
  label: string;
  type?: "date" | "text";
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="pending-invoice-form-field">
      <span>{label}</span>
      <input inputMode={inputMode} type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function LoadingMessage({ label, text }: { label: string; text: string }) {
  return (
    <div aria-label={label} className="pending-invoice-status-message" role="status">
      <span aria-hidden="true" className="pending-invoice-spinner" />
      <span>{text}</span>
    </div>
  );
}

function StatusMessage({ children, tone }: { children: ReactNode; tone: "danger" | "success" | "info" | "warning" }) {
  return (
    <div className={`pending-invoice-status-message pending-invoice-status-message--${tone}`} role={tone === "danger" ? "alert" : "status"}>
      {children}
    </div>
  );
}
