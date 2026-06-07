import { useEffect, useMemo, useState } from "react";

import type {
  OutputInvoiceCollectionRedRelationRequest,
  OutputInvoiceCollectionRow,
} from "../../features/outputInvoiceCollections/types";
import AppDrawer from "../common/AppDrawer";
import StatePanel from "../common/StatePanel";

type RedInvoiceRelationDrawerProps = {
  open: boolean;
  row: OutputInvoiceCollectionRow | null;
  candidateRows: OutputInvoiceCollectionRow[];
  onConfirm: (rowId: string, payload: OutputInvoiceCollectionRedRelationRequest) => Promise<void>;
  onRevoke: (relationId: string) => Promise<void>;
  onClose: () => void;
};

export default function RedInvoiceRelationDrawer({
  open,
  row,
  candidateRows,
  onConfirm,
  onRevoke,
  onClose,
}: RedInvoiceRelationDrawerProps) {
  const [search, setSearch] = useState("");
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [relationType, setRelationType] = useState<"red_invoice" | "blue_invoice">("red_invoice");
  const [evidence, setEvidence] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setSearch("");
    setSelectedCandidateId("");
    setRelationType("red_invoice");
    setEvidence("");
    setError(null);
  }, [open]);

  const candidates = useMemo(() => {
    const currentIdentity = new Set([row?.id, row?.invoiceId, row?.invoiceIdentityKey].filter(Boolean));
    const keyword = search.trim().toLowerCase();
    return candidateRows
      .filter((candidate) => !currentIdentity.has(candidate.id) && !currentIdentity.has(candidate.invoiceId) && !currentIdentity.has(candidate.invoiceIdentityKey))
      .filter((candidate) => {
        if (!keyword) {
          return true;
        }
        const searchable = [
          candidate.invoice.displayNo,
          candidate.invoice.invoiceNo,
          candidate.invoice.buyerName,
          candidate.invoice.totalWithTax,
          candidate.invoice.issueDate,
          candidate.invoiceId,
        ].join(" ").toLowerCase();
        return searchable.includes(keyword);
      })
      .slice(0, 20);
  }, [candidateRows, row, search]);

  const selectedCandidate = candidates.find((candidate) => candidate.id === selectedCandidateId)
    ?? candidateRows.find((candidate) => candidate.id === selectedCandidateId)
    ?? null;

  const handleSubmit = async () => {
    if (!row) {
      return;
    }
    if (!selectedCandidate) {
      setError("请选择关联发票");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm(row.id, {
        relatedInvoiceId: selectedCandidate.invoiceId,
        relatedInvoiceIdentityKey: selectedCandidate.invoiceIdentityKey || (selectedCandidate.invoiceId ? `id:${selectedCandidate.invoiceId}` : undefined),
        relationType,
        evidence,
        confidence: "manual_confirmed",
      });
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRevoke = async (relationId: string) => {
    setSubmitting(true);
    setError(null);
    try {
      await onRevoke(relationId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "撤销失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppDrawer
      className="output-invoice-collection-drawer"
      closeLabel="关闭红蓝票关系抽屉"
      footer={(
        <div className="output-invoice-collection-drawer__footer-actions">
          <button
            className="output-invoice-collection-drawer__button"
            disabled={submitting}
            onClick={onClose}
            type="button"
          >
            取消
          </button>
          <button
            className="output-invoice-collection-drawer__button output-invoice-collection-drawer__button--primary"
            disabled={submitting || !selectedCandidate || !evidence.trim()}
            onClick={handleSubmit}
            type="button"
          >
            确认关系
          </button>
        </div>
      )}
      onClose={onClose}
      open={open}
      subtitle={row?.invoice.displayNo || row?.invoice.invoiceNo || ""}
      title="红蓝票关系"
      width={560}
    >
      <div className="output-invoice-collection-drawer__body">
        {error ? <StatePanel compact tone="error">{error}</StatePanel> : null}
        {row?.redInvoice.summaries.length ? (
          <section className="output-invoice-collection-drawer__section">
            <h3>已有依据</h3>
            <div className="output-invoice-collection-relation-list">
              {row.redInvoice.summaries.map((item) => (
                <div className="output-invoice-collection-relation-list__item" key={`${item.id}:${item.source}`}>
                  <span>{item.invoiceNo || item.id} / {item.source || "auto"} / {item.evidence || item.reason}</span>
                  {item.source === "manual" && item.relationId ? (
                    <button
                      className="output-invoice-collection-drawer__button output-invoice-collection-drawer__button--warning"
                      disabled={submitting}
                      onClick={() => handleRevoke(item.relationId || "")}
                      type="button"
                    >
                      撤销人工关系 {item.invoiceNo || item.id}
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}
        <label className="output-invoice-collection-drawer__field">
          <span>搜索关联发票</span>
          <input
            onChange={(event) => setSearch(event.target.value)}
            placeholder="按发票号、购方、金额或日期搜索"
            value={search}
          />
        </label>
        <fieldset className="output-invoice-collection-candidate-list">
          <legend>关联发票候选</legend>
          <div className="output-invoice-collection-candidate-list__scroll">
            {candidates.length === 0 ? (
              <p className="output-invoice-collection-candidate-list__empty">暂无匹配候选发票。</p>
            ) : null}
            {candidates.map((candidate) => {
              const displayNo = candidate.invoice.displayNo || candidate.invoice.invoiceNo || candidate.invoiceId;
              const label = `${displayNo} / ${candidate.invoice.buyerName || "购方为空"} / ${candidate.invoice.totalWithTax || "金额为空"} / ${candidate.invoice.issueDate || "日期为空"}`;
              return (
                <label className="output-invoice-collection-candidate-list__option" key={candidate.id}>
                  <input
                    checked={selectedCandidateId === candidate.id}
                    name="output-invoice-red-relation-candidate"
                    onChange={(event) => setSelectedCandidateId(event.target.value)}
                    type="radio"
                    value={candidate.id}
                  />
                  <span>{label}</span>
                </label>
              );
            })}
          </div>
        </fieldset>
        <label className="output-invoice-collection-drawer__field">
          <span>关系类型</span>
          <select value={relationType} onChange={(event) => setRelationType(event.target.value as "red_invoice" | "blue_invoice")}>
            <option value="red_invoice">红字发票</option>
            <option value="blue_invoice">蓝字发票</option>
          </select>
        </label>
        <label className="output-invoice-collection-drawer__field">
          <span>确认依据</span>
          <textarea rows={4} value={evidence} onChange={(event) => setEvidence(event.target.value)} />
        </label>
      </div>
    </AppDrawer>
  );
}
