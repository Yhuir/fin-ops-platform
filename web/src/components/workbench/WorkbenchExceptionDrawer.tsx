import {
  Button,
  Disclosure,
  DisclosureGroup,
  ToggleButton,
  ToggleButtonGroup,
} from "@heroui/react";
import type { Key } from "@heroui/react";
import { useEffect, useRef, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import { formatMoney } from "../../features/money";
import { summarizeWorkbenchRows } from "../../features/workbench/selectionModel";
import {
  WORKBENCH_AMOUNT_ANOMALY_CODES,
  WORKBENCH_AMOUNT_ANOMALY_LABELS,
  type WorkbenchAmountAnomalyCode,
  type WorkbenchExceptionCounts,
  type WorkbenchExceptionView,
  type WorkbenchRecord,
  type WorkbenchRecordType,
  type WorkbenchRelationGroup,
} from "../../features/workbench/types";
import RelationGroupGrid from "./RelationGroupGrid";
import WorkbenchAnomalyIndicator from "./WorkbenchAnomalyIndicator";

type WorkbenchExceptionDrawerProps = {
  open: boolean;
  bucket: "unpaired" | "paired";
  bucketCounts: Record<"unpaired" | "paired", number>;
  view: WorkbenchExceptionView;
  selectedExceptionCode: WorkbenchAmountAnomalyCode | null;
  exceptionCounts: WorkbenchExceptionCounts | null;
  contentGeneration: number;
  groups: WorkbenchRelationGroup[];
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  total: number;
  hasMore: boolean;
  canMutateData: boolean;
  onBucketChange: (bucket: "unpaired" | "paired") => void;
  onViewChange: (view: WorkbenchExceptionView) => void;
  onExceptionCodeChange: (code: WorkbenchAmountAnomalyCode) => void;
  onClose: () => void;
  onEnsureGroupDetail: (group: WorkbenchRelationGroup) => Promise<WorkbenchRelationGroup>;
  onInvoiceEntry: (row: WorkbenchRecord, group: WorkbenchRelationGroup) => void;
  onInvoiceAssignment: (row: WorkbenchRecord, group: WorkbenchRelationGroup) => void;
  onLoadMore: () => Promise<void> | void;
  onReviewAnomaly: (
    group: WorkbenchRelationGroup,
    decision: "accept_paired" | "keep_unpaired",
  ) => Promise<void> | void;
};

const PANE_IDS: WorkbenchRecordType[] = ["oa", "bank", "invoice"];
const PANE_LABELS: Record<WorkbenchRecordType, string> = {
  oa: "OA",
  bank: "流水",
  invoice: "发票",
};
const AMOUNT_RULE_FAMILIES: Array<{
  label: string;
  codes: WorkbenchAmountAnomalyCode[];
}> = [
  {
    label: "OA = 流水",
    codes: ["oa_bank_equal_invoice_more", "oa_bank_equal_invoice_less"],
  },
  {
    label: "OA = 发票",
    codes: ["oa_invoice_equal_bank_more", "oa_invoice_equal_bank_less"],
  },
  {
    label: "流水 = 发票",
    codes: ["bank_invoice_equal_oa_less", "bank_invoice_equal_oa_more"],
  },
  {
    label: "三项互异",
    codes: ["all_amounts_different"],
  },
];
const AMOUNT_RULE_SHORT_LABELS: Record<WorkbenchAmountAnomalyCode, string> = {
  oa_bank_equal_invoice_more: "票多",
  oa_bank_equal_invoice_less: "票少",
  oa_invoice_equal_bank_more: "付多",
  oa_invoice_equal_bank_less: "付少",
  bank_invoice_equal_oa_less: "OA 提少",
  bank_invoice_equal_oa_more: "OA 提多",
  all_amounts_different: "三项不一致",
};
const DRAWER_DETAIL_COLUMNS = "minmax(320px, 1fr) 1px minmax(320px, 1fr) 1px minmax(320px, 1fr)";
export default function WorkbenchExceptionDrawer({
  open,
  bucket,
  bucketCounts,
  view,
  selectedExceptionCode,
  exceptionCounts,
  contentGeneration,
  groups,
  loading,
  loadingMore,
  error,
  total,
  hasMore,
  canMutateData,
  onBucketChange,
  onViewChange,
  onExceptionCodeChange,
  onClose,
  onEnsureGroupDetail,
  onInvoiceEntry,
  onInvoiceAssignment,
  onLoadMore,
  onReviewAnomaly,
}: WorkbenchExceptionDrawerProps) {
  const [expandedKeys, setExpandedKeys] = useState<Set<Key>>(new Set());
  const [pendingGroupId, setPendingGroupId] = useState<string | null>(null);
  const [detailGroups, setDetailGroups] = useState<Record<string, WorkbenchRelationGroup>>({});
  const [detailLoadingIds, setDetailLoadingIds] = useState<Set<string>>(new Set());
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});
  const detailRequestsRef = useRef(new Set<string>());
  const detailGenerationRef = useRef(0);
  const bucketControlsRef = useRef<HTMLDivElement>(null);
  const visibleGroups = groups;

  useEffect(() => {
    detailGenerationRef.current += 1;
    detailRequestsRef.current.clear();
    setExpandedKeys(new Set());
    setDetailGroups({});
    setDetailLoadingIds(new Set());
    setDetailErrors({});
    setPendingGroupId(null);
  }, [bucket, contentGeneration, open, selectedExceptionCode, view]);

  useEffect(() => {
    expandedKeys.forEach((key) => {
      const groupId = String(key);
      const group = visibleGroups.find((candidate) => candidate.id === groupId);
      if (!group || detailGroups[groupId] || detailRequestsRef.current.has(groupId)) {
        return;
      }
      const requestGeneration = detailGenerationRef.current;
      detailRequestsRef.current.add(groupId);
      setDetailLoadingIds((current) => new Set(current).add(groupId));
      setDetailErrors((current) => {
        if (!(groupId in current)) {
          return current;
        }
        const next = { ...current };
        delete next[groupId];
        return next;
      });
      void onEnsureGroupDetail(group)
        .then((detailGroup) => {
          if (detailGenerationRef.current === requestGeneration) {
            setDetailGroups((current) => ({ ...current, [groupId]: detailGroup }));
          }
        })
        .catch((detailError: unknown) => {
          const aborted = detailError instanceof DOMException && detailError.name === "AbortError";
          if (!aborted && detailGenerationRef.current === requestGeneration) {
            setDetailErrors((current) => ({
              ...current,
              [groupId]: detailError instanceof Error ? detailError.message : "明细加载失败，请重试。",
            }));
          }
        })
        .finally(() => {
          detailRequestsRef.current.delete(groupId);
          if (detailGenerationRef.current === requestGeneration) {
            setDetailLoadingIds((current) => {
              const next = new Set(current);
              next.delete(groupId);
              return next;
            });
          }
        });
    });
  }, [detailGroups, expandedKeys, onEnsureGroupDetail, visibleGroups]);

  const runGroupAction = async (groupId: string, action: () => Promise<void> | void) => {
    const currentBucketControl = bucketControlsRef.current?.querySelector<HTMLElement>(
      '[role="radio"][aria-checked="true"]',
    );
    if (currentBucketControl?.isConnected) {
      currentBucketControl.focus();
    }
    setPendingGroupId(groupId);
    try {
      await action();
    } finally {
      setPendingGroupId((current) => current === groupId ? null : current);
    }
  };

  const bucketControls = (
    <div className="workbench-anomaly-drawer__bucket-controls" ref={bucketControlsRef}>
      <ToggleButtonGroup
        aria-label="异常状态"
        className="workbench-anomaly-drawer__bucket-segmented"
        disallowEmptySelection
        selectedKeys={new Set<Key>([bucket])}
        selectionMode="single"
        size="sm"
        onSelectionChange={(keys) => {
          const [next] = Array.from(keys);
          if (next === "unpaired" || next === "paired") {
            onBucketChange(next);
          }
        }}
      >
        <ToggleButton id="unpaired">未配对异常 {bucketCounts.unpaired}</ToggleButton>
        <ToggleButton id="paired">
          <ToggleButtonGroup.Separator />
          已配对异常 {bucketCounts.paired}
        </ToggleButton>
      </ToggleButtonGroup>
    </div>
  );

  return (
    <AppDrawer
      ariaBusy={loading}
      className="workbench-anomaly-drawer"
      headerActions={bucketControls}
      open={open}
      title="异常处理"
      width="min(1740px, 96vw)"
      onClose={onClose}
    >
      <div className="workbench-anomaly-drawer__filters">
        <div className="workbench-anomaly-drawer__view-row">
          <ToggleButtonGroup
            aria-label="异常类型"
            className="workbench-anomaly-drawer__view-segmented"
            disallowEmptySelection
            selectedKeys={new Set<Key>([view])}
            selectionMode="single"
            size="sm"
            onSelectionChange={(keys) => {
              const [next] = Array.from(keys);
              if (next === "amount" || next === "document_only") {
                onViewChange(next);
              }
            }}
          >
            <ToggleButton id="amount">金额异常 {exceptionCounts?.amountTotal ?? 0}</ToggleButton>
            <ToggleButton id="document_only">
              <ToggleButtonGroup.Separator />
              仅资料异常 {exceptionCounts?.documentOnly ?? 0}
            </ToggleButton>
          </ToggleButtonGroup>
          <span aria-live="polite" className="workbench-anomaly-drawer__count">
            {visibleGroups.length < total ? `显示 ${visibleGroups.length} / ${total}` : `共 ${total} 项`}
          </span>
        </div>
        {view === "amount" ? (
          <section aria-labelledby="amount-anomaly-category-title" className="workbench-anomaly-drawer__amount-section">
            <h3 className="workbench-anomaly-drawer__filter-heading" id="amount-anomaly-category-title">
              金额异常分类
            </h3>
            <ToggleButtonGroup
              aria-label="金额异常分类"
              className="workbench-anomaly-drawer__amount-filters"
              disallowEmptySelection
              selectedKeys={selectedExceptionCode ? new Set<Key>([selectedExceptionCode]) : new Set<Key>()}
              selectionMode="single"
              size="sm"
              onSelectionChange={(keys) => {
                const [next] = Array.from(keys);
                if (WORKBENCH_AMOUNT_ANOMALY_CODES.some((code) => code === next)) {
                  onExceptionCodeChange(next as WorkbenchAmountAnomalyCode);
                }
              }}
            >
              {AMOUNT_RULE_FAMILIES.map((family) => (
                <div className="workbench-anomaly-drawer__amount-family" key={family.label}>
                  <span className="workbench-anomaly-drawer__amount-family-heading">
                    {family.label}
                  </span>
                  <div className="workbench-anomaly-drawer__amount-family-options">
                    {family.codes.map((code) => {
                      const count = exceptionCounts?.byCode[code] ?? 0;
                      return (
                        <ToggleButton
                          aria-label={`${WORKBENCH_AMOUNT_ANOMALY_LABELS[code]} ${count}`}
                          id={code}
                          key={code}
                        >
                          <span aria-hidden="true">{AMOUNT_RULE_SHORT_LABELS[code]}</span>
                          <strong aria-hidden="true">{count}</strong>
                        </ToggleButton>
                      );
                    })}
                  </div>
                </div>
              ))}
            </ToggleButtonGroup>
          </section>
        ) : null}
      </div>

      <div className="workbench-anomaly-drawer__content">
        {error ? <div className="detail-state-panel error">{error}</div> : null}
        {loading ? <div className="detail-state-panel">正在加载异常关系…</div> : null}
        {!loading && !error && visibleGroups.length === 0 ? (
          <div className="detail-state-panel">
            {view === "document_only"
              ? "当前没有仅资料异常。"
              : selectedExceptionCode
                ? "当前分类没有金额异常。"
                : "当前没有金额异常。"}
          </div>
        ) : null}
        {!loading && visibleGroups.length > 0 ? (
          <DisclosureGroup
            className="workbench-anomaly-drawer__list"
            expandedKeys={expandedKeys}
            onExpandedChange={setExpandedKeys}
          >
            {visibleGroups.map((group) => {
              const expanded = expandedKeys.has(group.id);
              const detailGroup = expanded ? detailGroups[group.id] : null;
              return (
                <Disclosure
                  className="workbench-anomaly-drawer__group"
                  id={group.id}
                  key={`${contentGeneration}:${group.id}`}
                >
                  <Disclosure.Heading className="workbench-anomaly-drawer__heading">
                    <Button
                      aria-label={`${expanded ? "收起" : "展开"}异常明细`}
                      className="workbench-anomaly-drawer__trigger"
                      fullWidth
                      slot="trigger"
                      variant="tertiary"
                    >
                      <span className="workbench-anomaly-drawer__outline">
                        {PANE_IDS.map((paneId) => {
                          const summary = paneSummary(group, paneId);
                          return (
                            <span className="workbench-anomaly-drawer__pane-summary" key={paneId}>
                              <span className="workbench-anomaly-drawer__pane-label">
                                {PANE_LABELS[paneId]} · {summary.count}项
                              </span>
                              <strong>{summary.total}</strong>
                            </span>
                          );
                        })}
                        <Disclosure.Indicator className="workbench-anomaly-drawer__indicator" />
                      </span>
                    </Button>
                    {!expanded && group.workbenchAnomaly?.items.length ? (
                      <WorkbenchAnomalyIndicator
                        anomalies={group.workbenchAnomaly.items}
                        className="workbench-anomaly-indicator--drawer-summary"
                        confirmation={group.workbenchAnomaly.confirmation}
                        levelLabel="该关联组"
                      />
                    ) : null}
                  </Disclosure.Heading>
                  <Disclosure.Content>
                    <Disclosure.Body className="workbench-anomaly-drawer__details">
                      {detailLoadingIds.has(group.id) ? (
                        <div className="detail-state-panel">正在加载完整异常明细…</div>
                      ) : null}
                      {detailErrors[group.id] ? (
                        <div className="detail-state-panel error">{detailErrors[group.id]}</div>
                      ) : null}
                      {detailGroup ? (
                        <div className="workbench-anomaly-drawer__detail-grid">
                          <RelationGroupGrid
                            allowInvoiceEntryInReadOnly={canMutateData}
                            canMutateData={false}
                            getRowState={() => "idle"}
                            groups={[detailGroup]}
                            hidePaneHeaders
                            onOpenDetail={() => undefined}
                            onRowAction={(row, action, actionGroup) => {
                              if (action === "enter-invoice") {
                                onInvoiceEntry(row, actionGroup);
                              }
                              if (action === "assign-invoice-expense-items") {
                                onInvoiceAssignment(row, actionGroup);
                              }
                            }}
                            onSelectRow={() => undefined}
                            panes={PANE_IDS.map((paneId) => ({
                              id: paneId,
                              title: PANE_LABELS[paneId],
                              rows: detailGroup.rows[paneId],
                            }))}
                            readOnly
                            rowTemplateColumns={DRAWER_DETAIL_COLUMNS}
                            zoneId={detailGroup.groupType}
                          />
                        </div>
                      ) : null}
                      <ExceptionReviewPanel
                        bucket={bucket}
                        canMutateData={canMutateData}
                        group={group}
                        pending={pendingGroupId === group.id}
                        onAction={(action) => runGroupAction(group.id, action)}
                        onReviewAnomaly={onReviewAnomaly}
                      />
                    </Disclosure.Body>
                  </Disclosure.Content>
                </Disclosure>
              );
            })}
          </DisclosureGroup>
        ) : null}
        {!loading && visibleGroups.length > 0 && hasMore ? (
          <div className="workbench-anomaly-drawer__load-more">
            <Button
              isDisabled={loadingMore}
              isPending={loadingMore}
              size="sm"
              variant="secondary"
              onPress={onLoadMore}
            >
              加载更多异常
            </Button>
          </div>
        ) : null}
      </div>
    </AppDrawer>
  );
}

