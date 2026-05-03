import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  confirmEtcBatchSubmitted,
  createEtcOaDraft,
  fetchEtcInvoices,
  markEtcBatchNotSubmitted,
  revokeEtcSubmittedInvoices,
} from "../features/etc/api";
import { useBackgroundJobProgress } from "../features/backgroundJobs/BackgroundJobProgressProvider";
import type { EtcInvoice, EtcInvoiceCounts, EtcInvoiceStatus, EtcOaDraftPayload } from "../features/etc/types";

const initialCounts: EtcInvoiceCounts = {
  unsubmitted: 0,
  submitted: 0,
};

function formatMoney(value: string | number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return String(value);
  }
  return parsed.toFixed(2);
}

function attachmentLabel(invoice: EtcInvoice) {
  if (invoice.hasPdf && invoice.hasXml) {
    return "PDF/XML完整";
  }
  if (!invoice.hasPdf && !invoice.hasXml) {
    return "缺PDF/XML";
  }
  return invoice.hasPdf ? "缺XML" : "缺PDF";
}

function invoiceMatchesBasket(invoice: EtcInvoice, basket: EtcInvoice[]) {
  return basket.some((item) => item.id === invoice.id);
}

function DialogShell({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="etc-dialog-backdrop">
      <section aria-modal="true" className="etc-dialog" role="dialog" aria-label={title}>
        <h2>{title}</h2>
        {children}
      </section>
    </div>
  );
}

