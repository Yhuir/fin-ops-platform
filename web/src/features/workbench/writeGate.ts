export type WorkbenchWriteGateReason =
  | "read_only"
  | "system_unavailable"
  | "oa_syncing";

export type WorkbenchWriteGate = {
  allowed: boolean;
  reason: WorkbenchWriteGateReason | null;
  message: string | null;
};

type WorkbenchWriteGateInput = {
  canMutateData: boolean;
  mutationsBlocked: boolean;
  oaSyncWriteBlocked: boolean;
};

export function resolveWorkbenchWriteGate({
  canMutateData,
  mutationsBlocked,
  oaSyncWriteBlocked,
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
  return { allowed: true, reason: null, message: null };
}
