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
          page_size: 50,
          total: 0,
          has_more: false,
          next_cursor: null,
          row_counts: { oa: 0, bank: 0, invoice: 0, rows: 0 },
          groups: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const { fetchWorkbenchGroupsPage } = await import("../features/workbench/api");

    await fetchWorkbenchGroupsPage("all", "unpaired", "opaque-next", 50, undefined, { detailLevel: "summary" });

    const [input, init] = fetchSpy.mock.calls[0];
    expect(String(input)).toBe("/fin-ops-api/api/workbench/groups?month=all&zone=unpaired&page_size=50&cursor=opaque-next&detail_level=summary");
    expect(init?.credentials).toBe("include");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer prod-token");
  });

  test("routes direct filter options through runtime api path", async () => {
    vi.doMock("../app/runtime", () => ({
      APP_BASE_PATH: "/fin-ops/",
      API_BASE_PATH: "/fin-ops-api/",
      apiUrl: (path: string) => `/fin-ops-api${path.startsWith("/") ? path : `/${path}`}`,
      isOaEmbeddedMode: () => true,
    }));
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          options: [{ value: "供应商A", label: "供应商A" }],
          page_size: 50,
          has_more: false,
          next_cursor: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const { fetchWorkbenchFilterOptions } = await import("../features/workbench/api");

    const result = await fetchWorkbenchFilterOptions("all", "unpaired", {
      pane: "invoice",
      facet: "column",
      column: "sellerName",
      cursor: null,
    });

    expect(result.options).toEqual([{ value: "供应商A", label: "供应商A", missing: false }]);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(String(fetchSpy.mock.calls[0][0])).toBe(
      "/fin-ops-api/api/workbench/filter-options?month=all&zone=unpaired&pane=invoice&facet=column&page_size=100&column=sellerName",
    );
    expect(fetchSpy.mock.calls[0][1]).toMatchObject({ method: "GET" });
  });

});
