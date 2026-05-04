import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import Alert from "@mui/material/Alert";
import type { ReactNode } from "react";

type PermissionNoticeProps = {
  children: ReactNode;
};

export default function PermissionNotice({ children }: PermissionNoticeProps) {
  return (
    <Alert icon={<LockOutlinedIcon fontSize="inherit" />} severity="warning">
      {children}
    </Alert>
  );
}
