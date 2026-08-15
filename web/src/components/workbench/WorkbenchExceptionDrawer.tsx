import {
  Button,
  Checkbox,
  Chip,
  Disclosure,
  DisclosureGroup,
  ListBox,
  Select,
  ToggleButton,
  ToggleButtonGroup,
} from "@heroui/react";
import type { Key } from "@heroui/react";
import { useEffect, useRef, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import { formatMoney } from "../../features/money";
import { summarizeWorkbenchRows } from "../../features/workbench/selectionModel";
import type {
  WorkbenchAnomalyReviewClassificationCode,
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
    reviewClassificationCodes: WorkbenchAnomalyReviewClassificationCode[],
  ) => Promise<void> | void;
};

const PANE_IDS: WorkbenchRecordType[] = ["oa", "bank", "invoice"];
const PANE_LABELS: Record<WorkbenchRecordType, string> = {
  oa: "OA",
  bank: "流水",
  invoice: "发票",
};
const DRAWER_DETAIL_COLUMNS = "minmax(320px, 1fr) 1px minmax(320px, 1fr) 1px minmax(320px, 1fr)";
const AMOUNT_ANOMALY_CODES = new Set<WorkbenchAnomalyReviewClassificationCode>([
  "oa_bank_amount_mismatch",
  "oa_invoice_amount_mismatch",
  "bank_invoice_amount_mismatch",
]);
const REVIEW_CLASSIFICATION_OPTIONS: Array<{
  value: WorkbenchAnomalyReviewClassificationCode;
  label: string;
}> = [
  { value: "oa_bank_amount_mismatch", label: "OA流水金额不一致" },
  { value: "oa_invoice_amount_mismatch", label: "OA发票金额不一致" },
  { value: "bank_invoice_amount_mismatch", label: "流水发票金额不一致" },
  { value: "no_anomaly", label: "无异常" },
];

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
  const [reviewClassifications, setReviewClassifications] = useState<
    Record<string, WorkbenchAnomalyReviewClassificationCode[]>
  >({});
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
    setReviewClassifications({});
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
      width="min(1740px, 96vw)"
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
              const anomalyCount = exceptionLabels(group).length;
              return (
                <Disclosure
                  className="workbench-anomaly-drawer__group"
                  id={group.id}
                  key={`${contentGeneration}:${group.id}`}
                >
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
                        <span className="workbench-anomaly-drawer__anomaly-summary">
                          <span className="workbench-anomaly-drawer__pane-label">异常</span>
                          <strong>{anomalyCount}项</strong>
                        </span>
                        <Disclosure.Indicator className="workbench-anomaly-drawer__indicator" />
                      </span>
                    </Button>
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
                        </div>
                      ) : null}
                      <ExceptionReviewPanel
                        bucket={bucket}
                        canMutateData={canMutateData}
                        group={group}
                        pending={pendingGroupId === group.id}
                        reviewClassifications={reviewClassifications[group.id]
                          ?? group.workbenchAnomaly?.reviewClassificationCodes
                          ?? []}
                        reviewedItems={reviewedItems[group.id]
                          ?? new Set(group.workbenchAnomaly?.reviewedItemFingerprints ?? [])}
                        onAction={(action) => runGroupAction(group.id, action)}
                        onReviewAnomaly={onReviewAnomaly}
                        onToggleReviewed={(fingerprint) => setReviewedItems((current) => {
                          const next = new Set(current[group.id] ?? []);
                          if (next.has(fingerprint)) next.delete(fingerprint);
                          else next.add(fingerprint);
                          return { ...current, [group.id]: next };
                        })}
                        onReviewClassificationChange={(codes) => setReviewClassifications((current) => ({
                          ...current,
                          [group.id]: codes,
                        }))}
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
  reviewClassifications,
  reviewedItems,
  onAction,
  onReviewAnomaly,
  onReviewClassificationChange,
  onToggleReviewed,
}: Pick<
  WorkbenchExceptionDrawerProps,
  | "canMutateData"
  | "bucket"
  | "onReviewAnomaly"