function ExceptionReviewPanel({
  canMutateData,
  bucket,
  group,
  pending,
  onAction,
  onReviewAnomaly,
}: Pick<
  WorkbenchExceptionDrawerProps,
  | "canMutateData"
  | "bucket"
  | "onReviewAnomaly"
> & {
  group: WorkbenchRelationGroup;
  pending: boolean;
  onAction: (action: () => Promise<void> | void) => void;
}) {
  const submit = (decision: "accept_paired" | "keep_unpaired") => () => (
    onReviewAnomaly(group, decision)
  );

  if (!canMutateData || !group.workbenchAnomaly) {
    return null;
  }

  return (
    <section aria-label="异常审阅" className="workbench-anomaly-drawer__review">
      <div className="workbench-anomaly-drawer__decision-buttons">
        {bucket === "paired" ? (
          <Button isDisabled={pending} isPending={pending} size="sm" variant="secondary"
            onPress={() => onAction(submit("keep_unpaired"))}>
            撤回到未配对
          </Button>
        ) : (
          <>
            <Button isDisabled={pending} isPending={pending} size="sm"
              variant="secondary" onPress={() => onAction(submit("keep_unpaired"))}>
              留在未配对
            </Button>
            <Button isDisabled={pending} isPending={pending} size="sm"
              variant="primary" onPress={() => onAction(submit("accept_paired"))}>
              接受异常并进入已配对
            </Button>
          </>
        )}
      </div>
    </section>
  );
}

function groupPaneRows(group: WorkbenchRelationGroup, paneId: WorkbenchRecordType) {
  return group.collapsedRows?.[paneId] ?? group.rows[paneId];
}

function allGroupRows(group: WorkbenchRelationGroup) {
  return PANE_IDS.flatMap((paneId) => groupPaneRows(group, paneId));
}

function paneSummary(group: WorkbenchRelationGroup, paneId: WorkbenchRecordType) {
  const rows = groupPaneRows(group, paneId);
  const count = group.rowCounts?.[paneId] ?? group.collapsedRowCounts?.[paneId] ?? rows.length;
  if (count === 0) {
    return { count, total: "—" };
  }
  const amountCheckTotal = paneId === "oa"
    ? group.amountCheck?.oaTotal
    : paneId === "bank"
      ? group.amountCheck?.bankTotal
      : group.amountCheck?.invoiceTotal;
  const fallbackTotal = summarizeWorkbenchRows(rows).amounts[paneId];
  return { count, total: formatMoney(amountCheckTotal || fallbackTotal) };
}
