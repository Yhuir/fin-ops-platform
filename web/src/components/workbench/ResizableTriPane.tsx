import { Fragment, memo, useMemo, useRef } from "react";

import type { WorkbenchZoneDisplayState } from "../../features/workbench/groupDisplayModel";
import type {
  WorkbenchCandidateGroup,
  WorkbenchColumnLayouts,
  WorkbenchRecord,
  WorkbenchRecordType,
} from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import CandidateGroupGrid from "./CandidateGroupGrid";
import type { WorkbenchInlineAction } from "./RowActions";
import type { WorkbenchColumnDropPosition } from "../../features/workbench/columnLayout";

const COLLAPSE_EPSILON = 0.0001;

export type WorkbenchPane = {
  id: WorkbenchRecordType;
  title: string;
  rows: WorkbenchRecord[];
};

type ResizableTriPaneProps = {
  zoneId: "paired" | "open";
  panes: WorkbenchPane[];
  groups?: WorkbenchCandidateGroup[];
  sourceGroups?: WorkbenchCandidateGroup[];
  displayState: WorkbenchZoneDisplayState;
  columnLayouts?: WorkbenchColumnLayouts;
  widths: number[];
  visibleIndices: number[];
  onStartDrag: (leftIndex: number, rightIndex: number, clientX: number, containerWidth: number) => void;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "open") => WorkbenchRowState;
  highlightedRowId?: string | null;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "open") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  onTogglePaneSearch: (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice") => void;
  onPaneSearchQueryChange: (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice", query: string) => void;
  onColumnFilterChange: (
    zoneId: "paired" | "open",
    paneId: "oa" | "bank" | "invoice",
    columnKey: string,
    selectedValues: string[],
  ) => void;
  onTogglePaneSort: (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice") => void;
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
  onTogglePaneSearch,
  onPaneSearchQueryChange,
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

  const rowTemplateColumns = useMemo(
    () => visibleIndices.map((paneIndex) => `minmax(0, ${Math.max(widths[paneIndex], COLLAPSE_EPSILON)}fr)`).join(" "),
    [visibleIndices, widths],
  );
  const visiblePanes = visibleIndices.map((paneIndex) => panes[paneIndex]);
  const effectiveGroups = useMemo(() => groups ?? buildFallbackGroups(panes), [groups, panes]);

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
      <CandidateGroupGrid
        columnLayouts={columnLayouts}
        displayState={displayState}
        getRowState={getRowState}
        groups={effectiveGroups}
        highlightedRowId={highlightedRowId}
        onOpenDetail={onOpenDetail}
        onRowAction={onRowAction}
        onColumnFilterChange={onColumnFilterChange}
        onPaneSearchQueryChange={onPaneSearchQueryChange}
        onReorderPaneColumns={onReorderPaneColumns}
        onSelectRow={onSelectRow}
        onTogglePaneSearch={onTogglePaneSearch}
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

function buildFallbackGroups(panes: WorkbenchPane[]): WorkbenchCandidateGroup[] {
  const maxRows = Math.max(...panes.map((pane) => pane.rows.length), 0);
  return Array.from({ length: maxRows }, (_, index) => ({
    id: `fallback-${index + 1}`,
    groupType: "candidate",
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
