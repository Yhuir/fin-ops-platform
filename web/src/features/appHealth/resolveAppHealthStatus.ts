import type { AppHealthSources, AppHealthStatus } from "./types";

function withDetails(detail: string) {
  return detail ? [detail] : [];
}

export function resolveAppHealthStatus(
  sources: AppHealthSources,
  detailReason = "",
): AppHealthStatus {
  if (sources.session === "expired") {
    return { level: "blocked", reason: "登录已失效", details: withDetails(detailReason), blocksMutations: true, sources };
  }
  if (sources.session === "forbidden") {
    return { level: "blocked", reason: "当前账号不可用", details: withDetails(detailReason), blocksMutations: true, sources };
  }
  if (sources.session === "error") {
    return { level: "blocked", reason: "会话校验失败", details: withDetails(detailReason), blocksMutations: true, sources };
  }
  if (sources.backgroundJobs === "unreachable") {
    return { level: "blocked", reason: "系统连接异常", details: withDetails(detailReason), blocksMutations: true, sources };
  }
  if (sources.workbench === "error") {
    return { level: "blocked", reason: detailReason || "关联台数据异常", details: [], blocksMutations: true, sources };
  }

  if (sources.session === "loading") {
    return { level: "busy", reason: "正在校验登录状态", details: withDetails(detailReason), blocksMutations: false, sources };
  }
  if (sources.backgroundJobs === "running") {
    return { level: "busy", reason: "后台任务处理中", details: withDetails(detailReason), blocksMutations: false, sources };
  }
  if (sources.importProgress === "running") {
    return { level: "busy", reason: "导入处理中", details: withDetails(detailReason), blocksMutations: false, sources };
  }
  if (sources.oaSync === "refreshing") {
    return { level: "busy", reason: "OA 正在同步", details: withDetails(detailReason), blocksMutations: false, sources };
  }
  if (sources.oaSync === "dirty") {
    return { level: "busy", reason: "关联台待刷新", details: withDetails(detailReason), blocksMutations: false, sources };
  }
  if (sources.workbench === "loading") {
    return { level: "busy", reason: "正在加载关联台", details: withDetails(detailReason), blocksMutations: false, sources };
  }
  if (sources.workbench === "stale") {
    return { level: "busy", reason: "关联台待刷新", details: withDetails(detailReason), blocksMutations: false, sources };
  }
  if (sources.backgroundJobs === "attention" || sources.importProgress === "error" || sources.oaSync === "error") {
    return { level: "busy", reason: detailReason || "有后台任务需要处理", details: [], blocksMutations: false, sources };
  }

  return { level: "ok", reason: detailReason || "系统状态正常", details: [], blocksMutations: false, sources };
}
