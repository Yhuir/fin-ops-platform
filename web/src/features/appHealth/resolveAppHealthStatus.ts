import type { AppHealthJobSummary, AppHealthResolveDetails, AppHealthSources, AppHealthStatus } from "./types";

function withDetails(detail: string) {
  return detail ? [detail] : [];
}

function normalizeDetails(detail: string | AppHealthResolveDetails): AppHealthResolveDetails {
  return typeof detail === "string" ? { fallbackReason: detail } : detail;
}

function limitDetails(details: Array<string | null | undefined>) {
  return details
    .map((detail) => String(detail ?? "").trim())
    .filter(Boolean)
    .slice(0, 3);
}

function formatMonths(months: string[] | undefined) {
  return (months ?? []).map((month) => String(month).trim()).filter(Boolean).join("、");
}

function jobDisplayLabel(job: AppHealthJobSummary | null | undefined) {
  return String(job?.shortLabel || job?.label || job?.message || "").trim();
}

function isWorkbenchMatchingJob(job: AppHealthJobSummary | null | undefined) {
  const type = String(job?.type ?? "").trim();
  return type === "workbench_matching";
}

function matchingMonthsFromJob(job: AppHealthJobSummary | null | undefined) {
  const months = formatMonths(job?.affectedMonths);
  return months || jobDisplayLabel(job).replace(/^正在生成关联台候选[:：]?/, "").trim();
}

function attentionReason(details: AppHealthResolveDetails) {
  const count = details.attentionCount ?? 0;
  const job = details.primaryAttention;
  if (count > 1) {
    return `有 ${count} 个后台任务需要确认`;
  }
  if (job?.status === "failed") {
    return "有 1 个失败导入任务需要确认";
  }
  if (job?.status === "partial_success") {
    return "有 1 个部分完成任务需要确认";
  }
  return details.fallbackReason || "有后台任务需要处理";
}

export function resolveAppHealthStatus(
  sources: AppHealthSources,
  detailReason: string | AppHealthResolveDetails = "",
): AppHealthStatus {
  const detail = normalizeDetails(detailReason);
  const fallbackReason = detail.fallbackReason ?? "";
  const detailList = limitDetails(detail.details ?? withDetails(fallbackReason));
  const matchingRunningMonths = formatMonths(detail.matchingRunningMonths);
  const matchingDirtyMonths = formatMonths(detail.matchingDirtyMonths);

  if (sources.session === "expired") {
    return { level: "blocked", reason: "登录已失效", details: detailList, blocksMutations: true, sources };
  }
  if (sources.session === "forbidden") {
    return { level: "blocked", reason: "当前账号不可用", details: detailList, blocksMutations: true, sources };
  }
  if (sources.session === "error") {
    return { level: "blocked", reason: "会话校验失败", details: detailList, blocksMutations: true, sources };
  }
  if (sources.backgroundJobs === "unreachable") {
    return { level: "blocked", reason: "系统连接异常", details: detailList, blocksMutations: true, sources };
  }
  if (sources.workbench === "error") {
    return { level: "blocked", reason: detail.matchingError || fallbackReason || "关联台数据异常", details: [], blocksMutations: true, sources };
  }

  if (sources.session === "loading") {
    return { level: "busy", reason: "正在校验登录状态", details: detailList, blocksMutations: false, sources };
  }
  if (sources.backgroundJobs === "running") {
    if (isWorkbenchMatchingJob(detail.primaryRunning)) {
      const months = matchingMonthsFromJob(detail.primaryRunning);
      return {
        level: "busy",
        reason: months ? `正在生成关联台候选：${months}` : "正在生成关联台候选",
        details: detailList,
        blocksMutations: false,
        sources,
      };
    }
    const label = jobDisplayLabel(detail.primaryRunning);
    return {
      level: "busy",
      reason: label ? `正在执行后台任务：${label}` : "后台任务处理中",
      details: detailList,
      blocksMutations: false,
      sources,
    };
  }
  if (sources.backgroundJobs === "attention") {
    return { level: "busy", reason: attentionReason(detail), details: [], blocksMutations: false, sources };
  }
  if (sources.importProgress === "running") {
    return { level: "busy", reason: "导入处理中", details: detailList, blocksMutations: false, sources };
  }
  if (matchingRunningMonths) {
    return { level: "busy", reason: `正在生成关联台候选：${matchingRunningMonths}`, details: detailList, blocksMutations: false, sources };
  }
  if (sources.oaSync === "refreshing") {
    return { level: "busy", reason: "OA 正在同步", details: detailList, blocksMutations: false, sources };
  }
  if (sources.oaSync === "dirty") {
    return { level: "busy", reason: matchingDirtyMonths ? `关联台待刷新：${matchingDirtyMonths}` : "关联台待刷新", details: detailList, blocksMutations: false, sources };
  }
  if (sources.workbench === "loading") {
    return { level: "busy", reason: "正在加载关联台", details: detailList, blocksMutations: false, sources };
  }
  if (sources.workbench === "stale") {
    return { level: "busy", reason: matchingDirtyMonths ? `关联台待刷新：${matchingDirtyMonths}` : "关联台待刷新", details: detailList, blocksMutations: false, sources };
  }
  if (sources.importProgress === "error" || sources.oaSync === "error") {
    return { level: "busy", reason: fallbackReason || "有后台任务需要处理", details: [], blocksMutations: false, sources };
  }

  return { level: "ok", reason: "系统状态正常", details: [], blocksMutations: false, sources };
}
