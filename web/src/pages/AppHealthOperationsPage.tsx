import { useEffect, useMemo, useState, type ReactNode } from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";

import { useSession, useSessionPermissions } from "../contexts/SessionContext";
import { fetchAppHealth } from "../features/appHealth/api";
import type { ApiAppHealthPayload } from "../features/appHealth/types";
import { settingsDataGridSx, settingsTokens } from "../components/settings/settingsDesign";

type OperationsPayload = ApiAppHealthPayload & Record<string, unknown>;

type GridRow = {
  id: string;
  status: string;
  type: string;
  label: string;
  updatedAt: string;
  message: string;
};

type AlertRow = {
  id: string;
  state: "active" | "recovered";
  severity: string;
  source: string;
  message: string;
  changedAt: string;
};

const EMPTY_VALUE = "—";

const sectionSx = {
  border: `1px solid ${settingsTokens.borderSubtle}`,
  borderRadius: "4px",
  bgcolor: settingsTokens.page,
  minWidth: 0,
};

const sectionHeaderSx = {
  px: 2,
  py: 1.25,
  borderBottom: `1px solid ${settingsTokens.borderSubtle}`,
};

const sectionBodySx = {
  p: 2,
  minWidth: 0,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function readString(source: Record<string, unknown>, keys: string[], fallback = EMPTY_VALUE) {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
    if (typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
  }
  return fallback;
}

function readNumber(source: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === "string" && value.trim().length > 0) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }
  return 0;
}

function readBoolean(source: Record<string, unknown>, keys: string[], fallback = false) {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "boolean") {
      return value;
    }
  }
  return fallback;
}

function readStringArray(source: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = source[key];
    if (Array.isArray(value)) {
      return value.map((item) => String(item ?? "").trim()).filter(Boolean);
    }
  }
  return [];
}

function readRecordArray(source: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = source[key];
    if (Array.isArray(value)) {
      return value.filter(isRecord);
    }
  }
  return [];
}

function statusReason(status: string) {
  if (status === "blocked") {
    return "系统阻断写操作或依赖不可用";
  }
  if (status === "busy") {
    return "后台任务、OA 同步或读模型处理中";
  }
  if (status === "ok") {
    return "系统状态正常";
  }
  return EMPTY_VALUE;
}

function statusColor(status: string): "default" | "success" | "warning" | "error" | "info" {
  if (["ok", "ready", "synced", "available", "authenticated", "completed", "success", "recovered"].includes(status)) {
    return "success";
  }
  if (["blocked", "error", "failed", "unavailable", "expired", "forbidden", "critical"].includes(status)) {
    return "error";
  }
  if (["busy", "refreshing", "rebuilding", "stale", "dirty", "queued", "running", "partial_success", "warning"].includes(status)) {
    return "warning";
  }
  return "default";
}

function Section({ title, children, testId }: { title: string; children: ReactNode; testId?: string }) {
  return (
    <Box component="section" data-testid={testId} sx={sectionSx}>
      <Box sx={sectionHeaderSx}>
        <Typography component="h2" sx={{ color: settingsTokens.textPrimary, fontSize: 16, fontWeight: 600, lineHeight: 1.3 }}>
          {title}
        </Typography>
      </Box>
      <Box sx={sectionBodySx}>{children}</Box>
    </Box>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Stack direction="row" spacing={1} sx={{ minWidth: 0, alignItems: "baseline" }}>
      <Typography sx={{ color: settingsTokens.textMuted, flex: "0 0 128px", fontSize: 12, lineHeight: 1.6 }}>
        {label}
      </Typography>
      <Box sx={{ color: settingsTokens.textPrimary, minWidth: 0, overflowWrap: "anywhere", fontSize: 14, lineHeight: 1.6 }}>
        {value}
      </Box>
    </Stack>
  );
}

function StatusChip({ value }: { value: string }) {
  return <Chip label={value || EMPTY_VALUE} size="small" color={statusColor(value)} variant="outlined" />;
}

function ChipList({ values }: { values: string[] }) {
  if (values.length === 0) {
    return <Typography component="span">{EMPTY_VALUE}</Typography>;
  }
  return (
    <Stack direction="row" spacing={0.75} useFlexGap sx={{ minWidth: 0, flexWrap: "wrap" }}>
      {values.map((value) => (
        <Chip
          key={value}
          label={value}
          size="small"
          variant="outlined"
          sx={{ maxWidth: "100%", "& .MuiChip-label": { overflow: "hidden", textOverflow: "ellipsis" } }}
        />
      ))}
    </Stack>
  );
}

