import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

const WORKBENCH_RENDER_TIMEOUT = 3000;

function getShellHeader() {
  const header = document.querySelector<HTMLElement>(".global-header");
  expect(header).not.toBeNull();
  return header as HTMLElement;
}

describe("Finance operations shell", () => {
  test("loads the workbench as an all-time view and keeps the month picker scoped to tax offset", async () => {
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();
    expect(screen.getByText("财务运营平台")).toBeInTheDocument();
    expect(screen.getByText("溯源办公系统")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        name: "OA & 银行流水 & 进销项发票关联台",
      }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "年月选择" })).not.toBeInTheDocument();
    expect(within(getShellHeader()).queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
    expect(within(getShellHeader()).queryByRole("button", { name: "设置" })).not.toBeInTheDocument();
    expect(within(getShellHeader()).queryByRole("button", { name: "导入中心" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设置" })).toHaveAttribute("href", "/settings");
    expect(screen.getByRole("link", { name: "导入中心" })).toHaveAttribute("href", "/imports");
    expect(screen.getByRole("link", { name: "银行流水导入" })).toHaveAttribute("href", "/");
    await user.click(screen.getByRole("link", { name: "关联台搜索" }));
    expect(await screen.findByRole("dialog", { name: "关联台搜索" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭搜索" }));
    expect(await screen.findByText("王青", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "税金抵扣" }));

    expect(
      screen.getByRole("heading", { name: "税金抵扣计划与试算" }),
    ).toBeInTheDocument();
    expect(within(getShellHeader()).queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
    expect(within(getShellHeader()).queryByRole("button", { name: "设置" })).not.toBeInTheDocument();
    expect(within(getShellHeader()).queryByRole("button", { name: "导入中心" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设置" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "导入中心" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "年月选择" })).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "年份" })).toHaveAttribute("aria-valuenow", "2026");
    expect(screen.getByRole("spinbutton", { name: "月份" })).toHaveAttribute("aria-valuenow", "3");
    expect(fetchMock).toHaveBeenCalledWith("/api/workbench?month=all", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/api/tax-offset?month=2026-03", expect.any(Object));
  });

  test("keeps the shell sidebar controls stable on cost statistics", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();
    expect(within(getShellHeader()).queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设置" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "导入中心" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "成本统计" })).toHaveAttribute("aria-current", "page");
  });

  test("hides the global workbench title block while a zone is expanded", async () => {
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();
    expect(screen.getByText("财务运营平台")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /放大 未配对/ }));

    expect(document.body.classList.contains("workbench-focus-mode")).toBe(true);

    await user.click(screen.getByRole("button", { name: /恢复 未配对/ }));

    expect(document.body.classList.contains("workbench-focus-mode")).toBe(false);
    expect(screen.getByText("财务运营平台")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "年月选择" })).not.toBeInTheDocument();
  });

  test("keeps the sidebar brand available inside the OA iframe", async () => {
    window.history.pushState({}, "", "/?embedded=oa");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "关联台" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "展开菜单" }));
    expect(await screen.findByText("财务运营平台")).toBeInTheDocument();
    expect(screen.getByText("溯源办公系统")).toBeInTheDocument();
    expect(document.querySelector(".app-shell.embedded-shell")).not.toBeNull();
    expect(document.querySelector(".page-body.embedded")).not.toBeNull();
  });

  test("shows OA status in the shell header and warns when OA data is incomplete", async () => {
    window.history.pushState({}, "", "/");
    installMockApiFetch({
      workbenchOaStatus: {
        code: "error",
        message: "OA 连接失败",
      },
    });

    render(<App />);

    const statusIndicator = await screen.findByRole("status", { name: "OA 连接失败" }, { timeout: WORKBENCH_RENDER_TIMEOUT });
    expect(statusIndicator).toHaveClass("error");
    expect(statusIndicator.textContent).toBe("");
    expect(screen.getByText("OA 连接失败，本次结果未包含完整 OA 数据。")).toBeInTheDocument();
  });

  test("navigates to the standalone settings page from the shell sidebar", async () => {
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华", {}, { timeout: WORKBENCH_RENDER_TIMEOUT })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "设置" }));

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "关联台设置" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设置" })).toHaveAttribute("aria-current", "page");
  });

  test("renders the standalone settings route directly", async () => {
    window.history.pushState({}, "", "/settings");
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "关联台设置" })).not.toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "设置" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "导入中心" })).toBeInTheDocument();
  });

  test("opens the workbench bank import dialog from the shell sidebar without leaving the app", async () => {
    window.history.pushState({}, "", "/cost-statistics");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "成本统计" })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "银行流水导入" }));

    expect(await screen.findByRole("heading", { name: "银行流水导入" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
    expect(window.location.search).toBe("");
  });
});
