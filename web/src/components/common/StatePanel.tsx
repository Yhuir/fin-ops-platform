import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

type StatePanelTone = "loading" | "empty" | "error" | "info" | "success" | "warning";

type StatePanelProps = {
  tone: StatePanelTone;
  title?: string;
  children?: ReactNode;
  compact?: boolean;
};

function severityFromTone(tone: StatePanelTone) {
  if (tone === "empty" || tone === "loading") {
    return "info";
  }
  return tone;
}

export default function StatePanel({ tone, title, children, compact = false }: StatePanelProps) {
  if (tone === "loading") {
    return (
      <Alert
        icon={<CircularProgress aria-label="加载中" size={compact ? 16 : 18} />}
        severity="info"
        role="status"
      >
        <Stack spacing={compact ? 0.5 : 1}>
          {title ? <Typography fontWeight={800}>{title}</Typography> : null}
          {children ? <Box>{children}</Box> : null}
          {!compact ? <LinearProgress aria-label="加载进度" /> : null}
        </Stack>
      </Alert>
    );
  }

  return (
    <Alert severity={severityFromTone(tone)} role={tone === "error" ? "alert" : "status"}>
      {title ? <Typography fontWeight={800}>{title}</Typography> : null}
      {children ? <Box sx={{ mt: title ? 0.5 : 0 }}>{children}</Box> : null}
    </Alert>
  );
}
