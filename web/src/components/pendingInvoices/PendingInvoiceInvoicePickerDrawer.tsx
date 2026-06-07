import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import type {
  AttachExistingInvoicePreview,
  AttachExistingInvoiceResult,
  FetchPendingInvoiceCandidatesRequest,
  PendingInvoiceCandidate,
  PendingInvoiceCandidatesResponse,
} from "../../features/pendingInvoices/types";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceInvoicePickerDrawerProps = {
  open: boolean;
  transactionId: string | null;
  loadCandidates: (request: FetchPendingInvoiceCandidatesRequest) => Promise<PendingInvoiceCandidatesResponse>;
  previewAttach: (transactionId: string, invoiceId: string, requestId: string) => Promise<AttachExistingInvoicePreview>;
  confirmAttach: (transactionId: string, invoiceId: string, previewId: string, requestId: string) => Promise<AttachExistingInvoiceResult>;
  onConfirmed: (result: AttachExistingInvoiceResult) => void;
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

export default function PendingInvoiceInvoicePickerDrawer({
  open,
  transactionId,
  loadCandidates,
  previewAttach,
  confirmAttach,
  onConfirmed,
  onClose,
}: PendingInvoiceInvoicePickerDrawerProps) {
  const [payload, setPayload] = useState<PendingInvoiceCandidatesResponse | null>(null);
  const [selected, setSelected] = useState<PendingInvoiceCandidate | null>(null);
  const [preview, setPreview] = useState<AttachExistingInvoicePreview | null>(null);
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

  const reloadCandidates = useCallback((guard: { active: boolean } = { active: true }) => {
    if (!transactionId) {
      return;
    }
    setLoading(true);
    setError(null);
    setPayload(null);
    setPreview(null);
    loadCandidates({
      transactionId,
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
  }, [amountMax, amountMin, issueDateFrom, issueDateTo, keyword, loadCandidates, page, pageSize, sellerName, transactionId]);

  useEffect(() => {
    if (!open || !transactionId) {
      setPayload(null);
      setSelected(null);
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
  }, [open, reloadCandidates, transactionId]);

  async function handlePreview(candidate: PendingInvoiceCandidate) {
    if (!transactionId || busy) {
      return;
    }
    setSelected(candidate);
    setBusy(true);
    setError(null);
    try {
      setPreview(await previewAttach(transactionId, candidate.invoiceId, createRequestId("attach-preview")));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "关联预览失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!transactionId || !selected || !preview || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await confirmAttach(transactionId, selected.invoiceId, preview.previewId, confirmRequestId);
      onConfirmed(result);
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

  return (
    <PendingInvoiceDrawerFrame
      closeLabel="关闭发票选择抽屉"
      footer={(
        <div className="pending-invoice-drawer-actions">
          <button className="pending-invoices-button" disabled={busy} onClick={onClose} type="button">关闭</button>
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
      subtitle={transactionId ?? undefined}
      title="选择已有进项发票"
      width={820}
    >
      {loading ? <LoadingMessage label="正在加载发票候选" text="正在加载发票候选" /> : null}
      {error ? <StatusMessage tone="danger">{error}</StatusMessage> : null}
      {preview ? (
        <StatusMessage tone={preview.canConfirm ? "info" : "warning"}>
          <span>{preview.requestKey}</span>
          <span>关联后待付 {formatMoney(preview.paymentImpact.remainingAmountAfter)}</span>
        </StatusMessage>
      ) : null}
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
              <th scope="col">发票号码</th>
              <th scope="col">销方</th>
              <th className="pending-invoice-simple-table__amount" scope="col">价税合计</th>
              <th className="pending-invoice-simple-table__amount" scope="col">待支付</th>
              <th scope="col">状态</th>
              <th className="pending-invoice-simple-table__amount" scope="col">操作</th>
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
                <td className="pending-invoice-simple-table__amount">{formatMoney(candidate.remainingAmount)}</td>
                <td>
                  <span className="pending-invoice-table-stack">
                    <span className={`pending-invoice-status-tag pending-invoice-status-tag--${candidateStatusTone(candidate.candidateStatus)}`}>
                      {candidateStatusLabel(candidate.candidateStatus)}
                    </span>
                    {candidate.conflictReason ? <span>{candidate.conflictReason}</span> : null}
                  </span>
                </td>
                <td className="pending-invoice-simple-table__amount">
                  <button
                    aria-label={`预览关联 ${invoiceNumber(candidate)}`}
                    className="pending-invoices-button"
                    disabled={candidate.candidateStatus !== "available" || busy}
                    onClick={() => handlePreview(candidate)}
                    type="button"
                  >
                    预览关联
                  </button>
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
