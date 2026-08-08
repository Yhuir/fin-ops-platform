import { Button, Checkbox, Chip, Input, ListBox, Select, Tabs } from "@heroui/react";
import { Filter, Search, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";

import AppDrawer from "../common/AppDrawer";
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
  InputInvoiceUsageOaReverseInvoice,
  InputInvoiceUsageOaReverseStagedDraftsResponse,
  InputInvoiceUsageOaReverseSubmittedHistoryResponse,
  InputInvoiceUsageOaReverseTargetApplicant,
  ManualInputInvoiceUsageOaReverseStatusRequest,
} from "../../features/inputInvoiceUsage/types";
import { formatMoney, normalizeMoneySearchQuery } from "../../features/money";

export type OaReversePreviewRequest = {
  sourceFilters: unknown[];
  selectedInvoiceIds: string[];
  targetApplicantCode?: string | null;
  signal?: AbortSignal;
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

type OaRelationStatus = "linked" | "unlinked";
type OaRelationFilter = "all" | "linked" | "unlinked";

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
  loadStagedDrafts?: () => Promise<InputInvoiceUsageOaReverseStagedDraftsResponse>;
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
  loadStagedDrafts,
  loadSubmittedHistory,
  manualStatus,
  onClose,
}: OaReverseWorkspaceDrawerProps) {
  const [preview, setPreview] = useState<OaReversePreviewPayload | null>(null);
  const [batch, setBatch] = useState<InputInvoiceUsageOaReverseBatch | null>(null);
  const [activeTab, setActiveTab] = useState<"pending" | "staged" | "submitted">("pending");
  const [stagedDrafts, setStagedDrafts] = useState<InputInvoiceUsageOaReverseStagedDraftsResponse["items"]>([]);
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
  const [oaRelationFilter, setOaRelationFilter] = useState<OaRelationFilter>("all");
  const [candidateSearch, setCandidateSearch] = useState("");
  const confirmationOpenRef = useRef(false);
  const previewRequestIdRef = useRef(0);
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
      setStagedDrafts([]);
      setStagedError(null);
      setStagedLoading(false);
      setSubmittedHistory([]);
      setHistoryError(null);
      setHistoryLoading(false);
      setSelectedCandidateIds([]);
      setTargetApplicantCode(null);
      setOaRelationFilter("all");
      setCandidateSearch("");
      return undefined;
    }

    let active = true;
    const requestId = previewRequestIdRef.current + 1;
    previewRequestIdRef.current = requestId;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    loadPreview({ ...request, signal: controller.signal })
      .then((payload) => {
        if (active && requestId === previewRequestIdRef.current) {
          setPreview(payload);
          if (!confirmationOpenRef.current) {
            setBatch(null);
            setFeedback(null);
          }
        }
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || isAbortError(reason)) {
          return;
        }
        if (active && requestId === previewRequestIdRef.current) {
          setError(reason instanceof Error ? reason.message : "反提 OA 预览加载失败");
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
  }, [loadPreview, open, request]);

  const candidateInvoices = useMemo(() => (preview ? invoicesFromPreview(preview) : []), [preview]);
  const selectableCandidateInvoices = useMemo(() => candidateInvoices.filter((invoice) => invoice.selectable), [candidateInvoices]);
  const normalizedCandidateSearch = useMemo(
    () => normalizeMoneySearchQuery(candidateSearch).toLowerCase(),
    [candidateSearch],
  );
  const visibleCandidateInvoices = useMemo(
    () => candidateInvoices.filter((invoice) => {
      const businessStatus = oaRelationBusinessStatus(invoice.oaRelationStatus);
      const relationMatches = oaRelationFilter === "all" || businessStatus === oaRelationFilter;
      return relationMatches && invoiceMatchesSearch(invoice, normalizedCandidateSearch);
    }),
    [candidateInvoices, normalizedCandidateSearch, oaRelationFilter],
  );
  const candidateIdsKey = selectableCandidateInvoices.map((invoice) => invoice.invoiceId).join("\n");
  useEffect(() => {
    setSelectedCandidateIds(selectableCandidateInvoices.map((invoice) => invoice.invoiceId));
  }, [candidateIdsKey]);
  const selectedCandidateIdSet = useMemo(() => new Set(selectedCandidateIds), [selectedCandidateIds]);
  const selectedCandidateInvoices = useMemo(
    () => selectableCandidateInvoices.filter((invoice) => selectedCandidateIdSet.has(invoice.invoiceId)),
    [selectableCandidateInvoices, selectedCandidateIdSet],
  );
  const selectedPayeeResolvable = selectedCandidateInvoices.length === selectedCandidateIds.length
    && selectedCandidateInvoices.length > 0
    && selectedCandidateInvoices.every((invoice) => Boolean(invoice.sellerName.trim()))
    && new Set(selectedCandidateInvoices.map((invoice) => invoice.sellerName.trim())).size === 1;
  const targetApplicants = preview?.targetApplicants ?? [];
  const selectedTargetApplicantCode = targetApplicantCode ?? preview?.targetApplicantCode ?? "";
  const canCreateDraft = Boolean(
    preview
    && createDraftFromSelection
    && preview.previewId
    && selectedPayeeResolvable
    && !batch?.oaDraftUrl
    && preview.permissions?.canCreateDraft === true,
  );
  const canConfirmSubmission = Boolean(batch && manualStatus && batch.oaDraftUrl && (batch.canConfirmSubmission ?? batch.status === "oa_draft_created"));
  const createDraftDisabled = Boolean(actionLoading) || !canCreateDraft;
  const headerNotices = useMemo(
    () => oaReverseHeaderNotices({
      error,
      feedback,
    }),
    [error, feedback],
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
        const currentCandidateIds = selectableCandidateInvoices.map((invoice) => invoice.invoiceId);
        const canUseCurrentPreview = selectedIds.length === currentCandidateIds.length
          && selectedIds.every((invoiceId, index) => invoiceId === currentCandidateIds[index]);
        const draftPreview = canUseCurrentPreview
          ? preview
          : await loadPreview({
            sourceFilters,
            selectedInvoiceIds: selectedIds,
            targetApplicantCode: resolvedTargetApplicantCode || null,
          });
        if (!canUseCurrentPreview) {
          setPreview(draftPreview);
          const refreshedCandidateIds = invoicesFromPreview(draftPreview)
            .filter((invoice) => invoice.selectable)
            .map((invoice) => invoice.invoiceId);
          setSelectedCandidateIds(refreshedCandidateIds);
          selectedIds.splice(0, selectedIds.length, ...refreshedCandidateIds);
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
      () => setConfirmationOpen(true),
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
      reason: decision === "submitted" ? "用户确认已在 OA 系统提交该草稿" : "用户确认 OA 提交内容需修改并删除本次提交内容",
    })
      .then((nextBatch) => {
        setConfirmationOpen(false);
        setStagedDrafts((current) => current.filter((item) => item.batchId !== targetBatch.batchId));
        if (decision === "submitted") {
          setBatch(nextBatch);
          setFeedback("已进入已提交历史。");
          setActiveTab("submitted");
          return;
        }
        setBatch(null);
        setFeedback("已清除暂存批次，返回待处理后可重新创建 OA 草稿。");
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
    loadStagedDrafts()
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
  }, [activeTab, loadStagedDrafts, open]);

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
        {headerNotices.length > 0 ? <OaReverseHeaderNotices notices={headerNotices} /> : null}
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
                      <span id={targetApplicantLabelId}>目标 OA 申请人</span>
                      <Select
                        aria-labelledby={targetApplicantLabelId}
                        className="input-invoice-usage-oa-select"
                        onSelectionChange={(key) => setTargetApplicantCode(String(key))}
                        selectedKey={selectedTargetApplicantCode}
                      >
                        <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
                        <Select.Popover>
                          <ListBox>
                            {targetApplicants.map((applicant) => (
                              <ListBox.Item id={applicant.code} key={applicant.code} textValue={applicant.name}>{applicant.name}</ListBox.Item>
                            ))}
                          </ListBox>
                        </Select.Popover>
                      </Select>
                    </div>
                  ) : (
                    <SummaryMetric label="目标 OA 申请人" value={preview.targetApplicantName ?? "-"} />
                  )}
                  <SummaryMetric label="候选发票数" value={String(preview.invoiceCount)} />
                  <SummaryMetric label="候选价税合计" value={formatMoney(preview.totalWithTax, "-")} />
                </div>
                <Section title="候选发票清单">
                  {candidateInvoices.length > 0 ? (
                    <div className="input-invoice-usage-oa-actions">
                      <Button
                        onPress={() => setSelectedCandidateIds(selectableCandidateInvoices.map((invoice) => invoice.invoiceId))}
                        size="sm"
                        variant="secondary"
                      >
                        全选候选
                      </Button>
                      <Button onPress={() => setSelectedCandidateIds([])} size="sm" variant="secondary">
                        清空选择
                      </Button>
                      <Chip color="default" size="sm" variant="soft">
                        <Chip.Label>已选 {selectedCandidateIds.length} 张</Chip.Label>
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
                      <label className="input-invoice-usage-rules-field input-invoice-usage-oa-search">
                        <span>搜索</span>
                        <span className="input-invoice-usage-oa-search-control">
                          <Search aria-hidden="true" size={14} />
                          <Input
                            aria-label="搜索候选发票"
                            onChange={(event) => setCandidateSearch(event.target.value)}
                            placeholder="发票号码、销方、金额"
                            type="search"
                            value={candidateSearch}
                          />
                        </span>
                      </label>
                    </div>
                  ) : null}
                  <FinanceTable ariaLabel="反提 OA 候选发票清单" className="input-invoice-usage-oa-table" minWidth={680}>
                    <FinanceTableHeader>
                      <FinanceTableColumn columnRole="selection">选择</FinanceTableColumn>
                      <FinanceTableColumn columnRole="identity" isRowHeader>发票号码</FinanceTableColumn>
                      <FinanceTableColumn columnRole="account">销方</FinanceTableColumn>
                      <FinanceTableColumn columnRole="amount">价税合计</FinanceTableColumn>
                      <FinanceTableColumn columnRole="status">
                            <div className="input-invoice-usage-oa-filter-header">
                              <span>OA 关联</span>
                              <div className="input-invoice-usage-oa-filter-menu">
                                <Select
                                  aria-label="筛选 OA 关联状态"
                                  className="input-invoice-usage-oa-filter-trigger"
                                  onSelectionChange={(key) => setOaRelationFilter(String(key) as OaRelationFilter)}
                                  selectedKey={oaRelationFilter}
                                >
                                  <Select.Trigger>
                                    <Filter aria-hidden="true" size={14} />
                                    <Select.Value />
                                    <Select.Indicator />
                                  </Select.Trigger>
                                  <Select.Popover>
                                    <ListBox>
                                      {OA_RELATION_FILTER_OPTIONS.map((option) => (
                                        <ListBox.Item id={option.value} key={option.value} textValue={option.label}>{option.label}</ListBox.Item>
                                      ))}
                                    </ListBox>
                                  </Select.Popover>
                                </Select>
                              </div>
                            </div>
                      </FinanceTableColumn>
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
                            textValue={`${invoiceNumber} ${invoice.issueDate} ${invoice.sellerName} ${invoice.totalWithTax} ${oaRelationChipLabel(invoice.oaRelationStatus)}`}
                          >
                            <FinanceTableCell columnRole="selection" className="input-invoice-usage-oa-table__select">
                              <Checkbox
                                aria-label={
                                  invoice.selectable
                                    ? `选择候选发票 ${invoiceNumber}`
                                    : `${oaRelationDisabledLabel(invoice.oaRelationStatus)} ${invoiceNumber} 不可选择`
                                }
                                isDisabled={!invoice.selectable}
                                isSelected={selectedCandidateIdSet.has(invoice.invoiceId)}
                                onChange={(selected) => {
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
                                    return selectableCandidateInvoices
                                      .map((candidate) => candidate.invoiceId)
                                      .filter((invoiceId) => next.has(invoiceId));
                                  });
                                }}
                              >
                                <Checkbox.Control>
                                  <Checkbox.Indicator />
                                </Checkbox.Control>
                              </Checkbox>
                            </FinanceTableCell>
                            <FinanceTableCell columnRole="identity" textValue={invoiceNumber}>
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
                            <FinanceTableCell columnRole="status" textValue={oaRelationChipLabel(invoice.oaRelationStatus)}>
                              <Chip
                                color={invoice.oaRelationStatus === "linked" ? "warning" : "success"}
                                size="sm"
                                variant="soft"
                              >
                                <Chip.Label>{oaRelationChipLabel(invoice.oaRelationStatus)}</Chip.Label>
                              </Chip>
                            </FinanceTableCell>
                          </FinanceTableRow>
                        );
                      })}
                    </FinanceTableBody>
                  </FinanceTable>
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
  );
}

