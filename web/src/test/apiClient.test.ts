import { afterEach, describe, expect, test, vi } from "vitest";

describe("apiClient", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  test("normalizes production API base path and sends OA auth credentials", async () => {
    vi.stubEnv("VITE_API_BASE_PATH", "/fin-ops-api/");
    vi.resetModules();
    document.cookie = "Admin-Token=oa-token-123";
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const { apiRequestJson } = await import("../features/apiClient");

    await expect(apiRequestJson<{ ok: boolean }>("/api/example", { method: "GET" })).resolves.toEqual({ ok: true });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0][0]).toBe("/fin-ops-api/api/example");
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe("include");
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer oa-token-123");
  });

  test("fails fast when a proxied API request returns HTML", async () => {
    vi.stubEnv("VITE_API_BASE_PATH", "/fin-ops-api/");
    vi.resetModules();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("<!doctype html><html><body>vite fallback</body></html>", {
        status: 200,
        headers: { "Content-Type": "text/html" },
      }),
    );

    const { apiRequestJson } = await import("../features/apiClient");

    await expect(apiRequestJson("/api/example")).rejects.toThrow("接口返回了 HTML 页面");
  });

  test("surfaces structured API errors with status and error code", async () => {
    vi.stubEnv("VITE_API_BASE_PATH", "/fin-ops-api/");
    vi.resetModules();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify({ error: "category_version_conflict", message: "银行明细标签已更新" }), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      }),
    ));

    const { ApiClientError, apiRequestJson } = await import("../features/apiClient");

    await expect(apiRequestJson("/api/bank-details/categories")).rejects.toMatchObject({
      name: "ApiClientError",
      status: 409,
      code: "category_version_conflict",
      message: "银行明细标签已更新",
    });
    await expect(apiRequestJson("/api/bank-details/categories")).rejects.toBeInstanceOf(ApiClientError);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });
});
