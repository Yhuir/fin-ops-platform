import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

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

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("global background job progress block", () => {
  test("does not render when there are no active jobs", async () => {
    installMockApiFetch({ backgroundJobs: [] });
    renderAppAt("/");

    await waitFor(() => {
      expect(screen.queryByTestId("background-progress-block")).not.toBeInTheDocument();
    });
  });

  test("shows a running job short label from the backend", async () => {
    installMockApiFetch({ backgroundJobs: [runningEtcJob] });
    renderAppAt("/");

    const block = await screen.findByTestId("background-progress-block");
    expect(block).toHaveTextContent("正在导入 ETC发票 3/31");
    expect(block).toHaveClass("running");
    expect(block).not.toHaveTextContent("etc-2026-03.zip");
  });

  test("prioritizes failed jobs and uses the failed style", async () => {
    installMockApiFetch({
      backgroundJobs: [
        runningEtcJob,
        {
          ...runningEtcJob,
          job_id: "job_failed_001",
          status: "failed",
          short_label: "ETC发票导入失败",
          error: "部分 XML 无法解析",
        },
      ],
    });
    renderAppAt("/");

    const block = await screen.findByTestId("background-progress-block");
    expect(block).toHaveTextContent("ETC发票导入失败");
    expect(block).toHaveClass("failed");
  });

  test("shows extra job count when multiple jobs are active", async () => {
    installMockApiFetch({
      backgroundJobs: [
        runningEtcJob,
        {
          ...runningEtcJob,
          job_id: "job_import_002",
          type: "file_import",
          short_label: "正在导入 银行流水 2/8",
        },
        {
          ...runningEtcJob,
          job_id: "job_rebuild_003",
          type: "workbench_rebuild",
          short_label: "正在重建关联台 2026-03",
        },
      ],
    });
    renderAppAt("/");

    const block = await screen.findByTestId("background-progress-block");
    expect(block).toHaveTextContent("正在导入 ETC发票 3/31");
    expect(block).toHaveTextContent("+2");
  });

  test("keeps showing backend job after route changes", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ backgroundJobs: [runningEtcJob] });
    renderAppAt("/");

    expect(await screen.findByTestId("background-progress-block")).toHaveTextContent("正在导入 ETC发票 3/31");

    await user.click(screen.getByRole("link", { name: "银行明细" }));

    expect(await screen.findByTestId("background-progress-block")).toHaveTextContent("正在导入 ETC发票 3/31");
  });

  test("acknowledges a failed job and hides the block after refresh", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      backgroundJobs: [
        {
          ...runningEtcJob,
          job_id: "job_failed_001",
          status: "failed",
          short_label: "ETC发票导入失败",
          error: "部分 XML 无法解析",
        },
      ],
    });
    renderAppAt("/");

    const block = await screen.findByTestId("background-progress-block");
    await user.click(screen.getByRole("button", { name: "确认已知" }));

    await waitFor(() => {
      expect(screen.queryByTestId("background-progress-block")).not.toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/background-jobs/job_failed_001/acknowledge",
      expect.objectContaining({ method: "POST" }),
    );
    expect(block).toHaveClass("failed");
  });

  test("shows retry action for retryable failed file import jobs", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      backgroundJobs: [
        {
          ...runningEtcJob,
          job_id: "job_failed_retryable",
          type: "file_import",
          status: "failed",
          short_label: "发票导入失败",
          retryable: true,
          acknowledgeable: true,
          source: {
            session_id: "import_session_0001",
            selected_file_ids: ["import_file_0001"],
          },
        },
      ],
    });
    renderAppAt("/");

    const block = await screen.findByTestId("background-progress-block");
    expect(block).toHaveTextContent("发票导入失败");
    await user.click(screen.getByRole("button", { name: "重新执行" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/background-jobs/job_failed_retryable/retry",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  test("does not show fake retry action for non retryable failed jobs", async () => {
    installMockApiFetch({
      backgroundJobs: [
        {
          ...runningEtcJob,
          job_id: "job_failed_no_retry",
          status: "failed",
          short_label: "后台任务失败",
          retryable: false,
          acknowledgeable: true,
        },
      ],
    });
    renderAppAt("/");

    expect(await screen.findByTestId("background-progress-block")).toHaveTextContent("后台任务失败");
    expect(screen.queryByRole("button", { name: "重新执行" })).not.toBeInTheDocument();
  });
});
