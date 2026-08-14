import {
  Chip,
  PopoverContent,
  PopoverDialog,
  PopoverRoot,
  PopoverTrigger,
  ProgressBar,
  Separator,
} from "@heroui/react";
import { Link as RouterLink } from "react-router-dom";

import { useAppHealthStatus, useAppStatusOverview } from "../../contexts/AppHealthStatusContext";
import { useOptionalSessionPermissions } from "../../contexts/SessionContext";
import type { AppStatusDomain, AppStatusQueueSummary, AppStatusRuntimeSummaryGroup, AppStatusTask } from "../../features/appStatus/types";
import financePlatformMark from "./finance-platform-mark.svg";

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

function importTaskObjectName(task: AppStatusTask) {
  const domains = new Set(task.affectedDomains);
  if (task.type === "invoice_import" || domains.has("imports_invoices") || task.route === "/imports/invoices") {
    return "发票";
  }
  if (
    task.type === "etc_invoice_import"
    || domains.has("imports_etc_invoices")
    || task.route === "/imports/etc-invoices"
  ) {
    return "ETC发票";
  }
  if (
    task.type === "bank_transaction_import"
    || domains.has("imports_bank_transactions")
    || task.route === "/imports/bank-transactions"
  ) {
    return "银行流水";
  }
  return null;
}

function taskPrimaryLabel(task: AppStatusTask) {
  const importObjectName = importTaskObjectName(task);
  if (importObjectName && task.total > 0) {
    return `正在导入${importObjectName} ${task.current}/${task.total}`;
  }
  if (importObjectName) {
    return `正在导入${importObjectName}`;
  }
  return task.shortLabel;
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
    return "来源异常";
  }
  if (status === "failed") {
    return "失败";
  }
  if (status === "unavailable") {
    return "不可用";
  }
  return status || "状态";
}

function domainDebugTitle(domain: AppStatusDomain) {
  return [domain.label, domain.reason, ...domain.details].filter(Boolean).join(" · ");
}

function workerSummaryLabel(summary: AppStatusRuntimeSummaryGroup | undefined) {
  if (!summary || summary.total === 0) {
    return "暂无 worker 事实";
  }
  const issueCount = (summary.stale ?? 0) + (summary.missing ?? 0) + (summary.mismatched ?? 0) + (summary.unavailable ?? 0);
  if (issueCount > 0) {
    return `${summary.stale ?? 0} stale / ${summary.missing ?? 0} missing / ${summary.mismatched ?? 0} mismatch`;
  }
  if ((summary.working ?? 0) > 0) {
    return `${summary.working ?? 0} working / ${summary.idle ?? 0} idle`;
  }
  return `全部 active ${summary.ready ?? summary.idle ?? 0}/${summary.required ?? summary.total}`;
}

function queueSummaryLabel(summary: AppStatusQueueSummary | undefined) {
  if (!summary || summary.eventTypeCount === 0) {
    return "无队列积压";
  }
  if (summary.failed > 0) {
    return `${summary.failed} failed / ${summary.backlog} backlog`;
  }
  if (summary.pending > 0 || summary.processing > 0) {
    return `${summary.pending} pending / ${summary.processing} processing`;
  }
  return "无队列积压";
}

function summaryTone(value: number | undefined) {
  return value && value > 0 ? "warning" : "success";
}

type AppStatusIndicatorProps = {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
};

export default function AppStatusIndicator({ isOpen, onOpenChange }: AppStatusIndicatorProps) {
  const healthStatus = useAppHealthStatus();
  const appStatus = useAppStatusOverview();
  const { canAdminAccess } = useOptionalSessionPermissions();
  const reason = appStatus?.overall.reason ?? healthStatus.reason;
  const level = appStatus?.overall.level ?? healthStatus.level;
  const tone = toneFromLevel(level);
  const tasks = appStatus?.backgroundTasks ?? [];
  const domains = appStatus?.domains ?? [];
  const runtimeSummary = appStatus?.runtimeSummary;
  const busyDomainCount = domains.filter((domain) => domain.level === "busy").length;
  const blockedDomainCount = domains.filter((domain) => domain.level === "blocked").length;
  const workerIssues = runtimeSummary?.workers.issueCount ?? 0;
  const queueIssues = runtimeSummary ? runtimeSummary.queue.failed + runtimeSummary.queue.backlog : 0;

  return (
    <PopoverRoot isOpen={isOpen} onOpenChange={onOpenChange}>
      <PopoverTrigger
        aria-label={reason}
        aria-live="polite"
        className={`app-sidebar-brand-mark ${tone}`}
        data-status-reason={reason}
      >
        <img alt="" className="app-sidebar-brand-status-icon" src={financePlatformMark} />
        <span className="app-sidebar-brand-status-dot" aria-hidden="true" />
      </PopoverTrigger>
      <PopoverContent className="app-status-popover-content" placement="right top">
        <PopoverDialog aria-label="全局运行状态" className="app-status-popover">
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
                          <span className="app-status-task-label">{taskPrimaryLabel(task)}</span>
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
                <h3>运行摘要</h3>
                <div className="app-status-runtime-summary" data-testid="app-status-runtime-summary">
                  <div className="app-status-summary-row">
                    <span>Worker</span>
                    <Chip size="sm" color={summaryTone(workerIssues)} variant="soft">
                      {workerSummaryLabel(runtimeSummary?.workers)}
                    </Chip>
                  </div>
                  <div className="app-status-summary-row">
                    <span>Queue</span>
                    <Chip size="sm" color={summaryTone(queueIssues)} variant="soft">
                      {queueSummaryLabel(runtimeSummary?.queue)}
                    </Chip>
                  </div>
                </div>
              </section>

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
        </PopoverDialog>
      </PopoverContent>
    </PopoverRoot>
  );
}
