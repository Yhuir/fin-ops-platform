import { useCallback, useEffect, useRef, useState } from "react";

import RefreshIcon from "@mui/icons-material/Refresh";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { settingsTokens } from "../components/settings/settingsDesign";
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

const tableSx = {
  "& th": {
    borderColor: settingsTokens.borderSubtle,
    color: settingsTokens.textMuted,
    fontSize: 12,
    fontWeight: 600,
    py: 1,
    whiteSpace: "nowrap",
  },
  "& td": {
    borderColor: settingsTokens.borderSubtle,
    color: settingsTokens.textPrimary,
    fontSize: 13,
    py: 1.1,
    verticalAlign: "top",
  },
  "& tr:last-child td": {
    borderBottom: 0,
  },
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

function metricToneSx(tone: MetricTone) {
  if (tone === "green") {
    return { bgcolor: "#ecfdf3", color: "#067647", borderColor: "#abefc6" };
  }
  if (tone === "yellow") {
    return { bgcolor: "#fffaeb", color: "#b54708", borderColor: "#fedf89" };
  }
  if (tone === "red") {
    return { bgcolor: "#fef3f2", color: "#b42318", borderColor: "#fecdca" };
  }
  return { bgcolor: "#f8fafc", color: settingsTokens.textMuted, borderColor: settingsTokens.borderSubtle };
}

function PerformanceCell({ value, kind }: { value: number | null | undefined; kind: "p95" | "p99" }) {
  const tone = metricTone(value, kind);
  const toneSx = metricToneSx(tone);
  return (
    <TableCell data-tone={tone} sx={{ minWidth: 92 }}>
      <Box
        component="span"
        sx={{
          ...toneSx,
          border: "1px solid",
          borderRadius: "6px",
          display: "inline-flex",
          fontSize: 12,
          fontWeight: 700,
          justifyContent: "center",
          lineHeight: 1.4,
          minWidth: 72,
          px: 0.75,
          py: 0.25,
        }}
      >
        {formatMs(value)}
      </Box>
    </TableCell>
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

function InventorySourceRows({ block }: { block: OperationsDashboardInventoryBlock }) {
  return (
    <TableContainer>
      <Table size="small" sx={tableSx}>
        <TableHead>
          <TableRow>
            <TableCell>来源</TableCell>
            <TableCell align="right">数量</TableCell>
            <TableCell>同步</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {block.sources.map((source) => (
            <TableRow key={source.key}>
              <TableCell>{source.label}</TableCell>
              <TableCell align="right">{formatNumber(source.count)}</TableCell>
              <TableCell>{formatTimestamp(source.latest_synced_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
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
        <InventorySourceRows block={payload.data_inventory.bank} />
        <InventorySourceRows block={payload.data_inventory.invoice} />
        <InventorySourceRows block={payload.data_inventory.oa} />
      </Box>
    </Section>
  );
}

function RequestPerformance({ rows }: { rows: OperationsDashboardEndpointPerformance[] }) {
  return (
    <Section title="请求" testId="app-health-requests">
      <TableContainer>
        <Table size="small" sx={tableSx}>
          <TableHead>
            <TableRow>
              <TableCell>接口</TableCell>
              <TableCell align="right">样本</TableCell>
              <TableCell>API p95</TableCell>
              <TableCell>API p99</TableCell>
              <TableCell>DB p95</TableCell>
              <TableCell>DB p99</TableCell>
              <TableCell>SQL p95</TableCell>
              <TableCell>连接 p95</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.endpoint}>
                <TableCell sx={{ maxWidth: 260, overflowWrap: "anywhere" }}>{row.endpoint}</TableCell>
                <TableCell align="right">{formatNumber(row.sample_count)}</TableCell>
                <PercentileCells value={row.duration_ms} />
                <PercentileCells value={row.database_duration_ms} />
                <PerformanceCell value={row.sql_execute_fetch_ms.p95} kind="p95" />
                <PerformanceCell value={row.connection_acquire_ms.p95} kind="p95" />
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
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
    <TableContainer>
      <Table size="small" sx={tableSx}>
        <TableHead>
          <TableRow>
            <TableCell>Outbox</TableCell>
            <TableCell align="right">值</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map(([label, value]) => (
            <TableRow key={label}>
              <TableCell>{label}</TableCell>
              <TableCell align="right">{label === "oldest_pending" ? formatSeconds(value) : formatNumber(value)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function QueueTable({ payload }: { payload: OperationsDashboardPayload }) {
  return (
    <TableContainer>
      <Table size="small" sx={tableSx}>
        <TableHead>
          <TableRow>
            <TableCell>RabbitMQ</TableCell>
            <TableCell>queue</TableCell>
            <TableCell align="right">ready</TableCell>
            <TableCell align="right">unacked</TableCell>
            <TableCell align="right">consumer</TableCell>
            <TableCell align="right">DLQ</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {payload.runtime_performance.queues.map((row) => (
            <TableRow key={`${row.event_type}:${row.queue}`}>
              <TableCell>{row.event_type}</TableCell>
              <TableCell sx={{ maxWidth: 240, overflowWrap: "anywhere" }}>{row.queue}</TableCell>
              <TableCell align="right">{formatNumber(row.messages)}</TableCell>
              <TableCell align="right">{formatNumber(row.unacked)}</TableCell>
              <TableCell align="right">{formatNumber(row.consumers)}</TableCell>
              <TableCell align="right">{formatNumber(row.dlq_messages)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function ReadModelTable({ rows }: { rows: OperationsDashboardReadModelMetric[] }) {
  return (
    <TableContainer>
      <Table size="small" sx={tableSx}>
        <TableHead>
          <TableRow>
            <TableCell>Read Model</TableCell>
            <TableCell>p95</TableCell>
            <TableCell>p99</TableCell>
            <TableCell align="right">stale</TableCell>
            <TableCell align="right">unavailable</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.key}>
              <TableCell>{row.key}</TableCell>
              <PercentileCells value={row.refresh_duration_ms} />
              <TableCell align="right">{formatNumber(row.stale_count)}</TableCell>
              <TableCell align="right">{formatNumber(row.unavailable_count)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function WorkerTable({ payload }: { payload: OperationsDashboardPayload }) {
  return (
    <TableContainer>
      <Table size="small" sx={tableSx}>
        <TableHead>
          <TableRow>
            <TableCell>Worker</TableCell>
            <TableCell align="right">lag</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {payload.runtime_performance.workers.length === 0 ? (
            <TableRow>
              <TableCell>{EMPTY_VALUE}</TableCell>
              <TableCell align="right">{EMPTY_VALUE}</TableCell>
            </TableRow>
          ) : (
            payload.runtime_performance.workers.map((row) => (
              <TableRow key={row.worker_kind}>
                <TableCell>{row.worker_kind}</TableCell>
                <TableCell align="right">{formatSeconds(row.heartbeat_lag_seconds)}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </TableContainer>
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
    if (!permissions.canAdminAccess) {
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
  }, [loadDashboard, permissions.canAdminAccess]);

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
