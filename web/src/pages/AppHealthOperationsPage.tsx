import { useCallback, useEffect, useRef, useState } from "react";

import { Alert, Button, Spinner, Tooltip } from "@heroui/react";
import { ClipboardCheck, History, RefreshCw } from "lucide-react";

import AppDrawer from "../components/common/AppDrawer";
import {
  FinanceStatusTag,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
  TableCellStack,
} from "../components/common/FinanceTable";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSession, useSessionPermissions } from "../contexts/SessionContext";
import { fetchAppHealthDashboard, fetchInputInvoiceUsageAudit } from "../features/appHealth/api";
import type {
  InputInvoiceUsageAuditPayload,
  OperationsDashboardEndpointPerformance,
  OperationsDashboardImportEvent,
  OperationsDashboardInventoryBlock,
  OperationsDashboardPayload,
  OperationsDashboardPercentiles,
  OperationsDashboardReadModelMetric,
} from "../features/appHealth/types";

const EMPTY_VALUE = "--";
const REFRESH_INTERVAL_MS = 10_000;

type NoticeStatus = "accent" | "warning" | "danger";

function Section({ title, children, testId }: { title: string; children: React.ReactNode; testId: string }) {
  return (
    <section className="app-health-section" data-testid={testId}>
      <header className="app-health-section__header">
        <h2 className="app-health-section__title">{title}</h2>
      </header>
      <div className="app-health-section__body">{children}</div>
    </section>
  );
}

function AppHealthNotice({
  status,
  children,
  role = status === "danger" ? "alert" : "status",
}: {
  status: NoticeStatus;
  children: React.ReactNode;
  role?: "alert" | "status";
}) {
  return (
    <Alert className={`app-health-notice app-health-notice--${status}`} role={role} status={status}>
      <Alert.Indicator />
      <Alert.Content className="app-health-notice__content">
        <Alert.Description className="app-health-notice__description">{children}</Alert.Description>
      </Alert.Content>
    </Alert>
  );
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return EMPTY_VALUE;
  }
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatCountWithSupplement(value: number | null | undefined, supplementary: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return EMPTY_VALUE;
  }
  const base = formatNumber(value);
  if (supplementary === null || supplementary === undefined || !Number.isFinite(supplementary)) {
    return base;
  }
  return `${base}（${formatNumber(supplementary)}）`;
}

function inventorySourceLabel(source: OperationsDashboardInventoryBlock["sources"][number]) {
  if (source.key === "oa_attachment") {
    return `${source.label}（进入统一发票池的数量）`;
  }
  return source.label;
}

function formatMs(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return EMPTY_VALUE;
  }
  return `${Math.round(value)} ms`;
}

