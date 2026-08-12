export type WorkbenchWriteGateReason =
  | "read_only"
  | "system_unavailable"
  | "direct_read_unavailable"
  | "oa_status_unavailable"
  | "oa_syncing";

export type WorkbenchWriteGate = {
  allowed: boolean;
  reason: WorkbenchWriteGateReason | null;
  message: string | null;
};

type WorkbenchWriteGateInput = {
  canMutateData: boolean;
  mutationsBlocked: boolean;
  directReadAvailable: boolean;
  oaSyncReachable: boolean;
  oaSyncStatus: string | null;
  oaDirtyScopes: readonly string[];
};

export function resolveWorkbenchWriteGate({
  canMutateData,
  mutationsBlocked,
  directReadAvailable,
  oaSyncReachable,
  oaSyncStatus,
  oaDirtyScopes,
}: WorkbenchWriteGateInput): WorkbenchWriteGate {
  if (!canMutateData) {
    return {
      allowed: false,
      reason: "read_only",
      message: "当前账号仅支持查看和导出，不能执行写操作。",
    };
  }
  if (mutationsBlocked) {
    return {
      allowed: false,
      reason: "system_unavailable",
      message: "登录已失效或系统不可用，请返回 OA 系统重新进入。",
    };
  }
  if (!directReadAvailable) {
    return {
      allowed: false,
      reason: "direct_read_unavailable",
      message: "关联台读取失败，请重新读取成功后再执行关联操作。",
    };
  }
  if (!oaSyncReachable) {
    return {
      allowed: false,
      reason: "oa_status_unavailable",
      message: "OA 同步状态读取失败，请重试；恢复后将自动开放关联操作。",
    };
  }
  const normalizedOaSyncStatus = oaSyncStatus?.trim().toLowerCase() ?? "";
  if (normalizedOaSyncStatus !== "synced" || oaDirtyScopes.length > 0) {
    const statusUnavailable = !normalizedOaSyncStatus
      || normalizedOaSyncStatus === "unknown"
      || normalizedOaSyncStatus === "error";
    return {
      allowed: false,
      reason: "oa_syncing",
      message: statusUnavailable
        ? "OA 同步状态尚未就绪，恢复后将自动开放关联操作。"
        : "OA 正在同步，完成后将自动恢复关联操作。",
    };
  }
  return { allowed: true, reason: null, message: null };
}
