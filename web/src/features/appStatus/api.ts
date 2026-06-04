import type { AppStatusColor, AppStatusDomain, AppStatusLevel, AppStatusOverview, AppStatusTask } from "./types";

type RawRecord = Record<string, unknown>;

const DOMAIN_STATUSES = new Set([
  "ready",
  "loading",
  "refreshing",
  "stale",
  "failed",
  "unavailable",
  "missing",
  "schema_mismatch",
  "source_mismatch",
]);

const TASK_STATUSES = new Set([
  "queued",
  "running",
  "succeeded",
  "partial_success",
  "failed",
  "cancelled",
  "acknowledged",
  "superseded",
]);

function record(value: unknown): RawRecord {
  return value && typeof value === "object" ? value as RawRecord : {};
}

function stringValue(value: unknown, fallback = "") {
  const text = typeof value === "string" ? value.trim() : "";
  return text || fallback;
}

function numberValue(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function nullablePercent(value: unknown) {
  if (value === null || value === undefined) {
    return null;
  }
  return Math.max(0, Math.min(100, numberValue(value, 0)));
}

function stringList(value: unknown) {
  return Array.isArray(value)
    ? value.map((item) => String(item ?? "").trim()).filter(Boolean)
    : [];
}

function appStatusLevel(value: unknown): AppStatusLevel | null {
  const text = stringValue(value);
  if (text === "blocked" || text === "busy" || text === "ok") {
    return text;
  }
  return null;
}

function appStatusColor(value: unknown): AppStatusColor | null {
  const text = stringValue(value);
  if (text === "red" || text === "yellow" || text === "green") {
    return text;
  }
  return null;
}

function appStatusDomainStatus(value: unknown): string | null {
  const text = stringValue(value);
  return DOMAIN_STATUSES.has(text) ? text : null;
}

function appStatusTaskStatus(value: unknown): string | null {
  const text = stringValue(value);
  return TASK_STATUSES.has(text) ? text : null;
}

function mapDomain(rawValue: unknown): AppStatusDomain | null {
  const raw = record(rawValue);
  const key = stringValue(raw.key);
  const level = appStatusLevel(raw.level);
  const status = appStatusDomainStatus(raw.status);
  const reason = stringValue(raw.reason);
  if (!key || !level || !status || !reason) {
    return null;
  }
  return {
    key,
    label: stringValue(raw.label, "状态域"),
    route: stringValue(raw.route, "/operations/app-health"),
    level,
    status,
    reason,
    details: stringList(raw.details),
    readModels: stringList(raw.read_models ?? raw.readModels),
    workers: stringList(raw.workers),
    jobIds: stringList(raw.job_ids ?? raw.jobIds),
    updatedAt: stringValue(raw.updated_at ?? raw.updatedAt),
  };
}

function mapTask(rawValue: unknown): AppStatusTask | null {
  const raw = record(rawValue);
  const jobId = stringValue(raw.job_id ?? raw.jobId);
  const status = appStatusTaskStatus(raw.status);
  if (!jobId || !status) {
    return null;
  }
  return {
    jobId,
    type: stringValue(raw.type),
    status,
    label: stringValue(raw.label, "后台任务"),
    shortLabel: stringValue(raw.short_label ?? raw.shortLabel ?? raw.message ?? raw.label, "后台任务处理中"),
    message: stringValue(raw.message),
    phase: stringValue(raw.phase),
    current: numberValue(raw.current),
    total: numberValue(raw.total),
    percent: nullablePercent(raw.percent),
    affectedDomains: stringList(raw.affected_domains ?? raw.affectedDomains),
    affectedScopes: stringList(raw.affected_scopes ?? raw.affectedScopes),
    affectedMonths: stringList(raw.affected_months ?? raw.affectedMonths),
    route: stringValue(raw.route, "/operations/app-health"),
    attention: raw.attention === true,
    updatedAt: stringValue(raw.updated_at ?? raw.updatedAt),
  };
}

export function mapAppStatusOverview(value: unknown): AppStatusOverview | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const raw = value as RawRecord;
  const overall = record(raw.overall);
  const overallLevel = appStatusLevel(overall.level);
  const overallColor = appStatusColor(overall.color);
  const overallReason = stringValue(overall.reason);
  if (!overallLevel || !overallColor || !overallReason) {
    return null;
  }
  const domains = Array.isArray(raw.domains) ? raw.domains.map(mapDomain) : [];
  if (domains.some((domain) => domain === null)) {
    return null;
  }
  const backgroundTasks = Array.isArray(raw.background_tasks)
    ? raw.background_tasks.map(mapTask)
    : [];
  if (backgroundTasks.some((task) => task === null)) {
    return null;
  }
  return {
    version: numberValue(raw.version, 1),
    generatedAt: stringValue(raw.generated_at ?? raw.generatedAt),
    overall: {
      level: overallLevel,
      color: overallColor,
      reason: overallReason,
      blocksMutations: overall.blocks_mutations === true || overall.blocksMutations === true,
    },
    domains: domains as AppStatusDomain[],
    backgroundTasks: backgroundTasks as AppStatusTask[],
    alerts: Array.isArray(raw.alerts)
      ? raw.alerts.filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
      : [],
  };
}
