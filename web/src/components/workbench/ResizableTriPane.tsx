import { Fragment, memo, useMemo, useRef } from "react";

import type { WorkbenchZoneDisplayState } from "../../features/workbench/groupDisplayModel";
import type {
  WorkbenchRelationGroup,
  WorkbenchColumnLayouts,
  WorkbenchInvoiceInventory,
  WorkbenchRecord,
  WorkbenchRecordType,
  WorkbenchFilterOptionsLoader,
} from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import RelationGroupGrid from "./RelationGroupGrid";
import type { WorkbenchInlineAction } from "./RowActions";
import type { WorkbenchColumnDropPosition } from "../../features/workbench/columnLayout";

const COLLAPSE_EPSILON = 0.0001;

export type WorkbenchPane = {
  id: WorkbenchRecordType;
  title: string;
  rows: WorkbenchRecord[];
  totalRows?: number;
};

type ResizableTriPaneProps = {
  zoneId: "paired" | "unpaired";
  panes: WorkbenchPane[];
  groups?: WorkbenchRelationGroup[];
  sourceGroups?: WorkbenchRelationGroup[];
  invoiceInventory?: WorkbenchInvoiceInventory;
  displayState: WorkbenchZoneDisplayState;
  columnLayouts?: WorkbenchColumnLayouts;
  widths: number[];
  visibleIndices: number[];
  onStartDrag: (leftIndex: number, rightIndex: number, clientX: number, containerWidth: number) => void;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "unpaired") => WorkbenchRowState;
  highlightedRowId?: string | null;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "unpaired") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  onEnsureGroupDetail?: (zoneId: "paired" | "unpaired", groupId: string) => Promise<void>;
  canRequestNextPage?: boolean;
  onRequestNextPage?: (zoneId: "paired" | "unpaired") => void;
  loadFilterOptions?: WorkbenchFilterOptionsLoader;
  onColumnFilterChange: (
    zoneId: "paired" | "unpaired",
    paneId: "oa" | "bank" | "invoice",
    columnKey: string,
    selectedValues: string[],
  ) => void;
  onTogglePaneSort: (zoneId: "paired" | "unpaired", paneId: "oa" | "bank" | "invoice") => void;
  onReorderPaneColumns: (
    paneId: "oa" | "bank" | "invoice",
    activeKey: string,
    overKey: string,
    position: WorkbenchColumnDropPosition,
  ) => void;
  canMutateData: boolean;
};

function ResizableTriPane({
  zoneId,
  panes,
  groups,
  sourceGroups,
  invoiceInventory,
  displayState,
  columnLayouts,
  widths,
  visibleIndices,
  onStartDrag,
  getRowState,
  highlightedRowId,
  onSelectRow,
  onOpenDetail,
  onRowAction,
  onEnsureGroupDetail,
  canRequestNextPage = false,
  onRequestNextPage,
  loadFilterOptions,
  onColumnFilterChange,
  onTogglePaneSort,
  onReorderPaneColumns,
  canMutateData,
}: ResizableTriPaneProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const handleStartDrag = (leftIndex: number, rightIndex: number, clientX: number) => {
    onStartDrag(leftIndex, rightIndex, clientX, containerRef.current?.clientWidth ?? 1);
  };

  const headerTemplateColumns = useMemo(() => {
    return visibleIndices
      .flatMap((paneIndex, order) => {
        const parts = [`minmax(0, ${Math.max(widths[paneIndex], COLLAPSE_EPSILON)}fr)`];
        if (order < visibleIndices.length - 1) {
          parts.push("10px");
        }
        return parts;
      })
      .join(" ");
  }, [visibleIndices, widths]);

  const rowTemplateColumns = headerTemplateColumns;
  const visiblePanes = visibleIndices.map((paneIndex) => panes[paneIndex]);
  const effectiveGroups = useMemo(() => groups ?? buildFallbackGroups(panes, zoneId), [groups, panes, zoneId]);

  return (
    <div
      ref={containerRef}
      className="resizable-tri-pane"
      data-testid="tri-pane"
    >
      <div className="candidate-grid-splitters" style={{ gridTemplateColumns: headerTemplateColumns }}>
        {visibleIndices.map((paneIndex, order) => {
          const pane = panes[paneIndex];
          const nextPaneIndex = visibleIndices[order + 1];

          return (
            <Fragment key={pane.id}>
              <div className="pane-header-slot" />
              {nextPaneIndex !== undefined ? (
                <div
                  aria-orientation="vertical"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  className="pane-splitter"
                  role="separator"
                  onMouseDown={(event) => handleStartDrag(paneIndex, nextPaneIndex, event.clientX)}
                  onPointerDown={(event) => handleStartDrag(paneIndex, nextPaneIndex, event.clientX)}
                />
              ) : null}
            </Fragment>
          );
        })}
      </div>
      <RelationGroupGrid
        columnLayouts={columnLayouts}
        displayState={displayState}
        getRowState={getRowState}
        groups={effectiveGroups}
        highlightedRowId={highlightedRowId}
        invoiceInventory={invoiceInventory}
        loadFilterOptions={loadFilterOptions}
        onOpenDetail={onOpenDetail}
        onRowAction={onRowAction}
        onEnsureGroupDetail={onEnsureGroupDetail}
        canRequestNextPage={canRequestNextPage}
        onRequestNextPage={onRequestNextPage}
        onColumnFilterChange={onColumnFilterChange}
        onReorderPaneColumns={onReorderPaneColumns}
        onSelectRow={onSelectRow}
        onTogglePaneSort={onTogglePaneSort}
        panes={visiblePanes}
        rowTemplateColumns={rowTemplateColumns}
        sourceGroups={sourceGroups ?? effectiveGroups}
        canMutateData={canMutateData}
        zoneId={zoneId}
      />
    </div>
  );
}

export default memo(ResizableTriPane);

function buildFallbackGroups(panes: WorkbenchPane[], zoneId: "paired" | "unpaired"): WorkbenchRelationGroup[] {
  const maxRows = Math.max(...panes.map((pane) => pane.rows.length), 0);
  return Array.from({ length: maxRows }, (_, index) => ({
    id: `fallback-${index + 1}`,
    groupType: zoneId,
    rawGroupType: "fallback_pane_alignment",
    matchConfidence: "medium",
    reason: "fallback_pane_alignment",
    rows: {
      oa: panes.find((pane) => pane.id === "oa")?.rows[index] ? [panes.find((pane) => pane.id === "oa")!.rows[index]] : [],
      bank: panes.find((pane) => pane.id === "bank")?.rows[index]
        ? [panes.find((pane) => pane.id === "bank")!.rows[index]]
        : [],
      invoice: panes.find((pane) => pane.id === "invoice")?.rows[index]
        ? [panes.find((pane) => pane.id === "invoice")!.rows[index]]
        : [],
    },
  }));
}
