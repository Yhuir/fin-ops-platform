import {
  Fragment,
  memo,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  useCallback,
  useRef,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";

import {
  buildWorkbenchGroupDisplayLayout,
  createEmptyWorkbenchZoneDisplayState,
  type WorkbenchZoneDisplayState,
} from "../../features/workbench/groupDisplayModel";
import type {
  WorkbenchRelationGroup,
  WorkbenchColumnLayouts,
  WorkbenchInvoiceInventory,
  WorkbenchRecord,
  WorkbenchRecordType,
  WorkbenchFilterOptionsLoader,
} from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import {
  getWorkbenchColumns,
  getWorkbenchPaneGridStyle,
} from "../../features/workbench/tableConfig";
import type { WorkbenchInlineAction } from "./RowActions";
import type { WorkbenchPane } from "./ResizableTriPane";
import RelationGroupCell from "./RelationGroupCell";
import WorkbenchAnomalyIndicator from "./WorkbenchAnomalyIndicator";
import WorkbenchColumnFilterMenu from "./WorkbenchColumnFilterMenu";
import type { WorkbenchColumnDropPosition } from "../../features/workbench/columnLayout";

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

type RelationGroupGridProps = {
  zoneId: "paired" | "unpaired";
  panes: WorkbenchPane[];
  groups: WorkbenchRelationGroup[];
  sourceGroups?: WorkbenchRelationGroup[];
  invoiceInventory?: WorkbenchInvoiceInventory;
  displayState?: WorkbenchZoneDisplayState;
  columnLayouts?: WorkbenchColumnLayouts;
  rowTemplateColumns: string;
  trailingColumns?: Array<{
    key: string;
    label: string;
    className?: string;
    renderGroup: (group: WorkbenchRelationGroup) => ReactNode;
  }>;
  highlightedRowId?: string | null;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "unpaired") => WorkbenchRowState;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "unpaired") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (
    row: WorkbenchRecord,
    action: WorkbenchInlineAction,
    group: WorkbenchRelationGroup,
  ) => void;
  onEnsureGroupDetail?: (zoneId: "paired" | "unpaired", groupId: string) => Promise<void>;
  canRequestNextPage?: boolean;
  onRequestNextPage?: (zoneId: "paired" | "unpaired") => void;
  loadFilterOptions?: WorkbenchFilterOptionsLoader;
  onColumnFilterChange?: (
    zoneId: "paired" | "unpaired",
    paneId: "oa" | "bank" | "invoice",
    columnKey: string,
    selectedValues: string[],
  ) => void;
  onTogglePaneSort?: (zoneId: "paired" | "unpaired", paneId: "oa" | "bank" | "invoice") => void;
  onReorderPaneColumns?: (
    paneId: "oa" | "bank" | "invoice",
    activeKey: string,
    overKey: string,
    position: WorkbenchColumnDropPosition,
  ) => void;
  canMutateData: boolean;
  readOnly?: boolean;
  allowInvoiceEntryInReadOnly?: boolean;
  hidePaneHeaders?: boolean;
};

type CollapsedSummaryCopy = {
  detailLabel: string;
  countUnit: string;
};

function isEtcInvoiceCollapse(
  group: WorkbenchRelationGroup,
  paneId: WorkbenchRecordType,
  collapsedRows: WorkbenchRecord[],
) {
  return paneId === "invoice" && (
    group.summaryRow?.sourceKind === "etc_invoice_summary"
    || collapsedRows.some((row) => row.sourceKind === "etc_invoice")
  );
}

function resolveCollapsedSummaryCopy(
  group: WorkbenchRelationGroup,
  paneId: WorkbenchRecordType,
  collapsedRows: WorkbenchRecord[],
): CollapsedSummaryCopy {
  if (isEtcInvoiceCollapse(group, paneId, collapsedRows)) {
    return {
      detailLabel: "ETC发票明细",
      countUnit: "张",
    };
  }
  if (group.relationMode === "bank_flow_rule_batch") {
    return {
      detailLabel: "流水规则批次明细",
      countUnit: "条",
    };
  }

  return {
    detailLabel: "折叠明细",
    countUnit: "条",
  };
}

