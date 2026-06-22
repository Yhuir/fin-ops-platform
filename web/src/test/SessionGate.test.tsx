import { act, render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import App from "../app/App";
import SessionGate from "../components/auth/SessionGate";
import { SessionProvider } from "../contexts/SessionContext";
import { installMockApiFetch } from "./apiMock";

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("OA session gate", () => {
  test("bootstraps the OA session before rendering business pages", async () => {
    window.history.pushState({}, "", "/");
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(screen.getByText("正在验证 OA 会话...")).toBeInTheDocument();
    expect(await screen.findByRole("navigation", { name: "主导航" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "关联台" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/session/me", expect.any(Object));
  });

  test("renders a forbidden state when the current OA account is not allowed", async () => {
    window.history.pushState({}, "", "/");
    installMockApiFetch({ sessionMode: "forbidden" });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "无权访问财务运营平台" })).toBeInTheDocument();
    expect(screen.getByText("当前 OA 账号未开通访问权限，请联系管理员处理。")).toBeInTheDocument();
  });

  test("renders an expired-session state when the OA token is invalid", async () => {
    window.history.pushState({}, "", "/");
    installMockApiFetch({ sessionMode: "expired" });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "OA 会话已失效" })).toBeInTheDocument();
    expect(screen.getByText("请返回 OA 系统重新登录后再进入财务运营平台。")).toBeInTheDocument();
  });

  test("keeps validating and retries after a transient OA session timeout", async () => {
    vi.useFakeTimers();
    let requestCount = 0;
    const fetchMock = vi.fn((_url: RequestInfo | URL, init?: RequestInit) => {
      requestCount += 1;
      if (requestCount === 1) {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }
      return Promise.resolve(new Response(JSON.stringify({
        user: {
          user_id: "101",
          username: "zhaohua",
          display_name: "赵华",
        },
        roles: ["finance"],
        permissions: ["finops:app:view"],
        allowed: true,
        access_tier: "full_access",
        can_access_app: true,
        can_mutate_data: true,
        can_admin_access: false,
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    });
    global.fetch = fetchMock as typeof fetch;

    render(
      <SessionProvider>
        <SessionGate>
          <div>业务页面已加载</div>
        </SessionGate>
      </SessionProvider>,
    );

    expect(screen.getByText("正在验证 OA 会话...")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(screen.getByText("正在验证 OA 会话...")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "会话校验失败" })).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });

    expect(screen.getByText("业务页面已加载")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
