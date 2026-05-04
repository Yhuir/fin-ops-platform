import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import type { ReactNode } from "react";

type AppDrawerProps = {
  open: boolean;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
  onClose: () => void;
};

export default function AppDrawer({ open, title, children, footer, width = 420, onClose }: AppDrawerProps) {
  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100%", sm: width }, maxWidth: "100vw" } }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 1.5 }}>
          <Typography component="h2" variant="h6" fontWeight={800}>
            {title}
          </Typography>
          <IconButton aria-label="关闭抽屉" onClick={onClose}>
            <CloseOutlinedIcon />
          </IconButton>
        </Stack>
        <Stack sx={{ flex: 1, minHeight: 0, overflow: "auto", px: 2, py: 1.5 }}>
          {children}
        </Stack>
        {footer ? <Stack sx={{ borderTop: 1, borderColor: "divider", p: 2 }}>{footer}</Stack> : null}
      </Stack>
    </Drawer>
  );
}
