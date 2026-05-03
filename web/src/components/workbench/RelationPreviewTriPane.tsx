import { memo, useMemo, useRef } from "react";

import { getWorkbenchColumns, getWorkbenchPaneGridStyle } from "../../features/workbench/tableConfig";
import type {
  WorkbenchCandidateGroup,
  WorkbenchColumnLayouts,
  WorkbenchRecord,
  WorkbenchRecordType,
} from "../../features/workbench/types";
import type { WorkbenchRowState } from "../../hooks/useWorkbenchSelection";
import CandidateGroupCell from "./CandidateGroupCell";
import type { WorkbenchInlineAction } from "./RowActions";

export type RelationPreviewTriPaneProps = {
  title: string;
  testId?: string;
  groups: WorkbenchCandidateGroup[];
  totals: {
    oaTotal: string;
    bankTotal: string;
    invoiceTotal: string;
  };
  mismatchFields: string[];
  columnLayouts?: WorkbenchColumnLayouts;
};

type PreviewPaneConfig = {
  id: WorkbenchRecordType;
  title: string;
  mismatchField: string;
};

const PREVIEW_PANES: PreviewPaneConfig[] = [
  { id: "oa", title: "OA", mismatchField: "oa_total" },
  { id: "bank", title: "流水", mismatchField: "bank_total" },
  { id: "invoice", title: "发票", mismatchField: "invoice_total" },
];

const ROW_TEMPLATE_COLUMNS = "repeat(3, minmax(0, 1fr))";
const PREVIEW_STATUS_LABELS = {
  matched: "金额一致",
  mismatch: "金额不一致",
  pending: "金额待核对",
} as const;

const noopSelectRow = (_row: WorkbenchRecord, _zoneId: "paired" | "open") => undefined;
const noopOpenDetail = (_row: WorkbenchRecord) => undefined;
const noopRowAction = (_row: WorkbenchRecord, _action: WorkbenchInlineAction) => undefined;
const getReadOnlyRowState = (): WorkbenchRowState => "idle";

