import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ApiAppHealthPayload, AppHealthStatus } from "../features/appHealth/types";

const mocked = vi.hoisted(() => ({
  session: {
    status: "authenticated",
    session: {
      canMutateData: true,
      canAccessApp: true,
      canAdminAccess: false,
      accessTier: "full_access",
    },
  } as any,
  permissions: {
    canMutateData: true,
    canAccessApp: true,
    canAdminAccess: false,
    accessTier: "full_access",
  } as any,
  jobs: [] as Array<Record<string, unknown> & { status: string }>,
  connectionFailed: false,
  progress: null as { tone: string } | null,
  workbenchStatus: null as { level: "ok" | "pending" | "error"; reason: string } | null,
  appHealth: null as ApiAppHealthPayload | null,
}));

vi.mock("../contexts/SessionContext", () => ({
  useSession: () => mocked.session,
  useSessionPermissions: () => mocked.permissions,
}));

vi.mock("../features/backgroundJobs/BackgroundJobProgressProvider", () => ({
  useBackgroundJobProgress: () => ({
    jobs: mocked.jobs,
    connectionFailed: mocked.connectionFailed,
  }),
}));

vi.mock("../contexts/ImportProgressContext", () => ({
  useImportProgress: () => ({ progress: mocked.progress }),
}));

vi.mock("../contexts/AppChromeContext", () => ({
  useAppChrome: () => ({ workbenchStatus: mocked.workbenchStatus }),
}));

vi.mock("../features/appHealth/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/appHealth/api")>();
  return {
    ...actual,
    fetchAppHealth: vi.fn(async () => mocked.appHealth ?? {
      status: "ok",
      session: { status: "authenticated" },
      oa_sync: { status: "synced", dirty_scopes: [] },
      workbench_matching: { status: "ready", dirty_scopes: [] },
      background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
      dependencies: {},
    }),
    fetchOaSyncStatus: vi.fn(async () => ({ status: "synced", dirty_scopes: [] })),
  };
});

const { fetchAppHealth } = await import("../features/appHealth/api");
const { AppHealthStatusProvider, useAppHealthStatus, useCanMutateWithHealth } = await import("../contexts/AppHealthStatusContext");

function StatusProbe() {
  const healthStatus = useAppHealthStatus();
  const canMutateWithHealth = useCanMutateWithHealth();
  return (
    <output
      aria-label="health"
      data-blocks={String(healthStatus.blocksMutations)}
      data-can-mutate={String(canMutateWithHealth)}
      data-level={healthStatus.level}
      data-reason={healthStatus.reason}
    >
      {JSON.stringify(healthStatus satisfies AppHealthStatus)}
    </output>
  );
}

function renderProbe() {
  render(
    <AppHealthStatusProvider>
      <StatusProbe />
    </AppHealthStatusProvider>,
  );
}

