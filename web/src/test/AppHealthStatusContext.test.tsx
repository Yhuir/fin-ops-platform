import { act, render, screen, waitFor } from "@testing-library/react";
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
  jobs: [] as Array<{ status: string }>,
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
      workbench_read_model: { status: "ready", dirty_scopes: [], stale_scopes: [], rebuilding_scopes: [] },
      background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
      dependencies: {},
    }),
    fetchOaSyncStatus: vi.fn(async () => ({ status: "synced", dirty_scopes: [] })),
  };
});

type MockEventSourceInstance = {
  url: string;
  options?: EventSourceInit;
  close: ReturnType<typeof vi.fn>;
  onerror: ((event: Event) => void) | null;
  listeners: Map<string, Array<(event: MessageEvent) => void>>;
  addEventListener: (type: string, listener: (event: MessageEvent) => void) => void;
};

const eventSourceInstances: MockEventSourceInstance[] = [];

function installMockEventSource() {
  eventSourceInstances.length = 0;
  const MockEventSource = vi.fn((url: string, options?: EventSourceInit) => {
    const instance: MockEventSourceInstance = {
      url,
      options,
      close: vi.fn(),
      onerror: null,
      listeners: new Map(),
      addEventListener: vi.fn((type: string, listener: (event: MessageEvent) => void) => {
        const listeners = instance.listeners.get(type) ?? [];
        listeners.push(listener);
        instance.listeners.set(type, listeners);
      }),
    };
    eventSourceInstances.push(instance);
    return instance;
  });
  vi.stubGlobal("EventSource", MockEventSource);
  return MockEventSource;
}

function emitAppHealthSnapshot(payload: ApiAppHealthPayload) {
  const instance = eventSourceInstances[0];
  expect(instance).toBeDefined();
  const listeners = instance.listeners.get("app_health") ?? [];
  expect(listeners.length).toBeGreaterThan(0);
  act(() => {
    listeners.forEach((listener) => listener(new MessageEvent("app_health", {
      data: JSON.stringify(payload),
    })));
  });
}

function emitSseError() {
  const instance = eventSourceInstances[0];
  expect(instance).toBeDefined();
  act(() => {
    instance.onerror?.(new Event("error"));
  });
}

const { fetchAppHealth } = await import("../features/appHealth/api");
const { AppHealthStatusProvider, useAppHealthStatus } = await import("../contexts/AppHealthStatusContext");

function StatusProbe() {
  const healthStatus = useAppHealthStatus();
  return (
    <output
      aria-label="health"
      data-blocks={String(healthStatus.blocksMutations)}
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
    mocked.jobs = [{ status: "running" }];
    renderProbe();
    await waitFor(() => {
      const status = screen.getByLabelText("health");
      expect(status).toHaveAttribute("data-level", "busy");
      expect(status).toHaveAttribute("data-reason", "后台任务处理中");
    });
  });

  it("reports yellow when the backend says the workbench read model is stale", async () => {
    mocked.appHealth = {
      session: { status: "authenticated" },
      oa_sync: { status: "synced", dirty_scopes: [] },
      workbench_read_model: { status: "stale", dirty_scopes: ["oa"], stale_scopes: ["oa"] },
      background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
    };
    renderProbe();
    await waitFor(() => {
      expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "busy");
      expect(screen.getByLabelText("health")).toHaveAttribute("data-reason", "关联台待刷新");
    });
  });

  it("updates from an app_health SSE snapshot before polling", async () => {
    installMockEventSource();
    renderProbe();

    await waitFor(() => {
      expect(eventSourceInstances).toHaveLength(1);
    });

    emitAppHealthSnapshot({
      status: "busy",
      generated_at: "2026-05-06T09:00:00+08:00",
      session: { status: "authenticated" },
      oa_sync: { status: "synced", dirty_scopes: [] },
      workbench_read_model: { status: "stale", dirty_scopes: ["oa"], stale_scopes: ["oa"] },
      background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
    });

    await waitFor(() => {
      expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "busy");
      expect(screen.getByLabelText("health")).toHaveAttribute("data-reason", "关联台待刷新");
    });
    expect(fetchAppHealth).not.toHaveBeenCalled();
  });

  it("falls back to polling after SSE errors", async () => {
    installMockEventSource();
    mocked.appHealth = {
      status: "ok",
      generated_at: "2026-05-06T09:01:00+08:00",
      session: { status: "authenticated" },
      oa_sync: { status: "synced", dirty_scopes: [] },
      workbench_read_model: { status: "ready", dirty_scopes: [], stale_scopes: [], rebuilding_scopes: [] },
      background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
    };
    renderProbe();

    await waitFor(() => {
      expect(eventSourceInstances).toHaveLength(1);
    });
    emitSseError();

    await waitFor(() => {
      expect(eventSourceInstances[0].close).toHaveBeenCalled();
      expect(fetchAppHealth).toHaveBeenCalled();
      expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "ok");
    });
  });
});
