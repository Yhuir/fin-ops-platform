import { Chip } from "@heroui/react";

export default function OaWorkflowStatusChip({ status }: { status?: string | null }) {
  const normalized = String(status ?? "").trim().toLowerCase();
  const inProgress = normalized === "in_progress" || normalized === "进行中";
  const completed = normalized === "completed" || normalized === "已完成";
  const label = inProgress ? "进行中" : completed ? "已完成" : "状态未知";
  const canonicalStatus = inProgress ? "in_progress" : completed ? "completed" : "unknown";

  return (
    <Chip
      aria-label={`OA流程状态：${label}`}
      className="oa-workflow-status-chip"
      color={inProgress ? "warning" : completed ? "success" : "default"}
      data-workflow-status={canonicalStatus}
      size="sm"
      variant="soft"
    >
      {label}
    </Chip>
  );
}
