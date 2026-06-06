import { useCallback, useEffect, useRef, useState } from "react";

import RefreshIcon from "@mui/icons-material/Refresh";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import {
  FinanceStatusTag,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../components/common/FinanceTable";
import { settingsTokens } from "../components/settings/settingsDesign";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSession, useSessionPermissions } from "../contexts/SessionContext";
import { fetchAppHealthDashboard } from "../features/appHealth/api";
import type {
  OperationsDashboardEndpointPerformance,
  OperationsDashboardInventoryBlock,
  OperationsDashboardPayload,
  OperationsDashboardPercentiles,
  OperationsDashboardReadModelMetric,
} from "../features/appHealth/types";

const EMPTY_VALUE = "--";
const REFRESH_INTERVAL_MS = 10_000;

const sectionSx = {
  border: `1px solid ${settingsTokens.borderSubtle}`,
  borderRadius: "8px",
  bgcolor: "#fff",
  boxShadow: "0 1px 2px rgba(15, 23, 42, 0.04)",
  minWidth: 0,
};

function Section({ title, children, testId }: { title: string; children: React.ReactNode; testId: string }) {
  return (
    <Box component="section" data-testid={testId} sx={sectionSx}>
      <Box sx={{ borderBottom: `1px solid ${settingsTokens.borderSubtle}`, px: 2, py: 1.25 }}>
        <Typography component="h2" sx={{ color: settingsTokens.textPrimary, fontSize: 16, fontWeight: 650, lineHeight: 1.3 }}>
          {title}
        </Typography>
      </Box>
      <Box sx={{ p: { xs: 1.25, md: 1.5 } }}>{children}</Box>
    </Box>
  );
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return EMPTY_VALUE;
  }
  return new Intl.NumberFormat("zh-CN").format(value);
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

function InventorySummary({ title, block }: { title: string; block: OperationsDashboardInventoryBlock }) {
  return (
    <Box sx={{ border: `1px solid ${settingsTokens.borderSubtle}`, borderRadius: "8px", minWidth: 0, p: 1.5 }}>
      <Typography sx={{ color: settingsTokens.textMuted, fontSize: 12, fontWeight: 600 }}>{title}</Typography>
      <Typography sx={{ color: settingsTokens.textPrimary, fontSize: 28, fontWeight: 700, lineHeight: 1.2, mt: 0.5 }}>
        {formatNumber(block.total_count)}
      </Typography>
      <Typography sx={{ color: settingsTokens.textMuted, fontSize: 12, mt: 0.5 }}>{formatTimestamp(block.latest_synced_at)}</Typography>
    </Box>
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
              <FinanceTableCell columnRole="identity" textValue={source.label}>{source.label}</FinanceTableCell>
              <FinanceTableCell columnRole="quantity">{formatNumber(source.count)}</FinanceTableCell>
              <FinanceTableCell columnRole="date">{formatTimestamp(source.latest_synced_at)}</FinanceTableCell>
            </FinanceTableRow>
          ))}
      </FinanceTableBody>
    </FinanceTable>
  );
}

function DataInventory({ payload }: { payload: OperationsDashboardPayload }) {
  return (
    <Section title="数据" testId="app-health-data">
      <Box
        sx={{
          display: "grid",
          gap: 1.25,
          gridTemplateColumns: { xs: "1fr", md: "repeat(3, minmax(0, 1fr))" },
        }}
      >
        <InventorySummary title="流水" block={payload.data_inventory.bank} />
        <InventorySummary title="发票" block={payload.data_inventory.invoice} />
        <InventorySummary title="OA" block={payload.data_inventory.oa} />
      </Box>
      <Box
        sx={{
          display: "grid",
          gap: 1.25,
          gridTemplateColumns: { xs: "1fr", lg: "repeat(3, minmax(0, 1fr))" },
          mt: 1.25,
        }}
      >
        <InventorySourceRows title="银行流水" block={payload.data_inventory.bank} />
        <InventorySourceRows title="发票" block={payload.data_inventory.invoice} />
        <InventorySourceRows title="OA" block={payload.data_inventory.oa} />
      </Box>
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
    <FinanceTable ariaLabel="Read Model 刷新" minWidth={720}>
      <FinanceTableHeader>
        <FinanceTableColumn columnRole="identity" isRowHeader>Read Model</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">15m p95</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">15m p99</FinanceTableColumn>
        <FinanceTableColumn columnRole="status">历史 p95</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">15m 样本</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">stale</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">unavailable</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
          {rows.map((row) => (
            <FinanceTableRow key={row.key} id={row.key}>
              <FinanceTableCell columnRole="identity" textValue={row.key}>{row.key}</FinanceTableCell>
              <PercentileCells value={row.refresh_duration_ms} />
              <PerformanceCell value={row.historical_refresh_duration_ms?.p95} kind="p95" />
              <FinanceTableCell columnRole="quantity">{sampleLabel(row)}</FinanceTableCell>
              <FinanceTableCell columnRole="quantity">{formatNumber(row.stale_count)}</FinanceTableCell>
              <FinanceTableCell columnRole="quantity">{formatNumber(row.unavailable_count)}</FinanceTableCell>
            </FinanceTableRow>
          ))}
      </FinanceTableBody>
    </FinanceTable>
  );
}

