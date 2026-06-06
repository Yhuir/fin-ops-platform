import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import ClickAwayListener from "@mui/material/ClickAwayListener";
import Divider from "@mui/material/Divider";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Popper from "@mui/material/Popper";
import Stack from "@mui/material/Stack";
import SvgIcon from "@mui/material/SvgIcon";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router-dom";

import { useAppHealthStatus, useAppStatusOverview } from "../../contexts/AppHealthStatusContext";
import { useOptionalSessionPermissions } from "../../contexts/SessionContext";
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

function overallStatusLabel(level: string) {
  if (level === "blocked") {
    return "阻断";
  }
  if (level === "busy") {
    return "同步中";
  }
  return "正常";
}

function domainStatusLabel(status: string) {
  if (status === "ready" || status === "fresh") {
    return "已同步";
  }
  if (status === "missing") {
    return "缺失";
  }
  if (status === "refreshing" || status === "loading" || status === "processing") {
    return "同步";
  }
  if (status === "stale") {
    return "过期";
  }
  if (status === "schema_mismatch") {
    return "结构";
  }
  if (status === "source_mismatch") {
    return "版本";
  }
  if (status === "failed") {
    return "失败";
  }
  if (status === "unavailable") {
    return "不可用";
  }
  return status || "状态";
}

function scopeDiagnostics(domain: AppStatusDomain) {
  if (domain.level === "ok") {
    return [];
  }
  return domain.readModelScopes
    .filter((scope) => scope.status !== "ready" && scope.status !== "fresh")
    .slice(0, 3);
}

function domainDebugTitle(domain: AppStatusDomain) {
  return [domain.label, domain.reason, ...domain.details].filter(Boolean).join(" · ");
}

export default function AppStatusIndicator() {
  const healthStatus = useAppHealthStatus();
  const appStatus = useAppStatusOverview();
  const { canAdminAccess } = useOptionalSessionPermissions();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const reason = appStatus?.overall.reason ?? healthStatus.reason;
  const level = appStatus?.overall.level ?? healthStatus.level;
  const tone = toneFromLevel(level);
  const open = Boolean(anchorEl);
  const popperId = "global-app-status-popover";
  const tasks = appStatus?.backgroundTasks ?? [];
  const domains = appStatus?.domains ?? [];
  const busyDomainCount = domains.filter((domain) => domain.level === "busy").length;
  const blockedDomainCount = domains.filter((domain) => domain.level === "blocked").length;

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
        aria-controls={open ? popperId : undefined}
        aria-expanded={open}
        aria-haspopup="dialog"
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
      <Popper
        id={popperId}
        open={open}
        anchorEl={anchorEl}
        placement="right-start"
        modifiers={[
          { name: "offset", options: { offset: [8, -4] } },
          { name: "preventOverflow", options: { padding: 16 } },
        ]}
        sx={{ zIndex: (theme) => theme.zIndex.modal + 1 }}
      >
        <ClickAwayListener mouseEvent="onMouseDown" touchEvent="onTouchStart" onClickAway={closePopover}>
          <Paper
            aria-label="全局运行状态"
            className="app-status-popover"
            elevation={8}
            role="dialog"
            tabIndex={-1}
            onMouseEnter={clearCloseTimer}
            onMouseLeave={scheduleClose}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                closePopover();
              }
            }}
          >
            <Stack spacing={1} sx={{ width: 480, maxWidth: "calc(100vw - 32px)", p: 1.25 }}>
              <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1}>
                <Stack minWidth={0} spacing={0.25}>
                  <Typography component="h2" fontWeight={800} variant="body2">运行状态</Typography>
                  <Typography color="text.secondary" noWrap variant="caption">{reason}</Typography>
                </Stack>
                <Chip size="small" color={tone === "error" ? "error" : tone === "pending" ? "warning" : "success"} label={overallStatusLabel(level)} />
              </Stack>

              {tasks.length > 0 ? (
                <>
                  <Divider />
                  <Stack spacing={0.75}>
                    <Typography color="text.secondary" fontWeight={700} variant="caption">任务</Typography>
                    {tasks.map((task) => (
                    <Box key={task.jobId} component={RouterLink} to={task.route} className="app-status-task-link">
                      <Stack spacing={0.4}>
                        <Stack direction="row" justifyContent="space-between" gap={1}>
                          <Typography noWrap fontWeight={700} variant="caption">{task.shortLabel}</Typography>
                          <Chip size="small" label={taskStatusLabel(task)} />
                        </Stack>
                        {task.percent !== null ? <LinearProgress variant="determinate" value={task.percent} /> : null}
                      </Stack>
                    </Box>
                    ))}
                  </Stack>
                </>
              ) : null}

              <Divider />

              <Stack spacing={0.75}>
                <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1}>
                  <Typography color="text.secondary" fontWeight={700} variant="caption">数据域</Typography>
                  <Stack direction="row" gap={0.5}>
                    {blockedDomainCount > 0 ? <Chip size="small" color="error" label={`阻断 ${blockedDomainCount}`} /> : null}
                    {busyDomainCount > 0 ? <Chip size="small" color="warning" label={`同步 ${busyDomainCount}`} /> : null}
                    {blockedDomainCount === 0 && busyDomainCount === 0 ? <Chip size="small" color="success" label={`已同步 ${domains.length}`} /> : null}
                  </Stack>
                </Stack>
                <Box className="app-status-domain-grid">
                  {domains.map((domain) => {
                    const scopes = scopeDiagnostics(domain);
                    return (
                      <Box
                        key={domain.key}
                        aria-label={`${domain.label} ${domainStatusLabel(domain.status)}`}
                        component={RouterLink}
                        to={domain.route}
                        title={domainDebugTitle(domain)}
                        className="app-status-domain-link"
                      >
                        <Stack spacing={0.35} minWidth={0}>
                          <Stack direction="row" alignItems="center" justifyContent="space-between" gap={0.75}>
                            <Typography noWrap fontWeight={700} variant="caption">{domain.label}</Typography>
                            <Chip className="app-status-domain-chip" size="small" color={domainTone(domain)} label={domainStatusLabel(domain.status)} />
                          </Stack>
                          {scopes.length > 0 ? (
                            <Stack spacing={0.2}>
                              {scopes.map((scope) => (
                                <Typography
                                  key={`${scope.readModelKey}:${scope.scopeType}:${scope.scopeKey}:${scope.status}`}
                                  color="text.secondary"
                                  noWrap
                                  variant="caption"
                                >
                                  <Box component="span" fontWeight={700}>{scope.scopeKey || scope.scopeType}</Box>
                                  {" · "}
                                  <Box component="span">{scope.lastError || domainStatusLabel(scope.status)}</Box>
                                </Typography>
                              ))}
                            </Stack>
                          ) : null}
                        </Stack>
                      </Box>
                    );
                  })}
                </Box>
              </Stack>

              {canAdminAccess ? (
                <>
                  <Divider />
                  <Typography component={RouterLink} to="/operations/app-health" variant="caption">
                    App Health
                  </Typography>
                </>
              ) : null}
            </Stack>
          </Paper>
        </ClickAwayListener>
      </Popper>
    </>
  );
}
