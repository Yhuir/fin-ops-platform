import { Button } from "@heroui/react";

import AppDrawer from "../common/AppDrawer";
import type { WorkbenchRelationGroup, WorkbenchRecord } from "../../features/workbench/types";
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
  onIgnoreAmountMismatch: (group: WorkbenchRelationGroup) => void;
  onRestoreAmountMismatch: (group: WorkbenchRelationGroup) => void;
  onCancelProcessedException: (row: WorkbenchRecord) => void;
  onUnignoreRow: (row: WorkbenchRecord) => void;
};

const DRAWER_GRID_COLUMNS =
  "minmax(320px, 1fr) 1px minmax(320px, 1fr) 1px minmax(320px, 1fr) 1px minmax(124px, 0.34fr)";

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
  const visibleGroups = bucket === "processed"
    ? [...groups, ...ignoredRows.map(ignoredRowGroup)]
    : groups;
  const panes = [
    { id: "oa" as const, title: "OA", rows: visibleGroups.flatMap((group) => group.rows.oa) },
    { id: "bank" as const, title: "银行流水", rows: visibleGroups.flatMap((group) => group.rows.bank) },
    { id: "invoice" as const, title: "进销项发票", rows: visibleGroups.flatMap((group) => group.rows.invoice) },
  ];

  return (
    <AppDrawer
      ariaBusy={loading}
      className="workbench-anomaly-drawer"
      open={open}
      subtitle="OA、银行流水与发票按关系组三栏对照；金额差异不做真假或容差判断。"
      title="异常处理"
      width="min(1220px, 96vw)"
      onClose={onClose}
    >
      <div className="workbench-anomaly-drawer__tabs" role="group" aria-label="异常状态">
        <Button
          aria-pressed={bucket === "active"}
          className="workbench-anomaly-drawer__tab"
          size="sm"
          variant={bucket === "active" ? "primary" : "secondary"}
          onPress={() => onBucketChange("active")}
        >
          进行中的异常
        </Button>
        <Button
          aria-pressed={bucket === "processed"}
          className="workbench-anomaly-drawer__tab"
          size="sm"
          variant={bucket === "processed" ? "primary" : "secondary"}
          onPress={() => onBucketChange("processed")}
        >
          已处理异常
        </Button>
        <span className="workbench-anomaly-drawer__count">{visibleGroups.length} 项</span>
      </div>

      {error ? <div className="detail-state-panel error">{error}</div> : null}
      {loading ? <div className="detail-state-panel">正在加载异常关系…</div> : null}
      {!loading && !error && visibleGroups.length === 0 ? (
        <div className="detail-state-panel">当前没有{bucket === "active" ? "进行中" : "已处理"}的异常。</div>
      ) : null}
      {!loading && !error && visibleGroups.length > 0 ? (
        <div className="workbench-anomaly-drawer__grid">
          <RelationGroupGrid
            canMutateData={false}
            getRowState={() => "idle"}
            groups={visibleGroups}
            onOpenDetail={() => undefined}
            onRowAction={() => undefined}
            onSelectRow={() => undefined}
            panes={panes}
            rowTemplateColumns={DRAWER_GRID_COLUMNS}
            trailingColumns={[{
              key: "exceptionAction",
              label: "操作",
              className: "workbench-anomaly-drawer__action-cell",
              renderGroup: (group) => (
                <ExceptionAction
                  canMutateData={canMutateData}
                  group={group}
                  onCancelProcessedException={onCancelProcessedException}
                  onIgnoreAmountMismatch={onIgnoreAmountMismatch}
                  onRestoreAmountMismatch={onRestoreAmountMismatch}
                  onUnignoreRow={onUnignoreRow}
                />
              ),
            }]}
            readOnly
            zoneId="paired"
          />
        </div>
      ) : null}
    </AppDrawer>
  );
}

function ExceptionAction({
  canMutateData,
  group,
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
> & { group: WorkbenchRelationGroup }) {
  const label = exceptionLabel(group);
  if (!canMutateData) {
    return (
      <div className="workbench-anomaly-drawer__action">
        <span className="workbench-anomaly-drawer__status">{label}</span>
        <span className="workbench-anomaly-drawer__readonly">只读</span>
      </div>
    );
  }
  if (group.amountAnomaly?.state === "active") {
    return (
      <div className="workbench-anomaly-drawer__action">
        <span className="workbench-anomaly-drawer__status">{label}</span>
        <Button size="sm" variant="secondary" onPress={() => onIgnoreAmountMismatch(group)}>忽略</Button>
      </div>
    );
  }
  if (group.amountAnomaly?.state === "ignored") {
    return (
      <div className="workbench-anomaly-drawer__action">
        <span className="workbench-anomaly-drawer__status">{label}</span>
        <Button size="sm" variant="secondary" onPress={() => onRestoreAmountMismatch(group)}>恢复</Button>
      </div>
    );
  }
  const firstRow = [...group.rows.oa, ...group.rows.bank, ...group.rows.invoice][0];
  if (!firstRow) {
    return null;
  }
  if (group.rawGroupType === "ignored_row") {
    return (
      <div className="workbench-anomaly-drawer__action">
        <span className="workbench-anomaly-drawer__status">{label}</span>
        <Button size="sm" variant="secondary" onPress={() => onUnignoreRow(firstRow)}>撤回忽略</Button>
      </div>
    );
  }
  return (
    <div className="workbench-anomaly-drawer__action">
      <span className="workbench-anomaly-drawer__status">{label}</span>
      <Button size="sm" variant="secondary" onPress={() => onCancelProcessedException(firstRow)}>撤回处理</Button>
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
  const displayTag = group.processedExceptionSummary?.displayTags?.[0];
  if (displayTag) {
    return displayTag;
  }
  const resolutionLabel = group.processedExceptionSummary?.resolution?.action_label;
  return typeof resolutionLabel === "string" && resolutionLabel ? resolutionLabel : "已处理异常";
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
  };
}
