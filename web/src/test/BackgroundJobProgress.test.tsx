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

describe("global background job page header", () => {
  test("does not render a page header when there are no active jobs", async () => {
    installMockApiFetch({ backgroundJobs: [] });
    renderAppAt("/");

    await waitFor(() => {
      expect(screen.queryByTestId("background-progress-block")).not.toBeInTheDocument();
    });
  });

  test("does not render a running job page header on the current page", async () => {
    installMockApiFetch({ backgroundJobs: [runningEtcJob] });
    renderAppAt("/");

    await waitFor(() => {
      expect(screen.queryByTestId("background-progress-block")).not.toBeInTheDocument();
    });
  });

  test("does not render a failed job page header; the status icon still carries the reason", async () => {
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

    await waitFor(() => {
      expect(screen.queryByTestId("background-progress-block")).not.toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "确认已知" })).not.toBeInTheDocument();
  });

  test("keeps the background job page header removed after route changes", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ backgroundJobs: [runningEtcJob] });
    renderAppAt("/");

    await waitFor(() => {
      expect(screen.queryByTestId("background-progress-block")).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("link", { name: "银行明细" }));

    await waitFor(() => {
      expect(screen.queryByTestId("background-progress-block")).not.toBeInTheDocument();
    });
  });
});
