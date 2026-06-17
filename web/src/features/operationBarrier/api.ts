import { apiRequestJson } from "../apiClient";

export type OperationBarrierTarget = {
  readModelKey: string;
  scopeKey: string;
  scopeType?: string;
};

export type OperationBarrierTargetStatus = {
  readModelKey: string;
  scopeType: string;
  scopeKey: string;
  status: "fresh" | "refreshing" | "blocked" | string;
  fresh: boolean;
  blocking: boolean;
  rawStatus: string;
  reason?: string;
  lastError?: string;
  updatedAt?: string;
  generatedAt?: string;
  workerStatus?: string;
  workerHeartbeatLagSeconds?: number;
};

export type OperationBarrierStatus = {
  status: "fresh" | "refreshing" | "blocked" | string;
  fresh: boolean;
  targets: OperationBarrierTargetStatus[];
  blockedTargets: OperationBarrierTargetStatus[];
  refreshingTargets: OperationBarrierTargetStatus[];
};

type ApiOperationBarrierTargetStatus = {
  read_model_key?: unknown;
  scope_type?: unknown;
  scope_key?: unknown;
  status?: unknown;
  fresh?: unknown;
  blocking?: unknown;
  raw_status?: unknown;
  reason?: unknown;
  last_error?: unknown;
  updated_at?: unknown;
  generated_at?: unknown;
  worker_status?: unknown;
  worker_heartbeat_lag_seconds?: unknown;
};

type ApiOperationBarrierStatus = {
  status?: unknown;
  fresh?: unknown;
  targets?: ApiOperationBarrierTargetStatus[];
  blocked_targets?: ApiOperationBarrierTargetStatus[];
  refreshing_targets?: ApiOperationBarrierTargetStatus[];
};

type WaitForOperationFreshnessOptions = {
  timeoutMs?: number;
  intervalMs?: number;
  onStatus?: (status: OperationBarrierStatus) => void;
};

const READ_MODEL_LABELS: Record<string, string> = {
  bank_detail: "银行流水",
  no_oa_bank_batch: "无 OA 银行批次",
  pending_invoice: "待处理发票",
  turnover_ledger: "往来款台账",
  workbench: "关联台",
  workbench_relation: "关联关系",
};

export class OperationBarrierBlockedError extends Error {
  payload: OperationBarrierStatus;

  constructor(message: string, payload: OperationBarrierStatus) {
    super(message);
    this.name = "OperationBarrierBlockedError";
    this.payload = payload;
  }
}

export async function fetchOperationBarrierStatus(targets: OperationBarrierTarget[]): Promise<OperationBarrierStatus> {
  const payload = await apiRequestJson<ApiOperationBarrierStatus>(
    "/api/operation-barrier/status",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        targets: targets.map((target) => ({
          read_model_key: target.readModelKey,
          scope_key: target.scopeKey,
          ...(target.scopeType ? { scope_type: target.scopeType } : {}),
        })),
      }),
    },
    { defaultErrorMessage: "操作同步状态检查失败" },
  );
  return mapOperationBarrierStatus(payload);
}

export async function waitForOperationFreshness(
  targets: OperationBarrierTarget[],
  {
    timeoutMs = 10_000,
    intervalMs = 300,
    onStatus,
  }: WaitForOperationFreshnessOptions = {},
): Promise<OperationBarrierStatus> {
  if (targets.length === 0) {
    return {
      status: "fresh",
      fresh: true,
      targets: [],
      blockedTargets: [],
      refreshingTargets: [],
    };
  }
  const startedAt = Date.now();
  let latest: OperationBarrierStatus | null = null;
  while (Date.now() - startedAt <= timeoutMs) {
    latest = await fetchOperationBarrierStatus(targets);
    onStatus?.(latest);
    if (latest.fresh || latest.status === "fresh") {
      return latest;
    }
    if (latest.status === "blocked" || latest.blockedTargets.length > 0) {
      throw new OperationBarrierBlockedError(operationBarrierMessage(latest, "操作同步被阻断"), latest);
    }
    await delay(intervalMs);
  }
  throw new OperationBarrierBlockedError(operationBarrierMessage(latest, "操作同步等待超时"), latest ?? {
    status: "refreshing",
    fresh: false,
    targets: [],
    blockedTargets: [],
    refreshingTargets: [],
  });
}

export function operationBarrierTargets(readModelKey: string, scopeKeys: string[]): OperationBarrierTarget[] {
  const normalizedScopeKeys = Array.from(new Set(
    scopeKeys
      .map((scopeKey) => scopeKey.trim())
      .filter(Boolean),
  ));
  return normalizedScopeKeys.map((scopeKey) => ({
    readModelKey,
    scopeKey,
  }));
}

export function operationBarrierTargetsFromMonths(readModelKey: string, months: string[], fallbackScopeKey = "all") {
  const scopeKeys = months.length > 0 ? months : [fallbackScopeKey];
  return operationBarrierTargets(readModelKey, scopeKeys);
}

function operationBarrierMessage(payload: OperationBarrierStatus | null, fallback: string) {
  const target = payload?.blockedTargets[0] ?? payload?.refreshingTargets[0] ?? payload?.targets.find((item) => item.blocking);
  if (!target) {
    return fallback;
  }
  const label = READ_MODEL_LABELS[target.readModelKey] ?? "相关数据";
  const scope = target.scopeKey && target.scopeKey !== "all" ? `（${target.scopeKey}）` : "";
  return `${fallback}，${label}${scope}仍在同步，请稍后刷新后重试。`;
}

function mapOperationBarrierStatus(payload: ApiOperationBarrierStatus): OperationBarrierStatus {
  return {
    status: text(payload.status, "refreshing"),
    fresh: Boolean(payload.fresh),
    targets: list(payload.targets).map(mapTargetStatus),
    blockedTargets: list(payload.blocked_targets).map(mapTargetStatus),
    refreshingTargets: list(payload.refreshing_targets).map(mapTargetStatus),
  };
}

function mapTargetStatus(payload: ApiOperationBarrierTargetStatus): OperationBarrierTargetStatus {
  return {
    readModelKey: text(payload.read_model_key),
    scopeType: text(payload.scope_type),
    scopeKey: text(payload.scope_key),
    status: text(payload.status, "refreshing"),
    fresh: Boolean(payload.fresh),
    blocking: Boolean(payload.blocking),
    rawStatus: text(payload.raw_status),
    reason: optionalText(payload.reason),
    lastError: optionalText(payload.last_error),
    updatedAt: optionalText(payload.updated_at),
    generatedAt: optionalText(payload.generated_at),
    workerStatus: optionalText(payload.worker_status),
    workerHeartbeatLagSeconds: numberOrUndefined(payload.worker_heartbeat_lag_seconds),
  };
}

function delay(ms: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function list<T>(value: T[] | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function text(value: unknown, fallback = "") {
  const normalized = typeof value === "string" ? value.trim() : "";
  return normalized || fallback;
}

function optionalText(value: unknown) {
  const normalized = text(value);
  return normalized || undefined;
}

function numberOrUndefined(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : undefined;
}
