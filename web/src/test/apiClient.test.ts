import { afterEach, describe, expect, test, vi } from "vitest";

describe("apiClient", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
    vi.useRealTimers();
    vi.restoreAllMocks();
    window.history.pushState({}, "", "/");
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

  test("falls back to canonical fin-ops API prefix when root API returns the SPA shell under fin-ops", async () => {
    window.history.pushState({}, "", "/fin-ops/oa-pending-payments");
    vi.resetModules();
    const fetchSpy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response("<!doctype html><html><body>fin-ops shell</body></html>", {
          status: 200,
          headers: { "Content-Type": "text/html" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    const { apiRequestJson } = await import("../features/apiClient");

    await expect(apiRequestJson<{ ok: boolean }>("/api/oa-pending-payments/auto-reconcile-bank-transactions", {
      method: "POST",
      body: "{}",
    })).resolves.toEqual({ ok: true });
    expect(fetchSpy.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/oa-pending-payments/auto-reconcile-bank-transactions",
      "/fin-ops-api/api/oa-pending-payments/auto-reconcile-bank-transactions",
    ]);
  });

  test("falls back to canonical fin-ops API prefix when a root API request returns HTML outside the fin-ops page path", async () => {
    window.history.pushState({}, "", "/oa-pending-payments");
    vi.resetModules();
    const fetchSpy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response("<!doctype html><html><body>spa shell</body></html>", {
          status: 200,
          headers: { "Content-Type": "text/html" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ rows: [], pagination: { total: 0 } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    const { apiRequestJson } = await import("../features/apiClient");

    await expect(apiRequestJson("/api/oa-pending-payments/bank-transaction-candidates?relation_status=all&page=1&page_size=100"))
      .resolves.toEqual({ rows: [], pagination: { total: 0 } });
    expect(fetchSpy.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/oa-pending-payments/bank-transaction-candidates?relation_status=all&page=1&page_size=100",
      "/fin-ops-api/api/oa-pending-payments/bank-transaction-candidates?relation_status=all&page=1&page_size=100",
    ]);
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

  test("turns an explicit request timeout into a structured API error", async () => {
    vi.useFakeTimers();
    vi.stubEnv("VITE_API_BASE_PATH", "/fin-ops-api/");
    vi.resetModules();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((_url, init) => new Promise((_resolve, reject) => {
      const signal = (init as RequestInit | undefined)?.signal;
      signal?.addEventListener("abort", () => {
        reject(new DOMException("Aborted", "AbortError"));
      });
    }));

    const { ApiClientError, apiRequestJson } = await import("../features/apiClient");
    const pendingRequest = apiRequestJson("/api/session/me", { method: "GET" }, {
      timeoutMs: 50,
      timeoutMessage: "会话校验超时。",
    });
    const rejection = expect(pendingRequest).rejects.toMatchObject({
      status: 0,
      code: "request_timeout",
      message: "会话校验超时。",
      url: "/fin-ops-api/api/session/me",
    });
    const instanceRejection = expect(pendingRequest).rejects.toBeInstanceOf(ApiClientError);

    await vi.advanceTimersByTimeAsync(50);

    await rejection;
    await instanceRejection;
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });
});
