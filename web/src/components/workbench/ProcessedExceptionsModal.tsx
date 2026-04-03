import CandidateGroupGrid from "./CandidateGroupGrid";
import type { WorkbenchCandidateGroup, WorkbenchRecord } from "../../features/workbench/types";
import type { WorkbenchPane } from "./ResizableTriPane";

type ProcessedExceptionsModalProps = {
  groups: WorkbenchCandidateGroup[];
  panes: WorkbenchPane[];
  highlightedRowId?: string | null;
  onClose: () => void;
  onCancelException: (row: WorkbenchRecord) => void;
};

export default function ProcessedExceptionsModal({
  groups,
  panes,
  highlightedRowId,
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
            <p>异常处理后的 OA、银行流水、发票按同一候选组横向展示；同栏多项会在单元格内上下排列。</p>
          </div>
          <button aria-label="关闭已处理异常弹窗" className="detail-close-btn" type="button" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="ignored-items-body">
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
              rowTemplateColumns="minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr)"
              zoneId="paired"
            />
          )}
        </div>
      </div>
    </div>
  );
}
