import { apiRequestJson } from "../apiClient";
import { fetchBackgroundJob, mapBackgroundJob, type ApiBackgroundJob } from "../backgroundJobs/api";
import type { BackgroundJob } from "../backgroundJobs/types";

export type ImportPreparationAccepted = { job: ApiBackgroundJob };

export async function waitForImportPreparation(accepted: ImportPreparationAccepted): Promise<BackgroundJob> {
  return waitForImportTask(accepted, "prepare");
}

export async function waitForImportCompletion(accepted: ImportPreparationAccepted): Promise<BackgroundJob> {
  return waitForImportTask(accepted, "commit");
}

async function waitForImportTask(accepted: ImportPreparationAccepted, phase: "prepare" | "commit"): Promise<BackgroundJob> {
  if (!accepted.job?.job_id) throw new Error("导入受理响应缺少任务编号。");
  let job = mapBackgroundJob(accepted.job);
  const deadline = Date.now() + 120_000;
  while (job.status === "queued" || job.status === "running") {
    if (Date.now() >= deadline) {
      throw new Error("导入任务仍在后台处理，请从全局任务查看进度；无需重新上传。");
    }
    await new Promise((resolve) => window.setTimeout(resolve, 300));
    job = await fetchBackgroundJob(job.jobId);
  }
  if (job.status !== "succeeded" && !(phase === "commit" && job.status === "partial_success") && !(phase === "prepare" && (job.status === "awaiting_confirmation" || job.status === "needs_review"))) {
    throw new Error(job.error || job.message || "文件准备未完成，请查看导入任务。");
  }
  return job;
}

export async function fetchImportTaskResult<T>(jobId: string): Promise<{ job: BackgroundJob; result: T }> {
  const payload = await apiRequestJson<{ job: ApiBackgroundJob; result: T }>(
    `/api/background-jobs/${encodeURIComponent(jobId)}/result`, { method: "GET" },
  );
  return { job: mapBackgroundJob(payload.job), result: payload.result };
}
