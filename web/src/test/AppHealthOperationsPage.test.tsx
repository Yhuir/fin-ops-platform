import { render, screen, waitFor, within } from "@testing-library/react";

import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

const PAGE_TIMEOUT = 3000;

function renderOperationsPage(options: Parameters<typeof installMockApiFetch>[0] = {}) {
  window.history.pushState({}, "", "/operations/app-health");
  const fetchMock = installMockApiFetch({
    sessionAccessTier: "admin",
    sessionUsername: "admin.ops",
    sessionDisplayName: "运维管理员",
    ...options,
  });
  render(<App />);
  return fetchMock;
}

describe("AppHealthOperationsPage", () => {
  test("renders admin app health diagnostics", async () => {
    renderOperationsPage({
      appHealth: {
        status: "ok",
        reason: "系统状态正常",
        generated_at: "2026-05-06T09:00:00+08:00",
        session: {
          status: "authenticated",
          user: {
            username: "admin.ops",
            display_name: "运维管理员",
          },
          access_tier: "admin",
          can_mutate_data: true,
        },
        oa_sync: {
          status: "synced",
          dirty_scopes: [],
          last_synced_at: "2026-05-06T08:59:00+08:00",
          version: 12,
          message: "OA 已同步",
        },
        workbench_read_model: {
          status: "ready",
          dirty_scopes: [],
          stale_scopes: [],
          rebuilding_scopes: [],
          last_rebuilt_at: "2026-05-06T08:58:00+08:00",
        },
        background_jobs: {
          queued: 0,
          running: 0,
          attention: 0,
          jobs: [
            {
              job_id: "job-001",
              type: "oa_sync",
              label: "OA 同步",
              status: "completed",
              updated_at: "2026-05-06T08:57:00+08:00",
              message: "done",
            },
          ],
        },
        dependencies: {
          oa_identity: { status: "available" },
          oa_sync: { status: "available", message: "OA 已同步" },
          background_jobs: { status: "available" },
          state_store: { status: "available", storage_mode: "file", backend: "json" },
        },
        alerts: {
          active: [],
          recent_recovered: [],
        },
      },
    });

    expect(await screen.findByRole("heading", { name: "AppHealth 运维状态" }, { timeout: PAGE_TIMEOUT })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("app-health-summary")).toHaveTextContent("ok"));
    expect(screen.getByTestId("app-health-summary")).toHaveTextContent("系统状态正常");
    expect(screen.getByTestId("app-health-session")).toHaveTextContent("运维管理员");
    expect(screen.getByTestId("app-health-session")).toHaveTextContent("admin.ops");
    expect(screen.getByTestId("app-health-session")).toHaveTextContent("admin");
    expect(screen.getByTestId("app-health-oa-sync")).toHaveTextContent("OA 已同步");
    expect(screen.getByTestId("app-health-oa-sync")).toHaveTextContent("12");
    expect(screen.getByTestId("app-health-workbench")).toHaveTextContent("ready");
    expect(await within(screen.getByTestId("app-health-background-jobs")).findByText("job-001")).toBeInTheDocument();
    expect(screen.getByTestId("app-health-dependencies")).toHaveTextContent("oa_identity");
    expect(screen.getByTestId("app-health-dependencies")).toHaveTextContent("state_store");
  });

  test("blocks non admin users without showing diagnostics", async () => {
    renderOperationsPage({
      sessionAccessTier: "full_access",
      sessionUsername: "finance.user",
      sessionDisplayName: "财务用户",
      appHealth: {
        status: "blocked",
        reason: "OA identity secret",
        dependencies: {
          oa_identity: { status: "unavailable", message: "secret connection failure" },
        },
      },
    });

    expect(await screen.findByText("当前账号没有管理员权限，不能查看 AppHealth 运维状态。", {}, { timeout: PAGE_TIMEOUT })).toBeInTheDocument();
    expect(screen.queryByTestId("app-health-summary")).not.toBeInTheDocument();
    expect(screen.queryByText("secret connection failure")).not.toBeInTheDocument();
  });

  test("shows busy, blocked and alert details", async () => {
    renderOperationsPage({
      appHealth: {
        status: "blocked",
        reason: "OA 同步失败",
        generated_at: "2026-05-06T09:05:00+08:00",
        session: {
          status: "authenticated",
          user: { username: "admin.ops", display_name: "运维管理员" },
          access_tier: "admin",
          can_mutate_data: true,
        },
        oa_sync: {
          status: "error",
          dirty_scopes: ["all", "2026-05"],
          last_synced_at: "2026-05-06T08:50:00+08:00",
          version: 13,
          message: "OA 同步失败",
        },
        workbench_read_model: {
          status: "rebuilding",
          dirty_scopes: ["all"],
          stale_scopes: ["2026-05"],
          rebuilding_scopes: ["all"],
          last_rebuilt_at: "2026-05-06T08:40:00+08:00",
        },
        background_jobs: {
          queued: 2,
          running: 1,
          attention: 1,
          jobs: [
            {
              job_id: "job-running",
              type: "workbench_rebuild",
              label: "重建关联台",
              status: "running",
              updated_at: "2026-05-06T09:04:00+08:00",
              message: "处理中",
            },
            {
              job_id: "job-failed",
              type: "oa_sync",
              label: "OA 同步",
              status: "failed",
              updated_at: "2026-05-06T09:03:00+08:00",
              message: "OA 同步失败",
            },
          ],
        },
        dependencies: {
          oa_identity: { status: "available" },
          oa_sync: { status: "unavailable", message: "OA 同步失败" },
          background_jobs: { status: "available" },
          state_store: { status: "available" },
        },
        alerts: {
          active: [
            {
              id: "alert-001",
              severity: "critical",
              source: "oa_sync",
              message: "OA 同步失败",
              started_at: "2026-05-06T09:03:00+08:00",
            },
          ],
          recent_recovered: [
            {
              id: "alert-000",
              severity: "warning",
              source: "background_jobs",
              message: "任务积压恢复",
              recovered_at: "2026-05-06T08:30:00+08:00",
            },
          ],
        },
      },
    });

    expect(await screen.findByRole("heading", { name: "AppHealth 运维状态" }, { timeout: PAGE_TIMEOUT })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("app-health-summary")).toHaveTextContent("blocked"));
    expect(screen.getByTestId("app-health-oa-sync")).toHaveTextContent("all");
    expect(screen.getByTestId("app-health-oa-sync")).toHaveTextContent("2026-05");
    expect(screen.getByTestId("app-health-workbench")).toHaveTextContent("rebuilding");
    expect(screen.getByTestId("app-health-background-jobs")).toHaveTextContent("Queued");
    expect(screen.getByTestId("app-health-background-jobs")).toHaveTextContent("2");
    expect(screen.getByTestId("app-health-background-jobs")).toHaveTextContent("job-failed");
    expect(screen.getByTestId("app-health-dependencies")).toHaveTextContent("unavailable");

    const alerts = screen.getByTestId("app-health-alerts");
    expect(within(alerts).getByText("alert-001")).toBeInTheDocument();
    expect(within(alerts).getByText("active")).toBeInTheDocument();
    expect(within(alerts).getByText("alert-000")).toBeInTheDocument();
    expect(within(alerts).getByText("recovered")).toBeInTheDocument();
  });
});