function formatSeconds(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return EMPTY_VALUE;
  }
  return `${Math.round(value)} s`;
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) {
    return EMPTY_VALUE;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

type MetricTone = "green" | "yellow" | "red" | "unknown";

function metricTone(value: number | null | undefined, kind: "p95" | "p99"): MetricTone {
  if (value === null || value === undefined) {
    return "unknown";
  }
  if (kind === "p95" && value > 1500) {
    return "red";
  }
  if (kind === "p99" && value > 5000) {
    return "red";
  }
  if ((kind === "p95" && value >= 500) || (kind === "p99" && value > 2500)) {
    return "yellow";
  }
  return "green";
}

function PerformanceCell({ value, kind }: { value: number | null | undefined; kind: "p95" | "p99" }) {
  const tone = metricTone(value, kind);
  return (
    <FinanceTableCell columnRole="status" dataTone={tone}>
      <FinanceStatusTag tone={tone === "green" ? "success" : tone === "yellow" ? "warning" : tone === "red" ? "danger" : "neutral"}>
        {formatMs(value)}
      </FinanceStatusTag>
    </FinanceTableCell>
  );
}

function PercentileCells({ value }: { value: OperationsDashboardPercentiles }) {
  return (
    <>
      <PerformanceCell value={value.p95} kind="p95" />
      <PerformanceCell value={value.p99} kind="p99" />
    </>
  );
}

function sampleLabel(row: OperationsDashboardReadModelMetric) {
  const sampleCount = row.refresh_duration_windows?.recent_15m?.sample_count;
  if (sampleCount === null || sampleCount === undefined) {
    return EMPTY_VALUE;
  }
  return formatNumber(sampleCount);
}

function readModelState(row: OperationsDashboardReadModelMetric) {
  if ((row.unavailable_count ?? 0) > 0) {
    return { label: "failed", tone: "danger" as const };
  }
  if ((row.stale_count ?? 0) > 0) {
    return { label: "refreshing", tone: "warning" as const };
  }
  if (row.status === "unknown") {
    return { label: "unknown", tone: "neutral" as const };
  }
  return { label: "fresh", tone: "success" as const };
}

function workerState(row: OperationsDashboardPayload["runtime_performance"]["workers"][number]) {
  if (row.warning_code || row.status === "unknown" || row.status === "missing" || row.status === "stale" || row.status === "mismatch") {
    return { label: row.warning_code || row.status, tone: row.status === "stale" ? "warning" as const : "danger" as const };
  }
  return { label: row.current_effective === false ? "historical" : "active", tone: row.current_effective === false ? "neutral" as const : "success" as const };
}

function importEventState(row: OperationsDashboardImportEvent) {
  const rawStatus = String(row.status || "");
  const status = rawStatus.toLowerCase();
  if (status === "completed" || status === "success" || status === "succeeded" || status === "done") {
    return { label: rawStatus || "completed", tone: "success" as const };
  }
  if (status === "running" || status === "processing" || status === "pending") {
    return { label: rawStatus, tone: "warning" as const };
  }
  if (status === "failed" || status === "error") {
    return { label: rawStatus, tone: "danger" as const };
  }
  return { label: rawStatus || "unknown", tone: "neutral" as const };
}

function auditStatus(payload: InputInvoiceUsageAuditPayload | null) {
  if (!payload) {
    return { label: "未验证", tone: "neutral" as const };
  }
  const status = String(payload.overall_status || "unknown");
  const blockingIssueCount = payload.summary?.blocking_issue_count ?? 0;
  const errorCount = payload.summary?.error_count ?? 0;
  if (status === "pass" && blockingIssueCount === 0 && errorCount === 0) {
    return { label: "pass", tone: "success" as const };
  }
  if (blockingIssueCount > 0 || errorCount > 0) {
    return { label: status, tone: "danger" as const };
  }
  if (status === "issues_found") {
    return { label: status, tone: "warning" as const };
  }
  return { label: status, tone: "neutral" as const };
}

function AuditMetric({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="app-health-audit-metric">
      <span>{label}</span>
      <strong>{formatNumber(value)}</strong>
    </div>
  );
}

function InputInvoiceUsageAuditPanel({
  payload,
  error,
  isLoading,
  onRun,
}: {
  payload: InputInvoiceUsageAuditPayload | null;
  error: string | null;
  isLoading: boolean;
  onRun: () => void;
}) {
  const state = auditStatus(payload);
  const summary = payload?.summary;
  const issueCodeEntries = Object.entries(summary?.issue_counts_by_code ?? {})
    .sort((left, right) => right[1] - left[1])
    .slice(0, 4);
  const visibleIssues = (payload?.issues ?? []).slice(0, 3);
  return (
    <Section title="Audit" testId="app-health-input-usage-audit">
      <div className="app-health-audit-card">
        <div className="app-health-audit-header">
          <div className="app-health-audit-heading">
            <h3>进项发票使用情况</h3>
            <p>{payload?.generated_at ? formatTimestamp(payload.generated_at) : "未验证"}</p>
          </div>
          <div className="app-health-audit-actions">
            <FinanceStatusTag tone={state.tone}>{state.label}</FinanceStatusTag>
            <Button
              className="app-health-audit-button"
              isDisabled={isLoading}
              onPress={onRun}
              size="sm"
              variant="tertiary"
            >
              {isLoading ? <Spinner color="current" size="sm" /> : <ClipboardCheck aria-hidden="true" size={15} strokeWidth={2.2} />}
              Audit 进项使用
            </Button>
          </div>
        </div>
        {error ? <AppHealthNotice status="danger">{error}</AppHealthNotice> : null}
        <div className="app-health-audit-grid">
          <AuditMetric label="进项发票" value={summary?.active_input_invoice_count} />
          <AuditMetric label="Read model 发票" value={summary?.read_model_invoice_member_count} />
          <AuditMetric label="Read model rows" value={summary?.read_model_row_count} />
          <AuditMetric label="Active relation" value={summary?.active_workbench_pair_relation_count} />
          <AuditMetric label="Relation groups" value={summary?.linked_workbench_relation_group_count} />
          <AuditMetric label="Blocking issues" value={summary?.blocking_issue_count} />
        </div>
        {issueCodeEntries.length > 0 || visibleIssues.length > 0 ? (
          <div className="app-health-audit-issues" aria-label="进项使用 Audit 问题">
            {issueCodeEntries.map(([code, count]) => (
              <FinanceStatusTag key={code} tone={state.tone === "danger" ? "danger" : "warning"}>{`${code}: ${formatNumber(count)}`}</FinanceStatusTag>
            ))}
            {visibleIssues.map((issue, index) => (
              <span key={`${issue.code || "issue"}:${index}`}>{[issue.code, issue.scope_key, issue.subject_id].filter(Boolean).join(" / ") || issue.message || "issue"}</span>
            ))}
          </div>
        ) : null}
      </div>
    </Section>
  );
}

function RuntimeOverview({ payload }: { payload: OperationsDashboardPayload }) {
  const readModels = payload.runtime_performance.read_models;
  const workers = payload.runtime_performance.workers;
  const staleReadModels = readModels.reduce((total, row) => total + (row.stale_count ?? 0), 0);
  const unavailableReadModels = readModels.reduce((total, row) => total + (row.unavailable_count ?? 0), 0);
  const workerIssues = workers.filter((row) => row.warning_code || row.status === "unknown" || row.status === "missing" || row.status === "stale" || row.status === "mismatch").length;
  const outbox = payload.runtime_performance.outbox;
  const queueBacklog = (outbox.pending_count ?? 0) + (outbox.publishing_count ?? 0) + (outbox.failed_count ?? 0) + (outbox.publish_failed_count ?? 0);
  const rows = [
    {
      key: "read-models",
      label: "Read model",
      value: unavailableReadModels > 0
        ? `${unavailableReadModels} failed`
        : staleReadModels > 0
          ? `${staleReadModels} refreshing`
          : `fresh ${readModels.length}`,
      tone: unavailableReadModels > 0 ? "danger" as const : staleReadModels > 0 ? "warning" as const : "success" as const,
    },
    {
      key: "workers",
      label: "Worker",
      value: workerIssues > 0 ? `${workerIssues} issue` : `active ${workers.filter((row) => row.current_effective !== false).length}`,
      tone: workerIssues > 0 ? "warning" as const : "success" as const,
    },
    {
      key: "queue",
      label: "Queue",
      value: queueBacklog > 0 ? `${queueBacklog} backlog` : "no backlog",
      tone: queueBacklog > 0 ? "warning" as const : "success" as const,
    },
  ];
  return (
    <div className="app-health-runtime-overview" data-testid="app-health-runtime-overview">
      {rows.map((row) => (
        <div key={row.key} className="app-health-runtime-overview__item">
          <span>{row.label}</span>
          <FinanceStatusTag tone={row.tone}>{row.value}</FinanceStatusTag>
        </div>
      ))}
    </div>
  );
}

function InventorySummary({ title, block }: { title: string; block: OperationsDashboardInventoryBlock }) {
  return (
    <div className="app-health-inventory-card">
      <div className="app-health-inventory-card__title">{title}</div>
      <div className="app-health-inventory-card__value">{formatNumber(block.total_count)}</div>
      <div className="app-health-inventory-card__meta">{formatTimestamp(block.latest_synced_at)}</div>
    </div>
  );
}

function InventorySourceRows({ title, block }: { title: string; block: OperationsDashboardInventoryBlock }) {
  return (
    <FinanceTable ariaLabel={`${title}来源`} minWidth={360}>
      <FinanceTableHeader>
        <FinanceTableColumn columnRole="identity" isRowHeader>来源</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">数量</FinanceTableColumn>
        <FinanceTableColumn columnRole="date">同步</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
          {block.sources.map((source) => (
            <FinanceTableRow key={source.key} id={source.key}>
              <FinanceTableCell columnRole="identity" textValue={inventorySourceLabel(source)}>{inventorySourceLabel(source)}</FinanceTableCell>
              <FinanceTableCell columnRole="quantity">{formatCountWithSupplement(source.count, source.supplementary_count)}</FinanceTableCell>
              <FinanceTableCell columnRole="date">{formatTimestamp(source.latest_synced_at)}</FinanceTableCell>
            </FinanceTableRow>
          ))}
      </FinanceTableBody>
    </FinanceTable>
  );
}

function ImportEventsTable({ ariaLabel, rows }: { ariaLabel: string; rows: OperationsDashboardImportEvent[] }) {
  return (
    <FinanceTable ariaLabel={ariaLabel} minWidth={760}>
      <FinanceTableHeader>
        <FinanceTableColumn columnRole="identity" isRowHeader>类型</FinanceTableColumn>
        <FinanceTableColumn columnRole="description">文件/来源</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">数量</FinanceTableColumn>
        <FinanceTableColumn columnRole="date">时间</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">状态</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
          {rows.length === 0 ? (
            <FinanceTableRow id="empty-import-events">
              <FinanceTableCell columnRole="identity">{EMPTY_VALUE}</FinanceTableCell>
              <FinanceTableCell columnRole="description">{EMPTY_VALUE}</FinanceTableCell>
              <FinanceTableCell columnRole="quantity">{EMPTY_VALUE}</FinanceTableCell>
              <FinanceTableCell columnRole="date">{EMPTY_VALUE}</FinanceTableCell>
              <FinanceTableCell columnRole="status">{EMPTY_VALUE}</FinanceTableCell>
            </FinanceTableRow>
          ) : (
            rows.map((row, index) => {
              const state = importEventState(row);
              const rowKey = row.key || `${row.source_key}:${row.imported_at ?? index}`;
              return (
                <FinanceTableRow key={rowKey} id={rowKey}>
                  <FinanceTableCell columnRole="identity" textValue={row.label}>{row.label}</FinanceTableCell>
                  <FinanceTableCell columnRole="description" textValue={row.source_name}>
                    <TableCellStack primary={row.source_name || EMPTY_VALUE} secondary={row.imported_by || undefined} />
                  </FinanceTableCell>
                  <FinanceTableCell columnRole="quantity">{formatCountWithSupplement(row.count, row.supplementary_count)}</FinanceTableCell>
                  <FinanceTableCell columnRole="date">{formatTimestamp(row.imported_at)}</FinanceTableCell>
                  <FinanceTableCell columnRole="status">
                    <FinanceStatusTag tone={state.tone}>{state.label}</FinanceStatusTag>
                  </FinanceTableCell>
                </FinanceTableRow>
              );
            })
          )}
      </FinanceTableBody>
    </FinanceTable>
  );
}

function DataInventory({ payload, onOpenImportHistory }: { payload: OperationsDashboardPayload; onOpenImportHistory: () => void }) {
  const importEvents = payload.data_inventory.import_events ?? [];
  const latestImportEvents = importEvents.slice(0, 5);
  return (
    <Section title="数据" testId="app-health-data">
      <div className="app-health-inventory-grid">
        <InventorySummary title="流水" block={payload.data_inventory.bank} />
        <InventorySummary title="发票" block={payload.data_inventory.invoice} />
        <InventorySummary title="OA" block={payload.data_inventory.oa} />
      </div>
      <div className="app-health-source-grid">
        <InventorySourceRows title="银行流水" block={payload.data_inventory.bank} />
        <InventorySourceRows title="发票" block={payload.data_inventory.invoice} />
        <InventorySourceRows title="OA" block={payload.data_inventory.oa} />
      </div>
      <div className="app-health-import-events">
        <div className="app-health-import-events__header">
          <h3 className="app-health-import-events__title">最近导入记录</h3>
          <Button
            className="app-health-history-button"
            isDisabled={importEvents.length === 0}
            onPress={onOpenImportHistory}
            size="sm"
            variant="tertiary"
          >
            <History aria-hidden="true" size={15} strokeWidth={2.2} />
            查看全部导入历史
          </Button>
        </div>
        <ImportEventsTable ariaLabel="最近导入记录" rows={latestImportEvents} />
      </div>
    </Section>
  );
}

function RequestPerformance({ rows }: { rows: OperationsDashboardEndpointPerformance[] }) {
  return (
    <Section title="请求" testId="app-health-requests">
      <FinanceTable ariaLabel="请求性能" minWidth={820}>
        <FinanceTableHeader>
          <FinanceTableColumn columnRole="description" isRowHeader>接口</FinanceTableColumn>
          <FinanceTableColumn columnRole="quantity">样本</FinanceTableColumn>
          <FinanceTableColumn columnRole="status">API p95</FinanceTableColumn>
          <FinanceTableColumn columnRole="status">API p99</FinanceTableColumn>
          <FinanceTableColumn columnRole="status">DB p95</FinanceTableColumn>
          <FinanceTableColumn columnRole="status">DB p99</FinanceTableColumn>
          <FinanceTableColumn columnRole="status">SQL p95</FinanceTableColumn>
          <FinanceTableColumn columnRole="status">连接 p95</FinanceTableColumn>
        </FinanceTableHeader>
        <FinanceTableBody>
            {rows.map((row) => (
              <FinanceTableRow key={row.endpoint} id={row.endpoint}>
                <FinanceTableCell columnRole="description" textValue={row.endpoint}>{row.endpoint}</FinanceTableCell>
                <FinanceTableCell columnRole="quantity">{formatNumber(row.sample_count)}</FinanceTableCell>
                <PercentileCells value={row.duration_ms} />
                <PercentileCells value={row.database_duration_ms} />
                <PerformanceCell value={row.sql_execute_fetch_ms.p95} kind="p95" />
                <PerformanceCell value={row.connection_acquire_ms.p95} kind="p95" />
              </FinanceTableRow>
            ))}
        </FinanceTableBody>
      </FinanceTable>
    </Section>
  );
}

function OutboxTable({ payload }: { payload: OperationsDashboardPayload }) {
  const outbox = payload.runtime_performance.outbox;
  const rows = [
    ["pending", outbox.pending_count],
    ["publishing", outbox.publishing_count],
    ["failed", outbox.failed_count],
    ["publish_failed", outbox.publish_failed_count],
    ["oldest_pending", outbox.oldest_pending_age_seconds],
  ] as const;
  return (
    <FinanceTable ariaLabel="Outbox 状态" minWidth={300}>
      <FinanceTableHeader>
        <FinanceTableColumn columnRole="identity" isRowHeader>Outbox</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">值</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
          {rows.map(([label, value]) => (
            <FinanceTableRow key={label} id={label}>
              <FinanceTableCell columnRole="identity" textValue={label}>{label}</FinanceTableCell>
              <FinanceTableCell columnRole="quantity">{label === "oldest_pending" ? formatSeconds(value) : formatNumber(value)}</FinanceTableCell>
            </FinanceTableRow>
          ))}
      </FinanceTableBody>
    </FinanceTable>
  );
}

function QueueTable({ payload }: { payload: OperationsDashboardPayload }) {
  return (
    <FinanceTable ariaLabel="RabbitMQ 队列" minWidth={720}>
      <FinanceTableHeader>
        <FinanceTableColumn columnRole="identity" isRowHeader>RabbitMQ</FinanceTableColumn>
        <FinanceTableColumn columnRole="description">queue</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">ready</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">unacked</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">consumer</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">DLQ</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
          {payload.runtime_performance.queues.map((row) => (
            <FinanceTableRow key={`${row.event_type}:${row.queue}`} id={`${row.event_type}:${row.queue}`}>
              <FinanceTableCell columnRole="identity">{row.event_type}</FinanceTableCell>
              <FinanceTableCell columnRole="description" textValue={row.queue}>{row.queue}</FinanceTableCell>
              <FinanceTableCell columnRole="quantity">{formatNumber(row.messages)}</FinanceTableCell>
              <FinanceTableCell columnRole="quantity">{formatNumber(row.unacked)}</FinanceTableCell>
              <FinanceTableCell columnRole="quantity">{formatNumber(row.consumers)}</FinanceTableCell>
              <FinanceTableCell columnRole="quantity">{formatNumber(row.dlq_messages)}</FinanceTableCell>
            </FinanceTableRow>
          ))}
      </FinanceTableBody>
    </FinanceTable>
  );
}

function ReadModelTable({ rows }: { rows: OperationsDashboardReadModelMetric[] }) {
  return (
    <FinanceTable ariaLabel="Read Model 状态" minWidth={920}>
      <FinanceTableHeader>
        <FinanceTableColumn columnRole="identity" isRowHeader>Read Model</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">状态</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">15m p95</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">15m p99</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">历史 p95</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">15m 样本</FinanceTableColumn>
        <FinanceTableColumn columnRole="date">最近完成</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">stale</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">unavailable</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
          {rows.map((row) => (
            (() => {
              const state = readModelState(row);
              return (
                <FinanceTableRow key={row.key} id={row.key}>
                  <FinanceTableCell columnRole="identity" textValue={row.key}>{row.key}</FinanceTableCell>
                  <FinanceTableCell columnRole="status"><FinanceStatusTag tone={state.tone}>{state.label}</FinanceStatusTag></FinanceTableCell>
                  <PercentileCells value={row.refresh_duration_ms} />
                  <PerformanceCell value={row.historical_refresh_duration_ms?.p95} kind="p95" />
                  <FinanceTableCell columnRole="quantity">{sampleLabel(row)}</FinanceTableCell>
                  <FinanceTableCell columnRole="date">{formatTimestamp(row.refresh_duration_windows?.recent_15m?.last_completed_at)}</FinanceTableCell>
                  <FinanceTableCell columnRole="quantity">{formatNumber(row.stale_count)}</FinanceTableCell>
                  <FinanceTableCell columnRole="quantity">{formatNumber(row.unavailable_count)}</FinanceTableCell>
                </FinanceTableRow>
              );
            })()
          ))}
      </FinanceTableBody>
    </FinanceTable>
  );
}

function WorkerTable({ payload }: { payload: OperationsDashboardPayload }) {
  return (
    <FinanceTable ariaLabel="Worker 状态" minWidth={900}>
      <FinanceTableHeader>
        <FinanceTableColumn columnRole="identity" isRowHeader>Worker</FinanceTableColumn>
        <FinanceTableColumn columnRole="description">kind</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">状态</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">required</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">lag</FinanceTableColumn>
        <FinanceTableColumn columnRole="description">warning</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
          {payload.runtime_performance.workers.length === 0 ? (
            <FinanceTableRow id="empty-worker">
              <FinanceTableCell columnRole="identity">{EMPTY_VALUE}</FinanceTableCell>
              <FinanceTableCell columnRole="description">{EMPTY_VALUE}</FinanceTableCell>
              <FinanceTableCell columnRole="status">{EMPTY_VALUE}</FinanceTableCell>
              <FinanceTableCell columnRole="status">{EMPTY_VALUE}</FinanceTableCell>
              <FinanceTableCell columnRole="quantity">{EMPTY_VALUE}</FinanceTableCell>
              <FinanceTableCell columnRole="description">{EMPTY_VALUE}</FinanceTableCell>
            </FinanceTableRow>
          ) : (
            payload.runtime_performance.workers.map((row) => (
              (() => {
                const state = workerState(row);
                const workerName = row.worker_instance || row.worker_kind;
                return (
              <FinanceTableRow key={workerName} id={workerName}>
                <FinanceTableCell columnRole="identity" textValue={workerName}>{workerName}</FinanceTableCell>
                <FinanceTableCell columnRole="description" textValue={row.worker_kind}>{row.worker_kind}</FinanceTableCell>
                <FinanceTableCell columnRole="status"><FinanceStatusTag tone={state.tone}>{state.label}</FinanceStatusTag></FinanceTableCell>
                <FinanceTableCell columnRole="status">{row.required === false ? "optional" : "required"}</FinanceTableCell>
                <FinanceTableCell columnRole="quantity">{formatSeconds(row.heartbeat_lag_seconds)}</FinanceTableCell>
                <FinanceTableCell columnRole="description" textValue={row.warning_code || ""}>{row.warning_code || EMPTY_VALUE}</FinanceTableCell>
              </FinanceTableRow>
                );
              })()
            ))
          )}
      </FinanceTableBody>
    </FinanceTable>
  );
}

function RuntimePerformance({ payload }: { payload: OperationsDashboardPayload }) {
  return (
    <Section title="后台" testId="app-health-runtime">
      <RuntimeOverview payload={payload} />
      <div className="app-health-runtime-grid app-health-runtime-grid--primary">
        <OutboxTable payload={payload} />
        <QueueTable payload={payload} />
      </div>
      <div className="app-health-runtime-grid app-health-runtime-grid--secondary">
        <ReadModelTable rows={payload.runtime_performance.read_models} />
        <WorkerTable payload={payload} />
      </div>
    </Section>
  );
}

export default function AppHealthOperationsPage() {
  const session = useSession();
  const permissions = useSessionPermissions();
  const { active } = useOptionalPageActivation("app-health-operations");
  const [payload, setPayload] = useState<OperationsDashboardPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [auditPayload, setAuditPayload] = useState<InputInvoiceUsageAuditPayload | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [isAuditLoading, setAuditLoading] = useState(false);
  const [isImportHistoryOpen, setImportHistoryOpen] = useState(false);
  const inFlightRef = useRef<AbortController | null>(null);
  const auditInFlightRef = useRef<AbortController | null>(null);

  const loadDashboard = useCallback(async () => {
    if (!permissions.canAdminAccess || inFlightRef.current) {
      return;
    }
    const controller = new AbortController();
    inFlightRef.current = controller;
    setIsLoading(true);
    try {
      const nextPayload = await fetchAppHealthDashboard(controller.signal);
      setPayload(nextPayload);
      setLoadError(null);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setLoadError(error instanceof Error && error.message.trim() ? error.message : "AppHealth 状态加载失败。");
    } finally {
      if (inFlightRef.current === controller) {
        inFlightRef.current = null;
      }
      setIsLoading(false);
    }
  }, [permissions.canAdminAccess]);

  const runInputUsageAudit = useCallback(async () => {
    if (!permissions.canAdminAccess || auditInFlightRef.current) {
      return;
    }
    const controller = new AbortController();
    auditInFlightRef.current = controller;
    setAuditLoading(true);
    try {
      const nextPayload = await fetchInputInvoiceUsageAudit(controller.signal);
      setAuditPayload(nextPayload);
      setAuditError(null);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setAuditError(error instanceof Error && error.message.trim() ? error.message : "进项使用 Audit 失败。");
    } finally {
      if (auditInFlightRef.current === controller) {
        auditInFlightRef.current = null;
      }
      setAuditLoading(false);
    }
  }, [permissions.canAdminAccess]);

  useEffect(() => {
    if (!permissions.canAdminAccess || !active) {
      return undefined;
    }
    void loadDashboard();
    const timer = window.setInterval(() => {
      void loadDashboard();
    }, REFRESH_INTERVAL_MS);
    return () => {
      window.clearInterval(timer);
      inFlightRef.current?.abort();
      inFlightRef.current = null;
      auditInFlightRef.current?.abort();
      auditInFlightRef.current = null;
    };
  }, [active, loadDashboard, permissions.canAdminAccess]);

  if (session.status === "loading") {
    return (
      <div className="app-health-page app-health-page--status" data-testid="app-health-page">
        <AppHealthNotice status="accent">正在加载。</AppHealthNotice>
      </div>
    );
  }

  if (!permissions.canAdminAccess) {
    return (
      <div className="app-health-page app-health-page--status" data-testid="app-health-page">
        <AppHealthNotice status="warning">当前账号没有管理员权限，不能查看 AppHealth 运维状态。</AppHealthNotice>
      </div>
    );
  }

  return (
    <div className="app-health-page" data-testid="app-health-page">
      <header className="app-health-header" data-testid="app-health-header">
        <div className="app-health-heading">
          <h1 className="app-health-title">AppHealth 运维状态</h1>
          <p className="app-health-generated-at">{payload ? formatTimestamp(payload.generated_at) : EMPTY_VALUE}</p>
        </div>
        <Tooltip delay={0}>
          <Button
            aria-label="刷新"
            className="app-health-refresh-button"
            isDisabled={isLoading}
            isIconOnly
            onPress={() => {
              void loadDashboard();
            }}
            size="sm"
            variant="tertiary"
          >
            {isLoading ? <Spinner color="current" size="sm" /> : <RefreshCw aria-hidden="true" size={16} strokeWidth={2.2} />}
          </Button>
          <Tooltip.Content>刷新</Tooltip.Content>
        </Tooltip>
      </header>

      {loadError ? <AppHealthNotice status="danger">{loadError}</AppHealthNotice> : null}

      {payload ? (
        <>
          <DataInventory payload={payload} onOpenImportHistory={() => setImportHistoryOpen(true)} />
          <InputInvoiceUsageAuditPanel
            error={auditError}
            isLoading={isAuditLoading}
            onRun={runInputUsageAudit}
            payload={auditPayload}
          />
          <RequestPerformance rows={payload.request_performance.endpoints} />
          <RuntimePerformance payload={payload} />
          <AppDrawer
            className="app-health-import-history-drawer"
            closeLabel="关闭导入历史"
            open={isImportHistoryOpen}
            onClose={() => setImportHistoryOpen(false)}
            title="导入历史"
            width={720}
          >
            <ImportEventsTable ariaLabel="全部导入历史" rows={payload.data_inventory.import_events ?? []} />
          </AppDrawer>
        </>
      ) : !loadError ? (
        <AppHealthNotice status="accent">正在加载。</AppHealthNotice>
      ) : null}
    </div>
  );
}
