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
import { fetchAppHealthDashboard, fetchPageAudit } from "../features/appHealth/api";
import type {
  AppHealthSystemAuditPayload,
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

function inventorySource(block: OperationsDashboardInventoryBlock, key: string) {
  return block.sources.find((source) => source.key === key);
}

function partitionDifference(total: number | null | undefined, values: Array<number | null | undefined>) {
  const knownValues = values.filter((value): value is number => value !== null && value !== undefined && Number.isFinite(value));
  if (total === null || total === undefined || !Number.isFinite(total) || knownValues.length !== values.length) {
    return null;
  }
  const difference = Math.abs(total - knownValues.reduce((sum, value) => sum + value, 0));
  return difference === 0 ? null : difference;
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

function latestScopeEvidence(row: OperationsDashboardReadModelMetric) {
  return row.scope_evidence?.[0];
}

function scopeEvidenceTitle(row: OperationsDashboardReadModelMetric) {
  const evidence = latestScopeEvidence(row);
  if (!evidence) {
    return "暂无 scope 运行证据";
  }
  return JSON.stringify({
    expected_source_version: evidence.expected_source_version,
    projection_status: evidence.projection_status,
    projection_source_versions: evidence.projection_source_versions,
    lag_seconds: evidence.lag_seconds,
    queue_wait_ms: evidence.queue_wait_ms,
    handler_duration_ms: evidence.handler_duration_ms,
    retry_count: evidence.retry_count,
    dedupe_reason: evidence.dedupe_reason,
    last_error: evidence.last_error,
  });
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

function auditStatus(payload: AppHealthSystemAuditPayload | null) {
  if (!payload) {
    return { label: "未验证", tone: "neutral" as const };
  }
  const status = String(payload.overall_status || "unknown");
  const blockingIssueSampleCount = payload.summary?.blocking_issue_sample_count ?? 0;
  const errorSampleCount = payload.summary?.error_sample_count ?? 0;
  const proofReady = payload.audit_contract?.proof_availability === "ready";
  const proofVersioned = Boolean(payload.audit_contract?.contract_revision);
  const snapshotConsistent =
    payload.audit_contract?.database_snapshot === true
    && payload.audit_contract?.snapshot_consistency === "repeatable_read_read_only";
  if (
    status === "pass"
    && payload.audit_status?.integrity === "pass"
    && payload.audit_status?.freshness === "fresh"
    && payload.audit_status?.queue === "drained"
    && proofReady
    && proofVersioned
    && snapshotConsistent
    && blockingIssueSampleCount === 0
    && errorSampleCount === 0
  ) {
    return { label: "pass", tone: "success" as const };
  }
  if (!proofReady || !proofVersioned || !snapshotConsistent) {
    return { label: "proof_unavailable", tone: "danger" as const };
  }
  if (payload.audit_status?.integrity === "issues_found" || blockingIssueSampleCount > 0 || errorSampleCount > 0) {
    return { label: status, tone: "danger" as const };
  }
  if (
    payload.audit_status?.freshness === "not_fresh"
    || payload.audit_status?.queue !== "drained"
    || status === "issues_found"
  ) {
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

function AppHealthSystemAuditPanel({
  payload,
  error,
  isLoading,
  onRun,
}: {
  payload: AppHealthSystemAuditPayload | null;
  error: string | null;
  isLoading: boolean;
  onRun: () => void;
}) {
  const state = auditStatus(payload);
  const summary = payload?.summary;
  const registeredPageLabel = typeof summary?.registered_page_count === "number"
    ? `${summary.registered_page_count} 页 App 内部合同`
    : "App 内部合同";
  const externalStatus = payload?.external_evidence?.status ?? "unknown";
  const externalTone = externalStatus === "pass" ? "success" : externalStatus === "fail" ? "danger" : externalStatus === "unknown" ? "warning" : "neutral";
  const issueCodeEntries = Object.entries(summary?.issue_sample_counts_by_code ?? {})
    .sort((left, right) => right[1] - left[1])
    .slice(0, 4);
  const visibleIssues = (payload?.issues ?? []).slice(0, 3);
  return (
    <Section title="System Audit" testId="app-health-system-audit">
      <div className="app-health-audit-card">
        <div className="app-health-audit-header">
          <div className="app-health-audit-heading">
            <h3>{registeredPageLabel}</h3>
            <p>{payload?.database_system_snapshot?.snapshot_generated_at ? formatTimestamp(payload.database_system_snapshot.snapshot_generated_at) : "未验证"}</p>
          </div>
          <div className="app-health-audit-actions">
            <FinanceStatusTag tone={state.tone}>{state.label}</FinanceStatusTag>
            <Tooltip delay={0}>
              <Tooltip.Trigger>
                <Button
                  aria-label="Audit 全系统 App 内部合同"
                  className="app-health-audit-button"
                  isDisabled={isLoading}
                  isIconOnly
                  onPress={onRun}
                  size="sm"
                  variant="tertiary"
                >
                  {isLoading ? <Spinner color="current" size="sm" /> : <ClipboardCheck aria-hidden="true" size={15} strokeWidth={2.2} />}
                </Button>
              </Tooltip.Trigger>
              <Tooltip.Content>Audit 全系统 App 内部合同</Tooltip.Content>
            </Tooltip>
          </div>
        </div>
        {error ? <AppHealthNotice status="danger">{error}</AppHealthNotice> : null}
        <div className="app-health-audit-grid">
          <AuditMetric label="注册页面" value={summary?.registered_page_count} />
          <AuditMetric label="业务页面 Audit" value={summary?.audited_business_page_count} />
          <AuditMetric label="业务页面通过" value={summary?.passed_business_page_count} />
          <AuditMetric label="外部域 unknown" value={payload?.external_evidence?.summary?.unknown_domain_count ?? payload?.external_evidence?.domains?.filter((item) => item.status === "unknown").length} />
          <AuditMetric label="问题样本" value={summary?.issue_sample_count} />
          <AuditMetric label="Blocking samples" value={summary?.blocking_issue_sample_count} />
        </div>
        {payload ? (
          <div className="app-health-audit-issues" aria-label="System Audit 证明边界">
            <FinanceStatusTag tone={state.tone}>{`App 内部 ${summary?.database_internal_contracts ?? "unknown"}`}</FinanceStatusTag>
            <FinanceStatusTag tone={externalTone}>
              {`外部证据 ${externalStatus}`}
            </FinanceStatusTag>
            <span>仅证明该只读数据库快照内的已登记 App 内部合同；后续写入会使本结果失效。</span>
            {(payload.external_evidence?.domains ?? []).map((domain) => (
              <FinanceStatusTag
                key={domain.domain ?? "external-domain"}
                tone={domain.status === "pass" ? "success" : domain.status === "fail" ? "danger" : "warning"}
              >
                {`${domain.domain ?? "external"} ${domain.status ?? "unknown"}${domain.observed_at ? ` · ${formatTimestamp(domain.observed_at)}` : ""}`}
              </FinanceStatusTag>
            ))}
            <span>{payload.external_evidence?.claim_boundary ?? "外部来源证明未登记；App 内部绿色不能替代外部来源对账。"}</span>
          </div>
        ) : null}
        {issueCodeEntries.length > 0 || visibleIssues.length > 0 ? (
          <div className="app-health-audit-issues" aria-label="System Audit 问题">
            {issueCodeEntries.map(([code, count]) => (
              <FinanceStatusTag key={code} tone={state.tone === "danger" ? "danger" : "warning"}>{`${code}: ${formatNumber(count)}`}</FinanceStatusTag>
            ))}
            {visibleIssues.map((issue, index) => (
              <span key={`${issue.code || "issue"}:${index}`}>{issue.message || issue.code || "检测到问题"}</span>
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

function InventoryPanel({
  title,
  syncedAt,
  children,
}: {
  title: string;
  syncedAt: string | null | undefined;
  children: React.ReactNode;
}) {
  return (
    <section className="app-health-inventory-panel">
      <header className="app-health-inventory-panel__header">
        <h3>{title}</h3>
        <span>同步 {formatTimestamp(syncedAt)}</span>
      </header>
      <div className="app-health-inventory-table-shell">{children}</div>
    </section>
  );
}

function BankInventory({ block }: { block: OperationsDashboardInventoryBlock }) {
  return (
    <InventoryPanel title="流水" syncedAt={block.latest_synced_at}>
      <table aria-label="银行流水来源" className="app-health-inventory-table">
        <thead>
          <tr><th scope="col">来源</th><th scope="col">数量</th><th scope="col">最近同步</th></tr>
        </thead>
        <tbody>
          {block.sources.map((source) => (
            <tr key={source.key}>
              <th scope="row">{source.label}</th>
              <td className="app-health-inventory-table__number">{formatNumber(source.count)}</td>
              <td>{formatTimestamp(source.latest_synced_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </InventoryPanel>
  );
}

function InvoiceInventory({ block }: { block: OperationsDashboardInventoryBlock }) {
  const input = inventorySource(block, "input_invoice");
  const output = inventorySource(block, "output_invoice");
  const manual = inventorySource(block, "manual");
  const oa = inventorySource(block, "oa_attachment");
  const typeDifference = partitionDifference(block.total_count, [input?.count, output?.count]);
  const importDifference = partitionDifference(block.total_count, [manual?.count, oa?.supplementary_count]);

  const dimensionCell = (label: string, difference: number | null) => (
    <th className="app-health-inventory-table__dimension" rowSpan={2} scope="rowgroup">
      <span>{label}</span>
      {difference !== null ? <small role="status">口径未闭合 · 差异 {formatNumber(difference)}</small> : null}
    </th>
  );

  return (
    <InventoryPanel title="发票统计" syncedAt={block.latest_synced_at}>
      <table aria-label="发票统计" className="app-health-inventory-table app-health-inventory-table--invoice">
        <thead>
          <tr><th scope="col">统计维度</th><th scope="col">分类</th><th scope="col">数量</th><th scope="col">合计</th><th scope="col">最近同步</th></tr>
        </thead>
        <tbody>
          <tr>
            {dimensionCell("按类型分", typeDifference)}
            <th scope="row">{input?.label ?? "进项发票"}</th>
            <td className="app-health-inventory-table__number">{formatNumber(input?.count)}</td>
            <td className="app-health-inventory-table__total" rowSpan={2}>{formatNumber(block.total_count)}</td>
            <td>{formatTimestamp(input?.latest_synced_at)}</td>
          </tr>
          <tr>
            <th scope="row">{output?.label ?? "销项发票"}</th>
            <td className="app-health-inventory-table__number">{formatNumber(output?.count)}</td>
            <td>{formatTimestamp(output?.latest_synced_at)}</td>
          </tr>
          <tr>
            {dimensionCell("按导入方式分", importDifference)}
            <th scope="row">{manual?.label ?? "手工导入"}</th>
            <td className="app-health-inventory-table__number">{formatNumber(manual?.count)}</td>
            <td className="app-health-inventory-table__total" rowSpan={2}>{formatNumber(block.total_count)}</td>
            <td>{formatTimestamp(manual?.latest_synced_at)}</td>
          </tr>
          <tr>
            <th scope="row">
              <span>{oa?.label ?? "OA 解析"}</span>
              <small className="app-health-inventory-table__annotation">仅新增入池</small>
            </th>
            <td className="app-health-inventory-table__number">{formatNumber(oa?.supplementary_count)}</td>
            <td>{formatTimestamp(oa?.latest_synced_at)}</td>
          </tr>
        </tbody>
      </table>
    </InventoryPanel>
  );
}

function OaInventory({ block }: { block: OperationsDashboardInventoryBlock }) {
  const rows = [
    inventorySource(block, "oa_records_completed"),
    inventorySource(block, "oa_records_in_progress"),
  ];

  return (
    <InventoryPanel title="OA 状态" syncedAt={block.latest_synced_at}>
      <table aria-label="OA 状态" className="app-health-inventory-table">
        <thead>
          <tr><th scope="col">状态</th><th scope="col">数量</th><th scope="col">最近同步</th></tr>
        </thead>
        <tbody>
          {rows.map((source, index) => (
            <tr key={source?.key ?? index}>
              <th scope="row">{source?.label ?? (index === 0 ? "已完成 OA" : "进行中 OA")}</th>
              <td className="app-health-inventory-table__number">{formatNumber(source?.count)}</td>
              <td>{formatTimestamp(source?.latest_synced_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </InventoryPanel>
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
        <BankInventory block={payload.data_inventory.bank} />
        <InvoiceInventory block={payload.data_inventory.invoice} />
        <OaInventory block={payload.data_inventory.oa} />
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
    <FinanceTable ariaLabel="Read Model 状态" minWidth={1160}>
      <FinanceTableHeader>
        <FinanceTableColumn columnRole="identity" isRowHeader>Read Model</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">状态</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">15m p95</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">15m p99</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">历史 p95</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">15m 样本</FinanceTableColumn>
        <FinanceTableColumn columnRole="date">最近完成</FinanceTableColumn>
        <FinanceTableColumn columnRole="description">最近 scope</FinanceTableColumn>
        <FinanceTableColumn columnRole="description">queue / handler / retry</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">stale</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">unavailable</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
          {rows.map((row) => (
            (() => {
              const state = readModelState(row);
              const evidence = latestScopeEvidence(row);
              return (
                <FinanceTableRow key={row.key} id={row.key}>
                  <FinanceTableCell columnRole="identity" textValue={row.key}>{row.key}</FinanceTableCell>
                  <FinanceTableCell columnRole="status"><FinanceStatusTag tone={state.tone}>{state.label}</FinanceStatusTag></FinanceTableCell>
                  <PercentileCells value={row.refresh_duration_ms} />
                  <PerformanceCell value={row.historical_refresh_duration_ms?.p95} kind="p95" />
                  <FinanceTableCell columnRole="quantity">{sampleLabel(row)}</FinanceTableCell>
                  <FinanceTableCell columnRole="date">{formatTimestamp(row.refresh_duration_windows?.recent_15m?.last_completed_at)}</FinanceTableCell>
                  <FinanceTableCell columnRole="description" textValue={evidence?.scope_key ?? EMPTY_VALUE}>
                    <span title={scopeEvidenceTitle(row)}>
                      {evidence
                        ? `${evidence.operation_class === "full_history_batch" ? "全量" : "当前"} ${evidence.scope_key}`
                        : EMPTY_VALUE}
                    </span>
                  </FinanceTableCell>
                  <FinanceTableCell columnRole="description">
                    {evidence
                      ? `${formatMs(evidence.queue_wait_ms)} / ${formatMs(evidence.handler_duration_ms)} / r${evidence.retry_count}`
                      : EMPTY_VALUE}
                  </FinanceTableCell>
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
  const { active, activationGeneration } = useOptionalPageActivation("app-health-operations");
  const [payload, setPayload] = useState<OperationsDashboardPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [auditPayload, setAuditPayload] = useState<AppHealthSystemAuditPayload | null>(null);
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
      setAuditPayload(null);
      setAuditError(null);
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

  const runSystemAudit = useCallback(async () => {
    if (!permissions.canAdminAccess || auditInFlightRef.current) {
      return;
    }
    const controller = new AbortController();
    auditInFlightRef.current = controller;
    setAuditLoading(true);
    try {
      const nextPayload = await fetchPageAudit<AppHealthSystemAuditPayload>("app-health-operations", controller.signal);
      setAuditPayload(nextPayload);
      if (nextPayload.page_projection) {
        setPayload(nextPayload.page_projection);
      }
      setAuditError(null);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setAuditError(error instanceof Error && error.message.trim() ? error.message : "System Audit 失败。");
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
  }, [active, activationGeneration, loadDashboard, permissions.canAdminAccess]);

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
          <AppHealthSystemAuditPanel
            error={auditError}
            isLoading={isAuditLoading}
            onRun={runSystemAudit}
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
