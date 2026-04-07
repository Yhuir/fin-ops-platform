import { render, screen } from "@testing-library/react";

import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

describe("OA session gate", () => {
  test("bootstraps the OA session before rendering business pages", async () => {
    window.history.pushState({}, "", "/");
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(screen.getByText("正在验证 OA 会话...")).toBeInTheDocument();
    expect(await screen.findByText("赵华")).toBeInTheDocument();
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
});
