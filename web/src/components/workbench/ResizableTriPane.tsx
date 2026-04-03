import { Fragment, useMemo, useRef } from "react";

import type { WorkbenchCandidateGroup, WorkbenchRecord, WorkbenchRecordType } from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import CandidateGroupGrid from "./CandidateGroupGrid";
import type { WorkbenchInlineAction } from "./RowActions";

export type WorkbenchPane = {
  id: WorkbenchRecordType;
  title: string;
  rows: WorkbenchRecord[];
};

type ResizableTriPaneProps = {
  zoneId: "paired" | "open";
  panes: WorkbenchPane[];
  groups?: WorkbenchCandidateGroup[];
  widths: number[];
  visibleIndices: number[];
  onStartDrag: (leftIndex: number, rightIndex: number, clientX: number, containerWidth: number) => void;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "open") => WorkbenchRowState;
  highlightedRowId?: string | null;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "open") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
};

export default function ResizableTriPane({
  zoneId,
  panes,
  groups,
  widths,
  visibleIndices,
  onStartDrag,
  getRowState,
  highlightedRowId,
  onSelectRow,
  onOpenDetail,
  onRowAction,
}: ResizableTriPaneProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const handleStartDrag = (leftIndex: number, rightIndex: number, clientX: number) => {
    onStartDrag(leftIndex, rightIndex, clientX, containerRef.current?.clientWidth ?? 1);
  };

  const headerTemplateColumns = useMemo(() => {
    return visibleIndices
      .flatMap((paneIndex, order) => {
        const parts = [`minmax(0, ${Math.max(widths[paneIndex], 0.0001)}fr)`];
        if (order < visibleIndices.length - 1) {
          parts.push("10px");
        }
        return parts;
      })
      .join(" ");
  }, [visibleIndices, widths]);

  const rowTemplateColumns = useMemo(
    () => visibleIndices.map((paneIndex) => `minmax(0, ${Math.max(widths[paneIndex], 0.0001)}fr)`).join(" "),
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
        getRowState={getRowState}
        groups={effectiveGroups}
        highlightedRowId={highlightedRowId}
        onOpenDetail={onOpenDetail}
        onRowAction={onRowAction}
        onSelectRow={onSelectRow}
        panes={visiblePanes}
        rowTemplateColumns={rowTemplateColumns}
        zoneId={zoneId}
      />
    </div>
  );
}

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
