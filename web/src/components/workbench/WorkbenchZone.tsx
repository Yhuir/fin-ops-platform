import { memo, useMemo } from "react";
import { Button, Dropdown, SearchField, Spinner, Tooltip } from "@heroui/react";
import { Ellipsis, RefreshCw } from "lucide-react";

import ResizableTriPane, { type WorkbenchPane } from "./ResizableTriPane";
import { useResizablePanes } from "../../hooks/useResizablePanes";
import {
  createEmptyWorkbenchZoneDisplayState,
  type WorkbenchPaneTimeFilter as WorkbenchPaneTimeFilterState,
  type WorkbenchZoneDisplayState,
} from "../../features/workbench/groupDisplayModel";
import type {
  WorkbenchRelationGroup,
  WorkbenchColumnLayouts,
  WorkbenchStatistics,
  WorkbenchRecord,
  WorkbenchZonePageInfo,
  WorkbenchFilterOptionsLoader,
} from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import type { WorkbenchInlineAction } from "./RowActions";
import type { WorkbenchColumnDropPosition } from "../../features/workbench/columnLayout";
import { formatMoney } from "../../features/money";
import WorkbenchPaneTimeFilter from "./WorkbenchPaneTimeFilter";

type WorkbenchZoneProps = {
  zoneId: "paired" | "unpaired";
  title: string;
  tone: "success" | "warning";
  meta?: string;
  panes: WorkbenchPane[];
  groups?: WorkbenchRelationGroup[];
  sourceGroups?: WorkbenchRelationGroup[];
  invoiceStatistics?: WorkbenchStatistics;
  displayState?: WorkbenchZoneDisplayState;
  columnLayouts?: WorkbenchColumnLayouts;
  getRowState: (row: WorkbenchRecord, zoneId: "paired" | "unpaired") => WorkbenchRowState;
  onSelectRow: (row: WorkbenchRecord, zoneId: "paired" | "unpaired") => void;
  onOpenDetail: (row: WorkbenchRecord) => void;
  onRowAction: (
    row: WorkbenchRecord,
    action: WorkbenchInlineAction,
    group: WorkbenchRelationGroup,
  ) => void;
  onEditReceipt?: (group: WorkbenchRelationGroup) => void;
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
  primarySelectionActionPending?: boolean;
  primarySelectionActionPendingLabel?: string;
  secondarySelectionActionPending?: boolean;
  secondarySelectionActionPendingLabel?: string;
  primarySelectionActionDisabled?: boolean;
  secondarySelectionActionDisabled?: boolean;
  tertiarySelectionActionDisabled?: boolean;
  selectionActionNotice?: string | null;
  pageInfo?: WorkbenchZonePageInfo;
  loadingMore?: boolean;
  loadMoreError?: string | null;
  onRequestNextPage?: (zoneId: "paired" | "unpaired") => void;
  loadFilterOptions?: WorkbenchFilterOptionsLoader;
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
    filter: WorkbenchPaneTimeFilterState,
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
  invoiceStatistics,
  displayState = createEmptyWorkbenchZoneDisplayState(),
  columnLayouts,
  getRowState,
  onSelectRow,
  onOpenDetail,
  onRowAction,
  onEditReceipt,
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
  primarySelectionActionPending = false,
  primarySelectionActionPendingLabel,
  secondarySelectionActionPending = false,
  secondarySelectionActionPendingLabel,
  primarySelectionActionDisabled,
  secondarySelectionActionDisabled,
  tertiarySelectionActionDisabled,
  selectionActionNotice,
  pageInfo,
  loadingMore = false,
  loadMoreError,
  onRequestNextPage,
  loadFilterOptions,
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
  const shouldShowSelectionToolbar = Boolean(selectionSummary);
  const explicitSelectionTotal = selectionSummary?.explicitTotal ?? selectionSummary?.total ?? 0;
  const contextualSelectionTotal = Math.max(0, (selectionSummary?.total ?? 0) - explicitSelectionTotal);
  const activePaneIds = panes.filter((_, index) => widths[index] > 0.0001).map((pane) => pane.id);
  const loadBankTimeYears = useMemo(() => loadFilterOptions
    ? (cursor: string | null, signal?: AbortSignal) => loadFilterOptions(zoneId, {
      pane: "bank",
      facet: "time_year",
      cursor,
    }, signal)
    : undefined, [loadFilterOptions, zoneId]);
  const canRequestNextPage = Boolean(
    pageInfo?.hasMore
    && !loadingMore
    && !loadMoreError
    && !searchPending
    && onRequestNextPage,
  );
  const primarySelectionActionBusyLabel = primarySelectionActionPendingLabel ?? primarySelectionActionLabel;
  const secondarySelectionActionBusyLabel = secondarySelectionActionPendingLabel ?? secondarySelectionActionLabel;

  return (
    <section
      className={`zone zone-${tone}`}
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
                <span className="zone-selection-pill">{`OA ${selectionSummary?.oa ?? 0} / ${formatMoney(selectionSummary?.amounts.oa)}`}</span>
                <span className="zone-selection-pill">{`流水 ${selectionSummary?.bank ?? 0} / ${formatMoney(selectionSummary?.amounts.bank)}`}</span>
                <span className="zone-selection-pill">{`发票 ${selectionSummary?.invoice ?? 0} / ${formatMoney(selectionSummary?.amounts.invoice)}`}</span>
              </div>
              <div className="zone-selection-actions">
                <Button
                  className="zone-selection-btn"
                  onPress={onClearSelection}
                  size="sm"
                  variant="tertiary"
                >
                  清空选择
                </Button>
                <Button
                  aria-label={primarySelectionActionPending ? primarySelectionActionBusyLabel : undefined}
                  className="zone-selection-btn primary"
                  isDisabled={primarySelectionActionDisabled}
                  isPending={primarySelectionActionPending}
                  onPress={onPrimarySelectionAction}
                  size="sm"
                  variant="primary"
                >
                  {primarySelectionActionPending ? (
                    <>
                      <span aria-label={primarySelectionActionBusyLabel} role="status">
                        <Spinner aria-hidden="true" color="current" size="sm" />
                      </span>
                      {primarySelectionActionBusyLabel}
                    </>
                  ) : primarySelectionActionLabel}
                </Button>
                {secondarySelectionActionLabel ? (
                  <Button
                    aria-label={secondarySelectionActionPending ? secondarySelectionActionBusyLabel : undefined}
                    className="zone-selection-btn warning"
                    isDisabled={secondarySelectionActionDisabled}
                    isPending={secondarySelectionActionPending}
                    onPress={onSecondarySelectionAction}
                    size="sm"
                    variant="tertiary"
                  >
                    {secondarySelectionActionPending ? (
                      <>
                        <span aria-label={secondarySelectionActionBusyLabel} role="status">
                          <Spinner aria-hidden="true" color="current" size="sm" />
                        </span>
                        {secondarySelectionActionBusyLabel}
                      </>
                    ) : secondarySelectionActionLabel}
                  </Button>
                ) : null}
                {tertiarySelectionActionLabel ? (
                  <Button
                    className="zone-selection-btn"
                    isDisabled={tertiarySelectionActionDisabled}
                    onPress={onTertiarySelectionAction}
                    size="sm"
                    variant="tertiary"
                  >
                    {tertiarySelectionActionLabel}
                  </Button>
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
                <Button
                  key={action.label}
                  className={`zone-toggle zone-aux-action${action.tone === "danger" ? " danger" : ""}`}
                  onPress={action.onClick}
                  size="sm"
                  variant="tertiary"
                >
                  {action.label}
                </Button>
              ))}
            </div>
          ) : null}
          <WorkbenchPaneTimeFilter
            filter={displayState.timeFilterByPane.bank}
            loadYears={loadBankTimeYears}
            paneTitle="银行流水"
            onChange={(filter) => onPaneTimeFilterChange?.(zoneId, "bank", filter)}
          />
          <Dropdown>
            <Dropdown.Trigger
              aria-label={`${title}栏显示`}
              className="zone-view-menu-trigger"
            >
              <Ellipsis aria-hidden="true" size={18} />
            </Dropdown.Trigger>
            <Dropdown.Popover placement="bottom end">
              <Dropdown.Menu
                aria-label={`${title}栏显示`}
                disabledKeys={visibleCount === 1 ? [`pane-${activePaneIds[0]}`] : []}
                onAction={(key) => {
                  const action = String(key);
                  const paneIndex = panes.findIndex((pane) => `pane-${pane.id}` === action);
                  if (paneIndex >= 0 && !(widths[paneIndex] > 0.0001 && visibleCount === 1)) {
                    togglePane(paneIndex);
                  }
                }}
              >
                {panes.map((pane, index) => (
                  <Dropdown.Item id={`pane-${pane.id}`} key={`pane-${pane.id}`}>
                    {widths[index] > 0.0001 ? `✓ ${pane.title}` : pane.title}
                  </Dropdown.Item>
                ))}
              </Dropdown.Menu>
            </Dropdown.Popover>
          </Dropdown>
        </div>
      </header>
      <ResizableTriPane
        columnLayouts={columnLayouts}
        displayState={displayState}
        getRowState={getRowState}
        groups={groups}
        highlightedRowId={highlightedRowId}
        invoiceStatistics={invoiceStatistics}
        loadFilterOptions={loadFilterOptions}
        onOpenDetail={onOpenDetail}
        onRowAction={onRowAction}
        onEditReceipt={onEditReceipt}
        onEnsureGroupDetail={onEnsureGroupDetail}
        canRequestNextPage={canRequestNextPage}
        onColumnFilterChange={onColumnFilterChange}
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
