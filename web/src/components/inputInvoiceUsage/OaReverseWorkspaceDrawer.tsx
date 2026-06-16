import { useEffect, useId, useMemo, useState, type ReactNode } from "react";

import AppDrawer from "../common/AppDrawer";
import type {
  CreateInputInvoiceUsageOaReverseDraftFromSelectionRequest,
  InputInvoiceUsageOaReverseBatch,
  InputInvoiceUsageOaReverseInvoice,
  InputInvoiceUsageOaReverseSubmittedHistoryResponse,
  InputInvoiceUsageOaReverseTargetApplicant,
  ManualInputInvoiceUsageOaReverseStatusRequest,
} from "../../features/inputInvoiceUsage/types";

export type OaReversePreviewRequest = {
  sourceFilters: unknown[];
  selectedInvoiceIds: string[];
  targetApplicantCode?: string | null;
};

export type OaReversePreviewGroup = {
  targetApplicantCode?: string | null;
  targetApplicantName: string;
  invoiceCount: number;
  totalWithTax: string;
  invoiceRows?: InputInvoiceUsageOaReverseInvoice[];
  candidateInvoiceIds?: string[];
  candidateInvoices?: InputInvoiceUsageOaReverseInvoice[];
  rejectedInvoices?: OaReverseRejectedInvoice[];
};

export type OaReverseRejectedInvoice = {
  invoiceId: string;
  invoiceNumber?: string | null;
  reasonCode?: string | null;
  reason: string;
};

export type OaReversePreviewPayload = {
  previewId?: string;
  previewHash?: string;
  source?: string;
  targetApplicantCode?: string;
  targetApplicantName?: string;
  targetApplicants?: InputInvoiceUsageOaReverseTargetApplicant[];
  invoiceCount: number;
  totalWithTax: string;
  groups: OaReversePreviewGroup[];
  invoiceRows?: InputInvoiceUsageOaReverseInvoice[];
  candidateInvoices?: InputInvoiceUsageOaReverseInvoice[];
  warnings?: string[];
  canCreateDraft?: boolean;
  nextAction?: string;
  unavailableReason?: string;
  permissions?: {
    canCreateBatch?: boolean;
    canCreateDraft?: boolean;
    canRevoke?: boolean;
    canManualStatus?: boolean;
  };
};

type OaReverseWorkspaceDrawerProps = {
  open: boolean;
  sourceFilters: unknown[];
  selectedInvoiceIds: string[];
  loadPreview: (request: OaReversePreviewRequest) => Promise<OaReversePreviewPayload>;
  createDraftFromSelection?: (request: CreateInputInvoiceUsageOaReverseDraftFromSelectionRequest) => Promise<InputInvoiceUsageOaReverseBatch>;
  loadSubmittedHistory?: () => Promise<InputInvoiceUsageOaReverseSubmittedHistoryResponse>;
  manualStatus?: (batchId: string, request: ManualInputInvoiceUsageOaReverseStatusRequest) => Promise<InputInvoiceUsageOaReverseBatch>;
  onClose: () => void;
};