function normalizeJobs(backgroundJobs: Record<string, unknown>): GridRow[] {
  return readRecordArray(backgroundJobs, ["jobs", "recent_jobs", "recentJobs", "recent"]).map((job, index) => {
    const id = readString(job, ["job_id", "jobId", "id"], `job-${index + 1}`);
    return {
      id,
      status: readString(job, ["status"]),
      type: readString(job, ["type", "job_type", "jobType"]),
      label: readString(job, ["label", "name"]),
      updatedAt: readString(job, ["updated_at", "updatedAt", "finished_at", "finishedAt", "started_at", "startedAt", "created_at", "createdAt"]),
      message: readString(job, ["message", "error", "detail", "details"]),
    };
  });
}

function normalizeAlerts(payload: OperationsPayload): AlertRow[] {
  const alerts = asRecord(payload.alerts);
  const active = readRecordArray(alerts, ["active", "active_alerts", "activeAlerts"])
    .concat(readRecordArray(payload, ["active_alerts", "activeAlerts"]));
  const recovered = readRecordArray(alerts, ["recent_recovered", "recentRecovered", "recovered"])
    .concat(readRecordArray(payload, ["recent_recovered", "recentRecovered", "recent_recovered_alerts"]));

  return [
    ...active.map((alert, index) => toAlertRow(alert, index, "active")),
    ...recovered.map((alert, index) => toAlertRow(alert, index, "recovered")),
  ];
}

function toAlertRow(alert: Record<string, unknown>, index: number, state: "active" | "recovered"): AlertRow {
  return {
    id: readString(alert, ["id", "alert_id", "alertId"], `${state}-${index + 1}`),
    state,
    severity: readString(alert, ["severity", "level", "status"]),
    source: readString(alert, ["source", "dependency", "scope"]),
    message: readString(alert, ["message", "reason", "details"]),
    changedAt: state === "active"
      ? readString(alert, ["started_at", "startedAt", "created_at", "createdAt", "last_seen_at", "lastSeenAt"])
      : readString(alert, ["recovered_at", "recoveredAt", "resolved_at", "resolvedAt", "updated_at", "updatedAt"]),
  };
}

const jobColumns: GridColDef<GridRow>[] = [
  { field: "id", headerName: "Job ID", minWidth: 128, flex: 0.9 },
  { field: "status", headerName: "Status", minWidth: 112, flex: 0.6, renderCell: (params) => <StatusChip value={String(params.value ?? "")} /> },
  { field: "type", headerName: "Type", minWidth: 144, flex: 0.9 },
  { field: "label", headerName: "Label", minWidth: 160, flex: 1 },
  { field: "updatedAt", headerName: "Updated", minWidth: 180, flex: 1 },
  { field: "message", headerName: "Message", minWidth: 180, flex: 1.2 },
];

const alertColumns: GridColDef<AlertRow>[] = [
  { field: "id", headerName: "Alert ID", minWidth: 128, flex: 0.8 },
  { field: "state", headerName: "State", minWidth: 112, flex: 0.5, renderCell: (params) => <StatusChip value={String(params.value ?? "")} /> },
  { field: "severity", headerName: "Severity", minWidth: 112, flex: 0.6, renderCell: (params) => <StatusChip value={String(params.value ?? "")} /> },
  { field: "source", headerName: "Source", minWidth: 144, flex: 0.8 },
  { field: "message", headerName: "Message", minWidth: 220, flex: 1.4 },
  { field: "changedAt", headerName: "Changed", minWidth: 180, flex: 1 },
];

function OperationsGrid({ rows, columns, ariaLabel, height }: {
  rows: GridRow[] | AlertRow[];
  columns: GridColDef[];
  ariaLabel: string;
  height: number;
}) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height, minHeight: 220, width: "100%" }}>
      <DataGrid
        aria-label={ariaLabel}
        rows={rows}
        columns={columns}
        disableColumnMenu
        disableRowSelectionOnClick
        hideFooter
        rowHeight={36}
        columnHeaderHeight={36}
        sx={{ ...settingsDataGridSx, minWidth: 0 }}
      />
    </Box>
  );
}

