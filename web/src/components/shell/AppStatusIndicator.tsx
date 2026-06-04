import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import LinearProgress from "@mui/material/LinearProgress";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import SvgIcon from "@mui/material/SvgIcon";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router-dom";

import { useAppHealthStatus, useAppStatusOverview } from "../../contexts/AppHealthStatusContext";
import { useSessionPermissions } from "../../contexts/SessionContext";
import type { AppStatusDomain, AppStatusTask } from "../../features/appStatus/types";

function toneFromLevel(level: string) {
  if (level === "blocked") {
    return "error";
  }
  if (level === "busy") {
    return "pending";
  }
  return "ok";
}

function domainTone(domain: AppStatusDomain) {
  if (domain.level === "blocked") {
    return "error";
  }
  if (domain.level === "busy") {
    return "warning";
  }
  return "success";
}

function taskStatusLabel(task: AppStatusTask) {
  if (task.percent !== null) {
    return `${task.percent}%`;
  }
  if (task.status === "queued") {
    return "排队中";
  }
  if (task.status === "running") {
    return "处理中";
  }
  if (task.status === "failed") {
    return "失败";
  }
  if (task.status === "partial_success") {
    return "部分完成";
  }
  return task.status || "后台任务";
}

export default function AppStatusIndicator() {
  const healthStatus = useAppHealthStatus();
  const appStatus = useAppStatusOverview();
  const { canAdminAccess } = useSessionPermissions();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const reason = appStatus?.overall.reason ?? healthStatus.reason;
  const level = appStatus?.overall.level ?? healthStatus.level;
  const tone = toneFromLevel(level);
  const open = Boolean(anchorEl);

  const clearCloseTimer = () => {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };

  const scheduleClose = () => {
    clearCloseTimer();
    closeTimerRef.current = window.setTimeout(() => {
      setAnchorEl(null);
      closeTimerRef.current = null;
    }, 120);
  };

  const openPopover = (target: HTMLElement) => {
    clearCloseTimer();
    setAnchorEl(target);
  };

  const closePopover = () => {
    clearCloseTimer();
    setAnchorEl(null);
  };

  useEffect(() => () => clearCloseTimer(), []);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closePopover();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  return (
    <>
      <span
        aria-label={reason}
        aria-live="polite"
        className={`app-sidebar-brand-mark ${tone}`}
        data-status-reason={reason}
        role="status"
        tabIndex={0}
        onClick={(event) => openPopover(event.currentTarget)}
        onFocus={(event) => openPopover(event.currentTarget)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            closePopover();
          }
        }}
        onMouseEnter={(event) => openPopover(event.currentTarget)}
        onMouseLeave={scheduleClose}
      >
        <SvgIcon className="app-sidebar-brand-status-icon" viewBox="0 0 100 100" aria-hidden="true">
          <circle className="app-sidebar-brand-status-track" cx="50" cy="50" r="37" />
          <circle className="app-sidebar-brand-status-sweep" cx="50" cy="50" r="37" />
        </SvgIcon>
      </span>
      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={closePopover}
        anchorOrigin={{ vertical: "center", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        slotProps={{
          paper: {
            className: "app-status-popover",
            onMouseEnter: clearCloseTimer,
            onMouseLeave: scheduleClose,
            onKeyDown: (event) => {
              if (event.key === "Escape") {
                closePopover();
              }
            },
          },
        }}
      >
        <Stack spacing={1.5} sx={{ width: 360, maxWidth: "calc(100vw - 32px)", p: 2 }}>
          <Stack spacing={0.5}>
            <Typography component="h2" fontWeight={800}>全局运行状态</Typography>
            <Typography color="text.secondary" variant="body2">{reason}</Typography>
            {appStatus?.generatedAt ? (
              <Typography color="text.secondary" variant="caption">更新于 {appStatus.generatedAt}</Typography>
            ) : null}
          </Stack>

          <Divider />

          <Stack spacing={1}>
            <Typography fontWeight={700} variant="body2">后台任务</Typography>
            {appStatus && appStatus.backgroundTasks.length > 0 ? (
              appStatus.backgroundTasks.map((task) => (
                <Box key={task.jobId} component={RouterLink} to={task.route} className="app-status-task-link">
                  <Stack spacing={0.5}>
                    <Stack direction="row" justifyContent="space-between" gap={1}>
                      <Typography fontWeight={700} variant="body2">{task.shortLabel}</Typography>
                      <Chip size="small" label={taskStatusLabel(task)} />
                    </Stack>
                    {task.message ? <Typography color="text.secondary" variant="caption">{task.message}</Typography> : null}
                    {task.percent !== null ? <LinearProgress variant="determinate" value={task.percent} /> : null}
                  </Stack>
                </Box>
              ))
            ) : (
              <Typography color="text.secondary" variant="body2">当前没有后台任务。</Typography>
            )}
          </Stack>

          <Divider />

          <Stack spacing={1}>
            <Typography fontWeight={700} variant="body2">数据域</Typography>
            {appStatus?.domains.map((domain) => (
              <Box key={domain.key} component={RouterLink} to={domain.route} className="app-status-domain-link">
                <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1}>
                  <Stack minWidth={0}>
                    <Typography noWrap fontWeight={700} variant="body2">{domain.label}</Typography>
                    <Typography color="text.secondary" variant="caption">{domain.reason}</Typography>
                    {domain.details.map((detail) => (
                      <Typography key={detail} color="text.secondary" noWrap variant="caption">
                        {detail}
                      </Typography>
                    ))}
                  </Stack>
                  <Chip size="small" color={domainTone(domain)} label={domain.status} />
                </Stack>
              </Box>
            ))}
          </Stack>

          <Divider />

          {canAdminAccess ? (
            <Typography component={RouterLink} to="/operations/app-health" variant="body2">
              查看 App Health
            </Typography>
          ) : null}
        </Stack>
      </Popover>
    </>
  );
}
