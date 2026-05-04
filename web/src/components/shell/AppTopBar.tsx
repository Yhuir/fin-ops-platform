import MenuOutlinedIcon from "@mui/icons-material/MenuOutlined";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import BackgroundProgressBlock from "../common/BackgroundProgressBlock";
import type { BackgroundJob } from "../../features/backgroundJobs/types";

type ShellImportProgress = {
  label: string;
  tone: "info" | "loading" | "success" | "error";
};

export function HeaderStatusIndicator({ level, reason }: { level: "ok" | "pending" | "error"; reason: string }) {
  return (
    <div
      aria-label={reason}
      aria-live="polite"
      className={`global-status-indicator ${level}`}
      data-status-reason={reason}
      role="status"
      title={reason}
    >
      <span className="global-status-dot" aria-hidden="true" />
    </div>
  );
}

type AppTopBarProps = {
  embedded: boolean;
  isCompact: boolean;
  workbenchStatus: { level: "ok" | "pending" | "error"; reason: string } | null;
  primaryJob: BackgroundJob | null;
  extraCount: number;
  connectionFailed: boolean;
  progress: ShellImportProgress | null;
  onOpenMobileSidebar: () => void;
  onAcknowledgeJob: (jobId: string) => void;
};

export default function AppTopBar({
  embedded,
  isCompact,
  workbenchStatus,
  primaryJob,
  extraCount,
  connectionFailed,
  progress,
  onOpenMobileSidebar,
  onAcknowledgeJob,
}: AppTopBarProps) {
  return (
    <AppBar
      className={`global-header${embedded ? " embedded-header" : ""}`}
      color="inherit"
      elevation={0}
      position="sticky"
    >
      <Toolbar className="global-toolbar" disableGutters>
        <Stack className="global-header-main" direction="row" alignItems="center" spacing={1.5}>
          {isCompact ? (
            <Tooltip title="打开菜单">
              <IconButton aria-label="打开菜单" edge="start" onClick={onOpenMobileSidebar}>
                <MenuOutlinedIcon />
              </IconButton>
            </Tooltip>
          ) : null}
          <Box className="global-heading-block">
            <Typography className="eyebrow" component="div">
              溯源办公系统
            </Typography>
            <Typography className="global-title" component="div">
              财务运营平台
            </Typography>
          </Box>
          {workbenchStatus ? <HeaderStatusIndicator level={workbenchStatus.level} reason={workbenchStatus.reason} /> : null}
        </Stack>

        <Stack className="header-actions" direction="row" alignItems="center" spacing={1.5}>
          {primaryJob ? (
            <BackgroundProgressBlock
              kind="job"
              job={primaryJob}
              extraCount={extraCount}
              onAcknowledge={onAcknowledgeJob}
            />
          ) : connectionFailed ? (
            <BackgroundProgressBlock kind="connection_error" />
          ) : progress ? (
            <div className={`global-progress-chip ${progress.tone}`} aria-live="polite">
              <span className="global-progress-label">进度</span>
              <strong>{progress.label}</strong>
            </div>
          ) : null}
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