function missingRequirementLabel(group: WorkbenchRelationGroup, paneId: WorkbenchRecordType) {
  if (!group.completion?.missingRecordTypes.includes(paneId)) {
    return null;
  }
  if (paneId === "oa") {
    return "待补 OA";
  }
  if (paneId === "invoice") {
    return "待补发票";
  }
  return "待补银行流水";
}

function RelationGroupGrid({
  zoneId,
  panes,
  groups,
  sourceGroups,
  invoiceInventory = emptyInvoiceInventory,
  displayState = createEmptyWorkbenchZoneDisplayState(),
  columnLayouts,
  rowTemplateColumns,
  trailingColumns = [],
  highlightedRowId,
  getRowState,
  onSelectRow,
  onOpenDetail,
  onRowAction,
  onEnsureGroupDetail,
  canRequestNextPage = false,
  onRequestNextPage,
  loadFilterOptions,
  onColumnFilterChange = () => undefined,
  onTogglePaneSort = () => undefined,
  onReorderPaneColumns = () => undefined,
  canMutateData,
  readOnly = false,
  allowInvoiceEntryInReadOnly = false,
  hidePaneHeaders = false,
}: RelationGroupGridProps) {
  const gridRef = useRef<HTMLDivElement | null>(null);
  const gridBodyRef = useRef<HTMLDivElement | null>(null);
  const nextPageSentinelRef = useRef<HTMLDivElement | null>(null);
  const [openFilterMenu, setOpenFilterMenu] = useState<{ paneId: WorkbenchRecordType; columnKey: string } | null>(null);
  const [expandedPaneGroups, setExpandedPaneGroups] = useState<Set<string>>(() => new Set());
  const [loadingPaneGroups, setLoadingPaneGroups] = useState<Set<string>>(() => new Set());
  const [failedPaneGroups, setFailedPaneGroups] = useState<Set<string>>(() => new Set());
  const searchGenerationRef = useRef(0);
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
  const scrollPositionsRef = useRef<Record<WorkbenchRecordType, { left: number; ratio: number | null }>>({
    oa: { left: 0, ratio: null },
    bank: { left: 0, ratio: null },
    invoice: { left: 0, ratio: null },
  });
  const normalizedSearchQuery = displayState.searchQuery.trim();
  useLayoutEffect(() => {
    searchGenerationRef.current += 1;
    setExpandedPaneGroups(new Set());
    setLoadingPaneGroups(new Set());
    setFailedPaneGroups(new Set());
  }, [normalizedSearchQuery]);

  useLayoutEffect(() => {
    setExpandedPaneGroups((current) => {
      if (current.size === 0) {
        return current;
      }
      const next = new Set(current);
      groups.forEach((group) => {
        panes.forEach((pane) => {
          const key = `${group.id}:${pane.id}`;
          const loadedRowCount = group.collapsedRows?.[pane.id]?.length ?? 0;
          const totalRowCount = group.collapsedRowCounts?.[pane.id] ?? loadedRowCount;
          if (next.has(key) && totalRowCount > loadedRowCount) {
            next.delete(key);
          }
        });
      });
      return next.size === current.size ? current : next;
    });
  }, [groups, panes]);

  useEffect(() => {
    const root = gridRef.current;
    if (!root) {
      return;
    }

    panes.forEach((pane) => {
      const scrollPosition = scrollPositionsRef.current[pane.id];
      root.querySelectorAll<HTMLElement>(`[data-scroll-pane="${pane.id}"]`).forEach((element) => {
        const maxScrollLeft = Math.max(0, element.scrollWidth - element.clientWidth);
        element.scrollLeft = scrollPosition.ratio === null
          ? scrollPosition.left
          : scrollPosition.ratio * maxScrollLeft;
      });
    });
  }, [groups, panes]);

  useEffect(() => {
    const root = gridBodyRef.current;
    const sentinel = nextPageSentinelRef.current;
    if (
      !canRequestNextPage
      || !onRequestNextPage
      || !root
      || !sentinel
      || typeof IntersectionObserver === "undefined"
    ) {
      return undefined;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        onRequestNextPage(zoneId);
      }
    }, {
      root,
      rootMargin: "0px 0px 200px 0px",
    });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [canRequestNextPage, onRequestNextPage, zoneId]);

  const handleSyncScroll = (paneId: WorkbenchRecordType, element: HTMLDivElement) => {
    const maxScrollLeft = Math.max(0, element.scrollWidth - element.clientWidth);
    const ratio = maxScrollLeft > 0 ? element.scrollLeft / maxScrollLeft : null;
    scrollPositionsRef.current[paneId] = { left: element.scrollLeft, ratio };
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
        const candidateMaxScrollLeft = Math.max(0, candidate.scrollWidth - candidate.clientWidth);
        candidate.scrollLeft = ratio === null
          ? element.scrollLeft
          : ratio * candidateMaxScrollLeft;
      }
    });
    queueMicrotask(() => {
      syncInFlightRef.current[paneId] = false;
    });
  };

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
      oa: getWorkbenchPaneGridStyle("oa", columnLayouts),
      bank: getWorkbenchPaneGridStyle("bank", columnLayouts),
      invoice: getWorkbenchPaneGridStyle("invoice", columnLayouts),
    }),
    [columnLayouts],
  );

  const sourceGroupById = useMemo(
    () => new Map((sourceGroups ?? groups).map((group) => [group.id, group])),
    [groups, sourceGroups],
  );

  const handleOpenFilterMenu = useCallback((paneId: WorkbenchRecordType, columnKey: string) => {
    setOpenFilterMenu({ paneId, columnKey });
  }, []);

  const setPaneGroupExpanded = useCallback((groupId: string, paneId: WorkbenchRecordType, expanded: boolean) => {
    const key = `${groupId}:${paneId}`;
    setExpandedPaneGroups((current) => {
      const next = new Set(current);
      if (expanded) {
        next.add(key);
      } else {
        next.delete(key);
      }
      return next;
    });
  }, []);

  const togglePaneGroupExpansion = useCallback(async (
    group: WorkbenchRelationGroup,
    paneId: WorkbenchRecordType,
    isExpanded: boolean,
    totalRowCount: number,
    visibleRowCount: number,
  ) => {
    const key = `${group.id}:${paneId}`;
    const searchGeneration = searchGenerationRef.current;
    if (isExpanded) {
      setPaneGroupExpanded(group.id, paneId, false);
      return;
    }
    if (totalRowCount > visibleRowCount) {
      if (!onEnsureGroupDetail) {
        return;
      }
      setFailedPaneGroups((current) => {
        const next = new Set(current);
        next.delete(key);
        return next;
      });
      setLoadingPaneGroups((current) => new Set(current).add(key));
      try {
        await onEnsureGroupDetail(zoneId, group.id);
      } catch (error) {
        if (!isAbortError(error) && searchGenerationRef.current === searchGeneration) {
          setFailedPaneGroups((current) => new Set(current).add(key));
        }
        return;
      } finally {
        if (searchGenerationRef.current === searchGeneration) {
          setLoadingPaneGroups((current) => {
            const next = new Set(current);
            next.delete(key);
            return next;
          });
        }
      }
    }
    if (searchGenerationRef.current !== searchGeneration) {
      return;
    }
    setPaneGroupExpanded(group.id, paneId, true);
  }, [onEnsureGroupDetail, setPaneGroupExpanded, zoneId]);

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
    <div ref={gridBodyRef} className="candidate-grid-body" role="rowgroup">
      {groups.length === 0 ? <div className="state-panel">当前区域暂无记录。</div> : null}
      {groups.map((group, index) => {
        const paneIsCollapsed = (paneId: WorkbenchRecordType) => (
          (group.collapsedRowCounts?.[paneId] ?? 0) > 0
          || (group.collapsedRows?.[paneId]?.length ?? 0) > 0
        );
        const paneRecords = (paneId: WorkbenchRecordType) => {
          const collapsedRows = group.collapsedRows?.[paneId] ?? [];
          if (!paneIsCollapsed(paneId)) {
            return group.rows[paneId];
          }
          const collapseKey = `${group.id}:${paneId}`;
          if (expandedPaneGroups.has(collapseKey)) {
            return collapsedRows;
          }
          return group.summaryRow?.recordType === paneId ? [group.summaryRow] : [];
        };
        const renderCollapseControls = (paneId: WorkbenchRecordType): ReactNode => {
          const collapsedRows = group.collapsedRows?.[paneId] ?? [];
          if (!paneIsCollapsed(paneId)) {
            return null;
          }
          const collapseKey = `${group.id}:${paneId}`;
          const isExpanded = expandedPaneGroups.has(collapseKey);
          const isLoading = loadingPaneGroups.has(collapseKey);
          const isFailed = failedPaneGroups.has(collapseKey);
          const rowTotal = group.collapsedRowCounts?.[paneId] ?? collapsedRows.length;
          const visibleRowCount = collapsedRows.length;
          const collapseCopy = resolveCollapsedSummaryCopy(group, paneId, collapsedRows);
          const isEtcInvoice = isEtcInvoiceCollapse(group, paneId, collapsedRows);
          return (
            <Fragment>
              <button
                aria-expanded={isExpanded}
                aria-label={
                  isExpanded
                    ? isEtcInvoice ? "收起ETC发票" : `收起${collapseCopy.detailLabel}`
                    : isFailed
                      ? `加载${collapseCopy.detailLabel}失败，点击重试`
                      : isEtcInvoice
                        ? `展开全部ETC发票，共 ${rowTotal} 张`
                        : `展开${collapseCopy.detailLabel}，${rowTotal} ${collapseCopy.countUnit}`
                }
                className="row-action-btn candidate-group-collapse-control"
                disabled={isLoading}
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  void togglePaneGroupExpansion(group, paneId, isExpanded, rowTotal, visibleRowCount);
                }}
              >
                {isLoading
                  ? "加载中"
                  : isExpanded
                    ? isEtcInvoice ? "收起发票" : "收起明细"
                    : isFailed
                      ? "加载失败，点击重试"
                      : isEtcInvoice
                        ? `展开全部 ${rowTotal} 张发票`
                        : `展开 ${rowTotal} ${collapseCopy.countUnit}明细`}
              </button>
            </Fragment>
          );
        };
        const displayLayout = buildWorkbenchGroupDisplayLayout(group, sourceGroupById.get(group.id) ?? group);
        const displaySegments = displayLayout?.segments ?? null;
        const segmentCount = displaySegments?.length ?? 0;
        const segmentedPaneIds = new Set(displayLayout?.segmentedPaneIds ?? []);
        const visibleAnomalyFingerprints = new Set(
          panes.flatMap((pane) => {
            const paneId = pane.id as WorkbenchRecordType;
            const visibleRows = displaySegments && segmentedPaneIds.has(paneId)
              ? displaySegments.flatMap((segment) => segment.rows[paneId])
              : paneRecords(paneId);
            return visibleRows.flatMap((row) => [
              ...(row.workbenchAnomalies ?? []).map((item) => item.fingerprint),
              ...(row.expenseItems ?? []).flatMap((expenseItem) => (
                expenseItem.workbenchAnomalies ?? []
              )).map((item) => item.fingerprint),
            ]);
          }),
        );
        const groupLevelAnomalies = (group.workbenchAnomaly?.items ?? []).filter((item) => (
          item.displayScope === "group" || !visibleAnomalyFingerprints.has(item.fingerprint)
        ));

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
                    if (!segmentedPaneIds.has(paneId)) {
                      return [];
                    }
                    return [
                      <div
                        key={`${group.id}-${segment.id}-${pane.id}`}
                        className={`candidate-group-pane-slot candidate-group-pane-slot-sheet candidate-group-segment-pane-slot${segmentIndex === 0 ? " first" : ""}`}
                        data-pane-id={paneId}
                        style={{
                          gridColumn: paneIndex * 2 + 1,
                          gridRow: segmentIndex + 1,
                        }}
                      >
                        <RelationGroupCell
                          columnGridStyle={paneGridStyleByPane[paneId]}
                          columns={columnsByPane[paneId]}
                          getRowState={getRowState}
                          highlightedRowId={highlightedRowId}
                          leadingControl={segmentIndex === 0 ? renderCollapseControls(paneId) : null}
                          searchQuery={displayState.searchQuery}
                          onOpenDetail={onOpenDetail}
                          onRowAction={(row, action) => onRowAction(row, action, group)}
                          onSelectRow={onSelectRow}
                          paneId={paneId}
                          records={segment.rows[paneId]}
                          scrollPaneId={paneId}
                          scrollTestId={`candidate-scroll-${zoneId}-${group.id}-${segment.id}-${pane.id}`}
                          showWorkflowActions={zoneId !== "unpaired"}
                          canMutateData={canMutateData}
                          readOnly={readOnly}
                          allowInvoiceEntryInReadOnly={allowInvoiceEntryInReadOnly}
                          zoneId={zoneId}
                        />
                      </div>,
                    ];
                  })}
                </div>
              ))}
              {panes.flatMap((pane, paneIndex) => {
                const paneId = pane.id as WorkbenchRecordType;
                if (segmentedPaneIds.has(paneId)) {
                  return [];
                }
                return [
                  <div
                    key={`${group.id}-${pane.id}`}
                    className="candidate-group-pane-slot candidate-group-pane-slot-sheet"
                    data-pane-id={paneId}
                    style={{
                      gridColumn: paneIndex * 2 + 1,
                      gridRow: `1 / span ${segmentCount}`,
                    }}
                  >
                    <RelationGroupCell
                      columnGridStyle={paneGridStyleByPane[paneId]}
                      columns={columnsByPane[paneId]}
                      getRowState={getRowState}
                      highlightedRowId={highlightedRowId}
                      leadingControl={renderCollapseControls(paneId)}
                      searchQuery={displayState.searchQuery}
                      onOpenDetail={onOpenDetail}
                      onRowAction={(row, action) => onRowAction(row, action, group)}
                      onSelectRow={onSelectRow}
                      paneId={paneId}
                      records={paneRecords(paneId)}
                      scrollPaneId={paneId}
                      scrollTestId={`candidate-scroll-${zoneId}-${group.id}-${pane.id}`}
                      showWorkflowActions={zoneId !== "unpaired"}
                      canMutateData={canMutateData}
                      readOnly={readOnly}
                      allowInvoiceEntryInReadOnly={allowInvoiceEntryInReadOnly}
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
                  style={{
                    gridColumn: panes.length * 2 + columnIndex + 1,
                    gridRow: `1 / span ${segmentCount}`,
                  }}
                >
                  {column.renderGroup(group)}
                </div>
              ))}
              {groupLevelAnomalies.length > 0 ? (
                <WorkbenchAnomalyIndicator
                  anomalies={groupLevelAnomalies}
                  className="workbench-anomaly-indicator--group"
                  levelLabel="该关联组"
                />
              ) : null}
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
              const requirementLabel = missingRequirementLabel(group, paneId);
              return (
                <Fragment key={`${group.id}-${pane.id}`}>
                  <div className="candidate-group-pane-slot candidate-group-pane-slot-sheet" data-pane-id={paneId}>
                    {requirementLabel ? (
                      <span
                        aria-label={requirementLabel}
                        className="candidate-group-missing-requirement"
                        role="status"
                      >
                        {requirementLabel}
                      </span>
                    ) : null}
                    <RelationGroupCell
                      columnGridStyle={paneGridStyleByPane[paneId]}
                      columns={columnsByPane[paneId]}
                      getRowState={getRowState}
                      highlightedRowId={highlightedRowId}
                      leadingControl={renderCollapseControls(paneId)}
                      searchQuery={displayState.searchQuery}
                      onOpenDetail={onOpenDetail}
                      onRowAction={(row, action) => onRowAction(row, action, group)}
                      onSelectRow={onSelectRow}
                      paneId={paneId}
                      records={paneRecords(paneId)}
                      scrollPaneId={paneId}
                      scrollTestId={`candidate-scroll-${zoneId}-${group.id}-${pane.id}`}
                      showWorkflowActions={zoneId !== "unpaired"}
                      canMutateData={canMutateData}
                      readOnly={readOnly}
                      allowInvoiceEntryInReadOnly={allowInvoiceEntryInReadOnly}
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
              >
                {column.renderGroup(group)}
              </div>
            ))}
            {groupLevelAnomalies.length > 0 ? (
              <WorkbenchAnomalyIndicator
                anomalies={groupLevelAnomalies}
                className="workbench-anomaly-indicator--group"
                levelLabel="该关联组"
              />
            ) : null}
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
      <div ref={nextPageSentinelRef} aria-hidden="true" className="candidate-grid-end-sentinel" />
    </div>
  ), [
    allowInvoiceEntryInReadOnly,
    canMutateData,
    columnsByPane,
    displayState,
    expandedPaneGroups,
    failedPaneGroups,
    getRowState,
    groups,
    highlightedRowId,
    loadingPaneGroups,
    displayState.searchQuery,
    onEnsureGroupDetail,
    onOpenDetail,
    onRowAction,
    onSelectRow,
    paneGridStyleByPane,
    panes,
    rowTemplateColumns,
    readOnly,
    sourceGroupById,
    trailingColumns,
    togglePaneGroupExpansion,
    zoneId,
  ]);

  return (
    <div
      ref={gridRef}
      aria-label={`${zoneId === "paired" ? "已配对" : "未配对"}三栏关联表`}
      className="candidate-grid"
      role="grid"
    >
      {!hidePaneHeaders ? <div className="candidate-grid-head" role="rowgroup" style={{ gridTemplateColumns: rowTemplateColumns }}>
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
                </div>
              </div>
              <div
                className="candidate-pane-scroll"
                data-scroll-pane={pane.id}
                data-testid={`pane-scroll-head-${zoneId}-${pane.id}`}
                onScroll={(event) => handleSyncScroll(pane.id, event.currentTarget)}
              >
                <div
                  className={`candidate-pane-columnheaders candidate-pane-columnheaders-${pane.id}`}
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
                          columnKey={column.key}
                          label={column.label}
                          loadFilterOptions={loadFilterOptions}
                          open={openFilterMenu?.paneId === pane.id && openFilterMenu.columnKey === column.key}
                          paneId={pane.id}
                          selectedValues={displayState.filtersByPaneAndColumn[pane.id][column.key] ?? []}
                          zoneId={zoneId}
                          onClose={() => setOpenFilterMenu(null)}
                          onOpen={() => handleOpenFilterMenu(pane.id, column.key)}
                          onChange={(selectedValues) => onColumnFilterChange(zoneId, pane.id, column.key, selectedValues)}
                        />
                      )}
                    </div>
                  ))}
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
          >
            <span className="candidate-columnheader-label">{column.label}</span>
          </div>
        ))}
      </div> : null}

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
                  className={`candidate-pane-scrollbar-track candidate-pane-columnheaders-${pane.id}`}
                  aria-hidden="true"
                  style={paneGridStyleByPane[pane.id]}
                >
                  {columnsByPane[pane.id].map((column) => (
                    <div key={column.key} className="candidate-scrollbar-track-cell" />
                  ))}
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

export default memo(RelationGroupGrid);

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
