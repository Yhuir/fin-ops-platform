import MenuOutlinedIcon from "@mui/icons-material/MenuOutlined";
import AppBar from "@mui/material/AppBar";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Tooltip from "@mui/material/Tooltip";

import BackgroundProgressBlock from "../common/BackgroundProgressBlock";
import type { BackgroundJob } from "../../features/backgroundJobs/types";

type ShellImportProgress = {
  label: string;
  tone: "info" | "loading" | "success" | "error";
};

type AppTopBarProps = {
  embedded: boolean;
  isCompact: boolean;
  primaryJob: BackgroundJob | null;
  extraCount: number;
  connectionFailed: boolean;
  progress: ShellImportProgress | null;
  onOpenMobileSidebar: () => void;
  onAcknowledgeJob: (jobId: string) => void;
  onRetryJob: (jobId: string) => void;
};

export default function AppTopBar({
  embedded,
  isCompact,
  primaryJob,
  extraCount,
  connectionFailed,
  progress,
  onOpenMobileSidebar,
  onAcknowledgeJob,
  onRetryJob,
}: AppTopBarProps) {
  const hasStatusContent = Boolean(primaryJob || connectionFailed || progress);

  if (!isCompact && !hasStatusContent) {
    return null;
  }

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
        </Stack>

        <Stack className="header-actions" direction="row" alignItems="center" spacing={1.5}>
          {primaryJob ? (
            <BackgroundProgressBlock
              kind="job"
              job={primaryJob}
              extraCount={extraCount}
              onAcknowledge={onAcknowledgeJob}
              onRetry={onRetryJob}
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