function RelationPreviewTriPane({
  title,
  testId,
  groups,
  totals,
  mismatchFields,
  columnLayouts,
}: RelationPreviewTriPaneProps) {
  const gridRef = useRef<HTMLDivElement | null>(null);
  const syncInFlightRef = useRef<Record<WorkbenchRecordType, boolean>>({
    oa: false,
    bank: false,
    invoice: false,
  });

  const previewGroups = useMemo(() => normalizePreviewGroups(groups, title), [groups, title]);
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
      oa: getWorkbenchPaneGridStyle("oa", columnLayouts, false),
      bank: getWorkbenchPaneGridStyle("bank", columnLayouts, false),
      invoice: getWorkbenchPaneGridStyle("invoice", columnLayouts, false),
    }),
    [columnLayouts],
  );
  const rowCountByPane = useMemo(
    () => ({
      oa: groups.reduce((sum, group) => sum + group.rows.oa.length, 0),
      bank: groups.reduce((sum, group) => sum + group.rows.bank.length, 0),
      invoice: groups.reduce((sum, group) => sum + group.rows.invoice.length, 0),
    }),
    [groups],
  );
  const previewStatus = resolvePreviewStatus(mismatchFields, totals, rowCountByPane);
  const visualMismatchFields = useMemo(
    () => resolveVisualMismatchFields(totals, mismatchFields, rowCountByPane),
    [totals, mismatchFields, rowCountByPane],
  );
  const deltaAmount = useMemo(() => buildDeltaAmount(totals, rowCountByPane), [totals, rowCountByPane]);
  const sectionToneClass = resolvePreviewSectionToneClass(testId, title);

  const handleSyncScroll = (paneId: WorkbenchRecordType, element: HTMLDivElement) => {
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

  return (
    <section
      className={`relation-preview-section relation-preview-tri-pane-section${sectionToneClass ? ` ${sectionToneClass}` : ""}`}
      data-testid={testId}
    >
      <div className="relation-preview-section-title">
        <h3>{title}</h3>
        <span className={`relation-preview-status relation-preview-status-${previewStatus}`}>
          {PREVIEW_STATUS_LABELS[previewStatus]}
        </span>
      </div>
      <div className="relation-preview-summary relation-preview-summary-inline" data-testid="relation-preview-summary">
        <span className="relation-preview-summary-title">金额核对</span>
        <div className="relation-preview-summary-value-list">
          {PREVIEW_PANES.map((pane) => {
            const mismatch = visualMismatchFields.includes(pane.mismatchField);
            const paneTotal = resolvePaneTotal(totals, pane.id);
            return (
              <div
                key={`summary-${pane.id}`}
                className={`relation-preview-summary-metric relation-preview-summary-metric-${pane.id}${mismatch ? " mismatch relation-preview-summary-metric-mismatch" : ""}`}
              data-testid={`relation-preview-summary-metric-${pane.id}`}
            >
              <span className="relation-preview-summary-label">{pane.title}</span>
                <strong>{formatDisplayAmount(paneTotal, rowCountByPane[pane.id] > 0)}</strong>
              </div>
            );
          })}
        </div>
        {deltaAmount ? (
          <span className="relation-preview-delta relation-preview-delta-pill" data-testid="relation-preview-delta">
            差额 {deltaAmount}
          </span>
        ) : null}
      </div>
      <div ref={gridRef} className="candidate-grid relation-preview-tri-pane" data-testid="tri-pane">
        <div className="candidate-grid-head relation-preview-tri-pane-head" style={{ gridTemplateColumns: ROW_TEMPLATE_COLUMNS }}>
          {PREVIEW_PANES.map((pane) => {
            const mismatch = visualMismatchFields.includes(pane.mismatchField);
            return (
              <section
                key={pane.id}
                className={`candidate-pane-head pane-card relation-preview-pane relation-preview-tri-pane-pane relation-preview-pane-${pane.id}${mismatch ? " mismatch relation-preview-pane-mismatch" : ""}`}
                data-testid={`pane-${pane.id}`}
              >
                <div className="pane-header relation-preview-pane-header">
                  <div className="pane-header-main">
                    <span>{pane.title}</span>
                    <span>{rowCountByPane[pane.id]} 项</span>
                  </div>
                </div>
                <div
                  className="candidate-pane-scroll"
                  data-scroll-pane={pane.id}
                  data-testid={`relation-preview-pane-scroll-head-${title}-${pane.id}`}
                >
                  <div
                    className={`candidate-pane-columnheaders candidate-pane-columnheaders-${pane.id} pane-layout-no-action`}
                    role="row"
                    style={paneGridStyleByPane[pane.id]}
                  >
                    {columnsByPane[pane.id].map((column) => (
                      <div
                        aria-label={column.label}
                        key={column.key}
                        className={`candidate-columnheader cell-${column.kind ?? "text"}${column.className ? ` ${column.className}` : ""}`}
                        role="columnheader"
                      >
                        <span className={`candidate-columnheader-label${column.headerLines ? " candidate-columnheader-label-lines" : ""}`}>
                          {column.headerLines
                            ? column.headerLines.map((line) => (
                              <span key={line} className="candidate-columnheader-label-line">
                                {line}
                              </span>
                            ))
                            : column.label}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            );
          })}
        </div>

        <div className="candidate-grid-body relation-preview-tri-pane-body">
          {previewGroups.map((group, index) => (
            <div
              key={group.id}
              className={`candidate-group-row candidate-group-row-sheet candidate-group-row-tone-${index % 4}`}
              data-testid={`candidate-group-${group.id}`}
              style={{ gridTemplateColumns: ROW_TEMPLATE_COLUMNS }}
            >
              {PREVIEW_PANES.map((pane) => (
                <div key={`${group.id}-${pane.id}`} className="candidate-group-pane-slot candidate-group-pane-slot-sheet">
                  <CandidateGroupCell
                    columnGridStyle={paneGridStyleByPane[pane.id]}
                    columns={columnsByPane[pane.id]}
                    getRowState={getReadOnlyRowState}
                    onOpenDetail={noopOpenDetail}
                    onRowAction={noopRowAction}
                    onSelectRow={noopSelectRow}
                    paneId={pane.id}
                    readOnly
                    records={group.rows[pane.id]}
                    scrollPaneId={pane.id}
                    scrollTestId={`relation-preview-candidate-scroll-${title}-${group.id}-${pane.id}`}
                    showWorkflowActions={false}
                    canMutateData={false}
                    zoneId="paired"
                  />
                </div>
              ))}
            </div>
          ))}
        </div>

        <div className="candidate-grid-footer relation-preview-tri-pane-footer" style={{ gridTemplateColumns: ROW_TEMPLATE_COLUMNS }}>
          {PREVIEW_PANES.map((pane) => (
            <div key={`footer-${pane.id}`} className="candidate-pane-footer-slot">
              <div
                className="candidate-pane-footer-scroll"
                data-scroll-pane={pane.id}
                data-testid={`relation-preview-pane-scrollbar-${title}-${pane.id}`}
                onScroll={(event) => handleSyncScroll(pane.id, event.currentTarget)}
              >
                <div
                  className={`candidate-pane-scrollbar-track candidate-pane-columnheaders-${pane.id} pane-layout-no-action`}
                  aria-hidden="true"
                  style={paneGridStyleByPane[pane.id]}
                >
                  {columnsByPane[pane.id].map((column) => (
                    <div key={column.key} className="candidate-scrollbar-track-cell" />
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default memo(RelationPreviewTriPane);

function normalizePreviewGroups(groups: WorkbenchCandidateGroup[], title: string): WorkbenchCandidateGroup[] {
  if (groups.length > 0) {
    return groups;
  }

  return [
    {
      id: `empty-${title}`,
      groupType: "candidate",
      matchConfidence: "medium",
      reason: "relation_preview_empty",
      rows: {
        oa: [],
        bank: [],
        invoice: [],
      },
    },
  ];
}

function resolvePaneTotal(totals: RelationPreviewTriPaneProps["totals"], paneId: WorkbenchRecordType) {
  if (paneId === "oa") {
    return totals.oaTotal;
  }
  if (paneId === "bank") {
    return totals.bankTotal;
  }
  return totals.invoiceTotal;
}

function resolvePreviewStatus(
  mismatchFields: string[],
  totals: RelationPreviewTriPaneProps["totals"],
  rowCountByPane: Record<WorkbenchRecordType, number>,
): keyof typeof PREVIEW_STATUS_LABELS {
  const visualMismatchFields = resolveVisualMismatchFields(totals, mismatchFields, rowCountByPane);
  if (visualMismatchFields.length > 0) {
    return "mismatch";
  }

  const totalValues = PREVIEW_PANES
    .filter((pane) => rowCountByPane[pane.id] > 0)
    .map((pane) => resolvePaneTotal(totals, pane.id));
  if (totalValues.length > 0 && totalValues.some((value) => parseMoneyAmount(value) === null)) {
    return "pending";
  }

  return "matched";
}

function parseMoneyAmount(value: string) {
  const normalized = value.replace(/,/g, "").replace(/\s/g, "");
  if (!normalized || normalized === "-") {
    return null;
  }

  const amount = Number(normalized);
  return Number.isFinite(amount) ? amount : null;
}

function formatMoneyDelta(value: number) {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function resolvePreviewSectionToneClass(testId: string | undefined, title: string) {
  const marker = `${testId ?? ""} ${title}`.toLowerCase();
  if (marker.includes("before") || marker.includes("操作前")) {
    return "relation-preview-section-before";
  }
  if (marker.includes("after") || marker.includes("操作后")) {
    return "relation-preview-section-after";
  }
  return "";
}

function formatDisplayAmount(value: string, hasRows: boolean) {
  if (!hasRows) {
    return "-";
  }
  return parseMoneyAmount(value) === null ? "-" : value;
}

function resolveComparableAmounts(
  totals: RelationPreviewTriPaneProps["totals"],
  rowCountByPane: Record<WorkbenchRecordType, number>,
) {
  return PREVIEW_PANES.filter((pane) => rowCountByPane[pane.id] > 0).map((pane) => {
    const displayValue = resolvePaneTotal(totals, pane.id);
    return {
      pane,
      amount: parseMoneyAmount(displayValue),
    };
  }).filter((total) => total.amount !== null) as Array<{
    pane: PreviewPaneConfig;
    amount: number;
  }>;
}

function resolveVisualMismatchFields(
  totals: RelationPreviewTriPaneProps["totals"],
  mismatchFields: string[],
  rowCountByPane: Record<WorkbenchRecordType, number>,
) {
  const comparableAmounts = resolveComparableAmounts(totals, rowCountByPane);
  const nonEmptyMismatchFields = mismatchFields.filter((field) =>
    PREVIEW_PANES.some((pane) => pane.mismatchField === field && rowCountByPane[pane.id] > 0),
  );

  if (comparableAmounts.length < 2) {
    return nonEmptyMismatchFields;
  }

  if (comparableAmounts.length === 2) {
    const [left, right] = comparableAmounts;
    return areMoneyAmountsEqual(left.amount, right.amount)
      ? []
      : [left.pane.mismatchField, right.pane.mismatchField];
  }

  const amountGroups = comparableAmounts.reduce<Array<typeof comparableAmounts>>((groups, total) => {
    const existingGroup = groups.find((group) => areMoneyAmountsEqual(group[0].amount, total.amount));
    if (existingGroup) {
      existingGroup.push(total);
    } else {
      groups.push([total]);
    }
    return groups;
  }, []);

  if (amountGroups.length === 1) {
    return [];
  }

  if (amountGroups.length === 2) {
    const isolatedGroup = amountGroups.find((group) => group.length === 1);
    return isolatedGroup ? [isolatedGroup[0].pane.mismatchField] : comparableAmounts.map((total) => total.pane.mismatchField);
  }

  return comparableAmounts.map((total) => total.pane.mismatchField);
}

function buildDeltaAmount(
  totals: RelationPreviewTriPaneProps["totals"],
  rowCountByPane: Record<WorkbenchRecordType, number>,
) {
  const comparableAmounts = resolveComparableAmounts(totals, rowCountByPane);
  if (comparableAmounts.length < 2) {
    return null;
  }

  const amounts = comparableAmounts.map((total) => total.amount);
  return formatMoneyDelta(Math.max(...amounts) - Math.min(...amounts));
}

function areMoneyAmountsEqual(left: number, right: number) {
  return Math.abs(left - right) < 0.005;
}
