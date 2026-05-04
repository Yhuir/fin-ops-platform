import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import type { ReactNode } from "react";

type AppDialogProps = {
  open: boolean;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  maxWidth?: "xs" | "sm" | "md" | "lg" | "xl";
  disableEscapeClose?: boolean;
  onClose: () => void;
};

export default function AppDialog({
  open,
  title,
  description,
  children,
  actions,
  maxWidth = "sm",
  disableEscapeClose = false,
  onClose,
}: AppDialogProps) {
  return (
    <Dialog
      open={open}
      fullWidth
      maxWidth={maxWidth}
      aria-labelledby="app-dialog-title"
      aria-describedby={description ? "app-dialog-description" : undefined}
      onClose={(_, reason) => {
        if (disableEscapeClose && reason === "escapeKeyDown") {
          return;
        }
        onClose();
      }}
    >
      <DialogTitle id="app-dialog-title">{title}</DialogTitle>
      <DialogContent dividers>
        {description ? (
          <DialogContentText id="app-dialog-description" sx={{ mb: children ? 2 : 0 }}>
            {description}
          </DialogContentText>
        ) : null}
        {children}
      </DialogContent>
      {actions ? <DialogActions>{actions}</DialogActions> : null}
    </Dialog>
  );
}
