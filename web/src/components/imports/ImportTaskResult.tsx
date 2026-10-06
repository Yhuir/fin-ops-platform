import { Button } from "@heroui/react";
import { useEffect, useState } from "react";

import { fetchBackgroundJob } from "../../features/backgroundJobs/api";
import { useBackgroundJobProgress } from "../../features/backgroundJobs/BackgroundJobProgressProvider";
import type { BackgroundJob } from "../../features/backgroundJobs/types";
import { SharedImportTasksButton } from "./ImportJobDiagnostics";

export default function ImportTaskResult({ accepted, embedded = false }: { accepted: BackgroundJob; embedded?: boolean }) {
  const { jobs } = useBackgroundJobProgress();
  const [job, setJob] = useState(accepted);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const running = job.status === "queued" || job.status === "running";
  useEffect(() => {
    if (!running) return;
    const current = jobs.find(item => item.jobId === accepted.jobId);
    if (current) { setJob(current); setError(""); return; }
    // Completed imports leave the global feed. Read this page's exact task once
    // per existing feed update; no independent polling or historical success replay.
    const request = new AbortController();
    void fetchBackgroundJob(accepted.jobId, request.signal).then(result => {
      if (!request.signal.aborted) { setJob(result); setError(""); }
    }).catch(reason => {
      if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : "导入结果读取失败。");
    });
    return () => request.abort();
  }, [accepted.jobId, jobs, running, revision]);

  return <section aria-label="本次导入结果">
    <p role={job.status === "failed" || job.status === "partial_success" ? "alert" : "status"}>{running ? "已开始后台导入" : job.message || job.shortLabel}</p>
    {error && <p role="alert">{error}<Button variant="secondary" onPress={() => setRevision(value => value + 1)}>重新读取结果</Button></p>}
    {!embedded && <SharedImportTasksButton jobId={accepted.jobId} label="查看本次导入结果" />}
  </section>;
}
