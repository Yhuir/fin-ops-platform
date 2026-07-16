import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";
import { mapBackgroundJob } from "../features/backgroundJobs/api";

const runningEtcJob = {
  job_id: "job_etc_001",
  type: "etc_invoice_import",
  label: "导入 ETC发票",
  short_label: "正在导入 ETC发票 3/31",
  status: "running",
  phase: "persist_items",
  current: 3,
  total: 31,
  percent: 10,
  message: "正在导入 ETC发票。",
  result_summary: {},
  error: null,
  created_at: "2026-05-03T18:30:00+08:00",
  updated_at: "2026-05-03T18:30:02+08:00",
  finished_at: null,
};

const failedWorkbenchMatchingJob = {
  job_id: "job_workbench_matching_failed",
  type: "workbench_matching",
  label: "关联台匹配",
  short_label: "关联台匹配失败",
  status: "failed",
  phase: "failed",
  current: 2,
  total: 4,
  percent: 50,
  message: "关联台匹配失败。",
  result_summary: {
    warmed: 2,
    failed: 2,
    total: 4,
  },
  retryable: true,
  retry_mode: "failed_scopes",
  acknowledgeable: true,
  attention: true,
  error: "warmup_failed",
  created_at: "2026-05-03T18:30:00+08:00",
  updated_at: "2026-05-03T18:30:02+08:00",
  finished_at: "2026-05-03T18:30:02+08:00",
};

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("global background job page header", () => {
  test("maps completed job result targets from result summary", () => {
    const job = mapBackgroundJob({
      job_id: "job_file_import_001",
      type: "file_import",
      status: "succeeded",
      result_summary: {
        affected_months: ["2026-04"],
        affected_scope_keys: ["all", "2026-04", "active:2026-04"],
        read_model_scope_keys: ["all", "2026-04", "active:2026-04"],
        operation_barrier_targets: [
          { read_model_key: "workbench", scope_key: "all" },
          { read_model_key: "workbench_relation", scope_key: "2026-04" },
          { read_model_key: "cost_statistics", scope_key: "active:2026-04" },
        ],
      },
    });

    expect(job.affectedMonths).toEqual(["2026-04"]);
    expect(job.affectedScopeKeys).toEqual(["2026-04", "active:2026-04"]);
    expect(job.readModelScopeKeys).toEqual(["2026-04", "active:2026-04"]);
    expect(job.operationBarrierTargets).toEqual([
      { readModelKey: "workbench_relation", scopeKey: "2026-04" },
      { readModelKey: "cost_statistics", scopeKey: "active:2026-04" },
    ]);
  });

  test("does not render a page header when there are no active jobs", async () => {
    installMockApiFetch({ backgroundJobs: [] });
    renderAppAt("/");

    await waitFor(() => {
      expect(screen.queryByTestId("background-progress-block")).not.toBeInTheDocument();
    });
  });

  test("renders a running job page header on the current page", async () => {
    installMockApiFetch({ backgroundJobs: [runningEtcJob] });
    renderAppAt("/");

    expect(await screen.findByTestId("background-progress-block")).toHaveTextContent("正在导入 ETC发票 3/31");
  });

  test("renders a retry action for retryable attention jobs", async () => {
    const fetchMock = installMockApiFetch({
      backgroundJobs: [
        failedWorkbenchMatchingJob,
      ],
    });
    renderAppAt("/");

    expect(await screen.findByTestId("background-progress-block")).toHaveTextContent("关联台匹配失败");

    await userEvent.click(screen.getByRole("button", { name: "重新执行" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/background-jobs/job_workbench_matching_failed/retry"),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  test("shows operation feedback when retry fails instead of appearing unresponsive", async () => {
    installMockApiFetch({
      backgroundJobs: [failedWorkbenchMatchingJob],
      backgroundJobRetryStatus: 409,
      backgroundJobRetryBody: { message: "关联台匹配任务缺少重新执行所需的范围。" },
    });
    renderAppAt("/");

    expect(await screen.findByTestId("background-progress-block")).toHaveTextContent("关联台匹配失败");

    await userEvent.click(screen.getByRole("button", { name: "重新执行" }));

    expect(await screen.findByText("关联台匹配任务缺少重新执行所需的范围。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新执行" })).toBeEnabled();
  });

  test("acknowledges known attention jobs from the global progress header", async () => {
    const fetchMock = installMockApiFetch({
      backgroundJobs: [failedWorkbenchMatchingJob],
    });
    renderAppAt("/");

    expect(await screen.findByTestId("background-progress-block")).toHaveTextContent("关联台匹配失败");

    await userEvent.click(screen.getByRole("button", { name: "确认已知" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/background-jobs/job_workbench_matching_failed/acknowledge"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => {
      expect(screen.queryByTestId("background-progress-block")).not.toBeInTheDocument();
    });
  });

  test("keeps the global background job status visible after route changes", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ backgroundJobs: [runningEtcJob] });
    renderAppAt("/");

    expect(await screen.findByTestId("background-progress-block")).toHaveTextContent("正在导入 ETC发票 3/31");

    await user.click(screen.getByRole("link", { name: "银行明细" }));

    expect(await screen.findByRole("status", { name: "正在执行后台任务：正在导入 ETC发票 3/31" })).toBeInTheDocument();
    expect(screen.queryByTestId("background-progress-block")).not.toBeInTheDocument();
  });
});
