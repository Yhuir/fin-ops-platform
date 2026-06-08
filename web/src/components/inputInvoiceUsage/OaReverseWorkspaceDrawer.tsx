import { useEffect, useId, useMemo, useState, type ReactNode } from "react";

import AppDrawer from "../common/AppDrawer";
import type {
  CreateInputInvoiceUsageOaReverseBatchRequest,
  InputInvoiceUsageOaReverseBatch,
  InputInvoiceUsageOaReverseInvoice,
  InputInvoiceUsageOaReverseTargetApplicant,
  InputInvoiceUsageOaReverseVersionedRequest,
  ManualInputInvoiceUsageOaReverseStatusRequest,
  RevokeInputInvoiceUsageOaReverseDraftRequest,
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
  createBatch?: (request: CreateInputInvoiceUsageOaReverseBatchRequest) => Promise<InputInvoiceUsageOaReverseBatch>;
  loadBatch?: (batchId: string) => Promise<InputInvoiceUsageOaReverseBatch>;
  createDraft?: (batchId: string, request: InputInvoiceUsageOaReverseVersionedRequest) => Promise<InputInvoiceUsageOaReverseBatch>;
  refreshStatus?: (batchId: string, request: Pick<InputInvoiceUsageOaReverseVersionedRequest, "expectedVersion">) => Promise<InputInvoiceUsageOaReverseBatch>;
  revokeDraft?: (batchId: string, request: RevokeInputInvoiceUsageOaReverseDraftRequest) => Promise<InputInvoiceUsageOaReverseBatch>;
  manualStatus?: (batchId: string, request: ManualInputInvoiceUsageOaReverseStatusRequest) => Promise<InputInvoiceUsageOaReverseBatch>;
  onClose: () => void;
};

