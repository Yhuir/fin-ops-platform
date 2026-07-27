import { afterEach, describe, expect, test, vi } from "vitest";

describe("workbench api runtime base path", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
    vi.doUnmock("../app/runtime");
    document.cookie = "Admin-Token=; Max-Age=0; path=/";
  });

  test("routes production /fin-ops workbench calls through /fin-ops-api with OA auth", async () => {
    vi.doMock("../app/runtime", () => ({
      APP_BASE_PATH: "/fin-ops/",
      API_BASE_PATH: "/fin-ops-api/",
      apiUrl: (path: string) => `/fin-ops-api${path.startsWith("/") ? path : `/${path}`}`,
      isOaEmbeddedMode: () => true,
    }));
    document.cookie = "Admin-Token=prod-token; path=/";

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "all",
          zone: "unpaired",
          page: 1,
          page_size: 50,
          total: 0,
          has_more: false,
          groups: [],
          read_model_status: "fresh",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const { fetchWorkbenchGroupsPage } = await import("../features/workbench/api");

    await fetchWorkbenchGroupsPage("all", "unpaired", 1, 50, undefined, { detailLevel: "summary" });

    const [input, init] = fetchSpy.mock.calls[0];
    expect(String(input)).toBe("/fin-ops-api/api/workbench/groups?month=all&zone=unpaired&page=1&page_size=50&detail_level=summary");
    expect(init?.credentials).toBe("include");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer prod-token");
  });

  test("routes refresh status through runtime api path", async () => {
    vi.doMock("../app/runtime", () => ({
      APP_BASE_PATH: "/fin-ops/",
      API_BASE_PATH: "/fin-ops-api/",
      apiUrl: (path: string) => `/fin-ops-api${path.startsWith("/") ? path : `/${path}`}`,
      isOaEmbeddedMode: () => true,
    }));
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          scope_key: "all",
          read_model_status: "fresh",
          dirty_scopes: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const { fetchWorkbenchRefreshStatus } = await import("../features/workbench/api");

    const status = await fetchWorkbenchRefreshStatus("all");

    expect(status.readModelStatus).toBe("fresh");
    expect(String(fetchSpy.mock.calls[0][0])).toBe("/fin-ops-api/api/workbench/refresh-status?month=all");
  });

  test("subscribes to workbench events through runtime api path", async () => {
    vi.doMock("../app/runtime", () => ({
      APP_BASE_PATH: "/fin-ops/",
      API_BASE_PATH: "/fin-ops-api/",
      apiUrl: (path: string) => `/fin-ops-api${path.startsWith("/") ? path : `/${path}`}`,
      isOaEmbeddedMode: () => true,
    }));
    const instances: Array<{ url: string; options?: EventSourceInit; close: () => void; addEventListener: ReturnType<typeof vi.fn> }> = [];
    const MockEventSource = vi.fn((url: string, options?: EventSourceInit) => {
      const instance = {
        url,
        options,
        close: vi.fn(),
        addEventListener: vi.fn(),
      };
      instances.push(instance);
      return instance;
    });
    vi.stubGlobal("EventSource", MockEventSource);
    const { subscribeWorkbenchRefreshEvents } = await import("../features/workbench/api");

    const subscription = subscribeWorkbenchRefreshEvents("all", vi.fn(), vi.fn());

    expect(subscription).not.toBeNull();
    expect(instances[0].url).toBe("/fin-ops-api/api/workbench/events?month=all");
    expect(instances[0].options?.withCredentials).toBe(true);
    subscription?.close();
    expect(instances[0].close).toHaveBeenCalled();
  });
});
