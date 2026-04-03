import { useEffect } from "react";

type ActionStatusModalProps = {
  title: string;
  message: string;
  phase: "loading" | "result";
  onAcknowledge: () => void;
};

export default function ActionStatusModal({ title, message, phase, onAcknowledge }: ActionStatusModalProps) {
  useEffect(() => {
    if (phase !== "result") {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onAcknowledge();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [phase, onAcknowledge]);

  return (
    <div
      aria-label="操作状态弹窗"
      aria-modal="true"
      className="detail-modal-backdrop"
      role="dialog"
    >
      <div className="action-status-modal" onClick={(event) => event.stopPropagation()}>
        <div className="action-status-modal-header">
          <div className="detail-drawer-title">{title}</div>
        </div>
        <div className="action-status-modal-body">
          {phase === "loading" ? (
            <div className="action-status-loading">
              <span aria-hidden="true" className="action-status-spinner" />
              <span>{message}</span>
            </div>
          ) : (
            <div className="detail-state-panel">{message}</div>
          )}
        </div>
        <div className="action-status-modal-actions">
          {phase === "result" ? (
            <button className="primary-button" type="button" onClick={onAcknowledge}>
              确定
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
