import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchSessionMe, readOATokenCookie } from "../features/session/api";

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
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
          access_tier: "read_export_only",
          can_access_app: true,
          can_mutate_data: false,
          can_admin_access: false,
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
    expect(payload.accessTier).toBe("read_export_only");
    expect(payload.canAccessApp).toBe(true);
    expect(payload.canMutateData).toBe(false);
    expect(payload.canAdminAccess).toBe(false);
  });
});
