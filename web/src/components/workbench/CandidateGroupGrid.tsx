import { memo, useEffect, useMemo, useState, useCallback, useRef, type PointerEvent as ReactPointerEvent } from "react";

import {
  collectWorkbenchFilterOptions,
  createEmptyWorkbenchZoneDisplayState,
  type WorkbenchZoneDisplayState,
} from "../../features/workbench/groupDisplayModel";
import type {
  WorkbenchCandidateGroup,
  WorkbenchColumnLayouts,
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
import type { WorkbenchColumnDropPosition } from "../../features/workbench/columnLayout";

type CandidateGroupGridProps = {
  zoneId: "paired" | "open";
  panes: WorkbenchPane[];
  groups: WorkbenchCandidateGroup[];
  sourceGroups?: WorkbenchCandidateGroup[];
  displayState?: WorkbenchZoneDisplayState;
  columnLayouts?: WorkbenchColumnLayouts;
  rowTemplateColumns: string;
  actionMode?: "default" | "cancel-exception-only";
  highlightedRowId?: string | null;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "open") => WorkbenchRowState;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "open") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  onTogglePaneSearch?: (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice") => void;
  onPaneSearchQueryChange?: (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice", query: string) => void;
  onColumnFilterChange?: (
    zoneId: "paired" | "open",
    paneId: "oa" | "bank" | "invoice",
    columnKey: string,
    selectedValues: string[],
  ) => void;
  onTogglePaneSort?: (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice") => void;
  onReorderPaneColumns?: (
    paneId: "oa" | "bank" | "invoice",
    activeKey: string,
    overKey: string,
    position: WorkbenchColumnDropPosition,
  ) => void;
  canMutateData: boolean;
};

function CandidateGroupGrid({
  zoneId,
  panes,
  groups,
  sourceGroups,
  displayState = createEmptyWorkbenchZoneDisplayState(),
  columnLayouts,
  rowTemplateColumns,
  actionMode = "default",
  highlightedRowId,
  getRowState,
  onSelectRow,
  onOpenDetail,
  onRowAction,
  onTogglePaneSearch = () => undefined,
  onPaneSearchQueryChange = () => undefined,
  onColumnFilterChange = () => undefined,
  onTogglePaneSort = () => undefined,
  onReorderPaneColumns = () => undefined,
  canMutateData,
}: CandidateGroupGridProps) {
  const gridRef = useRef<HTMLDivElement | null>(null);
  const [openFilterMenu, setOpenFilterMenu] = useState<{ paneId: WorkbenchRecordType; columnKey: string } | null>(null);
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

  const paneHasActionColumn = (paneId: WorkbenchRecordType) => actionMode === "cancel-exception-only" || paneId === "invoice";
  const paneLayoutClass = (paneId: WorkbenchRecordType) =>
    paneHasActionColumn(paneId) ? "pane-layout-with-action" : "pane-layout-no-action";

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
    [columnLayouts, actionMode],
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

  const handleToggleFilterMenu = useCallback((paneId: WorkbenchRecordType, columnKey: string) => {
    setOpenFilterMenu((current) => (
      current?.paneId === paneId && current.columnKey === columnKey ? null : { paneId, columnKey }
    ));
  }, []);

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

  return (
    <div ref={gridRef} className="candidate-grid">
      <div className="candidate-grid-head" style={{ gridTemplateColumns: rowTemplateColumns }}>
        {panes.map((pane) => (
          <section key={pane.id} className="candidate-pane-head pane-card" data-testid={`pane-${pane.id}`}>
            <div className="pane-header">
              <div className="pane-header-main">
                <span>{pane.title}</span>
                <span>{pane.rows.length} 条</span>
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
                <WorkbenchPaneSearch
                  open={displayState.openSearchPaneId === pane.id}
                  paneTitle={pane.title}
                  value={displayState.searchQueryByPane[pane.id]}
                  onChange={(query) => onPaneSearchQueryChange(zoneId, pane.id, query)}
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
        ))}
      </div>

      <div className="candidate-grid-body">
        {groups.length === 0 ? <div className="state-panel">当前区域暂无候选组。</div> : null}
        {groups.map((group) => (
          <div
            key={group.id}
            className="candidate-group-row"
            data-testid={`candidate-group-${zoneId}-${group.id}`}
            style={{ gridTemplateColumns: rowTemplateColumns }}
          >
            {panes.map((pane) => (
              <div key={`${group.id}-${pane.id}`} className="candidate-group-pane-slot">
                <CandidateGroupCell
                  actionMode={actionMode}
                  columnGridStyle={paneGridStyleByPane[pane.id as WorkbenchRecordType]}
                  columns={columnsByPane[pane.id as WorkbenchRecordType]}
                  getRowState={getRowState}
                  highlightedRowId={highlightedRowId}
                  onOpenDetail={onOpenDetail}
                  onRowAction={onRowAction}
                  onSelectRow={onSelectRow}
                  paneId={pane.id as WorkbenchRecordType}
                  records={group.rows[pane.id as WorkbenchRecordType]}
                  scrollPaneId={pane.id as WorkbenchRecordType}
                  scrollTestId={`candidate-scroll-${zoneId}-${group.id}-${pane.id}`}
                  showWorkflowActions={zoneId !== "open"}
                  canMutateData={canMutateData}
                  zoneId={zoneId}
                />
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="candidate-grid-footer" style={{ gridTemplateColumns: rowTemplateColumns }}>
        {panes.map((pane) => (
          <div key={`footer-${pane.id}`} className="candidate-pane-footer-slot">
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
        ))}
      </div>
    </div>
  );
}

export default memo(CandidateGroupGrid);

function buildPaneSortActionLabel(paneId: "oa" | "bank" | "invoice", currentDirection: "asc" | "desc" | null) {
  const paneTitle = paneId === "oa" ? "OA" : paneId === "bank" ? "银行流水" : "进销项发票";
  return `${paneTitle}按时间${currentDirection === "desc" ? "升序" : "降序"}`;
}

function buildPaneSortVisualLabel(currentDirection: "asc" | "desc" | null) {
  return currentDirection === "desc" ? "时间↑" : "时间↓";
}
