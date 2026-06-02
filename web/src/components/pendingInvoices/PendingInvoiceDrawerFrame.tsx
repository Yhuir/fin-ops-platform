import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { SxProps, Theme } from "@mui/material/styles";
import type { ReactNode } from "react";

type PendingInvoiceDrawerFrameProps = {
  open: boolean;
  title: string;
  subtitle?: string;
  closeLabel: string;
  width?: number;
  children: ReactNode;
  footer?: ReactNode;
  contentSx?: SxProps<Theme>;
  onClose: () => void;
};

export default function PendingInvoiceDrawerFrame({
  open,
  title,
  subtitle,
  closeLabel,
  width = 720,
  children,
  footer,
  contentSx,
  onClose,
}: PendingInvoiceDrawerFrameProps) {
  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      transitionDuration={{ enter: 180, exit: 140 }}
      PaperProps={{
        sx: { width: { xs: "100%", sm: width }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2.5, py: 1.5 }}>
          <Box sx={{ minWidth: 0 }}>
            <Typography component="h2" variant="h6" fontWeight={900} noWrap>{title}</Typography>
            {subtitle ? (
              <Typography variant="caption" color="text.secondary" noWrap>
                {subtitle}
              </Typography>
            ) : null}
          </Box>
          <IconButton aria-label={closeLabel} onClick={onClose}>
            <CloseOutlinedIcon />
          </IconButton>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={[{ flex: 1, minHeight: 0, overflow: "auto", p: 2.5 }, ...(Array.isArray(contentSx) ? contentSx : [contentSx])]}>
          {children}
        </Stack>
        {footer ? (
          <>
            <Divider />
            <Box sx={{ p: 2 }}>{footer}</Box>
          </>
        ) : null}
      </Stack>
    </Drawer>
  );
}
