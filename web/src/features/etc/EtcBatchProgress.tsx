import type {
  EtcBusinessBatchDetail,
  EtcBusinessBatchStatus,
  EtcBusinessBatchSummary,
  EtcReconciliationTask,
} from "./types";

type EtcBatchProgressState = "complete" | "current" | "pending" | "processing" | "manual" | "problem";

export type EtcBatchProgressStep = {
  id: "sources" | "reconciliation" | "import" | "oa";
  label: string;
  description: string;
  state: EtcBatchProgressState;
};

type EtcBatchProgressProps = {
  batch: EtcBusinessBatchSummary | EtcBusinessBatchDetail | null;
  task: EtcReconciliationTask | null;
  taskLoading?: boolean;
  taskError?: string | null;
};

const stepDefinitions: Array<Pick<EtcBatchProgressStep, "id" | "label" | "description">> = [
  { id: "sources", label: "准备核对资料", description: "上传账单与票根" },
  { id: "reconciliation", label: "确认核对结果", description: "处理差异并确认" },
  { id: "import", label: "导入 ETC 发票", description: "使用已确认的核对任务" },
  { id: "oa", label: "提交 OA 审批", description: "创建草稿并确认结果" },
];

const submittedStatuses = new Set<EtcBusinessBatchStatus>([
  "oa_submitted",
  "manually_marked_submitted",
  "closed",
]);

const problemStatuses = new Set<EtcBusinessBatchStatus>([
  "migration_conflict",
  "business_batch_invariant_broken",
  "superseded",
  "deleted",
]);

function initialSteps(): EtcBatchProgressStep[] {
  return stepDefinitions.map((step) => ({ ...step, state: "pending" }));
}

function completeThrough(steps: EtcBatchProgressStep[], index: number) {
  for (let current = 0; current <= index; current += 1) {
    steps[current].state = "complete";
  }
}

function setCurrent(
  steps: EtcBatchProgressStep[],
  index: number,
  state: Extract<EtcBatchProgressState, "current" | "processing" | "manual" | "problem">,
  description: string,
) {
  steps[index].state = state;
  steps[index].description = description;
}

export function deriveEtcBatchProgress(
  batch: EtcBusinessBatchSummary | EtcBusinessBatchDetail,
  task: EtcReconciliationTask | null,
  options: { taskLoading?: boolean; taskError?: string | null } = {},
) {
  const steps = initialSteps();

  if (options.taskLoading && !task) {
    setCurrent(steps, 0, "processing", "正在读取批次流程");
  } else if (task) {
    switch (task.status) {
      case "draft":
        setCurrent(steps, 0, "current", "等待上传并解析账单与票根");
        break;
      case "reviewing":
        completeThrough(steps, 0);
        setCurrent(steps, 1, "current", "处理差异并确认核对结果");
        break;
      case "ready_for_import":
        completeThrough(steps, 1);
        setCurrent(steps, 2, "current", "核对已确认，可以导入发票");
        break;
      case "importing":
        completeThrough(steps, 1);
        setCurrent(steps, 2, "processing", "ETC 发票正在导入");
        break;
      case "imported":
      case "closed":
        completeThrough(steps, 2);
        setCurrent(steps, 3, "current", "可以创建或确认 OA 草稿");
        break;
    }
  } else {
    switch (batch.status) {
      case "reviewing":
        completeThrough(steps, 0);
        setCurrent(steps, 1, "current", "处理差异并确认核对结果");
        break;
      case "ready_for_import":
        completeThrough(steps, 1);
        setCurrent(steps, 2, "current", "核对已确认，可以导入发票");
        break;
      case "importing":
        completeThrough(steps, 1);
        setCurrent(steps, 2, "processing", "ETC 发票正在导入");
        break;
      case "imported":
      case "oa_draft_creating":
      case "oa_draft_failed":
      case "oa_confirmation_pending":
      case "not_submitted":
      case "manually_marked_not_submitted":
      case "oa_submitted":
      case "manually_marked_submitted":
      case "closed":
        completeThrough(steps, 2);
        setCurrent(steps, 3, "current", "可以创建或确认 OA 草稿");
        break;
      default:
        setCurrent(steps, 0, "current", "等待上传并解析账单与票根");
    }
  }

  if (options.taskError && !task) {
    const activeIndex = Math.max(0, steps.findIndex((step) => step.state !== "complete"));
    setCurrent(steps, activeIndex, "problem", options.taskError);
  }

  if (batch.status === "import_failed" || batch.status === "import_partial_failed") {
    completeThrough(steps, 1);
    setCurrent(
      steps,
      2,
      "problem",
      batch.status === "import_partial_failed" ? "部分发票导入失败，需要处理" : "发票导入失败，需要重试",
    );
  } else if (batch.status === "oa_draft_creating") {
    completeThrough(steps, 2);
    setCurrent(steps, 3, "manual", "已发起 OA 草稿创建，等待人工确认");
  } else if (batch.status === "oa_confirmation_pending") {
    completeThrough(steps, 2);
    setCurrent(steps, 3, "manual", "OA 草稿已创建，等待人工确认");
  } else if (["oa_draft_failed", "not_submitted", "manually_marked_not_submitted"].includes(batch.status)) {
    completeThrough(steps, 2);
    setCurrent(
      steps,
      3,
      "problem",
      batch.createOaDraftAction?.message || "OA 草稿未提交，需要重新处理",
    );
  } else if (submittedStatuses.has(batch.status)) {
    completeThrough(steps, 3);
    steps[3].description = batch.status === "manually_marked_submitted" ? "已人工确认提交" : "OA 审批已提交";
  } else if (problemStatuses.has(batch.status)) {
    const activeIndex = Math.max(0, steps.findIndex((step) => step.state !== "complete"));
    setCurrent(steps, activeIndex, "problem", "批次状态异常，需要人工处理");
  }

  return steps;
}

const stateLabels: Record<EtcBatchProgressState, string> = {
  complete: "已完成",
  current: "当前阶段",
  pending: "待开始",
  processing: "处理中",
  manual: "待人工确认",
  problem: "需要处理",
};

export default function EtcBatchProgress({ batch, task, taskLoading = false, taskError = null }: EtcBatchProgressProps) {
  if (!batch) {
    return null;
  }
  const steps = deriveEtcBatchProgress(batch, task, { taskLoading, taskError });
  const allComplete = steps.every((step) => step.state === "complete");

  return (
    <ol className="etc-batch-progress" aria-label="批次生命周期">
      {steps.map((step, index) => {
        const isCurrent = ["current", "processing", "manual", "problem"].includes(step.state)
          || (allComplete && index === steps.length - 1);
        return (
          <li
            key={step.id}
            className="etc-batch-progress__step"
            data-state={step.state}
            aria-current={isCurrent ? "step" : undefined}
          >
            <span className="etc-batch-progress__marker" aria-hidden="true">
              {step.state === "complete" ? "✓" : index + 1}
            </span>
            <span className="etc-batch-progress__copy">
              <strong>{step.label}</strong>
              {step.state !== "complete" ? <span>{stateLabels[step.state]} · {step.description}</span> : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
