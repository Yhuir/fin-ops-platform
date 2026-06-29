import {
  Fragment,
  memo,
  useEffect,
  useMemo,
  useState,
  useCallback,
  useRef,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";

import {
  buildWorkbenchGroupDisplaySegments,
  collectWorkbenchFilterOptions,
  collectWorkbenchTimeFilterYears,
  createEmptyWorkbenchZoneDisplayState,
  resolveWorkbenchLinkedSearchQuery,
  type WorkbenchPaneTimeFilter as WorkbenchPaneTimeFilterState,
  type WorkbenchZoneDisplayState,
} from "../../features/workbench/groupDisplayModel";
import type {
  WorkbenchCandidateGroup,
  WorkbenchColumnLayouts,
  WorkbenchInvoiceInventory,
  WorkbenchRecord,
  WorkbenchRecordType,
} from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import { getWorkbenchColumns, getWorkbenchPaneGridStyle } from "../../features/workbench/tableConfig";
import type { WorkbenchInlineAction } from "./RowActions";
import type { WorkbenchPane } from "./ResizableTriPane";
import CandidateGroupCell from "./CandidateGroupCell";
import WorkbenchColumnFilterMenu from "./WorkbenchColumnFilterMenu";
import WorkbenchPaneSearch from "./WorkbenchPaneSearch";
import WorkbenchPaneTimeFilter from "./WorkbenchPaneTimeFilter";
import type { WorkbenchColumnDropPosition } from "../../features/workbench/columnLayout";

type CandidateGroupGridProps = {
  zoneId: "paired" | "open";
  panes: WorkbenchPane[];
  groups: WorkbenchCandidateGroup[];
  sourceGroups?: WorkbenchCandidateGroup[];
  invoiceInventory?: WorkbenchInvoiceInventory;
  displayState?: WorkbenchZoneDisplayState;
  columnLayouts?: WorkbenchColumnLayouts;
  rowTemplateColumns: string;
  trailingColumns?: Array<{
    key: string;
    label: string;
    className?: string;
    renderGroup: (group: WorkbenchCandidateGroup) => ReactNode;
  }>;
  actionMode?: "default" | "cancel-exception-only";
  highlightedRowId?: string | null;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "open") => WorkbenchRowState;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "open") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  onEnsureGroupDetail?: (zoneId: "paired" | "open", groupId: string) => Promise<void>;
  onTogglePaneSearch?: (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice") => void;
  onClosePaneSearch?: (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice") => void;
  onClearPaneSearch?: (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice") => void;
  onPaneSearchQueryChange?: (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice", query: string) => void;
  onColumnFilterChange?: (
    zoneId: "paired" | "open",
    paneId: "oa" | "bank" | "invoice",
    columnKey: string,
    selectedValues: string[],
  ) => void;
  onTogglePaneSort?: (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice") => void;
  onPaneTimeFilterChange?: (
    zoneId: "paired" | "open",
    paneId: "oa" | "bank" | "invoice",
    filter: WorkbenchPaneTimeFilterState,
  ) => void;
  onReorderPaneColumns?: (
    paneId: "oa" | "bank" | "invoice",
    activeKey: string,
    overKey: string,
    position: WorkbenchColumnDropPosition,
  ) => void;
  canMutateData: boolean;
};

type CollapsedSummaryCopy = {
  detailLabel: string;
  countUnit: string;
  totalLabel: (count: number) => string;
};

function resolveCollapsedSummaryCopy(
  group: WorkbenchCandidateGroup,
  paneId: WorkbenchRecordType,
  collapsedRows: WorkbenchRecord[],
): CollapsedSummaryCopy {
  const summaryRow = group.summaryRow ?? group.rows[paneId]?.[0];
  const isEtcInvoiceSummary =
    paneId === "invoice" &&
    (summaryRow?.sourceKind === "etc_invoice_summary" || collapsedRows.some((row) => row.sourceKind === "etc_invoice"));

  if (isEtcInvoiceSummary) {
    return {
      detailLabel: "ETC发票明细",
      countUnit: "张",
      totalLabel: (count) => `实际 ${count} 张发票`,
    };
  }
  if (group.relationMode === "bank_flow_rule_batch") {
    return {
      detailLabel: "流水规则批次明细",
      countUnit: "条",
      totalLabel: (count) => `实际 ${count} 条流水`,
    };
  }

  return {
    detailLabel: "免OA批次明细",
    countUnit: "条",
    totalLabel: (count) => `实际 ${count} 条流水`,
  };
}

function CandidateGroupGrid({
  zoneId,
  panes,
  groups,
  sourceGroups,
  invoiceInventory = emptyInvoiceInventory,
  displayState = createEmptyWorkbenchZoneDisplayState(),
  columnLayouts,
  rowTemplateColumns,
  trailingColumns = [],
  actionMode = "default",
  highlightedRowId,
  getRowState,
  onSelectRow,
  onOpenDetail,
  onRowAction,
  onEnsureGroupDetail,
  onTogglePaneSearch = () => undefined,
  onClosePaneSearch = () => undefined,
  onClearPaneSearch = () => undefined,
  onPaneSearchQueryChange = () => undefined,
  onColumnFilterChange = () => undefined,
  onTogglePaneSort = () => undefined,
  onPaneTimeFilterChange = () => undefined,
  onReorderPaneColumns = () => undefined,
  canMutateData,
}: CandidateGroupGridProps) {
  const gridRef = useRef<HTMLDivElement | null>(null);
  const [openFilterMenu, setOpenFilterMenu] = useState<{ paneId: WorkbenchRecordType; columnKey: string } | null>(null);
  const [expandedCollapsedGroups, setExpandedCollapsedGroups] = useState<Set<string>>(() => new Set());
  const [loadingCollapsedGroups, setLoadingCollapsedGroups] = useState<Set<string>>(() => new Set());
  const pendingPreviewDetailRequestsRef = useRef<Set<string>>(new Set());
  const failedPreviewDetailRequestsRef = useRef<Set<string>>(new Set());
  const syncInFlightRef = useRef<Record<WorkbenchRecordType, boolean>>({
    oa: false,
    bank: false,
    invoice: false,
  });
  const dragStateRef = useRef<{
    paneId: WorkbenchRecordType;
    activeKey: string;
    overKey: string | null;
    position: WorkbenchColumnDropPosition;
    activeElement: HTMLElement | null;
    targetElement: HTMLElement | null;
  } | null>(null);
  const scrollPositionsRef = useRef<Record<WorkbenchRecordType, number>>({
    oa: 0,
    bank: 0,
    invoice: 0,
  });

  useEffect(() => {
    const root = gridRef.current;
    if (!root) {
      return;
    }

    panes.forEach((pane) => {
      const scrollLeft = scrollPositionsRef.current[pane.id];
      root.querySelectorAll<HTMLElement>(`[data-scroll-pane="${pane.id}"]`).forEach((element) => {
        element.scrollLeft = scrollLeft;
      });
    });
  }, [groups, panes]);

  useEffect(() => {
    if (!onEnsureGroupDetail) {
      return;
    }
    groups.forEach((group) => {
      const requestKey = buildPreviewDetailRequestKey(zoneId, group, panes);
      if (!requestKey) {
        clearPreviewDetailRequestKeys(zoneId, group.id, pendingPreviewDetailRequestsRef.current);
        clearPreviewDetailRequestKeys(zoneId, group.id, failedPreviewDetailRequestsRef.current);
        return;
      }
      if (pendingPreviewDetailRequestsRef.current.has(requestKey) || failedPreviewDetailRequestsRef.current.has(requestKey)) {
        return;
      }
      pendingPreviewDetailRequestsRef.current.add(requestKey);
      void onEnsureGroupDetail(zoneId, group.id)
        .catch(() => {
          failedPreviewDetailRequestsRef.current.add(requestKey);
        })
        .finally(() => {
          pendingPreviewDetailRequestsRef.current.delete(requestKey);
        });
    });
  }, [groups, onEnsureGroupDetail, panes, zoneId]);

  const handleSyncScroll = (paneId: WorkbenchRecordType, element: HTMLDivElement) => {
    scrollPositionsRef.current[paneId] = element.scrollLeft;
    if (syncInFlightRef.current[paneId]) {
      return;
    }

    const root = gridRef.current;
    if (!root) {
      return;
    }

    syncInFlightRef.current[paneId] = true;
    root.querySelectorAll<HTMLElement>(`[data-scroll-pane="${paneId}"]`).forEach((candidate) => {
      if (candidate !== element) {
        candidate.scrollLeft = element.scrollLeft;
      }
    });
    queueMicrotask(() => {
      syncInFlightRef.current[paneId] = false;
    });
  };

  const paneHasActionColumn = useCallback((paneId: WorkbenchRecordType) => {
    if (actionMode === "cancel-exception-only") {
      return paneId !== "invoice";
    }
    if (actionMode !== "default") {
      return false;
    }
    return groups.some((group) => group.rows[paneId].some(hasDefaultRowActions));
  }, [actionMode, groups]);
  const paneLayoutClass = (paneId: WorkbenchRecordType) =>
    paneHasActionColumn(paneId) ? "pane-layout-with-action" : "pane-layout-no-action";
  const hasTrailingColumns = trailingColumns.length > 0;

  const columnsByPane = useMemo(
    () => ({
      oa: getWorkbenchColumns("oa", columnLayouts),
      bank: getWorkbenchColumns("bank", columnLayouts),
      invoice: getWorkbenchColumns("invoice", columnLayouts),
    }),
    [columnLayouts],
  );

  const paneGridStyleByPane = useMemo(
    () => ({
      oa: getWorkbenchPaneGridStyle("oa", columnLayouts, paneHasActionColumn("oa")),
      bank: getWorkbenchPaneGridStyle("bank", columnLayouts, paneHasActionColumn("bank")),
      invoice: getWorkbenchPaneGridStyle("invoice", columnLayouts, paneHasActionColumn("invoice")),
    }),
    [columnLayouts, paneHasActionColumn],
  );

  const filterOptionsByPane = useMemo(() => {
    return {
      oa: Object.fromEntries(
        columnsByPane.oa.map((column) => [column.key, collectWorkbenchFilterOptions(sourceGroups ?? groups, "oa", column.key)]),
      ),
      bank: Object.fromEntries(
        columnsByPane.bank.map((column) => [column.key, collectWorkbenchFilterOptions(sourceGroups ?? groups, "bank", column.key)]),
      ),
      invoice: Object.fromEntries(
        columnsByPane.invoice.map((column) => [column.key, collectWorkbenchFilterOptions(sourceGroups ?? groups, "invoice", column.key)]),
      ),
    } satisfies Record<WorkbenchRecordType, Record<string, string[]>>;
  }, [columnsByPane, groups, sourceGroups]);

  const timeFilterYearsByPane = useMemo(() => {
    const filterSourceGroups = sourceGroups ?? groups;
    return {
      oa: collectWorkbenchTimeFilterYears(filterSourceGroups, "oa"),
      bank: collectWorkbenchTimeFilterYears(filterSourceGroups, "bank"),
      invoice: collectWorkbenchTimeFilterYears(filterSourceGroups, "invoice"),
    } satisfies Record<WorkbenchRecordType, string[]>;
  }, [groups, sourceGroups]);

  const linkedSearchQuery = useMemo(() => resolveWorkbenchLinkedSearchQuery(displayState), [displayState]);

  const handleToggleFilterMenu = useCallback((paneId: WorkbenchRecordType, columnKey: string) => {
    setOpenFilterMenu((current) => (
      current?.paneId === paneId && current.columnKey === columnKey ? null : { paneId, columnKey }
    ));
  }, []);

  const setCollapsedGroupExpanded = useCallback((groupId: string, paneId: WorkbenchRecordType, expanded: boolean) => {
    const key = `${groupId}:${paneId}`;
    setExpandedCollapsedGroups((current) => {
      const next = new Set(current);
      if (expanded) {
        next.add(key);
      } else {
        next.delete(key);
      }
      return next;
    });
  }, []);

  const toggleCollapsedGroup = useCallback(async (
    group: WorkbenchCandidateGroup,
    paneId: WorkbenchRecordType,
    isExpanded: boolean,
    collapsedRowCount: number,
    visibleCollapsedRowCount: number,
  ) => {
    const key = `${group.id}:${paneId}`;
    if (isExpanded) {
      setCollapsedGroupExpanded(group.id, paneId, false);
      return;
    }
    if (onEnsureGroupDetail && collapsedRowCount > visibleCollapsedRowCount) {
      setLoadingCollapsedGroups((current) => new Set(current).add(key));
      try {
        await onEnsureGroupDetail(zoneId, group.id);
      } finally {
        setLoadingCollapsedGroups((current) => {
          const next = new Set(current);
          next.delete(key);
          return next;
        });
      }
    }
    setCollapsedGroupExpanded(group.id, paneId, true);
  }, [onEnsureGroupDetail, setCollapsedGroupExpanded, zoneId]);

  const clearDragClasses = useCallback(() => {
    const current = dragStateRef.current;
    current?.activeElement?.classList.remove("column-drag-active");
    current?.targetElement?.classList.remove("column-drop-before", "column-drop-after");
    document.body.classList.remove("column-layout-dragging");
  }, []);

  const handleStartColumnDrag = useCallback((
    event: ReactPointerEvent<HTMLButtonElement>,
    paneId: WorkbenchRecordType,
    columnKey: string,
  ) => {
    if (!canMutateData || event.button !== 0) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();

    const activeElement = (event.currentTarget.closest("[data-column-key]") as HTMLElement | null);
    if (!activeElement) {
      return;
    }

    clearDragClasses();
    activeElement.classList.add("column-drag-active");
    document.body.classList.add("column-layout-dragging");

    dragStateRef.current = {
      paneId,
      activeKey: columnKey,
      overKey: columnKey,
      position: "before",
      activeElement,
      targetElement: null,
    };

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const current = dragStateRef.current;
      if (!current) {
        return;
      }
      const hovered = document.elementFromPoint(moveEvent.clientX, moveEvent.clientY) as HTMLElement | null;
      const target = hovered?.closest<HTMLElement>(`[data-pane-id="${paneId}"][data-column-key]`) ?? null;
      if (!target) {
        return;
      }
      const targetKey = target.dataset.columnKey ?? "";
      if (!targetKey || targetKey === current.activeKey) {
        current.targetElement?.classList.remove("column-drop-before", "column-drop-after");
        current.targetElement = null;
        current.overKey = current.activeKey;
        return;
      }
      const rect = target.getBoundingClientRect();
      const position: WorkbenchColumnDropPosition = moveEvent.clientX > rect.left + rect.width / 2 ? "after" : "before";
      if (current.targetElement !== target || current.position !== position) {
        current.targetElement?.classList.remove("column-drop-before", "column-drop-after");
        target.classList.add(position === "after" ? "column-drop-after" : "column-drop-before");
        current.targetElement = target;
        current.overKey = targetKey;
        current.position = position;
      }
    };

    const handlePointerUp = () => {
      const current = dragStateRef.current;
      dragStateRef.current = null;
      clearDragClasses();
      document.removeEventListener("pointermove", handlePointerMove);
      document.removeEventListener("pointerup", handlePointerUp);
      if (!current || !current.overKey || current.overKey === current.activeKey) {
        return;
      }
      onReorderPaneColumns(paneId, current.activeKey, current.overKey, current.position);
    };

    document.addEventListener("pointermove", handlePointerMove);
    document.addEventListener("pointerup", handlePointerUp);
  }, [canMutateData, clearDragClasses, onReorderPaneColumns]);

  const gridBody = useMemo(() => (
    <div className="candidate-grid-body">
      {groups.length === 0 ? <div className="state-panel">当前区域暂无候选组。</div> : null}
      {groups.map((group, index) => {
        const renderCollapseControls = (paneId: WorkbenchRecordType): ReactNode => {
          const collapsedRows = group.collapsedRows?.[paneId] ?? [];
          const isCollapsedSummary = group.displayMode === "collapsed_summary" && collapsedRows.length > 0;
          if (!isCollapsedSummary) {
            return null;
          }
          const collapseKey = `${group.id}:${paneId}`;
          const isExpanded = expandedCollapsedGroups.has(collapseKey);
          const isLoading = loadingCollapsedGroups.has(collapseKey);
          const displayRowCount = group.displayRowCounts?.[paneId] ?? group.rows[paneId].length;
          const collapsedRowCount = group.rowCounts?.[paneId] ?? group.collapsedRowCounts?.[paneId] ?? collapsedRows.length;
          const collapseCopy = resolveCollapsedSummaryCopy(group, paneId, collapsedRows);
          return (
            <Fragment>
              <button
                aria-expanded={isExpanded}
                aria-label={
                  isExpanded
                    ? `收起${collapseCopy.detailLabel}`
                    : `展开${collapseCopy.detailLabel}，${collapsedRowCount} ${collapseCopy.countUnit}`
                }
                className="row-action-btn candidate-group-collapse-control"
                disabled={isLoading}
                type="button"
                onClick={() => void toggleCollapsedGroup(group, paneId, isExpanded, collapsedRowCount, collapsedRows.length)}
              >
                {isLoading
                  ? "加载中"
                  : isExpanded
                    ? "收起明细"
                    : `展开 ${collapsedRowCount} ${collapseCopy.countUnit}明细`}
              </button>
              {!isExpanded ? (
                <span className="candidate-group-collapse-counts">
                  <span>当前显示 {displayRowCount} 条摘要</span>
                  <span>{collapseCopy.totalLabel(collapsedRowCount)}</span>
                </span>
              ) : null}
            </Fragment>
          );
        };
        const displaySegments = buildWorkbenchGroupDisplaySegments(group);
        const segmentCount = displaySegments?.length ?? 0;

        if (displaySegments) {
          return (
            <div
              key={group.id}
              className={`candidate-group-row candidate-group-row-sheet candidate-group-row-segmented candidate-group-row-tone-${index % 4}`}
              data-testid={`candidate-group-${zoneId}-${group.id}`}
              style={{ gridTemplateColumns: rowTemplateColumns }}
            >
              {displaySegments.map((segment, segmentIndex) => (
                <div
                  key={`${group.id}-segment-${segment.id}`}
                  className="candidate-group-segment-row"
                  data-testid={`candidate-group-segment-${zoneId}-${group.id}-${segment.id}`}
                >
                  {panes.flatMap((pane, paneIndex) => {
                    const paneId = pane.id as WorkbenchRecordType;
                    if (!isSourceSegmentedPane(paneId, displaySegments)) {
                      return [];
                    }
                    return [
                      <div
                        key={`${group.id}-${segment.id}-${pane.id}`}
                        className={`candidate-group-pane-slot candidate-group-pane-slot-sheet candidate-group-segment-pane-slot${segmentIndex === 0 ? " first" : ""}`}
                        style={{
                          gridColumn: paneIndex * 2 + 1,
                          gridRow: segmentIndex + 1,
                        }}
                      >
                        {segmentIndex === 0 ? renderCollapseControls(paneId) : null}
                        <CandidateGroupCell
                          actionMode={actionMode}
                          columnGridStyle={paneGridStyleByPane[paneId]}
                          columns={columnsByPane[paneId]}
                          getRowState={getRowState}
                          highlightedRowId={highlightedRowId}
                          searchQuery={linkedSearchQuery || displayState.searchQueryByPane[paneId]}
                          onOpenDetail={onOpenDetail}
                          onRowAction={onRowAction}
                          onSelectRow={onSelectRow}
                          paneId={paneId}
                          records={segment.rows[paneId]}
                          scrollPaneId={paneId}
                          scrollTestId={`candidate-scroll-${zoneId}-${group.id}-${segment.id}-${pane.id}`}
                          showActionColumn={paneHasActionColumn(paneId)}
                          showWorkflowActions={zoneId !== "open"}
                          canMutateData={canMutateData}
                          zoneId={zoneId}
                        />
                      </div>,
                    ];
                  })}
                </div>
              ))}
              {panes.flatMap((pane, paneIndex) => {
                const paneId = pane.id as WorkbenchRecordType;
                if (isSourceSegmentedPane(paneId, displaySegments)) {
                  return [];
                }
                return [
                  <div
                    key={`${group.id}-${pane.id}`}
                    className="candidate-group-pane-slot candidate-group-pane-slot-sheet"
                    style={{
                      gridColumn: paneIndex * 2 + 1,
                      gridRow: `1 / span ${segmentCount}`,
                    }}
                  >
                    {renderCollapseControls(paneId)}
                    <CandidateGroupCell
                      actionMode={actionMode}
                      columnGridStyle={paneGridStyleByPane[paneId]}
                      columns={columnsByPane[paneId]}
                      getRowState={getRowState}
                      highlightedRowId={highlightedRowId}
                      searchQuery={linkedSearchQuery || displayState.searchQueryByPane[paneId]}
                      onOpenDetail={onOpenDetail}
                      onRowAction={onRowAction}
                      onSelectRow={onSelectRow}
                      paneId={paneId}
                      records={group.rows[paneId]}
                      scrollPaneId={paneId}
                      scrollTestId={`candidate-scroll-${zoneId}-${group.id}-${pane.id}`}
                      showActionColumn={paneHasActionColumn(paneId)}
                      showWorkflowActions={zoneId !== "open"}
                      canMutateData={canMutateData}
                      zoneId={zoneId}
                    />
                  </div>,
                ];
              })}
              {panes.slice(0, -1).map((pane, paneIndex) => (
                <div
                  key={`${group.id}-${pane.id}-divider`}
                  className="candidate-pane-grid-divider"
                  aria-hidden="true"
                  style={{
                    gridColumn: paneIndex * 2 + 2,
                    gridRow: `1 / span ${segmentCount}`,
                  }}
                />
              ))}
              {hasTrailingColumns ? (
                <div
                  className="candidate-pane-grid-divider"
                  aria-hidden="true"
                  style={{
                    gridColumn: panes.length * 2,
                    gridRow: `1 / span ${segmentCount}`,
                  }}
                />
              ) : null}
              {trailingColumns.map((column, columnIndex) => (
                <div
                  key={`${group.id}-trailing-${column.key}`}
                  className={`candidate-group-trailing-cell${column.className ? ` ${column.className}` : ""}`}
                  role="cell"
                  style={{
                    gridColumn: panes.length * 2 + columnIndex + 1,
                    gridRow: `1 / span ${segmentCount}`,
                  }}
                >
                  {column.renderGroup(group)}
                </div>
              ))}
            </div>
          );
        }

        return (
          <div
            key={group.id}
            className={`candidate-group-row candidate-group-row-sheet candidate-group-row-tone-${index % 4}`}
            data-testid={`candidate-group-${zoneId}-${group.id}`}
            style={{ gridTemplateColumns: rowTemplateColumns }}
          >
            {panes.map((pane, paneIndex) => {
              const paneId = pane.id as WorkbenchRecordType;
              const collapsedRows = group.collapsedRows?.[paneId] ?? [];
              const isCollapsedSummary = group.displayMode === "collapsed_summary" && collapsedRows.length > 0;
              const collapseKey = `${group.id}:${paneId}`;
              const isExpanded = isCollapsedSummary && expandedCollapsedGroups.has(collapseKey);
              const visibleRecords = isExpanded ? collapsedRows : group.rows[paneId];
              return (
                <Fragment key={`${group.id}-${pane.id}`}>
                  <div className="candidate-group-pane-slot candidate-group-pane-slot-sheet">
                    {renderCollapseControls(paneId)}
                    <CandidateGroupCell
                      actionMode={actionMode}
                      columnGridStyle={paneGridStyleByPane[paneId]}
                      columns={columnsByPane[paneId]}
                      getRowState={getRowState}
                      highlightedRowId={highlightedRowId}
                      searchQuery={linkedSearchQuery || displayState.searchQueryByPane[paneId]}
                      onOpenDetail={onOpenDetail}
                      onRowAction={onRowAction}
                      onSelectRow={onSelectRow}
                      paneId={paneId}
                      records={visibleRecords}
                      scrollPaneId={paneId}
                      scrollTestId={`candidate-scroll-${zoneId}-${group.id}-${pane.id}`}
                      showActionColumn={paneHasActionColumn(paneId)}
                      showWorkflowActions={zoneId !== "open"}
                      canMutateData={canMutateData}
                      zoneId={zoneId}
                    />
                  </div>
                  {paneIndex < panes.length - 1 ? <div className="candidate-pane-grid-divider" aria-hidden="true" /> : null}
                </Fragment>
              );
            })}
            {hasTrailingColumns ? <div className="candidate-pane-grid-divider" aria-hidden="true" /> : null}
            {trailingColumns.map((column) => (
              <div
                key={`${group.id}-trailing-${column.key}`}
                className={`candidate-group-trailing-cell${column.className ? ` ${column.className}` : ""}`}
                role="cell"
              >
                {column.renderGroup(group)}
              </div>
            ))}
          </div>
        );
      })}
      {groups.length > 0 ? (
        <div className="candidate-grid-body-filler" aria-hidden="true" style={{ gridTemplateColumns: rowTemplateColumns }}>
          {panes.map((pane, paneIndex) => (
            <Fragment key={`body-filler-${pane.id}`}>
              <div className="candidate-group-pane-slot candidate-group-pane-slot-filler" />
              {paneIndex < panes.length - 1 ? <div className="candidate-pane-grid-divider candidate-pane-grid-divider-filler" /> : null}
            </Fragment>
          ))}
          {hasTrailingColumns ? <div className="candidate-pane-grid-divider candidate-pane-grid-divider-filler" /> : null}
          {trailingColumns.map((column) => (
            <div key={`body-filler-trailing-${column.key}`} className="candidate-group-trailing-cell candidate-group-trailing-cell-filler" />
          ))}
        </div>
      ) : null}
    </div>
  ), [
    actionMode,
    canMutateData,
    columnsByPane,
    displayState,
    expandedCollapsedGroups,
    getRowState,
    groups,
    highlightedRowId,
    loadingCollapsedGroups,
    linkedSearchQuery,
    onEnsureGroupDetail,
    onOpenDetail,
    onRowAction,
    onSelectRow,
    paneGridStyleByPane,
    panes,
    rowTemplateColumns,
    trailingColumns,
    toggleCollapsedGroup,
    zoneId,
  ]);

  return (
    <div ref={gridRef} className="candidate-grid">
      <div className="candidate-grid-head" style={{ gridTemplateColumns: rowTemplateColumns }}>
        {panes.map((pane, paneIndex) => (
          <Fragment key={pane.id}>
            <section className="candidate-pane-head pane-card" data-testid={`pane-${pane.id}`}>
              <div className="pane-header">
                <div className="pane-header-main">
                  {pane.id === "invoice" ? (
                    <InvoiceInventoryDiagnosticsTrigger title={pane.title} inventory={invoiceInventory} />
                  ) : (
                    <span>{pane.title}</span>
                  )}
                  <span>{pane.totalRows ?? pane.rows.length} 条</span>
                </div>
                <div className="pane-header-tools">
                  {pane.id === "bank" ? (
                    <WorkbenchPaneTimeFilter
                      availableYears={timeFilterYearsByPane.bank}
                      filter={displayState.timeFilterByPane.bank}
                      paneTitle={pane.title}
                      onChange={(filter) => onPaneTimeFilterChange(zoneId, "bank", filter)}
                    />
                  ) : null}
                  {pane.id === "oa" || pane.id === "bank" || pane.id === "invoice" ? (
                    (() => {
                      const sortPaneId: "oa" | "bank" | "invoice" = pane.id;
                      return (
                        <button
                          aria-label={buildPaneSortActionLabel(sortPaneId, displayState.sortByPane[sortPaneId])}
                          className={`pane-tool-btn pane-sort-btn${displayState.sortByPane[sortPaneId] ? " active" : ""}`}
                          type="button"
                          onClick={() => onTogglePaneSort(zoneId, sortPaneId)}
                        >
                          <span className="pane-sort-label">{buildPaneSortVisualLabel(displayState.sortByPane[sortPaneId])}</span>
                        </button>
                      );
                    })()
                  ) : null}
                  <WorkbenchPaneSearch
                    open={displayState.openSearchPaneId === pane.id}
                    appliedValue={displayState.searchQueryByPane[pane.id]}
                    draftValue={displayState.draftSearchQueryByPane[pane.id]}
                    paneTitle={pane.title}
                    onChange={(query) => onPaneSearchQueryChange(zoneId, pane.id, query)}
                    onClear={() => onClearPaneSearch(zoneId, pane.id)}
                    onClose={() => onClosePaneSearch(zoneId, pane.id)}
                    onToggle={() => onTogglePaneSearch(zoneId, pane.id)}
                  />
                </div>
              </div>
              <div
                className="candidate-pane-scroll"
                data-scroll-pane={pane.id}
                data-testid={`pane-scroll-head-${zoneId}-${pane.id}`}
                onScroll={(event) => handleSyncScroll(pane.id, event.currentTarget)}
              >
                <div
                  className={`candidate-pane-columnheaders candidate-pane-columnheaders-${pane.id} ${paneLayoutClass(pane.id)}`}
                  role="row"
                  style={paneGridStyleByPane[pane.id]}
                >
                  {columnsByPane[pane.id].map((column) => (
                    <div
                      aria-label={column.label}
                      key={column.key}
                      data-column-key={column.key}
                      data-pane-id={pane.id}
                      className={`candidate-columnheader cell-${column.kind ?? "text"}${column.className ? ` ${column.className}` : ""}`}
                      role="columnheader"
                    >
                      <span className="candidate-columnheader-main">
                        <button
                          aria-label={`拖动 ${column.label} 列`}
                          className="column-drag-handle"
                          disabled={!canMutateData}
                          type="button"
                          onPointerDown={(event) => handleStartColumnDrag(event, pane.id, column.key)}
                        >
                          <span className="column-drag-dots" aria-hidden="true">
                            <span />
                            <span />
                            <span />
                            <span />
                            <span />
                            <span />
                          </span>
                        </button>
                        <span className={`candidate-columnheader-label${column.headerLines ? " candidate-columnheader-label-lines" : ""}`}>
                          {column.headerLines
                            ? column.headerLines.map((line) => (
                              <span key={line} className="candidate-columnheader-label-line">
                                {line}
                              </span>
                            ))
                            : column.label}
                        </span>
                      </span>
                      {column.filterable === false ? null : (
                        <WorkbenchColumnFilterMenu
                          label={column.label}
                          open={openFilterMenu?.paneId === pane.id && openFilterMenu.columnKey === column.key}
                          options={filterOptionsByPane[pane.id][column.key] ?? []}
                          selectedValues={displayState.filtersByPaneAndColumn[pane.id][column.key] ?? []}
                          onClose={() => setOpenFilterMenu(null)}
                          onToggle={() => handleToggleFilterMenu(pane.id, column.key)}
                          onChange={(selectedValues) => onColumnFilterChange(zoneId, pane.id, column.key, selectedValues)}
                        />
                      )}
                    </div>
                  ))}
                  {paneHasActionColumn(pane.id) ? (
                    <div className="candidate-columnheader action-column" role="columnheader">
                      操作
                    </div>
                  ) : null}
                </div>
              </div>
            </section>
            {paneIndex < panes.length - 1 ? <div className="candidate-pane-grid-divider candidate-pane-grid-divider-head" aria-hidden="true" /> : null}
          </Fragment>
        ))}
        {hasTrailingColumns ? <div className="candidate-pane-grid-divider candidate-pane-grid-divider-head" aria-hidden="true" /> : null}
        {trailingColumns.map((column) => (
          <div
            aria-label={column.label}
            key={`head-trailing-${column.key}`}
            className={`candidate-columnheader candidate-trailing-columnheader${column.className ? ` ${column.className}` : ""}`}
            role="columnheader"
          >
            <span className="candidate-columnheader-label">{column.label}</span>
          </div>
        ))}
      </div>

      {gridBody}

      <div className="candidate-grid-footer" style={{ gridTemplateColumns: rowTemplateColumns }}>
        {panes.map((pane, paneIndex) => (
          <Fragment key={`footer-${pane.id}`}>
            <div className="candidate-pane-footer-slot">
              <div
                className="candidate-pane-footer-scroll"
                data-scroll-pane={pane.id}
                data-testid={`pane-scrollbar-${zoneId}-${pane.id}`}
                onScroll={(event) => handleSyncScroll(pane.id, event.currentTarget)}
              >
                <div
                  className={`candidate-pane-scrollbar-track candidate-pane-columnheaders-${pane.id} ${paneLayoutClass(pane.id)}`}
                  aria-hidden="true"
                  style={paneGridStyleByPane[pane.id]}
                >
                  {columnsByPane[pane.id].map((column) => (
                    <div key={column.key} className="candidate-scrollbar-track-cell" />
                  ))}
                  {paneHasActionColumn(pane.id) ? <div className="candidate-scrollbar-track-cell action-column" /> : null}
                </div>
              </div>
            </div>
            {paneIndex < panes.length - 1 ? <div className="candidate-pane-grid-divider candidate-pane-grid-divider-footer" aria-hidden="true" /> : null}
          </Fragment>
        ))}
        {hasTrailingColumns ? <div className="candidate-pane-grid-divider candidate-pane-grid-divider-footer" aria-hidden="true" /> : null}
        {trailingColumns.map((column) => (
          <div key={`footer-trailing-${column.key}`} className="candidate-pane-footer-slot candidate-trailing-footer-slot" />
        ))}
      </div>
    </div>
  );
}

export default memo(CandidateGroupGrid);

function hasDefaultRowActions(row: WorkbenchRecord) {
  return row.availableActions.some((action) => action !== "detail" && action !== "view_relation");
}

function isSourceSegmentedPane(paneId: WorkbenchRecordType, segments: ReturnType<typeof buildWorkbenchGroupDisplaySegments>) {
  if (paneId === "oa") {
    return true;
  }
  return Boolean(segments?.some((segment) => segment.rows[paneId].length > 0));
}

function buildPreviewDetailRequestKey(zoneId: "paired" | "open", group: WorkbenchCandidateGroup, panes: WorkbenchPane[]) {
  if (group.displayMode === "collapsed_summary") {
    return null;
  }
  const truncatedPaneSignatures = panes.flatMap((pane) => {
    const paneId = pane.id as WorkbenchRecordType;
    const visible = group.rows[paneId]?.length ?? 0;
    const total = group.rowCounts?.[paneId] ?? visible;
    return total > visible ? [`${paneId}:${visible}/${total}`] : [];
  });
  if (truncatedPaneSignatures.length === 0) {
    return null;
  }
  return `${zoneId}:${group.id}:${truncatedPaneSignatures.join("|")}`;
}

function clearPreviewDetailRequestKeys(zoneId: "paired" | "open", groupId: string, requestKeys: Set<string>) {
  const prefix = `${zoneId}:${groupId}:`;
  requestKeys.forEach((requestKey) => {
    if (requestKey.startsWith(prefix)) {
      requestKeys.delete(requestKey);
    }
  });
}

function buildPaneSortActionLabel(paneId: "oa" | "bank" | "invoice", currentDirection: "asc" | "desc" | null) {
  const paneTitle = paneId === "oa" ? "OA" : paneId === "bank" ? "银行流水" : "进销项发票";
  return `${paneTitle}按时间${currentDirection === "desc" ? "升序" : "降序"}`;
}

function buildPaneSortVisualLabel(currentDirection: "asc" | "desc" | null) {
  return currentDirection === "desc" ? "时间↑" : "时间↓";
}

const emptyInvoiceInventory: WorkbenchInvoiceInventory = {
  systemTotal: 0,
  manualImportTotal: 0,
  workbenchVisibleTotal: 0,
  hiddenSubmittedEtcTotal: 0,
  extraEtcTotal: 0,
  etcSummaryBatchCount: 0,
  oaAttachmentTotal: 0,
};

function InvoiceInventoryDiagnosticsTrigger({
  title,
  inventory,
}: {
  title: string;
  inventory: WorkbenchInvoiceInventory;
}) {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const [popoverStyle, setPopoverStyle] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const rows = buildInvoiceInventoryRows(inventory);
  const ariaLabel = `${title}库存统计：${rows.map((row) => `${row.label} ${row.value}`).join("，")}`;

  const syncPopoverPosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) {
      return;
    }
    const rect = trigger.getBoundingClientRect();
    setPopoverStyle({
      top: rect.bottom + 6,
      left: rect.left,
    });
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }
    syncPopoverPosition();
    const handleViewportChange = () => syncPopoverPosition();
    window.addEventListener("scroll", handleViewportChange, true);
    window.addEventListener("resize", handleViewportChange);
    return () => {
      window.removeEventListener("scroll", handleViewportChange, true);
      window.removeEventListener("resize", handleViewportChange);
    };
  }, [open, syncPopoverPosition]);

  return (
    <div
      className="pane-title-hover"
      onMouseEnter={() => {
        syncPopoverPosition();
        setOpen(true);
      }}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        ref={triggerRef}
        aria-label={ariaLabel}
        className="pane-title-hover-trigger"
        type="button"
        onFocus={() => {
          syncPopoverPosition();
          setOpen(true);
        }}
        onBlur={() => setOpen(false)}
      >
        {title}
      </button>
      <div
        className={`pane-title-hover-popover${open ? " is-open" : ""}`}
        role="tooltip"
        style={{ top: `${popoverStyle.top}px`, left: `${popoverStyle.left}px` }}
      >
        {rows.map((row) => (
          <div className="pane-title-hover-row" key={row.label}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function buildInvoiceInventoryRows(inventory: WorkbenchInvoiceInventory) {
  return [
    { label: "系统发票总数", value: inventory.systemTotal },
    { label: "人工导入总数", value: inventory.manualImportTotal },
    { label: "普通可见", value: inventory.workbenchVisibleTotal },
    { label: "已提交 ETC 隐藏", value: inventory.hiddenSubmittedEtcTotal },
    { label: "额外 ETC", value: inventory.extraEtcTotal },
    { label: "ETC 折叠批次", value: inventory.etcSummaryBatchCount },
    { label: "OA附件解析发票", value: inventory.oaAttachmentTotal },
  ];
}
