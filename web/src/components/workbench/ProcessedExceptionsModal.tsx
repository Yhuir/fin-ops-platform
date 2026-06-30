import CandidateGroupGrid from "./CandidateGroupGrid";
import type { WorkbenchCandidateGroup, WorkbenchRecord } from "../../features/workbench/types";
import type { WorkbenchPane } from "./ResizableTriPane";

type ProcessedExceptionsModalProps = {
  groups: WorkbenchCandidateGroup[];
  panes: WorkbenchPane[];
  highlightedRowId?: string | null;
  canMutateData: boolean;
  onClose: () => void;
  onCancelException: (row: WorkbenchRecord) => void;
};

const PROCESSED_EXCEPTIONS_ROW_TEMPLATE_COLUMNS =
  "minmax(360px, 1fr) 1px minmax(360px, 1fr) 1px minmax(360px, 1fr) 1px minmax(220px, 0.5fr) minmax(260px, 0.6fr)";

export default function ProcessedExceptionsModal({
  groups,
  panes,
  highlightedRowId,
  canMutateData,
  onClose,
  onCancelException,
}: ProcessedExceptionsModalProps) {
  return (
    <div aria-modal="true" className="detail-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        aria-label="已处理异常弹窗"
        className="detail-modal processed-exceptions-modal"
        role="dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="detail-modal-header">
          <div>
            <h2>已处理异常</h2>
            <p>异常处理后的 OA、银行流水、发票按同一关系组横向展示；同栏多项会在单元格内上下排列。</p>
          </div>
          <button aria-label="关闭已处理异常弹窗" className="detail-close-btn" type="button" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="ignored-items-body processed-exceptions-body">
          {groups.length === 0 ? (
            <div className="detail-state-panel">当前没有已处理异常项。</div>
          ) : (
            <CandidateGroupGrid
              actionMode="cancel-exception-only"
              getRowState={() => "idle"}
              groups={groups}
              highlightedRowId={highlightedRowId}
              onOpenDetail={() => undefined}
              onRowAction={(row, action) => {
                if (action === "cancel-exception") {
                  onCancelException(row);
                }
              }}
              onSelectRow={() => undefined}
              panes={panes}
              rowTemplateColumns={PROCESSED_EXCEPTIONS_ROW_TEMPLATE_COLUMNS}
              trailingColumns={[
                {
                  key: "exceptionReason",
                  label: "异常原因",
                  className: "processed-exception-summary-cell",
                  renderGroup: (group) => <ProcessedExceptionSummaryText value={resolveProcessedExceptionReason(group)} />,
                },
                {
                  key: "exceptionNote",
                  label: "异常备注",
                  className: "processed-exception-summary-cell",
                  renderGroup: (group) => <ProcessedExceptionSummaryText value={resolveProcessedExceptionNote(group)} />,
                },
              ]}
              canMutateData={canMutateData}
              zoneId="paired"
            />
          )}
        </div>
      </div>
    </div>
  );
}

function ProcessedExceptionSummaryText({ value }: { value: string }) {
  return <span className="processed-exception-summary-text" title={value}>{value}</span>;
}

function resolveProcessedExceptionReason(group: WorkbenchCandidateGroup) {
  const summary = group.processedExceptionSummary;
  return firstText(
    summary?.scenario?.label,
    summary?.scenario?.scenario_label,
    summary?.scenario?.code,
    summary?.resolution?.action_label,
    summary?.resolution?.label,
    firstProcessedRow(group)?.status,
    group.reason,
  );
}

function resolveProcessedExceptionNote(group: WorkbenchCandidateGroup) {
  const row = firstProcessedRow(group);
  return firstText(
    group.processedExceptionSummary?.detailNote,
    group.processedExceptionSummary?.resolution?.note,
    group.processedExceptionSummary?.resolution?.comment,
    row?.relationNote,
    row?.detailFields.find((field) => field.label === "备注")?.value,
    group.relationNote,
    "—",
  );
}

function firstProcessedRow(group: WorkbenchCandidateGroup) {
  return [...group.rows.oa, ...group.rows.bank, ...group.rows.invoice][0];
}

function firstText(...values: unknown[]) {
  for (const value of values) {
    const text = typeof value === "string" ? value.trim() : "";
    if (text && text !== "--" && text !== "—") {
      return text;
    }
  }
  return "—";
}