export default function OaReverseWorkspaceDrawer({
  open,
  sourceFilters,
  selectedInvoiceIds,
  loadPreview,
  createDraftFromSelection,
  loadSubmittedHistory,
  manualStatus,
  onClose,
}: OaReverseWorkspaceDrawerProps) {
  const [preview, setPreview] = useState<OaReversePreviewPayload | null>(null);
  const [batch, setBatch] = useState<InputInvoiceUsageOaReverseBatch | null>(null);
  const [activeTab, setActiveTab] = useState<"pending" | "submitted">("pending");
  const [submittedHistory, setSubmittedHistory] = useState<InputInvoiceUsageOaReverseSubmittedHistoryResponse["items"]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([]);
  const [targetApplicantCode, setTargetApplicantCode] = useState<string | null>(null);
  const [targetApplicantMenuOpen, setTargetApplicantMenuOpen] = useState(false);
  const targetApplicantLabelId = useId();
  const request = useMemo(
    () => ({ sourceFilters, selectedInvoiceIds, targetApplicantCode }),
    [sourceFilters, selectedInvoiceIds, targetApplicantCode],
  );

  useEffect(() => {
    if (!open) {
      setPreview(null);
      setBatch(null);
      setLoading(false);
      setActionLoading(null);
      setError(null);
      setFeedback(null);
      setConfirmationOpen(false);
      setActiveTab("pending");
      setSubmittedHistory([]);
      setHistoryError(null);
      setHistoryLoading(false);
      setSelectedCandidateIds([]);
      setTargetApplicantCode(null);
      setTargetApplicantMenuOpen(false);
      return undefined;
    }

    let active = true;
    setLoading(true);
    setError(null);
    loadPreview(request)
      .then((payload) => {
        if (active) {
          setPreview(payload);
          setBatch(null);
          setFeedback(null);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "反提 OA 预览加载失败");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [loadPreview, open, request]);

  const candidateInvoices = useMemo(() => (preview ? invoicesFromPreview(preview) : []), [preview]);
  const candidateIdsKey = candidateInvoices.map((invoice) => invoice.invoiceId).join("\n");
  useEffect(() => {
    setSelectedCandidateIds(candidateInvoices.map((invoice) => invoice.invoiceId));
  }, [candidateIdsKey]);
  const selectedCandidateIdSet = useMemo(() => new Set(selectedCandidateIds), [selectedCandidateIds]);
  const targetApplicants = preview?.targetApplicants ?? [];
  const selectedTargetApplicantCode = targetApplicantCode ?? preview?.targetApplicantCode ?? "";
  const canCreateDraft = Boolean(
    preview
    && createDraftFromSelection
    && preview.previewId
    && (preview?.canCreateDraft ?? preview.nextAction === "create_oa_draft")
    && selectedCandidateIds.length > 0
    && !batch?.oaDraftUrl
    && (preview?.permissions?.canCreateDraft ?? true),
  );
  const canConfirmSubmission = Boolean(batch && manualStatus && batch.oaDraftUrl && (batch.canConfirmSubmission ?? batch.status === "oa_draft_created"));
  const createDraftDisabled = Boolean(actionLoading) || !canCreateDraft;

  const runBatchAction = (
    actionName: string,
    action: () => Promise<InputInvoiceUsageOaReverseBatch>,
    successMessage: string,
    onSuccess?: (nextBatch: InputInvoiceUsageOaReverseBatch) => void,
  ) => {
    setActionLoading(actionName);
    setError(null);
    setFeedback(null);
    action()
      .then((nextBatch) => {
        setBatch(nextBatch);
        setFeedback(successMessage);
        onSuccess?.(nextBatch);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : `${successMessage}失败。`);
      })
      .finally(() => setActionLoading(null));
  };

  const handleCreateDraft = () => {
    if (!preview?.previewId || !createDraftFromSelection) {
      return;
    }
    const selectedIds = [...selectedCandidateIds];
    const resolvedTargetApplicantCode = selectedTargetApplicantCode || firstTargetApplicantCode(preview);
    runBatchAction(
      "createDraft",
      async () => {
        const refreshedPreview = await loadPreview({
          sourceFilters,
          selectedInvoiceIds: selectedIds,
          targetApplicantCode: resolvedTargetApplicantCode || null,
        });
        setPreview(refreshedPreview);
        const refreshedCandidateIds = invoicesFromPreview(refreshedPreview).map((invoice) => invoice.invoiceId);
        setSelectedCandidateIds(refreshedCandidateIds);
        if (!refreshedPreview.previewId || !refreshedPreview.previewHash || refreshedCandidateIds.length === 0) {
          throw new Error(refreshedPreview.unavailableReason || "当前选择没有可创建 OA 草稿的候选发票。");
        }
        return createDraftFromSelection({
          previewId: refreshedPreview.previewId,
          expectedPreviewHash: refreshedPreview.previewHash,
          idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-draft"),
          selectedInvoiceIds: refreshedCandidateIds,
          targetApplicantCode: refreshedPreview.targetApplicantCode || resolvedTargetApplicantCode,
        });
      },
      "OA 草稿已创建，请在 OA 页面处理后选择提交状态。",
      () => setConfirmationOpen(true),
    );
  };

  const handleSubmissionDecision = (decision: "submitted" | "not_submitted") => {
    if (!batch || !manualStatus) {
      return;
    }
    setActionLoading(`submissionDecision:${decision}`);
    setError(null);
    setFeedback(null);
    manualStatus(batch.batchId, {
        expectedVersion: batch.version,
        idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-submission-decision"),
        decision,
        reason: decision === "submitted" ? "用户确认已在 OA 提交" : "用户确认暂未提交 OA",
      })
      .then((nextBatch) => {
        setConfirmationOpen(false);
        if (decision === "submitted") {
          setBatch(nextBatch);
          setFeedback("已进入已提交历史。");
          setActiveTab("submitted");
          return;
        }
        setBatch(null);
        setFeedback("已返回待处理，可重新创建 OA 草稿。");
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "OA 提交状态确认失败。");
      })
      .finally(() => setActionLoading(null));
  };

  useEffect(() => {
    if (!open || activeTab !== "submitted" || !loadSubmittedHistory) {
      return undefined;
    }
    let active = true;
    setHistoryLoading(true);
    setHistoryError(null);
    loadSubmittedHistory()
      .then((payload) => {
        if (active) {
          setSubmittedHistory(payload.items);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setHistoryError(reason instanceof Error ? reason.message : "已提交历史加载失败。");
        }
      })
      .finally(() => {
        if (active) {
          setHistoryLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [activeTab, loadSubmittedHistory, open]);

  return (
    <AppDrawer
      className="input-invoice-usage-oa-drawer"
      closeLabel="关闭以发票反提 OA 工作流"
      onClose={onClose}
      open={open}
      title="以发票反提 OA"
      modal={false}
      width="min(920px, 100vw)"
    >
      <div aria-label="以发票反提 OA 工作流" className="input-invoice-usage-drawer-body">
        {error ? (
          <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--error" role="alert">
            {error}
          </div>
        ) : null}
        {feedback ? (
          <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--success" role="status">
            {feedback}
          </div>
        ) : null}
        <div aria-label="反提 OA 状态" className="input-invoice-usage-oa-tabs" role="tablist">
          <TabButton active={activeTab === "pending"} onClick={() => setActiveTab("pending")}>
            待处理
          </TabButton>
          <TabButton active={activeTab === "submitted"} onClick={() => setActiveTab("submitted")}>
            已提交
          </TabButton>
        </div>
        {activeTab === "submitted" ? (
          <SubmittedHistoryPanel
            error={historyError}
            items={submittedHistory}
            loading={historyLoading}
          />
        ) : (
          <>
            {loading ? (
              <div className="input-invoice-usage-drawer-loading">
                <span aria-label="正在加载反提 OA 预览" className="input-invoice-usage-drawer-spinner" role="progressbar" />
                <span>正在读取后端预览</span>
              </div>
            ) : null}
            {preview ? (
              <>
                <div className="input-invoice-usage-oa-metrics">
                  <SummaryMetric label="候选发票数" value={String(preview.invoiceCount)} />
                  <SummaryMetric label="候选价税合计" value={preview.totalWithTax} />
                </div>
                {targetApplicants.length > 0 ? (
                  <div className="input-invoice-usage-rules-field input-invoice-usage-oa-target">
                    <span id={targetApplicantLabelId}>目标 OA 申请人</span>
                    <button
                      aria-expanded={targetApplicantMenuOpen}
                      aria-haspopup="listbox"
                      aria-labelledby={targetApplicantLabelId}
                      className="input-invoice-usage-oa-select"
                      onClick={() => setTargetApplicantMenuOpen((current) => !current)}
                      type="button"
                    >
                      {targetApplicants.find((applicant) => applicant.code === selectedTargetApplicantCode)?.name
                        ?? preview.targetApplicantName
                        ?? "请选择"}
                    </button>
                    {targetApplicantMenuOpen ? (
                      <div aria-labelledby={targetApplicantLabelId} className="input-invoice-usage-oa-options" role="listbox">
                        {targetApplicants.map((applicant) => (
                          <button
                            aria-selected={applicant.code === selectedTargetApplicantCode}
                            className="input-invoice-usage-oa-option"
                            key={applicant.code}
                            onClick={() => {
                              setTargetApplicantCode(applicant.code);
                              setTargetApplicantMenuOpen(false);
                            }}
                            role="option"
                            type="button"
                          >
                            {applicant.name}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {preview.warnings && preview.warnings.length > 0 ? (
                  <div className="input-invoice-usage-oa-stack">
                    {preview.warnings.map((warning) => (
                      <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--info" key={warning}>
                        {warning}
                      </div>
                    ))}
                  </div>
                ) : null}
                {!(preview.canCreateDraft ?? preview.nextAction === "create_oa_draft") ? (
                  <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--info">
                    {previewUnavailableMessage(preview, candidateInvoices.length)}
                  </div>
                ) : null}
                <Section title="目标 OA 分组">
                  {preview.groups.length === 0 ? <p className="input-invoice-usage-rules-empty">暂无可提交分组。</p> : null}
                  <div className="input-invoice-usage-oa-stack">
                    {preview.groups.map((group) => (
                      <article className="input-invoice-usage-oa-group" key={group.targetApplicantCode || group.targetApplicantName}>
                        <strong>{group.targetApplicantName}</strong>
                        {group.targetApplicantCode ? <span className="input-invoice-usage-rules-tag">{group.targetApplicantCode}</span> : null}
                        <span className="input-invoice-usage-rules-tag">{group.invoiceCount} 张</span>
                        <span className="input-invoice-usage-rules-tag input-invoice-usage-oa-amount-tag">{group.totalWithTax}</span>
                      </article>
                    ))}
                  </div>
                </Section>
                <Section title="候选发票清单">
                  {candidateInvoices.length > 0 ? (
                    <div className="input-invoice-usage-oa-actions">
                      <button
                        className="input-invoice-usage-button"
                        onClick={() => setSelectedCandidateIds(candidateInvoices.map((invoice) => invoice.invoiceId))}
                        type="button"
                      >
                        全选候选
                      </button>
                      <button className="input-invoice-usage-button" onClick={() => setSelectedCandidateIds([])} type="button">
                        清空选择
                      </button>
                      <span className="input-invoice-usage-rules-tag">已选 {selectedCandidateIds.length} 张</span>
                    </div>
                  ) : null}
                  <div className="input-invoice-usage-rules-table-shell">
                    <table aria-label="反提 OA 候选发票清单" className="input-invoice-usage-oa-table">
                      <thead>
                        <tr>
                          <th scope="col">选择</th>
                          <th scope="col">发票号码</th>
                          <th scope="col">销方</th>
                          <th scope="col">开票日期</th>
                          <th scope="col">价税合计</th>
                          <th scope="col">状态</th>
                        </tr>
                      </thead>
                      <tbody>
                        {candidateInvoices.map((invoice) => (
                          <tr key={invoice.invoiceId}>
                            <td className="input-invoice-usage-oa-table__select">
                              <input
                                aria-label={`选择候选发票 ${invoice.displayNo || invoice.invoiceNumber || invoice.invoiceId}`}
                                checked={selectedCandidateIdSet.has(invoice.invoiceId)}
                                onChange={(event) => {
                                  setSelectedCandidateIds((current) => {
                                    const next = new Set(current);
                                    if (event.target.checked) {
                                      next.add(invoice.invoiceId);
                                    } else {
                                      next.delete(invoice.invoiceId);
                                    }
                                    return candidateInvoices
                                      .map((candidate) => candidate.invoiceId)
                                      .filter((invoiceId) => next.has(invoiceId));
                                  });
                                }}
                                type="checkbox"
                              />
                            </td>
                            <td>{invoice.displayNo || invoice.invoiceNumber || invoice.invoiceId}</td>
                            <td>{invoice.sellerName || "-"}</td>
                            <td>{invoice.issueDate || "-"}</td>
                            <td className="input-invoice-usage-oa-table__amount">{invoice.totalWithTax || "-"}</td>
                            <td>{invoice.paymentStatusLabel || "候选"}</td>
                          </tr>
                        ))}
                        {candidateInvoices.length === 0 ? (
                          <tr>
                            <td colSpan={6}>当前预览未返回候选发票。</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                </Section>
                <Section title="OA 草稿">
                  {batch?.oaDraftUrl ? (
                    <DraftStatusPanel batch={batch} />
                  ) : (
                    <p className="input-invoice-usage-rules-empty">请选择候选发票后创建 OA 草稿。</p>
                  )}
                  <div className="input-invoice-usage-oa-actions">
                    <button
                      className="input-invoice-usage-button input-invoice-usage-button--primary"
                      disabled={createDraftDisabled}
                      onClick={handleCreateDraft}
                      type="button"
                    >
                      {actionLoading === "createDraft" ? "创建草稿中..." : "创建 OA 草稿"}
                    </button>
                    {batch?.oaDraftUrl ? (
                      <a className="input-invoice-usage-button" href={batch.oaDraftUrl} rel="noreferrer" target="_blank">
                        打开 OA 草稿
                      </a>
                    ) : null}
                  </div>
                </Section>
              </>
            ) : null}
          </>
        )}
        {confirmationOpen && canConfirmSubmission && batch?.oaDraftUrl ? (
          <DraftConfirmationDialog
            actionLoading={actionLoading}
            draftUrl={batch.oaDraftUrl}
            onDecision={handleSubmissionDecision}
          />
        ) : null}
      </div>
    </AppDrawer>
  );
}

function invoicesFromPreview(preview: OaReversePreviewPayload) {
  const byId = new Map<string, InputInvoiceUsageOaReverseInvoice>();
  for (const invoice of preview.candidateInvoices ?? []) {
    byId.set(invoice.invoiceId, invoice);
  }
  for (const invoice of preview.invoiceRows ?? []) {
    byId.set(invoice.invoiceId, invoice);
  }
  for (const group of preview.groups) {
    for (const invoice of group.invoiceRows ?? []) {
      byId.set(invoice.invoiceId, {
        ...invoice,
        targetApplicantName: invoice.targetApplicantName || group.targetApplicantName,
      });
    }
    for (const invoice of group.candidateInvoices ?? []) {
      byId.set(invoice.invoiceId, {
        ...invoice,
        targetApplicantName: invoice.targetApplicantName || group.targetApplicantName,
      });
    }
    for (const invoiceId of group.candidateInvoiceIds ?? []) {
      if (!byId.has(invoiceId)) {
        byId.set(invoiceId, {
          invoiceId,
          invoiceNumber: invoiceId,
          displayNo: invoiceId,
          sellerName: "",
          issueDate: "",
          totalWithTax: "",
          paymentStatusLabel: "候选",
          targetApplicantName: group.targetApplicantName,
        });
      }
    }
  }
  return Array.from(byId.values());
}

function firstTargetApplicantCode(preview: OaReversePreviewPayload) {
  return preview.groups.find((group) => group.targetApplicantCode)?.targetApplicantCode ?? null;
}

function previewUnavailableMessage(preview: OaReversePreviewPayload, candidateCount: number) {
  if (preview.unavailableReason) {
    return preview.unavailableReason;
  }
  if (candidateCount > 0 || preview.nextAction === "create_batch") {
    return "当前账户或预览状态暂不允许创建 OA 草稿。";
  }
  return "当前预览未返回可创建 OA 草稿的候选发票。";
}

function createIdempotencyKey(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}:${crypto.randomUUID()}`;
  }
  return `${prefix}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <article className="input-invoice-usage-oa-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="input-invoice-usage-rules-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function TabButton({ active, children, onClick }: { active: boolean; children: ReactNode; onClick: () => void }) {
  return (
    <button
      aria-selected={active}
      className={active ? "input-invoice-usage-oa-tab input-invoice-usage-oa-tab--active" : "input-invoice-usage-oa-tab"}
      onClick={onClick}
      role="tab"
      type="button"
    >
      {children}
    </button>
  );
}

function DraftStatusPanel({ batch }: { batch: InputInvoiceUsageOaReverseBatch }) {
  return (
    <article className="input-invoice-usage-oa-batch">
      <div className="input-invoice-usage-oa-group">
        <strong>{batch.targetApplicantName || batch.targetApplicantCode || "目标申请人"}</strong>
        <span className="input-invoice-usage-rules-tag">{batch.invoiceIds.length || batch.invoiceRows.length} 张</span>
        <span className="input-invoice-usage-rules-tag input-invoice-usage-oa-amount-tag">{batch.totalWithTax || "-"}</span>
      </div>
      <p>OA 草稿已创建。请在 OA 页面提交后回到这里确认结果。</p>
    </article>
  );
}

function DraftConfirmationDialog({
  actionLoading,
  draftUrl,
  onDecision,
}: {
  actionLoading: string | null;
  draftUrl: string;
  onDecision: (decision: "submitted" | "not_submitted") => void;
}) {
  return (
    <div className="input-invoice-usage-oa-confirmation-backdrop">
      <div aria-label="OA 草稿提交确认" aria-modal="true" className="input-invoice-usage-oa-confirmation" role="dialog">
        <h3>OA 草稿提交确认</h3>
        <p>请在 OA 页面手动提交草稿后，再选择本次处理结果。</p>
        <div className="input-invoice-usage-oa-actions">
          <a className="input-invoice-usage-button" href={draftUrl} rel="noreferrer" target="_blank">
            打开 OA 草稿
          </a>
          <button
            className="input-invoice-usage-button input-invoice-usage-button--primary"
            disabled={Boolean(actionLoading)}
            onClick={() => onDecision("submitted")}
            type="button"
          >
            {actionLoading === "submissionDecision:submitted" ? "记录中..." : "已提交 OA"}
          </button>
          <button
            className="input-invoice-usage-button"
            disabled={Boolean(actionLoading)}
            onClick={() => onDecision("not_submitted")}
            type="button"
          >
            {actionLoading === "submissionDecision:not_submitted" ? "回滚中..." : "未提交 OA"}
          </button>
        </div>
      </div>
    </div>
  );
}

function SubmittedHistoryPanel({
  error,
  items,
  loading,
}: {
  error: string | null;
  items: InputInvoiceUsageOaReverseSubmittedHistoryResponse["items"];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="input-invoice-usage-drawer-loading">
        <span aria-label="正在加载已提交历史" className="input-invoice-usage-drawer-spinner" role="progressbar" />
        <span>正在加载已提交历史</span>
      </div>
    );
  }
  if (error) {
    return (
      <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--error" role="alert">
        {error}
      </div>
    );
  }
  if (items.length === 0) {
    return <p className="input-invoice-usage-rules-empty">暂无已提交历史。</p>;
  }
  return (
    <div className="input-invoice-usage-oa-history">
      {items.map((item, index) => (
        <article className="input-invoice-usage-oa-history-item" key={`${item.targetApplicantName}:${item.submittedAt}:${index}`}>
          <div className="input-invoice-usage-oa-history-item__header">
            <strong>{item.targetApplicantName || "目标申请人"}</strong>
            <span>{item.submittedAt || "-"}</span>
            <span className="input-invoice-usage-rules-tag">{item.invoiceCount} 张</span>
            <span className="input-invoice-usage-rules-tag input-invoice-usage-oa-amount-tag">{item.totalWithTax || "-"}</span>
          </div>
          <div className="input-invoice-usage-rules-table-shell">
            <table aria-label={`${item.targetApplicantName || "目标申请人"}已提交发票`} className="input-invoice-usage-oa-table">
              <thead>
                <tr>
                  <th scope="col">发票号码</th>
                  <th scope="col">销方</th>
                  <th scope="col">开票日期</th>
                  <th scope="col">价税合计</th>
                </tr>
              </thead>
              <tbody>
                {item.invoices.map((invoice) => (
                  <tr key={`${invoice.invoiceNo}:${invoice.sellerName}:${invoice.invoiceDate}`}>
                    <td>{invoice.invoiceNo || "-"}</td>
                    <td>{invoice.sellerName || "-"}</td>
                    <td>{invoice.invoiceDate || "-"}</td>
                    <td className="input-invoice-usage-oa-table__amount">{invoice.totalWithTax || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ))}
    </div>
  );
}
