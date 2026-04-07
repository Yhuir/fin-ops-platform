import { useEffect, useRef } from "react";

import type { WorkbenchCandidateGroup, WorkbenchRecord, WorkbenchRecordType } from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import { workbenchColumns } from "../../features/workbench/tableConfig";
import type { WorkbenchInlineAction } from "./RowActions";
import type { WorkbenchPane } from "./ResizableTriPane";
import CandidateGroupCell from "./CandidateGroupCell";

type CandidateGroupGridProps = {
  zoneId: "paired" | "open";
  panes: WorkbenchPane[];
  groups: WorkbenchCandidateGroup[];
  rowTemplateColumns: string;
  actionMode?: "default" | "cancel-exception-only";
  highlightedRowId?: string | null;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "open") => WorkbenchRowState;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "open") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  canMutateData: boolean;
};

export default function CandidateGroupGrid({
  zoneId,
  panes,
  groups,
  rowTemplateColumns,
  actionMode = "default",
  highlightedRowId,
  getRowState,
  onSelectRow,
  onOpenDetail,
  onRowAction,
  canMutateData,
}: CandidateGroupGridProps) {
  const gridRef = useRef<HTMLDivElement | null>(null);
  const syncInFlightRef = useRef<Record<WorkbenchRecordType, boolean>>({
    oa: false,
    bank: false,
    invoice: false,
  });
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

  return (
    <div ref={gridRef} className="candidate-grid">
      <div className="candidate-grid-head" style={{ gridTemplateColumns: rowTemplateColumns }}>
        {panes.map((pane) => (
          <section key={pane.id} className="candidate-pane-head pane-card" data-testid={`pane-${pane.id}`}>
            <div className="pane-header">
              <span>{pane.title}</span>
              <span>{pane.rows.length} 条</span>
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
              >
                {workbenchColumns[pane.id].map((column) => (
                  <div
                    key={column.key}
                    className={`candidate-columnheader cell-${column.kind ?? "text"}${column.className ? ` ${column.className}` : ""}`}
                    role="columnheader"
                  >
                    {column.label}
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
              >
                {workbenchColumns[pane.id].map((column) => (
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
