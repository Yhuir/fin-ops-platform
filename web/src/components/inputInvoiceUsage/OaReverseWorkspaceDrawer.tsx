import { Filter } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";

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
  displayNo?: string | null;
  sellerName?: string | null;
  issueDate?: string | null;
  totalWithTax?: string | null;
  paymentStatusLabel?: string | null;
  oaRelationStatus?: OaRelationStatus | string | null;
  reasonCode?: string | null;
  reason: string;
};

type OaRelationStatus = "linked" | "candidate" | "unlinked";
type OaRelationFilter = "all" | OaRelationStatus;

type OaReverseDisplayInvoice = InputInvoiceUsageOaReverseInvoice & {
  oaRelationStatus: OaRelationStatus;
  selectable: boolean;
  rejectedReason?: string | null;
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
  rejectedInvoices?: OaReverseRejectedInvoice[];
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
  const [oaRelationFilter, setOaRelationFilter] = useState<OaRelationFilter>("all");
  const [oaRelationFilterMenuOpen, setOaRelationFilterMenuOpen] = useState(false);
  const confirmationOpenRef = useRef(false);
  const targetApplicantLabelId = useId();
  const selectedInvoiceIdsKey = selectedInvoiceIds.join("\n");
  const normalizedSelectedInvoiceIds = useMemo(
    () => (selectedInvoiceIdsKey ? selectedInvoiceIdsKey.split("\n") : []),
    [selectedInvoiceIdsKey],
  );
  const request = useMemo(
    () => ({ sourceFilters, selectedInvoiceIds: normalizedSelectedInvoiceIds, targetApplicantCode }),
    [sourceFilters, normalizedSelectedInvoiceIds, targetApplicantCode],
  );

  useEffect(() => {
    confirmationOpenRef.current = confirmationOpen;
  }, [confirmationOpen]);

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
      setOaRelationFilter("all");
      setOaRelationFilterMenuOpen(false);
      return undefined;
    }

    let active = true;
    setLoading(true);
    setError(null);
    loadPreview(request)
      .then((payload) => {
        if (active) {
          setPreview(payload);
          if (!confirmationOpenRef.current) {
            setBatch(null);
            setFeedback(null);
          }
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
  const selectableCandidateInvoices = useMemo(() => candidateInvoices.filter((invoice) => invoice.selectable), [candidateInvoices]);
  const visibleCandidateInvoices = useMemo(
    () => candidateInvoices.filter((invoice) => oaRelationFilter === "all" || invoice.oaRelationStatus === oaRelationFilter),
    [candidateInvoices, oaRelationFilter],
  );
  const candidateIdsKey = selectableCandidateInvoices.map((invoice) => invoice.invoiceId).join("\n");
  useEffect(() => {
    setSelectedCandidateIds(selectableCandidateInvoices.map((invoice) => invoice.invoiceId));
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
        const refreshedCandidateIds = invoicesFromPreview(refreshedPreview)
          .filter((invoice) => invoice.selectable)
          .map((invoice) => invoice.invoiceId);
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
                        onClick={() => setSelectedCandidateIds(selectableCandidateInvoices.map((invoice) => invoice.invoiceId))}
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
                          <th scope="col">
                            <div className="input-invoice-usage-oa-filter-header">
                              <span>OA 关联</span>
                              <div className="input-invoice-usage-oa-filter-menu">
                                <button
                                  aria-expanded={oaRelationFilterMenuOpen}
                                  aria-haspopup="menu"
                                  aria-label="筛选 OA 关联状态"
                                  className="input-invoice-usage-oa-filter-trigger"
                                  onClick={() => setOaRelationFilterMenuOpen((current) => !current)}
                                  type="button"
                                >
                                  <Filter aria-hidden="true" size={14} />
                                  <span>{oaRelationFilterLabel(oaRelationFilter)}</span>
                                </button>
                                {oaRelationFilterMenuOpen ? (
                                  <div className="input-invoice-usage-oa-filter-panel" role="menu">
                                    {OA_RELATION_FILTER_OPTIONS.map((option) => (
                                      <button
                                        aria-checked={oaRelationFilter === option.value}
                                        className="input-invoice-usage-oa-filter-item"
                                        key={option.value}
                                        onClick={() => {
                                          setOaRelationFilter(option.value);
                                          setOaRelationFilterMenuOpen(false);
                                        }}
                                        role="menuitemradio"
                                        type="button"
                                      >
                                        <span aria-hidden="true" className="input-invoice-usage-oa-filter-mark">
                                          {oaRelationFilter === option.value ? "●" : ""}
                                        </span>
                                        <span>{option.label}</span>
                                      </button>
                                    ))}
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          </th>
                          <th scope="col">状态</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleCandidateInvoices.map((invoice) => (
                          <tr key={invoice.invoiceId}>
                            <td className="input-invoice-usage-oa-table__select">
                              <input
                                aria-label={
                                  invoice.selectable
                                    ? `选择候选发票 ${invoice.displayNo || invoice.invoiceNumber || invoice.invoiceId}`
                                    : `${oaRelationDisabledLabel(invoice.oaRelationStatus)} ${invoice.displayNo || invoice.invoiceNumber || invoice.invoiceId} 不可选择`
                                }
                                checked={selectedCandidateIdSet.has(invoice.invoiceId)}
                                disabled={!invoice.selectable}
                                onChange={(event) => {
                                  setSelectedCandidateIds((current) => {
                                    if (!invoice.selectable) {
                                      return current;
                                    }
                                    const next = new Set(current);
                                    if (event.target.checked) {
                                      next.add(invoice.invoiceId);
                                    } else {
                                      next.delete(invoice.invoiceId);
                                    }
                                    return selectableCandidateInvoices
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
                            <td>
                              <span className={oaRelationChipClassName(invoice.oaRelationStatus)}>
                                {oaRelationChipLabel(invoice.oaRelationStatus)}
                              </span>
                            </td>
                            <td>{invoice.paymentStatusLabel || "候选"}</td>
                          </tr>
                        ))}
                        {visibleCandidateInvoices.length === 0 ? (
                          <tr>
                            <td colSpan={7}>当前筛选下暂无发票。</td>
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

const OA_RELATION_FILTER_OPTIONS: Array<{ value: OaRelationFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "linked", label: "已经关联oa" },
  { value: "candidate", label: "候选oa" },
  { value: "unlinked", label: "未关联oa" },
];

function oaRelationFilterLabel(value: OaRelationFilter) {
  return OA_RELATION_FILTER_OPTIONS.find((option) => option.value === value)?.label ?? "全部";
}

function oaRelationChipLabel(value: OaRelationStatus) {
  if (value === "linked") {
    return "已关联oa";
  }
  if (value === "candidate") {
    return "候选oa";
  }
  return "未关联oa";
}

function oaRelationChipClassName(value: OaRelationStatus) {
  if (value === "linked") {
    return "input-invoice-usage-rules-tag input-invoice-usage-rules-tag--warning";
  }
  if (value === "candidate") {
    return "input-invoice-usage-rules-tag input-invoice-usage-rules-tag--info";
  }
  return "input-invoice-usage-rules-tag input-invoice-usage-rules-tag--success";
}

function oaRelationDisabledLabel(value: OaRelationStatus) {
  return value === "candidate" ? "候选 OA 发票" : "已关联 OA 发票";
}

function normalizeOaRelationStatus(value: unknown): OaRelationStatus {
  return value === "linked" || value === "candidate" ? value : "unlinked";
}

function invoicesFromPreview(preview: OaReversePreviewPayload) {
  const byId = new Map<string, OaReverseDisplayInvoice>();
  const putSelectable = (invoice: InputInvoiceUsageOaReverseInvoice) => {
    const relationStatus = normalizeOaRelationStatus(invoice.oaRelationStatus);
    byId.set(invoice.invoiceId, {
      ...invoice,
      oaRelationStatus: relationStatus,
      selectable: relationStatus === "unlinked",
    });
  };
  const putNonSelectableRejected = (invoice: OaReverseRejectedInvoice, targetApplicantName?: string) => {
    const invoiceNumber = invoice.displayNo || invoice.invoiceNumber || invoice.invoiceId;
    const relationStatus = normalizeOaRelationStatus(
      invoice.oaRelationStatus || (invoice.reasonCode === "already_has_candidate_oa" ? "candidate" : "linked"),
    );
    byId.set(invoice.invoiceId, {
      invoiceId: invoice.invoiceId,
      invoiceNumber: String(invoice.invoiceNumber || invoiceNumber || ""),
      displayNo: String(invoice.displayNo || invoiceNumber || invoice.invoiceId),
      sellerName: String(invoice.sellerName || ""),
      issueDate: String(invoice.issueDate || ""),
      totalWithTax: String(invoice.totalWithTax || ""),
      paymentStatusLabel: String(invoice.paymentStatusLabel || "候选"),
      targetApplicantName,
      oaRelationStatus: relationStatus,
      selectable: false,
      rejectedReason: invoice.reason,
    });
  };
  for (const invoice of preview.candidateInvoices ?? []) {
    putSelectable(invoice);
  }
  for (const invoice of preview.invoiceRows ?? []) {
    putSelectable(invoice);
  }
  for (const invoice of preview.rejectedInvoices ?? []) {
    if (invoice.reasonCode === "already_has_active_oa" || invoice.reasonCode === "already_has_candidate_oa") {
      putNonSelectableRejected(invoice, preview.targetApplicantName);
    }
  }
  for (const group of preview.groups) {
    for (const invoice of group.invoiceRows ?? []) {
      putSelectable({
        ...invoice,
        targetApplicantName: invoice.targetApplicantName || group.targetApplicantName,
      });
    }
    for (const invoice of group.candidateInvoices ?? []) {
      putSelectable({
        ...invoice,
        targetApplicantName: invoice.targetApplicantName || group.targetApplicantName,
      });
    }
    for (const invoiceId of group.candidateInvoiceIds ?? []) {
      if (!byId.has(invoiceId)) {
        putSelectable({
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
    for (const invoice of group.rejectedInvoices ?? []) {
      if (invoice.reasonCode !== "already_has_active_oa" && invoice.reasonCode !== "already_has_candidate_oa") {
        continue;
      }
      putNonSelectableRejected(invoice, group.targetApplicantName);
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
