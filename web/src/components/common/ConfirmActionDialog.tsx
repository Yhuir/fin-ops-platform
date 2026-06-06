import { Button } from "@heroui/react";

import AppDialog from "./AppDialog";

type ConfirmActionDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  loading?: boolean;
  destructive?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export default function ConfirmActionDialog({
  open,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  loading = false,
  destructive = false,
  onCancel,
  onConfirm,
}: ConfirmActionDialogProps) {
  return (
    <AppDialog
      open={open}
      title={title}
      description={description}
      onClose={onCancel}
      actions={
        <>
          <Button isDisabled={loading} onPress={onCancel} variant="secondary">
            {cancelLabel}
          </Button>
          <Button
            isDisabled={loading}
            isPending={loading}
            onPress={onConfirm}
            variant={destructive ? "danger" : "primary"}
          >
            {loading ? "处理中..." : confirmLabel}
          </Button>
        </>
      }
    />
  );
}
