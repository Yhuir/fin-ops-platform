import { workbenchColumns } from "../../features/workbench/tableConfig";
import type { WorkbenchRecord } from "../../features/workbench/types";

type IgnoredItemsModalProps = {
  rows: WorkbenchRecord[];
  highlightedRowId?: string | null;
  canMutateData: boolean;
  onClose: () => void;
  onUnignore: (row: WorkbenchRecord) => void;
};

export default function IgnoredItemsModal({
  rows,
  highlightedRowId,
  canMutateData,
  onClose,
  onUnignore,
}: IgnoredItemsModalProps) {
  const columns = workbenchColumns.invoice;

  return (
    <div aria-modal="true" className="detail-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        aria-label="已忽略弹窗"
        className="detail-modal ignored-items-modal"
        role="dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="detail-modal-header">
          <div>
            <h2>已忽略</h2>
            <p>直接查看当前月份已忽略的发票，可随时撤回。</p>
          </div>
          <button aria-label="关闭已忽略弹窗" className="detail-close-btn" type="button" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="ignored-items-body">
          {rows.length === 0 ? (
            <div className="detail-state-panel">当前没有已忽略项。</div>
          ) : (
            <div className="ignored-items-table">
              <div className="ignored-items-header" role="row">
                {columns.map((column) => (
                  <div key={column.key} className="ignored-items-cell ignored-items-header-cell" role="columnheader">
                    {column.label}
                  </div>
                ))}
                <div className="ignored-items-cell ignored-items-header-cell ignored-items-action-cell" role="columnheader">
                  操作
                </div>
              </div>
              {rows.map((row) => (
                <div
                  key={row.id}
                  className={`ignored-items-row${highlightedRowId === row.id ? " search-target-highlighted" : ""}`}
                  data-row-id={row.id}
                  data-search-highlighted={highlightedRowId === row.id ? "true" : "false"}
                  role="row"
                >
                  {columns.map((column) => (
                    <div key={column.key} className="ignored-items-cell" role="cell">
                      {row.tableValues[column.key] ?? "--"}
                    </div>
                  ))}
                  <div className="ignored-items-cell ignored-items-action-cell" role="cell">
                    {canMutateData ? (
                      <button className="row-action-btn primary" type="button" onClick={() => onUnignore(row)}>
                        撤回忽略
                      </button>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
