export type WorkbenchWriteGateReason =
  | "read_only"
  | "system_unavailable"
  | "oa_syncing"
  | "read_model_not_fresh"
  | "read_model_version_missing";

export type WorkbenchWriteGate = {
  allowed: boolean;
  reason: WorkbenchWriteGateReason | null;
  message: string | null;
};

type WorkbenchWriteGateInput = {
  canMutateData: boolean;
  mutationsBlocked: boolean;
  oaSyncWriteBlocked: boolean;
  readModelStatus: string;
  readModelVersion: string | null;
};

export function resolveWorkbenchWriteGate({
  canMutateData,
  mutationsBlocked,
  oaSyncWriteBlocked,
  readModelStatus,
  readModelVersion,
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
  if (oaSyncWriteBlocked) {
    return {
      allowed: false,
      reason: "oa_syncing",
      message: "OA 正在同步，完成后将自动恢复关联操作。",
    };
  }
  if (readModelStatus !== "fresh") {
    return {
      allowed: false,
      reason: "read_model_not_fresh",
      message: readModelStatus === "failed"
        ? "关联台刷新失败，当前写操作已禁用。"
        : readModelStatus === "unavailable"
          ? "关联台读模型不可用，当前写操作已禁用。"
          : readModelStatus === "stale"
            ? "关联台数据已过期，刷新完成后将自动恢复写操作。"
            : "关联台正在刷新，完成后将自动恢复写操作。",
    };
  }
  if (!readModelVersion) {
    return {
      allowed: false,
      reason: "read_model_version_missing",
      message: "关联台最新数据尚未就绪，刷新完成后将自动恢复写操作。",
    };
  }
  return { allowed: true, reason: null, message: null };
}
