import { Button, Checkbox, Chip, ListBox, Select, Tabs } from "@heroui/react";
import { X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";

import OaApplicantCredentialsDrawer from "./OaApplicantCredentialsDrawer";
import OaDraftPrefillDrawer from "../common/OaDraftPrefillDrawer";
import { useOaApplicantCredentials } from "../../features/inputInvoiceUsage/useOaApplicantCredentials";
import { applicantLabel } from "../../features/inputInvoiceUsage/oaApplicantCredentials";
import AppDrawer from "../common/AppDrawer";
import AppDialog from "../common/AppDialog";
import QuerySearch from "../common/QuerySearch";
import {
  EmptyValue,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
  TableCellStack,
} from "../common/FinanceTable";
import type {
  CreateInputInvoiceUsageOaReverseDraftFromSelectionRequest,
  InputInvoiceUsageOaReverseBatch,
  InputInvoiceUsageOaReversePreviewRequest,
  InputInvoiceUsageOaReverseInvoice,
  InputInvoiceUsageOaReverseStagedDraftsResponse,
  InputInvoiceUsageOaReverseSubmittedHistoryResponse,
  InputInvoiceUsageOaReverseTargetApplicant,
  ManualInputInvoiceUsageOaReverseStatusRequest,
} from "../../features/inputInvoiceUsage/types";
import { formatMoney } from "../../features/money";

export type OaReversePreviewRequest = Omit<InputInvoiceUsageOaReversePreviewRequest, "targetApplicantCode"> & {
  targetApplicantCode?: string | null;
  signal?: AbortSignal;
};

type OaReverseCandidateScope = Pick<InputInvoiceUsageOaReversePreviewRequest, "keyword" | "month" | "invoiceDateFrom" | "invoiceDateTo" | "filters">;
const EMPTY_CANDIDATE_SCOPE: OaReverseCandidateScope = {};

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

type OaRelationStatus = "linked" | "unlinked";

type OaReverseDisplayInvoice = InputInvoiceUsageOaReverseInvoice & {
  oaRelationStatus: OaRelationStatus;
  selectable: boolean;
  rejectedReason?: string | null;
};

export type OaReversePreviewPayload = {
  pagination?: { page: number; pageSize: number; total: number };
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
  canManageCredentials?: boolean;
  initialScope?: OaReverseCandidateScope;
  loadPreview: (request: OaReversePreviewRequest) => Promise<OaReversePreviewPayload>;
  createDraftFromSelection?: (request: CreateInputInvoiceUsageOaReverseDraftFromSelectionRequest) => Promise<InputInvoiceUsageOaReverseBatch>;
  loadStagedDrafts?: (limit?: number) => Promise<InputInvoiceUsageOaReverseStagedDraftsResponse>;
  loadSubmittedHistory?: () => Promise<InputInvoiceUsageOaReverseSubmittedHistoryResponse>;
  manualStatus?: (batchId: string, request: ManualInputInvoiceUsageOaReverseStatusRequest) => Promise<InputInvoiceUsageOaReverseBatch>;
  onClose: () => void;
  onChanged?: () => Promise<void> | void;
};

export default function OaReverseWorkspaceDrawer({
  open,
  canManageCredentials = false,
  initialScope = EMPTY_CANDIDATE_SCOPE,
  loadPreview,
  createDraftFromSelection,
  loadStagedDrafts,
  loadSubmittedHistory,
  manualStatus,
  onClose,
  onChanged,
}: OaReverseWorkspaceDrawerProps) {
  const [configuration, setConfiguration] = useState<"credentials" | "prefill" | null>(null);
  const [preview, setPreview] = useState<OaReversePreviewPayload | null>(null);
  const [batch, setBatch] = useState<InputInvoiceUsageOaReverseBatch | null>(null);
  const [activeTab, setActiveTab] = useState<"pending" | "staged" | "submitted">("pending");
  const [stagedDrafts, setStagedDrafts] = useState<InputInvoiceUsageOaReverseStagedDraftsResponse["items"]>([]);
  const [stagedLimit, setStagedLimit] = useState(50);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [stagedRefreshVersion, setStagedRefreshVersion] = useState(0);
  const [stagedLoading, setStagedLoading] = useState(false);
  const [stagedError, setStagedError] = useState<string | null>(null);
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
  const [scope, setScope] = useState(initialScope);
  const [candidateSearch, setCandidateSearch] = useState(initialScope.keyword ?? "");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState(initialScope.keyword ?? "");
  const [selectedMetadata, setSelectedMetadata] = useState<Record<string, InputInvoiceUsageOaReverseInvoice>>({});
  const previewRequestIdRef = useRef(0);
  const targetApplicantLabelId = useId();
  const request = useMemo(
    () => ({ ...scope, selectedInvoiceIds: [], targetApplicantCode, page, pageSize: 50, keyword }),
    [scope, targetApplicantCode, page, keyword],
  );

  useEffect(() => {
    if (!open) {
      setConfiguration(null);
      setPreview(null);
      setBatch(null);
      setLoading(false);
      setActionLoading(null);
      setError(null);
      setFeedback(null);
      setConfirmationOpen(false);
      setActiveTab("pending");
      setStagedLimit(50);
      setPreviewError(null);
      setStagedDrafts([]);
      setStagedError(null);
      setStagedLoading(false);
      setSubmittedHistory([]);
      setHistoryError(null);
      setHistoryLoading(false);
      setSelectedCandidateIds([]);
      setTargetApplicantCode(null);
      setScope(initialScope);
      setPage(1);
      setKeyword(initialScope.keyword ?? "");
      setSelectedMetadata({});
      setCandidateSearch(initialScope.keyword ?? "");
      return undefined;
    }

    let active = true;
    const requestId = previewRequestIdRef.current + 1;
    previewRequestIdRef.current = requestId;
    const controller = new AbortController();
    setLoading(true);
    setPreviewError(null);
    loadPreview({ ...request, signal: controller.signal })
      .then((payload) => {
        if (active && requestId === previewRequestIdRef.current) {
          setPreview(payload);
          setSelectedMetadata((current) => {
            const next = { ...current };
            for (const invoice of invoicesFromPreview(payload)) {
              if (invoice.invoiceId in next) next[invoice.invoiceId] = invoice;
            }
            return next;
          });
        }
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || isAbortError(reason)) {
          return;
        }
        if (active && requestId === previewRequestIdRef.current) {
          setPreview(null);
          setPreviewError(reason instanceof Error ? reason.message : "反提 OA 预览加载失败");
        }
      })
      .finally(() => {
        if (active && requestId === previewRequestIdRef.current) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [loadPreview, open, request, refreshVersion, initialScope]);

  const candidateInvoices = useMemo(() => (preview ? invoicesFromPreview(preview) : []), [preview]);
  const selectableCandidateInvoices = useMemo(() => candidateInvoices.filter((invoice) => invoice.selectable), [candidateInvoices]);
  const visibleCandidateInvoices = candidateInvoices;
  const selectedCandidateIdSet = useMemo(() => new Set(selectedCandidateIds), [selectedCandidateIds]);
  const selectedCandidateInvoices = useMemo(
    () => selectedCandidateIds.map((id) => selectedMetadata[id]).filter(Boolean),
    [selectedCandidateIds, selectedMetadata],
  );
  const hiddenSelectedCount = selectedCandidateIds.filter((id) => !candidateInvoices.some((invoice) => invoice.invoiceId === id)).length;
  const selectPage = () => {
    setSelectedCandidateIds((current) => [...new Set([...current, ...selectableCandidateInvoices.map((invoice) => invoice.invoiceId)])]);
    setSelectedMetadata((current) => ({ ...current, ...Object.fromEntries(selectableCandidateInvoices.map((invoice) => [invoice.invoiceId, invoice])) }));
  };
  const selectedPayeeResolvable = selectedCandidateInvoices.length === selectedCandidateIds.length
    && selectedCandidateInvoices.length > 0
    && selectedCandidateInvoices.every((invoice) => Boolean(invoice.sellerName.trim()) && !invoice.occupiedBatchId)
    && new Set(selectedCandidateInvoices.map((invoice) => invoice.sellerName.trim())).size === 1;
  const targetApplicants = preview?.targetApplicants ?? [];
  const selectedTargetApplicantCode = targetApplicantCode ?? preview?.targetApplicantCode ?? "";
  const credentials = useOaApplicantCredentials(open && configuration === "credentials" && canManageCredentials, (deletedCode) => {
    if (deletedCode && selectedTargetApplicantCode === deletedCode) setTargetApplicantCode("");
    setRefreshVersion(value => value + 1);
  }, () => { setConfiguration(null); setFeedback("凭据已保存"); });
  const canCreateDraft = Boolean(
    preview
    && createDraftFromSelection
    && preview.previewId
    && selectedPayeeResolvable
    && targetApplicants.some((applicant) => applicant.code === selectedTargetApplicantCode)
    && !batch?.oaDraftUrl
    && preview.permissions?.canCreateDraft === true,
  );
  const canConfirmSubmission = Boolean(batch && manualStatus && batch.oaDraftUrl && (batch.canConfirmSubmission ?? batch.status === "oa_draft_created"));
  const createDraftDisabled = loading || Boolean(actionLoading) || !canCreateDraft;
  const headerNotices = useMemo(
    () => oaReverseHeaderNotices({
      error: error ?? previewError,
      feedback,
    }),
    [error, previewError, feedback],
  );

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
        setRefreshVersion((current) => current + 1);
      })
      .finally(() => setActionLoading(null));
  };

  const handleCreateDraft = () => {
    if (!preview?.previewId || !createDraftFromSelection) {
      return;
    }
    const selectedIds = [...selectedCandidateIds];
    const resolvedTargetApplicantCode = selectedTargetApplicantCode;
    runBatchAction(
      "createDraft",
      async () => {
        const draftPreview = await loadPreview({
          selectedInvoiceIds: selectedIds,
          targetApplicantCode: resolvedTargetApplicantCode || null,
        });
        const checkedIds = new Set(invoicesFromPreview(draftPreview).filter((invoice) => invoice.selectable).map((invoice) => invoice.invoiceId));
        if (checkedIds.size !== selectedIds.length || selectedIds.some((id) => !checkedIds.has(id))) {
          const rejected = draftPreview.rejectedInvoices ?? [];
          throw new Error(rejected.length > 0
            ? rejected.map((invoice) => `${invoice.invoiceNumber || invoice.invoiceId}：${invoice.reason}`).join("；")
            : "所选发票的关联或占用状态已变化，请刷新并重新选择。");
        }
        if (
          !draftPreview.previewId
          || !draftPreview.previewHash
          || selectedIds.length === 0
          || draftPreview.permissions?.canCreateDraft !== true
          || draftPreview.canCreateDraft !== true
        ) {
          throw new Error(
            draftPreview.unavailableReason
              || draftPreview.warnings?.[0]
              || "当前选择没有可创建 OA 草稿的候选发票。",
          );
        }
        return createDraftFromSelection({
          previewId: draftPreview.previewId,
          expectedPreviewHash: draftPreview.previewHash,
          idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-draft"),
          selectedInvoiceIds: selectedIds,
          targetApplicantCode: draftPreview.targetApplicantCode || resolvedTargetApplicantCode,
        });
      },
      "OA 草稿已创建，请在 OA 页面处理后选择提交状态。",
      () => { setConfirmationOpen(true); setRefreshVersion((current) => current + 1); },
    );
  };

  const handleSubmissionDecision = (decision: "submitted" | "not_submitted", targetBatch = batch) => {
    if (!targetBatch || !manualStatus) {
      return;
    }
    setActionLoading(`submissionDecision:${decision}`);
    setError(null);
    setFeedback(null);
    manualStatus(targetBatch.batchId, {
      expectedVersion: targetBatch.version,
      idempotencyKey: createIdempotencyKey("input-invoice-usage-oa-reverse-submission-decision"),
      decision,
      reason: decision === "submitted"
        ? "用户确认已在 OA 系统提交该草稿"
        : targetBatch.draftRequestState === "unknown"
          ? "用户已到 OA 核实并删除可能存在的草稿，确认无有效 OA 单据，解除本地发票占用"
          : targetBatch.draftRequestState === "not_started"
            ? "用户取消尚未发起的 OA 草稿批次，解除本地发票占用"
            : "用户确认 OA 提交内容需修改并删除本次提交内容",
    })
      .then(async (nextBatch) => {
        setRefreshVersion((current) => current + 1);
        await onChanged?.();
        setConfirmationOpen(false);
        setStagedDrafts((current) => current.filter((item) => item.batchId !== targetBatch.batchId));
        if (decision === "submitted") {
          setBatch(nextBatch);
          setFeedback("已进入已提交历史。");
          setActiveTab("submitted");
          return;
        }
        setBatch(null);
        setFeedback("已解除本地暂存占用，返回候选后可重新选择发票。");
        setActiveTab("pending");
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "OA 提交状态确认失败。");
      })
      .finally(() => setActionLoading(null));
  };

  useEffect(() => {
    if (!open || activeTab !== "staged" || !loadStagedDrafts) {
      return undefined;
    }
    let active = true;
    setStagedLoading(true);
    setStagedError(null);
    loadStagedDrafts(stagedLimit)
      .then((payload) => {
        if (active) {
          setStagedDrafts(payload.items);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setStagedError(reason instanceof Error ? reason.message : "暂存批次加载失败。");
        }
      })
      .finally(() => {
        if (active) {
          setStagedLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [activeTab, loadStagedDrafts, open, stagedRefreshVersion, stagedLimit]);

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
    <>
    <AppDrawer
      className="input-invoice-usage-oa-drawer"
      closeLabel="关闭以发票反提 OA 工作流"
      onClose={() => { if (configuration === null) onClose(); }}
      closeDisabled={configuration !== null}
      isDismissable
      open={open}
      title="以发票反提 OA"
      width="min(920px, 100vw)"
    >
      <div aria-label="以发票反提 OA 工作流" className="input-invoice-usage-drawer-body">
        <div className="oa-reverse-settings-actions">
          {canManageCredentials ? <Button variant="secondary" size="sm" onPress={() => setConfiguration("credentials")}>OA 申请人凭据</Button> : null}
          <Button variant="secondary" size="sm" onPress={() => setConfiguration("prefill")}>OA 草稿预填管理</Button>
        </div>
        {headerNotices.length > 0 ? <OaReverseHeaderNotices notices={headerNotices} /> : null}
        {error && activeTab === "pending" ? <Button size="sm" variant="secondary" onPress={() => setActiveTab("staged")}>查看暂存与异常</Button> : null}
        <Tabs
          onSelectionChange={(key) => {
            if (key === "pending" || key === "staged" || key === "submitted") {
              setActiveTab(key);
            }
          }}
          selectedKey={activeTab}
        >
          <Tabs.List aria-label="反提 OA 状态" className="input-invoice-usage-oa-tabs">
            <Tabs.Tab className="input-invoice-usage-oa-tab" id="pending">待处理</Tabs.Tab>
            <Tabs.Tab className="input-invoice-usage-oa-tab" id="staged">暂存</Tabs.Tab>
            <Tabs.Tab className="input-invoice-usage-oa-tab" id="submitted">已提交</Tabs.Tab>
          </Tabs.List>
        </Tabs>
        {activeTab === "submitted" ? (
          <SubmittedHistoryPanel
            error={historyError}
            items={submittedHistory}
            loading={historyLoading}
          />
        ) : activeTab === "staged" ? (
          <StagedDraftsPanel
            actionLoading={actionLoading}
            error={stagedError}
            items={stagedDrafts}
            loading={stagedLoading}
            onDecision={handleSubmissionDecision}
            canManage={Boolean(manualStatus && preview?.permissions?.canCreateDraft === true)}
            onRefresh={() => setStagedRefreshVersion((current) => current + 1)}
            hasMore={stagedDrafts.length === stagedLimit}
            onLoadMore={() => setStagedLimit((current) => current + 50)}
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
                <div className="input-invoice-usage-oa-summary-row">
                  {targetApplicants.length > 0 ? (
                    <div className="input-invoice-usage-rules-field input-invoice-usage-oa-target input-invoice-usage-oa-target-card">
                      <span id={targetApplicantLabelId}>反提 OA 申请人</span>
                      <Select
                        aria-labelledby={targetApplicantLabelId}
                        className="input-invoice-usage-oa-select"
                        onSelectionChange={(key) => setTargetApplicantCode(key === null ? "" : String(key))}
                        selectedKey={selectedTargetApplicantCode || null}
                      >
                        <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
                        <Select.Popover>
                          <ListBox>
                            {targetApplicants.map((applicant) => (
                              <ListBox.Item id={applicant.code} key={applicant.code} textValue={applicantLabel(applicant.name, applicant.remark)}>{applicantLabel(applicant.name, applicant.remark)}</ListBox.Item>
                            ))}
                          </ListBox>
                        </Select.Popover>
                      </Select>
                    </div>
                  ) : (
                    <SummaryMetric label="反提 OA 申请人" value={preview.targetApplicantName ?? "-"} />
                  )}
                  <SummaryMetric label="候选发票数" value={`${preview.invoiceCount} 张`} />
                  <SummaryMetric label="候选价税合计" value={formatMoney(preview.totalWithTax, "-")} />
                </div>
                <Section title="待使用发票">
                  {preview ? (
                    <div className="input-invoice-usage-oa-actions">
                      <Button
                        onPress={selectPage}
                        isDisabled={loading}
                        size="sm"
                        variant="secondary"
                      >
                        选择本页
                      </Button>
                      <Button onPress={() => { setSelectedCandidateIds([]); setSelectedMetadata({}); }} size="sm" variant="secondary">
                        清空选择
                      </Button>
                      <Chip color="default" size="sm" variant="soft">
                        <Chip.Label>已选 {selectedCandidateIds.length} 张{hiddenSelectedCount > 0 ? `（其中 ${hiddenSelectedCount} 张不在本页）` : ""}</Chip.Label>
                      </Chip>
                      <Button
                        isDisabled={createDraftDisabled}
                        isPending={actionLoading === "createDraft"}
                        onPress={handleCreateDraft}
                        size="sm"
                        variant="primary"
                      >
                        {actionLoading === "createDraft" ? "创建草稿中..." : "创建 OA 草稿"}
                      </Button>
                      <QuerySearch ariaLabel="搜索候选发票" className="input-invoice-usage-oa-search" value={candidateSearch} onChange={setCandidateSearch} onSubmit={() => { setKeyword(candidateSearch); setPage(1); }} onClear={() => { setCandidateSearch(""); setKeyword(""); setPage(1); }} placeholder="发票号码、销方、金额" />
                    </div>
                  ) : null}
                  <FinanceTable ariaLabel="反提 OA 候选发票清单" className="input-invoice-usage-oa-table" minWidth={680}>
                    <FinanceTableHeader>
                      <FinanceTableColumn columnRole="selection">选择</FinanceTableColumn>
                      <FinanceTableColumn columnRole="identity" isRowHeader className="input-invoice-usage-oa-table__number">发票号码</FinanceTableColumn>
                      <FinanceTableColumn columnRole="account">销方</FinanceTableColumn>
                      <FinanceTableColumn columnRole="amount">价税合计</FinanceTableColumn>
                      <FinanceTableColumn columnRole="status">可选状态</FinanceTableColumn>
                    </FinanceTableHeader>
                    <FinanceTableBody>
                      {visibleCandidateInvoices.length === 0 ? (
                        <FinanceTableRow id="oa-reverse-empty" textValue="当前筛选下暂无发票">
                          <FinanceTableCell columnRole="selection"><EmptyValue /></FinanceTableCell>
                          <FinanceTableCell columnRole="identity">当前筛选下暂无发票。</FinanceTableCell>
                          <FinanceTableCell columnRole="account"><EmptyValue /></FinanceTableCell>
                          <FinanceTableCell columnRole="amount"><EmptyValue /></FinanceTableCell>
                          <FinanceTableCell columnRole="status"><EmptyValue /></FinanceTableCell>
                        </FinanceTableRow>
                      ) : null}
                      {visibleCandidateInvoices.map((invoice) => {
                        const invoiceNumber = invoice.displayNo || invoice.invoiceNumber || "未识别号码";
                        return (
                          <FinanceTableRow
                            id={invoice.invoiceId}
                            key={invoice.invoiceId}
                            textValue={`${invoiceNumber} ${invoice.issueDate} ${invoice.sellerName} ${invoice.totalWithTax} ${candidateStatusLabel(invoice)}`}
                          >
                            <FinanceTableCell columnRole="selection" className="input-invoice-usage-oa-table__select">
                              <Checkbox
                                aria-label={
                                  invoice.selectable
                                    ? `选择候选发票 ${invoiceNumber}`
                                    : `${invoice.occupiedBatchId ? "暂存或提交中的发票" : oaRelationDisabledLabel(invoice.oaRelationStatus)} ${invoiceNumber} 不可选择`
                                }
                                isDisabled={loading || !invoice.selectable}
                                isSelected={selectedCandidateIdSet.has(invoice.invoiceId)}
                                onChange={(selected) => {
                                  setSelectedMetadata((current) => ({ ...current, [invoice.invoiceId]: invoice }));
                                  setSelectedCandidateIds((current) => {
                                    if (!invoice.selectable) {
                                      return current;
                                    }
                                    const next = new Set(current);
                                    if (selected) {
                                      next.add(invoice.invoiceId);
                                    } else {
                                      next.delete(invoice.invoiceId);
                                    }
                                    return [...next];
                                  });
                                }}
                              >
                                <Checkbox.Control>
                                  <Checkbox.Indicator />
                                </Checkbox.Control>
                              </Checkbox>
                            </FinanceTableCell>
                            <FinanceTableCell columnRole="identity" className="input-invoice-usage-oa-table__number" textValue={invoiceNumber}>
                              <TableCellStack
                                className="input-invoice-usage-oa-table__invoice"
                                primary={invoiceNumber}
                                secondary={invoice.issueDate ? (
                                  <Chip className="input-invoice-usage-oa-table__date" color="default" size="sm" variant="soft">
                                    <Chip.Label>{invoice.issueDate}</Chip.Label>
                                  </Chip>
                                ) : undefined}
                              />
                            </FinanceTableCell>
                            <FinanceTableCell columnRole="account" textValue={invoice.sellerName || "-"}>
                              {invoice.sellerName || <EmptyValue />}
                            </FinanceTableCell>
                            <FinanceTableCell columnRole="amount" className="input-invoice-usage-oa-table__amount" textValue={invoice.totalWithTax}>
                              {formatMoney(invoice.totalWithTax, "-")}
                            </FinanceTableCell>
                            <FinanceTableCell columnRole="status" textValue={candidateStatusLabel(invoice)}>
                              <Chip
                                color="default"
                                size="sm"
                                variant="soft"
                              >
                                <Chip.Label>{candidateStatusLabel(invoice)}</Chip.Label>
                              </Chip>
                            </FinanceTableCell>
                          </FinanceTableRow>
                        );
                      })}
                    </FinanceTableBody>
                  </FinanceTable>
                  <div className="input-invoice-usage-oa-actions">
                    <Button size="sm" variant="secondary" isDisabled={loading || page <= 1} onPress={() => setPage((current) => current - 1)}>上一页</Button>
                    <span>第 {page} 页 · 当前筛选 {preview.invoiceCount} 张</span>
                    <Button size="sm" variant="secondary" isDisabled={loading || page * 50 >= preview.invoiceCount} onPress={() => setPage((current) => current + 1)}>下一页</Button>
                    {selectedCandidateIds.length > 0 && !selectedPayeeResolvable ? <span>请选择同一销方的发票创建 OA 草稿。</span> : null}
                    {targetApplicants.length === 0 ? <span>{canManageCredentials ? "暂无可用申请人" : "暂无可用申请人，请联系管理员"}</span> : null}
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
            onCancel={() => {
              if (batch) {
                setStagedDrafts((current) => upsertStagedDraft(current, batch));
              }
              setConfirmationOpen(false);
              setBatch(null);
              setActiveTab("staged");
            }}
            onDecision={handleSubmissionDecision}
          />
        ) : null}
      </div>
    </AppDrawer>
    <OaApplicantCredentialsDrawer {...credentials} open={open && configuration === "credentials" && canManageCredentials} onClose={() => setConfiguration(null)} />
    <OaDraftPrefillDrawer family="input-invoice-usage" onSaved={() => setFeedback("OA 草稿预填已保存")} open={open && configuration === "prefill"} onClose={() => setConfiguration(null)} />
    </>
  );
}

function candidateStatusLabel(invoice: OaReverseDisplayInvoice) {
  return invoice.occupiedBatchId ? "已占用" : invoice.selectable ? "可选择" : "不可选择";
}
function oaRelationDisabledLabel(value: OaRelationStatus) {
  return value === "linked" ? "已关联 OA 发票" : "不可用发票";
}
function normalizeOaRelationStatus(value: unknown): OaRelationStatus {
  return value === "linked" ? value : "unlinked";
}

type OaReverseHeaderNotice = {
  tone: "error" | "info" | "success";
  text: string;
};

function oaReverseHeaderNotices({
  error,
  feedback,
}: {
  error: string | null;
  feedback: string | null;
}) {
  const notices: OaReverseHeaderNotice[] = [];
  if (error) {
    notices.push({ tone: "error", text: error });
  }
  if (feedback) {
    notices.push({ tone: "success", text: feedback });
  }
  return notices;
}

function OaReverseHeaderNotices({ notices }: { notices: OaReverseHeaderNotice[] }) {
  return (
    <div aria-label="以发票反提 OA 提示" className="input-invoice-usage-oa-header-notices">
      {notices.map((notice, index) => (
        <span
          className={`input-invoice-usage-oa-header-notice input-invoice-usage-oa-header-notice--${notice.tone}`}
          key={`${notice.tone}:${notice.text}:${index}`}
          role={notice.tone === "error" ? "alert" : "status"}
          title={notice.text}
        >
          {notice.text}
        </span>
      ))}
    </div>
  );
}

function invoicesFromPreview(preview: OaReversePreviewPayload) {
  const byId = new Map<string, OaReverseDisplayInvoice>();
  const putSelectable = (invoice: InputInvoiceUsageOaReverseInvoice) => {
    const relationStatus = normalizeOaRelationStatus(invoice.oaRelationStatus);
    byId.set(invoice.invoiceId, {
      ...invoice,
      oaRelationStatus: relationStatus,
      selectable: relationStatus === "unlinked" && invoice.bankRelationStatus !== "linked" && !invoice.occupiedBatchId,
    });
  };
  for (const invoice of preview.candidateInvoices ?? []) {
    putSelectable(invoice);
  }
  for (const invoice of preview.invoiceRows ?? []) {
    putSelectable(invoice);
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
  }
  return Array.from(byId.values());
}

function upsertStagedDraft(
  current: InputInvoiceUsageOaReverseStagedDraftsResponse["items"],
  batch: InputInvoiceUsageOaReverseBatch,
) {
  return [batch, ...current.filter((item) => item.batchId !== batch.batchId)];
}

function createIdempotencyKey(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}:${crypto.randomUUID()}`;
  }
  return `${prefix}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
}

function isAbortError(reason: unknown) {
  return typeof DOMException !== "undefined" && reason instanceof DOMException
    ? reason.name === "AbortError"
    : reason instanceof Error && reason.name === "AbortError";
}

function formatSubmittedAt(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return "-";
  }
  const normalized = trimmed.replace(/\.(\d{3})\d+(?=Z|[+-]\d{2}:?\d{2}$)/, ".$1");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return trimmed;
  }
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")}`;
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

