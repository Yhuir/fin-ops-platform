import { memo } from "react";
import { Button, SearchField, Spinner, Tooltip } from "@heroui/react";
import { RefreshCw } from "lucide-react";

import ResizableTriPane, { type WorkbenchPane } from "./ResizableTriPane";
import { useResizablePanes } from "../../hooks/useResizablePanes";
import type { WorkbenchPaneTimeFilter, WorkbenchZoneDisplayState } from "../../features/workbench/groupDisplayModel";
import type {
  WorkbenchRelationGroup,
  WorkbenchColumnLayouts,
  WorkbenchInvoiceInventory,
  WorkbenchRecord,
  WorkbenchZonePageInfo,
} from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import type { WorkbenchInlineAction } from "./RowActions";
import type { WorkbenchColumnDropPosition } from "../../features/workbench/columnLayout";

type WorkbenchZoneProps = {
  zoneId: "paired" | "unpaired";
  title: string;
  tone: "success" | "warning";
  meta?: string;
  panes: WorkbenchPane[];
  groups?: WorkbenchRelationGroup[];
  sourceGroups?: WorkbenchRelationGroup[];
  invoiceInventory?: WorkbenchInvoiceInventory;
  displayState: WorkbenchZoneDisplayState;
  columnLayouts?: WorkbenchColumnLayouts;
  isExpanded: boolean;
  isVisible: boolean;
  onToggleExpand: () => void;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "unpaired") => WorkbenchRowState;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "unpaired") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (row: WorkbenchRecord, action: WorkbenchInlineAction) => void;
  onEnsureGroupDetail?: (zoneId: "paired" | "unpaired", groupId: string) => Promise<void>;
  canMutateData: boolean;
  highlightedRowId?: string | null;
  selectionSummary?: {
    explicitTotal?: number;
    total: number;
    oa: number;
    bank: number;
    invoice: number;
    amounts: {
      oa: string;
      bank: string;
      invoice: string;
    };
  };
  onClearSelection?: () => void;
  primarySelectionActionLabel?: string;
  secondarySelectionActionLabel?: string;
  tertiarySelectionActionLabel?: string;
  onPrimarySelectionAction?: () => void;
  onSecondarySelectionAction?: () => void;
  onTertiarySelectionAction?: () => void;
  primarySelectionActionDisabled?: boolean;
  secondarySelectionActionDisabled?: boolean;
  tertiarySelectionActionDisabled?: boolean;
  selectionActionNotice?: string | null;
  pageInfo?: WorkbenchZonePageInfo;
  loadingMore?: boolean;
  loadMoreError?: string | null;
  onRequestNextPage?: (zoneId: "paired" | "unpaired") => void;
  auxiliaryHeaderActions?: Array<{
    label: string;
    onClick: () => void;
    tone?: "warning" | "danger";
  }>;
  searchQuery: string;
  searchPending?: boolean;
  searchError?: string | null;
  onSearchQueryChange: (query: string) => void;
  onRetrySearch?: () => void;
  onColumnFilterChange: (
    zoneId: "paired" | "unpaired",
    paneId: "oa" | "bank" | "invoice",
    columnKey: string,
    selectedValues: string[],
  ) => void;
  onTogglePaneSort: (zoneId: "paired" | "unpaired", paneId: "oa" | "bank" | "invoice") => void;
  onPaneTimeFilterChange?: (
    zoneId: "paired" | "unpaired",
    paneId: "oa" | "bank" | "invoice",
    filter: WorkbenchPaneTimeFilter,
  ) => void;
  onReorderPaneColumns: (
    paneId: "oa" | "bank" | "invoice",
    activeKey: string,
    overKey: string,
    position: WorkbenchColumnDropPosition,
  ) => void;
};

