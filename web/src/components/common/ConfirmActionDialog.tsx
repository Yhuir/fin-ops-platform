import Button from "@mui/material/Button";

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
          <Button disabled={loading} onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            variant="contained"
            color={destructive ? "error" : "primary"}
            disabled={loading}
            onClick={onConfirm}
          >
            {loading ? "处理中..." : confirmLabel}
          </Button>
        </>
      }
    />
  );
}
