import type { BackgroundJob, BackgroundJobStatus } from "../../features/backgroundJobs/types";

type BackgroundProgressBlockProps =
  | {
      kind: "job";
      job: BackgroundJob;
      extraCount: number;
      operating: boolean;
      onAcknowledge: (jobId: string) => void;
      onRetry: (jobId: string) => void;
    }
  | {
      kind: "connection_error";
    };

function statusTone(status: BackgroundJobStatus) {
  if (status === "succeeded") {
    return "succeeded";
  }
  if (status === "partial_success") {
    return "partial_success";
  }
  if (status === "failed") {
    return "failed";
  }
  if (status === "queued") {
    return "queued";
  }
  return "running";
}

function canAcknowledge(status: BackgroundJobStatus) {
  return status === "failed" || status === "partial_success" || status === "succeeded";
}

function canRetry(job: BackgroundJob) {
  return job.retryable && (job.status === "failed" || job.status === "partial_success");
}

export default function BackgroundProgressBlock(props: BackgroundProgressBlockProps) {
  if (props.kind === "connection_error") {
    return (
      <div
        aria-live="polite"
        className="background-progress-block failed"
        data-testid="background-progress-block"
        role="status"
        title="后台进度连接失败"
      >
        <span className="background-progress-dot" aria-hidden="true" />
        <strong>后台进度连接失败</strong>
      </div>
    );
  }

  const { job, extraCount, operating, onAcknowledge, onRetry } = props;
  const tone = statusTone(job.status);
  const label = job.shortLabel || job.message || job.label || "后台任务处理中";
  const actionLabel = operating ? "处理中" : "重新执行";
  const acknowledgeLabel = operating ? "处理中" : "确认已知";

  return (
    <div
      aria-live="polite"
      className={`background-progress-block ${tone}`}
      data-testid="background-progress-block"
      role="status"
      title={label}
    >
      <span className="background-progress-dot" aria-hidden="true" />
      <strong>{label}</strong>
      {extraCount > 0 ? <span className="background-progress-extra">+{extraCount}</span> : null}
      {canRetry(job) ? (
        <button
          aria-label={actionLabel}
          className="background-progress-action"
          disabled={operating}
          type="button"
          onClick={() => onRetry(job.jobId)}
        >
          {actionLabel}
        </button>
      ) : null}
      {job.acknowledgeable && canAcknowledge(job.status) ? (
        <button
          aria-label={acknowledgeLabel}
          className="background-progress-close"
          disabled={operating}
          type="button"
          onClick={() => onAcknowledge(job.jobId)}
        >
          {acknowledgeLabel}
        </button>
      ) : null}
    </div>
  );
}
