import type { BackgroundJob, BackgroundJobStatus } from "../../features/backgroundJobs/types";

type BackgroundProgressBlockProps =
  | {
      kind: "job";
      job: BackgroundJob;
      extraCount: number;
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
  const hasImportRetrySource =
    job.type === "file_import"
    && typeof job.source.session_id === "string"
    && Array.isArray(job.source.selected_file_ids)
    && job.source.selected_file_ids.length > 0;
  return job.retryable && hasImportRetrySource && (job.status === "failed" || job.status === "partial_success");
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

  const { job, extraCount, onAcknowledge, onRetry } = props;
  const tone = statusTone(job.status);
  const label = job.shortLabel || job.message || job.label || "后台任务处理中";

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
          aria-label="重新执行"
          className="background-progress-action"
          type="button"
          onClick={() => onRetry(job.jobId)}
        >
          重新执行
        </button>
      ) : null}
      {job.acknowledgeable !== false && canAcknowledge(job.status) ? (
        <button
          aria-label="确认已知"
          className="background-progress-close"
          type="button"
          onClick={() => onAcknowledge(job.jobId)}
        >
          确认已知
        </button>
      ) : null}
    </div>
  );
}