function WorkbenchZone({
  zoneId,
  title,
  tone,
  meta,
  panes,
  groups,
  sourceGroups,
  invoiceInventory,
  displayState,
  columnLayouts,
  isExpanded,
  isVisible,
  onToggleExpand,
  getRowState,
  onSelectRow,
  onOpenDetail,
  onRowAction,
  onEnsureGroupDetail,
  canMutateData,
  highlightedRowId,
  selectionSummary,
  onClearSelection,
  primarySelectionActionLabel,
  secondarySelectionActionLabel,
  tertiarySelectionActionLabel,
  onPrimarySelectionAction,
  onSecondarySelectionAction,
  onTertiarySelectionAction,
  primarySelectionActionDisabled,
  secondarySelectionActionDisabled,
  tertiarySelectionActionDisabled,
  selectionActionNotice,
  pageInfo,
  loadingMore = false,
  loadMoreError,
  onRequestNextPage,
  auxiliaryHeaderActions,
  searchQuery,
  searchPending = false,
  searchError,
  onSearchQueryChange,
  onRetrySearch,
  onColumnFilterChange,
  onTogglePaneSort,
  onPaneTimeFilterChange = () => undefined,
  onReorderPaneColumns,
}: WorkbenchZoneProps) {
  const { widths, visibleIndices, visibleCount, togglePane, startDrag } = useResizablePanes();
  const expandLabel = `${isExpanded ? "恢复" : "放大"} ${title}`;
  const shouldShowSelectionToolbar = Boolean(selectionSummary);
  const explicitSelectionTotal = selectionSummary?.explicitTotal ?? selectionSummary?.total ?? 0;
  const contextualSelectionTotal = Math.max(0, (selectionSummary?.total ?? 0) - explicitSelectionTotal);
  const activePaneIds = panes.filter((_, index) => widths[index] > 0.0001).map((pane) => pane.id);
  const canRequestNextPage = Boolean(
    isVisible
    && pageInfo?.hasMore
    && pageInfo.readModelStatus === "fresh"
    && !loadingMore
    && !loadMoreError
    && !searchPending
    && onRequestNextPage,
  );

  return (
    <section
      aria-hidden={!isVisible}
      className={`zone zone-${tone}${isExpanded ? " zone-expanded" : ""}${isVisible ? "" : " zone-hidden"}`}
      data-testid={`zone-${zoneId}`}
    >
      <header className={`zone-header ${tone}`}>
        <div className="zone-title-block">
          <div className="zone-heading-row">
            <div className="zone-title-copy">
              <div className="zone-title">
                {title}
              </div>
              {meta ? (
                <div className="zone-meta">
                  {meta}
                </div>
              ) : null}
            </div>
            <SearchField
              aria-label={`搜索${zoneId === "paired" ? "已配对" : "未配对"}区域`}
              className="workbench-zone-search"
              fullWidth
              isInvalid={Boolean(searchError)}
              maxLength={200}
              onChange={onSearchQueryChange}
              value={searchQuery}
            >
              <SearchField.Group className="workbench-zone-search-group">
                {searchPending ? (
                  <Spinner aria-label="搜索中" className="workbench-zone-search-spinner" color="current" size="sm" />
                ) : (
                  <SearchField.SearchIcon className="workbench-zone-search-icon" />
                )}
                <SearchField.Input
                  className="workbench-zone-search-input"
                  placeholder="搜索 OA、流水、发票"
                />
                {searchError && onRetrySearch ? (
                  <Tooltip delay={0}>
                    <Button
                      aria-label="重试搜索"
                      className="workbench-zone-search-retry"
                      isIconOnly
                      onPress={onRetrySearch}
                      size="sm"
                      variant="tertiary"
                    >
                      <RefreshCw aria-hidden="true" size={14} strokeWidth={2.2} />
                    </Button>
                    <Tooltip.Content>{searchError}</Tooltip.Content>
                  </Tooltip>
                ) : (
                  <SearchField.ClearButton aria-label="清空搜索" className="workbench-zone-search-clear" />
                )}
              </SearchField.Group>
            </SearchField>
          </div>
          <span aria-live="polite" className="sr-only">
            {searchPending ? "正在更新搜索结果" : searchError ? `搜索失败：${searchError}` : ""}
          </span>
          {shouldShowSelectionToolbar ? (
            <div className="zone-selection-toolbar">
              <div className="zone-selection-summary">
                <span className="zone-selection-pill">{`已选 ${explicitSelectionTotal}`}</span>
                {contextualSelectionTotal > 0 ? (
                  <span className="zone-selection-pill zone-selection-pill-context">{`带入 ${contextualSelectionTotal}`}</span>
                ) : null}
                <span className="zone-selection-pill">{`OA ${selectionSummary?.oa ?? 0} / ${selectionSummary?.amounts.oa ?? "0.00"}`}</span>
                <span className="zone-selection-pill">{`流水 ${selectionSummary?.bank ?? 0} / ${selectionSummary?.amounts.bank ?? "0.00"}`}</span>
                <span className="zone-selection-pill">{`发票 ${selectionSummary?.invoice ?? 0} / ${selectionSummary?.amounts.invoice ?? "0.00"}`}</span>
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
                {tertiarySelectionActionLabel ? (
                  <button
                    className="zone-selection-btn"
                    disabled={tertiarySelectionActionDisabled}
                    type="button"
                    onClick={onTertiarySelectionAction}
                  >
                    {tertiarySelectionActionLabel}
                  </button>
                ) : null}
              </div>
              {selectionActionNotice ? (
                <p
                  aria-label={selectionActionNotice}
                  aria-live="polite"
                  className="zone-selection-notice"
                  role="status"
                >
                  {selectionActionNotice}
                </p>
              ) : null}
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
          <div
            aria-label={`${title}栏显示切换`}
            className="zone-toggle-group"
            role="group"
          >
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
            title={expandLabel}
            type="button"
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
        columnLayouts={columnLayouts}
        displayState={displayState}
        getRowState={getRowState}
        groups={groups}
        highlightedRowId={highlightedRowId}
        invoiceInventory={invoiceInventory}
        onOpenDetail={onOpenDetail}
        onRowAction={onRowAction}
        onEnsureGroupDetail={onEnsureGroupDetail}
        canRequestNextPage={canRequestNextPage}
        onColumnFilterChange={onColumnFilterChange}
        onPaneTimeFilterChange={onPaneTimeFilterChange}
        onReorderPaneColumns={onReorderPaneColumns}
        onSelectRow={onSelectRow}
        onRequestNextPage={onRequestNextPage}
        onTogglePaneSort={onTogglePaneSort}
        panes={panes}
        sourceGroups={sourceGroups}
        visibleIndices={visibleIndices}
        widths={widths}
        canMutateData={canMutateData}
        onStartDrag={startDrag}
        zoneId={zoneId}
      />
      {loadingMore ? (
        <div aria-live="polite" className="zone-auto-load-status" role="status">
          <Spinner aria-label="正在加载更多结果" color="current" size="sm" />
          <span>正在加载更多结果</span>
        </div>
      ) : loadMoreError ? (
        <div className="zone-auto-load-status error" role="alert">
          <span>{loadMoreError}</span>
          <Button
            onPress={() => onRequestNextPage?.(zoneId)}
            size="sm"
            variant="tertiary"
          >
            重试自动加载
          </Button>
        </div>
      ) : null}
    </section>
  );
}

export default memo(WorkbenchZone);
