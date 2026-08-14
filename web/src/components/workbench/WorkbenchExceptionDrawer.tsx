import {
  Button,
  Chip,
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
import type {
  WorkbenchRecordType,
  WorkbenchRelationGroup,
} from "../../features/workbench/types";
import RelationGroupGrid from "./RelationGroupGrid";

type WorkbenchExceptionDrawerProps = {
  open: boolean;
  bucket: "unpaired" | "paired";
  contentGeneration: number;
  groups: WorkbenchRelationGroup[];
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  total: number;
  hasMore: boolean;
  canMutateData: boolean;
  onBucketChange: (bucket: "unpaired" | "paired") => void;
  onClose: () => void;
  onEnsureGroupDetail: (group: WorkbenchRelationGroup) => Promise<WorkbenchRelationGroup>;
  onLoadMore: () => Promise<void> | void;
  onReviewAnomaly: (
    group: WorkbenchRelationGroup,
    decision: "accept_paired" | "keep_unpaired",
    reviewedItemFingerprints: string[],
  ) => Promise<void> | void;
};

const PANE_IDS: WorkbenchRecordType[] = ["oa", "bank", "invoice"];
const PANE_LABELS: Record<WorkbenchRecordType, string> = {
  oa: "OA",
  bank: "流水",
  invoice: "发票",
};
const DRAWER_DETAIL_COLUMNS = "minmax(320px, 1fr) 1px minmax(320px, 1fr) 1px minmax(320px, 1fr)";

export default function WorkbenchExceptionDrawer({
  open,
  bucket,
  contentGeneration,
  groups,
  loading,
  loadingMore,
  error,
  total,
  hasMore,
  canMutateData,
  onBucketChange,
  onClose,
  onEnsureGroupDetail,
  onLoadMore,
  onReviewAnomaly,
}: WorkbenchExceptionDrawerProps) {
  const [expandedKeys, setExpandedKeys] = useState<Set<Key>>(new Set());
  const [pendingGroupId, setPendingGroupId] = useState<string | null>(null);
  const [detailGroups, setDetailGroups] = useState<Record<string, WorkbenchRelationGroup>>({});
  const [detailLoadingIds, setDetailLoadingIds] = useState<Set<string>>(new Set());
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});
  const [reviewedItems, setReviewedItems] = useState<Record<string, Set<string>>>({});
  const detailRequestsRef = useRef(new Set<string>());
  const detailGenerationRef = useRef(0);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const visibleGroups = groups;

  useEffect(() => {
    detailGenerationRef.current += 1;
    detailRequestsRef.current.clear();
    setExpandedKeys(new Set());
    setDetailGroups({});
    setDetailLoadingIds(new Set());
    setDetailErrors({});
    setReviewedItems({});
    setPendingGroupId(null);
  }, [bucket, contentGeneration, open]);

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
    const currentBucketControl = toolbarRef.current?.querySelector<HTMLElement>(
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

  return (
    <AppDrawer
      ariaBusy={loading}
      className="workbench-anomaly-drawer"
      open={open}
      title="异常处理"
      width="min(1160px, 96vw)"
      onClose={onClose}
    >
      <div className="workbench-anomaly-drawer__toolbar" ref={toolbarRef}>
        <ToggleButtonGroup
          aria-label="异常状态"
          className="workbench-anomaly-drawer__segmented"
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
          <ToggleButton id="unpaired">未配对异常</ToggleButton>
          <ToggleButton id="paired">
            <ToggleButtonGroup.Separator />
            已配对异常
          </ToggleButton>
        </ToggleButtonGroup>
        <span className="workbench-anomaly-drawer__count">
          {visibleGroups.length < total ? `${visibleGroups.length} / ${total}` : total} 项
        </span>
      </div>

      <div className="workbench-anomaly-drawer__content">
        {error ? <div className="detail-state-panel error">{error}</div> : null}
        {loading ? <div className="detail-state-panel">正在加载异常关系…</div> : null}
        {!loading && !error && visibleGroups.length === 0 ? (
          <div className="detail-state-panel">当前没有{bucket === "unpaired" ? "未配对" : "已配对"}异常。</div>
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
                  <div className="workbench-anomaly-drawer__group-header">
                    <Disclosure.Heading>
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
                    </Disclosure.Heading>
                    <ExceptionAction
                      bucket={bucket}
                      canMutateData={canMutateData}
                      group={group}
                      pending={pendingGroupId === group.id}
                      reviewedItems={reviewedItems[group.id] ?? new Set()}
                      onAction={(action) => runGroupAction(group.id, action)}
                      onReviewAnomaly={onReviewAnomaly}
                      onToggleReviewed={(fingerprint) => setReviewedItems((current) => {
                        const next = new Set(current[group.id] ?? []);
                        if (next.has(fingerprint)) next.delete(fingerprint);
                        else next.add(fingerprint);
                        return { ...current, [group.id]: next };
                      })}
                    />
                  </div>
                  <Disclosure.Content>
                    <Disclosure.Body className="workbench-anomaly-drawer__details">
                      {detailLoadingIds.has(group.id) ? (
                        <div className="detail-state-panel">正在加载完整异常明细…</div>
                      ) : null}
                      {detailErrors[group.id] ? (
                        <div className="detail-state-panel error">{detailErrors[group.id]}</div>
                      ) : null}
                      {detailGroup ? (
                        <RelationGroupGrid
                          canMutateData={false}
                          getRowState={() => "idle"}
                          groups={[detailGroup]}
                          hidePaneHeaders
                          onOpenDetail={() => undefined}
                          onRowAction={() => undefined}
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
                      ) : null}
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

function ExceptionAction({
  canMutateData,
  bucket,
  group,
  pending,
  reviewedItems,
  onAction,
  onReviewAnomaly,
  onToggleReviewed,
}: Pick<
  WorkbenchExceptionDrawerProps,
  | "canMutateData"
  | "bucket"
  | "onReviewAnomaly"
> & {
  group: WorkbenchRelationGroup;
  pending: boolean;
  reviewedItems: Set<string>;
  onAction: (action: () => Promise<void> | void) => void;
  onToggleReviewed: (fingerprint: string) => void;
}) {
  const labels = exceptionLabels(group);
  const itemFingerprints = group.workbenchAnomaly?.items.map((item) => item.fingerprint) ?? [];
  const allReviewed = itemFingerprints.length > 0
    && itemFingerprints.every((fingerprint) => reviewedItems.has(fingerprint));
  const submit = (decision: "accept_paired" | "keep_unpaired") => () => (
    onReviewAnomaly(group, decision, itemFingerprints)
  );

  return (
    <div className="workbench-anomaly-drawer__action">
      <div className="workbench-anomaly-drawer__chips">
        {labels.map((label) => (
          <label className="workbench-anomaly-drawer__review-item" key={label.fingerprint}>
            {bucket === "unpaired" && canMutateData ? (
              <input
                aria-label={`确认已审阅 ${label.text}`}
                checked={reviewedItems.has(label.fingerprint)}
                type="checkbox"
                onChange={() => onToggleReviewed(label.fingerprint)}
              />
            ) : null}
            <Chip color={label.color} size="sm" variant="soft">
              <Chip.Label>{label.text}</Chip.Label>
            </Chip>
          </label>
        ))}
      </div>
      {canMutateData && group.workbenchAnomaly ? (
        bucket === "paired" ? (
          <Button isDisabled={pending} isPending={pending} size="sm" variant="secondary"
            onPress={() => onAction(submit("keep_unpaired"))}>
            撤回
          </Button>
        ) : (
          <div className="workbench-anomaly-drawer__decision-buttons">
            <Button isDisabled={pending || !allReviewed} isPending={pending} size="sm"
              variant="secondary" onPress={() => onAction(submit("keep_unpaired"))}>
              留在未配对
            </Button>
            <Button isDisabled={pending || !allReviewed} isPending={pending} size="sm"
              variant="primary" onPress={() => onAction(submit("accept_paired"))}>
              进入已配对
            </Button>
          </div>
        )
      ) : null}
    </div>
  );
}

function exceptionLabels(group: WorkbenchRelationGroup) {
  return Array.from(new Map((group.workbenchAnomaly?.items ?? []).map((item) => [item.fingerprint, {
    fingerprint: item.fingerprint,
    text: item.displayLabel,
    color: item.code.endsWith("amount_mismatch")
        ? "danger" as const
        : "warning" as const,
  }])).values());
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