export default function AppHealthOperationsPage() {
  const session = useSession();
  const { canAdminAccess, accessTier } = useSessionPermissions();
  const [payload, setPayload] = useState<OperationsPayload | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!canAdminAccess) {
      setPayload(null);
      setLoadError(null);
      setIsLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setLoadError(null);

    fetchAppHealth(controller.signal)
      .then((nextPayload) => {
        setPayload(nextPayload as OperationsPayload);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setLoadError(error instanceof Error && error.message.trim() ? error.message : "AppHealth 状态加载失败。");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [canAdminAccess]);

  const normalized = useMemo(() => {
    const source = payload ?? {};
    const sessionSource = asRecord(source.session);
    const sessionUser = asRecord(sessionSource.user);
    const currentSession = session.status === "authenticated" ? session.session : null;
    const oaSync = asRecord(source.oa_sync);
    const workbench = asRecord(source.workbench_read_model);
    const backgroundJobs = asRecord(source.background_jobs);
    const dependencies = asRecord(source.dependencies);
    const status = readString(source, ["status"], "unknown");

    return {
      status,
      reason: readString(source, ["reason", "message"], statusReason(status)),
      generatedAt: readString(source, ["generated_at", "generatedAt"]),
      session: {
        status: readString(sessionSource, ["status"]),
        username: readString(sessionUser, ["username"], currentSession?.user.username ?? EMPTY_VALUE),
        displayName: readString(sessionUser, ["display_name", "displayName", "nickname"], currentSession?.user.displayName ?? EMPTY_VALUE),
        accessTier: readString(sessionSource, ["access_tier", "accessTier"], accessTier),
        canMutateData: readBoolean(sessionSource, ["can_mutate_data", "canMutateData"], false),
      },
      oaSync: {
        status: readString(oaSync, ["status"]),
        dirtyScopes: readStringArray(oaSync, ["dirty_scopes", "dirtyScopes", "changed_scopes", "changedScopes"]),
        lastSyncedAt: readString(oaSync, ["last_synced_at", "lastSyncedAt"]),
        version: readString(oaSync, ["version"]),
        message: readString(oaSync, ["message"]),
      },
      workbench: {
        status: readString(workbench, ["status"]),
        dirtyScopes: readStringArray(workbench, ["dirty_scopes", "dirtyScopes"]),
        staleScopes: readStringArray(workbench, ["stale_scopes", "staleScopes"]),
        rebuildingScopes: readStringArray(workbench, ["rebuilding_scopes", "rebuildingScopes", "rebuild_job_ids", "rebuildJobIds"]),
        lastRebuiltAt: readString(workbench, ["last_rebuilt_at", "lastRebuiltAt", "last_built_at", "lastBuiltAt", "generated_at", "generatedAt"]),
      },
      backgroundJobs: {
        active: readNumber(backgroundJobs, ["active"]),
        queued: readNumber(backgroundJobs, ["queued"]),
        running: readNumber(backgroundJobs, ["running"]),
        attention: readNumber(backgroundJobs, ["attention"]),
        rows: normalizeJobs(backgroundJobs),
      },
      dependencies,
      alertRows: normalizeAlerts(source as OperationsPayload),
    };
  }, [accessTier, payload, session]);

  const dependencyRows = useMemo(() => {
    const preferredKeys = ["oa_identity", "oa_sync", "background_jobs", "state_store"];
    const entries = Object.entries(normalized.dependencies);
    const orderedKeys = [
      ...preferredKeys.filter((key) => Object.prototype.hasOwnProperty.call(normalized.dependencies, key)),
      ...entries.map(([key]) => key).filter((key) => !preferredKeys.includes(key)),
    ];
    return orderedKeys.map((key) => {
      const dependency = asRecord(normalized.dependencies[key]);
      return {
        key,
        status: readString(dependency, ["status"]),
        message: readString(dependency, ["message", "detail", "details"]),
        meta: [
          readString(dependency, ["storage_mode", "storageMode"], ""),
          readString(dependency, ["backend"], ""),
        ].filter(Boolean).join(" / ") || EMPTY_VALUE,
      };
    });
  }, [normalized.dependencies]);

  if (!canAdminAccess) {
    return (
      <Box sx={{ p: { xs: 2, md: 3 }, bgcolor: settingsTokens.page, minHeight: "100%", minWidth: 0 }}>
        <Alert severity="warning" variant="outlined" sx={{ bgcolor: settingsTokens.page }}>
          当前账号没有管理员权限，不能查看 AppHealth 运维状态。
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", minHeight: "100%", bgcolor: settingsTokens.page, minWidth: 0 }}>
      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={1.5}
        sx={{
          px: { xs: 2, md: 3 },
          py: 2,
          borderBottom: `1px solid ${settingsTokens.borderSubtle}`,
          alignItems: { xs: "stretch", md: "center" },
          justifyContent: "space-between",
          minWidth: 0,
        }}
      >
        <Typography component="h1" sx={{ color: settingsTokens.textPrimary, fontSize: 20, fontWeight: 600, lineHeight: 1.3 }}>
          AppHealth 运维状态
        </Typography>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", minWidth: 0 }}>
          <StatusChip value={normalized.status} />
          <Chip label={normalized.generatedAt} size="small" variant="outlined" sx={{ maxWidth: "100%" }} />
        </Stack>
      </Stack>

      <Stack spacing={2} sx={{ p: { xs: 2, md: 3 }, minWidth: 0 }}>
        {isLoading ? <Alert severity="info">正在加载 AppHealth 状态。</Alert> : null}
        {loadError ? <Alert severity="error">{loadError}</Alert> : null}

        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", lg: "repeat(2, minmax(0, 1fr))" }, gap: 2, minWidth: 0 }}>
          <Section title="Summary" testId="app-health-summary">
            <Stack spacing={1}>
              <Field label="Status" value={<StatusChip value={normalized.status} />} />
              <Field label="Reason" value={normalized.reason} />
              <Field label="Generated" value={normalized.generatedAt} />
            </Stack>
          </Section>

          <Section title="Session" testId="app-health-session">
            <Stack spacing={1}>
              <Field label="Status" value={<StatusChip value={normalized.session.status} />} />
              <Field label="User" value={`${normalized.session.displayName} / ${normalized.session.username}`} />
              <Field label="Access tier" value={normalized.session.accessTier} />
              <Field label="Writable" value={normalized.session.canMutateData ? "是" : "否"} />
            </Stack>
          </Section>

          <Section title="OA Sync" testId="app-health-oa-sync">
            <Stack spacing={1}>
              <Field label="Status" value={<StatusChip value={normalized.oaSync.status} />} />
              <Field label="Dirty scopes" value={<ChipList values={normalized.oaSync.dirtyScopes} />} />
              <Field label="Last synced" value={normalized.oaSync.lastSyncedAt} />
              <Field label="Version" value={normalized.oaSync.version} />
              <Field label="Message" value={normalized.oaSync.message} />
            </Stack>
          </Section>

          <Section title="Workbench Read Model" testId="app-health-workbench">
            <Stack spacing={1}>
              <Field label="Status" value={<StatusChip value={normalized.workbench.status} />} />
              <Field label="Stale scopes" value={<ChipList values={normalized.workbench.staleScopes} />} />
              <Field label="Dirty scopes" value={<ChipList values={normalized.workbench.dirtyScopes} />} />
              <Field label="Rebuilding" value={<ChipList values={normalized.workbench.rebuildingScopes} />} />
              <Field label="Last rebuilt" value={normalized.workbench.lastRebuiltAt} />
            </Stack>
          </Section>
        </Box>

        <Section title="Background Jobs" testId="app-health-background-jobs">
          <Stack spacing={1.5} sx={{ minWidth: 0 }}>
            <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", minWidth: 0 }}>
              <Chip label={`Active ${normalized.backgroundJobs.active}`} size="small" variant="outlined" />
              <Chip label={`Queued ${normalized.backgroundJobs.queued}`} size="small" color={normalized.backgroundJobs.queued > 0 ? "warning" : "default"} variant="outlined" />
              <Chip label={`Running ${normalized.backgroundJobs.running}`} size="small" color={normalized.backgroundJobs.running > 0 ? "warning" : "default"} variant="outlined" />
              <Chip label={`Attention ${normalized.backgroundJobs.attention}`} size="small" color={normalized.backgroundJobs.attention > 0 ? "error" : "default"} variant="outlined" />
            </Stack>
            <OperationsGrid ariaLabel="最近后台任务" rows={normalized.backgroundJobs.rows} columns={jobColumns} height={300} />
          </Stack>
        </Section>

        <Section title="Dependencies" testId="app-health-dependencies">
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "repeat(2, minmax(0, 1fr))" }, gap: 1, minWidth: 0 }}>
            {dependencyRows.length === 0 ? (
              <Typography sx={{ color: settingsTokens.textSecondary, fontSize: 14 }}>{EMPTY_VALUE}</Typography>
            ) : dependencyRows.map((dependency) => (
              <Stack
                key={dependency.key}
                direction="row"
                spacing={1}
                sx={{
                  minWidth: 0,
                  alignItems: "center",
                  px: 1.25,
                  py: 1,
                  border: `1px solid ${settingsTokens.borderSubtle}`,
                  borderRadius: "4px",
                }}
              >
                <Typography sx={{ flex: "0 0 132px", minWidth: 0, overflowWrap: "anywhere", fontSize: 13 }}>
                  {dependency.key}
                </Typography>
                <StatusChip value={dependency.status} />
                <Typography sx={{ minWidth: 0, flex: 1, color: settingsTokens.textSecondary, fontSize: 13, overflowWrap: "anywhere" }}>
                  {dependency.message !== EMPTY_VALUE ? dependency.message : dependency.meta}
                </Typography>
              </Stack>
            ))}
          </Box>
        </Section>

        <Section title="Alerts" testId="app-health-alerts">
          <OperationsGrid ariaLabel="AppHealth 告警" rows={normalized.alertRows} columns={alertColumns} height={260} />
        </Section>
      </Stack>
    </Box>
  );
}
