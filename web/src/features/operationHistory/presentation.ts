import type { OperationHistoryOperation } from "./api";

export const operationCategories = [
  { key: "all", label: "全部" },
  { key: "oa", label: "OA 申请与凭据" },
  { key: "settings", label: "App 设置" },
  { key: "business", label: "业务处理" },
  { key: "transfer", label: "导入与导出" },
  { key: "system", label: "系统任务" },
  { key: "unclassified", label: "未分类" },
] as const;

export const operationOutcomes = [
  { key: "success", label: "成功", color: "success" },
  { key: "failed", label: "失败", color: "danger" },
  { key: "pending", label: "进行中", color: "warning" },
  { key: "incomplete", label: "执行未完成", color: "warning" },
  { key: "unknown", label: "结果未记录", color: "default" },
] as const;

export function outcomeView(outcome: string) {
  const result = operationOutcomes.find(item => item.key === outcome);
  if (!result) throw new Error(`未登记的操作结果：${outcome}`);
  return result;
}

export function actorLabel(actor: Pick<OperationHistoryOperation, "actor_id" | "actor_name" | "actor_account">) {
  const actorId = String(actor.actor_id ?? "");
  if (!actorId || actorId === "system" || actorId === "database" || actorId.includes("-persistence") || actorId.includes("-repair")) return "系统";
  const name = String(actor.actor_name || "").trim();
  const account = String(actor.actor_account || "").trim();
  return name && account ? `${name} · ${account}` : name || account || actorId;
}

export function operationDateRange(days: number, now = new Date()) {
  const today = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  const from = new Date(`${today}T00:00:00Z`);
  from.setUTCDate(from.getUTCDate() - days + 1);
  return { dateFrom: from.toISOString().slice(0, 10), dateTo: today };
}
