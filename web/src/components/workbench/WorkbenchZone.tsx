import ResizableTriPane, { type WorkbenchPane } from "./ResizableTriPane";
import { useResizablePanes } from "../../hooks/useResizablePanes";
import type { WorkbenchCandidateGroup, WorkbenchRecord } from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import type { WorkbenchInlineAction } from "./RowActions";

type WorkbenchZoneProps = {
  zoneId: "paired" | "open";
  title: string;
  tone: "success" | "warning";
  meta: string;
  panes: WorkbenchPane[];
  groups?: WorkbenchCandidateGroup[];
  isExpanded: boolean;
  onToggleExpand: () => void;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "open") => WorkbenchRowState;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "open") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  highlightedRowId?: string | null;
  selectionSummary?: {
    total: number;
    oa: number;
    bank: number;
    invoice: number;
  };
  onClearSelection?: () => void;
  primarySelectionActionLabel?: string;
  secondarySelectionActionLabel?: string;
  onPrimarySelectionAction?: () => void;
  onSecondarySelectionAction?: () => void;
  primarySelectionActionDisabled?: boolean;
  secondarySelectionActionDisabled?: boolean;
  auxiliaryHeaderActions?: Array<{
    label: string;
    onClick: () => void;
    tone?: "warning" | "danger";
  }>;
};

export default function WorkbenchZone({
  zoneId,
  title,
  tone,
  meta,
  panes,
  groups,
  isExpanded,
  onToggleExpand,
  getRowState,
  onSelectRow,
  onOpenDetail,
  onRowAction,
  highlightedRowId,
  selectionSummary,
  onClearSelection,
  primarySelectionActionLabel,
  secondarySelectionActionLabel,
  onPrimarySelectionAction,
  onSecondarySelectionAction,
  primarySelectionActionDisabled,
  secondarySelectionActionDisabled,
  auxiliaryHeaderActions,
}: WorkbenchZoneProps) {
  const { widths, visibleIndices, visibleCount, togglePane, startDrag } = useResizablePanes();
  const expandLabel = `${isExpanded ? "恢复" : "放大"} ${title}`;
  const shouldShowSelectionToolbar = Boolean(selectionSummary);

  return (
    <section className={`zone${isExpanded ? " zone-expanded" : ""}`} data-testid={`zone-${zoneId}`}>
      <header className={`zone-header ${tone}`}>
        <div className="zone-title-block">
          <div>{title}</div>
          <div className="zone-meta">{meta}</div>
          {shouldShowSelectionToolbar ? (
            <div className="zone-selection-toolbar">
              <div className="zone-selection-summary">
                <span className="zone-selection-pill">已选 {selectionSummary?.total ?? 0}</span>
                <span className="zone-selection-pill">OA {selectionSummary?.oa ?? 0}</span>
                <span className="zone-selection-pill">流水 {selectionSummary?.bank ?? 0}</span>
                <span className="zone-selection-pill">发票 {selectionSummary?.invoice ?? 0}</span>
              </div>
              <div className="zone-selection-actions">
                <button
                  className="zone-selection-btn"
                  type="button"
                  onClick={onClearSelection}
                >
                  清空选择
                </button>
                <button
                  className="zone-selection-btn primary"
                  disabled={primarySelectionActionDisabled}
                  type="button"
                  onClick={onPrimarySelectionAction}
                >
                  {primarySelectionActionLabel}
                </button>
                {secondarySelectionActionLabel ? (
                  <button
                    className="zone-selection-btn warning"
                    disabled={secondarySelectionActionDisabled}
                    type="button"
                    onClick={onSecondarySelectionAction}
                  >
                    {secondarySelectionActionLabel}
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
        <div className="zone-actions">
          {auxiliaryHeaderActions?.length ? (
            <div className="zone-aux-action-group">
              {auxiliaryHeaderActions.map((action) => (
                <button
                  key={action.label}
                  className={`zone-toggle zone-aux-action${action.tone === "danger" ? " danger" : ""}`}
                  type="button"
                  onClick={action.onClick}
                >
                  {action.label}
                </button>
              ))}
            </div>
          ) : null}
          <div className="zone-toggle-group">
            {panes.map((pane, index) => {
              const active = widths[index] > 0.0001;
              return (
                <button
                  key={pane.id}
                  aria-pressed={active}
                  className={`zone-toggle${active ? " active" : ""}`}
                  disabled={active && visibleCount === 1}
                  type="button"
                  onClick={() => togglePane(index)}
                >
                  {pane.title}
                </button>
              );
            })}
          </div>
          <button
            aria-label={expandLabel}
            className={`zone-expand-icon-btn${isExpanded ? " active" : ""}`}
            type="button"
            title={expandLabel}
            onClick={onToggleExpand}
          >
            {isExpanded ? (
              <svg aria-hidden="true" className="zone-expand-icon" viewBox="0 0 20 20">
                <path
                  d="M7 3H3v4M13 3h4v4M17 13v4h-4M7 17H3v-4"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.8"
                />
                <path
                  d="M3 7h4V3M17 7h-4V3M3 13h4v4M17 13h-4v4"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.8"
                />
              </svg>
            ) : (
              <svg aria-hidden="true" className="zone-expand-icon" viewBox="0 0 20 20">
                <path
                  d="M7 3H3v4M13 3h4v4M17 13v4h-4M7 17H3v-4"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.8"
                />
                <path
                  d="M7 7 3 3M13 7l4-4M13 13l4 4M7 13l-4 4"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.8"
                />
              </svg>
            )}
          </button>
        </div>
      </header>
      <ResizableTriPane
        getRowState={getRowState}
        groups={groups}
        highlightedRowId={highlightedRowId}
        onOpenDetail={onOpenDetail}
        onRowAction={onRowAction}
        onSelectRow={onSelectRow}
        panes={panes}
        visibleIndices={visibleIndices}
        widths={widths}
        onStartDrag={startDrag}
        zoneId={zoneId}
      />
    </section>
  );
}