function WorkerTable({ payload }: { payload: OperationsDashboardPayload }) {
  return (
    <FinanceTable ariaLabel="Worker 心跳" minWidth={300}>
      <FinanceTableHeader>
        <FinanceTableColumn columnRole="identity" isRowHeader>Worker</FinanceTableColumn>
        <FinanceTableColumn columnRole="quantity">lag</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
          {payload.runtime_performance.workers.length === 0 ? (
            <FinanceTableRow id="empty-worker">
              <FinanceTableCell columnRole="identity">{EMPTY_VALUE}</FinanceTableCell>
              <FinanceTableCell columnRole="quantity">{EMPTY_VALUE}</FinanceTableCell>
            </FinanceTableRow>
          ) : (
            payload.runtime_performance.workers.map((row) => (
              <FinanceTableRow key={row.worker_kind} id={row.worker_kind}>
                <FinanceTableCell columnRole="identity" textValue={row.worker_kind}>{row.worker_kind}</FinanceTableCell>
                <FinanceTableCell columnRole="quantity">{formatSeconds(row.heartbeat_lag_seconds)}</FinanceTableCell>
              </FinanceTableRow>
            ))
          )}
      </FinanceTableBody>
    </FinanceTable>
  );
}

function RuntimePerformance({ payload }: { payload: OperationsDashboardPayload }) {
  return (
    <Section title="后台" testId="app-health-runtime">
      <Box sx={{ display: "grid", gap: 1.25, gridTemplateColumns: { xs: "1fr", xl: "0.8fr 1.2fr" } }}>
        <OutboxTable payload={payload} />
        <QueueTable payload={payload} />
      </Box>
      <Box sx={{ display: "grid", gap: 1.25, gridTemplateColumns: { xs: "1fr", lg: "1.4fr 0.6fr" }, mt: 1.25 }}>
        <ReadModelTable rows={payload.runtime_performance.read_models} />
        <WorkerTable payload={payload} />
      </Box>
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
  const inFlightRef = useRef<AbortController | null>(null);

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
    };
  }, [active, loadDashboard, permissions.canAdminAccess]);

  if (session.status === "loading") {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="info">正在加载。</Alert>
      </Box>
    );
  }

  if (!permissions.canAdminAccess) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">当前账号没有管理员权限，不能查看 AppHealth 运维状态。</Alert>
      </Box>
    );
  }

  return (
    <Stack spacing={2} sx={{ bgcolor: settingsTokens.layer01, minHeight: "100%", p: { xs: 2, md: 3 } }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", justifyContent: "space-between", minWidth: 0 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography component="h1" sx={{ color: settingsTokens.textPrimary, fontSize: { xs: 24, md: 28 }, fontWeight: 750, lineHeight: 1.2 }}>
            AppHealth 运维状态
          </Typography>
          <Typography sx={{ color: settingsTokens.textMuted, fontSize: 12, mt: 0.5 }}>
            {payload ? formatTimestamp(payload.generated_at) : EMPTY_VALUE}
          </Typography>
        </Box>
        <Tooltip title="刷新">
          <span>
            <IconButton
              aria-label="刷新"
              disabled={isLoading}
              onClick={() => {
                void loadDashboard();
              }}
              size="small"
              sx={{
                border: `1px solid ${settingsTokens.borderSubtle}`,
                bgcolor: "#fff",
                borderRadius: "8px",
              }}
            >
              {isLoading ? <CircularProgress size={18} /> : <RefreshIcon fontSize="small" />}
            </IconButton>
          </span>
        </Tooltip>
      </Stack>

      {loadError ? <Alert severity="error">{loadError}</Alert> : null}

      {payload ? (
        <>
          <DataInventory payload={payload} />
          <RequestPerformance rows={payload.request_performance.endpoints} />
          <RuntimePerformance payload={payload} />
        </>
      ) : !loadError ? (
        <Alert severity="info">正在加载。</Alert>
      ) : null}
    </Stack>
  );
}
