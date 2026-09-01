import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchSessionMe, readOATokenCookie } from "../features/session/api";

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
  vi.useRealTimers();
  document.cookie = "Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("session api", () => {
  test("reads OA Admin-Token from cookie", () => {
    expect(readOATokenCookie("foo=bar; Admin-Token=abc123; x=y")).toBe("abc123");
  });

  test("sends Authorization header from Admin-Token cookie", async () => {
    document.cookie = "Admin-Token=mock-cookie-token; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          user: {
            user_id: "101",
            username: "liuji",
            display_name: "刘际涛",
          },
          roles: ["finance"],
          permissions: ["finops:app:view"],
          allowed: true,
          can_access_app: true,
          can_admin_access: false,
          allowed_page_keys: ["bank-details"],
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );
    global.fetch = fetchMock as typeof fetch;

    const payload = await fetchSessionMe();

    expect(fetchMock).toHaveBeenCalledWith("/api/session/me", expect.objectContaining({
      method: "GET",
      credentials: "include",
    }));
    const requestInit = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined;
    const requestHeaders = requestInit?.headers as Headers | undefined;
    expect(requestHeaders?.get("Authorization")).toBe("Bearer mock-cookie-token");
    expect(payload.user.username).toBe("liuji");
    expect(payload.allowed).toBe(true);
    expect(payload.canAccessApp).toBe(true);
    expect(payload.canAdminAccess).toBe(false);
    expect(payload.allowedPageKeys).toEqual(["bank-details"]);
  });

  test("keeps OA roles and permission informational when the canonical session is denied", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      user: {
        user_id: "106",
        username: "YNSYLP006",
        display_name: "权限攻击样例",
      },
      roles: ["finance", "business", "finops_user"],
      permissions: ["finops:app:view"],
      allowed: false,
      can_access_app: false,
      can_admin_access: false,
      allowed_page_keys: [],
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })) as typeof fetch;

    const payload = await fetchSessionMe();

    expect(payload).toMatchObject({
      roles: ["finance", "business", "finops_user"],
      permissions: ["finops:app:view"],
      allowed: false,
      canAccessApp: false,
      canAdminAccess: false,
      allowedPageKeys: [],
    });
  });

  test("fails the OA session bootstrap when the session endpoint never returns", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn((_url: RequestInfo | URL, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => {
        reject(new DOMException("Aborted", "AbortError"));
      });
    }));
    global.fetch = fetchMock as typeof fetch;

    const pendingSession = fetchSessionMe();
    const rejection = expect(pendingSession).rejects.toMatchObject({
      name: "SessionApiError",
      status: 0,
      code: "request_timeout",
      message: "OA 会话校验超时，请检查网络或稍后重试。",
    });

    await vi.advanceTimersByTimeAsync(10_000);

    await rejection;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
