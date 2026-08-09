import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

describe("OperationHistoryPage", () => {
  test("only loads for an administrator and shows the durable event detail", async () => {
    window.history.pushState({}, "", "/operations/history");
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      sessionDisplayName: "权限管理员",
    });
    render(<App />);

    expect(await screen.findByRole("heading", { name: "操作历史" })).toBeInTheDocument();
    const table = await screen.findByRole("grid", { name: "操作历史" });
    expect(table).toHaveTextContent("权限管理员");
    expect(table).toHaveTextContent("YNSYLP005");
    expect(table).toHaveTextContent("关联台");
    expect(table).toHaveTextContent("页面操作");
    expect(table).not.toHaveTextContent("http_request");
    expect(table).toHaveTextContent("确认关联");

    await userEvent.click(within(table).getByRole("button", { name: "查看确认关联详情" }));
    const drawer = await screen.findByRole("dialog", { name: "操作详情" });
    expect(drawer).toHaveTextContent("关联台");
    expect(drawer).not.toHaveTextContent("/api/workbench/actions/confirm-link");
    expect(drawer).toHaveTextContent("云南昂超商贸有限公司");
    expect(drawer).toHaveTextContent("未配对");
    expect(drawer).toHaveTextContent("已配对");
    expect(drawer).not.toHaveTextContent("internal-relation-1");
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/operations/history/request%3Arequest-1"))).toBe(true);
    });
  });

  test("redirects a non-admin away before loading audit data", async () => {
    window.history.pushState({}, "", "/operations/history");
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "full_access",
      sessionUsername: "YNSYLP006",
    });
    render(<App />);

    expect(await screen.findByRole("heading", { name: "关联台" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "操作历史" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/operations/history"))).toBe(false);
  });
});
