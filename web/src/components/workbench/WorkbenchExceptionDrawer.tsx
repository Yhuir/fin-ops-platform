import {
  Button,
  Chip,
  Disclosure,
  DisclosureGroup,
  ToggleButton,
  ToggleButtonGroup,
} from "@heroui/react";
import type { Key } from "@heroui/react";
import { useEffect, useMemo, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import { formatMoney } from "../../features/money";
import { summarizeWorkbenchRows } from "../../features/workbench/selectionModel";
import type {
  WorkbenchRecord,
  WorkbenchRecordType,
  WorkbenchRelationGroup,
} from "../../features/workbench/types";
import RelationGroupGrid from "./RelationGroupGrid";

type WorkbenchExceptionDrawerProps = {
  open: boolean;
  bucket: "active" | "processed";
  groups: WorkbenchRelationGroup[];
  ignoredRows: WorkbenchRecord[];
  loading: boolean;
  error: string | null;
  canMutateData: boolean;
  onBucketChange: (bucket: "active" | "processed") => void;
  onClose: () => void;
  onIgnoreAmountMismatch: (group: WorkbenchRelationGroup) => Promise<void> | void;
  onRestoreAmountMismatch: (group: WorkbenchRelationGroup) => Promise<void> | void;
  onCancelProcessedException: (group: WorkbenchRelationGroup) => Promise<void> | void;
  onUnignoreRow: (row: WorkbenchRecord) => Promise<void> | void;
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
  groups,
  ignoredRows,
  loading,
  error,
  canMutateData,
  onBucketChange,
  onClose,
  onIgnoreAmountMismatch,
  onRestoreAmountMismatch,
  onCancelProcessedException,
  onUnignoreRow,
}: WorkbenchExceptionDrawerProps) {
  const [expandedKeys, setExpandedKeys] = useState<Set<Key>>(new Set());
  const [pendingGroupId, setPendingGroupId] = useState<string | null>(null);
  const visibleGroups = useMemo(
    () => bucket === "processed" ? [...groups, ...ignoredRows.map(ignoredRowGroup)] : groups,
    [bucket, groups, ignoredRows],
  );

  useEffect(() => {
    setExpandedKeys(new Set());
  }, [bucket, open]);

  const runGroupAction = async (groupId: string, action: () => Promise<void> | void) => {
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
      width="min(1220px, 96vw)"
      onClose={onClose}
    >
      <div className="workbench-anomaly-drawer__toolbar">
        <ToggleButtonGroup
          aria-label="异常状态"
          className="workbench-anomaly-drawer__segmented"
          disallowEmptySelection
          selectedKeys={new Set<Key>([bucket])}
          selectionMode="single"
          size="sm"
          onSelectionChange={(keys) => {
            const [next] = Array.from(keys);
            if (next === "active" || next === "processed") {
              onBucketChange(next);
            }
          }}
        >
          <ToggleButton id="active">进行中的异常</ToggleButton>
          <ToggleButton id="processed">
            <ToggleButtonGroup.Separator />
            已忽略的异常
          </ToggleButton>
        </ToggleButtonGroup>
        <span className="workbench-anomaly-drawer__count">{visibleGroups.length} 项</span>
      </div>

      <div className="workbench-anomaly-drawer__content">
        {error ? <div className="detail-state-panel error">{error}</div> : null}
        {loading ? <div className="detail-state-panel">正在加载异常关系…</div> : null}
        {!loading && !error && visibleGroups.length === 0 ? (
          <div className="detail-state-panel">当前没有{bucket === "active" ? "进行中" : "已忽略"}的异常。</div>
        ) : null}
        {!loading && !error && visibleGroups.length > 0 ? (
          <DisclosureGroup
            className="workbench-anomaly-drawer__list"
            expandedKeys={expandedKeys}
            onExpandedChange={setExpandedKeys}
          >
            {visibleGroups.map((group) => {
              const expanded = expandedKeys.has(group.id);
              const detailGroup = expanded ? materializeDetailGroup(group) : null;
              return (
                <Disclosure className="workbench-anomaly-drawer__group" id={group.id} key={group.id}>
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
                      canMutateData={canMutateData}
                      group={group}
                      pending={pendingGroupId === group.id}
                      onAction={(action) => runGroupAction(group.id, action)}
                      onCancelProcessedException={onCancelProcessedException}
                      onIgnoreAmountMismatch={onIgnoreAmountMismatch}
                      onRestoreAmountMismatch={onRestoreAmountMismatch}
                      onUnignoreRow={onUnignoreRow}
                    />
                  </div>
                  <Disclosure.Content>
                    <Disclosure.Body className="workbench-anomaly-drawer__details">
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
      </div>
    </AppDrawer>
  );
}

function ExceptionAction({
  canMutateData,
  group,
  pending,
  onAction,
  onIgnoreAmountMismatch,
  onRestoreAmountMismatch,
  onCancelProcessedException,
  onUnignoreRow,
}: Pick<
  WorkbenchExceptionDrawerProps,
  | "canMutateData"
  | "onIgnoreAmountMismatch"
  | "onRestoreAmountMismatch"
  | "onCancelProcessedException"
  | "onUnignoreRow"
> & {
  group: WorkbenchRelationGroup;
  pending: boolean;
  onAction: (action: () => Promise<void> | void) => void;
}) {
  const label = exceptionLabel(group);
  const firstRow = allGroupRows(group)[0];
  let action: (() => Promise<void> | void) | null = null;
  let actionLabel = "";

  if (group.amountAnomaly?.state === "active") {
    action = () => onIgnoreAmountMismatch(group);
    actionLabel = "忽略";
  } else if (group.amountAnomaly?.state === "ignored") {
    action = () => onRestoreAmountMismatch(group);
    actionLabel = "撤回忽略";
  } else if (firstRow && group.rawGroupType === "ignored_row") {
    action = () => onUnignoreRow(firstRow);
    actionLabel = "撤回忽略";
  } else if (firstRow && group.exceptionState === "processed") {
    action = () => onCancelProcessedException(group);
    actionLabel = "撤回忽略";
  }

  return (
    <div className="workbench-anomaly-drawer__action">
      <Chip color={group.amountAnomaly?.state === "active" ? "danger" : "default"} size="sm" variant="soft">
        <Chip.Label>{label}</Chip.Label>
      </Chip>
      {canMutateData && action ? (
        <Button
          isDisabled={pending}
          isPending={pending}
          size="sm"
          variant="secondary"
          onPress={() => onAction(action)}
        >
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}

function exceptionLabel(group: WorkbenchRelationGroup) {
  if (group.amountAnomaly) {
    return group.amountAnomaly.displayLabel;
  }
  if (group.rawGroupType === "ignored_row") {
    return "已忽略";
  }
  const detail = group.processedExceptionSummary?.displayTags?.[0]
    ?? group.processedExceptionSummary?.resolution?.action_label;
  return typeof detail === "string" && detail.trim() ? `已忽略：${detail.trim()}` : "已忽略";
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
  const anomalyTotal = paneId === "oa"
    ? group.amountAnomaly?.oaTotal
    : paneId === "invoice"
      ? group.amountAnomaly?.invoiceTotal
      : undefined;
  const fallbackTotal = summarizeWorkbenchRows(rows).amounts[paneId];
  return { count, total: formatMoney(amountCheckTotal || anomalyTotal || fallbackTotal) };
}

function materializeDetailGroup(group: WorkbenchRelationGroup): WorkbenchRelationGroup {
  return {
    ...group,
    displayMode: "normal",
    defaultCollapsed: false,
    summaryRow: undefined,
    collapsedRows: undefined,
    collapsedRowCounts: undefined,
    rows: {
      oa: groupPaneRows(group, "oa"),
      bank: groupPaneRows(group, "bank"),
      invoice: groupPaneRows(group, "invoice"),
    },
  };
}

function ignoredRowGroup(row: WorkbenchRecord): WorkbenchRelationGroup {
  const rows = { oa: [] as WorkbenchRecord[], bank: [] as WorkbenchRecord[], invoice: [] as WorkbenchRecord[] };
  rows[row.recordType].push(row);
  return {
    id: `ignored:${row.id}`,
    groupType: "unpaired",
    rawGroupType: "ignored_row",
    matchConfidence: "low",
    reason: "ignored_row",
    rows,
    rowCounts: { [row.recordType]: 1 },
  };
}
