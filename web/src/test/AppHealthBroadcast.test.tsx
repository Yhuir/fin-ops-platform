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
    fetchAppHealth: vi.fn(async () => mocked.appHealth ?? healthyPayload("2026-05-06T10:00:00+08:00")),
    fetchOaSyncStatus: vi.fn(async () => ({ status: "synced", dirty_scopes: [] })),
  };
});

type MockBroadcastChannelInstance = {
  name: string;
  close: ReturnType<typeof vi.fn>;
  postMessage: ReturnType<typeof vi.fn>;
  onmessage: ((event: MessageEvent) => void) | null;
};

const broadcastInstances: MockBroadcastChannelInstance[] = [];

function healthyPayload(generatedAt: string): ApiAppHealthPayload {
  return {
    status: "ok",
    generated_at: generatedAt,
    session: { status: "authenticated" },
    oa_sync: { status: "synced", dirty_scopes: [] },
    workbench_read_model: { status: "ready", dirty_scopes: [], stale_scopes: [], rebuilding_scopes: [] },
    background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
  };
}

function stalePayload(generatedAt: string): ApiAppHealthPayload {
  return {
    status: "busy",
    generated_at: generatedAt,
    session: { status: "authenticated" },
    oa_sync: { status: "synced", dirty_scopes: [] },
    workbench_read_model: { status: "stale", dirty_scopes: ["oa"], stale_scopes: ["oa"] },
    background_jobs: { active: 0, queued: 0, running: 0, attention: 0 },
  };
}

function installMockBroadcastChannel() {
  broadcastInstances.length = 0;
  const MockBroadcastChannel = vi.fn((name: string) => {
    const instance: MockBroadcastChannelInstance = {
      name,
      close: vi.fn(),
      postMessage: vi.fn(),
      onmessage: null,
    };
    broadcastInstances.push(instance);
    return instance;
  });
  vi.stubGlobal("BroadcastChannel", MockBroadcastChannel);
}

function emitBroadcastSnapshot(payload: ApiAppHealthPayload) {
  const instance = broadcastInstances[0];
  expect(instance).toBeDefined();
  act(() => {
    instance.onmessage?.({
      data: {
        type: "app-health:snapshot",
        generatedAt: payload.generated_at ?? "2026-05-06T00:00:00+08:00",
        payload,
      },
    } as MessageEvent);
  });
}

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

describe("AppHealth BroadcastChannel sync", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    vi.stubGlobal("EventSource", undefined);
    installMockBroadcastChannel();
    mocked.appHealth = healthyPayload("2026-05-06T10:00:00+08:00");
  });

  it("accepts a newer snapshot from another tab without broadcasting it again", async () => {
    renderProbe();

    await waitFor(() => {
      expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "ok");
      expect(broadcastInstances).toHaveLength(1);
      expect(broadcastInstances[0].postMessage).toHaveBeenCalledTimes(1);
    });
    broadcastInstances[0].postMessage.mockClear();

    emitBroadcastSnapshot(stalePayload("2026-05-06T11:00:00+08:00"));

    await waitFor(() => {
      expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "busy");
      expect(screen.getByLabelText("health")).toHaveAttribute("data-reason", "关联台待刷新");
    });
    expect(broadcastInstances[0].postMessage).not.toHaveBeenCalled();
  });

  it("ignores a snapshot older than the current local snapshot", async () => {
    renderProbe();

    await waitFor(() => {
      expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "ok");
      expect(broadcastInstances).toHaveLength(1);
    });

    emitBroadcastSnapshot(stalePayload("2026-05-06T09:00:00+08:00"));

    expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "ok");
    expect(screen.getByLabelText("health")).toHaveAttribute("data-reason", "系统状态正常");
  });

  it("continues to work when BroadcastChannel is unavailable", async () => {
    vi.stubGlobal("BroadcastChannel", undefined);

    renderProbe();

    await waitFor(() => {
      expect(screen.getByLabelText("health")).toHaveAttribute("data-level", "ok");
      expect(screen.getByLabelText("health")).toHaveAttribute("data-reason", "系统状态正常");
    });
  });
});
