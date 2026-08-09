import { Button } from "@heroui/react";

import AppDialog from "../common/AppDialog";

type ActionStatusModalProps = {
  title: string;
  message: string;
  phase: "loading" | "result";
  onAcknowledge: () => void;
};

export default function ActionStatusModal({ title, message, phase, onAcknowledge }: ActionStatusModalProps) {
  return (
    <AppDialog
      actions={phase === "result" ? (
        <Button onPress={onAcknowledge} variant="primary">
          确定
        </Button>
      ) : undefined}
      ariaLabel="操作状态弹窗"
      className="action-status-modal"
      disableEscapeClose={phase === "loading"}
      isDismissable={phase === "result"}
      maxWidth="sm"
      onClose={onAcknowledge}
      open
      title={title}
    >
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
    </AppDialog>
  );
}
