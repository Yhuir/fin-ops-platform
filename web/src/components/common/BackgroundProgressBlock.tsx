import type { BackgroundJob, BackgroundJobStatus } from "../../features/backgroundJobs/types";

type BackgroundProgressBlockProps =
  | {
      kind: "job";
      job: BackgroundJob;
      extraCount: number;
      onAcknowledge: (jobId: string) => void;
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

  const { job, extraCount, onAcknowledge } = props;
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
      {canAcknowledge(job.status) ? (
        <button
          aria-label="关闭后台任务提示"
          className="background-progress-close"
          type="button"
          onClick={() => onAcknowledge(job.jobId)}
        >
          x
        </button>
      ) : null}
    </div>
  );
}
