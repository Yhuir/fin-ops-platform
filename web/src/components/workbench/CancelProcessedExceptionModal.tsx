type CancelProcessedExceptionModalProps = {
  affectedCount: number;
  onClose: () => void;
  onConfirm: () => void;
};

export default function CancelProcessedExceptionModal({
  affectedCount,
  onClose,
  onConfirm,
}: CancelProcessedExceptionModalProps) {
  return (
    <div aria-modal="true" className="detail-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        aria-label="取消异常处理确认弹窗"
        className="detail-modal cancel-processed-exception-modal"
        role="dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="detail-modal-header">
          <div>
            <h2>确认取消异常处理</h2>
            <p>确认取消异常处理后，这组记录会回到未配对区域。</p>
          </div>
          <button aria-label="关闭取消异常处理确认弹窗" className="detail-close-btn" type="button" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="detail-modal-body">
          <div className="detail-state-panel">本次将撤回 {affectedCount} 条记录的异常处理状态。</div>
        </div>

        <footer className="detail-modal-footer">
          <button className="secondary-button" type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary-button warning" type="button" onClick={onConfirm}>
            确认取消异常处理
          </button>
        </footer>
      </div>
    </div>
  );
}
