import { memo, useEffect, useMemo, useState, useCallback, useRef, type PointerEvent as ReactPointerEvent } from "react";

import {
  collectWorkbenchFilterOptions,
  collectWorkbenchTimeFilterYears,
  createEmptyWorkbenchZoneDisplayState,
  type WorkbenchPaneTimeFilter as WorkbenchPaneTimeFilterState,
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
import WorkbenchPaneTimeFilter from "./WorkbenchPaneTimeFilter";
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

  const timeFilterYearsByPane = useMemo(() => {
    const filterSourceGroups = sourceGroups ?? groups;
    return {
      oa: collectWorkbenchTimeFilterYears(filterSourceGroups, "oa"),
      bank: collectWorkbenchTimeFilterYears(filterSourceGroups, "bank"),
      invoice: collectWorkbenchTimeFilterYears(filterSourceGroups, "invoice"),
    } satisfies Record<WorkbenchRecordType, string[]>;
  }, [groups, sourceGroups]);

  const invoiceAttachmentDiagnostics = useMemo(
    () => buildInvoiceAttachmentDiagnostics(groups),
    [groups],
  );

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

  const gridBody = useMemo(() => (
    <div className="candidate-grid-body">
      {groups.length === 0 ? <div className="state-panel">当前区域暂无候选组。</div> : null}
      {groups.map((group, index) => (
        <div
          key={group.id}
          className={`candidate-group-row candidate-group-row-sheet candidate-group-row-tone-${index % 4}`}
          data-testid={`candidate-group-${zoneId}-${group.id}`}
          style={{ gridTemplateColumns: rowTemplateColumns }}
        >
          {panes.map((pane) => (
            <div key={`${group.id}-${pane.id}`} className="candidate-group-pane-slot candidate-group-pane-slot-sheet">
              <CandidateGroupCell
                actionMode={actionMode}
                columnGridStyle={paneGridStyleByPane[pane.id as WorkbenchRecordType]}
                columns={columnsByPane[pane.id as WorkbenchRecordType]}
                getRowState={getRowState}
                highlightedRowId={highlightedRowId}
                searchQuery={displayState.unifiedSearchQuery}
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
  ), [
    actionMode,
    canMutateData,
    columnsByPane,
    getRowState,
    groups,
    highlightedRowId,
    onOpenDetail,
    onRowAction,
    onSelectRow,
    paneGridStyleByPane,
    panes,
    rowTemplateColumns,
    zoneId,
  ]);

  return (
    <div ref={gridRef} className="candidate-grid">
      <div className="candidate-grid-head" style={{ gridTemplateColumns: rowTemplateColumns }}>
        {panes.map((pane) => (
          <section key={pane.id} className="candidate-pane-head pane-card" data-testid={`pane-${pane.id}`}>
            <div className="pane-header">
              <div className="pane-header-main">
                {pane.id === "invoice" ? (
                  <InvoiceAttachmentDiagnosticsTrigger title={pane.title} diagnostics={invoiceAttachmentDiagnostics} />
                ) : (
                  <span>{pane.title}</span>
                )}
                <span>{pane.rows.length} 条</span>
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
        ))}
      </div>

      {gridBody}

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

type InvoiceAttachmentDiagnostics = {
  oaAttachmentCount: number;
  parsedOaInvoiceCount: number;
  importedInvoiceCount: number;
};

function InvoiceAttachmentDiagnosticsTrigger({
  title,
  diagnostics,
}: {
  title: string;
  diagnostics: InvoiceAttachmentDiagnostics;
}) {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const [popoverStyle, setPopoverStyle] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

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
        aria-label={`${title}附件统计：OA附件 ${diagnostics.oaAttachmentCount}，已解析 ${diagnostics.parsedOaInvoiceCount}，已导入 ${diagnostics.importedInvoiceCount}`}
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
        <div className="pane-title-hover-row">
          <span>OA里的发票附件数量</span>
          <strong>{diagnostics.oaAttachmentCount}</strong>
        </div>
        <div className="pane-title-hover-row">
          <span>已解析的OA发票数量</span>
          <strong>{diagnostics.parsedOaInvoiceCount}</strong>
        </div>
        <div className="pane-title-hover-row">
          <span>已导入的发票数量</span>
          <strong>{diagnostics.importedInvoiceCount}</strong>
        </div>
      </div>
    </div>
  );
}

function buildInvoiceAttachmentDiagnostics(groups: WorkbenchCandidateGroup[]): InvoiceAttachmentDiagnostics {
  const oaAttachmentRows = groups
    .flatMap((group) => group.rows.oa)
    .filter((row) => {
      const recognition = parseAttachmentRecognitionStatus(detailFieldValue(row, "附件发票识别情况"));
      if (recognition !== null) {
        return recognition.total > 0;
      }
      const parsedCount = parseInteger(detailFieldValue(row, "附件发票数量"));
      return parsedCount !== null && parsedCount > 0;
    });
  const parsedOaInvoiceCount = groups
    .flatMap((group) => group.rows.invoice)
    .filter((row) => row.sourceKind === "oa_attachment_invoice")
    .length;
  const importedInvoiceCount = groups
    .flatMap((group) => group.rows.invoice)
    .filter((row) => row.sourceKind !== "oa_attachment_invoice")
    .length;
  const oaAttachmentCount = oaAttachmentRows.length;

  return {
    oaAttachmentCount,
    parsedOaInvoiceCount,
    importedInvoiceCount,
  };
}

function detailFieldValue(row: WorkbenchRecord, label: string) {
  return row.detailFields.find((field) => field.label === label)?.value ?? "";
}

function parseAttachmentRecognitionStatus(value: string) {
  const match = value.match(/(\d+)\s*\/\s*(\d+)/);
  if (!match) {
    return null;
  }
  return {
    parsed: Number.parseInt(match[1], 10),
    total: Number.parseInt(match[2], 10),
  };
}

function parseInteger(value: string) {
  const trimmedValue = value.trim();
  if (!/^\d+$/.test(trimmedValue)) {
    return null;
  }
  return Number.parseInt(trimmedValue, 10);
}