describe("AppHealthStatusProvider", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    mocked.session = {
      status: "authenticated",
      session: {
        canMutateData: true,
        canAccessApp: true,
        canAdminAccess: false,
        accessTier: "full_access",
      },
    };
    mocked.permissions = {
      canMutateData: true,
      canAccessApp: true,
      canAdminAccess: false,
      accessTier: "full_access",
    };
    mocked.jobs = [];
    mocked.connectionFailed = false;
    mocked.progress = null;
    mocked.workbenchStatus = null;
    mocked.appHealth = null;
  });

  it("reports yellow before local session validation finishes", () => {
    mocked.session = { status: "loading" };
    mocked.permissions = { ...mocked.permissions, canMutateData: false };
    renderProbe();
    const status = screen.getByLabelText("health");
    expect(status).toHaveAttribute("data-level", "busy");
    expect(status).toHaveAttribute("data-reason", "正在校验登录状态");
  });

  it("reports red when the local session is expired", () => {
    mocked.session = { status: "expired", message: "expired" };
    mocked.permissions = { ...mocked.permissions, canMutateData: false };
    renderProbe();
    const status = screen.getByLabelText("health");
    expect(status).toHaveAttribute("data-level", "blocked");
    expect(status).toHaveAttribute("data-blocks", "true");
  });

  it("reports yellow while background jobs are running", async () => {
    mocked.jobs = [{
      jobId: "job-running",
      type: "file_import",
      label: "导入发票",
      shortLabel: "导入 发票 2/5",
      status: "running",
    }];
    renderProbe();
    await waitFor(() => {
      const status = screen.getByLabelText("health");
      expect(status).toHaveAttribute("data-level", "busy");
      expect(status).toHaveAttribute("data-reason", "正在执行后台任务：导入 发票 2/5");
    });
  });

  it("reports failed import attention without being overwritten by OA synced", async () => {
    mocked.appHealth = {
      status: "busy",
      session: { status: "authenticated" },
      oa_sync: { status: "synced", message: "OA 已同步", dirty_scopes: [] },
      workbench_matching: { status: "ready", dirty_scopes: [] },
      background_jobs: {
        active: 1,
        queued: 0,
        running: 0,
        attention: 1,
        primary_attention: {
          job_id: "job-failed",
          type: "file_import",
          label: "导入发票",
          short_label: "导入发票失败",
          status: "failed",
          acknowledgeable: true,
          retryable: true,
        },
      },
    };
    renderProbe();
    await waitFor(() => {
      expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "busy");
      expect(screen.getByLabelText("health")).toHaveAttribute("data-reason", "有 1 个失败导入任务需要确认");
    });
  });

  it("does not block mutations when app status is blocked only by read freshness", async () => {
    mocked.appHealth = {
      status: "blocked",
      session: { status: "authenticated" },
      oa_sync: { status: "synced", message: "OA 已同步", dirty_scopes: [] },
      workbench_matching: { status: "ready", dirty_scopes: [] },
      background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
      app_status: {
        version: 1,
        generated_at: "2026-06-13T17:30:00+08:00",
        overall: {
          level: "blocked",
          color: "red",
          reason: "关联关系不可用",
          blocks_mutations: false,
          write_safety: {
            status: "ready",
            reason: "写操作可用",
            blocks_mutations: false,
            blockers: [],
          },
        },
        domains: [
          {
            key: "workbench",
            label: "关联台",
            route: "/",
            level: "blocked",
            status: "failed",
            reason: "关联关系不可用",
            details: ["projection failed"],
            read_models: ["workbench_relation"],
            read_model_scopes: [],
            workers: ["workbench-relation"],
            job_ids: [],
            updated_at: "2026-06-13T17:30:00+08:00",
          },
        ],
        background_tasks: [],
        alerts: [],
      },
    };

    renderProbe();

    await waitFor(() => {
      const status = screen.getByLabelText("health");
      expect(status).toHaveAttribute("data-level", "blocked");
      expect(status).toHaveAttribute("data-blocks", "false");
      expect(status).toHaveAttribute("data-can-mutate", "true");
    });
  });

  it("preserves OA dirty source when app status overview is present", async () => {
    mocked.appHealth = {
      status: "busy",
      session: { status: "authenticated" },
      oa_sync: { status: "idle", message: "OA 有待处理变更", dirty_scopes: ["2026-03"] },
      workbench_matching: { status: "ready", dirty_scopes: [] },
      background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
      app_status: {
        version: 1,
        generated_at: "2026-06-13T17:30:00+08:00",
        overall: {
          level: "busy",
          color: "yellow",
          reason: "关联台待刷新",
          blocks_mutations: false,
          write_safety: {
            status: "ready",
            reason: "写操作可用",
            blocks_mutations: false,
            blockers: [],
          },
        },
        domains: [
          {
            key: "workbench",
            label: "关联台",
            route: "/",
            level: "ok",
            status: "ready",
            reason: "关联台已同步",
            details: [],
            read_models: ["workbench_relation"],
            read_model_scopes: [],
            workers: ["workbench-relation"],
            job_ids: [],
            updated_at: "2026-06-13T17:30:00+08:00",
          },
        ],
        background_tasks: [],
        alerts: [],
      },
    };

    renderProbe();

    await waitFor(() => {
      const status = screen.getByLabelText("health");
      expect(status).toHaveAttribute("data-level", "busy");
      expect(status).toHaveAttribute("data-reason", "关联台待刷新");
      expect(status).toHaveAttribute("data-blocks", "false");
      expect(status).toHaveAttribute("data-can-mutate", "true");
      expect(status).toHaveTextContent("\"oaSync\":\"dirty\"");
    });
  });

  it("keeps matching worker activity out of the global page progress message", async () => {
    mocked.appHealth = {
      status: "busy",
      session: { status: "authenticated" },
      oa_sync: { status: "synced", message: "OA 已同步", dirty_scopes: [] },
      workbench_matching: {
        status: "rebuilding",
        dirty_scopes: [],
        matching_running_scopes: ["2026-03"],
      },
      background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
    };
    renderProbe();
    await waitFor(() => {
      expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "busy");
      expect(screen.getByLabelText("health").getAttribute("data-reason")).not.toContain("正式配对关系");
    });
  });

  it("does not treat succeeded jobs as running AppHealth work", async () => {
    mocked.jobs = [{
      jobId: "job-succeeded",
      type: "file_import",
      label: "导入发票",
      shortLabel: "导入发票完成",
      status: "succeeded",
    }];
    renderProbe();
    await waitFor(() => {
      expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "ok");
      expect(screen.getByLabelText("health")).toHaveAttribute("data-reason", "系统状态正常");
    });
  });

  it("reports yellow when workbench matching is stale", async () => {
    mocked.appHealth = {
      session: { status: "authenticated" },
      oa_sync: { status: "synced", dirty_scopes: [] },
      workbench_matching: { status: "stale", dirty_scopes: ["oa"] },
      background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
    };
    renderProbe();
    await waitFor(() => {
      expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "busy");
      expect(screen.getByLabelText("health")).toHaveAttribute("data-reason", "关联台待刷新");
    });
    expect(screen.getByLabelText("health")).toHaveTextContent("\"oaSync\":\"idle\"");
    expect(screen.getByLabelText("health")).toHaveTextContent("\"workbench\":\"stale\"");
  });

  it("loads app health through bounded polling", async () => {
    mocked.appHealth = {
      status: "ok",
      generated_at: "2026-05-06T09:01:00+08:00",
      session: { status: "authenticated" },
      oa_sync: { status: "synced", dirty_scopes: [] },
      workbench_matching: { status: "ready", dirty_scopes: [] },
      background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
    };
    renderProbe();

    await waitFor(() => {
      expect(fetchAppHealth).toHaveBeenCalled();
      expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "ok");
    });
  });
});
