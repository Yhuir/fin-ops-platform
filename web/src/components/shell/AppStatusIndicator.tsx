import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { Chip, ProgressBar, Separator } from "@heroui/react";
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
    return "danger";
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
  const [open, setOpen] = useState(false);
  const [popoverPosition, setPopoverPosition] = useState({ left: 0, top: 0 });
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const reason = appStatus?.overall.reason ?? healthStatus.reason;
  const level = appStatus?.overall.level ?? healthStatus.level;
  const tone = toneFromLevel(level);
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
      setOpen(false);
      closeTimerRef.current = null;
    }, 120);
  };

  const updatePopoverPosition = () => {
    const trigger = triggerRef.current;
    if (!trigger) {
      return;
    }
    const rect = trigger.getBoundingClientRect();
    const popoverWidth = 480;
    const left = Math.max(8, Math.min(rect.right + 8, window.innerWidth - popoverWidth - 16));
    const top = Math.max(8, Math.min(rect.top - 4, window.innerHeight - 32));
    setPopoverPosition({ left, top });
  };

  const openPopover = () => {
    clearCloseTimer();
    updatePopoverPosition();
    setOpen(true);
  };

  const closePopover = () => {
    clearCloseTimer();
    setOpen(false);
  };

  useEffect(() => () => clearCloseTimer(), []);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    updatePopoverPosition();
    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (triggerRef.current?.contains(target) || popoverRef.current?.contains(target)) {
        return;
      }
      closePopover();
    };
    const handlePositionChange = () => updatePopoverPosition();
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    window.addEventListener("resize", handlePositionChange);
    window.addEventListener("scroll", handlePositionChange, true);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
      window.removeEventListener("resize", handlePositionChange);
      window.removeEventListener("scroll", handlePositionChange, true);
    };
  }, [open]);

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
          ref={triggerRef}
          aria-label={reason}
          aria-controls={open ? popperId : undefined}
          aria-expanded={open}
          aria-haspopup="dialog"
          aria-live="polite"
          className={`app-sidebar-brand-mark ${tone}`}
          data-status-reason={reason}
          role="status"
          tabIndex={0}
          onClick={openPopover}
          onFocus={openPopover}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              closePopover();
            }
          }}
          onMouseEnter={openPopover}
          onMouseLeave={scheduleClose}
        >
          <svg className="app-sidebar-brand-status-icon" viewBox="0 0 100 100" aria-hidden="true">
            <circle className="app-sidebar-brand-status-track" cx="50" cy="50" r="37" />
            <circle className="app-sidebar-brand-status-sweep" cx="50" cy="50" r="37" />
          </svg>
        </span>
      {open ? createPortal(
        <div
          ref={popoverRef}
          id={popperId}
          aria-label="全局运行状态"
          className="app-status-popover"
          role="dialog"
          tabIndex={-1}
          style={{
            "--app-status-popover-left": `${popoverPosition.left}px`,
            "--app-status-popover-top": `${popoverPosition.top}px`,
          } as CSSProperties}
          onMouseEnter={clearCloseTimer}
          onMouseLeave={scheduleClose}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              closePopover();
            }
          }}
        >
          <div className="app-status-popover-stack">
            <div className="app-status-popover-header">
              <div className="app-status-popover-heading">
                <h2>运行状态</h2>
                <p>{reason}</p>
              </div>
              <Chip size="sm" color={tone === "error" ? "danger" : tone === "pending" ? "warning" : "success"} variant="soft">
                {overallStatusLabel(level)}
              </Chip>
            </div>

              {tasks.length > 0 ? (
                <>
                  <Separator />
                  <section className="app-status-section">
                    <h3>任务</h3>
                    {tasks.map((task) => (
                      <RouterLink key={task.jobId} to={task.route} className="app-status-task-link">
                        <span className="app-status-task-main">
                          <span className="app-status-task-label">{task.shortLabel}</span>
                          <Chip size="sm" variant="soft">{taskStatusLabel(task)}</Chip>
                        </span>
                        {task.percent !== null ? (
                          <ProgressBar
                            aria-label={`${task.shortLabel} 进度`}
                            className="app-status-task-progress"
                            maxValue={100}
                            value={task.percent}
                          />
                        ) : null}
                      </RouterLink>
                    ))}
                  </section>
                </>
              ) : null}

              <Separator />

              <section className="app-status-section">
                <div className="app-status-section-header">
                  <h3>数据域</h3>
                  <div className="app-status-summary-chips">
                    {blockedDomainCount > 0 ? <Chip size="sm" color="danger" variant="soft">{`阻断 ${blockedDomainCount}`}</Chip> : null}
                    {busyDomainCount > 0 ? <Chip size="sm" color="warning" variant="soft">{`同步 ${busyDomainCount}`}</Chip> : null}
                    {blockedDomainCount === 0 && busyDomainCount === 0 ? <Chip size="sm" color="success" variant="soft">{`已同步 ${domains.length}`}</Chip> : null}
                  </div>
                </div>
                <div className="app-status-domain-grid">
                  {domains.map((domain) => {
                    const scopes = scopeDiagnostics(domain);
                    return (
                      <RouterLink
                        key={domain.key}
                        aria-label={`${domain.label} ${domainStatusLabel(domain.status)}`}
                        to={domain.route}
                        title={domainDebugTitle(domain)}
                        className="app-status-domain-link"
                      >
                        <span className="app-status-domain-main">
                          <span className="app-status-domain-label">{domain.label}</span>
                          <Chip className="app-status-domain-chip" size="sm" color={domainTone(domain)} variant="soft">
                            {domainStatusLabel(domain.status)}
                          </Chip>
                        </span>
                          {scopes.length > 0 ? (
                            <span className="app-status-scope-list">
                              {scopes.map((scope) => (
                                <span
                                  key={`${scope.readModelKey}:${scope.scopeType}:${scope.scopeKey}:${scope.status}`}
                                  className="app-status-scope-row"
                                >
                                  <strong>{scope.scopeKey || scope.scopeType}</strong>
                                  {" · "}
                                  <span>{scope.lastError || domainStatusLabel(scope.status)}</span>
                                </span>
                              ))}
                            </span>
                          ) : null}
                      </RouterLink>
                    );
                  })}
                </div>
              </section>

              {canAdminAccess ? (
                <>
                  <Separator />
                  <RouterLink className="app-status-admin-link" to="/operations/app-health">
                    App Health
                  </RouterLink>
                </>
              ) : null}
          </div>
        </div>,
        document.body,
      ) : null}
    </>
  );
}
