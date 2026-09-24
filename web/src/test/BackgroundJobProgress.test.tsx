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

const failedImportJob = {
  job_id: "job_file_import_failed",
  type: "file_import",
  label: "导入银行流水",
  short_label: "导入银行流水失败",
  status: "failed",
  phase: "failed",
  current: 2,
  total: 4,
  percent: 50,
  message: "导入银行流水失败。",
  result_summary: {
    warmed: 2,
    failed: 2,
    total: 4,
  },
  retryable: true,
  retry_mode: "file_import",
  acknowledgeable: true,
  attention: true,
  error: "warmup_failed",
  source: { session_id: "session-1", selected_file_ids: ["file-1"] },
  created_at: "2026-05-03T18:30:00+08:00",
  updated_at: "2026-05-03T18:30:02+08:00",
  finished_at: "2026-05-03T18:30:02+08:00",
};

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function openStatus() {
  const button = await waitFor(() => {
    const trigger = document.querySelector<HTMLElement>('.app-sidebar-brand-mark[role="button"]');
    expect(trigger).toBeVisible();
    return trigger!;
  });
  await userEvent.click(button);
  return screen.findByRole("dialog", { name: "全局运行状态" });
}

describe("background tasks are handled only in the runtime status popover", () => {
  test("maps completed job affected scopes", () => {
    expect(mapBackgroundJob({ job_id: "one", status: "succeeded", result_summary: {
      affected_months: ["2026-04"], affected_scope_keys: ["all", "2026-04"],
    } }).affectedScopeKeys).toEqual(["2026-04"]);
  });

  test.each(["/", "/bank-details", "/cost-statistics", "/imports/invoices"])("never mounts a global progress banner on %s", async path => {
    const fetchMock = installMockApiFetch({ backgroundJobs: [runningEtcJob] });
    renderAppAt(path);
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/background-jobs/active"))).toBe(true));
    expect(screen.queryByTestId("background-progress-block")).not.toBeInTheDocument();
    expect(document.querySelector(".app-shell-progress-stack")).toBeNull();
    expect(screen.queryByText(runningEtcJob.short_label)).not.toBeInTheDocument();
    await openStatus();
    expect(await screen.findByText(runningEtcJob.short_label)).toBeInTheDocument();
  });

  test("retries a task from the existing status popover", async () => {
    const fetchMock = installMockApiFetch({ backgroundJobs: [failedImportJob] });
    renderAppAt("/");
    await openStatus();
    await userEvent.click(await screen.findByRole("button", { name: "重新执行" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/job_file_import_failed/retry"), expect.objectContaining({ method: "POST" })));
  });

  test("failed retry stays visible in the popover without a global banner", async () => {
    installMockApiFetch({ backgroundJobs: [failedImportJob], backgroundJobRetryStatus: 409,
      backgroundJobRetryBody: { message: "任务范围已变化" } });
    renderAppAt("/");
    await openStatus();
    await userEvent.click(await screen.findByRole("button", { name: "重新执行" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("任务范围已变化");
    expect(screen.getByRole("button", { name: "重新执行" })).toBeEnabled();
    expect(screen.queryByTestId("background-progress-block")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "关闭错误" }));
    expect(screen.queryByText("任务范围已变化")).not.toBeInTheDocument();
  });

  test("acknowledges a task through the existing API", async () => {
    const fetchMock = installMockApiFetch({ backgroundJobs: [failedImportJob] });
    renderAppAt("/");
    await openStatus();
    await userEvent.click(await screen.findByRole("button", { name: "确认已知" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/job_file_import_failed/acknowledge"), expect.objectContaining({ method: "POST" })));
    await waitFor(() => expect(screen.queryByText(failedImportJob.short_label)).not.toBeInTheDocument());
  });

  test("shared import tasks keep their dedicated entry and cannot be blindly acknowledged", async () => {
    installMockApiFetch({ backgroundJobs: [{ ...failedImportJob, job_id: "import:review", status: "needs_review",
      short_label: "预览需要复核", retry_mode: "reprepare", acknowledgeable: false,
      source: { route: "/imports/invoices" } }] });
    renderAppAt("/");
    await openStatus();
    expect(await screen.findByRole("button", { name: "预览需要复核" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重新执行" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "确认已知" })).not.toBeInTheDocument();
  });
});