export default function OaReverseWorkspaceDrawer({
  open,
  sourceFilters,
  selectedInvoiceIds,
  loadPreview,
  createBatch,
  createDraft,
  refreshStatus,
  revokeDraft,
  manualStatus,
  onClose,
}: OaReverseWorkspaceDrawerProps) {
  const [preview, setPreview] = useState<OaReversePreviewPayload | null>(null);
  const [batch, setBatch] = useState<InputInvoiceUsageOaReverseBatch | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [revokeReason, setRevokeReason] = useState("");
  const [manualReason, setManualReason] = useState("");
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
      setRevokeReason("");
      setManualReason("");
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
  const rejected = preview ? rejectedInvoices(preview) : [];
  const canCreateBatch = Boolean(
    preview
    && !batch
    && createBatch
    && preview.previewId
    && preview.canCreateDraft
    && selectedCandidateIds.length > 0
    && (preview.permissions?.canCreateBatch ?? true),
  );
  const canCreateDraft = Boolean(batch && createDraft && (batch.canCreateDraft ?? true) && !batch.oaDraftUrl);
  const canConfirmSubmission = Boolean(batch && manualStatus && batch.oaDraftUrl && (batch.canConfirmSubmission ?? batch.status === "oa_draft_created"));
  const canRefreshStatus = Boolean(batch && refreshStatus && (batch.canRefreshStatus ?? true));
  const canRevoke = Boolean(batch && revokeDraft && batch.oaDraftUrl && (batch.canRevoke ?? true));
  const canManualFallback = Boolean(batch && manualStatus && isManualFallbackStatus(batch.status, batch.oaDetectionStatus) && (batch.canManualStatus ?? true));

  const runBatchAction = (
    actionName: string,
    action: () => Promise<InputInvoiceUsageOaReverseBatch>,
    successMessage: string,
  ) => {
    setActionLoading(actionName);
    setError(null);
    setFeedback(null);
    action()
      .then((nextBatch) => {
        setBatch(nextBatch);
        setFeedback(successMessage);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : `${successMessage}失败。`);
      })
      .finally(() => setActionLoading(null));
  };

  const handleCreateBatch = () => {
    if (!preview?.previewId || !createBatch) {
      return;
    }
    runBatchAction(
      "createBatch",
      () => createBatch({
        previewId: preview.previewId ?? "",
        expectedPreviewHash: preview.previewHash,
        idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-batch"),
        selectedInvoiceIds: selectedCandidateIds,
        targetApplicantCode: firstTargetApplicantCode(preview),
      }),
      "本地批次已创建。",
    );
  };

  const handleCreateDraft = () => {
    if (!batch || !createDraft) {
      return;
    }
    runBatchAction(
      "createDraft",
      () => createDraft(batch.batchId, {
        expectedVersion: batch.version,
        idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-draft"),
      }),
      "OA 草稿已创建，请在 OA 页面处理后选择提交状态。",
    );
  };

  const handleRefreshStatus = () => {
    if (!batch || !refreshStatus) {
      return;
    }
    runBatchAction(
      "refreshStatus",
      () => refreshStatus(batch.batchId, { expectedVersion: batch.version }),
      "OA 状态已刷新。",
    );
  };

  const handleRevokeDraft = () => {
    if (!batch || !revokeDraft) {
      return;
    }
    runBatchAction(
      "revokeDraft",
      () => revokeDraft(batch.batchId, {
        expectedVersion: batch.version,
        reason: revokeReason,
        idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-revoke"),
      }),
      "本地草稿绑定已释放。",
    );
  };

  const handleManualStatus = (decision: "submitted" | "not_submitted") => {
    if (!batch || !manualStatus) {
      return;
    }
    runBatchAction(
      `manualStatus:${decision}`,
      () => manualStatus(batch.batchId, {
        expectedVersion: batch.version,
        idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-manual-status"),
        decision,
        reason: manualReason,
      }),
      "人工状态已记录。",
    );
  };

  const handleSubmissionDecision = (decision: "submitted" | "not_submitted") => {
    if (!batch || !manualStatus) {
      return;
    }
    runBatchAction(
      `submissionDecision:${decision}`,
      () => manualStatus(batch.batchId, {
        expectedVersion: batch.version,
        idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-submission-decision"),
        decision,
        reason: decision === "submitted" ? "用户确认已在 OA 提交" : "用户确认暂未提交 OA",
      }),
      decision === "submitted" ? "已记录 OA 提交确认，可刷新 OA 状态。" : "已记录暂未提交 OA。",
    );
  };

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
        {loading ? (
          <div className="input-invoice-usage-drawer-loading">
            <span aria-label="正在加载反提 OA 预览" className="input-invoice-usage-drawer-spinner" role="progressbar" />
            <span>正在读取后端预览</span>
          </div>
        ) : null}
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
            {!preview.canCreateDraft ? (
              <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--info">
                {preview.unavailableReason || preview.nextAction || "后端当前未允许创建 OA 草稿。"}
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
            <Section title="不可提交原因">
              {rejected.length === 0 ? <p className="input-invoice-usage-rules-empty">当前预览未返回不可提交发票。</p> : null}
              <div className="input-invoice-usage-oa-stack">
                {rejected.map((item) => (
                  <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--warning" key={item.invoiceId}>
                    <strong>{item.invoiceNumber || item.invoiceId}</strong>
                    <span>{item.reason}</span>
                  </div>
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
            <Section title="批次与 OA 草稿">
              {batch ? <BatchStatusPanel batch={batch} /> : <p className="input-invoice-usage-rules-empty">尚未创建本地批次。</p>}
              <div className="input-invoice-usage-oa-actions">
                {canCreateBatch ? (
                  <button
                    className="input-invoice-usage-button input-invoice-usage-button--primary"
                    disabled={Boolean(actionLoading)}
                    onClick={handleCreateBatch}
                    type="button"
                  >
                    {actionLoading === "createBatch" ? "创建批次中..." : "创建本地批次"}
                  </button>
                ) : null}
                {canCreateDraft ? (
                  <button
                    className="input-invoice-usage-button input-invoice-usage-button--primary"
                    disabled={Boolean(actionLoading)}
                    onClick={handleCreateDraft}
                    type="button"
                  >
                    {actionLoading === "createDraft" ? "创建草稿中..." : "创建 OA 草稿"}
                  </button>
                ) : null}
                {batch?.oaDraftUrl ? (
                  <a className="input-invoice-usage-button" href={batch.oaDraftUrl} rel="noreferrer" target="_blank">
                    打开 OA 草稿
                  </a>
                ) : null}
                {canConfirmSubmission ? (
                  <>
                    <button
                      className="input-invoice-usage-button input-invoice-usage-button--primary"
                      disabled={Boolean(actionLoading)}
                      onClick={() => handleSubmissionDecision("submitted")}
                      type="button"
                    >
                      {actionLoading === "submissionDecision:submitted" ? "记录中..." : "我已在 OA 提交"}
                    </button>
                    <button
                      className="input-invoice-usage-button"
                      disabled={Boolean(actionLoading)}
                      onClick={() => handleSubmissionDecision("not_submitted")}
                      type="button"
                    >
                      {actionLoading === "submissionDecision:not_submitted" ? "记录中..." : "暂未提交 OA"}
                    </button>
                  </>
                ) : null}
                {canRefreshStatus ? (
                  <button
                    className="input-invoice-usage-button"
                    disabled={Boolean(actionLoading)}
                    onClick={handleRefreshStatus}
                    type="button"
                  >
                    {actionLoading === "refreshStatus" ? "刷新中..." : "刷新 OA 状态"}
                  </button>
                ) : null}
              </div>
              {canRevoke ? (
                <div className="input-invoice-usage-oa-form">
                  <label className="input-invoice-usage-rules-field">
                    <span>撤销原因</span>
                    <input onChange={(event) => setRevokeReason(event.target.value)} value={revokeReason} />
                  </label>
                  <button
                    className="input-invoice-usage-button"
                    disabled={Boolean(actionLoading) || !revokeReason.trim()}
                    onClick={handleRevokeDraft}
                    type="button"
                  >
                    {actionLoading === "revokeDraft" ? "撤销中..." : "撤销本地草稿绑定"}
                  </button>
                </div>
              ) : null}
              {canManualFallback ? (
                <div className="input-invoice-usage-oa-form">
                  <label className="input-invoice-usage-rules-field">
                    <span>人工处理原因</span>
                    <input onChange={(event) => setManualReason(event.target.value)} value={manualReason} />
                  </label>
                  <div className="input-invoice-usage-oa-actions">
                    <button
                      className="input-invoice-usage-button"
                      disabled={Boolean(actionLoading) || !manualReason.trim()}
                      onClick={() => handleManualStatus("submitted")}
                      type="button"
                    >
                      标记已进入 OA
                    </button>
                    <button
                      className="input-invoice-usage-button"
                      disabled={Boolean(actionLoading) || !manualReason.trim()}
                      onClick={() => handleManualStatus("not_submitted")}
                      type="button"
                    >
                      标记未进入 OA
                    </button>
                  </div>
                </div>
              ) : null}
            </Section>
          </>
        ) : null}
      </div>
    </AppDrawer>
  );
}

function rejectedInvoices(preview: OaReversePreviewPayload) {
  const byId = new Map<string, OaReverseRejectedInvoice>();
  for (const group of preview.groups) {
    for (const item of group.rejectedInvoices ?? []) {
      byId.set(item.invoiceId, item);
    }
  }
  return Array.from(byId.values());
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

function isManualFallbackStatus(status?: string | null, detectionStatus?: string | null) {
  const batchStatuses = new Set(["oa_detection_missing", "oa_detection_conflict", "oa_detection_unavailable"]);
  const detectionStatuses = new Set(["missing", "conflict", "unavailable"]);
  return batchStatuses.has(String(status || "")) || detectionStatuses.has(String(detectionStatus || ""));
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

function BatchStatusPanel({ batch }: { batch: InputInvoiceUsageOaReverseBatch }) {
  return (
    <article className="input-invoice-usage-oa-batch">
      <div className="input-invoice-usage-oa-group">
        <strong>{batch.batchId}</strong>
        <span className="input-invoice-usage-rules-tag">版本 {batch.version}</span>
        <span className="input-invoice-usage-rules-tag">{batch.status || "未知状态"}</span>
        {batch.idempotentReplay ? <span className="input-invoice-usage-rules-tag">幂等重放</span> : null}
      </div>
      <p>合计 {batch.totalWithTax || "-"}，目标申请人 {batch.targetApplicantName || batch.targetApplicantCode || "-"}</p>
      {batch.oaDraftId ? <p>OA 草稿 ID：{batch.oaDraftId}</p> : null}
      {batch.oaDetectionStatus ? <p>OA 检测状态：{batch.oaDetectionStatus}</p> : null}
      {batch.nextRunAt ? <p>下次检测：{batch.nextRunAt}</p> : null}
    </article>
  );
}