function DraftConfirmationDialog({
  actionLoading,
  draftUrl,
  onCancel,
  onDecision,
}: {
  actionLoading: string | null;
  draftUrl: string;
  onCancel: () => void;
  onDecision: (decision: "submitted" | "not_submitted") => void;
}) {
  return (
    <AppDialog
      className="input-invoice-usage-oa-confirmation"
      closeLabel="关闭确认弹窗"
      disableEscapeClose={Boolean(actionLoading)}
      isDismissable={!actionLoading}
      maxWidth="md"
      onClose={onCancel}
      open
      title="OA 草稿提交确认"
    >
      <div className="input-invoice-usage-oa-actions">
          <a className="input-invoice-usage-button" href={draftUrl} rel="noreferrer" target="_blank">
            打开 OA 草稿
          </a>
          <Button
            className="input-invoice-usage-button input-invoice-usage-button--primary"
            isDisabled={Boolean(actionLoading)}
            isPending={actionLoading === "submissionDecision:submitted"}
            onPress={() => onDecision("submitted")}
            size="sm"
            variant="primary"
          >
            {actionLoading === "submissionDecision:submitted" ? "记录中..." : (
              <DecisionLabel
                primary="我已在OA系统提交该草稿"
                secondary="OA正在进行中"
              />
            )}
          </Button>
          <Button
            className="input-invoice-usage-button"
            isDisabled={Boolean(actionLoading)}
            isPending={actionLoading === "submissionDecision:not_submitted"}
            onPress={() => onDecision("not_submitted")}
            size="sm"
            variant="secondary"
          >
            {actionLoading === "submissionDecision:not_submitted" ? "清除中..." : (
              <DecisionLabel
                primary="OA提交内容需修改"
                secondary="删除本次提交内容"
              />
            )}
          </Button>
      </div>
    </AppDialog>
  );
}