export default function EtcTicketManagementPage() {
  const { jobs } = useBackgroundJobProgress();
  const [activeStatus, setActiveStatus] = useState<EtcInvoiceStatus>("unsubmitted");
  const [month, setMonth] = useState("");
  const [plate, setPlate] = useState("");
  const [keyword, setKeyword] = useState("");
  const [counts, setCounts] = useState(initialCounts);
  const [invoices, setInvoices] = useState<EtcInvoice[]>([]);
  const [selectedInvoiceIds, setSelectedInvoiceIds] = useState<string[]>([]);
  const [basket, setBasket] = useState<EtcInvoice[]>([]);
  const [selectedBasketIds, setSelectedBasketIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [revokeDialogOpen, setRevokeDialogOpen] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [draftCreating, setDraftCreating] = useState(false);
  const [draftResult, setDraftResult] = useState<EtcOaDraftPayload | null>(null);
  const refreshedImportJobIdsRef = useRef<Set<string>>(new Set());

  const loadInvoices = async (signal?: AbortSignal) => {
    setLoading(true);
    setActionError(null);
    try {
      const payload = await fetchEtcInvoices({
        status: activeStatus,
        month,
        plate: plate.trim(),
        keyword: keyword.trim(),
        signal,
      });
      setCounts(payload.counts);
      setInvoices(payload.items);
      setSelectedInvoiceIds([]);
      setBasket((current) => current.filter((item) => item.status === "unsubmitted"));
      setSelectedBasketIds([]);
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setActionError(caught instanceof Error ? caught.message : "ETC发票加载失败。");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void loadInvoices(controller.signal);
    return () => controller.abort();
  }, [activeStatus, month, plate, keyword]);

  useEffect(() => {
    const completedImportJobs = jobs.filter(
      (job) =>
        job.type === "etc_invoice_import"
        && (job.status === "succeeded" || job.status === "partial_success")
        && !refreshedImportJobIdsRef.current.has(job.jobId),
    );
    if (completedImportJobs.length === 0) {
      return;
    }
    completedImportJobs.forEach((job) => refreshedImportJobIdsRef.current.add(job.jobId));
    void loadInvoices();
  }, [jobs]);

  const basketTotal = useMemo(
    () => basket.reduce((sum, invoice) => sum + Number(invoice.totalAmount || 0), 0),
    [basket],
  );

  const selectedInvoices = useMemo(
    () => invoices.filter((invoice) => selectedInvoiceIds.includes(invoice.id)),
    [invoices, selectedInvoiceIds],
  );
  const hasBasketAttachmentGap = basket.some((invoice) => !invoice.hasPdf || !invoice.hasXml);

  const selectedSubmittedCount = selectedInvoices.filter((invoice) => invoice.status === "submitted").length;
  const canAddToBasket = activeStatus === "unsubmitted" && selectedInvoices.some((invoice) => !invoiceMatchesBasket(invoice, basket));

  const toggleInvoice = (invoiceId: string) => {
    setSelectedInvoiceIds((current) =>
      current.includes(invoiceId)
        ? current.filter((id) => id !== invoiceId)
        : [...current, invoiceId],
    );
  };

  const toggleBasketInvoice = (invoiceId: string) => {
    setSelectedBasketIds((current) =>
      current.includes(invoiceId)
        ? current.filter((id) => id !== invoiceId)
        : [...current, invoiceId],
    );
  };

  const addSelectedToBasket = () => {
    setBasket((current) => {
      const existingIds = new Set(current.map((invoice) => invoice.id));
      const additions = selectedInvoices.filter(
        (invoice) => invoice.status === "unsubmitted" && !existingIds.has(invoice.id),
      );
      return [...current, ...additions];
    });
  };

  const removeSelectedFromBasket = () => {
    setBasket((current) => current.filter((invoice) => !selectedBasketIds.includes(invoice.id)));
    setSelectedBasketIds([]);
  };

  const handleRevoke = async () => {
    const invoiceIds = selectedInvoices.filter((invoice) => invoice.status === "submitted").map((invoice) => invoice.id);
    if (invoiceIds.length === 0) {
      return;
    }
    setActionError(null);
    await revokeEtcSubmittedInvoices(invoiceIds);
    setRevokeDialogOpen(false);
    await loadInvoices();
  };

  const handleCreateDraft = async () => {
    setActionError(null);
    setDraftCreating(true);
    const draftWindow = window.open("about:blank", "_blank");
    if (draftWindow) {
      draftWindow.opener = null;
    }
    try {
      const result = await createEtcOaDraft(basket.map((invoice) => invoice.id));
      setDraftResult(result);
      if (!result.oaDraftUrl) {
        throw new Error("OA 草稿地址为空，请在 OA 系统中手动查找刚创建的草稿。");
      }
      if (draftWindow && !draftWindow.closed) {
        draftWindow.location.href = result.oaDraftUrl;
      } else {
        window.location.assign(result.oaDraftUrl);
      }
    } catch (caught) {
      if (draftWindow && !draftWindow.closed) {
        draftWindow.close();
      }
      setActionError(caught instanceof Error ? caught.message : "OA 草稿创建失败。");
    } finally {
      setDraftCreating(false);
    }
  };

  const handleResultConfirmation = async (submitted: boolean) => {
    if (!draftResult?.batchId) {
      return;
    }
    setActionError(null);
    if (submitted) {
      await confirmEtcBatchSubmitted(draftResult.batchId);
    } else {
      await markEtcBatchNotSubmitted(draftResult.batchId);
    }
    setCreateDialogOpen(false);
    setDraftResult(null);
    setBasket([]);
    setSelectedBasketIds([]);
    await loadInvoices();
  };

  const listTitle = activeStatus === "unsubmitted"
    ? `未提交发票 ${invoices.length} 张`
    : `已提交发票 ${invoices.length} 张`;

  return (
    <div className="etc-page" data-testid="etc-ticket-management-page">
      <header className="etc-page-header">
        <div>
          <div className="eyebrow">ETC批量提交</div>
          <h1>ETC票据管理</h1>
        </div>
        <Link className="etc-import-link" to="/imports?intent=etc_invoice">
          去导入中心导入 ETC 发票
        </Link>
      </header>

      {actionError ? <div className="state-panel error">{actionError}</div> : null}

      <section className="etc-filter-bar" aria-label="ETC筛选">
        <label>
          状态
          <select aria-label="状态筛选" value={activeStatus} onChange={(event) => setActiveStatus(event.target.value as EtcInvoiceStatus)}>
            <option value="unsubmitted">未提交</option>
            <option value="submitted">已提交</option>
          </select>
        </label>
        <label>
          月份
          <input aria-label="月份筛选" type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
        </label>
        <label>
          车牌
          <input aria-label="车牌筛选" value={plate} onChange={(event) => setPlate(event.target.value)} placeholder="云ADA0381" />
        </label>
        <label>
          搜索
          <input aria-label="keyword 搜索" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="发票号/销方/购方" />
        </label>
      </section>

      <div className="etc-layout">
        <section className="etc-left-layout" aria-label="ETC发票区">
          <aside className="etc-status-groups" aria-label="状态分组">
            <button
              type="button"
              className={activeStatus === "unsubmitted" ? "active" : ""}
              onClick={() => setActiveStatus("unsubmitted")}
            >
              未提交 {counts.unsubmitted}
            </button>
            <button
              type="button"
              className={activeStatus === "submitted" ? "active" : ""}
              onClick={() => setActiveStatus("submitted")}
            >
              已提交 {counts.submitted}
            </button>
          </aside>

          <section className="etc-invoice-panel">
            <div className="etc-panel-heading">
              <h2>{listTitle}</h2>
              {activeStatus === "unsubmitted" ? (
                <button type="button" disabled={!canAddToBasket} onClick={addSelectedToBasket}>加入提交篮子</button>
              ) : (
                <button type="button" disabled={selectedSubmittedCount === 0} onClick={() => setRevokeDialogOpen(true)}>撤销提交状态</button>
              )}
            </div>
            {loading ? <div className="state-panel">正在加载ETC发票。</div> : null}
            {!loading && invoices.length === 0 ? <div className="state-panel">当前筛选下没有ETC发票。</div> : null}
            <div className="etc-invoice-list">
              {invoices.map((invoice) => {
                const inBasket = invoiceMatchesBasket(invoice, basket);
                return (
                  <article
                    key={invoice.id}
                    className={`etc-ticket-row ${invoice.status}${inBasket ? " in-basket" : ""}`}
                    data-testid={`etc-invoice-row-${invoice.id}`}
                  >
                    <label className="etc-row-check">
                      <input
                        aria-label={`选择发票 ${invoice.invoiceNumber}`}
                        checked={selectedInvoiceIds.includes(invoice.id)}
                        type="checkbox"
                        onChange={() => toggleInvoice(invoice.id)}
                      />
                    </label>
                    <div className="etc-row-main">
                      <div className="etc-row-title">
                        <strong>{invoice.invoiceNumber}</strong>
                        {inBasket ? <span className="etc-badge">已在篮子</span> : null}
                      </div>
                      <div className="etc-row-fields">
                        <span>开票 {invoice.issueDate}</span>
                        <span>通行 {invoice.passageStartDate ?? "-"} 至 {invoice.passageEndDate ?? "-"}</span>
                        <span>车牌 {invoice.plateNumber}</span>
                        <span>金额 {formatMoney(invoice.totalAmount)}</span>
                        <span>税额 {formatMoney(invoice.taxAmount)}</span>
                        <span>销方 {invoice.sellerName}</span>
                        <span>购方 {invoice.buyerName}</span>
                        <span>{attachmentLabel(invoice)}</span>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        </section>

        <aside className="etc-basket" aria-label="提交篮子">
          <div className="etc-panel-heading">
            <div>
              <h2>待提交 {basket.length} 张</h2>
              <p>合计金额 {formatMoney(basketTotal)}</p>
            </div>
            <button type="button" disabled={selectedBasketIds.length === 0} onClick={removeSelectedFromBasket}>移回未提交</button>
          </div>
          {basket.length === 0 ? <div className="state-panel">提交篮子为空。</div> : null}
          {hasBasketAttachmentGap ? <div className="state-panel error">提交篮子存在缺PDF或缺XML的发票，补齐附件后才能创建 OA 草稿。</div> : null}
          <div className="etc-basket-list">
            {basket.map((invoice) => (
              <article key={invoice.id} className="etc-basket-row">
                <label>
                  <input
                    aria-label={`从提交篮子选择发票 ${invoice.invoiceNumber}`}
                    checked={selectedBasketIds.includes(invoice.id)}
                    type="checkbox"
                    onChange={() => toggleBasketInvoice(invoice.id)}
                  />
                  <span>{invoice.invoiceNumber}</span>
                </label>
                <strong>{formatMoney(invoice.totalAmount)}</strong>
              </article>
            ))}
          </div>
          <button
            type="button"
            className="etc-primary-action"
            disabled={basket.length === 0 || hasBasketAttachmentGap}
            onClick={() => setCreateDialogOpen(true)}
          >
            提交OA支付申请
          </button>
        </aside>
      </div>

      {revokeDialogOpen ? (
        <DialogShell title="撤销提交状态">
          <p>只修改 fin-ops 内部 ETC 发票状态，不删除 OA 草稿，不撤回 OA 流程，不修改 OA 数据。</p>
          <div className="etc-dialog-actions">
            <button type="button" onClick={() => setRevokeDialogOpen(false)}>取消</button>
            <button type="button" onClick={handleRevoke}>确认撤销</button>
          </div>
        </DialogShell>
      ) : null}

      {createDialogOpen ? (
        <DialogShell title={draftResult ? "OA提交结果确认" : "创建OA支付申请草稿"}>
          {draftResult ? (
            <>
              <p>OA 草稿已打开，请根据你在 OA 中的实际处理结果确认本批次状态。</p>
              <div className="etc-dialog-actions">
                <button type="button" onClick={() => handleResultConfirmation(true)}>确认已提交OA</button>
                <button type="button" onClick={() => handleResultConfirmation(false)}>未提交OA</button>
              </div>
            </>
          ) : (
            <>
              <p>将创建 OA 支付申请草稿。</p>
              <p>将跳转 OA 页面。</p>
              <p>app 不会自动提交 OA。</p>
              <p>需要在 OA 中检查并手动提交。</p>
              <div className="etc-dialog-actions">
                <button type="button" onClick={() => setCreateDialogOpen(false)}>取消</button>
                <button type="button" onClick={handleCreateDraft} disabled={draftCreating}>
                  {draftCreating ? "正在创建..." : "确认创建草稿"}
                </button>
              </div>
            </>
          )}
        </DialogShell>
      ) : null}
    </div>
  );
}