const OA_RELATION_FILTER_OPTIONS: Array<{ value: OaRelationFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "linked", label: "已经关联oa" },
  { value: "unlinked", label: "未关联oa" },
];

function oaRelationChipLabel(value: OaRelationStatus) {
  if (value === "linked") {
    return "已关联oa";
  }
  return "未关联oa";
}

function oaRelationDisabledLabel(value: OaRelationStatus) {
  return value === "linked" ? "已关联 OA 发票" : "未关联 OA 发票";
}

function normalizeOaRelationStatus(value: unknown): OaRelationStatus {
  return value === "linked" ? value : "unlinked";
}

function oaRelationBusinessStatus(value: OaRelationStatus): OaRelationFilter {
  return value === "linked" ? "linked" : "unlinked";
}

function invoiceMatchesSearch(invoice: OaReverseDisplayInvoice, searchTerm: string) {
  if (!searchTerm) {
    return true;
  }
  const haystack = [
    invoice.invoiceId,
    invoice.invoiceNumber,
    invoice.displayNo,
    invoice.sellerName,
    invoice.issueDate,
    invoice.totalWithTax,
    invoice.targetApplicantName,
    invoice.paymentStatusLabel,
    invoice.rejectedReason,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return (/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(searchTerm) ? haystack.replace(/,/g, "") : haystack).includes(searchTerm);
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
      selectable: relationStatus === "unlinked",
    });
  };
  const putNonSelectableRejected = (invoice: OaReverseRejectedInvoice, targetApplicantName?: string) => {
    const invoiceNumber = invoice.displayNo || invoice.invoiceNumber || "未识别号码";
    const relationStatus = normalizeOaRelationStatus(invoice.oaRelationStatus || "linked");
    byId.set(invoice.invoiceId, {
      invoiceId: invoice.invoiceId,
      invoiceNumber: String(invoice.invoiceNumber || invoiceNumber || ""),
      displayNo: String(invoice.displayNo || invoiceNumber),
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
    if (invoice.reasonCode === "already_has_active_oa") {
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
    for (const invoice of group.rejectedInvoices ?? []) {
      if (invoice.reasonCode !== "already_has_active_oa") {
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
    <div className="input-invoice-usage-oa-confirmation-backdrop">
      <div aria-label="OA 草稿提交确认" aria-modal="true" className="input-invoice-usage-oa-confirmation" role="dialog">
        <div className="input-invoice-usage-oa-confirmation__header">
          <h3>OA 草稿提交确认</h3>
          <Button
            aria-label="关闭确认弹窗"
            className="input-invoice-usage-oa-confirmation__close"
            isDisabled={Boolean(actionLoading)}
            isIconOnly
            onPress={onCancel}
            size="sm"
            variant="tertiary"
          >
            <X aria-hidden="true" size={16} />
          </Button>
        </div>
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
      </div>
    </div>
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
}: {
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
      <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--error" role="alert">
        {error}
      </div>
    );
  }
  if (items.length === 0) {
    return <p className="input-invoice-usage-rules-empty">暂无暂存批次。</p>;
  }
  return (
    <div className="input-invoice-usage-oa-history">
      {items.map((item) => (
        <article className="input-invoice-usage-oa-history-item" key={item.batchId}>
          <div className="input-invoice-usage-oa-history-item__header">
            <strong>{item.targetApplicantName || "目标申请人"}</strong>
            <span className="input-invoice-usage-rules-tag">{item.invoiceIds.length || item.invoiceRows.length} 张</span>
            <span className="input-invoice-usage-rules-tag input-invoice-usage-oa-amount-tag">{formatMoney(item.totalWithTax, "-")}</span>
          </div>
          <div className="input-invoice-usage-rules-table-shell">
            <table aria-label={`${item.targetApplicantName || "目标申请人"}暂存发票`} className="input-invoice-usage-oa-table">
              <thead>
                <tr>
                  <th scope="col">发票号码</th>
                  <th scope="col">销方</th>
                  <th scope="col">开票日期</th>
                  <th scope="col">价税合计</th>
                </tr>
              </thead>
              <tbody>
                {item.invoiceRows.map((invoice) => (
                  <tr key={`${invoice.invoiceId}:${invoice.displayNo || invoice.invoiceNumber}`}>
                    <td>{invoice.displayNo || invoice.invoiceNumber || "未识别号码"}</td>
                    <td>{invoice.sellerName || "-"}</td>
                    <td>{invoice.issueDate || "-"}</td>
                    <td className="input-invoice-usage-oa-table__amount">{formatMoney(invoice.totalWithTax, "-")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="input-invoice-usage-oa-actions">
            <Button
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
            </Button>
            <Button
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
            </Button>
          </div>
        </article>
      ))}
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
                    <td className="input-invoice-usage-oa-table__amount">{formatMoney(invoice.totalWithTax, "-")}</td>
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
