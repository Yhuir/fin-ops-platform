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
          zone: "open",
          page: 1,
          page_size: 50,
          total: 0,
          has_more: false,
          groups: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const { fetchWorkbenchGroupsPage } = await import("../features/workbench/api");

    await fetchWorkbenchGroupsPage("all", "open", 1, 50, undefined, { detailLevel: "summary" });

    const [input, init] = fetchSpy.mock.calls[0];
    expect(String(input)).toBe("/fin-ops-api/api/workbench/groups?month=all&zone=open&page=1&page_size=50&detail_level=summary");
    expect(init?.credentials).toBe("include");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer prod-token");
  });
});