> & {
  group: WorkbenchRelationGroup;
  pending: boolean;
  reviewClassifications: WorkbenchAnomalyReviewClassificationCode[];
  reviewedItems: Set<string>;
  onAction: (action: () => Promise<void> | void) => void;
  onReviewClassificationChange: (codes: WorkbenchAnomalyReviewClassificationCode[]) => void;
  onToggleReviewed: (fingerprint: string) => void;
}) {
  const labels = exceptionLabels(group);
  const itemFingerprints = group.workbenchAnomaly?.items.map((item) => item.fingerprint) ?? [];
  const amountItemFingerprints = new Set(
    group.workbenchAnomaly?.items
      .filter((item) => AMOUNT_ANOMALY_CODES.has(item.code as WorkbenchAnomalyReviewClassificationCode))
      .map((item) => item.fingerprint) ?? [],
  );
  const attachmentItemFingerprints = itemFingerprints.filter(
    (fingerprint) => !amountItemFingerprints.has(fingerprint),
  );
  const allReviewed = itemFingerprints.length > 0
    && (amountItemFingerprints.size === 0 || reviewClassifications.length > 0)
    && attachmentItemFingerprints.every((fingerprint) => reviewedItems.has(fingerprint));
  const submit = (decision: "accept_paired" | "keep_unpaired") => () => (
    onReviewAnomaly(group, decision, itemFingerprints, reviewClassifications)
  );

  return (
    <section aria-label="异常审阅" className="workbench-anomaly-drawer__review">
      <div className="workbench-anomaly-drawer__chips">
        {labels.map((label) => (
          bucket === "unpaired" && canMutateData && !amountItemFingerprints.has(label.fingerprint) ? (
            <Checkbox
              key={label.fingerprint}
              aria-label={`确认已审阅 ${label.text}`}
              className="workbench-anomaly-drawer__review-item"
              isSelected={reviewedItems.has(label.fingerprint)}
              onChange={() => onToggleReviewed(label.fingerprint)}
            >
              <Checkbox.Control>
                <Checkbox.Indicator />
              </Checkbox.Control>
              <Checkbox.Content>
                <Chip color={label.color} size="sm" variant="soft">
                  <Chip.Label>{label.text}</Chip.Label>
                </Chip>
              </Checkbox.Content>
            </Checkbox>
          ) : (
            <span className="workbench-anomaly-drawer__review-item" key={label.fingerprint}>
              <Chip color={label.color} size="sm" variant="soft">
                <Chip.Label>{label.text}</Chip.Label>
              </Chip>
            </span>
          )
        ))}
      </div>
      {canMutateData && group.workbenchAnomaly ? (
        bucket === "paired" ? (
          <div className="workbench-anomaly-drawer__decision-buttons">
            <Button isDisabled={pending} isPending={pending} size="sm" variant="secondary"
              onPress={() => onAction(submit("keep_unpaired"))}>
              撤回
            </Button>
          </div>
        ) : (
          <>
            {amountItemFingerprints.size > 0 ? (
              <Select<object, "multiple">
                aria-label="人工金额判断"
                className="workbench-anomaly-drawer__classification"
                placeholder="人工金额判断"
                selectionMode="multiple"
                value={reviewClassifications}
                onChange={(keys) => {
                  const selected = keys.map(String).filter(
                      (key): key is WorkbenchAnomalyReviewClassificationCode => (
                        key === "oa_bank_amount_mismatch"
                        || key === "oa_invoice_amount_mismatch"
                        || key === "bank_invoice_amount_mismatch"
                        || key === "no_anomaly"
                      ),
                    );
                  const previouslySelectedNoAnomaly = reviewClassifications.includes("no_anomaly");
                  const next = selected.includes("no_anomaly")
                    ? previouslySelectedNoAnomaly && selected.length > 1
                      ? selected.filter((code) => code !== "no_anomaly")
                      : ["no_anomaly" as const]
                    : selected;
                  onReviewClassificationChange(next);
                }}
              >
                <Select.Trigger>
                  <Select.Value />
                  <Select.Indicator />
                </Select.Trigger>
                <Select.Popover>
                  <ListBox>
                    {REVIEW_CLASSIFICATION_OPTIONS.map((option) => (
                      <ListBox.Item id={option.value} key={option.value} textValue={option.label}>
                        {option.label}
                      </ListBox.Item>
                    ))}
                  </ListBox>
                </Select.Popover>
              </Select>
            ) : null}
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
          </>
        )
      ) : null}
    </section>
  );
}

function exceptionLabels(group: WorkbenchRelationGroup) {
  const anomaly = group.workbenchAnomaly;
  const itemLabels = (anomaly?.items ?? [])
    .filter((item) => (
      anomaly?.reviewDecision === "pending"
      || (anomaly?.reviewClassificationCodes ?? []).length === 0
      || !AMOUNT_ANOMALY_CODES.has(item.code as WorkbenchAnomalyReviewClassificationCode)
    ))
    .map((item) => [item.fingerprint, {
    fingerprint: item.fingerprint,
    text: item.displayLabel,
    color: item.code.endsWith("amount_mismatch")
        ? "danger" as const
        : "warning" as const,
  }] as const);
  const classificationLabels = anomaly?.reviewDecision !== "pending"
    ? (anomaly?.reviewClassificationCodes ?? []).map((code) => {
      const option = REVIEW_CLASSIFICATION_OPTIONS.find((candidate) => candidate.value === code);
      return [`classification:${code}`, {
        fingerprint: `classification:${code}`,
        text: option?.label ?? code,
        color: code === "no_anomaly" ? "success" as const : "danger" as const,
      }] as const;
    })
    : [];
  return [...itemLabels, ...classificationLabels].map(([, label]) => label);
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