function DecisionLabel({ primary, secondary }: { primary: string; secondary: string }) {
  return (
    <span className="input-invoice-usage-oa-decision-label">
      <span>{primary}</span>
      <span>{secondary}</span>
    </span>
  );
}

function StagedDraftsPanel({
  actionLoading,
  error,
  items,
  loading,
  onDecision,
  onRefresh,
  hasMore,
  onLoadMore,
  canManage,
}: {
  canManage: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
  onRefresh: () => void;
  actionLoading: string | null;
  error: string | null;
  items: InputInvoiceUsageOaReverseStagedDraftsResponse["items"];
  loading: boolean;
  onDecision: (decision: "submitted" | "not_submitted", batch: InputInvoiceUsageOaReverseBatch) => void;
}) {
  if (loading) {
    return (
      <div className="input-invoice-usage-drawer-loading">
        <span aria-label="正在加载暂存批次" className="input-invoice-usage-drawer-spinner" role="progressbar" />
        <span>正在加载暂存批次</span>
      </div>
    );
  }
  if (error) {
    return (
      <><div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--error" role="alert">{error}</div>
      <Button size="sm" variant="secondary" onPress={onRefresh}>刷新暂存状态</Button></>
    );
  }
  if (items.length === 0) {
    return <><p className="input-invoice-usage-rules-empty">暂无暂存批次。</p><Button size="sm" variant="secondary" onPress={onRefresh}>刷新暂存状态</Button></>;
  }
  return (
    <div className="input-invoice-usage-oa-history">
      <Button size="sm" variant="secondary" isDisabled={Boolean(actionLoading)} onPress={onRefresh}>刷新暂存状态</Button>
      {items.map((item) => (
        <article className="input-invoice-usage-oa-history-item" key={item.batchId}>
          <div className="input-invoice-usage-oa-history-item__header">
            <strong>{item.targetApplicantName || "目标申请人"}</strong>
            <span className="input-invoice-usage-rules-tag">{item.invoiceIds.length || item.invoiceRows.length} 张</span>
            <span className="input-invoice-usage-rules-tag input-invoice-usage-oa-amount-tag">{formatMoney(item.totalWithTax, "-")}</span>
          </div>
          {item.draftRequestState === "requesting" ? <p role="status">OA 创建请求正在处理。请勿重复创建，稍后刷新暂存状态。</p> : null}
          {item.draftRequestState === "unknown" ? <div role="alert" className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--error">
            <p>创建结果不明。请先到 OA 核实；如存在草稿，请确认未提交并删除可能存在的草稿后再解除占用。</p>
            <p>这里只解除本地发票占用，不会删除 OA 中的草稿。已有有效 OA 单据时，请保留占用并完成 OA 同步与关联。</p>
            {item.oaDetectionError ? <p>{item.oaDetectionError}</p> : null}
          </div> : null}
          {item.draftRequestState === "not_started" ? <p>尚未发起 OA 创建，可取消本次暂存并解除发票占用。</p> : null}
          {item.status.startsWith("oa_detection_") || item.status === "oa_submission_detecting" ? <p>OA 提交结果尚待核实，请检查 OA 单据及同步结果。</p> : null}
          <div className="input-invoice-usage-rules-table-shell">
            <FinanceTable ariaLabel={`${item.targetApplicantName || "目标申请人"}暂存发票`} className="input-invoice-usage-oa-table" minWidth={620}>
              <FinanceTableHeader>
                <FinanceTableColumn id="number" isRowHeader columnRole="identity" className="input-invoice-usage-oa-table__number">发票号码</FinanceTableColumn>
                <FinanceTableColumn id="seller" columnRole="identity">销方</FinanceTableColumn>
                <FinanceTableColumn id="date" columnRole="date">开票日期</FinanceTableColumn>
                <FinanceTableColumn id="amount" columnRole="amount">价税合计</FinanceTableColumn>
              </FinanceTableHeader>
              <FinanceTableBody>
                {item.invoiceRows.map((invoice) => (
                  <FinanceTableRow id={`${invoice.invoiceId}:${invoice.displayNo || invoice.invoiceNumber}`} key={`${invoice.invoiceId}:${invoice.displayNo || invoice.invoiceNumber}`}>
                    <FinanceTableCell columnRole="identity" className="input-invoice-usage-oa-table__number">{invoice.displayNo || invoice.invoiceNumber || "未识别号码"}</FinanceTableCell>
                    <FinanceTableCell columnRole="identity">{invoice.sellerName || "-"}</FinanceTableCell>
                    <FinanceTableCell columnRole="date">{invoice.issueDate || "-"}</FinanceTableCell>
                    <FinanceTableCell className="input-invoice-usage-oa-table__amount" columnRole="amount">{formatMoney(invoice.totalWithTax, "-")}</FinanceTableCell>
                  </FinanceTableRow>
                ))}
              </FinanceTableBody>
            </FinanceTable>
          </div>
          <div className="input-invoice-usage-oa-actions">
            {canManage && item.canConfirmSubmission === true ? <Button
              className="input-invoice-usage-button input-invoice-usage-button--primary"
              isDisabled={Boolean(actionLoading)}
              isPending={actionLoading === "submissionDecision:submitted"}
              onPress={() => onDecision("submitted", item)}
              size="sm"
              variant="primary"
            >
              {actionLoading === "submissionDecision:submitted" ? "记录中..." : (
                <DecisionLabel
                  primary="我已在OA系统提交该草稿"
                  secondary="OA正在进行中"
                />
              )}
            </Button> : null}
            {canManage && item.canConfirmSubmission === true ? <Button
              className="input-invoice-usage-button"
              isDisabled={Boolean(actionLoading)}
              isPending={actionLoading === "submissionDecision:not_submitted"}
              onPress={() => onDecision("not_submitted", item)}
              size="sm"
              variant="secondary"
            >
              {actionLoading === "submissionDecision:not_submitted" ? "清除中..." : (
                <DecisionLabel
                  primary="OA提交内容需修改"
                  secondary="删除本次提交内容"
                />
              )}
            </Button> : null}
            {canManage && item.canRelease === true && item.canConfirmSubmission !== true ? <Button
              size="sm" variant="secondary" isDisabled={Boolean(actionLoading) || item.draftRequestState === "requesting"}
              isPending={actionLoading === "submissionDecision:not_submitted"}
              onPress={() => onDecision("not_submitted", item)}
            >{item.draftRequestState === "unknown" ? "已核实并清理 OA 草稿，解除本地占用" : "解除占用，返回候选"}</Button> : null}
          </div>
        </article>
      ))}
      {hasMore ? <Button size="sm" variant="secondary" onPress={onLoadMore}>加载更多暂存批次</Button> : null}
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
            <span>{formatSubmittedAt(item.submittedAt)}</span>
            <span className="input-invoice-usage-rules-tag">{item.invoiceCount} 张</span>
            <span className="input-invoice-usage-rules-tag input-invoice-usage-oa-amount-tag">{formatMoney(item.totalWithTax, "-")}</span>
          </div>
          <div className="input-invoice-usage-rules-table-shell">
            <FinanceTable ariaLabel={`${item.targetApplicantName || "目标申请人"}已提交发票`} className="input-invoice-usage-oa-table" minWidth={620}>
              <FinanceTableHeader>
                <FinanceTableColumn id="number" isRowHeader columnRole="identity" className="input-invoice-usage-oa-table__number">发票号码</FinanceTableColumn>
                <FinanceTableColumn id="seller" columnRole="identity">销方</FinanceTableColumn>
                <FinanceTableColumn id="date" columnRole="date">开票日期</FinanceTableColumn>
                <FinanceTableColumn id="amount" columnRole="amount">价税合计</FinanceTableColumn>
              </FinanceTableHeader>
              <FinanceTableBody>
                {item.invoices.map((invoice) => (
                  <FinanceTableRow id={`${invoice.invoiceNo}:${invoice.sellerName}:${invoice.invoiceDate}`} key={`${invoice.invoiceNo}:${invoice.sellerName}:${invoice.invoiceDate}`}>
                    <FinanceTableCell columnRole="identity" className="input-invoice-usage-oa-table__number">{invoice.invoiceNo || "-"}</FinanceTableCell>
                    <FinanceTableCell columnRole="identity">{invoice.sellerName || "-"}</FinanceTableCell>
                    <FinanceTableCell columnRole="date">{invoice.invoiceDate || "-"}</FinanceTableCell>
                    <FinanceTableCell className="input-invoice-usage-oa-table__amount" columnRole="amount">{formatMoney(invoice.totalWithTax, "-")}</FinanceTableCell>
                  </FinanceTableRow>
                ))}
              </FinanceTableBody>
            </FinanceTable>
          </div>
        </article>
      ))}
    </div>
  );
}
